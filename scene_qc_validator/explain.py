# -*- coding: utf-8 -*-
"""Реестр находок: русская метка, русский текст с замером и способ починки.

Устроено как `ardena_codes.py` в ARDENA Tools, и намеренно: проверяющий смотрит
отчёты двух инструментов подряд, и находка должна читаться одинаково - короткая
метка, одна строка с замером, под ней строка «чем чинится». Поэтому здесь те же
три таблицы и те же четыре вида починки (AUTO / BUTTON / MANUAL / NOTE).

Почему текст собирается из `values`, а не берётся из сообщения проверки.
Сообщение проверки - машинное («1 UV island(s) overlap another on UV set UV3»):
оно нужно, чтобы сравнивать прогоны, и меняться не должно. Художнику нужен тот
же замер по-русски и с конкретикой: какой канал, сколько граней, какой был
предел. Числа приходят из проверки полями (`values`), и строка собирается здесь -
разбирать обратно английское предложение было бы гаданием.

Правило для текстов: называть вещи, а не рассуждать о них. «Канал UV1: 3026
граней за квадратом 0-1» - да; «развёртка выходит за пределы, что приведёт к
неприятностям на бейке» - нет.
"""

# --- вид починки (те же четыре, что в ARDENA Tools)
AUTO = "auto"       # снимает кнопка «Исправить» в отчёте или Fix в панели
BUTTON = "button"   # отдельная кнопка: правка заметная, сама собой не делается
MANUAL = "manual"   # руками, с короткой подсказкой, что именно сделать
NOTE = "note"       # чинить нечего: это сведение

FIX_LABEL = {AUTO: "авто", BUTTON: "кнопкой", MANUAL: "руками", NOTE: "к сведению"}

# BUTTON - это правка, которую нельзя делать заодно: переименование объектов и
# материалов. Общая кнопка «Исправить автоматически» их не трогает (см.
# `operators/stage_check._auto_check_ids`), у каждой находки своя кнопка.

AUTO_TEXT = "«Исправить» в отчёте или Fix у строки в панели валидатора"

# id проверки -> короткая русская метка. Реестр: панель, отчёт и документация
# называют одно правило одинаково.
CODES = {
    # --- геометрия
    "geo_has_soft_edges":   "все рёбра - hard edges",
    "geo_ngons":            "n-гоны",
    "geo_non_manifold":     "non manifold геометрия",
    "geo_zero_area":        "грани нулевой площади",
    "geo_zero_length":      "рёбра нулевой длины",
    "geo_non_planar":       "неплоские грани",
    "geo_concave_faces":    "вогнутые грани",
    "geo_duplicate_faces":  "задвоенные грани",
    "geo_loose":            "болтающаяся геометрия",
    "geo_flipped_normals":  "вывернутые нормали",
    "obj_extra_data":       "лишние данные на меше",
    "geo_animation_keys":   "анимационные ключи",
    # --- объект
    "tr_unapplied":         "трансформация не применена",
    "tr_world_origin":      "пивот не в нуле сцены",
    "tr_pivot_center":      "пивот не в центре габарита",
    "tr_pivot_bottom":      "пивот не внизу",
    "nm_object_pattern":    "имя объекта не по шаблону",
    "nm_name_characters":   "в имени пробел или кириллица",
    "obj_nanite_closed_geometry": "открытая геометрия для Nanite",
    # --- развёртка
    "uv_missing":           "нет UV-развёртки",
    "uv_set_count":         "лишние UV-каналы",
    "uv_single_tile":       "шеллы за квадратом 0-1",
    "uv_set_names":         "имена UV-каналов не те",
    "uv_overlap":           "шеллы наложены друг на друга",
    "uv_udim_shell_in_tile": "шелл не внутри своего тайла",
    "uv_udim_tile_set":     "набор UDIM-тайлов",
    "uv_udim_tile_fill":    "пустой UDIM-тайл",
    "uv_shifted_duplicate": "шелл сдвинут на тайл",
    "uv_packing_density":   "плотность паковки",
    "uv_texel_density":     "плотность текселя",
    "uv_padding_gap":       "отступ между шеллами",
    "uv_padding":           "паддинг между шеллами",
    "uv_no_hard_edge_on_uv_borders": "шов без hard edge",
    "uv_random_sharp":      "hard edges не по швам",
    "uv_unaligned_edges":   "границы шеллов завалены",
    # --- материал
    "vc_missing":           "нет Vertex Color",
    "vc_id_values":         "Vertex Color ID не по правилам",
    "mat_missing":          "нет материала",
    "mat_material_count":   "слишком много материалов",
    "mat_material_name":    "имя материала не по шаблону",
    # --- коллизии
    "col_missing":          "нет коллизии",
    "col_name":             "имя коллизии не по шаблону",
    "col_convex":           "коллизия не выпуклая",
    "col_material":         "на коллизии не тот материал",
}

