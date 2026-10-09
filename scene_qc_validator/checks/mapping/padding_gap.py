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

Отчитываемся ЗАЗОРОМ между шеллами. У UVPackmaster параметр Margin (px) - это
расстояние между шеллами целиком, а не раздувание каждого: проверено на кубе,
упакованном с Margin 16 при 2048, - между соседними островами ровно 16.0 px,
до края тайла 8. Делить пополам для этого пакера неверно.

Наложенные друг на друга острова - не соседи. Стакинг на текстурном канале
законный приём: повторяющиеся куски кладут в одно место, чтобы маски выходили
детальнее. Расстояние между такими островами - не отступ, а почти ноль, и
считать его отступом бессмысленно. Узнаются они по пересечению габаритов.

Замерено на живой полке: из 121 острова у 108 ближайшим оказывался наложенный
на них же, и отступ выходил 1.8 px вместо настоящих 33. Отбрасывать только
нулевые расстояния не помогло - у двух наложенных шеллов контуры расходятся на
пиксель-другой, и эта разница подменяла собой отступ.

Соприкасающиеся острова тоже не считаются: всё, что ближе пикселя, - это
склейка, а не отступ. На кубе четыре острова из шести имели ноль до
ближайшего, и медиана выходила нулевой при настоящем отступе 16.

Край тайла в расчёт не берётся: у пакера для него свой параметр (Border
Margin), и на том же кубе он вдвое меньше междушелльного.

Результат округляется до целого пикселя: это оценка, а не измерение. Точки
контура дают расстояние чуть больше истинного - между точками, а не между
линиями.

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

# Сколько шеллов показывать по нажатию на находку. Выделять все сто с лишним -
# то же, что не выделять ничего: смотреть надо на худшие.
SHOW_SHELLS = 20


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


def measure_gap(obj, layer, reach=None, floor=0.0):
    """(медиана, минимум, число шеллов) в единицах UV, или None.

    `floor` - ниже этого расстояния соседи считаются склеенными и в расчёт не
    идут. Шелл, у которого нет соседа в радиусе, тоже выпадает: про настройку
    пакера он ничего не говорит.
    """
    islands = [island for island in islands_of(obj, layer, 1e-4) if island.in_grid]
    if len(islands) < 2:
        return None
    points = _boundary_points(obj, layer, islands)
    if len(points) < 2:
        return None

    # наложенные пары: габариты пересекаются - значит это стак, а не соседство
    stacked = set()
    for first in range(len(islands)):
        a = islands[first]
        for second in range(first + 1, len(islands)):
            b = islands[second]
            if (a.umin < b.umax and b.umin < a.umax
                    and a.vmin < b.vmax and b.vmin < a.vmax):
                stacked.add((first, second))
                stacked.add((second, first))

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
    floor_squared = floor * floor
    for (tile, x, y), here in buckets.items():
        near = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                near.extend(buckets.get((tile, x + dx, y + dy), ()))
        for index, u, v in here:
            for other_index, ou, ov in near:
                if other_index == index or (index, other_index) in stacked:
                    continue
                distance = (u - ou) ** 2 + (v - ov) ** 2
                if distance <= floor_squared or distance >= limit:
                    continue        # вплотную - это склейка, а не отступ
                if distance < best.get(index, limit):
                    best[index] = distance
    if not best:
        return None
    nearest = {index: math.sqrt(value) for index, value in best.items()}
    values = sorted(nearest.values())
    return _median(values), values[0], len(values), nearest, islands


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
        found = measure_gap(obj, layer, floor=1.0 / size)
        if found is None:
            continue
        median_uv, minimum_uv, pairs, nearest, islands = found
        padding_px = median_uv * size
        if low <= round(padding_px) <= high:
            continue
        # грани тех шеллов, что увели замер за норму: художник нажмёт на находку
        # и увидит в UV-редакторе ровно их, а не будет искать сам
        guilty = sorted(
            (index for index, value in nearest.items()
             if not low <= round(value * size) <= high),
            key=lambda index: abs(nearest[index] * size - padding_px),
            reverse=True)[:SHOW_SHELLS]
        faces = sorted({face for index in guilty for face in islands[index].faces})
        issues.append({
            "message": ("Padding on UV set %s looks like %.0f px at %d, "
                        "expected %g..%g (tightest %.1f px over %d shell(s))"
                        % (layer.name, padding_px, size, low, high,
                           minimum_uv * size, pairs)),
            "element_ref": ("uv:%s;f:%s" % (layer.name, ",".join(map(str, faces)))
                            if faces else "uv:%s" % layer.name),
            "values": {"uv": layer.name, "padding": round(padding_px, 1),
                       "size": size, "min": low, "max": high, "shells": pairs,
                       "tightest": round(minimum_uv * size, 1),
                       "shown": len(guilty), "tight": padding_px < low},
        })
    return issues
