from ..common import *


DEFAULT_ZERO_AREA_THRESHOLD = 1e-10


def _zero_area_threshold(item):
    return item.float_param_1 if item.float_param_1 > 0 else DEFAULT_ZERO_AREA_THRESHOLD


def _read_bmesh(obj):
    if obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        return bm, False
    return _bmesh_from_obj(obj), True


def check_zero_area_faces(obj, item):
    threshold = _zero_area_threshold(item)
    bm, should_free = _read_bmesh(obj)
    bad = [f.index for f in bm.faces if f.calc_area() <= threshold]
    if should_free:
        bm.free()
    if bad:
        return [{
            "message": f"{len(bad)} face(s) with area below {threshold}",
            "element_ref": "f:" + ",".join(map(str, bad)),
        }]
    return []


def fix_zero_area_faces(obj, item, result):
    threshold = _zero_area_threshold(item)
    bm, should_free = _read_bmesh(obj)
    geom = [f for f in bm.faces if f.calc_area() < threshold]
    if geom:
        dist = min(max(threshold ** 0.5, 1e-12), 1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=dist, edges=bm.edges[:])
    if should_free:
        _write_bmesh(obj, bm)
    else:
        bmesh.update_edit_mesh(obj.data)
    return bool(geom)
