import os

import bpy
from mathutils import Vector

from render_lib.banner import log_render_config
from render_lib.cameras import build_cameras
from render_lib.compositor import setup_alpha_threshold_compositor
from render_lib.cycles_setup import configure_render_engine
from render_lib.images import find_image_node, replace_missing_image_nodes
from render_lib.lighting import (
    aim_key_light_for_camera,
    isolate_phone_from_indirect,
    setup_key_light,
)
from render_lib.logging_utils import log
from render_lib.screen_emission import gate_screen_emission
from render_lib.screenshots import scan_screenshots
from render_lib.settings import Outputs, Settings
from render_lib.shadow import setup_shadow_catcher
from render_lib.svg_export import generate_svg_from_png
from render_lib.uv_autofit import disable_screen_uv_autofit, fit_screen_uvs


def _build_passes(outputs: Outputs):
    passes = []
    if outputs.png_no_shadow or outputs.svg_no_shadow:
        passes.append({
            "label":             "no-shadow",
            "shadow_catcher_on": False,
            "save_png":          outputs.png_no_shadow,
            "save_svg":          outputs.svg_no_shadow,
            "png_suffix":        "__noshadow",
        })
    if outputs.png_with_shadow:
        passes.append({
            "label":             "shadow",
            "shadow_catcher_on": True,
            "save_png":          True,
            "save_svg":          False,
            "png_suffix":        "",
        })
    return passes


def _render_one_shot(scene, cam, key_light, phone_center, resolved, pass_cfg,
                     image_node, out_dir, safe_screen, angle_name, settings):
    scene.camera = cam
    base_name = f"{safe_screen}__{angle_name}"
    png_path = os.path.join(out_dir, f"{base_name}{pass_cfg['png_suffix']}.png")
    scene.render.filepath = png_path

    if key_light is not None:
        aim_key_light_for_camera(
            key_light, cam, phone_center,
            elevation_deg=resolved.key_light_elevation_deg,
            shadow_azimuth_deg=resolved.key_light_shadow_azimuth_deg,
        )
    bpy.context.view_layer.update()
    log(f"Rendering {png_path}")
    bpy.ops.render.render(write_still=True)

    if pass_cfg["save_svg"]:
        svg_path = os.path.join(out_dir, f"{base_name}.svg")
        try:
            generate_svg_from_png(
                png_path, svg_path,
                alpha_threshold=settings.svg_alpha_threshold,
                simplify_tol_px=settings.svg_simplify_tol_px,
            )
        except Exception as exc:
            log(f"[svg] failed to write {svg_path}: {exc}")

    if not pass_cfg["save_png"]:
        try:
            os.remove(png_path)
        except OSError as exc:
            log(f"[warn] could not remove intermediate {png_path}: {exc}")


def _render_pass(scene, phone, phone_center, resolved, pass_cfg, settings,
                 screenshot_files, image_node, image_mat, out_dir, key_light):
    sc_on = pass_cfg["shadow_catcher_on"]

    setup_shadow_catcher(
        scene, phone,
        enabled=sc_on,
        size_multiplier=resolved.shadow_catcher_size,
        z_offset=resolved.shadow_catcher_z,
    )

    isolate_phone_from_indirect(
        phone, enabled=sc_on and resolved.phone_isolate_indirect
    )

    gate_screen_emission(
        image_node, image_mat,
        enabled=sc_on and resolved.screen_emission_isolate,
        allow_glossy=resolved.screen_emission_allow_glossy,
    )

    effective_fit_margin = (
        resolved.shadow_fit_margin if sc_on else resolved.fit_margin
    )
    cams = build_cameras(
        scene, phone, settings.angles, settings.default_lens_mm, effective_fit_margin
    )

    log_render_config(
        scene,
        resolved=resolved,
        shadow_catcher_on=sc_on,
        pass_label=pass_cfg["label"],
    )

    for filepath in screenshot_files:
        img = bpy.data.images.load(filepath, check_existing=True)
        try:
            img.reload()
        except RuntimeError:
            pass
        img.colorspace_settings.name = 'sRGB'
        image_node.image = img

        screen_name = os.path.splitext(os.path.basename(filepath))[0]
        safe_screen = "".join(
            ch if ch.isalnum() or ch in "-_" else "_" for ch in screen_name
        )

        for angle_name, cam in cams:
            _render_one_shot(
                scene, cam, key_light, phone_center, resolved, pass_cfg,
                image_node, out_dir, safe_screen, angle_name, settings,
            )


