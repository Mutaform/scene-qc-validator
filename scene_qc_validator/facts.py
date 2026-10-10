# -*- coding: utf-8 -*-
"""Разбор объекта по строкам: значение, состояние, норма.

Устроено как `_rows_mesh` в ARDENA Tools. Находки говорят, что сломано; этот
разбор говорит, что вообще измеряли - и чем норма отличается от замера. Без него
чистый объект в отчёте выглядит пустой карточкой, и по странице не понять,
проверяли его или забыли.

Строка - `(подпись, значение, состояние, норма, краткое, действие)`. «Действие» -
это кнопка у строки: `(подпись кнопки, имя действия)`, которое отчёт умеет
выполнить в Blender. Пока такая одна - показать маску вершинного цвета во
вьюпорте: число «ID 0.1, 0.2, 0.3» говорит, что слои есть, но не говорит, что
они назначены тем кускам, которым надо, - а это видно только глазами. «Краткое» нужно
сводной таблице, где на колонку есть полтора сантиметра: «не применена» вместо
«позиция (0, 0, 5), поворот (90, 0, 0), масштаб (0.01, 0.01, 0.01)».
Состояния:
  OK   зелёное с галочкой - по правилам этапа;
  WARN жёлтое с «!»       - в допуске, но стоит взглянуть;
  BAD  красное с крестом  - против правил, на это есть находка;
  INFO серое              - справочное по природе (число треугольников);
  DIM  серое с пометкой «правила нет» - проверка в этом этапе выключена.

Состояние берётся из находок и из списка включённых проверок, а не считается
заново: пороги живут в параметрах проверок, и вторая копия тех же чисел
разъехалась бы с первой в первый же месяц. Поэтому здесь нет ни одного своего
порога - только замер и подпись к нему.
"""

import math
import re

from . import explain

OK = "ok"
WARN = "warn"
BAD = "bad"
INFO = "info"
DIM = None


def _n(value):
    """12345 -> «12 345»: длинные числа глазами не читаются."""
    try:
        return "{:,}".format(int(value)).replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


class _Lookup:
    """Состояние строки по проверке: есть находка - её цвет, нет - OK.

    Выключенную в этапе проверку помечаем DIM: серое без пояснения читается как
    «забыли посмотреть», а это «правила на это в этом этапе нет».
    """

    def __init__(self, settings, object_name):
        self.items = {c.check_id: c for c in settings.checks if c.enabled}
        self.findings = {}
        for result in settings.results:
            if result.object_name != object_name or result.muted:
                continue
            state = BAD if result.severity == 'FAIL' else WARN
            # у одного объекта может быть несколько находок одной проверки -
            # строка показывает худшее
            if self.findings.get(result.check_id) != BAD:
                self.findings[result.check_id] = state

    def __call__(self, *check_ids):
        """Состояние строки, которую судят эти проверки."""
        watched = [c for c in check_ids if c in self.items]
        if not watched:
            return DIM
        for check_id in watched:
            if self.findings.get(check_id) == BAD:
                return BAD
        for check_id in watched:
            if self.findings.get(check_id) == WARN:
                return WARN
        return OK

    def item(self, check_id):
        return self.items.get(check_id)

    def param(self, check_id, name, default=None):
        item = self.items.get(check_id)
        if item is None:
            return default
        value = getattr(item, name, default)
        return default if value in ("", None) else value


def _verdict(state_value, bad, good):
    """«есть» / «нет» - но только если это проверяли.

    У выключенной в этапе проверки состояние DIM, и в колонке нормы стоит
    «правила нет». А в колонке значения при этом стояло бодрое «нет» или «по
    осям» - утверждение, которого никто не делал: строка «Границы шеллов | по
    осям | правила нет» читается как «посмотрели и всё хорошо». Не посмотрели.

    Замечание - тоже находка. Раньше «есть» писалось только на ошибке, и
    проверка, понижённая до замечания, давала строку «Шеллы в 0-1 ✓внутри» при
    находке «UV1: шеллы за квадратом, 4 597 граней» - прямая ложь (денис,
    2026-10-10). Что нашли, говорит значение; насколько это страшно - цвет.
    """
    if state_value == DIM:
        return "—"
    return bad if state_value in (BAD, WARN) else good


