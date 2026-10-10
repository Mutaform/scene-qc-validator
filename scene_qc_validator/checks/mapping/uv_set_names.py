from ..common import *


def _is_default_uv_name(name):
    return name == "UVMap" or name.startswith("UVMap.")


def _schemes(item):
    """The naming schemes a project accepts, each a list of names in channel order.

    Comma separates channels, a vertical bar separates whole schemes:
    `UV1,UV2,UV3|map1,map2,map3` means a mesh may be named either way - but one
    way for the whole mesh. MET asks for exactly that: its artists come from
    Maya, where the first channel is `map1`, and both spellings are correct,
    while mixing them inside one mesh is not.

    Empty when the project states none: the check then only objects to the
    names Blender itself hands out, and the fix falls back to map1, map2, ...
    """
    out = []
    for scheme in item.string_param_1.split("|"):
        names = [name.strip() for name in scheme.split(",") if name.strip()]
        if names:
            out.append(names)
    return out


def _chosen(schemes, uv_layers):
    """Which scheme the mesh is closest to, and whether it follows it whole.

    The mesh is judged against the scheme it already follows best, so a mesh
    named map1 / UV2 / map3 is told to fix channel 2, not channels 1 and 3.
    A tie keeps the first scheme, which is the project's preferred spelling.
    """
    names = [uv.name for uv in uv_layers]

    def hits(scheme):
        return sum(1 for index, name in enumerate(names)
                   if index < len(scheme) and name == scheme[index])

    best = max(schemes, key=hits)
    return best, hits(best)


def _belongs_elsewhere(schemes, chosen, index, name):
    """Is this name correct, but from another scheme? Then the mesh is mixed."""
    return any(scheme is not chosen and index < len(scheme)
               and scheme[index] == name
               for scheme in schemes)


def check_uv_set_names(obj, item):
    uv_layers = obj.data.uv_layers
    schemes = _schemes(item)
    if not schemes:
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

    expected, _matched = _chosen(schemes, uv_layers)
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
            mixed = _belongs_elsewhere(schemes, expected, index, uv.name)
            issues.append({
                "message": (
                    f"UV set {index + 1} is named '{uv.name}', expected "
                    f"'{expected[index]}'"
                    + (" - one naming scheme per mesh" if mixed else "")
                ),
                "element_ref": f"uv:{uv.name}",
                "values": {"kind": "named", "slot": index + 1, "uv": uv.name,
                           "want": expected[index], "mixed": mixed,
                           "scheme": list(expected),
                           "schemes": [list(s) for s in schemes]},
            })
    return issues


def fix_uv_set_names(obj, item, result):
    uv_layers = obj.data.uv_layers
    schemes = _schemes(item)
    if not schemes:
        expected = [f"map{i + 1}" for i in range(len(uv_layers))]
    else:
        # Выравниваем по той схеме, которой меш и так следует больше всего:
        # у меша map1 / UV2 / map3 чинится второй канал, а не два остальных.
        expected, _matched = _chosen(schemes, uv_layers)

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
