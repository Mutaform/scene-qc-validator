# -*- coding: utf-8 -*-
"""Отступ между шеллами: прикинуть, какой паддинг художник задал при паковке.

Что меряем и почему именно так. Точный зазор между контурами тут не нужен и
даже вреден: у шелла сложной формы два соседа могут локально сойтись ближе, чем
задавал пакер, и это не дефект раскладки, а следствие формы. Минимум по всей
развёртке такое защемление и покажет - то есть соврёт про настройку, которую мы
ищем. Нужна типичная величина, а не худшая.

Поэтому: у каждого шелла берём расстояние до ближайшего соседа, и из этих
расстояний - медиану. Медиана переживает и пару защемлённых шеллов, и пару
улетевших далеко.

Считаем по ТОЧКАМ контура, а не по отрезкам: разница между ними меньше шага
тесселяции, а работы на порядок меньше. Габариты не годятся вовсе - замерено на
живом ассете: у плотно упакованной раскладки габариты шеллов перекрываются
сплошь, и зазор по ним выходит нулевым у всех.

Точки раскладываются в сетку с ячейкой в радиус поиска, так что каждая
сравнивается только с соседними ячейками. Дальше радиуса не смотрим: шелл, у
которого нет соседа ближе, про настройку пакера ничего не говорит.

Зазор - это ДВА паддинга. Пакер раздувает каждый шелл на заданную величину, и
между двумя соседями получается сумма их отступов. Проверено на живом ассете
(S_TAR_DK_Estate_GuestRoom_Bed_01, упакован под 16 px при 2048): до края тайла
15.99 px, между шеллами 32.9. Поэтому отчитываемся половиной зазора - тем
числом, которое художник вбил в пакер, а не тем, что между шеллами видно.

Край тайла в расчёт не берётся: там отступ одинарный, и смешивать его с
двойным в одной медиане значит её смазать.

Результат округляется до целого пикселя: это оценка, а не измерение. Точки
контура дают расстояние чуть больше истинного (между точками, а не между
линиями), и на упакованном ассете это дало 16.45 вместо 16 - с жёсткой границей
правильно упакованный ассет падал бы на половине пикселя.

Шеллы в разных UDIM-тайлах не сравниваются: это разные текстуры, и зазор между
ними ничего не значит.
"""

import math

from ..common import *
from .udim import islands_of, layer_by_index

# Во сколько раз дальше верхней границы ещё интересно смотреть. Шелл, у которого
# ближайший сосед дальше, в медиану не идёт: он стоит на отшибе и про отступ,
# заданный пакером, ничего не сообщает.
REACH = 4.0


def _boundary_points(obj, layer, islands):
    """{номер шелла: точки его контура} в UV.

    Контур - точки рёбер, у которых соседняя грань либо из другого шелла, либо
    разошлась по UV. Внутренние точки до соседей не ближе своих же границ, и
    тащить их в расчёт незачем.
    """
    bm = _bmesh_from_obj(obj)
    try:
        uv_layer = bm.loops.layers.uv.get(layer.name)
        if uv_layer is None:
            return {}
        owner = {}
        for index, island in enumerate(islands):
            for face_index in island.faces:
                owner[face_index] = index
        bm.faces.ensure_lookup_table()

        points = {}
        for face in bm.faces:
            island_index = owner.get(face.index)
            if island_index is None:
                continue
            for loop in face.loops:
                edge = loop.edge
                linked = [f for f in edge.link_faces if f.index != face.index]
                if linked and owner.get(linked[0].index) == island_index:
                    # ребро внутри шелла: его точки не на контуре
                    other = linked[0]
                    shared = sum(1 for other_loop in other.loops
                                 if (other_loop[uv_layer].uv - loop[uv_layer].uv).length < 1e-5)
                    if shared:
                        continue
                points.setdefault(island_index, set()).add(
                    tuple(round(value, 6) for value in loop[uv_layer].uv))
        return {index: list(found) for index, found in points.items()}
    finally:
        bm.free()


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def measure_gap(obj, layer, reach=None):
    """(медиана, минимум, число шеллов) в единицах UV, или None.

    Шелл, у которого нет соседа в радиусе, в расчёт не идёт: про настройку
    пакера он ничего не говорит.
    """
    islands = [island for island in islands_of(obj, layer, 1e-4) if island.in_grid]
    if len(islands) < 2:
        return None
    points = _boundary_points(obj, layer, islands)
    if len(points) < 2:
        return None

    radius = reach if reach and reach > 0 else (16.0 * REACH) / 2048.0
    cell = radius
    buckets = {}
    for index, found in points.items():
        tile = islands[index].tile
        for u, v in found:
            buckets.setdefault(
                (tile, int(math.floor(u / cell)), int(math.floor(v / cell))), []
            ).append((index, u, v))

    best = {}
    limit = radius * radius
    for (tile, x, y), here in buckets.items():
        near = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                near.extend(buckets.get((tile, x + dx, y + dy), ()))
        for index, u, v in here:
            for other_index, ou, ov in near:
                if other_index == index:
                    continue
                distance = (u - ou) ** 2 + (v - ov) ** 2
                if distance >= limit:
                    continue
                if distance < best.get(index, limit):
                    best[index] = distance
    if not best:
        return None
    nearest = [math.sqrt(value) for value in best.values()]
    return _median(nearest), min(nearest), len(nearest)


def check_padding_gap(obj, item):
    """Типичный отступ между шеллами должен лежать в заданных границах."""
    size = item.int_param_1 if item.int_param_1 > 0 else 2048
    low = item.float_param_1 if item.float_param_1 > 0 else 8.0
    high = item.float_param_2 if item.float_param_2 > 0 else 16.0

    # Канал берём по НОМЕРУ: как он назван, проверяет uv_set_names, замеру имя
    # безразлично. Канала нет вовсе - здесь молчим, про это скажут uv_missing и
    # uv_set_count; но строка разбора покажет «не измерен» серым, а не зелёную
    # галочку (см. facts._padding_gap).
    layer = layer_by_index(obj, item.int_param_2 or 1)
    issues = []
    for layer in ([layer] if layer is not None else []):
        found = measure_gap(obj, layer)
        if found is None:
            continue
        median_uv, minimum_uv, pairs = found
        gap_px = median_uv * size
        padding_px = gap_px / 2.0
        if low <= round(padding_px) <= high:
            continue
        issues.append({
            "message": ("Padding on UV set %s looks like %.0f px at %d, "
                        "expected %g..%g (shell gap %.1f px over %d shell(s))"
                        % (layer.name, padding_px, size, low, high, gap_px, pairs)),
            "element_ref": "uv:%s" % layer.name,
            "values": {"uv": layer.name, "padding": round(padding_px, 1),
                       "gap": round(gap_px, 1), "size": size,
                       "min": low, "max": high, "shells": pairs,
                       "tightest": round(minimum_uv * size / 2.0, 1),
                       "tight": padding_px < low},
        })
    return issues
