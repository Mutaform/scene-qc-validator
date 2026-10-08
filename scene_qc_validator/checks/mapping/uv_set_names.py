from ..common import *


def _is_default_uv_name(name):
    return name == "UVMap" or name.startswith("UVMap.")


def _expected_names(item):
    """The UV set names a project demands, in channel order.

    Empty when the project states none: the check then only objects to the
    names Blender itself hands out, and the fix falls back to map1, map2, ...
    """
    return [name.strip() for name in item.string_param_1.split(",") if name.strip()]


def check_uv_set_names(obj, item):
    uv_layers = obj.data.uv_layers
    expected = _expected_names(item)
    if not expected:
        bad = [uv.name for uv in uv_layers if _is_default_uv_name(uv.name)]
        if bad:
            fallback = ", ".join(f"map{i + 1}" for i in range(len(uv_layers)))
            return [{
                "message": (
                    f"Default Blender UV set name(s) found: {', '.join(bad)}. "
                    f"Expected: {fallback}"
                ),
                "element_ref": "",
                "values": {"kind": "default", "bad": bad,
                           "want": [f"map{i + 1}" for i in range(len(uv_layers))]},
            }]
        return []

    issues = []
    for index, uv in enumerate(uv_layers):
        if index >= len(expected):
            issues.append({
                "message": (
                    f"UV set {index + 1} '{uv.name}' is beyond the expected "
                    f"set: {', '.join(expected)}"
                ),
                "element_ref": f"uv:{uv.name}",
                "values": {"kind": "extra", "slot": index + 1, "uv": uv.name,
                           "expected": list(expected)},
            })
        elif uv.name != expected[index]:
            issues.append({
                "message": (
                    f"UV set {index + 1} is named '{uv.name}', "
                    f"expected '{expected[index]}'"
                ),
                "element_ref": f"uv:{uv.name}",
                "values": {"kind": "named", "slot": index + 1, "uv": uv.name,
                           "want": expected[index]},
            })
    return issues


def fix_uv_set_names(obj, item, result):
    uv_layers = obj.data.uv_layers
    expected = _expected_names(item)
    if not expected:
        expected = [f"map{i + 1}" for i in range(len(uv_layers))]

    # Two passes through placeholder names: renaming a channel straight to a
    # name another channel still holds makes Blender suffix it (UV1.001), so
    # swapping two sets in place would corrupt both.
    renaming = [
        (uv, expected[index])
        for index, uv in enumerate(uv_layers)
        if index < len(expected) and uv.name != expected[index]
    ]
    if not renaming:
        return True
    for position, (uv, _target) in enumerate(renaming):
        uv.name = f"_sqc_uv_tmp_{position}"
    for uv, target in renaming:
        uv.name = target
    return True
