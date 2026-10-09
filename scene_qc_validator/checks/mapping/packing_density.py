# -*- coding: utf-8 -*-
"""Плотность паковки UV: сколько текстуры канал реально занимает.

Считаем ПОКРЫТУЮ площадь, а не сумму площадей шеллов. Разница существенная:
сложенные друг на друга шеллы занимают одну и ту же текстуру, и сумма их
площадей насчитала бы вдвое больше, чем художник на самом деле потратил. У
текстурного канала стакинг - законный приём экономии, и проверка не должна
ругать за него как за перерасход.

Покрытие считается растеризацией: UV-пространство каждого занятого тайла
кроется сеткой, треугольники отмечают свои клетки, занятые клетки считаются.
Точный союз многоугольников здесь не нужен - нужно число, которое художник
сверит с нормой, а сетки 512x512 на тайл хватает с запасом: ошибка идёт по
периметру шеллов и на реальной раскладке не доходит до процента.

Тронутая клетка считается занятой целиком, и это не огрубление, а то, как оно
и работает: текселю всё равно, насколько он накрыт - он потрачен.
"""

from ..common import *
from .udim import islands_of, layer_by_index

GRID = 512          # клеток на сторону тайла


def _triangles(obj, layer_name):
    """Треугольники канала в UV-пространстве. Веером от первой вершины грани:
    для замера площади разбиение не важно, важно покрытие."""
    bm, should_free = _read_bmesh(obj)
    try:
        uv_layer = bm.loops.layers.uv.get(layer_name)
        if uv_layer is None:
            return []
        out = []
        for face in bm.faces:
            points = [tuple(loop[uv_layer].uv) for loop in face.loops]
            for index in range(1, len(points) - 1):
                out.append((points[0], points[index], points[index + 1]))
        return out
    finally:
        if should_free:
            bm.free()


def _cover_tile(triangles, u_tile, v_tile, grid):
    """Сколько клеток тайла накрыто. Треугольники вне тайла отсеиваются по габариту."""
    covered = bytearray(grid * grid)
    step = 1.0 / grid
    for a, b, c in triangles:
        umin = min(a[0], b[0], c[0]) - u_tile
        umax = max(a[0], b[0], c[0]) - u_tile
        vmin = min(a[1], b[1], c[1]) - v_tile
        vmax = max(a[1], b[1], c[1]) - v_tile
        if umax <= 0.0 or umin >= 1.0 or vmax <= 0.0 or vmin >= 1.0:
            continue
        x0 = max(0, int(umin * grid))
        x1 = min(grid - 1, int(umax * grid))
        y0 = max(0, int(vmin * grid))
        y1 = min(grid - 1, int(vmax * grid))

        ax, ay = a[0] - u_tile, a[1] - v_tile
        bx, by = b[0] - u_tile, b[1] - v_tile
        cx, cy = c[0] - u_tile, c[1] - v_tile
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(area) < 1e-12:
            continue
        inverse = 1.0 / area

        for y in range(y0, y1 + 1):
            py = (y + 0.5) * step
            row = y * grid
            for x in range(x0, x1 + 1):
                if covered[row + x]:
                    continue
                px = (x + 0.5) * step
                # барицентрические координаты: точка внутри, если все три
                # положительны (знак площади уже учтён делением)
                w0 = ((bx - px) * (cy - py) - (by - py) * (cx - px)) * inverse
                if w0 < 0.0:
                    continue
                w1 = ((cx - px) * (ay - py) - (cy - py) * (ax - px)) * inverse
                if w1 < 0.0:
                    continue
                w2 = ((ax - px) * (by - py) - (ay - py) * (bx - px)) * inverse
                if w2 < 0.0:
                    continue
                covered[row + x] = 1
    return sum(covered)


def check_packing_density(obj, item):
    """Доля текстуры, занятая шеллами канала, не ниже нормы проекта."""
    minimum = item.float_param_1 if item.float_param_1 > 0 else 0.7
    picked = layer_by_index(obj, item.int_param_2 or 1)

    issues = []
    for layer in ([picked] if picked is not None else []):
        islands = islands_of(obj, layer, 1e-4)
        tiles = sorted({island.tile for island in islands if island.in_grid})
        if not tiles:
            continue
        triangles = _triangles(obj, layer.name)
        if not triangles:
            continue

        cells = GRID * GRID
        per_tile = {}
        covered = 0
        for number in tiles:
            u_tile = (number - 1001) % 10
            v_tile = (number - 1001) // 10
            filled = _cover_tile(triangles, u_tile, v_tile, GRID)
            per_tile[number] = round(filled / cells, 4)
            covered += filled

        density = covered / float(cells * len(tiles))
        if density >= minimum:
            continue
        issues.append({
            "message": ("UV set %s is packed at %.1f%% across %d tile(s), "
                        "minimum is %.0f%%"
                        % (layer.name, density * 100.0, len(tiles), minimum * 100.0)),
            "element_ref": "uv:%s" % layer.name,
            "values": {"uv": layer.name, "density": round(density, 4),
                       "min": round(minimum, 4), "tiles": tiles,
                       "per_tile": [[number, per_tile[number]] for number in tiles]},
        })
    return issues


def packing_density(obj, number=1):
    """Плотность паковки канала для строки разбора. None - считать нечего."""
    layer = layer_by_index(obj, number)
    if layer is None:
        return None, []
    islands = islands_of(obj, layer, 1e-4)
    tiles = sorted({island.tile for island in islands if island.in_grid})
    if not tiles:
        return None, []
    triangles = _triangles(obj, layer.name)
    if not triangles:
        return None, []

    cells = GRID * GRID
    covered = 0
    per_tile = []
    for number in tiles:
        filled = _cover_tile(triangles, (number - 1001) % 10, (number - 1001) // 10, GRID)
        per_tile.append((number, filled / cells))
        covered += filled
    return covered / float(cells * len(tiles)), per_tile
