# -*- coding: utf-8 -*-
"""UDIM: отличить настоящую раскладку по тайлам от шеллов, вынесенных в сторону.

Задача. Канал, которому разрешён UDIM, законно выходит за квадрат 0-1, и
правило «снаружи 0-1 - ошибка» для него умирает. А вынести наложенные шеллы
вправо - самый быстрый способ сделать вид, что наложений нет: снаружи это
выглядит так же, как UDIM. Отличить одно от другого по положению шелла нельзя,
нужны признаки самой РАСКЛАДКИ.

Текстуры в Blender у проекта нет, поэтому спросить её, какие тайлы существуют,
не у кого (`image.source == 'TILED'` - единственный неэвристический признак, и
он недоступен). Остаётся геометрия, и здесь она разделена на то, что можно
доказать, и то, что можно только заподозрить:

  доказуемо            шелл пересекает границу тайла;
                       тайл вне сетки UDIM;
                       раскладка начинается не с 1001;
                       шелл - копия другого, сдвинутая на целое число тайлов.

  подозрение           в тайле занято слишком мало площади.

Поэтому проверок четыре, а не одна: у доказуемого и у подозрения должна быть
разная строгость, и проект включает их по отдельности.

Чего здесь нет намеренно:

  * «наложение после взятия по модулю 1». В настоящем UDIM два тайла - это две
    разные текстуры, и шеллы в них законно занимают одно и то же локальное
    место. Это не признак.
  * плотность текселей. У вынесенного шелла она та же самая: его просто
    подвинули, не масштабируя.
"""

import math
import re

from ..common import *
from .overlapped_uv import _uv_islands_from_faces, _uv_polygon_area

TILE_COLUMNS = 10          # сетка UDIM: 10 тайлов в ряд, 1001..1010, 1011..


def tile_number(u_tile, v_tile):
    return 1001 + u_tile + TILE_COLUMNS * v_tile


def tile_origin(number):
    index = number - 1001
    return index % TILE_COLUMNS, index // TILE_COLUMNS


class Island:
    """Шелл с тем, что о нём нужно знать для разговора про тайлы."""

    __slots__ = ("faces", "area", "umin", "vmin", "umax", "vmax",
                 "u_tile", "v_tile", "straddles")

    def __init__(self, faces, area, bounds, tolerance):
        self.faces = faces
        self.area = area
        self.umin, self.vmin, self.umax, self.vmax = bounds
        # тайл - по вложенному углу, а не по центру: шелл, прижатый к границе,
        # принадлежит тому тайлу, в котором лежит его тело
        self.u_tile = int(math.floor(self.umin + tolerance))
        self.v_tile = int(math.floor(self.vmin + tolerance))
        # прижатый вплотную к границе шелл её не пересекает, поэтому допуск
        # вычитается с обеих сторон
        self.straddles = (
            int(math.floor(self.umin + tolerance)) != int(math.floor(self.umax - tolerance))
            or int(math.floor(self.vmin + tolerance)) != int(math.floor(self.vmax - tolerance))
        )

    @property
    def tile(self):
        return tile_number(self.u_tile, self.v_tile)

    @property
    def width(self):
        return self.umax - self.umin

    @property
    def height(self):
        return self.vmax - self.vmin

    @property
    def in_grid(self):
        return 0 <= self.u_tile < TILE_COLUMNS and self.v_tile >= 0


def layer_by_index(obj, number):
    """Канал по НОМЕРУ, считая с единицы. None - такого нет или он не читается.

    По номеру, а не по имени: как канал назван, проверяет uv_set_names, и
    замеру это безразлично. Привязка к имени делала проверку молчаливо
    бесполезной на ассете, где канал назвали иначе - а именно так выглядит
    свежий импорт, где он ещё «UVMap».
    """
    layers = getattr(obj.data, "uv_layers", None)
    if not layers:
        return None
    index = max(1, int(number or 1)) - 1
    if index >= len(layers):
        return None
    layer = layers[index]
    if getattr(obj.data, "is_editmode", False):
        return layer                # в правке RNA пуст всегда, читаем из bmesh
    if len(layer.data) < len(obj.data.loops):
        return None                 # данные не прочитаны, мерить нечего
    return layer


def _layers(obj, item, default=1):
    """Канал замера списком, чтобы вызывающие не менялись. (каналы, None)."""
    layer = layer_by_index(obj, getattr(item, "int_param_2", 0) or default)
    return ([] if layer is None else [layer]), None