def _mesh_counts(mesh):
    """Треугольники считаем по граням: calc_loop_triangles перестраивает кэш на
    каждом объекте, а здесь нужна только цифра для глаз."""
    faces = len(mesh.polygons)
    tris = sum(max(len(p.vertices) - 2, 0) for p in mesh.polygons)
    return faces, tris


def _hard_edges(mesh):
    return sum(1 for e in mesh.edges if e.use_edge_sharp)


def _size_cm(obj):
    return " × ".join("%g" % round(v * 100.0, 1) for v in obj.dimensions)


def _xyz(values):
    return "(%s)" % ", ".join(("0" if ("%g" % round(v, 4)) == "-0" else "%g" % round(v, 4))
                              for v in values)


def _transform_text(obj):
    parts = []
    if obj.location.length > 1e-4:
        parts.append("позиция " + _xyz(obj.location))
    if obj.rotation_euler.to_quaternion().angle > 1e-4:
        parts.append("поворот " + _xyz([math.degrees(a) for a in obj.rotation_euler]))
    if any(abs(v - 1.0) > 1e-4 for v in obj.scale):
        parts.append("масштаб " + _xyz(obj.scale))
    return ", ".join(parts) or "применена"


def _percent(value):
    try:
        return "%.0f%%" % (float(value) * 100.0)
    except (TypeError, ValueError):
        return "—"


def _section(title):
    """Заголовок раздела внутри разбора.

    Подпись у такой строки пустая, во втором поле - название раздела: по
    пустой подписи отчёт её и узнаёт. Разделы те же, что в коде ниже были
    комментариями, и тот же порядок: объект, геометрия, развёртка, материал,
    коллизии. Двадцать с лишним строк подряд читать глазами невозможно
    (денис, 2026-10-10).
    """
    return (None, title, None, "", "", None)


def _uv_number(obj, pattern):
    """Номер канала, который судит проверка с регэкспом, или 0 - если любой.

    Нужен порядку строк: раздел «Развёртка» идёт по каналам подряд, и строке
    надо знать, к какому она относится.
    """
    layers = getattr(getattr(obj, "data", None), "uv_layers", None) or ()
    text = (pattern or "").strip()
    if not text or text in (".+", ".*", "^.+$", "^.*$"):
        return 0
    try:
        rule = re.compile(text)
    except re.error:
        return 0
    for index, layer in enumerate(layers, start=1):
        if rule.match(layer.name):
            return index
    return 0


def _uv_matching(obj, pattern, fallback=""):
    """Имена каналов меша, подходящих под регэксп проверки.

    Нужно подписи строки: «UV overlap ✓нет» на меше с тремя каналами читается
    как «наложений нет нигде», а проверка смотрела один канал - на остальных
    стакинг может быть законным и быть (денис, 2026-10-10). Берём настоящие
    имена слоёв, а не то, что написано в регэкспе: канал может называться map3.
    """
    layers = getattr(getattr(obj, "data", None), "uv_layers", None) or ()
    text = (pattern or "").strip()
    if not text or text in (".+", ".*", "^.+$", "^.*$"):
        return fallback
    try:
        rule = re.compile(text)
    except re.error:
        return fallback
    names = [layer.name for layer in layers if rule.match(layer.name)]
    return ", ".join(names) if names else fallback


def _uv_label(obj, number):
    """Имя канала по его номеру: «UV2», «map2» - как он назван у этого меша.

    В разборе есть строки, которые меряют ОДИН канал: паддинг, плотность
    паковки, тайлы UDIM. Без имени канала «57.4%» непонятно к чему относится -
    у меша их три (денис, 2026-10-10). Берём настоящее имя слоя, а не «UV%d»:
    у MET канал законно может называться map2.
    """
    layers = getattr(getattr(obj, "data", None), "uv_layers", None)
    index = max(0, (number or 1) - 1)
    if layers and index < len(layers):
        return layers[index].name
    return "UV%d" % (index + 1)


def _packing_density(obj, number=1):
    """Плотность паковки канала. Считает растеризацией, поэтому через try:
    разбор не должен падать из-за строки, которую можно и не показать."""
    try:
        from .checks.mapping.packing_density import packing_density
        return packing_density(obj, number)
    except Exception as error:                      # noqa: BLE001
        print("[Scene QC Validator] плотность паковки %s: %s" % (obj.name, error))
        return None, []


