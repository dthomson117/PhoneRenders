import bmesh

import bpy

from render_lib.logging_utils import log

AUTOFIT_COORD_NODE   = "_AutoFitTexCoord"
AUTOFIT_MAPPING_NODE = "_AutoFitMapping"


def _collect_screen_uvs(phone, screen_material):
    """Return ``(us, vs, mat_idx, layer_name)`` for every loop UV on
    ``phone`` whose face uses ``screen_material``."""
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
    """Honour the .blend's hand-laid UVs verbatim instead of normalising them."""
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
    """Normalise the screen face's UVs to the 0..1 range *shader-side*."""
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
