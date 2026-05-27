import bpy
from mathutils import Vector

from render_lib.logging_utils import log

SHADOW_CATCHER_NAME_PREFIX = "_ShadowCatcher_"


def _make_catcher_non_bouncing(plane):
    """Catch shadows but never act as a bouncing surface.

    Without this, the catcher plane is a plain Lambertian white surface and
    happily reflects the key light (and any other direct/indirect light)
    back UP into the scene. The phone's chrome chassis is glossy, so that
    bounce shows up as a hot spot wrapped around the bottom edge of the
    phone right where the speakers / charging port live - exactly the
    "bright glow under the phone" we've been chasing.

    Flags:
      - visible_camera        = True   (catcher must render so its shadow
                                        alpha ends up in the PNG)
      - visible_shadow        = True   (it must still occlude / receive
                                        shadow samples)
      - visible_diffuse       = False  (no diffuse bounce contribution back
                                        into the scene)
      - visible_glossy        = False  (no glossy reflection of the catcher
                                        on the phone's chrome)
      - visible_transmission  = False  (no transmission contribution)
    """
    mapping = {
        'visible_camera':       True,
        'visible_shadow':       True,
        'visible_diffuse':      False,
        'visible_glossy':       False,
        'visible_transmission': False,
    }
    for attr, value in mapping.items():
        if hasattr(plane, attr):
            try:
                setattr(plane, attr, value)
            except (AttributeError, TypeError):
                pass

    legacy = getattr(plane, 'cycles_visibility', None)
    if legacy is not None:
        for attr, value in (
            ('camera',       True),
            ('shadow',       True),
            ('diffuse',      False),
            ('glossy',       False),
            ('transmission', False),
        ):
            if hasattr(legacy, attr):
                try:
                    setattr(legacy, attr, value)
                except (AttributeError, TypeError):
                    pass


def setup_shadow_catcher(scene, phone, enabled, size_multiplier=8.0, z_offset=0.0):
    """Add (or remove) a Cycles shadow-catcher plane underneath ``phone``."""
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

    plane.hide_select = True
    plane.hide_render = False
    plane.hide_viewport = False

    set_flag = False
    try:
        plane.cycles.is_shadow_catcher = True
        set_flag = True
    except AttributeError:
        pass
    if not set_flag:
        try:
            plane.is_shadow_catcher = True
            set_flag = True
        except AttributeError:
            pass
    if not set_flag:
        log("[shadow] could not set is_shadow_catcher on plane - check engine")

    _make_catcher_non_bouncing(plane)

    log(
        f"[shadow] catcher plane at "
        f"({center_x:+.3f}, {center_y:+.3f}, {plane.location.z:+.3f}) "
        f"size={plane_size:.3f} (footprint x{size_multiplier:.1f}) "
        "non-bouncing (no diffuse/glossy/transmission contribution)"
    )
    return plane
