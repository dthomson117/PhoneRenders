import math

import bpy

from render_lib.cameras import UI_UP, look_at
from render_lib.logging_utils import log

KEY_LIGHT_NAME_PREFIX = "_KeyLight_"


def _apply_ray_visibility(obj, *, glossy=True, transmission=True,
                          diffuse=True, camera=True):
    """Best-effort setter for Cycles per-object ray visibility."""
    mapping = {
        'visible_glossy': glossy,
        'visible_transmission': transmission,
        'visible_diffuse': diffuse,
        'visible_camera': camera,
    }
    for attr, value in mapping.items():
        if hasattr(obj, attr):
            try:
                setattr(obj, attr, value)
            except (AttributeError, TypeError):
                pass

    legacy = getattr(obj, 'cycles_visibility', None)
    if legacy is not None:
        for attr, value in (
            ('glossy', glossy),
            ('transmission', transmission),
            ('diffuse', diffuse),
            ('camera', camera),
        ):
            if hasattr(legacy, attr):
                try:
                    setattr(legacy, attr, value)
                except (AttributeError, TypeError):
                    pass


def _walk_object_hierarchy(root):
    """Yield ``root`` and every descendant Object (children, recursively)."""
    yield root
    children = list(getattr(root, 'children_recursive', None) or [])
    if not children:
        stack = list(root.children)
        while stack:
            obj = stack.pop()
            children.append(obj)
            stack.extend(obj.children)
    for obj in children:
        yield obj


def setup_key_light(scene, enabled, strength=4.0, angle_deg=3.0,
                    color=(1.0, 1.0, 1.0),
                    visible_glossy=False, visible_transmission=False):
    """Create (or remove) a Sun light named ``_KeyLight_<scene>``."""
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
        sun.angle = math.radians(float(angle_deg))
    except AttributeError:
        pass
    sun.color = (float(color[0]), float(color[1]), float(color[2]))

    light_obj.hide_select = True
    light_obj.hide_render = False
    light_obj.hide_viewport = False

    _apply_ray_visibility(
        light_obj,
        glossy=bool(visible_glossy),
        transmission=bool(visible_transmission),
    )

    log(
        f"[light] key light '{light_name}' "
        f"strength={strength:.2f}W/m² angle={angle_deg:.1f}° "
        f"colour=({color[0]:.2f}, {color[1]:.2f}, {color[2]:.2f}) "
        f"glossy={'on' if visible_glossy else 'off'} "
        f"transmission={'on' if visible_transmission else 'off'}"
    )
    return light_obj


def isolate_phone_from_indirect(phone, enabled):
    """Make the phone hierarchy invisible to *indirect diffuse* rays."""
    if phone is None:
        return
    diffuse_visible = not bool(enabled)
    affected = 0
    for obj in _walk_object_hierarchy(phone):
        if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}:
            continue
        _apply_ray_visibility(
            obj,
            diffuse=diffuse_visible,
            glossy=True,
            transmission=True,
            camera=True,
        )
        affected += 1
    state = "isolated" if enabled else "restored"
    log(
        f"[phone] indirect-diffuse {state} on {affected} mesh object"
        f"{'s' if affected != 1 else ''} under '{phone.name}'"
    )


def aim_key_light_for_camera(sun_obj, cam_obj, phone_center,
                             elevation_deg=50.0,
                             shadow_azimuth_deg=315.0):
    """Aim a Sun light so the cast shadow falls in a *screen-space* direction."""
    m = cam_obj.matrix_world
    cam_right = m.col[0].to_3d().normalized()
    cam_up    = m.col[1].to_3d().normalized()
    cam_back  = m.col[2].to_3d().normalized()

    az = math.radians(float(shadow_azimuth_deg))
    el = math.radians(max(0.0, min(89.9, float(elevation_deg))))

    shadow_screen = math.cos(az) * cam_right + math.sin(az) * cam_up
    direction = (
        math.cos(el) * shadow_screen
        + math.sin(el) * (-cam_back)
    ).normalized()

    offset_dist = (cam_obj.location - phone_center).length * 0.5 or 1.0
    sun_obj.location = cam_obj.location - direction * offset_dist
    look_at(sun_obj, sun_obj.location + direction, UI_UP)
