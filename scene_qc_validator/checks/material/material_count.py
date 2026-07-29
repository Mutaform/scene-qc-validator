from ..common import *


def check_material_count(obj, item):
    max_count = item.int_param_1 if item.int_param_1 > 0 else 1
    materials = {
        slot.material
        for slot in obj.material_slots
        if slot.material is not None
    }
    count = len(materials)
    if count > max_count:
        return [{
            "message": (
                f"Object uses {count} material(s), maximum allowed "
                f"is {max_count}"
            ),
            "element_ref": "",
        }]
    return []
