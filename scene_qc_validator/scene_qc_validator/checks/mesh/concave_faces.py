from ..common import *


def _concave_faces_from_bmesh(bm):
    bm.faces.ensure_lookup_table()
    bad = []
    for face in bm.faces:
        if len(face.verts) < 4:
            continue
        if any(not loop.is_convex for loop in face.loops):
            bad.append(face.index)
    return bad


def check_concave_faces(obj, item):
    if obj.data.is_editmode:
        bm = bmesh.from_edit_mesh(obj.data)
        bad = _concave_faces_from_bmesh(bm)
    else:
        bm = _bmesh_from_obj(obj)
        bad = _concave_faces_from_bmesh(bm)
        bm.free()

    if bad:
        return [{
            "message": f"{len(bad)} concave face(s) found",
            "element_ref": "f:" + ",".join(map(str, bad)),
        }]
    return []


def fix_concave_faces(obj, item, result):
    if obj.data.is_editmode:
        if bpy.context.view_layer.objects.active != obj:
            bpy.context.view_layer.objects.active = obj
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        faces = [face for face in bm.faces if len(face.verts) >= 4 and any(not loop.is_convex for loop in face.loops)]
        if faces:
            bmesh.ops.triangulate(bm, faces=faces)
            bmesh.update_edit_mesh(obj.data)
            return True
        return False

    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bm = _bmesh_from_obj(obj)
    faces = [face for face in bm.faces if len(face.verts) >= 4 and any(not loop.is_convex for loop in face.loops)]
    if faces:
        bmesh.ops.triangulate(bm, faces=faces)
        _write_bmesh(obj, bm)
        return True
    bm.free()
    return False
