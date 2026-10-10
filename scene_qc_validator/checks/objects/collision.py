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

Имя, переделанное целиком, по имени уже не найти - а коллизия при этом лежит
на месте и видна глазами. Говорить про такой ассет «коллизии нет» бессмысленно
дважды: это неправда, и починить по такой находке нечего. Поэтому объект,
похожий на коллизию (префикс в любом регистре, с разделителем или без), но не
принадлежащий по имени никакому мешу, считается НИЧЕЙНЫМ, и его отдают мешу,
на котором он лежит: по пересечению габаритов, а при неясности - по похожести
имени. Это догадка, и в тексте находки она названа догадкой - зато у художника
есть кнопка, которая даст коллизии правильное имя.

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

import difflib
import re

from ..common import *

PREFIXES = ("UCX", "UBX", "USP", "UCP")
DEFAULT_PREFIX = r"^(UCX|UBX|USP|UCP)_"
DEFAULT_TOLERANCE = 0.001           # метр: ниже этого вмятина - шум сетки
SHOW_EDGES = 40                     # сколько рёбер выделять по нажатию


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


def _prefixes(item):
    """Префиксы коллизий списком - из того же регэкспа, что и всё остальное.

    Регэксп удобен, чтобы спросить «похоже ли это на коллизию», но опечатку
    им не разобрать: «ucx_» и «UCXMesh» он не узнает вовсе, и меш получит
    «нет коллизии» вместо «в имени опечатка». Поэтому вытаскиваем из него сами
    слова: `^(UCX|UBX|USP|UCP)_` -> UCX, UBX, USP, UCP.
    """
    text = (getattr(item, "string_param_1", "") or "").strip() or DEFAULT_PREFIX
    found = tuple(re.findall(r"[A-Za-z]{2,}", text))
    return tuple(p.upper() for p in found) or PREFIXES


def looks_like_collider(name, prefixes):
    """Префикс коллизии в любом регистре, с разделителем или без. '' - не она."""
    upper = name.upper()
    for prefix in prefixes:
        if upper.startswith(prefix):
            return prefix
    return ""


def _bounds(obj):
    """Габарит объекта в мире: (минимум, максимум)."""
    corners = [obj.matrix_world @ mathutils.Vector(corner)
               for corner in obj.bound_box]
    low = mathutils.Vector((min(c.x for c in corners), min(c.y for c in corners),
                            min(c.z for c in corners)))
    high = mathutils.Vector((max(c.x for c in corners), max(c.y for c in corners),
                             max(c.z for c in corners)))
    return low, high


def _inside_share(collider, mesh):
    """Какая доля габарита коллизии попадает в габарит меша: 0..1."""
    try:
        low_a, high_a = _bounds(collider)
        low_b, high_b = _bounds(mesh)
    except (ValueError, AttributeError):
        return 0.0
    volume = 1.0
    overlap = 1.0
    for axis in range(3):
        side = max(0.0, high_a[axis] - low_a[axis])
        volume *= side if side > 1e-9 else 1e-9
        overlap *= max(0.0, min(high_a[axis], high_b[axis])
                       - max(low_a[axis], low_b[axis]))
    return min(1.0, overlap / volume) if volume > 0 else 0.0


def _name_likeness(collider_name, mesh_name, prefixes):
    """Похожесть имени без префикса на имя меша: 0..1."""
    prefix = looks_like_collider(collider_name, prefixes)
    body = collider_name[len(prefix):].lstrip("_") if prefix else collider_name
    body = _strip_blender_numeric_suffix(body)
    return difflib.SequenceMatcher(None, body.lower(), mesh_name.lower()).ratio()