# id проверки -> (вид, что сделать). Строка под находкой: лид сразу видит, что
# уйдёт кнопкой, а что возвращать художнику.
FIX = {
    "geo_has_soft_edges":   (AUTO, "снять hard edge со всех рёбер; расставить заново там, где нужны"),
    "geo_ngons":            (AUTO, "триангулировать найденные грани"),
    "geo_non_manifold":     (AUTO, "разрезать «веера» граней и сварить каждый остров по отдельности; "
                                   "после правки посмотреть на меш глазами"),
    "geo_zero_area":        (AUTO, "растворить вырожденную геометрию (Dissolve Degenerate)"),
    "geo_zero_length":      (AUTO, "сварить вершины ближе допуска (Merge by Distance)"),
    "geo_non_planar":       (AUTO, "триангулировать: дальше форма не зависит от того, кто режет"),
    "geo_concave_faces":    (AUTO, "триангулировать вогнутые грани"),
    "geo_duplicate_faces":  (AUTO, "удалить дубликаты, оставив по одной грани"),
    "geo_loose":            (AUTO, "удалить вершины и рёбра без граней"),
    "geo_flipped_normals":  (AUTO, "развернуть грани наружу (Recalculate Outside)"),
    # автофикса нет намеренно: применить модификатор - изменить геометрию,
    # удалить - потерять работу, а шейп-кейс удаляется без возврата
    "obj_extra_data":       (MANUAL, "применить или снять модификаторы, удалить шейп-кейсы и "
                                     "вертекс-группы: статик-мешу они не нужны, а замеры "
                                     "валидатора идут по базовому мешу"),
    "geo_animation_keys":   (AUTO, "очистить анимационные данные объекта, меша и шейп-кейсов"),
    "tr_unapplied":         (AUTO, "применить перечисленное (Apply). Поворот 90° и масштаб 0.01 - "
                                   "это след импорта FBX из Maya"),
    "tr_world_origin":      (AUTO, "перенести пивот в мировой ноль, компенсируя сдвиг геометрией"),
    "tr_pivot_bottom":      (AUTO, "перенести пивот на низ геометрии, компенсируя сдвиг "
                                   "геометрией - на экране ничего не шевельнётся"),
    "tr_pivot_center":      (MANUAL, "Object → Set Origin → Origin to Geometry. Если по проекту пивот "
                                     "стоит иначе (у ARDENA - внизу, Z = 0), выключить проверку в этапе"),
    "nm_name_characters":   (BUTTON, "«Исправить» у этой строки перепишет имя: уберёт пробелы "
                                     "и заменит кириллические буквы на латинские. Буква без "
                                     "латинского двойника остаётся - её менять не на что"),
    "nm_object_pattern":    (BUTTON, "«Исправить» у этой строки знает только студийную схему: "
                                     "переименует в «SM_<имя>» (скелетные - «SK_»). У проекта своя "
                                     "схема - переименовывать руками"),
    "obj_nanite_closed_geometry": (MANUAL, "утопить открытый край внутрь соседней геометрии или закрыть "
                                           "оболочку: это правка формы, автофикса нет"),
    "uv_missing":           (MANUAL, "развернуть меш и добавить нужные каналы"),
    "uv_set_count":         (MANUAL, "удалить лишние каналы (Object Data → UV Maps)"),
    "uv_single_tile":       (MANUAL, "уложить шеллы внутрь 0-1. Если канал уходит за квадрат законно "
                                     "(как UV3 у ARDENA), исключить его в «UV Set Regex» этой проверки"),
    "uv_set_names":         (AUTO, "переименовать каналы по порядку в заданные («Expected Names»)"),
    "uv_overlap":           (MANUAL, "разложить канал заново, без наложений"),
    "uv_udim_shell_in_tile": (MANUAL, "вернуть шелл внутрь одного тайла: на границе он разрежется "
                                      "между двумя текстурами, а тайлов с отрицательным U или V "
                                      "не существует"),
    "uv_udim_tile_set":     (MANUAL, "упаковать тайлы подряд начиная с 1001: дыра в нумерации "
                                     "означает, что шелл улетел в сторону, а не что набор такой"),
    "uv_udim_tile_fill":    (MANUAL, "разложить содержимое пустого тайла по занятым или оставить "
                                     "его осознанно: лишний тайл - это лишняя текстура целиком"),
    "uv_texel_density":     (MANUAL, "привести шеллы к одной плотности - 1024 px/м при карте "
                                     "2048, то есть 1 UV = 2 м. Правило на каждый шелл, а не "
                                     "на среднее по ассету"),
    "uv_packing_density":   (MANUAL, "упаковать плотнее: пустое место в развёртке - это "
                                     "оплаченные и неиспользованные тексели"),
    "uv_shifted_duplicate": (MANUAL, "разложить шелл на своё место, а не отодвигать на тайл: "
                                     "сдвиг прячет наложение от проверки, но текстуру под него "
                                     "всё равно никто не нарисует"),
    # одной строкой и с числом: всё остальное - бейк, Margin, кнопка показа -
    # художник и так знает, а в подсказке это читалось набором слов
    "uv_padding_gap":       (MANUAL, "перепаковать канал с отступом из нормы - 16 для 2048"),
    "uv_padding":           (NOTE, "это предпросмотр отступов, а не проверка: смотреть кнопкой Show Padding"),
    "uv_no_hard_edge_on_uv_borders": (AUTO, "поставить hard edge ровно на границы шеллов, остальные швы не трогая"),
    "uv_random_sharp":      (AUTO, "снять hard edge со всех рёбер, кроме границ шеллов"),
    "uv_unaligned_edges":   (AUTO, "выпрямить границы по горизонтали и вертикали; UV сдвинутся "
                                   "не больше чем на 16 текселей, где нужно сильнее - руками"),
    "vc_missing":           (MANUAL, "залить меш чёрным и назначить ID участкам: в ARDENA это "
                                     "Mesh Display → Apply Color в Maya, значение только в красном"),
    "vc_id_values":         (MANUAL, "выставить ID ровными десятыми в красном канале (0.1 - слой 1, "
                                     "0.2 - слой 2, до 1.0), G и B оставить в нуле. Маска из одного "
                                     "значения ничего не разделяет - слоёв должно быть минимум два"),
    "mat_missing":          (AUTO, "создать материал по правилу проекта и закрыть им пустые слоты"),
    "mat_material_count":   (MANUAL, "свести к разрешённому числу и удалить пустые слоты"),
    "mat_material_name":    (BUTTON, "«Исправить» у этой строки схлопнет дубли «.001» обратно "
                                     "на родителя и переименует по шаблону проекта - если проект "
                                     "его задал. Без шаблона имя не угадать, и материал остаётся "
                                     "как есть: переименовать руками. Общая кнопка «Исправить "
                                     "автоматически» переименованием не занимается"),
    # --- коллизии
    "col_missing":          (MANUAL, "сделать коллизию и назвать «UCX_<имя меша>» или "
                                     "«UCX_<имя меша>_01»"),
    # кнопкой, а не общим автофиксом: переименование - заметная правка, и
    # остальные переименования в этом наборе живут так же
    "col_name":             (BUTTON, "«Исправить» у этой строки переименует коллизии правильно: "
                                     "префикс заглавными, через «_», без блендеровского хвоста "
                                     "«.001». Движок находит коллизию только по имени"),
    "col_convex":           (MANUAL, "собрать оболочку заново выпуклой (Convex Hull): вмятину "
                                     "движок не исправит, персонаж провалится внутрь"),
    "col_material":         (AUTO, "поставить на коллизию материал её меша"),
}


