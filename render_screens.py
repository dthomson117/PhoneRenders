import bpy
import os
import json
import math
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view

# --- SETTINGS LOADER ------------------------------------------------------
# All tweakable values live in `render_settings.json` next to this script
# (or next to the .blend file). Environment variables override individual
# fields where noted. The defaults below are only used if the JSON file is
# missing or a key is absent.
SETTINGS_FILENAME = "render_settings.json"

DEFAULT_SETTINGS = {
    "output_dir": "//renders/",
    "resolution": {"x": 2160, "y": 3840},
    "resolution_percentage": 100,
    "samples": 256,
    "transparent_background": True,
    "device": "GPU",
    "use_auto_tile": True,
    "tile_size": 1024,
    "use_persistent_data": True,
    "fit_margin": 1.08,
    "default_lens_mm": 50,
    "supported_extensions": [".png", ".jpg", ".jpeg", ".webp"],
    "angles": [
        {"name": "front",                  "tilt_deg": 15, "yaw_deg": 180, "distance_multiplier": 1.0},
        {"name": "threequarter_left",      "tilt_deg": 30, "yaw_deg": 215, "distance_multiplier": 1.0},
        {"name": "threequarter_right",     "tilt_deg": 30, "yaw_deg": 145, "distance_multiplier": 1.0},
        {"name": "threequarter_left_top",  "tilt_deg": 30, "yaw_deg": 325, "distance_multiplier": 1.0},
        {"name": "threequarter_right_top", "tilt_deg": 30, "yaw_deg":  35, "distance_multiplier": 1.0},
        {"name": "hero_top",               "tilt_deg":  0, "yaw_deg":   0, "distance_multiplier": 1.1},
    ],
    "scenes": {
        "iOS": {
            "phone_object":    "iPhone 17 ProMax",
            "screen_material": "17ProMax_Screen",
            "screens_dir":     "//screenshots/iOS/",
            "screen_node_id":  "ScreenTextureiOS",
        },
        "Android": {
            "phone_object":    "Google Pixel 9 Pro XL",
            "screen_material": "GP9XL_Screen",
            "screens_dir":     "//screenshots/Android/",
            "screen_node_id":  "ScreenTextureAndroid",
        },
    },
}


def _candidate_settings_paths():
    paths = []
    env_path = os.environ.get("RENDER_SETTINGS")
    if env_path:
        paths.append(env_path)
    try:
        paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGS_FILENAME))
    except NameError:
        pass
    blend_path = bpy.data.filepath
    if blend_path:
        paths.append(os.path.join(os.path.dirname(blend_path), SETTINGS_FILENAME))
    return paths


def load_settings():
    for path in _candidate_settings_paths():
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                print(f"Loaded settings from: {path}")
                merged = dict(DEFAULT_SETTINGS)
                merged.update(data)
                return merged
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[warn] could not parse settings at {path}: {exc}")
    print(f"[warn] {SETTINGS_FILENAME} not found - using built-in defaults.")
    return dict(DEFAULT_SETTINGS)


SETTINGS = load_settings()

SCENE_CONFIGS = SETTINGS["scenes"]
OUTPUT_DIR    = SETTINGS["output_dir"]
RES_X         = int(SETTINGS["resolution"]["x"])
RES_Y         = int(SETTINGS["resolution"]["y"])
SAMPLES        = int(os.environ.get("RENDER_SAMPLES", SETTINGS["samples"]))
TRANSPARENT_BG = bool(SETTINGS["transparent_background"])
SUPPORTED_EXTS = tuple(ext.lower() for ext in SETTINGS["supported_extensions"])
FIT_MARGIN      = float(SETTINGS["fit_margin"])
DEFAULT_LENS_MM = float(SETTINGS["default_lens_mm"])
SCREEN_NODE_ID  = str(SETTINGS.get("screen_node_id", "ScreenTexture"))
RES_PERCENT     = int(SETTINGS.get("resolution_percentage", 100))
DEVICE          = str(SETTINGS.get("device", "GPU")).upper()
USE_AUTO_TILE   = bool(SETTINGS.get("use_auto_tile", True))
TILE_SIZE       = int(SETTINGS.get("tile_size", 1024))
USE_PERSISTENT  = bool(SETTINGS.get("use_persistent_data", True))

ANGLES = [
    (a["name"], a["tilt_deg"], a["yaw_deg"], a.get("distance_multiplier", 1.0))
    for a in SETTINGS["angles"]
]