def _padding_gap(obj, number, size):
    """(паддинг в пикселях, причина). Значение None - мерить не получилось.

    Считает замером, а не по настройкам: строка разбора должна показывать то,
    что в меше, иначе она врёт теми же числами, что стоят в параметрах. А если
    замерить не вышло, обязана сказать почему: «не измерен» без причины
    читается как недоработка инструмента.
    """
    try:
        from .checks.mapping.padding_gap import measure_gap
        from .checks.mapping.udim import layer_by_index
        layer = layer_by_index(obj, number)
        if layer is None:
            total = len(getattr(obj.data, "uv_layers", ()))
            return None, ("не измерен: UV-канала №%d нет (каналов %d)"
                          % (number, total))
        found = measure_gap(obj, layer, floor=1.0 / max(size, 1))
    except Exception as error:                      # noqa: BLE001
        print("[Scene QC Validator] отступ %s: %s" % (obj.name, error))
        return None, "не измерен: ошибка расчёта, см. консоль"
    if found is None:
        return None, ("не измерен: в «%s» нечего сравнивать - соседних шеллов нет"
                      % layer.name)
    return found[0] * size, ""          # found = (медиана, минимум, шеллов, ...)


def _udim_tiles(obj, number=1):
    """Номера тайлов, занятых каналом. Пусто - канала нет или он весь в 1001.

    Считаем по углу грани, а не по острову: строке разбора нужен сам факт
    «канал занимает три тайла», а разбираться, законно это или нет, - дело
    проверок uv_udim_*. Читаем из bmesh, иначе в режиме правки строка молча
    исчезает (почему - в checks/common._read_bmesh).
    """
    seen = set()
    try:
        from .checks.common import _read_bmesh
        from .checks.mapping.udim import layer_by_index
        layer = layer_by_index(obj, number)
        if layer is None:
            return []
        bm, should_free = _read_bmesh(obj)
        try:
            uv_layer = bm.loops.layers.uv.get(layer.name)
            if uv_layer is None:
                return []
            for face in bm.faces:
                for loop in face.loops:
                    u, v = loop[uv_layer].uv
                    u_tile, v_tile = int(math.floor(u)), int(math.floor(v))
                    if 0 <= u_tile < 10 and v_tile >= 0:
                        seen.add(1001 + u_tile + 10 * v_tile)
                    else:
                        seen.add(-1)      # вне сетки - покажем явно
        finally:
            if should_free:
                bm.free()
    except Exception as error:                      # noqa: BLE001
        print("[Scene QC Validator] тайлы %s: %s" % (obj.name, error))
        return []
    if seen <= {1001}:
        return []
    return sorted(seen)


def _collisions_text(obj, state):
    """Что нашлось по имени: «2: UCX_..._001, UCX_..._002».

    Имена показываем, а не только число: по ним сразу видно и опечатку, и
    блендеровский хвост «.001», из-за которого в движке это уже не коллизия.
    """
    item = (state.item("col_missing") or state.item("col_name")
            or state.item("col_convex") or state.item("col_material"))
    if item is None:
        return "—"                  # правила нет - и искать незачем
    try:
        from .checks.objects.collision import colliders_of
        mine, _wrong = colliders_of(obj, item)
    except Exception as error:                      # noqa: BLE001
        print("[Scene QC Validator] коллизии %s: %s" % (obj.name, error))
        return "—"
    if not mine:
        return "нет"
    names = [o.name for o in mine[:4]]
    if len(mine) > len(names):
        names.append("…")
    return "%d: %s" % (len(mine), ", ".join(names))


def _bottom_text(obj):
    """«+4.2 см» - насколько низ геометрии отстоит от пивота."""
    try:
        from .checks.objects.pivot_bottom import bottom_offset
        offset = bottom_offset(obj)
    except Exception as error:                      # noqa: BLE001
        print("[Scene QC Validator] низ %s: %s" % (obj.name, error))
        return "—"
    if offset is None:
        return "—"
    return "%+g см" % round(offset * 100.0, 2)