def _n(count, one, few, many):
    """«3 грани», «21 грань», «15 граней»."""
    n10, n100 = count % 10, count % 100
    word = (one if (n10 == 1 and n100 != 11)
            else few if (2 <= n10 <= 4 and not 12 <= n100 <= 14)
            else many)
    return "%d %s" % (count, word)


def _n_plain(value):
    """12345 -> «12 345»: длинные числа глазами не читаются."""
    try:
        return "{:,}".format(int(value)).replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def _g(value):
    """Число без хвоста нулей: 0.001, а не 0.0010000000475."""
    try:
        return ("%g" % float(value))
    except (TypeError, ValueError):
        return str(value)


def _faces(count):
    return _n(count, "грань", "грани", "граней")


def _edges(count):
    return _n(count, "ребро", "ребра", "рёбер")


def _verts(count):
    return _n(count, "вершина", "вершины", "вершин")


def _verb(count, one, many):
    """Глагол под число: «1 грань задвоена», «5 граней задвоены»."""
    n10, n100 = count % 10, count % 100
    return one if (n10 == 1 and n100 != 11) else many


def _uv_list(names):
    if not names:
        return "UV-каналов у меша нет"
    return ("канал " if len(names) == 1 else "каналы ") + ", ".join(names)


def _channel(values):
    """«Канал UV3» - с какого канала начинается текст находки по развёртке."""
    name = values.get("uv")
    return ("Канал %s: " % name) if name else ""


_SOURCES = {"object": "объект", "mesh data": "меш", "shape keys": "шейп-кейсы"}
# ключи приходят из самой проверки (`check_unapplied_transform`), поэтому
# "translation", а не "location"
_PARTS = {"translation": "позиция", "location": "позиция",
          "rotation": "поворот", "scale": "масштаб"}


def _xyz(values, unit=""):
    """«(0.01, 0.01, 0.01)». -0 от округления печатаем как 0."""
    try:
        parts = []
        for value in values:
            text = _g(value)
            parts.append(("0" if text == "-0" else text) + unit)
        return "(%s)" % ", ".join(parts)
    except TypeError:
        return ""


