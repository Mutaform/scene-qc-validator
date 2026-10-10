# Импорты здесь - часть экспорта, а не личная нужда этого файла: __all__
# внизу собирает всё из globals(), а модули проверок делают
# `from ..common import *`. На `mathutils` отсюда живут collision,
# pivot_center, pivot_world_origin и unapplied_transform - сами они его не
# импортируют. Так что «неиспользуемый» импорт тут убирать нельзя: проверки
# упадут на NameError только в момент запуска.
import re
import bmesh
import bpy
import mathutils


def _bmesh_from_obj(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    return bm


def _read_bmesh(obj):
    """(bmesh, освобождать ли). Единственный надёжный способ прочитать атрибуты.

    В режиме правки RNA-массивы атрибутов пусты. Не «иногда» и не «пока не
    обновили»: проверено на Blender 5.2 на живом ассете - 44 908 лупов,
    `len(uv_layers["UV1"].data) == 0` и после `update_from_editmode()`, который
    вернул True; у атрибутов цвета то же самое. Геометрия при этом читается
    нормально, поэтому пустота выглядит не как отказ, а как «на меше нет UV».

    Цена этого была видна на полке в Edit Mode: uv_single_tile давал ложную
    ошибку «канал не читается», а замеры паддинга и плотности молча
    отключались - четыре находки вместо пяти, и художник решил бы, что чисто.

    bmesh правки отдавать наружу можно, а освобождать нельзя: он принадлежит
    редактору, и free() уронил бы сессию. Про это и второе значение.
    """
    if obj.mode == 'EDIT' or getattr(obj.data, "is_editmode", False):
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        return bm, False
    return _bmesh_from_obj(obj), True


def _write_bmesh(obj, bm):
    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()


def _parse_name_list(text):
    return [t.strip() for t in text.split(",") if t.strip()]


def _strip_blender_numeric_suffix(name):
    return re.sub(r"\.\d{3}$", "", name)


def _clean_asset_name(name):
    name = _strip_blender_numeric_suffix(name)
    name = re.sub(r"^(SM|SK|M)_", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "Asset"


def _unique_id_name(collection, desired, current=None):
    if current and desired == current.name:
        return desired
    if collection.get(desired) is None:
        return desired
    index = 1
    while True:
        candidate = f"{desired}_{index:02d}"
        if collection.get(candidate) is None or (current and candidate == current.name):
            return candidate
        index += 1


def _object_project_name(obj):
    base = _clean_asset_name(obj.name)
    prefix = "SK" if obj.type == 'ARMATURE' or base.lower().startswith(("sk_", "skel", "skeleton", "rig")) else "SM"
    return _unique_id_name(bpy.data.objects, f"{prefix}_{base}", obj)


def _world_scale(obj, enabled=True):
    """Во сколько раз локальная единица объекта больше мировой.

    Пороги «нулевой длины» и «нулевой площади» задаются в метрах сцены, а меряет
    их проверка по данным меша - то есть в локальных единицах. Пока трансформ не
    применён, это разные вещи: у ассета с масштабом 0.01 локальная единица - это
    сантиметр, и порог 0.1 мм на деле означает 1 мкм. Применили трансформ -
    и тот же ассет внезапно судится в сто раз строже, хотя геометрия не менялась.

    Поэтому замер домножается на масштаб объекта. Нужен самый мелкий из трёх:
    неравномерный масштаб сжимает сильнее всего по одной оси, и судить надо по
    ней, иначе вырожденное ребро проскочит.
    """
    if not enabled:
        return 1.0
    try:
        return min(abs(value) for value in obj.matrix_world.to_scale()) or 1.0
    except (AttributeError, ValueError):
        return 1.0


__all__ = [name for name in globals() if not name.startswith("__")]
