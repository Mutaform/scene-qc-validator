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
    """
    if state_value == DIM:
        return "—"
    return bad if state_value == BAD else good


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
    """«2.4 px/см» или «1001 - 2.4, 1002 - 1.9»: плотность канала для разбора."""
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
            text = "%.2f px/см" % list(value.values())[0]
        else:
            text = ", ".join("%s - %.2f" % (tile if tile > 0 else "вне сетки", density)
                             for tile, density in sorted(value.items())) + " px/см"
    else:
        if value is None:
            return "—"
        text = "%.2f px/см" % value
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
    return " или ".join(schemes) if schemes else str(raw)


def _channels(pattern, fallback="во всех каналах"):
    """«^UV3$» -> «UV3», «^(UV1|UV2)$» -> «UV1 и UV2», «.+» -> «во всех каналах».

    В колонке нормы стоит правило, по которому судят, и художник читает его
    глазами. Регексп он читать не обязан: «канал ^UV3$ без наложений» - это
    отписка, а не правило.
    """
    text = (pattern or "").strip()
    if not text or text in (".+", ".*", "^.+$", "^.*$"):
        return fallback
    core = text.lstrip("^").rstrip("$")
    if core.startswith("(") and core.endswith(")"):
        core = core[1:-1]
    names = [part for part in core.split("|") if part]
    if names and all(re.fullmatch(r"[A-Za-z0-9_]+", name) for name in names):
        if len(names) == 1:
            return names[0]
        return ", ".join(names[:-1]) + " и " + names[-1]
    return text                     # что-то сложное - показываем как есть


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
    out.append(("Имя", obj.name,
                state("nm_object_pattern", "nm_name_characters"),
                "шаблон: %s, без пробелов и кириллицы"
                % state.param("nm_object_pattern", "string_param_1", "—")))
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
    out.append(("Топология", _verdict(topology, "non manifold", "чисто"),
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
    has_colors = bool(getattr(mesh, "color_attributes", None))
    out.append(("Vertex Color", _vertex_color_text(obj, mesh),
                state("vc_missing", "vc_id_values"),
                "ID десятыми в красном, G и B в нуле, слоёв не меньше %s"
                % state.param("vc_id_values", "int_param_1", 2),
                None,
                ("Посмотреть", "show_vc") if has_colors else None))

    # --- развёртка
    out.append(("UV-каналов", _uv_text(mesh), state("uv_missing", "uv_set_count", "uv_set_names"),
                "имена: %s, не больше %s"
                % (_uv_names_norm(state.param("uv_set_names", "string_param_1", "—")),
                   state.param("uv_set_count", "int_param_1", "—")),
                _n(len(mesh.uv_layers)) if mesh.uv_layers else "нет"))
    tile = state("uv_single_tile")
    judged = _channels(state.param("uv_single_tile", "string_param_1", ".+"),
                       "все каналы")
    out.append(("Шеллы в 0-1", _verdict(tile, "выходят за квадрат", "внутри"), tile,
                ("канал %s не должен выходить за квадрат 0-1" % judged
                 if judged != "все каналы"
                 else "ни один канал не должен выходить за квадрат 0-1")))
    overlap = state("uv_overlap")
    watched = _channels(state.param("uv_overlap", "string_param_1", ".+"))
    out.append(("UV overlap", _verdict(overlap, "есть", "нет"), overlap,
                ("в канале %s наложений быть не должно" % watched
                 if watched != "во всех каналах"
                 else "наложений не должно быть ни в одном канале")))
    gap = state.item("uv_padding_gap")
    if gap is not None:
        size = gap.int_param_1 or 2048
        measured, why = _padding_gap(obj, gap.int_param_2 or 1, size)
        out.append(("Паддинг при паковке",
                    why if measured is None
                    else "~%g px при карте %s" % (round(measured), _n(size)),
                    # не измерили - значит сказать нечего. Зелёная галочка здесь
                    # читалась бы как «проверено и в порядке»
                    INFO if measured is None else state("uv_padding_gap"),
                    "норма по ТЗ %g-%g px"
                    % (gap.float_param_1 or 8.0, gap.float_param_2 or 16.0)))
    # плотность текселя: UV1 показываем всегда (правила нет, норма зависит от
    # плана ассета), судимый канал - строкой с вердиктом
    size = state.param("uv_texel_density", "int_param_1", 2048) or 2048
    out.append(("Плотность текселя UV1", _texel_text(obj, 1, size, per_tile=True), INFO,
                "правила нет: норма зависит от плана ассета"))
    judged = state.item("uv_texel_density")
    if judged is not None:
        number = judged.int_param_2 or 3
        value, _collapsed = (None, 0.0)
        try:
            from .checks.mapping.texel_density import px_per_m
            value, _collapsed = px_per_m(obj, number, size)
        except Exception as error:                  # noqa: BLE001
            print("[Scene QC Validator] плотность текселя %s: %s" % (obj.name, error))
        out.append(("Плотность текселя UV%d" % number,
                    "—" if value is None else "%d px/м" % round(value),
                    state("uv_texel_density"),
                    "%g px/м при карте %s ±%g%%"
                    % (judged.float_param_1 or 1024.0, _n(size),
                       (judged.float_param_2 or 0.15) * 100.0)))
    density, _per_tile = _packing_density(obj, state.param("uv_packing_density",
                                                           "int_param_2", 1))
    if density is not None:
        out.append(("Плотность паковки", "%.1f%%" % (density * 100.0),
                    state("uv_packing_density"),
                    "не меньше %s"
                    % _percent(state.param("uv_packing_density", "float_param_1", 0.7))))
    tiles = _udim_tiles(obj, state.param("uv_udim_shell_in_tile", "int_param_2", 1))
    if tiles:
        out.append(("UDIM-тайлы", ", ".join(str(t) for t in tiles),
                    state("uv_udim_shell_in_tile", "uv_udim_tile_set",
                          "uv_udim_tile_fill", "uv_shifted_duplicate"),
                    "подряд с 1001, каждый заполнен",
                    str(len(tiles))))
    elif state.item("uv_udim_shell_in_tile") is not None:
        # тайл один - строку всё равно показываем: иначе четыре UDIM-проверки
        # судят ассет молча, и в разборе их не видно
        out.append(("UDIM-тайлы", "один, 1001",
                    state("uv_udim_shell_in_tile", "uv_udim_tile_set",
                          "uv_udim_tile_fill", "uv_shifted_duplicate"),
                    "подряд с 1001, каждый заполнен", "1"))
    # строки нет вовсе, если проверки нет в этапе: у ARDENA это правило не
    # используется, и прочерк в разборе только вызывал вопросы (денис)
    if state.item("uv_unaligned_edges") is not None:
        out.append(("Границы шеллов",
                    _verdict(state("uv_unaligned_edges"), "завалены", "ровные"),
                    state("uv_unaligned_edges"),
                    "у шеллов, задуманных прямыми, границы ровно по горизонтали "
                    "и вертикали (допуск %s°)"
                    % state.param("uv_unaligned_edges", "float_param_1", 0.1)))

    nanite = state("obj_nanite_closed_geometry")
    if state.item("obj_nanite_closed_geometry") is not None:
        out.append(("Геометрия для Nanite",
                    _verdict(nanite, "есть открытый край", "закрыта"), nanite,
                    "открытые оболочки утоплены в соседнюю геометрию"))

    # --- материал
    out.append(("Материалы", _materials_text(obj),
                state("mat_missing", "mat_material_count", "mat_material_name"),
                "не больше %s, имя по шаблону %s"
                % (state.param("mat_material_count", "int_param_1", "—"),
                   state.param("mat_material_name", "string_param_1", "—")),
                _n(len(obj.material_slots)) if obj.material_slots else "нет"))

    # --- коллизии
    out.append(("Коллизии", _collisions_text(obj, state),
                state("col_missing", "col_name", "col_convex", "col_material"),
                "UCX_<имя меша> или UCX_<имя меша>_NN, выпуклые, "
                "с материалом меша"))
    return out
