from ..common import *


def check_non_manifold(obj, item):
    bm = _bmesh_from_obj(obj)
    bad = [e.index for e in bm.edges if not e.is_manifold]
    bm.free()
    if bad:
        return [{
            "message": f"{len(bad)} non-manifold edge(s) found",
            "element_ref": "e:" + ",".join(map(str, bad)),
        }]
    return []
