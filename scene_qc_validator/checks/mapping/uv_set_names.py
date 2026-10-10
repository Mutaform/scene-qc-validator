from ..common import *


def _is_default_uv_name(name):
    return name == "UVMap" or name.startswith("UVMap.")


def _expected_names(item):
    """The UV set names a project demands, in channel order.

    One entry per channel, comma separated. A channel may accept several
    spellings, written with a vertical bar: `UV1|map1,UV2|map2` means the first
    channel may be called either, and the first spelling is the one the fix
    renames to. MET asks for this - its artists come from Maya, where the first
    channel is `map1`, and both names are correct there.

    Empty when the project states none: the check then only objects to the
    names Blender itself hands out, and the fix falls back to map1, map2, ...
    """
    slots = []
    for slot in item.string_param_1.split(","):
        names = [name.strip() for name in slot.split("|") if name.strip()]
        if names:
            slots.append(tuple(names))
    return slots


def _canonical(slots):
    """The name the fix renames to - the first spelling of each channel."""
    return [names[0] for names in slots]


def _spelled(names):
    """«UV1» or «UV1 or map1» - for a message that has to name the requirement."""
    return names[0] if len(names) == 1 else " or ".join(names)


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
                    f"set: {', '.join(_canonical(expected))}"
                ),
                "element_ref": f"uv:{uv.name}",
                "values": {"kind": "extra", "slot": index + 1, "uv": uv.name,
                           "expected": _canonical(expected)},
            })
        elif uv.name not in expected[index]:
            issues.append({
                "message": (
                    f"UV set {index + 1} is named '{uv.name}', "
                    f"expected '{_spelled(expected[index])}'"
                ),
                "element_ref": f"uv:{uv.name}",
                "values": {"kind": "named", "slot": index + 1, "uv": uv.name,
                           "want": expected[index][0],
                           "allowed": list(expected[index])},
            })
    return issues


def fix_uv_set_names(obj, item, result):
    uv_layers = obj.data.uv_layers
    slots = _expected_names(item)
    if not slots:
        slots = [(f"map{i + 1}",) for i in range(len(uv_layers))]
    # Канал, уже названный одним из допустимых имён, оставляем как есть:
    # переименовывать map1 в UV1 только потому, что UV1 записан первым, значит
    # менять правильное на другое правильное.
    expected = [
        uv.name if index < len(slots) and uv.name in slots[index]
        else slots[index][0] if index < len(slots) else f"map{index + 1}"
        for index, uv in enumerate(uv_layers)
    ]

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
