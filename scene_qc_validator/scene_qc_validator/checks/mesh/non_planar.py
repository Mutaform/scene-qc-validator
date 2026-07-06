from ..common import *


def _is_face_planar(face, tolerance):
    if len(face.verts) < 4:
        return True

    origin = face.verts[0].co
    normal = (face.verts[1].co - origin).cross(face.verts[2].co - origin)
    if normal.length <= 1e-12:
        return False
    normal.normalize()

    for vert in face.verts[3:]:
        if abs((vert.co - origin).dot(normal)) > tolerance:
            return False
    return True


def _non_planar_faces_from_bmesh(bm, tolerance):
    bm.faces.ensure_lookup_table()
    return [
        face.index
        for face in bm.faces
        if not _is_face_planar(face, tolerance)
    ]


def check_non_planar_faces(obj, item):
    tolerance = item.float_param_1 if item.float_param_1 > 0 else 0.00001
    if obj.data.is_editmode:
        bm = bmesh.from_edit_mesh(obj.data)
        bad = _non_planar_faces_from_bmesh(bm, tolerance)
    else:
        bm = _bmesh_from_obj(obj)
        bad = _non_planar_faces_from_bmesh(bm, tolerance)
        bm.free()

    if bad:
        return [{
            "message": f"{len(bad)} non-planar face(s) found",
            "element_ref": "f:" + ",".join(map(str, bad)),
        }]
    return []


def fix_non_planar_faces(obj, item, result):
    tolerance = item.float_param_1 if item.float_param_1 > 0 else 0.00001
    if obj.data.is_editmode:
        if bpy.context.view_layer.objects.active != obj:
            bpy.context.view_layer.objects.active = obj
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        faces = [face for face in bm.faces if not _is_face_planar(face, tolerance)]
        if faces:
            bmesh.ops.triangulate(bm, faces=faces)
            bmesh.update_edit_mesh(obj.data)
            return True
        return False

    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bm = _bmesh_from_obj(obj)
    faces = [face for face in bm.faces if not _is_face_planar(face, tolerance)]
    if faces:
        bmesh.ops.triangulate(bm, faces=faces)
        _write_bmesh(obj, bm)
        return True
    bm.free()
    return False
