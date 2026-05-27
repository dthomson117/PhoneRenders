"""Gate the phone screen's emission so it does not light up diffuse surfaces.

Why this exists
---------------
The screen image is wired into *both* Base Color and Emission Color of the
screen material's Principled BSDF, which turns the on-screen pixels into a
diffuse light source. That looks great when the camera sees the screen
directly, but it has a nasty side-effect on the Cycles shadow catcher:

* The phone model has small geometric openings near the bottom edge
  (charging port, speaker grilles, the seam between bezel and frame).
* Light from the bright screen leaks through those openings and hits the
  shadow catcher just below the phone.
* That lowers the catcher's alpha in tight spots, leaving bright pin-prick
  "holes" in what should be a smooth, fading shadow.

Disabling diffuse ray visibility on the phone object is not enough: in
Cycles, an emissive surface is still importance-sampled as a direct light
by surrounding diffuse surfaces. The robust fix is to gate the *emission
output* of the material with a Light Path node, so the screen only emits
along ray types we actually want it to contribute to.

Gate behaviour
--------------
With the gate on, the multiplier applied to the emission color is::

    gate = clamp(is_camera_ray + is_glossy_ray, 0, 1)

That means:

* Camera rays  -> full emission (the screen looks bright on-screen).
* Glossy rays  -> full emission (the screen still reflects in the
  metal chassis / glass bezel, which is what makes the render look real).
* Diffuse rays / shadow rays from diffuse surfaces -> emission goes to
  black, so the shadow catcher (and any other diffuse surface) is no
  longer illuminated by the screen.

Set ``allow_glossy=False`` for the most aggressive variant -- emission
only contributes along the primary camera ray.
"""

import bpy

from render_lib.logging_utils import log

GATE_PATH_NODE  = "_ScreenEmissionLightPath"
GATE_ADD_NODE   = "_ScreenEmissionRayMask"
GATE_CLAMP_NODE = "_ScreenEmissionMaskClamp"
GATE_MIX_NODE   = "_ScreenEmissionMaskMix"

_GATE_NODE_NAMES = (
    GATE_MIX_NODE,
    GATE_CLAMP_NODE,
    GATE_ADD_NODE,
    GATE_PATH_NODE,
)


def _find_principled(material):
    for node in material.node_tree.nodes:
        if node.bl_idname == 'ShaderNodeBsdfPrincipled':
            return node
    return None


def _find_emission_input(bsdf):
    """Return the BSDF emission color input across Blender versions."""
    for name in ("Emission Color", "Emission"):
        sock = bsdf.inputs.get(name)
        if sock is not None and sock.type == 'RGBA':
            return sock
    return None


def _remove_gate_nodes(material):
    """Tear down any previously-installed gate nodes on this material."""
    nodes = material.node_tree.nodes
    removed = False
    for name in _GATE_NODE_NAMES:
        node = nodes.get(name)
        if node is not None:
            nodes.remove(node)
            removed = True
    return removed


def _disconnect_emission_input(material, emission_input):
    links = material.node_tree.links
    for link in list(links):
        if link.to_socket == emission_input:
            links.remove(link)


def gate_screen_emission(image_node, screen_material, *, enabled, allow_glossy=True):
    """Install (or remove) a Light Path gate on the screen emission path.

    Returns ``True`` if the material was touched, ``False`` if there was
    nothing to do (e.g. no Principled BSDF was found).
    """
    if screen_material is None or not screen_material.use_nodes:
        return False

    bsdf = _find_principled(screen_material)
    if bsdf is None:
        log(
            f"[screen-emission] no Principled BSDF in '{screen_material.name}' - "
            "leaving emission wiring unchanged"
        )
        return False

    emission_input = _find_emission_input(bsdf)
    if emission_input is None:
        log(
            f"[screen-emission] no Emission Color input in '{screen_material.name}' - "
            "leaving emission wiring unchanged"
        )
        return False

    nodes = screen_material.node_tree.nodes
    links = screen_material.node_tree.links

    if not enabled:
        removed = _remove_gate_nodes(screen_material)
        _disconnect_emission_input(screen_material, emission_input)
        links.new(image_node.outputs['Color'], emission_input)
        if removed:
            log(
                f"[screen-emission] gate removed from '{screen_material.name}'; "
                "image color wired straight into Emission Color"
            )
        return removed

    base_x = image_node.location.x
    base_y = image_node.location.y

    path_node = nodes.get(GATE_PATH_NODE)
    if path_node is None:
        path_node = nodes.new('ShaderNodeLightPath')
        path_node.name  = GATE_PATH_NODE
        path_node.label = GATE_PATH_NODE
    path_node.location = (base_x + 120, base_y - 320)

    add_node = nodes.get(GATE_ADD_NODE)
    if add_node is None:
        add_node = nodes.new('ShaderNodeMath')
        add_node.name  = GATE_ADD_NODE
        add_node.label = GATE_ADD_NODE
    add_node.operation = 'ADD'
    add_node.use_clamp = False
    add_node.location  = (base_x + 340, base_y - 320)

    clamp_node = nodes.get(GATE_CLAMP_NODE)
    if clamp_node is None:
        clamp_node = nodes.new('ShaderNodeClamp')
        clamp_node.name  = GATE_CLAMP_NODE
        clamp_node.label = GATE_CLAMP_NODE
    clamp_node.clamp_type = 'MINMAX'
    clamp_node.inputs['Min'].default_value = 0.0
    clamp_node.inputs['Max'].default_value = 1.0
    clamp_node.location = (base_x + 520, base_y - 320)

    mix_node = nodes.get(GATE_MIX_NODE)
    if mix_node is None:
        mix_node = nodes.new('ShaderNodeMixRGB')
        mix_node.name  = GATE_MIX_NODE
        mix_node.label = GATE_MIX_NODE
    mix_node.blend_type = 'MULTIPLY'
    mix_node.inputs['Fac'].default_value = 1.0
    mix_node.location = (base_x + 720, base_y - 60)

    # Tear down any links into our gate chain (idempotent re-runs).
    for link in list(links):
        if link.to_node in (add_node, clamp_node, mix_node):
            links.remove(link)

    camera_socket = path_node.outputs.get('Is Camera Ray')
    glossy_socket = path_node.outputs.get('Is Glossy Ray')

    if camera_socket is None:
        log(
            f"[screen-emission] Light Path node missing 'Is Camera Ray' on this "
            f"Blender build - skipping gate on '{screen_material.name}'"
        )
        return False

    links.new(camera_socket, add_node.inputs[0])
    if allow_glossy and glossy_socket is not None:
        links.new(glossy_socket, add_node.inputs[1])
    else:
        add_node.inputs[1].default_value = 0.0

    links.new(add_node.outputs[0], clamp_node.inputs['Value'])

    _disconnect_emission_input(screen_material, emission_input)
    links.new(image_node.outputs['Color'],     mix_node.inputs['Color1'])
    links.new(clamp_node.outputs['Result'],    mix_node.inputs['Color2'])
    links.new(mix_node.outputs['Color'],       emission_input)

    log(
        f"[screen-emission] gated on '{screen_material.name}' "
        f"(camera{' + glossy' if allow_glossy and glossy_socket else ''} "
        "rays pass through, diffuse/shadow rays masked)"
    )
    return True
