from ..common import *


def _soft_edge_indices_from_bmesh(bm):
    bm.edges.ensure_lookup_table()
    return [edge.index for edge in bm.edges if edge.smooth]


def _sharp_edge_indices_from_bmesh(bm):
    bm.edges.ensure_lookup_table()
    return [edge.index for edge in bm.edges if not edge.smooth]


def _soft_edge_indices_from_mesh(mesh):
    return [edge.index for edge in mesh.edges if not edge.use_edge_sharp]


def _sharp_edge_indices_from_mesh(mesh):
    return [edge.index for edge in mesh.edges if edge.use_edge_sharp]


def check_has_soft_edges(obj, item):
    if obj.data.is_editmode:
        bm = bmesh.from_edit_mesh(obj.data)
        soft_edges = _soft_edge_indices_from_bmesh(bm)
        sharp_edges = _sharp_edge_indices_from_bmesh(bm)
    else:
        soft_edges = _soft_edge_indices_from_mesh(obj.data)
        sharp_edges = _sharp_edge_indices_from_mesh(obj.data)

    if not soft_edges:
        return [{
            "message": "Object has marked sharp edges only",
            "element_ref": "e:" + ",".join(map(str, sharp_edges)) if sharp_edges else "",
        }]
    return []


def fix_has_soft_edges(obj, item, result):
    if obj.data.is_editmode:
        if bpy.context.view_layer.objects.active != obj:
            bpy.context.view_layer.objects.active = obj
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        changed = False
        for edge in bm.edges:
            if not edge.smooth:
                edge.smooth = True
                changed = True
        if changed:
            bmesh.update_edit_mesh(obj.data)
        return changed

    changed = False
    for edge in obj.data.edges:
        if edge.use_edge_sharp:
            edge.use_edge_sharp = False
            changed = True
    if changed:
        obj.data.update()
    return changed