def islands_of(obj, layer, tolerance):
    """Шеллы канала с габаритом, площадью и тайлом. Пустой список - нечего мерить."""
    bm, should_free = _read_bmesh(obj)
    try:
        uv_layer = bm.loops.layers.uv.get(layer.name)
        if uv_layer is None:
            return []
        groups = _uv_islands_from_faces(
            bm, uv_layer, [face.index for face in bm.faces], tolerance)
        faces_by_index = {face.index: face for face in bm.faces}
        out = []
        for group in groups:
            area = 0.0
            umin = vmin = float("inf")
            umax = vmax = float("-inf")
            for face_index in group:
                points = [tuple(loop[uv_layer].uv)
                          for loop in faces_by_index[face_index].loops]
                area += _uv_polygon_area(points)
                for u, v in points:
                    umin, umax = min(umin, u), max(umax, u)
                    vmin, vmax = min(vmin, v), max(vmax, v)
            out.append(Island(group, area, (umin, vmin, umax, vmax), tolerance))
        return out
    finally:
        if should_free:
            bm.free()


def _ref(faces):
    return "f:" + ",".join(str(index) for index in sorted(faces))


def _tiles_used(islands):
    """{номер тайла: [шеллы]} - только шеллы, целиком лежащие в своём тайле."""
    tiles = {}
    for island in islands:
        if island.straddles or not island.in_grid:
            continue
        tiles.setdefault(island.tile, []).append(island)
    return tiles


# ----------------------------------------------------------- шелл внутри тайла


def check_udim_shell_in_tile(obj, item):
    """Шелл не должен пересекать границу тайла и не должен лежать вне сетки UDIM.

    Сломано в обоих случаях независимо от замысла: шелл на границе разрежется
    между двумя текстурами, а тайла с отрицательным U или V не существует.
    """
    tolerance = item.float_param_1 if item.float_param_1 > 0 else 1e-4
    layers, error = _layers(obj, item)
    if error:
        return [error]

    issues = []
    for layer in layers:
        crossing, outside = [], []
        for island in islands_of(obj, layer, tolerance):
            if island.straddles:
                crossing.append(island)
            elif not island.in_grid:
                outside.append(island)
        if crossing:
            faces = [i for island in crossing for i in island.faces]
            issues.append({
                "message": ("%d UV island(s) cross a tile border on UV set %s"
                            % (len(crossing), layer.name)),
                "element_ref": "uv:%s;%s" % (layer.name, _ref(faces)),
                "values": {"uv": layer.name, "islands": len(crossing),
                           "faces": len(faces), "kind": "border"},
            })
        if outside:
            faces = [i for island in outside for i in island.faces]
            issues.append({
                "message": ("%d UV island(s) sit outside the UDIM grid on UV set %s"
                            % (len(outside), layer.name)),
                "element_ref": "uv:%s;%s" % (layer.name, _ref(faces)),
                "values": {"uv": layer.name, "islands": len(outside),
                           "faces": len(faces), "kind": "grid",
                           "corners": sorted({(i.u_tile, i.v_tile) for i in outside})},
            })
    return issues


# ----------------------------------------------------------- набор тайлов


def check_udim_tile_set(obj, item):
    """Раскладка начинается с 1001, идёт подряд и укладывается в лимит.

    Художник пакует тайлы по порядку. Дыра в нумерации означает, что что-то
    улетело в сторону, а не что набор такой.
    """
    tolerance = 1e-4
    require_contiguous = item.bool_param_1
    limit = max(0, item.int_param_1)
    layers, error = _layers(obj, item)
    if error:
        return [error]

    issues = []
    for layer in layers:
        tiles = sorted(_tiles_used(islands_of(obj, layer, tolerance)))
        if not tiles:
            continue
        if tiles[0] != 1001:
            issues.append({
                "message": ("UV set %s starts at tile %d instead of 1001"
                            % (layer.name, tiles[0])),
                "element_ref": "uv:%s" % layer.name,
                "values": {"uv": layer.name, "kind": "start",
                           "first": tiles[0], "tiles": tiles},
            })
        if require_contiguous:
            missing = [t for t in range(tiles[0], tiles[-1] + 1) if t not in tiles]
            if missing:
                issues.append({
                    "message": ("UV set %s skips tile(s) %s"
                                % (layer.name, ", ".join(map(str, missing)))),
                    "element_ref": "uv:%s" % layer.name,
                    "values": {"uv": layer.name, "kind": "gap",
                               "missing": missing, "tiles": tiles},
                })
        if limit and len(tiles) > limit:
            issues.append({
                "message": ("UV set %s uses %d tiles, maximum allowed is %d"
                            % (layer.name, len(tiles), limit)),
                "element_ref": "uv:%s" % layer.name,
                "values": {"uv": layer.name, "kind": "limit",
                           "count": len(tiles), "max": limit, "tiles": tiles},
            })
    return issues


