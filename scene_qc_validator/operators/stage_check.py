# -*- coding: utf-8 -*-
"""Проверка этапа одной кнопкой: загрузить этап, прогнать, открыть сводку в браузере.

Кнопка живёт в шапке вьюпорта, рядом с остальными инструментами студии: художник
проверяет ассет, не открывая боковую панель и не вспоминая, какой этап сейчас
загружен. Этапы берутся из активного проекта, так что для ARDENA это ровно три
кнопки, а для студийного чеклиста - его пять.

Отсюда же выполняются кнопки «Исправить» со страницы отчёта: их приносит
:mod:`live`, а делает работу `run_action` - в главном потоке, без единого окна.
"""

import json
import os

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from .selection import select_result_by_index
from .core import (
    _scope_empty_message,
    _settings,
    _validation_targets,
    checks_mod,
    ensure_checks_initialized,
    presets_mod,
    run_validation_logic,
)
from .. import explain as explain_mod
from .. import live as live_mod
from .. import report as report_mod
from ..ui.helpers import addon_version


def _reports_dir():
    try:
        return bpy.utils.extension_path_user(__package__.rsplit(".", 1)[0],
                                             path="reports", create=True)
    except Exception:
        return bpy.app.tempdir


def _scope_label(settings):
    items = settings.bl_rna.properties["validation_scope"].enum_items
    item = items.get(settings.validation_scope)
    return item.name if item is not None else settings.validation_scope


def _pin_targets(settings, targets):
    """Запомнить, по каким объектам собран отчёт."""
    settings.report_targets = "\n".join(obj.name for obj in targets)


def _pinned_targets(context, settings):
    """Объекты открытого отчёта. Пусто - значит отчёта ещё не было."""
    names = [n for n in settings.report_targets.split("\n") if n]
    objects = [context.scene.objects.get(name) for name in names]
    return [obj for obj in objects if obj is not None]


def _build_doc(context, settings, note=None, targets=None):
    if targets is None:
        targets = _validation_targets(context)
    _pin_targets(settings, targets)
    return report_mod.build(
        settings,
        addon_version(),
        settings.active_project_name,
        settings.active_stage_name,
        _scope_label(settings),
        targets,
        muted_keys={(m.object_name, m.check_id) for m in settings.muted},
        note=note,
    )


def _write(context, settings, note=None, targets=None):
    """Переписать страницу и объявить её новую версию открытой вкладке."""
    doc = _build_doc(context, settings, note=note, targets=targets)
    info = live_mod.begin_revision()
    path = report_mod.write(doc, _reports_dir(), live=info)
    if path:
        live_mod.set_page(path)
    return doc, path


def _write_and_open(context, settings):
    live_mod.start()
    # открытая вкладка подхватит новую версию сама - вторую не открываем
    watched = live_mod.page_watched()
    doc, path = _write(context, settings)
    if path and not watched:
        report_mod.open_in_browser(path)
    return doc, path


def _fix_one_check(context, settings, check_id, only=""):
    """Применить фикс одной проверки. Возвращает число правок.

    `only` - имена объектов через запятую: у строки в отчёте своя кнопка, и
    чинить она должна объекты своей строки. Одна проверка даёт по строке на
    каждый разный замер, и без этого обе кнопки делали бы одно и то же.
    """
    if not check_id:
        return 0
    definition = checks_mod.get_check_definition(check_id)
    check_item = next((c for c in settings.checks if c.check_id == check_id), None)
    if not (definition and definition.get("fix") and check_item):
        return 0
    wanted = {n for n in (only or "").split(",") if n}
    names = [r.object_name for r in settings.results
             if r.check_id == check_id and r.can_fix and not r.muted
             and (not wanted or r.object_name in wanted)]
    fixed = 0
    for name in dict.fromkeys(names):
        obj = context.scene.objects.get(name)
        if obj is None:
            continue
        try:
            if definition["fix"](obj, check_item, None):
                fixed += 1
        except Exception as error:
            print(f"[Scene QC Validator] Fix {check_id} on {name} failed: {error}")
    return fixed


# Вьюпорт, переключённый на показ вершинного цвета, и то, каким он был до этого.
# Модульное состояние, а не настройка сцены: это временный взгляд, он не должен
# пережить перезагрузку аддона и уж тем более попасть в .blend художника.
_vertex_view = {"saved": [], "object": ""}


