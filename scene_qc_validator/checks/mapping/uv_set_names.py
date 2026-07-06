from ..common import *


def _is_default_uv_name(name):
    return name == "UVMap" or name.startswith("UVMap.")


def check_uv_set_names(obj, item):
    bad = [uv.name for uv in obj.data.uv_layers if _is_default_uv_name(uv.name)]
    if bad:
        expected = ", ".join(f"map{i + 1}" for i in range(len(obj.data.uv_layers)))
        return [{
            "message": f"Default Blender UV set name(s) found: {', '.join(bad)}. Expected: {expected}",
            "element_ref": "",
        }]
    return []


def fix_uv_set_names(obj, item, result):
    for i, uv in enumerate(obj.data.uv_layers, start=1):
        uv.name = f"map{i}"
    return True
