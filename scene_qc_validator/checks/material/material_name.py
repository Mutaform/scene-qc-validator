from ..common import *


LEGACY_MATERIAL_PATTERN = r"^m_[A-Za-z0-9_]+_01$"
DEFAULT_MATERIAL_PATTERN = r"^m_[A-Za-z0-9_]+(?:_\d{2})?$"


def _material_allowed(name, token):
    try:
        if re.fullmatch(token, name, flags=re.IGNORECASE):
            return True
    except re.error:
        pass
    return name.lower() == token.lower() or name.lower().startswith(token.lower())


def _material_qc_base_name(name):
    name = _strip_blender_numeric_suffix(name)
    name = re.sub(r"^m_", "", name, flags=re.IGNORECASE)
    name = re.sub(r"_\d{2}$", "", name)
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_").lower()
    return f"m_{name or 'material'}"


def _material_qc_name(mat):
    desired = _material_qc_base_name(mat.name)
    if mat.name == desired:
        return desired
    if bpy.data.materials.get(desired) is None:
        return desired
    index = 1
    while True:
        candidate = f"{desired}_{index:02d}"
        existing = bpy.data.materials.get(candidate)
        if existing is None or existing == mat:
            return candidate
        index += 1


def check_material_name(obj, item):
    pattern = item.string_param_1 or DEFAULT_MATERIAL_PATTERN
    if pattern == LEGACY_MATERIAL_PATTERN:
        pattern = DEFAULT_MATERIAL_PATTERN
    allowed = _parse_name_list(pattern)
    if not allowed:
        return []
    bad = []
    for slot in obj.material_slots:
        if slot.material and not any(_material_allowed(slot.material.name, token) for token in allowed):
            bad.append(slot.material.name)
    if bad:
        return [{
            "message": f"Disallowed material name(s): {', '.join(sorted(set(bad)))}",
            "element_ref": "",
        }]
    return []


def fix_material_name(obj, item, result):
    fixed = False
    suffix_re = re.compile(r"^(?P<base>.+)\.\d{3}$")
    for slot in obj.material_slots:
        mat = slot.material
        if not mat:
            continue

        match = suffix_re.match(mat.name)
        if match:
            base = bpy.data.materials.get(match.group("base"))
            if base and base != mat:
                slot.material = base
                fixed = True
                continue

        target_name = _material_qc_name(mat)
        if mat.name != target_name:
            mat.name = target_name
            fixed = True
    return fixed