def _t_non_manifold(v):
    kind = v.get("kind")
    if kind == "edges":
        return "%s с тремя и более гранями" % _edges(v.get("edges", 0))
    if kind == "fans":
        return "%s с разорванным веером граней" % _verts(v.get("verts", 0))
    verts = v.get("verts", 0)
    return "%s %s в одной точке и не сварены" % (_verts(verts),
                                                 _verb(verts, "стоит", "стоят"))


def _t_loose(v):
    parts = []
    if v.get("verts"):
        parts.append(_verts(v["verts"]))
    if v.get("edges"):
        parts.append(_edges(v["edges"]))
    return "Вне граней: %s" % " и ".join(parts)


def _t_unapplied(v):
    named = []
    for part in v.get("parts", ()):
        label = _PARTS.get(part, part)
        if part in ("translation", "location"):
            label += " " + _xyz(v.get("location", ()))
        elif part == "rotation":
            label += " " + _xyz(v.get("rotation", ()), "°")
        elif part == "scale":
            label += " " + _xyz(v.get("scale", ()))
        named.append(label)
    return "Не применены: " + ", ".join(named)


def _t_nanite(v):
    shells = v.get("shells", 0)
    count = _n(shells, "открытая оболочка", "открытые оболочки", "открытых оболочек")
    if v.get("kind") == "stranded":
        edges = v.get("edges", 0)
        return ("%s %s ничем: %s по краю %s в пустоту"
                % (count, _verb(shells, "не перекрыта", "не перекрыты"),
                   _edges(edges), _verb(edges, "смотрит", "смотрят")))
    return ("%s %s в соседнюю геометрию не до конца: %s по краю, зазор до %s мм"
            % (count, _verb(shells, "утоплена", "утоплены"),
               _edges(v.get("edges", 0)), _g(v.get("gap_mm", 0))))


def _t_single_tile(v):
    if v.get("error"):
        return "Регулярное выражение «%s» не читается: %s" % (v.get("regex", ""), v["error"])
    if v.get("loops"):
        return ("%sне читается - %s на %s"
                % (_channel(v), _n(v.get("uvs", 0), "UV", "UV", "UV"),
                   _n(v["loops"], "луп", "лупа", "лупов")))
    u, w = v.get("u") or (0, 0), v.get("v") or (0, 0)
    return ("%s%s за квадратом 0-1, U %s..%s, V %s..%s"
            % (_channel(v), _faces(v.get("faces", 0)),
               _g(u[0]), _g(u[1]), _g(w[0]), _g(w[1])))


def _t_set_names(v):
    kind = v.get("kind")
    if kind == "default":
        want = list(v.get("want", ()))
        return ("Блендеровские имена каналов: %s. %s %s"
                % (", ".join(v.get("bad", ())),
                   _verb(len(want), "Ожидается", "Ожидаются"), ", ".join(want)))
    if kind == "extra":
        return ("Канал %d «%s» лишний: проект ждёт %s"
                % (v.get("slot", 0), v.get("uv", ""), ", ".join(v.get("expected", ()))))
    if v.get("mixed"):
        # имя само по себе законное, но из другой схемы - сказать именно это,
        # иначе художник смотрит на «map2» и не понимает, чем оно плохо
        return ("Канал %d назван «%s», ожидается «%s»: схема имён у меша должна "
                "быть одна, а это имя из другой"
                % (v.get("slot", 0), v.get("uv", ""), v.get("want", "")))
    return ("Канал %d назван «%s», ожидается «%s»"
            % (v.get("slot", 0), v.get("uv", ""), v.get("want", "")))


def _t_overlap(v):
    if v.get("error"):
        return "Проверку наложений не удалось выполнить: %s" % v["error"]
    if v.get("regex") is not None:
        return ("Ни один канал не подходит под «%s»; у меша %s"
                % (v["regex"], _uv_list(v.get("uvs", ()))))
    where = " внутри UDIM 1001" if v.get("udim_only") else ""
    islands = v.get("islands") or 0
    if islands == 1:
        return "%s1 остров наложен на другой%s (%s)" % (_channel(v), where,
                                                       _faces(v.get("faces", 0)))
    if islands:
        # без глагола: «21 остров наложены» неверно, «21 остров наложен друг на
        # друга»верно и нелепо. Безличная форма одинаково годится для любого числа
        return ("%sшеллы лежат друг на друге%s: %s, %s"
                % (_channel(v), where,
                   _n(islands, "остров", "острова", "островов"),
                   _faces(v.get("faces", 0))))
    return "%s%s с наложенными UV%s" % (_channel(v), _faces(v.get("faces", 0)), where)


def _per_tile(v):
    """«: 1001 - 90%, 1002 - 34%» - по тайлам, когда их больше одного."""
    rows = v.get("per_tile") or []
    if len(rows) < 2:
        return ""
    return ": " + ", ".join("%d - %.0f%%" % (number, share * 100.0)
                            for number, share in rows)