def _texel_text(obj, number, map_px, per_tile=False):
    """«1024 px/м» или «1001 - 1041, 1002 - 1040»: плотность канала для разбора.

    В px/м, а не в px/см (денис, 2026-10-10): в этих же единицах написана норма
    в ТЗ («1024 px/м»), в этих же её спрашивает чекер движка, и в этих же о ней
    говорит находка. Три единицы на одну величину на одной странице - лишний
    повод ошибиться.
    """
    try:
        from .checks.mapping.texel_density import px_per_cm
        value, collapsed = px_per_cm(obj, number, map_px, per_tile=per_tile)
    except Exception as error:                      # noqa: BLE001
        print("[Scene QC Validator] плотность текселя %s: %s" % (obj.name, error))
        return "—"
    if per_tile:
        if not value:
            return "—"
        if len(value) == 1:
            text = "%s px/м" % _n(round(list(value.values())[0] * 100))
        else:
            text = ", ".join(
                "%s - %s" % (tile if tile > 0 else "вне сетки", _n(round(density * 100)))
                for tile, density in sorted(value.items())) + " px/м"
    else:
        if value is None:
            return "—"
        text = "%s px/м" % _n(round(value * 100))
    text += " при карте %s" % _n(map_px)
    if collapsed > 0.01:
        text += " (схлопнуто %.0f%% площади)" % (collapsed * 100.0)
    return text


def _uv_names_norm(raw):
    """«UV1,UV2,UV3|map1,map2,map3» -> «UV1, UV2, UV3 или map1, map2, map3».

    Чтобы колонка нормы читалась требованием, а не настройкой. Вертикальная
    черта разделяет целые схемы: меш называется по одной из них, но по одной.
    """
    schemes = []
    for scheme in str(raw).split("|"):
        names = [name.strip() for name in scheme.split(",") if name.strip()]
        if names:
            schemes.append(", ".join(names))
    # только первая схема: вторая - то же самое другими словами, и в норме от
    # неё больше шума, чем пользы (денис, 2026-10-11). Найдётся канал, названный
    # по второй схеме, - проверка его примет и промолчит
    return schemes[0] if schemes else str(raw)


def _channels(pattern, fallback="во всех каналах", join=" и "):
    """Имя канала словами. Разбор один на всех - он в `explain.channels`."""
    return explain.channels(pattern, fallback, join)


def _uv_text(mesh):
    names = [uv.name for uv in mesh.uv_layers]
    if not names:
        return "нет"
    return "%d: %s" % (len(names), ", ".join(names))


def _materials_text(obj):
    if not obj.material_slots:
        return "нет слотов"
    names = [s.material.name if s.material else "пусто" for s in obj.material_slots]
    return "%d: %s" % (len(names), ", ".join(names))


def _modifiers_text(obj):
    names = [m.name for m in obj.modifiers]
    return ", ".join(names) if names else "нет"


def _vertex_groups_text(obj):
    names = [g.name for g in obj.vertex_groups]
    if not names:
        return "нет"
    return "%d: %s" % (len(names), ", ".join(names[:4]))


def _shape_keys_text(obj):
    keys = getattr(obj.data, "shape_keys", None)
    if keys is None or not keys.key_blocks:
        return "нет"
    return "%d" % len(keys.key_blocks)


def _colors_text(mesh):
    names = [layer.name for layer in getattr(mesh, "color_attributes", ())]
    return ", ".join(names) if names else "нет"


def _vertex_color_text(obj, mesh):
    """«UV1Color: ID 0.1, 0.3, 0.5» - какие слои маски реально лежат в меше."""
    if not getattr(mesh, "color_attributes", None):
        return "нет"
    try:
        from .checks.material.vertex_color import layer_summary
        name, layers = layer_summary(obj)
    except Exception as error:                      # noqa: BLE001
        print("[Scene QC Validator] vertex color %s: %s" % (obj.name, error))
        return _colors_text(mesh)
    if not name:
        return _colors_text(mesh)
    if not layers:
        return "%s: слоёв нет, залит чёрным" % name
    return "%s: ID %s" % (name, ", ".join("%g" % (number * 0.1) for number in layers))


def _animated(obj):
    if obj.animation_data and (obj.animation_data.action or obj.animation_data.nla_tracks):
        return "есть"
    data = getattr(obj.data, "animation_data", None)
    if data and (data.action or data.nla_tracks):
        return "есть, на меше"
    return "нет"


def rows(obj, settings):
    """Разбор одного объекта. Падать нельзя: отчёт пишется после долгой проверки."""
    try:
        return _rows(obj, settings)
    except Exception as error:                      # noqa: BLE001 - см. докстринг
        print("[Scene QC Validator] разбор %s: %s" % (obj.name, error))
        return []


