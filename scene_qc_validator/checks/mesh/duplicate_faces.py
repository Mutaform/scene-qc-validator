from ..common import *


COORD_PRECISION = 6


def check_duplicate_faces(obj, item):
    bad = _duplicate_face_indices(obj)
    if bad:
        return [{
            "message": f"{len(bad)} duplicate face(s) found",
            "element_ref": "f:" + ",".join(map(str, bad)),
        }]
    return []


def _read_bmesh(obj):
    if obj.mode == 'EDIT' or obj.data.is_editmode:
        if bpy.context.view_layer.objects.active != obj:
            bpy.context.view_layer.objects.active = obj
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        return bm, False
    return _bmesh_from_obj(obj), True


def _face_position_key(face, precision=COORD_PRECISION):
    return tuple(sorted(
        (
            round(vert.co.x, precision),
            round(vert.co.y, precision),
            round(vert.co.z, precision),
        )
        for vert in face.verts
    ))


def _duplicate_face_indices(obj):
    bm, should_free = _read_bmesh(obj)
    face_map = {}
    for face in bm.faces:
        key = _face_position_key(face)
        face_map.setdefault(key, []).append(face.index)
    duplicates = [i for faces in face_map.values() if len(faces) > 1 for i in faces[1:]]
    if should_free:
        bm.free()
    return duplicates


def fix_duplicate_faces(obj, item, result):
    duplicate_indices = set(_duplicate_face_indices(obj))
    if not duplicate_indices:
        return False

    if obj.mode == 'EDIT' or obj.data.is_editmode:
        if bpy.context.view_layer.objects.active != obj:
            bpy.context.view_layer.objects.active = obj
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        faces = [face for face in bm.faces if face.index in duplicate_indices]
        if faces:
            bmesh.ops.delete(bm, geom=faces, context='FACES')
            bmesh.update_edit_mesh(obj.data)
            return True
        return False

    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bm = _bmesh_from_obj(obj)
    faces = [face for face in bm.faces if face.index in duplicate_indices]
    if faces:
        bmesh.ops.delete(bm, geom=faces, context='FACES')
        _write_bmesh(obj, bm)
        return True
    bm.free()
    return False
