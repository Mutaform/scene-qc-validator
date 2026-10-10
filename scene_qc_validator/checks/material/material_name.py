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


def _unique_material_name(desired, mat):
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


def _material_qc_name(mat):
    return _unique_material_name(_material_qc_base_name(mat.name), mat)


def _template_material_name(template, obj, mat):
    """Build a material name from the object it sits on.

    A project can name materials after the asset rather than after whatever the
    material happened to be called: ARDENA wants
    `S_TAR_DK_Estate_GuestRoom_Bed_01` to carry `MI_TAR_DK_Estate_GuestRoom_Bed_01`,
    which is the template `MI_{asset}`.

    * ``{object}`` - the object's own name;
    * ``{asset}``  - that name without its leading type token (`S_`, `SM_`, ...).
    """
    asset = re.sub(r"^[A-Za-z]+_", "", obj.name, count=1)
    desired = template.format(object=obj.name, asset=asset).strip()
    if not desired:
        return None
    return _unique_material_name(desired, mat)


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
            "values": {"names": sorted(set(bad)), "allowed": list(allowed)},
        }]
    return []


def fix_material_name(obj, item, result):
    fixed = False
    suffix_re = re.compile(r"^(?P<base>.+)\.\d{3}$")

    # Pass 1: collapse Blender's auto-numbered duplicates (Material.001,
    # Material.002, ...) back onto their parent material wherever it still
    # exists. This must finish before any renaming, otherwise renaming the
    # parent first makes the `.001/.002` slots fail to find it and they end up
    # split into separate materials instead of merged.
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

    # Pass 2: rename each remaining material to its QC-compliant name.
    template = item.string_param_2.strip()
    pattern = item.string_param_1 or DEFAULT_MATERIAL_PATTERN
    if pattern == LEGACY_MATERIAL_PATTERN:
        pattern = DEFAULT_MATERIAL_PATTERN
    allowed = _parse_name_list(pattern)
    for slot in obj.material_slots:
        mat = slot.material
        if not mat:
            continue
        target_name = None
        if template:
            try:
                target_name = _template_material_name(template, obj, mat)
            except (KeyError, IndexError, ValueError) as error:
                print(
                    "[Scene QC Validator] Material name template "
                    f"'{template}' is not usable: {error}"
                )
                return fixed
        if target_name is None:
            target_name = _material_qc_name(mat)
        # Имя, которое не пройдёт ЭТУ ЖЕ проверку, - не починка.
        #
        # `_material_qc_name` строит студийное `m_<имя>`, и пока у проекта не
        # было своего шаблона, этого хватало. У проекта со своим правилом
        # (MET: `^MI_<уровень>_…`) та же запасная ветка переименовывала
        # `MI_GKZ_Sphinx_PapierMache_01_Wood` в `m_mi_gkz_sphinx_papiermache` -
        # имя, которое проверка отвергает следующим же прогоном, а художник
        # остаётся без исходного (денис, 2026-10-10). Теперь кандидат
        # сверяется с шаблоном проекта, и не подошедший материал не трогаем:
        # пусть находка останется и его переименуют руками.
        #
        # У ARDENA шаблон `MI_{asset}` даёт имя, которое её же регэксп
        # принимает, у студийного пресета - `m_…` под студийный регэксп:
        # там ничего не меняется.
        if allowed and not any(_material_allowed(target_name, token)
                               for token in allowed):
            continue
        if mat.name != target_name:
            mat.name = target_name
            fixed = True
    return fixed
