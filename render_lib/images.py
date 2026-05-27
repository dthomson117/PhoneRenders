import os

import bpy

from render_lib.logging_utils import log


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


def find_image_node(phone, screen_material_name, screen_node_id=None, default_node_id="ScreenTexture"):
    """Find the screen Image Texture node on the phone."""
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
        f"or label to '{screen_node_id or default_node_id}', and connect its Color "
        "output to Base Colour and Emission Colour."
    )
