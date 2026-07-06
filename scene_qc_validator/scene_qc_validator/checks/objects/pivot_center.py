from ..common import *


def check_pivot_center(obj, item):
    if obj.type != 'MESH' or not obj.data.vertices:
        return []
    local_bbox_center = sum((mathutils.Vector(c) for c in obj.bound_box), mathutils.Vector()) / 8
    if local_bbox_center.length > 1e-3:
        return [{
            "message": f"Object origin is not centered on geometry (offset {local_bbox_center.length:.4f})",
            "element_ref": "",
        }]
    return []
