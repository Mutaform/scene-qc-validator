# -*- coding: utf-8 -*-
"""Отступ между шеллами: замер в пикселях, а не напоминание о норме.

Что меряем. Наименьший зазор между границами РАЗНЫХ шеллов, переведённый в
пиксели целевой карты. Это и есть паддинг: по нему растекается бейк, и если
где-то зазор меньше нормы, текстура одного шелла затечёт на соседний. Хватает
одного узкого места - поэтому минимум, а не среднее.

Верхняя граница тоже нужна. Минимум больше нормы означает, что узких мест нет
нигде, то есть художник раздвинул всё с запасом и потратил место на пустоту.
Вместе нижняя и верхняя дают «от 8 до 16» - ровно то, что просит ТЗ.

Шеллы в разных UDIM-тайлах не сравниваются: это разные текстуры, и зазор между
ними ничего не значит. Край тайла считается соседом - то, что утекло за край,
не нарисует никто.

Скорость. Пар шеллов много, а отрезков границ - тысячи, поэтому вместо полного
перебора - равномерная сетка: каждый отрезок кладётся в ячейки своего габарита,
и сравнивается только с отрезками соседних ячеек. Ячейка размером с верхнюю
границу: всё, что дальше, нас уже не интересует - мы и так знаем, что норма
превышена.
"""

import math
import re

from ..common import *
from .overlapped_uv import _uv_islands_from_faces


def _point_segment_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    if length <= 1e-24:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _segments_cross(a, b, c, d):
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    d1, d2 = side(c, d, a), side(c, d, b)
    d3, d4 = side(a, b, c), side(a, b, d)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _segment_distance(a, b, c, d):
    """Расстояние между отрезками. Пересеклись - ноль."""
    if _segments_cross(a, b, c, d):
        return 0.0
    return min(
        _point_segment_distance(a[0], a[1], c[0], c[1], d[0], d[1]),
        _point_segment_distance(b[0], b[1], c[0], c[1], d[0], d[1]),
        _point_segment_distance(c[0], c[1], a[0], a[1], b[0], b[1]),
        _point_segment_distance(d[0], d[1], a[0], a[1], b[0], b[1]),
    )


def _boundary_segments(faces, uv_layer, faces_by_index):
    """Отрезки границы шелла: внутренние встречаются дважды, граничные - один раз."""
    seen = {}
    for face_index in faces:
        loops = faces_by_index[face_index].loops
        points = [tuple(loop[uv_layer].uv) for loop in loops]
        for index, start in enumerate(points):
            end = points[(index + 1) % len(points)]
            key = tuple(sorted((tuple(round(v, 6) for v in start),
                                tuple(round(v, 6) for v in end))))
            seen[key] = seen.get(key, 0) + 1
    return [(key[0], key[1]) for key, count in seen.items() if count == 1]


def _tile_of(segments):
    """Тайл шелла по его габариту: сравнивать имеет смысл только внутри тайла."""
    umin = min(min(a[0], b[0]) for a, b in segments)
    vmin = min(min(a[1], b[1]) for a, b in segments)
    return int(math.floor(umin + 1e-6)), int(math.floor(vmin + 1e-6))


def _border_distance(segments, u_tile, v_tile):
    """Ближайший край своего тайла."""
    best = float("inf")
    for a, b in segments:
        for u, v in (a, b):
            best = min(best, u - u_tile, (u_tile + 1) - u,
                       v - v_tile, (v_tile + 1) - v)
    return max(best, 0.0)


def check_padding_gap(obj, item):
    """Наименьший отступ между шеллами должен лежать в заданных границах."""
    size = item.int_param_1 if item.int_param_1 > 0 else 2048
    low = item.float_param_1 if item.float_param_1 > 0 else 8.0
    high = item.float_param_2 if item.float_param_2 > 0 else 16.0
    count_border = item.bool_param_1

    if not obj.data.uv_layers:
        return []
    expression = item.string_param_1 or r"^UV1$"
    try:
        pattern = re.compile(expression)
    except re.error as error:
        return [{
            "message": "Invalid UV set regex '%s': %s" % (expression, error),
            "element_ref": "",
            "values": {"regex": expression, "error": str(error)},
        }]

    # дальше верхней границы мерить незачем: нам важно только «не теснее низа»
    # и «не просторнее верха», а точная величина огромного зазора ни на что не влияет
    reach = (high * 2.0) / size
    issues = []
    for layer in obj.data.uv_layers:
        if not pattern.match(layer.name) or len(layer.data) < len(obj.data.loops):
            continue
        found = _measure(obj, layer, reach, count_border)
        if found is None:
            continue
        gap_uv, kind = found
        gap_px = gap_uv * size
        if low <= gap_px <= high:
            continue
        issues.append({
            "message": ("Smallest padding on UV set %s is %.1f px at %d, "
                        "expected %g..%g" % (layer.name, gap_px, size, low, high)),
            "element_ref": "uv:%s" % layer.name,
            "values": {"uv": layer.name, "gap": round(gap_px, 2), "size": size,
                       "min": low, "max": high, "kind": kind,
                       "tight": gap_px < low},
        })
    return issues


def _measure(obj, layer, reach, count_border):
    """(зазор в UV, откуда он) или None, если сравнивать не с чем."""
    bm = _bmesh_from_obj(obj)
    try:
        uv_layer = bm.loops.layers.uv.get(layer.name)
        if uv_layer is None:
            return None
        faces_by_index = {face.index: face for face in bm.faces}
        groups = _uv_islands_from_faces(bm, uv_layer, list(faces_by_index), 1e-5)
        islands = []
        for group in groups:
            segments = _boundary_segments(group, uv_layer, faces_by_index)
            if segments:
                islands.append((segments, _tile_of(segments)))
        if not islands:
            return None

        best, source = float("inf"), "shell"
        if count_border:
            for segments, (u_tile, v_tile) in islands:
                distance = _border_distance(segments, u_tile, v_tile)
                if distance < best:
                    best, source = distance, "border"

        # сетка: ячейка размером с предел, который нам интересен
        cell = max(reach, 1e-6)
        buckets = {}
        for index, (segments, tile) in enumerate(islands):
            for a, b in segments:
                x0 = int(math.floor(min(a[0], b[0]) / cell))
                x1 = int(math.floor(max(a[0], b[0]) / cell))
                y0 = int(math.floor(min(a[1], b[1]) / cell))
                y1 = int(math.floor(max(a[1], b[1]) / cell))
                for x in range(x0, x1 + 1):
                    for y in range(y0, y1 + 1):
                        buckets.setdefault((x, y), []).append((index, tile, a, b))

        checked = set()
        for (x, y), here in buckets.items():
            near = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    near.extend(buckets.get((x + dx, y + dy), ()))
            for first in here:
                for second in near:
                    if first[0] == second[0] or first[1] != second[1]:
                        continue            # свой же шелл или соседний тайл
                    key = (id(first[2]), id(second[2]))
                    if key in checked:
                        continue
                    checked.add(key)
                    distance = _segment_distance(first[2], first[3],
                                                 second[2], second[3])
                    if distance < best:
                        best, source = distance, "shell"
        return (None if best == float("inf") else (best, source))
    finally:
        bm.free()
