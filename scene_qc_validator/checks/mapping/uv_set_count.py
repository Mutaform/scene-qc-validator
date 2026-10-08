from ..common import *


def check_uv_set_count(obj, item):
    max_count = item.int_param_1 if item.int_param_1 > 0 else 1
    count = len(obj.data.uv_layers)
    if count > max_count:
        return [{
            "message": f"Object has {count} UV map(s), maximum allowed is {max_count}",
            "element_ref": "",
            "values": {"count": count, "max": max_count,
                       "names": [uv.name for uv in obj.data.uv_layers],
                       "extra": [uv.name for uv in obj.data.uv_layers][max_count:]},
        }]
    return []