def _rows(obj, settings):
    mesh = obj.data
    state = _Lookup(settings, obj.name)
    faces, tris = _mesh_counts(mesh)
    edges, hard = len(mesh.edges), _hard_edges(mesh)
    out = []

    # --- объект
    out.append(_section("Объект"))
    out.append(("Имя", obj.name,
                state("nm_object_pattern", "nm_name_characters"),
                "как %s, без пробелов и кириллицы"
                % explain.pattern_norm(
                    state.param("nm_object_pattern", "string_param_1", "—"))))
    moved = _transform_text(obj)
    out.append(("Трансформация", moved, state("tr_unapplied"), "должна быть применена",
                "применена" if moved == "применена" else "не применена"))
    out.append(("Пивот", _xyz(obj.location),
                state("tr_world_origin", "tr_pivot_center", "tr_pivot_bottom"),
                "в нуле сцены, допуск %g"
                % (state.param("tr_world_origin", "float_param_1", 0.001) or 0.001),
                "в нуле" if obj.location.length < 1e-4 else "смещён"))
    if state.item("tr_pivot_bottom") is not None:
        out.append(("Низ относительно пивота", _bottom_text(obj),
                    state("tr_pivot_bottom"),
                    "низ геометрии на пивоте, допуск %g см"
                    % ((state.param("tr_pivot_bottom", "float_param_1", 0.001) or 0.001)
                       * 100.0)))
    out.append(("Габарит, см", _size_cm(obj), INFO))
    out.append(("Анимация", _animated(obj), state("geo_animation_keys"),
                "на статичном ассете ключей быть не должно"))

    # --- геометрия
    out.append(_section("Геометрия"))
    out.append(("Треугольников", _n(tris), INFO))
    out.append(("Граней / вершин", "%s / %s" % (_n(faces), _n(len(mesh.vertices))), INFO))
    out.append(("N-гонов", _n(sum(1 for p in mesh.polygons if len(p.vertices) > 4)),
                state("geo_ngons"), "норма: 0"))
    concave = state("geo_concave_faces")
    out.append(("Вогнутые грани", _verdict(concave, "есть", "нет"), concave,
                "норма: 0 — вогнутая грань режется по-разному в разных пакетах"))
    out.append(("Hard edges", "%s из %s рёбер" % (_n(hard), _n(edges)),
                state("geo_has_soft_edges", "uv_random_sharp",
                      "uv_no_hard_edge_on_uv_borders"),
                "только по границам UV-шеллов"))
    topology = state("geo_non_manifold")
    out.append(("Топология", _verdict(topology, "есть non manifold",
                                      "без non manifold"),
                topology, "норма: без non manifold"))
    normals = state("geo_flipped_normals")
    out.append(("Нормали", _verdict(normals, "вывернуты", "наружу"), normals,
                "все грани наружу, замкнутые оболочки не наизнанку"))
    degenerate = state("geo_zero_area", "geo_zero_length",
                       "geo_duplicate_faces", "geo_loose")
    out.append(("Вырожденная геометрия",
                _verdict(degenerate, "есть", "нет"), degenerate,
                "норма: 0 — нулевые площади и длины, дубли, болтающееся"))
    extra = state("obj_extra_data")
    norm = ("на статик-меше их быть не должно"
            if state.item("obj_extra_data") is not None else "")
    out.append(("Модификаторы", _modifiers_text(obj), extra, norm))
    out.append(("Шейп-кейсы", _shape_keys_text(obj), extra, norm))
    out.append(("Вертекс-группы", _vertex_groups_text(obj), extra, norm))
    if state.item("obj_nanite_closed_geometry") is not None:
        # про геометрию, а не про развёртку - стояла в UV-разделе по привычке
        nanite = state("obj_nanite_closed_geometry")
        out.append(("Геометрия для Nanite",
                    _verdict(nanite, "есть открытый край", "закрыта"), nanite,
                    "открытые оболочки утоплены в соседнюю геометрию"))

    # --- развёртка
    #
    # Строки идут по каналам подряд: сначала всё про первый, потом про второй
    # и так далее (денис, 2026-10-10). До этого они шли в порядке проверок, и
    # на меше с тремя каналами получалось «паддинг UV2, тексель UV1, тексель
    # UV3, паковка UV2» - читать невозможно. Канал 0 - это строки про
    # развёртку вообще, они идут первыми. Сортировка устойчивая, поэтому
    # внутри одного канала порядок остаётся тем, в котором строки собраны.
    out.append(_section("Развёртка"))
    uv_rows = []
    uv_rows.append((0, ("UV-каналов", _uv_text(mesh),
                        state("uv_missing", "uv_set_count", "uv_set_names"),
                        "имена: %s, не больше %s"
                        % (_uv_names_norm(state.param("uv_set_names", "string_param_1", "—")),
                           state.param("uv_set_count", "int_param_1", "—")),
                        _n(len(mesh.uv_layers)) if mesh.uv_layers else "нет")))
    if state.item("uv_unaligned_edges") is not None:
        # строки нет вовсе, если проверки нет в этапе: у ARDENA это правило не
        # используется, и прочерк в разборе только вызывал вопросы (денис)
        uv_rows.append((0, ("Границы шеллов",
                            _verdict(state("uv_unaligned_edges"), "завалены", "ровные"),
                            state("uv_unaligned_edges"),
                            "у шеллов, задуманных прямыми, границы ровно по горизонтали "
                            "и вертикали (допуск %s°)"
                            % state.param("uv_unaligned_edges", "float_param_1", 0.1))))

    tile = state("uv_single_tile")
    tile_pattern = state.param("uv_single_tile", "string_param_1", ".+")
    judged = _channels(tile_pattern, "все каналы", join=" или ")
    tile_where = _uv_matching(obj, tile_pattern)
    uv_rows.append((_uv_number(obj, tile_pattern),
                    ("Шеллы в 0-1" + (" " + tile_where if tile_where else ""),
                     _verdict(tile, "выходят за квадрат", "внутри"), tile,
                     ("канал %s не должен выходить за квадрат 0-1" % judged
                      if judged != "все каналы"
                      else "ни один канал не должен выходить за квадрат 0-1"))))

    overlap = state("uv_overlap")
    overlap_pattern = state.param("uv_overlap", "string_param_1", ".+")
    watched = _channels(overlap_pattern, join=" или ")
    # В подписи - канал, который и правда судили: на остальных каналах стакинг
    # может быть разрешён, и «UV overlap: нет» без имени канала читается шире,
    # чем проверка смотрела.
    overlap_where = _uv_matching(obj, overlap_pattern)
    uv_rows.append((_uv_number(obj, overlap_pattern),
                    ("UV overlap" + (" " + overlap_where if overlap_where else ""),
                     _verdict(overlap, "есть", "нет"), overlap,
                     ("в канале %s наложений быть не должно" % watched
                      if watched != "во всех каналах"
                      else "наложений не должно быть ни в одном канале"))))

    gap = state.item("uv_padding_gap")
    if gap is not None:
        size = gap.int_param_1 or 2048
        channel = gap.int_param_2 or 1
        measured, why = _padding_gap(obj, channel, size)
        uv_rows.append((channel,
                        ("Паддинг при паковке %s" % _uv_label(obj, channel),
                         why if measured is None
                         else "~%g px при карте %s" % (round(measured), _n(size)),
                         # не измерили - значит сказать нечего. Зелёная галочка
                         # здесь читалась бы как «проверено и в порядке»
                         INFO if measured is None else state("uv_padding_gap"),
                         "норма по ТЗ %g-%g px"
                         % (gap.float_param_1 or 8.0, gap.float_param_2 or 16.0))))

    # плотность текселя: первый канал показываем всегда (правила нет, норма
    # зависит от плана ассета), судимый канал - строкой с вердиктом
    size = state.param("uv_texel_density", "int_param_1", 2048) or 2048
    # Размер карты - в самом значении: px/м без него число ни о чём, а норма
    # рядом стоит только у строки с вердиктом и видна только при находке
    # (денис, 2026-10-10).
    uv_rows.append((1, ("Плотность текселя %s" % _uv_label(obj, 1),
                        _texel_text(obj, 1, size, per_tile=True), INFO,
                        "правила нет: норма зависит от плана ассета")))
    judged_item = state.item("uv_texel_density")
    if judged_item is not None:
        number = judged_item.int_param_2 or 3
        value, _collapsed = (None, 0.0)
        try:
            from .checks.mapping.texel_density import px_per_m
            value, _collapsed = px_per_m(obj, number, size)
        except Exception as error:                  # noqa: BLE001
            print("[Scene QC Validator] плотность текселя %s: %s" % (obj.name, error))
        uv_rows.append((number,
                        ("Плотность текселя %s" % _uv_label(obj, number),
                         "—" if value is None
                         else "%d px/м при карте %s" % (round(value), _n(size)),
                         state("uv_texel_density"),
                         "%g px/м при карте %s ±%g%%"
                         % (judged_item.float_param_1 or 1024.0, _n(size),
                            (judged_item.float_param_2 or 0.15) * 100.0))))

    pack_channel = state.param("uv_packing_density", "int_param_2", 1)
    density, _per_tile = _packing_density(obj, pack_channel)
    if density is not None:
        uv_rows.append((pack_channel,
                        ("Плотность паковки %s" % _uv_label(obj, pack_channel),
                         "%.1f%%" % (density * 100.0),
                         state("uv_packing_density"),
                         "не меньше %s"
                         % _percent(state.param("uv_packing_density",
                                                "float_param_1", 0.7)))))

    tile_channel = state.param("uv_udim_shell_in_tile", "int_param_2", 1)
    tiles = _udim_tiles(obj, tile_channel)
    # Норма - только из включённых проверок. У MET набор тайлов квадратом
    # 2x2 / 3x3 / 4x4, поэтому «подряд с 1001» и «каждый заполнен» там
    # выключены, и писать их значило бы обещать правило, по которому никто не
    # судит (денис, 2026-10-10).
    udim_norm = ", ".join(
        part for part, check in (
            ("шелл целиком в своём тайле", "uv_udim_shell_in_tile"),
            ("подряд с 1001", "uv_udim_tile_set"),
            ("каждый заполнен", "uv_udim_tile_fill"),
            ("без копий со сдвигом на тайл", "uv_shifted_duplicate"),
        ) if state(check) != DIM)
    udim_state = state("uv_udim_shell_in_tile", "uv_udim_tile_set",
                       "uv_udim_tile_fill", "uv_shifted_duplicate")
    if tiles:
        uv_rows.append((tile_channel,
                        ("UDIM-тайлы %s" % _uv_label(obj, tile_channel),
                         ", ".join(str(t) for t in tiles), udim_state,
                         udim_norm, str(len(tiles)))))
    elif state.item("uv_udim_shell_in_tile") is not None:
        # тайл один - строку всё равно показываем: иначе четыре UDIM-проверки
        # судят ассет молча, и в разборе их не видно
        uv_rows.append((tile_channel,
                        ("UDIM-тайлы %s" % _uv_label(obj, tile_channel),
                         "один, 1001", udim_state, udim_norm, "1")))

    out.extend(row for _channel, row in sorted(uv_rows, key=lambda pair: pair[0]))

    # --- материал
    out.append(_section("Материал"))
    has_colors = bool(getattr(mesh, "color_attributes", None))
    out.append(("Vertex Color", _vertex_color_text(obj, mesh),
                state("vc_missing", "vc_id_values"),
                "ID десятыми в красном, G и B в нуле, слоёв не меньше %s"
                % state.param("vc_id_values", "int_param_1", 2),
                None,
                ("Посмотреть", "show_vc") if has_colors else None))
    # «не больше N» пишем, только когда лимит и правда задан: у проекта, где
    # материалов на меше может быть сколько нужно, эта проверка выключена, и
    # строка «не больше —» была бы требованием, которого нет (денис, 2026-10-10)
    limit = state.param("mat_material_count", "int_param_1", None)
    name_norm = "имя как %s" % explain.pattern_norm(
        state.param("mat_material_name", "string_param_1", "—"))
    out.append(("Материалы", _materials_text(obj),
                state("mat_missing", "mat_material_count", "mat_material_name"),
                ("не больше %s, %s" % (limit, name_norm)
                 if state("mat_material_count") != DIM and limit else name_norm),
                _n(len(obj.material_slots)) if obj.material_slots else "нет"))

    # --- коллизии
    out.append(_section("Коллизии"))
    out.append(("Коллизии", _collisions_text(obj, state),
                state("col_missing", "col_name", "col_convex", "col_material"),
                "UCX_<имя меша> или UCX_<имя меша>_NN, выпуклые"
                + ("" if state("col_material") == DIM
                   else ", с материалом меша"
                   if state.param("col_material", "bool_param_1", True)
                   else ", без материала")))
    return out
