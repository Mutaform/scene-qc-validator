from ..common import *


def check_zero_length_edges(obj, item):
    threshold = item.float_param_1 if item.float_param_1 > 0 else 1e-6
    if obj.data.is_editmode:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        bad = [e.index for e in bm.edges if e.calc_length() < threshold]
        if bad:
            return [{
                "message": f"{len(bad)} edge(s) shorter than {threshold}",
                "element_ref": "e:" + ",".join(map(str, bad)),
            }]
        return []

    bm = _bmesh_from_obj(obj)
    bad = [e.index for e in bm.edges if e.calc_length() < threshold]
    bm.free()
    if bad:
        return [{
            "message": f"{len(bad)} edge(s) shorter than {threshold}",
            "element_ref": "e:" + ",".join(map(str, bad)),
        }]
    return []


def fix_zero_length_edges(obj, item, result):
    threshold = item.float_param_1 if item.float_param_1 > 0 else 1e-6
    if obj.data.is_editmode:
        if bpy.context.view_layer.objects.active != obj:
            bpy.context.view_layer.objects.active = obj
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        before = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=threshold)
        bmesh.update_edit_mesh(obj.data)
        return len(bm.verts) != before

    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bm = _bmesh_from_obj(obj)
    before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=threshold)
    _write_bmesh(obj, bm)
    return len(obj.data.vertices) != before
