from ..common import *


def check_object_name_pattern(obj, item):
    pattern = item.string_param_1
    if not pattern:
        return []
    if not re.search(pattern, obj.name):
        return [{
            "message": f"Object name '{obj.name}' does not match pattern '{pattern}'",
            "element_ref": "",
        }]
    return []


def fix_object_name_pattern(obj, item, result):
    obj.name = _object_project_name(obj)
    return True
