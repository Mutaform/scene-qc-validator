"""Viewport emphasis for RandomSharp result selection only."""

import bmesh
import bpy
import gpu
from gpu_extras.batch import batch_for_shader


_draw_handle = None
_object_name = ""
_edge_indices = set()

# Blender's regular selected edge is approximately 2 px. Draw this checker at
# twice that width, in a high-contrast yellow, without touching user themes.
_LINE_WIDTH = 4.0
_COLOR = (1.0, 0.82, 0.05, 1.0)


def set_highlight(obj, edge_indices):
    global _object_name, _edge_indices
    _object_name = obj.name
    _edge_indices = set(edge_indices)
    _ensure_draw_handler()


def clear_highlight():
    global _object_name, _edge_indices
    _object_name = ""
    _edge_indices = set()


def _ensure_draw_handler():
    global _draw_handle
    if _draw_handle is None:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw, (), 'WINDOW', 'POST_VIEW'
        )


def unregister():
    global _draw_handle
    clear_highlight()
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None


def _draw():
    if not _object_name or not _edge_indices:
        return

    obj = bpy.context.scene.objects.get(_object_name)
    if not obj or bpy.context.view_layer.objects.active != obj or obj.mode != 'EDIT':
        return

    bm = bmesh.from_edit_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    positions = []
    for index in _edge_indices:
        if index >= len(bm.edges):
            continue
        edge = bm.edges[index]
        # The overlay follows Blender's live selection. Deselecting the edge
        # (including Alt-A) immediately removes the custom emphasis too.
        if not edge.select:
            continue
        positions.extend((
            obj.matrix_world @ edge.verts[0].co,
            obj.matrix_world @ edge.verts[1].co,
        ))
    if not positions:
        return

    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'LINES', {"pos": positions})
    region = bpy.context.region
    if region is None:
        return

    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')
    shader.bind()
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", _LINE_WIDTH)
    shader.uniform_float("color", _COLOR)
    batch.draw(shader)
    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('NONE')
