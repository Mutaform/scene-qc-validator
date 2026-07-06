from ..common import *


def check_pivot_world_origin(obj, item):
    tolerance = item.float_param_1 if item.float_param_1 > 0 else 0.001
    if obj.location.length > tolerance:
        return [{
            "message": f"Object origin is not at world origin (offset {obj.location.length:.4f}, tolerance {tolerance})",
            "element_ref": "",
        }]
    return []


def fix_pivot_world_origin(obj, item, result):
    old_matrix = obj.matrix_world.copy()
    new_matrix = old_matrix.copy()
    new_matrix.translation = mathutils.Vector((0.0, 0.0, 0.0))
    if obj.type == 'MESH':
        obj.data.transform(new_matrix.inverted() @ old_matrix)
        obj.data.update()
    obj.matrix_world = new_matrix
    return True