def _t_udim_shell(v):
    if v.get("kind") == "grid":
        corners = v.get("corners") or []
        where = ", ".join("U %d V %d" % (u, w) for u, w in corners[:4])
        return ("%s%s вне сетки UDIM%s"
                % (_channel(v), _n(v.get("islands", 0), "остров", "острова", "островов"),
                   (": " + where) if where else ""))
    return ("%s%s %s границу тайла (%s)"
            % (_channel(v), _n(v.get("islands", 0), "остров", "острова", "островов"),
               _verb(v.get("islands", 0), "пересекает", "пересекают"),
               _faces(v.get("faces", 0))))


def _t_udim_tiles(v):
    kind = v.get("kind")
    tiles = ", ".join(str(t) for t in v.get("tiles", ()))
    if kind == "start":
        return "%sраскладка начинается с тайла %d, а не с 1001 (занято: %s)" % (
            _channel(v), v.get("first", 0), tiles)
    if kind == "gap":
        missing = v.get("missing", ())
        return ("%sв нумерации пропущен%s %s (занято: %s)"
                % (_channel(v), "" if len(missing) == 1 else "ы",
                   ", ".join(str(t) for t in missing), tiles))
    return "%s%d тайлов при допустимых %d: %s" % (
        _channel(v), v.get("count", 0), v.get("max", 0), tiles)


def _t_vertex_color_ids(v):
    kind = v.get("kind")
    where = "«%s»" % v.get("attr", "")
    if kind == "step":
        return ("В %s значения ID не кратны %s: %s"
                % (where, _g(v.get("step", 0.1)),
                   ", ".join("%g" % value for value in v.get("values", ()))))
    if kind == "gb":
        return ("В %s зелёный или синий не в нуле у %d из %s: ID пишется только в красный"
                % (where, v.get("count", 0),
                   _n(v.get("total", 0), "значения", "значений", "значений")))
    if kind == "range":
        return ("В %s значения выше %g: %s - в таблице проекта слои кончаются на %d"
                % (where, v.get("top", 10) * 0.1,
                   ", ".join("%g" % (n * 0.1) for n in v.get("layers", ())),
                   v.get("top", 10)))
    layers = ", ".join("%g" % (number * 0.1) for number in v.get("layers", ()))
    if kind == "few":
        if not v.get("layers"):
            return ("В %s нет ни одного слоя: меш залит чёрным, маска ничего не разделяет"
                    % where)
        return ("В %s всего %s (%s), нужно не меньше %d: маска из одного значения ничего "
                "не разделяет"
                % (where, _n(v.get("count", 0), "слой", "слоя", "слоёв"), layers,
                   v.get("min", 0)))
    return ("В %s %s (%s) при лимите %d на ассет"
            % (where, _n(v.get("count", 0), "слой", "слоя", "слоёв"), layers, v.get("max", 0)))


def _t_missing_material(v):
    if v.get("faces"):
        return "%s %s в пустой слот" % (_faces(v["faces"]),
                                        _verb(v["faces"], "смотрит", "смотрят"))
    slots = v.get("slots", 0)
    if not slots:
        return "У объекта нет ни одного слота материала"
    return "Все слоты материала пусты (%s)" % _n(slots, "слот", "слота", "слотов")



def _t_name_characters(v):
    """Показать сам символ и его место: иначе имя выглядит правильным."""
    parts = []
    spaces = v.get("spaces") or []
    if spaces:
        parts.append("%s на %s %s"
                     % (_n(len(spaces), "лишний пробел", "лишних пробела",
                           "лишних пробелов"),
                        "позиции" if len(spaces) == 1 else "позициях",
                        ", ".join(str(p) for p in spaces)))
    twins = v.get("twins") or []
    if twins:
        parts.append("кириллица, выглядит как латиница: %s"
                     % ", ".join("«%s» на %s (это «%s»)" % (char, place, latin)
                                 for place, char, latin in twins))
    other = v.get("other") or []
    if other:
        parts.append("не латиница: %s"
                     % ", ".join("«%s» на %s" % (char, place)
                                 for place, char in other))
    tail = (" Правильно: «%s»" % v.get("want")) if v.get("want") else ""
    return ("В имени %s «%s» %s.%s"
            % (v.get("what", "объекта"), v.get("name", ""), "; ".join(parts), tail))


_EXTRA_WORDS = {
    "modifiers": ("модификатор", "модификатора", "модификаторов"),
    "shape_keys": ("шейп-кейс", "шейп-кейса", "шейп-кейсов"),
    "vertex_groups": ("вертекс-группа", "вертекс-группы", "вертекс-групп"),
}


def _t_extra_data(v):
    """Что именно осталось на меше и как оно называется."""
    parts = []
    for kind in ("modifiers", "shape_keys", "vertex_groups"):
        names = v.get(kind) or []
        if not names:
            continue
        parts.append("%s (%s)" % (_n(len(names), *_EXTRA_WORDS[kind]),
                                  ", ".join(names[:4])))
    return "На статик-меше осталось: %s" % "; ".join(parts)


