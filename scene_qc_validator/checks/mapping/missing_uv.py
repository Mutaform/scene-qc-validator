from ..common import *


def check_missing_uv(obj, item):
    if not obj.data.uv_layers:
        return [{"message": "No UV map found", "element_ref": ""}]
    return []