def _restore_vertex_view():
    """Вернуть вьюпортам прежнее затенение. Молча: окно могли закрыть."""
    for space, shading_type, color_type in _vertex_view["saved"]:
        try:
            space.shading.type = shading_type
            space.shading.color_type = color_type
        except (ReferenceError, TypeError, AttributeError):
            pass
    _vertex_view["saved"] = []
    _vertex_view["object"] = ""


def _show_vertex_color(context, object_name):
    """Показать маску вершинного цвета во вьюпорте. Повторное нажатие - выключить.

    Числа в разборе говорят, что слои есть и что они по правилам. Они не говорят,
    что слой назначен тому куску, которому надо, - это видно только глазами.
    """
    if _vertex_view["saved"] and _vertex_view["object"] == object_name:
        _restore_vertex_view()
        return {"ok": True, "text": "Вершинный цвет выключен, вьюпорт как был"}
    _restore_vertex_view()

    obj = context.scene.objects.get(object_name)
    if obj is None:
        return {"ok": False, "text": "Объект %s не найден в сцене" % object_name}
    attributes = getattr(obj.data, "color_attributes", None)
    if not attributes:
        return {"ok": False, "text": "У %s нет вершинного цвета" % object_name}

    # активный атрибут - тот же, по которому судила проверка
    active = attributes.active_color or attributes[0]
    try:
        attributes.active_color = active
    except (AttributeError, TypeError):
        pass

    for o in list(context.selected_objects):
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj

    saved = []
    for screen_area in getattr(context.screen, "areas", ()):
        if screen_area.type != 'VIEW_3D':
            continue
        space = screen_area.spaces.active
        saved.append((space, space.shading.type, space.shading.color_type))
        space.shading.type = 'SOLID'
        space.shading.color_type = 'VERTEX'
        screen_area.tag_redraw()
    if not saved:
        return {"ok": False, "text": "Во вьюпорте нечего переключать"}
    _vertex_view["saved"] = saved
    _vertex_view["object"] = object_name
    return {"ok": True, "text": "Вершинный цвет «%s» показан на %s - нажмите ещё раз, "
                                "чтобы вернуть вьюпорт" % (active.name, object_name)}


def _auto_check_ids(settings):
    """Проверки, которые страница объявила как «авто» - их и чинит общая кнопка.

    `sqc.fix_all` берёт всё, у чего есть фикс, и переименовывает объекты с
    материалами заодно. В отчёте переименование стоит отдельным видом
    («кнопкой: правка заметная, сама собой не делается»), и нажатие на «авто»
    не должно делать больше, чем написано на кнопке.
    """
    out = []
    for result in settings.results:
        if not result.can_fix or result.muted or result.check_id in out:
            continue
        values = {}
        if result.values_json:
            try:
                values = json.loads(result.values_json)
            except ValueError:
                values = {}
        if explain_mod.fix_hint(result.check_id, values, True)[0] == explain_mod.AUTO:
            out.append(result.check_id)
    return out


def _fix_auto(context, settings, targets, max_passes=6):
    """Прогнать «авто»-фиксы, пока они что-то меняют. Возвращает число правок."""
    total = 0
    for _pass in range(max_passes):
        fixed = sum(_fix_one_check(context, settings, check_id)
                    for check_id in _auto_check_ids(settings))
        total += fixed
        run_validation_logic(context, targets=targets)
        if not fixed:
            break
    return total