# Phone orientation: screen faces +Z, UI top is at -Y, UI right is +X.
SCREEN_NORMAL = Vector(( 0,  0,  1))
UI_UP         = Vector(( 0, -1,  0))
# --------------------------------------------------------------------------

def setup_gpu():
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for dev_type in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL'):
        try:
            prefs.compute_device_type = dev_type
            prefs.get_devices()
            break
        except TypeError:
            continue
    enabled = []
    for device in prefs.devices:
        device.use = (device.type != 'CPU')
        if device.use:
            enabled.append(f"{device.type}: {device.name}")
    print(f"Cycles compute_device_type = {prefs.compute_device_type}")
    for line in enabled:
        print(f"  - {line}")
    if not enabled:
        print("  (no GPU detected - falling back to CPU)")

setup_gpu()


def _image_file_exists(img):
    if img is None or img.packed_file:
        return True
    if img.source not in {'FILE', 'SEQUENCE', 'MOVIE'}:
        return True
    if not img.filepath:
        return True
    return os.path.isfile(bpy.path.abspath(img.filepath))


def _missing_image_fallback():
    fallback = bpy.data.images.get("_MissingExternalImageFallback")
    if fallback is None:
        fallback = bpy.data.images.new("_MissingExternalImageFallback", 1, 1, alpha=True)
        fallback.pixels[:] = (0.0, 0.0, 0.0, 0.0)
    return fallback


def replace_missing_image_nodes(scene):
    """Stop stale external image references in the .blend from breaking renders."""
    fallback = None
    inspected_node_trees = set()

    def inspect_node_tree(node_tree, owner_name):
        nonlocal fallback
        if node_tree is None or node_tree.name in inspected_node_trees:
            return
        inspected_node_trees.add(node_tree.name)

        for node in node_tree.nodes:
            if node.bl_idname == "ShaderNodeTexImage" and node.image:
                if not _image_file_exists(node.image):
                    if fallback is None:
                        fallback = _missing_image_fallback()
                    missing_path = bpy.path.abspath(node.image.filepath)
                    print(
                        f"[warn] replacing missing image on '{owner_name}' "
                        f"node '{node.name}': {missing_path}"
                    )
                    node.image = fallback
            elif node.bl_idname == "ShaderNodeGroup":
                inspect_node_tree(node.node_tree, f"{owner_name}/{node.name}")

    if scene.world and scene.world.use_nodes:
        inspect_node_tree(scene.world.node_tree, scene.world.name)

    for obj in scene.objects:
        for slot in obj.material_slots:
            mat = slot.material
            if mat and mat.use_nodes:
                inspect_node_tree(mat.node_tree, mat.name)


def find_image_node(phone, screen_material_name, screen_node_id=None):
    """Find the screen Image Texture node on the phone.

    Preference order:
      1. An Image Texture node whose name or label matches ``screen_node_id``
         (search all materials on the phone, plus the named screen material).
      2. The first Image Texture node found in the named screen material.
      3. The first Image Texture node found in any of the phone's materials.

    Tagging a node by name/label (default: 'ScreenTexture') is the recommended
    setup - it removes any ambiguity when a material has multiple image nodes.
    """
    candidate_mats = []
    if screen_material_name in bpy.data.materials:
        candidate_mats.append(bpy.data.materials[screen_material_name])
    for slot in phone.material_slots:
        if slot.material and slot.material not in candidate_mats:
            candidate_mats.append(slot.material)

    if screen_node_id:
        target = screen_node_id.strip().lower()
        for mat in candidate_mats:
            if not mat.use_nodes:
                continue
            for node in mat.node_tree.nodes:
                if node.bl_idname != "ShaderNodeTexImage":
                    continue
                if node.name.strip().lower() == target or node.label.strip().lower() == target:
                    print(
                        f"Matched screen node by id '{screen_node_id}': "
                        f"name='{node.name}', label='{node.label}' in '{mat.name}'"
                    )
                    return node, mat

    for mat in candidate_mats:
        if not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.bl_idname == "ShaderNodeTexImage":
                return node, mat

    print("No Image Texture node found. Inspected:")
    for mat in candidate_mats:
        print(f"- {mat.name}")
        if mat.use_nodes:
            for n in mat.node_tree.nodes:
                print(f"    {n.name} ({n.bl_idname})  label='{n.label}'")
    raise RuntimeError(
        f"No Image Texture node found in material '{screen_material_name}' or other "
        f"materials on '{phone.name}'. Add one to the screen material, set its name "
        f"or label to '{screen_node_id or SCREEN_NODE_ID}', and connect its Color "
        "output to Base Colour and Emission Colour."
    )