def _t_flipped(v):
    """Два разных повода: шов между гранями и оболочка наизнанку."""
    if v.get("kind") == "inside_out":
        tail = (" (у объекта отрицательный масштаб - в движке он приедет "
                "вывернутым)" if v.get("mirrored") else "")
        shells = v.get("shells", 0)
        head = ("Замкнутая оболочка вывернута наизнанку" if shells == 1
                else "%s вывернуты наизнанку"
                     % _n(shells, "замкнутая оболочка", "замкнутые оболочки",
                          "замкнутых оболочек"))
        return ("%s: нормали смотрят внутрь, %s%s"
                % (head, _faces(v.get("faces", 0)), tail))
    return ("Грани смотрят в разные стороны: %s, где соседние грани развёрнуты "
            "друг против друга (%s)"
            % (_edges(v.get("edges", 0)), _faces(v.get("faces", 0))))


def _t_texel(v):
    """Плотность текселя: сколько шеллов ушло от нормы и насколько.

    Больше px/м - шелл КРУПНЕЕ: на тот же метр модели ложится больше пикселей.
    Обратное прочтение сбивает с толку сильнее, чем помогает число.
    """
    bad, total = v.get("bad", 0), v.get("shells", 0)
    if bad:
        low, high = v.get("low", 0), v.get("high", 0)
        if bad == total:
            head = ("шелл" if total == 1
                    else "все %s" % _n(total, "шелл", "шелла", "шеллов"))
        else:
            head = "%s из %d" % (_n(bad, "шелл", "шелла", "шеллов"), total)
        spread = ("%d px/м" % low if low == high
                  else "разброс %d..%d px/м" % (low, high))
        return ("%s%s не по норме %d px/м: %s (допуск ±%d%%)"
                % (_channel(v), head, v.get("want", 0), spread,
                   v.get("tolerance", 0)))
    scale = v.get("scale", 1) or 1
    times = scale if scale >= 1 else (1.0 / scale)
    return ("%s%d px/м при карте %s, норма %d ±%d%% - развёртка %s нормы в %g раза "
            "(1 UV = %g м, нужно %g)"
            % (_channel(v), v.get("px_m", 0), _n_plain(v.get("size", 0)),
               v.get("want", 0), v.get("tolerance", 0),
               "крупнее" if scale > 1 else "мельче", round(times, 2),
               v.get("m_per_uv", 0), v.get("want_m_per_uv", 0)))


_COLLISION_REASON = {
    "case": "префикс не заглавными",
    "separator": "после префикса нет «_»",
    "duplicate": "блендеровский хвост «.001»",
    # имя переделали целиком: по имени её с мешем уже не связать, опознали по
    # тому, что она лежит на нём
    "stray": "имя не связано с мешем, коллизия опознана по месту в сцене",
}


def _t_collision_name(v):
    """Имя коллизии: что именно не так и каким имя должно стать."""
    names = v.get("names") or []
    wants = v.get("wants") or []
    count = v.get("count", len(names))
    why = ", ".join(_COLLISION_REASON.get(r, r) for r in (v.get("reasons") or []))
    pairs = ", ".join("«%s» → «%s»" % (name, want)
                      for name, want in zip(names, wants)) or         ", ".join("«%s»" % name for name in names)
    head = ("Коллизия названа не по шаблону" if count == 1
            else "%s названы не по шаблону"
                 % _n(count, "коллизия", "коллизии", "коллизий"))
    return "%s (%s): %s" % (head, why or "не то имя", pairs)


def _t_collision_convex(v):
    """Выпуклость: дыра и вмятина - разные беды, и чинят их по-разному."""
    name = v.get("collider", "")
    if v.get("kind") == "open":
        return ("Коллизия «%s» не замкнута: у оболочки открытый край (%s)"
                % (name, _edges(v.get("edges", 0))))
    return ("Коллизия «%s» не выпуклая: вмятина до %g мм (%s)"
            % (name, v.get("dent", 0), _edges(v.get("edges", 0))))


def _t_collision_material(v):
    """Материал коллизии против материала меша.

    Пустой слот - отдельная фраза: «материал: материала нет» читается как
    опечатка, а это самый частый случай из трёх.
    """
    name = v.get("collider", "")
    here = ", ".join(v.get("has") or [])
    want = ", ".join(v.get("want") or [])
    if not here:
        return "На коллизии «%s» нет материала, а на меше %s" % (name, want)
    if not want:
        return "На меше нет материала, а на коллизии «%s» стоит %s" % (name, here)
    return "На коллизии «%s» материал %s, а на меше %s" % (name, here, want)


