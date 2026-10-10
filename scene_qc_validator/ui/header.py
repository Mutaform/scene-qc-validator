# -*- coding: utf-8 -*-
"""Кнопки проверки в шапке 3D-вьюпорта - по одной на клиента.

Художник проверяет ассет десятки раз за день, а боковая панель чаще закрыта.
Кнопка даёт по действию на этап - в один клик, со сводкой сразу в браузере.

Проекты здесь зашиты константами, а не берутся из настроек сцены. Буква на
кнопке - это буква клиента, и означать она должна ровно его: иначе художник,
переключивший панель на студийный чеклист, нажимает «А» и получает проверку не
того проекта, ничего об этом не узнав. Панель остаётся общей - там проект
выбирается как раньше.

Кнопок две. «А» - ARDENA, один проект. «М» - MET, и у него ДВА проекта в одном
меню: ветки MET независимы, художник работает по одной, а правила UV у них
расходятся настолько, что одним пресетом их не проверить (подробности - в
`MET\\Git\\tools\\blender_validator\\make_preset.py`). Поэтому меню «М» перечисляет
сначала уникальный пайплайн с его этапами, потом LMS со своими.
"""

from bpy.types import Panel

from .. import presets as presets_mod
from .checklist_panel import _stage_button_text
from .helpers import addon_version


# Имя проекта - ключ к файлу пресета, в меню оно показывается человеческим.
PROJECT_LABEL = {
    "MET_Unique": "MET · уникальный пайплайн",
    "MET_LMS": "MET · LMS",
}


def _draw_projects(layout, projects):
    """Колонка кнопок «проверить этап» на каждый проект, в заданном порядке."""
    for project in projects:
        stages = presets_mod.project_stage_names(project)
        box = layout.column(align=True)
        box.label(text=PROJECT_LABEL.get(project, project), icon='PRESET')
        if not stages:
            # проект удалили или переименовали: молчаливая пустота выглядела бы
            # как «кнопка сломалась», поэтому говорим, чего не хватает
            box.label(text=f"Project '{project}' is not installed", icon='ERROR')
            continue
        column = box.column(align=True)
        column.scale_y = 1.3
        for stage in stages:
            op = column.operator(
                "sqc.check_stage",
                text=f"Check {_stage_button_text(stage)}",
                icon='PLAY',
            )
            op.project_name = project
            op.stage_name = stage
        if project is not projects[-1]:
            layout.separator()


def _draw_menu(layout, context, title, projects):
    settings = context.scene.sqc_settings

    head = layout.row(align=True)
    head.label(text="QC Validator · %s" % title, icon='CHECKMARK')
    version = head.row(align=True)
    version.alignment = 'RIGHT'
    version.enabled = False
    version.label(text=f"ver {addon_version()}")

    if not len(settings.checks):
        layout.operator("sqc.init_checks", text="Initialize Checklist", icon='FILE_REFRESH')
        return

    layout.prop(settings, "validation_scope", text="")
    _draw_projects(layout, projects)

    layout.separator()
    # взгляд, а не проверка: числа в отчёте говорят, что слои есть и что они
    # по правилам, но не что назначены нужным кускам - это видно только глазами
    layout.operator("sqc.show_vertex_color", text="Показать Vertex Color",
                    icon='COLOR')
    layout.operator("sqc.open_report", text="Open Last Report", icon='URL')


class SQC_PT_header_menu(Panel):
    """Выпадающее меню кнопки «А» в шапке вьюпорта."""
    bl_label = "QC Validator"
    bl_idname = "SQC_PT_header_menu"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 13

    def draw(self, context):
        _draw_menu(self.layout, context, "ARDENA", ("ARDENA",))


class SQC_PT_header_menu_met(Panel):
    """Выпадающее меню кнопки «М»: обе ветки MET, уникальная первой."""
    bl_label = "QC Validator"
    bl_idname = "SQC_PT_header_menu_met"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 13

    def draw(self, context):
        _draw_menu(self.layout, context, "MET", ("MET_Unique", "MET_LMS"))


# Кнопка на клиента: буква и её меню. Порядок тот же, что и в шапке.
BUTTONS = (
    ("SQC_PT_header_menu", 'EVENT_A'),
    ("SQC_PT_header_menu_met", 'EVENT_M'),
)


# Кнопки должны стоять в средней группе шапки, рядом с остальными инструментами студии,
# а не в самом её конце: `append` рисует после всего, то есть за режимами отображения.
# Поэтому оборачиваем `draw_xform_template` - метод, которым Blender рисует группу
# ориентации/привязок, - и дорисовываем кнопки сразу за ней. Так же устроен QC Bridge.
# Если в этой версии Blender такого метода нет, остаётся обычный `append` в конец ряда:
# флаг `_buttons_drawn` следит, чтобы кнопки не нарисовались дважды.
_buttons_drawn = False
_xform_original = None


def _draw_button(layout):
    global _buttons_drawn
    if _buttons_drawn:
        return
    row = layout.row(align=True)
    for panel, icon in BUTTONS:
        row.popover(panel=panel, text="", icon=icon)
    _buttons_drawn = True


def _header_begin(self, context):
    """Перед отрисовкой шапки: сбросить отметку этого прохода."""
    global _buttons_drawn
    _buttons_drawn = False


def _header_end(self, context):
    """После отрисовки шапки: нарисовать кнопки, если их никто не нарисовал раньше."""
    _draw_button(self.layout)


def _xform_wrapped(layout, context):
    _xform_original(layout, context)
    _draw_button(layout)


def install():
    import bpy
    global _xform_original
    header = bpy.types.VIEW3D_HT_header
    header.prepend(_header_begin)
    header.append(_header_end)
    original = getattr(header, "draw_xform_template", None)
    if callable(original) and _xform_original is None:
        _xform_original = original
        header.draw_xform_template = staticmethod(_xform_wrapped)


def remove():
    import bpy
    global _xform_original
    header = bpy.types.VIEW3D_HT_header
    for handler in (_header_begin, _header_end):
        try:
            header.remove(handler)
        except Exception:
            pass
    if _xform_original is not None:
        current = getattr(header, "draw_xform_template", None)
        # чужую обёртку поверх нашей не трогаем: она восстановит своё сама
        if getattr(current, "__name__", "") == "_xform_wrapped":
            header.draw_xform_template = staticmethod(_xform_original)
        _xform_original = None
