# -*- coding: utf-8 -*-
"""Плотность текселя: сколько пикселей карты приходится на размер модели.

Считаем ровно как чекер в движке (`ardena_import_fix._uv_stats`), иначе два
набора разойдутся числами на одном и том же ассете. На каждую грань берём её
площадь в мире и площадь в UV, плотность грани - корень из их отношения
(единиц UV на сантиметр), а по мешу - **медиана, взвешенная по площади**.

Медиана, а не среднее: у ассета всегда есть пара мелких граней с растянутой
развёрткой, и среднее они утаскивают. Вес по площади - потому что плотность
большой стены важнее плотности болта на ней.

Грани без площади в UV (схлопнутые) в расчёт не идут: деление на ноль ничего
не измеряет. Их доля считается отдельно - по ней видно, что развёртка рваная.

Замер идёт в МИРОВЫХ единицах: bmesh переводится матрицей объекта. У ассета с
неприменённым масштабом 0.01 локальные размеры в сто раз меньше настоящих, и
без перевода плотность вышла бы стократно другой.

UV3 судим: по ТЗ 1024 px/м при карте 2048 (то есть 1 UV = 2 м), допуск 15%.
UV1 только показываем: норма там зависит от плана ассета - ближний, средний,
дальний, - а план по мешу не определить. Если в UV1 лежит UDIM, показываем по
тайлам отдельно: у разных тайлов плотность законно разная.
"""

import math

from ..common import *
from .overlapped_uv import _uv_polygon_area
from .udim import layer_by_index

DEFAULT_MAP_PX = 2048
DEFAULT_PX_PER_M = 1024.0
DEFAULT_TOLERANCE = 0.15
TILE_COLUMNS = 10


def _tile_of(points):
    """Номер UDIM-тайла по центру грани; -1 - вне сетки."""
    u = sum(p[0] for p in points) / len(points)
    v = sum(p[1] for p in points) / len(points)
    u_tile, v_tile = int(math.floor(u)), int(math.floor(v))
    if 0 <= u_tile < TILE_COLUMNS and v_tile >= 0:
        return 1001 + u_tile + TILE_COLUMNS * v_tile
    return -1


def samples(obj, layer, per_tile=False):
    """[(единиц UV на см, вес)] или {тайл: [...]}, плюс доля схлопнутой площади."""
    bm, owned = _read_bmesh(obj)
    if not owned:
        bm = bm.copy()              # меш в правке: живой bmesh двигать нельзя
        owned = True
    try:
        uv_layer = bm.loops.layers.uv.get(layer.name)
        if uv_layer is None:
            return ({} if per_tile else []), 0.0
        bm.transform(obj.matrix_world)
        out = {} if per_tile else []
        total = collapsed = 0.0
        for face in bm.faces:
            world_cm2 = face.calc_area() * 10000.0      # м² -> см², как в движке
            if world_cm2 <= 1e-9:
                continue
            total += world_cm2
            points = [tuple(loop[uv_layer].uv) for loop in face.loops]
            uv_area = abs(_uv_polygon_area(points))
            if uv_area <= 1e-12:
                collapsed += world_cm2
                continue
            pair = (math.sqrt(uv_area / world_cm2), world_cm2)
            if per_tile:
                out.setdefault(_tile_of(points), []).append(pair)
            else:
                out.append(pair)
        return out, (collapsed / total if total else 0.0)
    finally:
        if owned:
            bm.free()


def weighted_median(pairs):
    """Медиана плотности, взвешенная по площади. None - мерить нечего."""
    if not pairs:
        return None
    ordered = sorted(pairs)
    half = sum(weight for _d, weight in ordered) / 2.0
    run = 0.0
    for density, weight in ordered:
        run += weight
        if run >= half:
            return density
    return ordered[-1][0]


def px_per_cm(obj, number=1, map_px=DEFAULT_MAP_PX, per_tile=False):
    """Плотность канала в пикселях на сантиметр. (значение|словарь, доля схлопнутого)."""
    layer = layer_by_index(obj, number)
    if layer is None:
        return (None, 0.0)
    found, collapsed = samples(obj, layer, per_tile=per_tile)
    if per_tile:
        return ({tile: weighted_median(pairs) * map_px
                 for tile, pairs in sorted(found.items())
                 if weighted_median(pairs)}, collapsed)
    density = weighted_median(found)
    return ((density * map_px if density else None), collapsed)


def px_per_m(obj, number=3, map_px=DEFAULT_MAP_PX):
    """Плотность канала в пикселях на метр: так норма записана в ТЗ для UV3."""
    value, collapsed = px_per_cm(obj, number, map_px)
    return ((value * 100.0 if value is not None else None), collapsed)


def check_texel_density(obj, item):
    """Плотность судимого канала должна совпадать с нормой проекта."""
    number = getattr(item, "int_param_2", 0) or 3
    map_px = getattr(item, "int_param_1", 0) or DEFAULT_MAP_PX
    want = getattr(item, "float_param_1", 0.0) or DEFAULT_PX_PER_M
    tolerance = getattr(item, "float_param_2", 0.0)
    tolerance = tolerance if 0.0 < tolerance < 1.0 else DEFAULT_TOLERANCE

    layer = layer_by_index(obj, number)
    if layer is None:
        return []
    value, _collapsed = px_per_m(obj, number, map_px)
    if value is None:
        return []
    if abs(value - want) <= want * tolerance:
        return []
    return [{
        "message": ("UV set %s is %d px/m at %d, expected %d px/m (tolerance %d%%)"
                    % (layer.name, round(value), map_px, round(want),
                       round(tolerance * 100))),
        "element_ref": "uv:%s" % layer.name,
        "values": {"uv": layer.name, "px_m": int(round(value)),
                   "want": int(round(want)), "size": map_px,
                   "tolerance": int(round(tolerance * 100)),
                   "scale": round(value / want, 2) if want else 0,
                   "m_per_uv": round(map_px / value, 3) if value else 0,
                   "want_m_per_uv": round(map_px / want, 3) if want else 0},
    }]