def fit_screen_uvs(phone, image_node, screen_material):
    """Normalise the screen face's UVs to the 0..1 range *shader-side*.

    Looks at every polygon on ``phone`` that uses ``screen_material``, takes
    the UV bounding box across all of their loops, and inserts (or refreshes)
    a TexCoord -> Mapping pair wired into the screen Image Texture's Vector
    input. The Mapping node remaps the screen's UV bbox onto (0,0)..(1,1),
    so the screenshot fills the screen face regardless of how the mesh
    happens to be unwrapped in the .blend.

    Mutates only the screen material's node graph - never the mesh.
    No-op when the UVs already fill 0..1.
    """
    mesh = phone.data
    if not hasattr(mesh, "polygons") or mesh.uv_layers.active is None:
        return

    mat_idx = None
    for i, slot in enumerate(phone.material_slots):
        if slot.material is screen_material:
            mat_idx = i
            break
    if mat_idx is None:
        return

    uv_data = mesh.uv_layers.active.data
    us, vs = [], []
    for poly in mesh.polygons:
        if poly.material_index != mat_idx:
            continue
        for loop_idx in poly.loop_indices:
            u, v = uv_data[loop_idx].uv
            us.append(u)
            vs.append(v)

    if not us:
        print(
            f"[autofit] no faces on '{phone.name}' use material "
            f"'{screen_material.name}' - skipping UV fit"
        )
        return

    u_min, u_max = min(us), max(us)
    v_min, v_max = min(vs), max(vs)
    du, dv = u_max - u_min, v_max - v_min
    if du <= 1e-6 or dv <= 1e-6:
        return

    nodes = screen_material.node_tree.nodes
    links = screen_material.node_tree.links

    AUTOFIT_COORD   = "_AutoFitTexCoord"
    AUTOFIT_MAPPING = "_AutoFitMapping"

    tol = 1e-4
    already_unit = (
        abs(u_min) < tol and abs(u_max - 1) < tol
        and abs(v_min) < tol and abs(v_max - 1) < tol
    )
    if already_unit:
        # Tear down any previous auto-fit nodes so we don't double-correct.
        for name in (AUTOFIT_MAPPING, AUTOFIT_COORD):
            n = nodes.get(name)
            if n is not None:
                nodes.remove(n)
        return

    coord_node = nodes.get(AUTOFIT_COORD)
    if coord_node is None:
        coord_node = nodes.new("ShaderNodeTexCoord")
        coord_node.name  = AUTOFIT_COORD
        coord_node.label = AUTOFIT_COORD
        coord_node.location = (image_node.location.x - 620, image_node.location.y)

    mapping_node = nodes.get(AUTOFIT_MAPPING)
    if mapping_node is None:
        mapping_node = nodes.new("ShaderNodeMapping")
        mapping_node.name  = AUTOFIT_MAPPING
        mapping_node.label = AUTOFIT_MAPPING
        mapping_node.location = (image_node.location.x - 360, image_node.location.y)

    for link in list(links):
        if (link.to_node is mapping_node and link.to_socket.name == "Vector") \
                or (link.to_node is image_node and link.to_socket.name == "Vector"):
            links.remove(link)
    links.new(coord_node.outputs["UV"], mapping_node.inputs["Vector"])
    links.new(mapping_node.outputs["Vector"], image_node.inputs["Vector"])

    mapping_node.vector_type = 'POINT'
    mapping_node.inputs["Location"].default_value = (-u_min / du, -v_min / dv, 0.0)
    mapping_node.inputs["Rotation"].default_value = (0.0, 0.0, 0.0)
    mapping_node.inputs["Scale"].default_value    = (1.0 / du, 1.0 / dv, 1.0)

    print(
        f"[autofit] '{phone.name}' screen UV bbox "
        f"({u_min:.3f}..{u_max:.3f}, {v_min:.3f}..{v_max:.3f}) "
        "-> normalised to 0..1 via Mapping node"
    )


def scan_screenshots(screens_dir_path):
    """Return a sorted list of image filepaths in the directory."""
    abs_dir = bpy.path.abspath(screens_dir_path)
    if not os.path.isdir(abs_dir):
        raise RuntimeError(f"Screenshots directory not found: {abs_dir}")

    files = []
    for fn in sorted(os.listdir(abs_dir)):
        if fn.startswith('.'):
            continue
        if fn.lower().endswith(SUPPORTED_EXTS):
            files.append(os.path.join(abs_dir, fn))
    return files