TEXT = {
    "geo_has_soft_edges":  lambda v: "Все рёбра помечены hard edge: %s, мягких нет"
                                     % _edges(v.get("sharp", 0)),
    "geo_ngons":           lambda v: "%s с пятью и более вершинами" % _faces(v.get("faces", 0)),
    "geo_non_manifold":    _t_non_manifold,
    "geo_zero_area":       lambda v: "%s площадью меньше %s" % (_faces(v.get("faces", 0)),
                                                                _g(v.get("threshold", 0))),
    "geo_zero_length":     lambda v: "%s короче %s" % (_edges(v.get("edges", 0)),
                                                       _g(v.get("threshold", 0))),
    "geo_non_planar":      lambda v: "%s с вершинами не в одной плоскости (допуск %s)"
                                     % (_faces(v.get("faces", 0)), _g(v.get("tolerance", 0))),
    "geo_concave_faces":   lambda v: "%s с вогнутым углом" % _faces(v.get("faces", 0)),
    "geo_duplicate_faces": lambda v: "%s %s: дубль на тех же вершинах"
                                     % (_faces(v.get("faces", 0)),
                                        _verb(v.get("faces", 0), "задвоена", "задвоены")),
    "geo_flipped_normals": _t_flipped,
    "obj_extra_data":      _t_extra_data,
    "geo_loose":           _t_loose,
    "geo_animation_keys":  lambda v: "Анимационные данные на: %s"
                                     % ", ".join(_SOURCES.get(s, s) for s in v.get("sources", ())),
    "tr_unapplied":        _t_unapplied,
    "tr_world_origin":     lambda v: "Пивот в %s, это %s от нуля сцены (допуск %s)"
                                     % (_xyz(v.get("xyz", ())), _g(v.get("offset", 0)),
                                        _g(v.get("tolerance", 0))),
    "tr_pivot_center":     lambda v: "Пивот смещён от центра габарита на %s" % _g(v.get("offset", 0)),
    "tr_pivot_bottom":     lambda v: ("Низ меша на %g см %s пивота, а пивот должен быть внизу "
                                      "(допуск %g см)"
                                      % (abs(v.get("offset_cm", 0)),
                                         "выше" if v.get("above") else "ниже",
                                         v.get("tolerance_cm", 0.1))),
    "nm_name_characters":  _t_name_characters,
    "nm_object_pattern":   lambda v: "Имя «%s» не подходит под шаблон «%s»"
                                     % (v.get("name", ""), v.get("pattern", "")),
    "obj_nanite_closed_geometry": _t_nanite,
    "uv_missing":          lambda v: "У меша нет ни одного UV-канала",
    "uv_set_count":        lambda v: "%s при %s: лишние - %s"
                                     % (_n(v.get("count", 0), "канал", "канала", "каналов"),
                                        _n(v.get("max", 0), "допустимом", "допустимых",
                                           "допустимых"),
                                        ", ".join(v.get("extra", ())) or "?"),
    "uv_padding_gap":      lambda v: "%sпаддинг похож на %g px при карте %s, норма %g-%g "
                                     "(самое узкое %g px, замерено по %s)"
                                     % (_channel(v), v.get("padding", 0),
                                        _n_plain(v.get("size", 0)),
                                        v.get("min", 0), v.get("max", 0),
                                        v.get("tightest", 0),
                                        _n(v.get("shells", 0), "шеллу", "шеллам",
                                           "шеллам")),
    "uv_single_tile":      _t_single_tile,
    "uv_udim_shell_in_tile": _t_udim_shell,
    "uv_udim_tile_set":    _t_udim_tiles,
    "uv_udim_tile_fill":   lambda v: "%sв тайле %d занято %.2f%% площади при норме %.0f%% "
                                     "(%s, %s)"
                                     % (_channel(v), v.get("tile", 0),
                                        (v.get("fill", 0) or 0) * 100.0,
                                        (v.get("min", 0) or 0) * 100.0,
                                        _n(v.get("islands", 0), "остров", "острова", "островов"),
                                        _faces(v.get("faces", 0))),
    "uv_texel_density":    _t_texel,
    "uv_packing_density":  lambda v: "%sупакован на %.1f%% при норме %.0f%% (%s%s)"
                                     % (_channel(v), (v.get("density", 0) or 0) * 100.0,
                                        (v.get("min", 0) or 0) * 100.0,
                                        _n(len(v.get("tiles", ())), "тайл", "тайла", "тайлов"),
                                        _per_tile(v)),
    "uv_shifted_duplicate": lambda v: "%s%s - один и тот же шелл, сдвинутый на целые тайлы "
                                      "(затронуты тайлы %s, %s)"
                                      % (_channel(v),
                                         _n(v.get("pairs", 0), "пара шеллов", "пары шеллов",
                                            "пар шеллов"),
                                         ", ".join(str(t) for t in v.get("tiles", ())),
                                         _faces(v.get("faces", 0))),
    "uv_set_names":        _t_set_names,
    "uv_overlap":          _t_overlap,
    "uv_no_hard_edge_on_uv_borders":
        lambda v: "%s на границах шеллов %s hard edge (%s)"
                  % (_edges(v.get("edges", 0)),
                     _verb(v.get("edges", 0), "не помечено", "не помечены"),
                     _uv_list(v.get("uvs", ()))),
    "uv_random_sharp":     lambda v: "%s %s hard edge вне границ шеллов (%s)"
                                     % (_edges(v.get("edges", 0)),
                                        _verb(v.get("edges", 0), "помечено", "помечены"),
                                        _uv_list(v.get("uvs", ()))),
    "uv_unaligned_edges":  lambda v: "%sграницы прямоугольных шеллов завалены: %s, "
                                     "до %s° от горизонтали и вертикали (проверено %s)"
                                     % (_channel(v), _edges(v.get("edges", 0)),
                                        _g(v.get("tilt", 0)),
                                        _n(v.get("islands", 0), "шелл", "шелла",
                                           "шеллов")),
    "col_missing":         lambda v: "У меша нет коллизии: нужен объект «UCX_%s» или «UCX_%s_01»"
                                     % (v.get("mesh", ""), v.get("mesh", "")),
    "col_name":            _t_collision_name,
    "col_convex":          _t_collision_convex,
    "col_material":        _t_collision_material,
    "vc_missing":          lambda v: ("Атрибута вершинного цвета «%s» на меше нет"
                                      % v["wanted"]) if v.get("wanted")
                                     else ("У меша нет вершинного цвета, а в нём лежит "
                                           "маска слоёв"),
    "vc_id_values":        _t_vertex_color_ids,
    "mat_missing":         _t_missing_material,
    "mat_material_count":  lambda v: "%s при %s: %s"
                                     % (_n(v.get("count", 0), "материал", "материала",
                                           "материалов"),
                                        _n(v.get("max", 0), "допустимом", "допустимых",
                                           "допустимых"),
                                        ", ".join(v.get("names", ()))),
    "mat_material_name":   lambda v: "Имена не по шаблону: %s. Ожидается %s"
                                     % (", ".join(v.get("names", ())),
                                        ", ".join("«%s»" % a for a in v.get("allowed", ())) or "?"),
}