# ----------------------------------------------------------- заполненность


def check_udim_tile_fill(obj, item):
    """В тайле должно быть занято не меньше заданной доли площади.

    UDIM заводят ради разрешения: лишний тайл - это лишняя текстура целиком.
    Тайл, в котором занято полпроцента, заведён не ради разрешения, а чтобы
    куда-то деть шеллы. Доказать это нельзя - поэтому проверка отдельная, и
    проект сам решает, ошибка это или замечание.

    Судим только раскладку из нескольких тайлов: насколько плотно упакован
    единственный тайл - совсем другой разговор, и не этой проверки.
    """
    minimum = item.float_param_1 if item.float_param_1 > 0 else 0.1
    layers, error = _layers(obj, item)
    if error:
        return [error]

    issues = []
    for layer in layers:
        tiles = _tiles_used(islands_of(obj, layer, 1e-4))
        if len(tiles) < 2:
            continue
        for number in sorted(tiles):
            group = tiles[number]
            filled = sum(island.area for island in group)   # тайл 1x1: площадь = доля
            if filled >= minimum:
                continue
            faces = [i for island in group for i in island.faces]
            issues.append({
                "message": ("Tile %d on UV set %s is %.2f%% full (%d island(s)), "
                            "minimum is %.0f%%"
                            % (number, layer.name, filled * 100.0, len(group),
                               minimum * 100.0)),
                "element_ref": "uv:%s;%s" % (layer.name, _ref(faces)),
                "values": {"uv": layer.name, "tile": number,
                           "fill": round(filled, 5), "min": round(minimum, 5),
                           "islands": len(group), "faces": len(faces)},
            })
    return issues


# ----------------------------------------------------------- сдвинутый дубль


def check_shifted_duplicate(obj, item):
    """Шелл - копия другого, сдвинутая на целое число тайлов.

    Подпись «вынес в сторону»: наложение не разложили, а подвинули на тайл.
    Совпадать должны все четыре величины сразу - число граней, площадь и обе
    стороны габарита, - и смещение между шеллами должно быть целым и ненулевым.
    Случайно так не совпадают.

    Два одинаковых куска, разложенные каждый на своё место, под это не попадают:
    у них смещение не целое. А ровно наложенные друг на друга - попадают к
    `uv_overlap`, здесь смещение нулевое и мы молчим.

    И последнее сито: тайл, скопированный ЦЕЛИКОМ - все шеллы один к одному и
    все с одним и тем же сдвигом, - это не вынесенный шелл, а осознанно
    продублированная раскладка. Странная, но своя. Вынос узнаётся по тому, что
    переехала ЧАСТЬ тайла.
    """
    tolerance = item.float_param_1 if item.float_param_1 > 0 else 1e-4
    layers, error = _layers(obj, item)
    if error:
        return [error]

    digits = max(3, int(round(-math.log10(tolerance))) - 1)
    issues = []
    for layer in layers:
        islands = islands_of(obj, layer, tolerance)
        buckets = {}
        for island in islands:
            key = (len(island.faces), round(island.area, digits),
                   round(island.width, digits), round(island.height, digits))
            buckets.setdefault(key, []).append(island)

        sizes = {number: len(group) for number, group in _tiles_used(islands).items()}
        matched = {}
        for group in buckets.values():
            if len(group) < 2:
                continue
            for first in range(len(group)):
                for second in range(first + 1, len(group)):
                    a, b = group[first], group[second]
                    du, dv = b.umin - a.umin, b.vmin - a.vmin
                    if abs(du - round(du)) > tolerance or abs(dv - round(dv)) > tolerance:
                        continue
                    if round(du) == 0 and round(dv) == 0:
                        continue            # ровный стак - это к uv_overlap
                    key = (a.tile, b.tile, int(round(du)), int(round(dv)))
                    matched.setdefault(key, []).append((a, b))

        pairs, faces = [], []
        for (tile_a, tile_b, _du, _dv), found in matched.items():
            whole = (len(found) == sizes.get(tile_a) == sizes.get(tile_b))
            if whole:
                continue                    # тайл продублирован целиком, не вынос
            for a, b in found:
                pairs.append((tile_a, tile_b))
                faces.extend(a.faces)
                faces.extend(b.faces)
        if pairs:
            issues.append({
                "message": ("%d UV island pair(s) on UV set %s are the same shell "
                            "moved by whole tiles" % (len(pairs), layer.name)),
                "element_ref": "uv:%s;%s" % (layer.name, _ref(set(faces))),
                "values": {"uv": layer.name, "pairs": len(pairs),
                           "faces": len(set(faces)),
                           "tiles": sorted({t for pair in pairs for t in pair})},
            })
    return issues
