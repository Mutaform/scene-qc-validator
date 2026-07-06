from ..common import *
from collections import defaultdict


def _uv_point_key(uv, tolerance):
    step = max(tolerance, 1e-9)
    return (round(uv.x / step), round(uv.y / step))


def _uv_edge_key(a, b, tolerance):
    return tuple(sorted((_uv_point_key(a, tolerance), _uv_point_key(b, tolerance))))


def _uv_border_edges(obj, tolerance):
    if not obj.data.uv_layers:
        return set()

    border_edges = set()
    for layer in obj.data.uv_layers:
        if len(layer.data) < len(obj.data.loops):
            continue
        edge_uvs = defaultdict(set)
        edge_use_count = defaultdict(int)
        uv_data = layer.data
        for poly in obj.data.polygons:
            loop_indices = list(poly.loop_indices)
            for offset, loop_index in enumerate(loop_indices):
                next_loop_index = loop_indices[(offset + 1) % len(loop_indices)]
                edge_index = obj.data.loops[loop_index].edge_index
                edge_use_count[edge_index] += 1
                edge_uvs[edge_index].add(_uv_edge_key(uv_data[loop_index].uv, uv_data[next_loop_index].uv, tolerance))
        for edge_index, uv_keys in edge_uvs.items():
            if edge_use_count[edge_index] < 2 or len(uv_keys) > 1:
                border_edges.add(edge_index)
    return border_edges


def _bmesh_uv_layers(bm):
    try:
        return [bm.loops.layers.uv[name] for name in bm.loops.layers.uv.keys()]
    except Exception:
        active = bm.loops.layers.uv.active
        return [active] if active else []


def _uv_border_edges_from_bmesh(bm, tolerance):
    uv_layers = _bmesh_uv_layers(bm)
    if not uv_layers:
        return set()

    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    border_edges = set()
    for layer in uv_layers:
        edge_uvs = defaultdict(set)
        edge_use_count = defaultdict(int)
        for face in bm.faces:
            for loop in face.loops:
                edge_index = loop.edge.index
                edge_use_count[edge_index] += 1
                edge_uvs[edge_index].add(
                    _uv_edge_key(loop[layer].uv, loop.link_loop_next[layer].uv, tolerance)
                )
        for edge_index, uv_keys in edge_uvs.items():
            if edge_use_count[edge_index] < 2 or len(uv_keys) > 1:
                border_edges.add(edge_index)
    return border_edges


def _is_edge_sharp(edge):
    return bool(getattr(edge, "use_edge_sharp", False))


def check_random_sharp(obj, item):
    tolerance = item.float_param_1 if item.float_param_1 > 0 else 0.001
    if obj.data.is_editmode:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        uv_borders = _uv_border_edges_from_bmesh(bm, tolerance)
        bad = [edge.index for edge in bm.edges if not edge.smooth and edge.index not in uv_borders]
        if bad:
            return [{
                "message": f"Object {obj.name} has sharp edges that are not UV borders",
                "element_ref": "e:" + ",".join(map(str, bad)),
            }]
        return []

    uv_borders = _uv_border_edges(obj, tolerance)
    bad = [edge.index for edge in obj.data.edges if _is_edge_sharp(edge) and edge.index not in uv_borders]
    if bad:
        return [{
            "message": f"Object {obj.name} has sharp edges that are not UV borders",
            "element_ref": "e:" + ",".join(map(str, bad)),
        }]
    return []


def fix_random_sharp(obj, item, result):
    tolerance = item.float_param_1 if item.float_param_1 > 0 else 0.001
    if obj.data.is_editmode:
        if bpy.context.view_layer.objects.active != obj:
            bpy.context.view_layer.objects.active = obj
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        uv_borders = _uv_border_edges_from_bmesh(bm, tolerance)
        changed = False
        for edge in bm.edges:
            if not edge.smooth and edge.index not in uv_borders:
                edge.smooth = True
                changed = True
        if changed:
            bmesh.update_edit_mesh(obj.data)
        return changed

    uv_borders = _uv_border_edges(obj, tolerance)
    changed = False
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for edge in obj.data.edges:
        if _is_edge_sharp(edge) and edge.index not in uv_borders:
            edge.use_edge_sharp = False
            changed = True
    if changed:
        obj.data.update()
    return changed
