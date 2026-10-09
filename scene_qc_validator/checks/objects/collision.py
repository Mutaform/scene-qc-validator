# -*- coding: utf-8 -*-
"""Коллизии: есть ли они, так ли названы, выпуклые ли и тот ли на них материал.

Коллизия в Unreal приезжает вместе с мешем в одном FBX и узнаётся по имени:
`UCX_<имя меша>` или `UCX_<имя меша>_NN`, плюс примитивы UBX, USP, UCP. Имя -
единственная связь между мешем и его коллизией, поэтому опечатка в нём не
«некрасиво», а «коллизии не будет»: движок положит объект в сцену как обычную
геометрию.

Проверки живут на РЕНДЕР-МЕШЕ, а не на самих коллизиях: в пресете ARDENA
объекты по `^(UCX|UBX|USP|UCP)_` исключены из проверки целиком (у них нет ни
UV, ни своего пивота, и гонять по ним меш-проверки незачем). Поэтому меш сам
ищет свои коллизии по имени и отвечает за них.

Про выпуклость. UCX - это convex hull: движок сам ничего не выпрямляет, он
принимает оболочку как есть, и вмятина в ней означает, что персонаж провалится
в стену. Проверяем по рёбрам, а не перебором «каждая вершина против каждой
грани»: у замкнутой манифолдной поверхности локальной выпуклости на всех рёбрах
достаточно для выпуклости целиком, и это O(рёбра) вместо O(грани × вершины) -
разница между мгновенно и минутами на коллизии, которую по ошибке сделали
копией меша.

Открытая оболочка выпуклой не бывает по определению: у объёма должна быть
граница. Дырку показываем отдельным поводом, чтобы в тексте находки было
написано, что именно не так.

Замеры идут в мировых единицах: bmesh перед проверкой переводится матрицей
объекта, иначе у коллизии с масштабом 0.01 допуск в миллиметр означал бы
десять сантиметров.
"""

import re

from ..common import *

PREFIXES = ("UCX", "UBX", "USP", "UCP")
DEFAULT_PREFIX = r"^(UCX|UBX|USP|UCP)_"
DEFAULT_TOLERANCE = 0.001           # метр: ниже этого вмятина - шум сетки
SHOW_EDGES = 40                     # сколько рёбер выделять по нажатию


def _prefix_pattern(item):
    text = (getattr(item, "string_param_1", "") or "").strip() or DEFAULT_PREFIX
    try:
        return re.compile(text)
    except re.error:
        return re.compile(DEFAULT_PREFIX)


def _skips(item, name):
    """Меш, которому коллизия не нужна: регексом в настройках проверки."""
    text = (getattr(item, "string_param_2", "") or "").strip()
    if not text:
        return False
    try:
        return re.search(text, name) is not None
    except re.error:
        return False


def _tolerance(item):
    value = getattr(item, "float_param_1", 0.0)
    return value if value and value > 0 else DEFAULT_TOLERANCE


def collider_name_state(collider_name, mesh_name, pattern):
    """(моя ли это коллизия, правильно ли названа).

    «Моя» - с точностью до блендеровского хвоста «.001», который дописывается
    при дубле и при импорте поверх существующего объекта. Такой объект в Unreal
    уже не коллизия: там в имени точка, и шаблон его не узнаёт.
    """
    match = pattern.match(collider_name)
    if match is None:
        return False, False
    rest = collider_name[match.end():]
    proper = bool(rest == mesh_name
                  or re.fullmatch(re.escape(mesh_name) + r"_\d+", rest))
    base = _strip_blender_numeric_suffix(rest)
    mine = proper or bool(base == mesh_name
                          or re.fullmatch(re.escape(mesh_name) + r"_\d+", base))
    return mine, proper


def colliders_of(obj, item):
    """([мои коллизии], [названные неправильно]) в порядке сцены."""
    pattern = _prefix_pattern(item)
    scene = bpy.context.scene
    mine, wrong = [], []
    for other in scene.objects:
        if other is obj or other.type != 'MESH':
            continue
        is_mine, proper = collider_name_state(other.name, obj.name, pattern)
        if not is_mine:
            continue
        mine.append(other)
        if not proper:
            wrong.append(other)
    return mine, wrong


def _is_collider(obj, item):
    return _prefix_pattern(item).match(obj.name) is not None


# ------------------------------------------------------------------ выпуклость