def look_at(cam_obj, target_pos, world_up):
    direction = (cam_obj.location - target_pos).normalized()
    right = world_up.cross(direction).normalized()
    new_up = direction.cross(right).normalized()
    rot = Matrix((
        (right.x, new_up.x, direction.x, 0),
        (right.y, new_up.y, direction.y, 0),
        (right.z, new_up.z, direction.z, 0),
        (0,       0,        0,           1),
    ))
    cam_obj.matrix_world = Matrix.Translation(cam_obj.location) @ rot


def fit_camera_to_object(scene, cam, obj, margin=1.08):
    bpy.context.view_layer.update()
    bbox_world = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    max_dx, max_dy = 0.0, 0.0
    for corner in bbox_world:
        co = world_to_camera_view(scene, cam, corner)
        if co.z <= 0:
            return
        max_dx = max(max_dx, abs(co.x - 0.5))
        max_dy = max(max_dy, abs(co.y - 0.5))
    if max_dx <= 0 or max_dy <= 0:
        return
    target = 0.5 / margin
    scale = min(target / max_dx, target / max_dy)
    cam.data.lens = cam.data.lens * scale


def build_cameras(scene, phone):
    bbox_corners = [phone.matrix_world @ Vector(c) for c in phone.bound_box]
    center = sum(bbox_corners, Vector()) / 8.0
    size = max(
        (max(c[i] for c in bbox_corners) - min(c[i] for c in bbox_corners))
        for i in range(3)
    )
    base_distance = size * 4.0

    right_dir = SCREEN_NORMAL.cross(UI_UP).normalized()
    cams = []
    for name, theta_deg, phi_deg, dist_mul in ANGLES:
        theta = math.radians(theta_deg)
        phi   = math.radians(phi_deg)
        tangent = math.cos(phi) * UI_UP + math.sin(phi) * right_dir
        offset = base_distance * dist_mul * (
            math.cos(theta) * SCREEN_NORMAL + math.sin(theta) * tangent
        )

        cam_name = f"_Cam_{scene.name}_{name}"
        cam = bpy.data.objects.get(cam_name)
        if cam is None:
            cam_data = bpy.data.cameras.new(cam_name)
            cam = bpy.data.objects.new(cam_name, cam_data)

        if cam.name not in scene.collection.all_objects:
            try:
                scene.collection.objects.link(cam)
            except RuntimeError:
                pass

        for c in list(cam.constraints):
            cam.constraints.remove(c)

        cam.location = center + offset
        look_at(cam, center, UI_UP)
        cam.data.lens = DEFAULT_LENS_MM
        fit_camera_to_object(scene, cam, phone, margin=FIT_MARGIN)
        cams.append((name, cam))
    return cams