def collider_name_state(collider_name, mesh_name, prefixes):
    """(моя ли коллизия, правильно ли названа, каким должно быть имя, что не так).

    Опечатки, которые ловим, - ровно те, что портят импорт в Unreal:

      * регистр префикса: `ucx_` движок не считает коллизией;
      * нет разделителя: `UCXMesh_01` - тоже обычный меш;
      * блендеровский хвост `.001` после дубля или повторного импорта.

    Тело имени сверяем точно: угадывать, что художник имел в виду, нельзя -
    `UCX_Shelf_01` рядом с мешем `Shelf_02` это не опечатка, а чужая коллизия.
    """
    upper = collider_name.upper()
    for prefix in prefixes:
        if not upper.startswith(prefix):
            continue
        rest = collider_name[len(prefix):]
        case_ok = collider_name[:len(prefix)] == prefix
        separator_ok = rest.startswith("_")
        body = rest[1:] if separator_ok else rest
        base = _strip_blender_numeric_suffix(body)
        duplicate = base != body
        if not (base == mesh_name
                or re.fullmatch(re.escape(mesh_name) + r"_\d+", base)):
            continue
        want = "%s_%s" % (prefix, base)
        reason = ("" if (case_ok and separator_ok and not duplicate)
                  else "case" if not case_ok
                  else "separator" if not separator_ok
                  else "duplicate")
        return True, not reason, want, reason
    return False, False, "", ""


def _claimed_by_name(name, prefixes, meshes):
    """Есть ли в сцене меш, которому это имя принадлежит по имени."""
    for mesh in meshes:
        if collider_name_state(name, mesh.name, prefixes)[0]:
            return True
    return False


def _next_free_name(mesh_name, prefix, taken):
    """Следующее свободное «PREFIX_<меш>_NNN»."""
    for number in range(1, 1000):
        candidate = "%s_%s_%03d" % (prefix, mesh_name, number)
        if candidate not in bpy.data.objects and candidate not in taken:
            return candidate
    return "%s_%s" % (prefix, mesh_name)


def colliders_of(obj, item):
    """([мои коллизии], [(объект, каким быть имени, что не так)])."""
    prefixes = _prefixes(item)
    scene = bpy.context.scene
    candidates = [o for o in scene.objects
                  if o.type == 'MESH' and looks_like_collider(o.name, prefixes)]
    meshes = [o for o in scene.objects
              if o.type == 'MESH' and not looks_like_collider(o.name, prefixes)]

    mine, wrong, stray = [], [], []
    for other in candidates:
        if other is obj:
            continue
        is_mine, proper, want, reason = collider_name_state(
            other.name, obj.name, prefixes)
        if is_mine:
            mine.append(other)
            if not proper:
                wrong.append((other, want, reason))
        elif not _claimed_by_name(other.name, prefixes, meshes):
            stray.append(other)

    # ничейные: отдаём тому мешу, на котором лежат. Догадка, но лучше, чем
    # сказать «коллизии нет» про объект, который видно в сцене
    taken = set()
    for orphan in stray:
        best, best_score = None, 0.0
        for mesh in meshes:
            share = _inside_share(orphan, mesh)
            likeness = _name_likeness(orphan.name, mesh.name, prefixes)
            score = max(share, likeness)
            if score > best_score:
                best, best_score = mesh, score
        if best is obj and best_score >= 0.5:
            prefix = looks_like_collider(orphan.name, prefixes)
            want = _next_free_name(obj.name, prefix, taken)
            taken.add(want)
            mine.append(orphan)
            wrong.append((orphan, want, "stray"))
    return mine, wrong


def _free_name(wanted, mesh_name, prefix_of_wanted):
    """Свободное имя: если `wanted` занято, Blender допишет «.001» - а это
    снова сломанная коллизия. Берём следующий номер вместо точки."""
    if wanted not in bpy.data.objects:
        return wanted
    stem = re.sub(r"_\d+$", "", wanted)
    for number in range(1, 1000):
        candidate = "%s_%03d" % (stem, number)
        if candidate not in bpy.data.objects:
            return candidate
    return wanted


