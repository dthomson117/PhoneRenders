import bpy
import os
import json
import math
import sys
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view


def log(message=""):
    """Write to stderr with an immediate flush.

    Blender buffers Python stdout in --background mode, so important script
    messages (settings loaded, render config banner, "Rendering ..." lines)
    can sit hidden until the run is nearly over. Routing them through stderr
    with flush=True puts them in the same stream as Blender's own
    warnings/errors and makes them appear in real time."""
    print(message, file=sys.stderr, flush=True)


# --- SETTINGS LOADER ------------------------------------------------------
# All tweakable values live in `render_settings.json` next to this script
# (or next to the .blend file). Environment variables override individual
# fields where noted. The defaults below are only used if the JSON file is
# missing or a key is absent.
SETTINGS_FILENAME = "render_settings.json"

DEFAULT_SETTINGS = {
    "output_dir": "//renders/",
    "resolution": {"x": 1440, "y": 2560},
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
    "view_transform": "Standard",
    "view_look": "None",
    "view_exposure": 0.0,
    "view_gamma": 1.0,
    "shadow_catcher": False,
    "shadow_catcher_size_multiplier": 8.0,
    "shadow_catcher_z_offset": 0.0,
    "key_light": False,
    "key_light_strength": 4.0,
    "key_light_elevation_deg": 45.0,
    "key_light_angle_deg": 3.0,
    "key_light_color": [1.0, 1.0, 1.0],
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
                log(f"Loaded settings from: {path}")
                merged = dict(DEFAULT_SETTINGS)
                merged.update(data)
                return merged
            except (OSError, json.JSONDecodeError) as exc:
                log(f"[warn] could not parse settings at {path}: {exc}")
    log(f"[warn] {SETTINGS_FILENAME} not found - using built-in defaults.")
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
VIEW_TRANSFORM        = str(SETTINGS.get("view_transform", "Standard"))
VIEW_LOOK             = str(SETTINGS.get("view_look", "None"))
VIEW_EXPOSURE         = float(SETTINGS.get("view_exposure", 0.0))
VIEW_GAMMA            = float(SETTINGS.get("view_gamma", 1.0))
SHADOW_CATCHER        = bool(SETTINGS.get("shadow_catcher", False))
SHADOW_CATCHER_SIZE   = float(SETTINGS.get("shadow_catcher_size_multiplier", 8.0))
SHADOW_CATCHER_Z      = float(SETTINGS.get("shadow_catcher_z_offset", 0.0))
KEY_LIGHT             = bool(SETTINGS.get("key_light", False))
KEY_LIGHT_STRENGTH    = float(SETTINGS.get("key_light_strength", 4.0))
KEY_LIGHT_ELEVATION   = float(SETTINGS.get("key_light_elevation_deg", 45.0))
KEY_LIGHT_ANGLE       = float(SETTINGS.get("key_light_angle_deg", 3.0))
_kl_color             = SETTINGS.get("key_light_color", [1.0, 1.0, 1.0])
KEY_LIGHT_COLOR       = tuple(float(c) for c in (list(_kl_color) + [1.0, 1.0, 1.0])[:3])

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
    log(f"Cycles compute_device_type = {prefs.compute_device_type}")
    for line in enabled:
        log(f"  - {line}")
    if not enabled:
        log("  (no GPU detected - falling back to CPU)")

setup_gpu()


def log_render_config(scene):
    """Print a prominent banner of what the next render(s) will actually use.

    Reads back the configured values from the scene rather than the settings
    file, so we report what Blender will really do - not what we asked for."""
    engine = scene.render.engine
    res_x = int(scene.render.resolution_x * scene.render.resolution_percentage / 100)
    res_y = int(scene.render.resolution_y * scene.render.resolution_percentage / 100)

    log("-" * 60)
    log(f"Render engine:    {engine}")
    log(f"Resolution:       {res_x} x {res_y}")
    log(f"Film transparent: {scene.render.film_transparent}")
    log(
        f"Color management: view={scene.view_settings.view_transform} "
        f"look={scene.view_settings.look or 'None'} "
        f"exposure={scene.view_settings.exposure:+.2f} "
        f"gamma={scene.view_settings.gamma:.2f} "
        f"display={scene.display_settings.display_device}"
    )
    log(
        f"Shadow catcher:   {'on' if SHADOW_CATCHER else 'off'} "
        f"(size_x={SHADOW_CATCHER_SIZE:.1f}, z_offset={SHADOW_CATCHER_Z:+.4f})"
    )
    log(
        f"Key light:        {'on' if KEY_LIGHT else 'off'} "
        f"(strength={KEY_LIGHT_STRENGTH:.2f}W/m², elev={KEY_LIGHT_ELEVATION:.1f}°, "
        f"angle={KEY_LIGHT_ANGLE:.1f}°)"
    )

    if engine == 'CYCLES':
        prefs = bpy.context.preferences.addons['cycles'].preferences
        active_gpus = [
            f"{d.type}: {d.name}" for d in prefs.devices
            if d.use and d.type != 'CPU'
        ]
        cdt = prefs.compute_device_type
        device_label = scene.cycles.device
        if device_label == 'GPU' and active_gpus:
            device_label = f"GPU ({cdt})"
        elif device_label == 'GPU':
            device_label = f"GPU ({cdt}) - NO ACTIVE DEVICES, will fall back to CPU"
        log(f"Device:           {device_label}")
        for g in active_gpus:
            log(f"  - {g}")
        log(f"Samples (max):    {scene.cycles.samples}")
        log(
            f"Adaptive:         threshold={scene.cycles.adaptive_threshold} "
            f"min_samples={scene.cycles.adaptive_min_samples}"
        )
        if scene.cycles.use_denoising:
            denoiser = getattr(scene.cycles, 'denoiser', '?')
            quality = getattr(scene.cycles, 'denoising_quality', '?')
            prefilter = getattr(scene.cycles, 'denoising_prefilter', '?')
            passes = getattr(scene.cycles, 'denoising_input_passes', '?')
            use_gpu = getattr(scene.cycles, 'denoising_use_gpu', False)
            log(
                f"Denoiser:         {denoiser} "
                f"(quality={quality}, prefilter={prefilter}, "
                f"passes={passes}, gpu={use_gpu})"
            )
        else:
            log("Denoiser:         OFF")
        try:
            log(
                f"Tiling:           auto_tile={scene.cycles.use_auto_tile} "
                f"tile_size={scene.cycles.tile_size}"
            )
        except AttributeError:
            pass
        log(f"Persistent data:  {scene.render.use_persistent_data}")
    elif engine in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        log(f"Samples:          {scene.eevee.taa_render_samples}")
    log("-" * 60)


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
                    log(
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
                    log(
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

    log("No Image Texture node found. Inspected:")
    for mat in candidate_mats:
        log(f"- {mat.name}")
        if mat.use_nodes:
            for n in mat.node_tree.nodes:
                log(f"    {n.name} ({n.bl_idname})  label='{n.label}'")
    raise RuntimeError(
        f"No Image Texture node found in material '{screen_material_name}' or other "
        f"materials on '{phone.name}'. Add one to the screen material, set its name "
        f"or label to '{screen_node_id or SCREEN_NODE_ID}', and connect its Color "
        "output to Base Colour and Emission Colour."
    )


AUTOFIT_COORD_NODE   = "_AutoFitTexCoord"
AUTOFIT_MAPPING_NODE = "_AutoFitMapping"


def _collect_screen_uvs(phone, screen_material):
    """Return ``(us, vs, mat_idx, layer_name)`` for every loop UV on
    ``phone`` whose face uses ``screen_material``.

    Goes through ``bmesh`` rather than the ``mesh.uv_layers[…].data`` or
    ``mesh.attributes[…].data`` collections because both of those paths
    have historically come back empty on certain meshes (Blender 4.1+ moved
    UVs into the attribute system, and the legacy shim can return a
    zero-length collection in Blender 5.x even when the mesh clearly has
    UVs). ``bmesh.loops.layers.uv`` has been the stable, canonical way to
    read UVs since Blender 2.6 and works on every version.

    Returns ``(None, None, None, None)`` if no matching material slot
    exists, ``([], [], mat_idx, layer_name)`` if the material has no faces,
    or ``([], [], mat_idx, None)`` if the mesh has no UV layer at all.
    """
    import bmesh

    mat_idx = None
    for i, slot in enumerate(phone.material_slots):
        if slot.material is screen_material:
            mat_idx = i
            break
    if mat_idx is None:
        return None, None, None, None

    mesh = phone.data
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None:
            uv_keys = list(bm.loops.layers.uv.keys())
            if uv_keys:
                uv_layer = bm.loops.layers.uv[uv_keys[0]]
        if uv_layer is None:
            return [], [], mat_idx, None

        us, vs = [], []
        for face in bm.faces:
            if face.material_index != mat_idx:
                continue
            for loop in face.loops:
                u, v = loop[uv_layer].uv
                us.append(u)
                vs.append(v)
        return us, vs, mat_idx, uv_layer.name
    finally:
        bm.free()


def disable_screen_uv_autofit(image_node, screen_material):
    """Honour the .blend's hand-laid UVs verbatim instead of normalising them.

    Tears down any TexCoord/Mapping nodes left over from a previous
    ``fit_screen_uvs`` run so the Image Texture node falls back to the mesh's
    active UV map untouched, and switches the texture's extension mode to
    'CLIP' so UVs that fall outside 0..1 (e.g. an island scaled up to inset
    the screenshot inside a curved bezel) render as transparent rather than
    tiling the edge pixels."""
    nodes = screen_material.node_tree.nodes
    for name in (AUTOFIT_MAPPING_NODE, AUTOFIT_COORD_NODE):
        node = nodes.get(name)
        if node is not None:
            nodes.remove(node)
    try:
        image_node.extension = 'CLIP'
    except (AttributeError, TypeError):
        pass


def fit_screen_uvs(phone, image_node, screen_material, inset=0.0):
    """Normalise the screen face's UVs to the 0..1 range *shader-side*.

    Looks at every polygon on ``phone`` that uses ``screen_material``, takes
    the UV bounding box across all of their loops, and inserts (or refreshes)
    a TexCoord -> Mapping pair wired into the screen Image Texture's Vector
    input. The Mapping node remaps the screen's UV bbox onto (0,0)..(1,1),
    so the screenshot fills the screen face regardless of how the mesh
    happens to be unwrapped in the .blend.

    ``inset`` (0..0.5) shrinks the screenshot inward by that fraction on
    every side, leaving transparent margin between the screenshot and the
    screen face's edge. Useful when a phone mesh has rounded display corners
    that bite into status-bar content. Implemented by oversampling: the
    Mapping node samples *outside* 0..1, and the Image Texture is forced to
    'CLIP' so the over-sampled area returns transparent rather than tiling.

    Mutates only the screen material's node graph - never the mesh.
    No-op when the UVs already fill 0..1 *and* no inset is requested.
    """
    if not hasattr(phone.data, "polygons"):
        return

    us, vs, mat_idx, layer_name = _collect_screen_uvs(phone, screen_material)
    if mat_idx is None:
        return
    if layer_name is None:
        log(f"[autofit] '{phone.name}' has no UV layer - skipping UV fit")
        return
    if not us:
        log(
            f"[autofit] no faces on '{phone.name}' use material "
            f"'{screen_material.name}' (layer: {layer_name!r}) - skipping UV fit"
        )
        return

    u_min, u_max = min(us), max(us)
    v_min, v_max = min(vs), max(vs)
    du, dv = u_max - u_min, v_max - v_min
    if du <= 1e-6 or dv <= 1e-6:
        return

    inset = max(0.0, min(0.49, float(inset)))

    nodes = screen_material.node_tree.nodes
    links = screen_material.node_tree.links

    tol = 1e-4
    already_unit = (
        abs(u_min) < tol and abs(u_max - 1) < tol
        and abs(v_min) < tol and abs(v_max - 1) < tol
    )
    if already_unit and inset == 0.0:
        # Tear down any previous auto-fit nodes so we don't double-correct.
        for name in (AUTOFIT_MAPPING_NODE, AUTOFIT_COORD_NODE):
            n = nodes.get(name)
            if n is not None:
                nodes.remove(n)
        try:
            image_node.extension = 'REPEAT'
        except (AttributeError, TypeError):
            pass
        return

    coord_node = nodes.get(AUTOFIT_COORD_NODE)
    if coord_node is None:
        coord_node = nodes.new("ShaderNodeTexCoord")
        coord_node.name  = AUTOFIT_COORD_NODE
        coord_node.label = AUTOFIT_COORD_NODE
        coord_node.location = (image_node.location.x - 620, image_node.location.y)

    mapping_node = nodes.get(AUTOFIT_MAPPING_NODE)
    if mapping_node is None:
        mapping_node = nodes.new("ShaderNodeMapping")
        mapping_node.name  = AUTOFIT_MAPPING_NODE
        mapping_node.label = AUTOFIT_MAPPING_NODE
        mapping_node.location = (image_node.location.x - 360, image_node.location.y)

    for link in list(links):
        if (link.to_node is mapping_node and link.to_socket.name == "Vector") \
                or (link.to_node is image_node and link.to_socket.name == "Vector"):
            links.remove(link)
    links.new(coord_node.outputs["UV"], mapping_node.inputs["Vector"])
    links.new(mapping_node.outputs["Vector"], image_node.inputs["Vector"])

    # Compose two transforms into one Mapping node:
    #   normalise:  norm  = (UV - min) / d                  (UV bbox -> 0..1)
    #   inset:      tex   = (1 + 2*inset) * norm - inset    (shrinks content
    #                                                       toward centre by
    #                                                       `inset` on each
    #                                                       side; outside 0..1
    #                                                       is sampled and
    #                                                       clipped to alpha=0)
    #
    # Blender's shader Mapping node applies location after scale:
    #   tex = UV * Scale + Location
    # so Location must be in scaled texture-coordinate units.
    oversample = 1.0 + 2.0 * inset
    mapping_node.vector_type = 'POINT'
    mapping_node.inputs["Location"].default_value = (
        -u_min * oversample / du - inset,
        -v_min * oversample / dv - inset,
        0.0,
    )
    mapping_node.inputs["Rotation"].default_value = (0.0, 0.0, 0.0)
    mapping_node.inputs["Scale"].default_value = (
        oversample / du,
        oversample / dv,
        1.0,
    )

    # When inset > 0 the screen face samples outside 0..1; CLIP makes the
    # over-sampled fringe transparent so the bezel/back-of-glass material
    # behind the screen face shows through cleanly.
    if inset > 0.0:
        try:
            image_node.extension = 'CLIP'
        except (AttributeError, TypeError):
            pass

    log(
        f"[autofit] '{phone.name}' screen UV bbox "
        f"({u_min:.3f}..{u_max:.3f}, {v_min:.3f}..{v_max:.3f}) "
        f"-> normalised to 0..1 via Mapping node (inset={inset:.3f})"
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


SHADOW_CATCHER_NAME_PREFIX = "_ShadowCatcher_"
KEY_LIGHT_NAME_PREFIX      = "_KeyLight_"


def setup_shadow_catcher(scene, phone, enabled, size_multiplier=8.0, z_offset=0.0):
    """Add (or remove) a Cycles shadow-catcher plane underneath ``phone``.

    Creates a horizontal plane named ``_ShadowCatcher_<scene>`` flush with the
    phone's lowest world-Z point, sized to ``size_multiplier`` times the phone's
    widest XY dimension, and flags it as ``cycles.is_shadow_catcher`` so it
    renders only the soft contact shadow falling on it - the rest of the plane
    stays transparent. With ``film_transparent=True`` the final PNG ends up with
    the phone + a real baked shadow on an otherwise transparent background,
    which sidesteps Figma's drop-shadow-on-alpha quirks entirely.

    ``z_offset`` pushes the plane *down* by that many world units (positive
    values move further below the phone) - useful if you want a millimeter of
    gap between the phone's chassis and the floor for a softer contact line.

    When ``enabled`` is False, any previously-created catcher plane is removed
    so toggling the setting off cleans up after itself.
    """
    plane_name = f"{SHADOW_CATCHER_NAME_PREFIX}{scene.name}"
    existing = bpy.data.objects.get(plane_name)

    if not enabled:
        if existing is not None:
            mesh = existing.data
            bpy.data.objects.remove(existing, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            log(f"[shadow] removed catcher plane '{plane_name}'")
        return None

    if scene.render.engine != 'CYCLES':
        log(
            f"[shadow] catcher requires Cycles (current engine: "
            f"{scene.render.engine}) - skipping"
        )
        return None

    bpy.context.view_layer.update()
    bbox_world = [phone.matrix_world @ Vector(c) for c in phone.bound_box]
    min_x = min(c.x for c in bbox_world)
    max_x = max(c.x for c in bbox_world)
    min_y = min(c.y for c in bbox_world)
    max_y = max(c.y for c in bbox_world)
    min_z = min(c.z for c in bbox_world)

    center_x = 0.5 * (min_x + max_x)
    center_y = 0.5 * (min_y + max_y)
    footprint = max(max_x - min_x, max_y - min_y)
    plane_size = max(footprint * float(size_multiplier), 1e-3)

    plane = existing
    if plane is None:
        mesh_data = bpy.data.meshes.new(plane_name + "_mesh")
        # Unit square in the XY plane centred on the origin; we scale to size
        # via object scale so size tweaks don't require rebuilding the mesh.
        mesh_data.from_pydata(
            [(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)],
            [],
            [(0, 1, 2, 3)],
        )
        mesh_data.update()
        plane = bpy.data.objects.new(plane_name, mesh_data)
        scene.collection.objects.link(plane)

    plane.location = (center_x, center_y, min_z - float(z_offset))
    plane.scale = (plane_size, plane_size, 1.0)
    plane.rotation_euler = (0.0, 0.0, 0.0)

    # Hide from selection in the outliner to avoid accidentally dragging it,
    # but keep it visible to the renderer.
    plane.hide_select = True
    plane.hide_render = False
    plane.hide_viewport = False

    # Cycles object setting - present on every Object in Cycles-aware builds.
    set_flag = False
    try:
        plane.cycles.is_shadow_catcher = True
        set_flag = True
    except AttributeError:
        pass
    if not set_flag:
        # Fallback for older Blender shorthand (kept just in case).
        try:
            plane.is_shadow_catcher = True
            set_flag = True
        except AttributeError:
            pass
    if not set_flag:
        log("[shadow] could not set is_shadow_catcher on plane - check engine")

    log(
        f"[shadow] catcher plane at "
        f"({center_x:+.3f}, {center_y:+.3f}, {plane.location.z:+.3f}) "
        f"size={plane_size:.3f} (footprint x{size_multiplier:.1f})"
    )
    return plane


def setup_key_light(scene, enabled, strength=4.0, angle_deg=3.0,
                    color=(1.0, 1.0, 1.0)):
    """Create (or remove) a Sun light named ``_KeyLight_<scene>``.

    The Sun's *orientation* is updated per-camera by ``aim_key_light_for_camera``
    so its shadow always falls "behind" the phone from whichever camera is
    rendering; this function just owns the light's existence and its non-
    directional properties (energy, soft-shadow angle, colour).

    Removes the light when ``enabled`` is False so toggling off cleans up.
    """
    light_name = f"{KEY_LIGHT_NAME_PREFIX}{scene.name}"
    existing = bpy.data.objects.get(light_name)

    if not enabled:
        if existing is not None:
            data = existing.data
            bpy.data.objects.remove(existing, do_unlink=True)
            if data is not None and data.users == 0 and isinstance(data, bpy.types.Light):
                bpy.data.lights.remove(data)
            log(f"[light] removed key light '{light_name}'")
        return None

    light_obj = existing
    if light_obj is None or not isinstance(light_obj.data, bpy.types.Light) \
            or light_obj.data.type != 'SUN':
        # Replace anything stale with a fresh Sun.
        if light_obj is not None:
            stale_data = light_obj.data
            bpy.data.objects.remove(light_obj, do_unlink=True)
            if (stale_data is not None and stale_data.users == 0
                    and isinstance(stale_data, bpy.types.Light)):
                bpy.data.lights.remove(stale_data)
        sun_data = bpy.data.lights.new(name=light_name + "_data", type='SUN')
        light_obj = bpy.data.objects.new(name=light_name, object_data=sun_data)
        scene.collection.objects.link(light_obj)

    sun = light_obj.data
    sun.energy = float(strength)
    try:
        # Cycles reads `Light.angle` as the sun's apparent angular diameter
        # in radians; bigger angle = softer shadow penumbra.
        sun.angle = math.radians(float(angle_deg))
    except AttributeError:
        pass
    sun.color = (float(color[0]), float(color[1]), float(color[2]))

    light_obj.hide_select = True
    light_obj.hide_render = False
    light_obj.hide_viewport = False

    log(
        f"[light] key light '{light_name}' "
        f"strength={strength:.2f}W/m² angle={angle_deg:.1f}° "
        f"colour=({color[0]:.2f}, {color[1]:.2f}, {color[2]:.2f})"
    )
    return light_obj


def aim_key_light_for_camera(sun_obj, cam_obj, phone_center, elevation_deg=45.0):
    """Aim a Sun light so it shines from "behind" the camera toward the phone.

    Only the camera's *azimuth* (its horizontal direction onto the phone) is
    inherited; the sun's elevation above horizontal is fixed at
    ``elevation_deg`` so the cast shadow looks the same length/softness across
    every camera angle (front / threequarter / hero-top). This is what makes
    the shadow read "behind the phone from the viewer's POV" consistently in
    the final image set.

    ``elevation_deg`` is interpreted in standard terms:
        0°   -> sun on the horizon, infinitely-long shadow
        45°  -> nice product-shot default
        90°  -> sun straight overhead, shadow directly beneath the phone
    """
    cam_to_phone = phone_center - cam_obj.location
    horiz = Vector((cam_to_phone.x, cam_to_phone.y, 0.0))
    if horiz.length < 1e-6:
        # `hero_top` looks straight down: no horizontal direction to inherit.
        # Default the azimuth to +Y so the shadow points toward the "bottom"
        # of the rendered frame (UI_UP is -Y, so +Y = downward in screen).
        horiz = Vector((0.0, 1.0, 0.0))
    horiz.normalize()

    elev_rad = math.radians(max(0.0, min(89.9, float(elevation_deg))))
    direction = (
        math.cos(elev_rad) * horiz
        + math.sin(elev_rad) * Vector((0.0, 0.0, -1.0))
    ).normalized()

    # Sun lights are positionless for rendering, but parking the object near
    # the camera (offset backward along its light direction) makes the
    # viewport gizmo show up where the eye expects "behind the camera".
    offset_dist = (cam_obj.location - phone_center).length * 0.5 or 1.0
    sun_obj.location = cam_obj.location - direction * offset_dist
    look_at(sun_obj, sun_obj.location + direction, UI_UP)


def render_scene(scene_name, cfg):
    if scene_name not in bpy.data.scenes:
        log(f"[skip] scene '{scene_name}' not found in this .blend")
        return

    scene = bpy.data.scenes[scene_name]
    bpy.context.window.scene = scene
    log(f"\n=== Rendering scene: {scene_name} ===")
    replace_missing_image_nodes(scene)

    phone = scene.objects.get(cfg["phone_object"])
    if phone is None:
        raise RuntimeError(
            f"Phone object '{cfg['phone_object']}' not in scene '{scene.name}'"
        )

    screen_node_id = cfg.get("screen_node_id", SCREEN_NODE_ID)
    image_node, image_mat = find_image_node(phone, cfg["screen_material"], screen_node_id)
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

    screenshot_files = scan_screenshots(cfg["screens_dir"])
    if not screenshot_files:
        log(f"[skip] no screenshots found in {cfg['screens_dir']}")
        return
    log(f"Found {len(screenshot_files)} screenshot(s) in {cfg['screens_dir']}")

    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = RES_PERCENT
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = TRANSPARENT_BG
    scene.render.use_persistent_data = USE_PERSISTENT

    # Color management: 'Standard' gives a 1:1 linear->sRGB pass-through, so
    # on-screen UI pixels render at their authored values (no Filmic/AgX
    # mid-tone roll-off muting the colours). The trade-off is that scenes
    # whose lighting was tuned under Filmic/AgX look underexposed under
    # 'Standard'; bump `view_exposure` to compensate, or switch to 'AgX' for
    # a gentler modern tone-map.
    try:
        scene.view_settings.view_transform = VIEW_TRANSFORM
    except (AttributeError, TypeError) as exc:
        log(f"[warn] could not set view_transform={VIEW_TRANSFORM!r}: {exc}")
    try:
        scene.view_settings.look = VIEW_LOOK
    except (AttributeError, TypeError) as exc:
        log(f"[warn] could not set look={VIEW_LOOK!r}: {exc}")
    try:
        scene.view_settings.exposure = VIEW_EXPOSURE
        scene.view_settings.gamma    = VIEW_GAMMA
    except AttributeError:
        pass

    if scene.render.engine == 'CYCLES':
        scene.cycles.samples = SAMPLES
        scene.cycles.device = DEVICE
        scene.cycles.use_adaptive_sampling = True
        # Tighter threshold + higher floor: keeps fine detail (speaker grilles,
        # USB port lip, chamfered edges) from being undersampled and then
        # smeared into asterisk-shaped artifacts by the denoiser.
        scene.cycles.adaptive_threshold = 0.01
        scene.cycles.adaptive_min_samples = 16
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

    setup_shadow_catcher(
        scene, phone,
        enabled=SHADOW_CATCHER,
        size_multiplier=SHADOW_CATCHER_SIZE,
        z_offset=SHADOW_CATCHER_Z,
    )

    key_light = setup_key_light(
        scene,
        enabled=KEY_LIGHT,
        strength=KEY_LIGHT_STRENGTH,
        angle_deg=KEY_LIGHT_ANGLE,
        color=KEY_LIGHT_COLOR,
    )

    cams = build_cameras(scene, phone)

    # Phone centroid in world space - reused per-camera to aim the key light.
    _bbox_world = [phone.matrix_world @ Vector(c) for c in phone.bound_box]
    phone_center = sum(_bbox_world, Vector()) / 8.0

    log_render_config(scene)

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
            if key_light is not None:
                aim_key_light_for_camera(
                    key_light, cam, phone_center,
                    elevation_deg=KEY_LIGHT_ELEVATION,
                )
            bpy.context.view_layer.update()
            log(f"Rendering {scene.render.filepath}")
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
log(f"Rendering platforms: {', '.join(scenes_to_render)}")

for scene_name, cfg in scenes_to_render.items():
    try:
        render_scene(scene_name, cfg)
    except Exception as e:
        log(f"[error] scene '{scene_name}' failed: {e}")

log("\nAll scenes done.")