def convex_report(collider, tolerance):
    """(поводов, худшая вмятина в метрах, рёбра) - пусто, если всё выпукло.

    Поводов два: `open` - оболочка не замкнута, `dent` - вмятина на ребре.
    """
    bm, owned = _read_bmesh(collider)
    if not owned:
        bm = bm.copy()          # меш в правке: трогать живой bmesh нельзя
    try:
        bm.transform(collider.matrix_world)
        # треугольники, а не квады: у неплоского квада нормаль усреднённая, и
        # двугранный угол по ней врёт в обе стороны. Движок коллизию всё равно
        # триангулирует, так что считаем то же, что увидит он
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.normal_update()
        bm.edges.ensure_lookup_table()

        open_edges = [edge.index for edge in bm.edges if len(edge.link_faces) != 2]
        if open_edges:
            return "open", 0.0, open_edges[:SHOW_EDGES]

        worst = 0.0
        dents = []
        for edge in bm.edges:
            first, second = edge.link_faces
            origin = first.calc_center_median()
            normal = first.normal
            on_edge = set(edge.verts)
            for vertex in second.verts:
                if vertex in on_edge:
                    continue
                distance = normal.dot(vertex.co - origin)
                if distance > tolerance:
                    worst = max(worst, distance)
                    dents.append(edge.index)
                    break
        if dents:
            return "dent", worst, sorted(dents)[:SHOW_EDGES]
        return "", 0.0, []
    finally:
        bm.free()


# --------------------------------------------------------------- сами проверки


def check_collision_missing(obj, item):
    """У меша должна быть коллизия."""
    if _is_collider(obj, item) or _skips(item, obj.name):
        return []
    mine, _wrong = colliders_of(obj, item)
    if mine:
        return []
    return [{
        "message": "No collision mesh named %s%s" % (DEFAULT_PREFIX, obj.name),
        "element_ref": "",
        "values": {"mesh": obj.name,
                   "prefix": (getattr(item, "string_param_1", "")
                              or DEFAULT_PREFIX)},
    }]


def check_collision_name(obj, item):
    """Имя коллизии должно быть ровно «UCX_<меш>» или «UCX_<меш>_NN»."""
    if _is_collider(obj, item) or _skips(item, obj.name):
        return []
    _mine, wrong = colliders_of(obj, item)
    if not wrong:
        return []
    return [{
        "message": ("%d collision mesh(es) are named off the pattern: %s"
                    % (len(wrong), ", ".join(o.name for o in wrong[:6]))),
        "element_ref": "obj:%s" % wrong[0].name,
        "values": {"mesh": obj.name, "count": len(wrong),
                   "names": [o.name for o in wrong[:6]],
                   "want": "%s или %s_NN" % (obj.name, obj.name)},
    }]


def check_collision_convex(obj, item):
    """Каждая коллизия должна быть замкнутой выпуклой оболочкой."""
    if _is_collider(obj, item) or _skips(item, obj.name):
        return []
    tolerance = _tolerance(item)
    mine, _wrong = colliders_of(obj, item)
    issues = []
    for collider in mine:
        try:
            kind, worst, edges = convex_report(collider, tolerance)
        except (RuntimeError, ReferenceError, ValueError) as error:
            print("[Scene QC Validator] выпуклость %s: %s" % (collider.name, error))
            continue
        if not kind:
            continue
        reference = "obj:%s" % collider.name
        if edges:
            reference += ";e:" + ",".join(str(i) for i in edges)
        issues.append({
            "message": ("%s is not a convex hull (%s)"
                        % (collider.name,
                           "open shell" if kind == "open"
                           else "dent up to %.1f mm" % (worst * 1000.0))),
            "element_ref": reference,
            "values": {"mesh": obj.name, "collider": collider.name, "kind": kind,
                       "edges": len(edges), "dent": round(worst * 1000.0, 1),
                       "tolerance": round(tolerance * 1000.0, 2)},
        })
    return issues


def check_collision_material(obj, item):
    """На коллизии должен стоять тот же материал, что и на меше."""
    if _is_collider(obj, item) or _skips(item, obj.name):
        return []
    wanted = [slot.material.name for slot in obj.material_slots if slot.material]
    mine, _wrong = colliders_of(obj, item)
    issues = []
    for collider in mine:
        here = [slot.material.name for slot in collider.material_slots if slot.material]
        if here == wanted:
            continue
        if not here:
            message = ("%s has no material, the mesh carries %s"
                       % (collider.name, ", ".join(wanted)))
        elif not wanted:
            message = ("the mesh has no material, %s carries %s"
                       % (collider.name, ", ".join(here)))
        else:
            message = ("%s carries %s, the mesh carries %s"
                       % (collider.name, ", ".join(here), ", ".join(wanted)))
        issues.append({
            "message": message,
            "element_ref": "obj:%s" % collider.name,
            "values": {"mesh": obj.name, "collider": collider.name,
                       "has": here, "want": wanted},
        })
    return issues


# ------------------------------------------------------------------- автофикс


def fix_collision_material(obj, item, result):
    """Повесить на коллизию материал меша: слот за слотом, как на меше."""
    if _is_collider(obj, item) or _skips(item, obj.name):
        return False
    wanted = [slot.material for slot in obj.material_slots if slot.material]
    if not wanted:
        return False                # у самого меша материала нет - чинить нечем
    mine, _wrong = colliders_of(obj, item)
    changed = False
    for collider in mine:
        here = [slot.material.name for slot in collider.material_slots if slot.material]
        if here == [m.name for m in wanted]:
            continue
        collider.data.materials.clear()
        for material in wanted:
            collider.data.materials.append(material)
        changed = True
    return changed
