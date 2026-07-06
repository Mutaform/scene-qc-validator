from ..common import *


def check_ngons(obj, item):
    bm = _bmesh_from_obj(obj)
    bad = [f.index for f in bm.faces if len(f.verts) > 4]
    bm.free()
    if bad:
        return [{
            "message": f"{len(bad)} n-gon face(s) found",
            "element_ref": "f:" + ",".join(map(str, bad)),
        }]
    return []


def fix_ngons(obj, item, result):
    if obj.mode == 'EDIT' or obj.data.is_editmode:
        if bpy.context.view_layer.objects.active != obj:
            bpy.context.view_layer.objects.active = obj
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        faces = [f for f in bm.faces if len(f.verts) > 4]
        if faces:
            bmesh.ops.triangulate(bm, faces=faces)
            bmesh.update_edit_mesh(obj.data)
            return True
        return False

    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bm = _bmesh_from_obj(obj)
    faces = [f for f in bm.faces if len(f.verts) > 4]
    if faces:
        bmesh.ops.triangulate(bm, faces=faces)
        _write_bmesh(obj, bm)
        return True
    bm.free()
    return False
