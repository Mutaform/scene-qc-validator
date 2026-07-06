from ..common import *


def check_missing_material(obj, item):
    if not obj.material_slots or all(s.material is None for s in obj.material_slots):
        return [{"message": "Object has no material assigned", "element_ref": ""}]
    bm = _bmesh_from_obj(obj)
    bad = [f.index for f in bm.faces if f.material_index >= len(obj.material_slots)
           or obj.material_slots[f.material_index].material is None]
    bm.free()
    if bad:
        return [{
            "message": f"{len(bad)} face(s) with no material assigned",
            "element_ref": "f:" + ",".join(map(str, bad)),
        }]
    return []
