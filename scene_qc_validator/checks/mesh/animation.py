from ..common import *


def _has_animation_data(id_block):
    ad = getattr(id_block, "animation_data", None)
    if not ad:
        return False
    if getattr(ad, "action", None):
        return True
    if len(getattr(ad, "drivers", ())) > 0:
        return True
    if len(getattr(ad, "nla_tracks", ())) > 0:
        return True
    return False


def check_animation_keys(obj, item):
    sources = []
    if _has_animation_data(obj):
        sources.append("object")
    if _has_animation_data(obj.data):
        sources.append("mesh data")
    shape_keys = getattr(obj.data, "shape_keys", None)
    if shape_keys and _has_animation_data(shape_keys):
        sources.append("shape keys")
    if sources:
        return [{
            "message": "Animation data found on " + ", ".join(sources),
            "element_ref": "",
        }]
    return []


def fix_animation_keys(obj, item, result):
    obj.animation_data_clear()
    obj.data.animation_data_clear()
    shape_keys = getattr(obj.data, "shape_keys", None)
    if shape_keys:
        shape_keys.animation_data_clear()
    return True
