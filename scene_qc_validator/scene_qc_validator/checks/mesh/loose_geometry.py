from ..common import *


def check_loose_geometry(obj, item):
    bm = _bmesh_from_obj(obj)
    loose_verts = [v.index for v in bm.verts if not v.link_faces]
    loose_edges = [e.index for e in bm.edges if not e.link_faces]
    bm.free()
    if loose_verts or loose_edges:
        parts = []
        if loose_verts:
            parts.append(f"{len(loose_verts)} loose vertex/vertices")
        if loose_edges:
            parts.append(f"{len(loose_edges)} loose edge(s)")
        ref = []
        if loose_verts:
            ref.append("v:" + ",".join(map(str, loose_verts)))
        if loose_edges:
            ref.append("e:" + ",".join(map(str, loose_edges)))
        return [{
            "message": " and ".join(parts),
            "element_ref": ";".join(ref),
        }]
    return []


def fix_loose_geometry(obj, item, result):
    if obj.mode == 'EDIT' or obj.data.is_editmode:
        if bpy.context.view_layer.objects.active != obj:
            bpy.context.view_layer.objects.active = obj
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        loose_edges = [e for e in bm.edges if not e.link_faces]
        changed = bool(loose_edges)
        if loose_edges:
            bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')
        bm.verts.ensure_lookup_table()
        loose_verts = [v for v in bm.verts if not v.link_faces and not v.link_edges]
        if loose_verts:
            bmesh.ops.delete(bm, geom=loose_verts, context='VERTS')
            changed = True
        bmesh.update_edit_mesh(obj.data)
        return changed

    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bm = _bmesh_from_obj(obj)
    loose_verts = [v for v in bm.verts if not v.link_faces and not v.link_edges]
    loose_edges = [e for e in bm.edges if not e.link_faces]
    changed = bool(loose_edges or loose_verts)
    if loose_edges:
        bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')
    bm.verts.ensure_lookup_table()
    loose_verts = [v for v in bm.verts if not v.link_faces and not v.link_edges]
    if loose_verts:
        bmesh.ops.delete(bm, geom=loose_verts, context='VERTS')
    _write_bmesh(obj, bm)
    return changed