def _is_collider(obj, item):
    """Коллизия ли это сама - считая и кривые префиксы: с такого объекта
    спрашивать про ЕГО коллизию незачем, он и есть коллизия."""
    return bool(looks_like_collider(obj.name, _prefixes(item)))


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
                    % (len(wrong), ", ".join(o.name for o, _w, _r in wrong[:6]))),
        "element_ref": "obj:%s" % wrong[0][0].name,
        "values": {"mesh": obj.name, "count": len(wrong),
                   "names": [o.name for o, _w, _r in wrong[:6]],
                   "wants": [w for _o, w, _r in wrong[:6]],
                   "reasons": sorted({r for _o, _w, r in wrong}),
                   "want": "%s или %s_NN" % (obj.name, obj.name)},
    }]


def fix_collision_name(obj, item, result):
    """Переименовать коллизии в правильное имя: префикс заглавными, через «_»,
    без блендеровского хвоста."""
    if _is_collider(obj, item) or _skips(item, obj.name):
        return False
    _mine, wrong = colliders_of(obj, item)
    changed = False
    for collider, want, _reason in wrong:
        if not want or collider.name == want:
            continue
        collider.name = _free_name(want, obj.name, None)
        changed = True
    return changed


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
    """На коллизии должен стоять материал меша.

    Материалов у меша может быть несколько: у MET на одном ассете законно
    живут MI_..._Wood, MI_..._PapierMache и MI_..._Metal. Коллизия - выпуклая
    оболочка, на ней один материал, и требовать от неё весь список значило бы
    не пройти никогда. Поэтому условие - ПОДМНОЖЕСТВО: материалы коллизии
    должны быть среди материалов меша. У ассета с одним материалом (ARDENA) это
    то же самое, что прежняя точная сверка.
    """
    if _is_collider(obj, item) or _skips(item, obj.name):
        return []
    # bool_param_1: True - на коллизии материал меша (ARDENA), False - материала
    # быть не должно (MET, правило проекта от 2026-10-10). Два проекта требуют
    # противоположного, поэтому это настройка, а не зашитое правило.
    want_material = bool(getattr(item, "bool_param_1", True))
    wanted = [slot.material.name for slot in obj.material_slots if slot.material]
    mine, _wrong = colliders_of(obj, item)
    issues = []
    for collider in mine:
        here = [slot.material.name for slot in collider.material_slots if slot.material]
        if not want_material:
            if not here:
                continue
            issues.append({
                "message": ("%s carries %s, a collision must carry none"
                            % (collider.name, ", ".join(here))),
                "element_ref": "obj:%s" % collider.name,
                "values": {"mesh": obj.name, "collider": collider.name,
                           "has": here, "want": [], "mode": "empty"},
            })
            continue
        if here and wanted and set(here) <= set(wanted):
            continue
        if here == wanted:
            continue
        if not here:
            message = ("%s has no material, the mesh carries %s"
                       % (collider.name, ", ".join(wanted)))
        elif not wanted:
            message = ("the mesh has no material, %s carries %s"
                       % (collider.name, ", ".join(here)))
        else:
            message = ("%s carries %s, which the mesh does not: it carries %s"
                       % (collider.name, ", ".join(sorted(set(here) - set(wanted))),
                          ", ".join(wanted)))
        issues.append({
            "message": message,
            "element_ref": "obj:%s" % collider.name,
            "values": {"mesh": obj.name, "collider": collider.name,
                       "has": here, "want": wanted, "mode": "same"},
        })
    return issues


# ------------------------------------------------------------------- автофикс


def fix_collision_material(obj, item, result):
    """Привести материал коллизии к правилу проекта: как на меше или снять."""
    if _is_collider(obj, item) or _skips(item, obj.name):
        return False
    if not bool(getattr(item, "bool_param_1", True)):
        # правило «материала быть не должно» - чистим слоты
        mine, _wrong = colliders_of(obj, item)
        changed = False
        for collider in mine:
            if any(slot.material for slot in collider.material_slots):
                collider.data.materials.clear()
                changed = True
        return changed
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