def render_scene(scene_name, cfg, settings: Settings):
    if scene_name not in bpy.data.scenes:
        log(f"[skip] scene '{scene_name}' not found in this .blend")
        return

    scene = bpy.data.scenes[scene_name]
    bpy.context.window.scene = scene
    log(f"\n=== Rendering scene: {scene_name} ===")
    replace_missing_image_nodes(scene)

    resolved = settings.for_scene(cfg)

    phone = scene.objects.get(cfg["phone_object"])
    if phone is None:
        raise RuntimeError(
            f"Phone object '{cfg['phone_object']}' not in scene '{scene.name}'"
        )

    screen_node_id = cfg.get("screen_node_id", settings.screen_node_id)
    image_node, image_mat = find_image_node(
        phone, cfg["screen_material"], screen_node_id, settings.screen_node_id
    )
    log(f"Image Texture node: '{image_node.name}' in material '{image_mat.name}'")

    if cfg.get("autofit_screen_uvs", True):
        screen_inset = float(cfg.get("screen_inset", 0.0))
        fit_screen_uvs(phone, image_node, image_mat, inset=screen_inset)
    else:
        disable_screen_uv_autofit(image_node, image_mat)
        log(
            f"[uv] autofit disabled for '{scene_name}': using mesh UVs as-is, "
            "Image Texture extension set to CLIP"
        )

    screenshot_files = scan_screenshots(cfg["screens_dir"], settings.supported_exts)
    if not screenshot_files:
        log(f"[skip] no screenshots found in {cfg['screens_dir']}")
        return
    log(f"Found {len(screenshot_files)} screenshot(s) in {cfg['screens_dir']}")

    configure_render_engine(scene, settings)

    scene_outputs = resolved.outputs
    passes = _build_passes(scene_outputs)

    if not passes:
        log(f"[skip] scene '{scene_name}': no outputs enabled in settings")
        return

    enabled_labels = [
        label for label, enabled in (
            ("png_with_shadow", scene_outputs.png_with_shadow),
            ("png_no_shadow",   scene_outputs.png_no_shadow),
            ("svg_no_shadow",   scene_outputs.svg_no_shadow),
        ) if enabled
    ]
    log(f"Outputs:          {', '.join(enabled_labels)}")
    log(f"Render passes:    {', '.join(p['label'] for p in passes)}")

    setup_alpha_threshold_compositor(scene, resolved.alpha_threshold)

    key_light = setup_key_light(
        scene,
        enabled=resolved.key_light,
        strength=resolved.key_light_strength,
        angle_deg=resolved.key_light_angle_deg,
        color=resolved.key_light_color,
        visible_glossy=resolved.key_light_visible_glossy,
        visible_transmission=resolved.key_light_visible_transmission,
    )

    out_dir = os.path.join(bpy.path.abspath(settings.output_dir), scene_name)
    os.makedirs(out_dir, exist_ok=True)

    _bbox_world = [phone.matrix_world @ Vector(c) for c in phone.bound_box]
    phone_center = sum(_bbox_world, Vector()) / 8.0

    for pass_cfg in passes:
        _render_pass(
            scene, phone, phone_center, resolved, pass_cfg, settings,
            screenshot_files, image_node, image_mat, out_dir, key_light,
        )
