# -*- coding: utf-8 -*-
"""Пивот внизу: низ геометрии должен лежать на уровне точки опоры объекта.

Правило ARDENA: ассет ставится на пол, и его начало координат - низ, а не
центр габарита и не случайная точка. Проверяет это сейчас только чекер в
движке (`MESH.PIVOT.Z`, допуск 0.1 см), то есть ошибка всплывает уже после
импорта - когда ассет отдан, принят и разложен по сцене.

Считаем, как считает движок: берём САМУЮ НИЖНЮЮ точку геометрии и смотрим, на
сколько она отстоит от пивота по мировой оси Z. В движок ассет приезжает с
применённым трансформом, и там локальные координаты меша - это и есть
координаты ассета; в Blender тот же смысл даёт замер относительно пивота в
мировых единицах.

Не габарит `obj.bound_box`: у повёрнутого объекта его нижний угол лежит ниже
настоящей геометрии, и проверка начала бы врать ровно на тех ассетах, у
которых поворот ещё не применён (а это каждый свежий импорт FBX из Maya).

Знак важен для текста находки: плюс - пивот под геометрией (ассет будет парить
над полом), минус - геометрия ушла ниже пивота (утонет).
"""

from ..common import *

DEFAULT_TOLERANCE = 0.001           # метр = 0.1 см, как в чекере движка


def _tolerance(item):
    value = getattr(item, "float_param_1", 0.0)
    return value if value and value > 0 else DEFAULT_TOLERANCE


def bottom_offset(obj):
    """На сколько метров низ геометрии выше пивота. None - мерить нечего."""
    if obj.type != 'MESH':
        return None
    bm, owned = _read_bmesh(obj)
    try:
        if not bm.verts:
            return None
        matrix = obj.matrix_world
        lowest = min((matrix @ vertex.co).z for vertex in bm.verts)
        return lowest - matrix.translation.z
    finally:
        if owned:
            bm.free()


def check_pivot_bottom(obj, item):
    tolerance = _tolerance(item)
    offset = bottom_offset(obj)
    if offset is None or abs(offset) <= tolerance:
        return []
    return [{
        "message": ("Lowest point sits %.3f m from the pivot, the pivot belongs at "
                    "the bottom (tolerance %g m)" % (offset, tolerance)),
        "element_ref": "",
        "values": {"offset_cm": round(offset * 100.0, 2),
                   "tolerance_cm": round(tolerance * 100.0, 2),
                   "above": offset > 0},
    }]


def fix_pivot_bottom(obj, item, result):
    """Перенести пивот на низ геометрии, оставив саму геометрию на месте."""
    tolerance = _tolerance(item)
    offset = bottom_offset(obj)
    if offset is None or abs(offset) <= tolerance:
        return False
    old_matrix = obj.matrix_world.copy()
    new_matrix = old_matrix.copy()
    new_matrix.translation.z += offset
    # геометрию компенсируем обратным сдвигом - тот же приём, что у переноса
    # пивота в ноль сцены: на экране не должно шевельнуться ничего
    obj.data.transform(new_matrix.inverted() @ old_matrix)
    obj.data.update()
    obj.matrix_world = new_matrix
    return True
