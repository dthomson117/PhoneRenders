import bpy

from render_lib._compat import set_attr_safe
from render_lib.logging_utils import log

ALPHA_THRESHOLD_TREE_NAME = "_AppStoreAlphaThreshold"


def _alpha_threshold_acquire_tree(scene):
    """Return the compositor node tree to build into."""
    if hasattr(scene, 'compositing_node_group'):
        tree = bpy.data.node_groups.get(ALPHA_THRESHOLD_TREE_NAME)
        if tree is not None and getattr(tree, 'type', None) != 'COMPOSITING':
            bpy.data.node_groups.remove(tree)
            tree = None
        if tree is None:
            tree = bpy.data.node_groups.new(
                ALPHA_THRESHOLD_TREE_NAME, "CompositorNodeTree"
            )
        scene.compositing_node_group = tree

        try:
            items = list(tree.interface.items_tree)
            for item in items:
                tree.interface.remove(item)
            tree.interface.new_socket(
                name="Image", in_out='OUTPUT', socket_type='NodeSocketColor'
            )
        except (AttributeError, RuntimeError) as exc:
            log(f"[alpha-threshold] could not reset tree interface: {exc}")

        return tree, 'NodeGroupOutput'

    set_attr_safe(scene, 'use_nodes', True)
    return scene.node_tree, 'CompositorNodeComposite'


def _new_node_first_available(tree, node_types):
    """Create the first registered node type from ``node_types``."""
    last_exc = None
    for node_type in node_types:
        try:
            return tree.nodes.new(node_type)
        except RuntimeError as exc:
            last_exc = exc
    raise RuntimeError(
        f"None of these node types are available: {', '.join(node_types)}"
    ) from last_exc


def setup_alpha_threshold_compositor(scene, threshold):
    """Wire the compositor so pixels with alpha <= ``threshold`` are forced to
    fully transparent in the output PNG."""
    tree, output_node_type = _alpha_threshold_acquire_tree(scene)

    for node in list(tree.nodes):
        tree.nodes.remove(node)

    rl = tree.nodes.new('CompositorNodeRLayers')
    rl.location = (0, 0)

    out = tree.nodes.new(output_node_type)
    out.location = (900, 0)

    if threshold <= 0.0:
        tree.links.new(rl.outputs['Image'], out.inputs[0])
        log("[alpha-threshold] off (pass-through compositor)")
        return

    gt = _new_node_first_available(tree, ('ShaderNodeMath', 'CompositorNodeMath'))
    gt.operation = 'GREATER_THAN'
    gt.inputs[1].default_value = float(threshold)
    gt.location = (250, -120)

    mult = _new_node_first_available(tree, ('ShaderNodeMath', 'CompositorNodeMath'))
    mult.operation = 'MULTIPLY'
    mult.location = (470, -120)

    set_alpha = tree.nodes.new('CompositorNodeSetAlpha')
    set_attr_safe(set_alpha, 'mode', 'REPLACE_ALPHA')
    set_alpha.location = (700, 0)

    links = tree.links
    links.new(rl.outputs['Image'], set_alpha.inputs['Image'])
    links.new(rl.outputs['Alpha'], gt.inputs[0])
    links.new(rl.outputs['Alpha'], mult.inputs[0])
    links.new(gt.outputs[0], mult.inputs[1])
    links.new(mult.outputs[0], set_alpha.inputs['Alpha'])
    links.new(set_alpha.outputs['Image'], out.inputs[0])

    log(f"[alpha-threshold] on (threshold={threshold:.3f})")