def run_action(context, action, code="", object_name=""):
    """Кнопка со страницы отчёта. Чиним, перепроверяем, переписываем страницу.

    Окон здесь нет ни одного: человек в этот момент смотрит в браузер, и окно
    Blender осталось бы незамеченным за ним. Всё, что нужно сказать, уходит в
    строку состояния на странице.
    """
    settings = _settings(context)

    if action == "select":
        # то же, что клик по строке в панели: выделить объект и его элементы
        index = next(
            (i for i, r in enumerate(settings.results)
             if r.object_name == object_name and r.check_id == code),
            -1,
        )
        if index < 0:
            return {"ok": False, "text": "Находка больше не в списке - перепроверьте"}
        if context.scene.objects.get(object_name) is None:
            return {"ok": False, "text": "Объект %s не найден в сцене" % object_name}
        # присваивание индекса само зовёт select_result_by_index (колбэк
        # свойства). Звать её ещё раз нельзя: у наложений UV это переключатель,
        # и второй вызов тут же гасит показанное
        if settings.active_result_index == index:
            select_result_by_index(context, index)
        else:
            settings.active_result_index = index
        for area in getattr(context.screen, "areas", ()):
            area.tag_redraw()
        return {"ok": True, "text": "Показано в Blender: %s" % object_name}

    if action == "show_vc":
        result = _show_vertex_color(context, object_name)
        for area in getattr(context.screen, "areas", ()):
            area.tag_redraw()
        return result

    if context.mode != 'OBJECT' and context.object is not None:
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass

    # чиним и перепроверяем по объектам отчёта: выделение в Blender к этому
    # моменту уже другое - его сменил клик по находке или сам фикс
    targets = _pinned_targets(context, settings) or _validation_targets(context)
    before = sum(1 for r in settings.results if not r.muted)
    if action == "fix_all":
        label = "Исправить автоматически"
        if not _fix_auto(context, settings, targets):
            note = {"ok": False, "text": "%s — чинить нечего" % label}
            _write(context, settings, note=note, targets=targets)
            return {"ok": False, "text": note["text"]}
    elif action == "fix_code":
        # имя проверки по-русски: строку читают в браузере, рядом с русскими находками
        definition = checks_mod.get_check_definition(code)
        label = "Исправить: %s" % explain_mod.label(
            code, definition["label"] if definition else code)
        if not _fix_one_check(context, settings, code, object_name):
            note = {"ok": False, "text": "%s — чинить нечего" % label}
            _write(context, settings, note=note, targets=targets)
            return {"ok": False, "text": note["text"]}
        run_validation_logic(context, targets=targets)
    else:
        return {"ok": False, "text": "Неизвестное действие"}

    after = sum(1 for r in settings.results if not r.muted)
    gone = before - after
    text = ("%s — снято находок: %d" % (label, gone)) if gone > 0 else \
        ("%s — список не изменился" % label)
    _write(context, settings, note={"ok": gone > 0, "text": text}, targets=targets)
    return {"ok": gone > 0, "text": text}


class SQC_OT_check_stage(Operator):
    bl_idname = "sqc.check_stage"
    bl_label = "Check Stage"
    bl_description = (
        "Load this stage of the active project, validate the current scope and "
        "open the summary in a browser"
    )

    project_name: StringProperty()
    stage_name: StringProperty()

    def execute(self, context):
        ensure_checks_initialized(context)
        settings = _settings(context)
        project = self.project_name or settings.active_project_name
        stage = self.stage_name or settings.active_stage_name

        if not presets_mod.load_stage(project, stage, settings.checks, settings):
            self.report({'WARNING'}, f"Stage '{stage}' is missing from '{project}'")
            return {'CANCELLED'}
        settings.active_project_name = project
        settings.active_stage_name = stage
        settings.active_preset_name = project
        settings.applied_stage_key = f"{project}::{stage}"

        targets_found, any_fail = run_validation_logic(context)
        if not targets_found:
            self.report({'WARNING'}, _scope_empty_message(settings.validation_scope))
            return {'CANCELLED'}

        doc, path = _write_and_open(context, settings)
        if not path:
            self.report({'WARNING'}, "Could not write the report page")
            return {'CANCELLED'}
        self.report(
            {'WARNING'} if any_fail else {'INFO'},
            f"{stage}: {doc['errors']} error(s), {doc['warnings']} note(s) "
            f"on {len(doc['objects'])} object(s)",
        )
        return {'FINISHED'}


class SQC_OT_show_vertex_color(Operator):
    bl_idname = "sqc.show_vertex_color"
    bl_label = "Show Vertex Color"
    bl_description = (
        "Show the vertex color mask on the active object in the viewport. "
        "Press again to put the viewport back"
    )

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            # уже показываем что-то - дадим выключить, даже если активного меша нет
            if _vertex_view["saved"]:
                _restore_vertex_view()
                self.report({'INFO'}, "Вьюпорт возвращён")
                return {'FINISHED'}
            self.report({'WARNING'}, "Нет активного меша")
            return {'CANCELLED'}
        outcome = _show_vertex_color(context, obj.name)
        self.report({'INFO'} if outcome["ok"] else {'WARNING'}, outcome["text"])
        return {'FINISHED'} if outcome["ok"] else {'CANCELLED'}


class SQC_OT_open_report(Operator):
    bl_idname = "sqc.open_report"
    bl_label = "Open Last Report"
    bl_description = "Open the last written summary page again"

    def execute(self, context):
        path = os.path.join(_reports_dir(), "qc_report.html")
        if not os.path.exists(path):
            self.report({'WARNING'}, "No report yet - run a stage check first")
            return {'CANCELLED'}
        report_mod.open_in_browser(path)
        return {'FINISHED'}
