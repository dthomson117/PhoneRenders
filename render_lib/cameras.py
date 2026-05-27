import math

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

# Phone orientation: screen faces +Z, UI top is at -Y, UI right is +X.
SCREEN_NORMAL = Vector((0, 0, 1))
UI_UP         = Vector((0, -1, 0))


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


def build_cameras(scene, phone, angles, default_lens_mm, fit_margin):
    bbox_corners = [phone.matrix_world @ Vector(c) for c in phone.bound_box]
    center = sum(bbox_corners, Vector()) / 8.0
    size = max(
        (max(c[i] for c in bbox_corners) - min(c[i] for c in bbox_corners))
        for i in range(3)
    )
    base_distance = size * 4.0

    right_dir = SCREEN_NORMAL.cross(UI_UP).normalized()
    cams = []
    for angle in angles:
        theta = math.radians(angle.tilt_deg)
        phi   = math.radians(angle.yaw_deg)
        tangent = math.cos(phi) * UI_UP + math.sin(phi) * right_dir
        offset = base_distance * angle.distance_multiplier * (
            math.cos(theta) * SCREEN_NORMAL + math.sin(theta) * tangent
        )

        cam_name = f"_Cam_{scene.name}_{angle.name}"
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
        cam.data.lens = default_lens_mm
        fit_camera_to_object(scene, cam, phone, margin=fit_margin)
        cams.append((angle.name, cam))
    return cams