def label(check_id, fallback=""):
    """Короткая русская метка проверки."""
    return CODES.get(check_id) or fallback or check_id


def text(check_id, values, fallback=""):
    """Находка по-русски, с замером. Нет замера или собрать не вышло - машинный текст.

    Падать здесь нельзя: отчёт пишется после долгой проверки, и ошибка в одной
    строке не должна стоить художнику всей страницы.
    """
    builder = TEXT.get(check_id)
    if builder is None or not isinstance(values, dict):
        return fallback      # в том числе values is None: замера не было
    try:
        built = builder(values)
    except Exception:
        return fallback
    return built or fallback


def fix_hint(check_id, values=None, can_fix=None):
    """(вид, что сделать). can_fix - есть ли у этой находки рабочая кнопка.

    Вид берётся из таблицы, и только понижается: проверку могли включить в этапе
    без фикса, или фикс отвязали (так сделано у наложений UV). Обещать «авто»
    там, где кнопки нет, хуже, чем промолчать.

    Обратно - не повышаем. Если у проверки появился фикс, а строка в таблице
    осталась прежней, повышение дало бы самопротиворечивую строку: ярлык «авто»
    и текст «автофикса нет намеренно». Расхождение ловит `inconsistent()`.
    """
    kind, how = FIX.get(check_id, (MANUAL, ""))
    if can_fix is False and kind in (AUTO, BUTTON):
        kind = MANUAL
    return kind, how


def missing(check_ids):
    """Проверки без метки - страховка от опечатки в id при добавлении новой."""
    return sorted(check_id for check_id in check_ids if check_id not in CODES)


def inconsistent(definitions):
    """Расхождения реестра с определениями проверок, строками.

    Зовётся при регистрации аддона и печатает найденное в консоль: таблицы здесь
    сведены руками, и забытая строка проявилась бы в отчёте у художника - то
    находкой без русского текста, то обещанием кнопки, которой нет.
    """
    out = []
    for check_id, definition in definitions.items():
        if check_id not in CODES:
            out.append("%s: нет русской метки в CODES" % check_id)
        if check_id not in FIX:
            out.append("%s: нет строки в FIX" % check_id)
            continue
        kind = FIX[check_id][0]
        can_fix = bool(definition.get("can_fix"))
        if can_fix and kind in (MANUAL, NOTE):
            out.append("%s: фикс есть, а в FIX записано «%s»" % (check_id, FIX_LABEL[kind]))
        if not can_fix and kind in (AUTO, BUTTON):
            out.append("%s: в FIX обещано «%s», а фикса нет" % (check_id, FIX_LABEL[kind]))
    for check_id in CODES:
        if check_id not in definitions:
            out.append("%s: есть в CODES, но такой проверки нет" % check_id)
    return out


def describe(check_id):
    """Совместимость со старым отчётом: (метка, «», как чинить, «»)."""
    return CODES.get(check_id, ""), "", FIX.get(check_id, (MANUAL, ""))[1], ""