def render_scene(scene_name, cfg):
    if scene_name not in bpy.data.scenes:
        print(f"[skip] scene '{scene_name}' not found in this .blend")
        return

    scene = bpy.data.scenes[scene_name]
    bpy.context.window.scene = scene
    print(f"\n=== Rendering scene: {scene_name} ===")
    replace_missing_image_nodes(scene)

    phone = scene.objects.get(cfg["phone_object"])
    if phone is None:
        raise RuntimeError(
            f"Phone object '{cfg['phone_object']}' not in scene '{scene.name}'"
        )

    screen_node_id = cfg.get("screen_node_id", SCREEN_NODE_ID)
    image_node, image_mat = find_image_node(phone, cfg["screen_material"], screen_node_id)
    print(f"Image Texture node: '{image_node.name}' in material '{image_mat.name}'")
    fit_screen_uvs(phone, image_node, image_mat)

    screenshot_files = scan_screenshots(cfg["screens_dir"])
    if not screenshot_files:
        print(f"[skip] no screenshots found in {cfg['screens_dir']}")
        return
    print(f"Found {len(screenshot_files)} screenshot(s) in {cfg['screens_dir']}")

    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = RES_PERCENT
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = TRANSPARENT_BG
    scene.render.use_persistent_data = USE_PERSISTENT

    if scene.render.engine == 'CYCLES':
        scene.cycles.samples = SAMPLES
        scene.cycles.device = DEVICE
        scene.cycles.use_adaptive_sampling = True
        # Tighter threshold + higher floor: keeps fine detail (speaker grilles,
        # USB port lip, chamfered edges) from being undersampled and then
        # smeared into asterisk-shaped artifacts by the denoiser.
        scene.cycles.adaptive_threshold = 0.01
        scene.cycles.adaptive_min_samples = 64
        scene.cycles.use_denoising = True
        # Disabled: clipping indirect light tends to flatten the highlights on
        # chamfered phone edges and the screen glass without much speed win.
        scene.cycles.sample_clamp_indirect = 0.0

        scene.cycles.pixel_filter_type = 'BLACKMAN_HARRIS'
        scene.cycles.filter_width = 1.5

        scene.cycles.max_bounces = 8
        scene.cycles.diffuse_bounces = 3
        scene.cycles.glossy_bounces = 4
        scene.cycles.transmission_bounces = 8
        scene.cycles.volume_bounces = 0
        scene.cycles.transparent_max_bounces = 8

        scene.cycles.caustics_reflective = False
        scene.cycles.caustics_refractive = False
        scene.cycles.blur_glossy = 1.0

        try:
            scene.cycles.use_light_tree = True
        except AttributeError:
            pass
        try:
            scene.cycles.use_auto_tile = USE_AUTO_TILE
            scene.cycles.tile_size = TILE_SIZE
        except AttributeError:
            pass

        # Prefer OpenImageDenoise: preserves fine geometry (speaker grilles,
        # micro-perforations) much better than the OptiX denoiser, which tends
        # to hallucinate star/asterisk shapes on tiny dark features. OIDN runs
        # on the GPU in Blender 4.2+ so the speed cost is small.
        denoiser_set = False
        for denoiser_name in ('OPENIMAGEDENOISE', 'OPTIX'):
            try:
                scene.cycles.denoiser = denoiser_name
                denoiser_set = True
                break
            except TypeError:
                continue
        if denoiser_set:
            try:
                scene.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
            except (AttributeError, TypeError):
                pass
            try:
                scene.cycles.denoising_prefilter = 'ACCURATE'
            except (AttributeError, TypeError):
                pass
            try:
                scene.cycles.denoising_quality = 'HIGH'
            except (AttributeError, TypeError):
                pass
            try:
                scene.cycles.denoising_use_gpu = True
            except AttributeError:
                pass

        try:
            scene.render.compositor_device = 'GPU'
        except AttributeError:
            pass
    elif scene.render.engine in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        scene.eevee.taa_render_samples = SAMPLES

    cams = build_cameras(scene, phone)

    out_dir = os.path.join(bpy.path.abspath(OUTPUT_DIR), scene_name)
    os.makedirs(out_dir, exist_ok=True)

    loaded_images = []
    for filepath in screenshot_files:
        img = bpy.data.images.load(filepath, check_existing=True)
        try:
            img.reload()  # pick up disk changes between runs
        except RuntimeError:
            pass
        img.colorspace_settings.name = 'sRGB'
        image_node.image = img
        loaded_images.append(img)

        screen_name = os.path.splitext(os.path.basename(filepath))[0]
        safe_screen = "".join(
            ch if ch.isalnum() or ch in "-_" else "_" for ch in screen_name
        )

        for angle_name, cam in cams:
            scene.camera = cam
            scene.render.filepath = os.path.join(
                out_dir, f"{safe_screen}__{angle_name}.png"
            )
            bpy.context.view_layer.update()
            print(f"Rendering {scene.render.filepath}")
            bpy.ops.render.render(write_still=True)

    # Optional: keep loaded images cached in the file. Comment out the next
    # block if you want a "fresh load every run" behaviour at the cost of
    # slightly slower restarts. For headless runs the file isn't saved, so
    # this matters only for interactive Blender.
    # for img in loaded_images:
    #     if img.users == 0:
    #         bpy.data.images.remove(img)


# --- main loop ------------------------------------------------------------
def selected_scene_configs():
    """Filter SCENE_CONFIGS via the RENDER_PLATFORMS env var (case-insensitive,
    comma-separated). Unset/empty -> render everything."""
    requested = os.environ.get("RENDER_PLATFORMS", "").strip()
    if not requested:
        return SCENE_CONFIGS

    wanted = {name.strip().lower() for name in requested.split(",") if name.strip()}
    selected = {
        scene_name: cfg
        for scene_name, cfg in SCENE_CONFIGS.items()
        if scene_name.lower() in wanted
    }

    if not selected:
        raise RuntimeError(
            f"RENDER_PLATFORMS={requested!r} matched no scenes. "
            f"Valid options: {', '.join(SCENE_CONFIGS)}"
        )
    return selected


scenes_to_render = selected_scene_configs()
print(f"Rendering platforms: {', '.join(scenes_to_render)}")

for scene_name, cfg in scenes_to_render.items():
    try:
        render_scene(scene_name, cfg)
    except Exception as e:
        print(f"[error] scene '{scene_name}' failed: {e}")

print("\nAll scenes done.")