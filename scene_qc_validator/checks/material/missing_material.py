from ..common import *

from .material_name import DEFAULT_MATERIAL_PATTERN, _material_qc_base_name, _template_material_name


def check_missing_material(obj, item):
    if not obj.material_slots or all(s.material is None for s in obj.material_slots):
        return [{
            "message": "Object has no material assigned",
            "element_ref": "",
            "values": {"slots": len(obj.material_slots), "faces": 0},
        }]
    bm = _bmesh_from_obj(obj)
    bad = [f.index for f in bm.faces if f.material_index >= len(obj.material_slots)
           or obj.material_slots[f.material_index].material is None]
    bm.free()
    if bad:
        return [{
            "message": f"{len(bad)} face(s) with no material assigned",
            "element_ref": "f:" + ",".join(map(str, bad)),
            "values": {"slots": len(obj.material_slots), "faces": len(bad)},
        }]
    return []


def _name_rule(context):
    """(шаблон, образец имени) из проверки имён материалов этого проекта."""
    settings = getattr(context.scene, "sqc_settings", None)
    if settings is None:
        return "", ""
    item = next((c for c in settings.checks if c.check_id == "mat_material_name"), None)
    if item is None:
        return "", ""
    return item.string_param_2.strip(), (item.string_param_1 or DEFAULT_MATERIAL_PATTERN)


def _new_material_for(obj, template):
    """Материал, названный по правилу проекта: по шаблону проекта, иначе m_<ассет>."""
    material = bpy.data.materials.new("Material")
    material.use_nodes = True
    if template:
        name = _template_material_name(template, obj, material)
    else:
        name = _material_qc_base_name(obj.name)
    if name:
        material.name = name
    return material


def fix_missing_material(obj, item, result):
    """Создать материал по правилу проекта и закрыть им пустые слоты.

    Имя берётся из шаблона проверки имён материалов («Fix Name Template»), так
    что материал сразу проходит и проверку имени: у ARDENA это «MI_<имя ассета>».
    """
    template, _pattern = _name_rule(bpy.context)
    changed = False

    if not obj.material_slots:
        obj.data.materials.append(_new_material_for(obj, template))
        return True

    # пустые слоты закрываем материалом самого ассета: либо уже назначенным,
    # либо новым, чтобы не плодить по материалу на слот
    existing = next((s.material for s in obj.material_slots if s.material), None)
    material = existing or _new_material_for(obj, template)
    for slot in obj.material_slots:
        if slot.material is None:
            slot.material = material
            changed = True
    if changed:
        return True

    # слоты заполнены, но часть граней смотрит за их пределы - вернём такие грани
    # в первый слот, иначе в движке они останутся без материала
    mesh = obj.data
    limit = len(obj.material_slots)
    for polygon in mesh.polygons:
        if polygon.material_index >= limit:
            polygon.material_index = 0
            changed = True
    if changed:
        mesh.update()
    return changed
