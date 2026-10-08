# -*- coding: utf-8 -*-
"""Кнопка проверки в шапке 3D-вьюпорта.

Художник проверяет ассет десятки раз за день, а боковая панель чаще закрыта.
Кнопка в шапке даёт три действия в один клик - по кнопке на этап активного
проекта - и сразу открывает сводку в браузере.
"""

from bpy.types import Panel

from .. import presets as presets_mod
from .checklist_panel import _stage_button_text
from .helpers import addon_version


class SQC_PT_header_menu(Panel):
    """Выпадающее меню кнопки «А» в шапке вьюпорта."""
    bl_label = "QC Validator"
    bl_idname = "SQC_PT_header_menu"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 13

    def draw(self, context):
        layout = self.layout
        settings = context.scene.sqc_settings

        title = layout.row(align=True)
        title.label(text="QC Validator", icon='CHECKMARK')
        version = title.row(align=True)
        version.alignment = 'RIGHT'
        version.enabled = False
        version.label(text=f"ver {addon_version()}")

        if not len(settings.checks):
            layout.operator("sqc.init_checks", text="Initialize Checklist", icon='FILE_REFRESH')
            return

        layout.prop(settings, "validation_scope", text="")

        project = settings.active_project_name
        stages = presets_mod.project_stage_names(project)
        box = layout.column(align=True)
        box.label(text=project or "No project", icon='PRESET')
        if not stages:
            box.label(text="No stages in project", icon='INFO')
        else:
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

        layout.separator()
        layout.operator("sqc.open_report", text="Open Last Report", icon='URL')


# Кнопка должна стоять в средней группе шапки, рядом с остальными инструментами студии,
# а не в самом её конце: `append` рисует после всего, то есть за режимами отображения.
# Поэтому оборачиваем `draw_xform_template` - метод, которым Blender рисует группу
# ориентации/привязок, - и дорисовываем кнопку сразу за ней. Так же устроен QC Bridge.
# Если в этой версии Blender такого метода нет, остаётся обычный `append` в конец ряда:
# флаг `_button_drawn` следит, чтобы кнопка не нарисовалась дважды.
_button_drawn = False
_xform_original = None


def _draw_button(layout):
    global _button_drawn
    if _button_drawn:
        return
    layout.popover(panel="SQC_PT_header_menu", text="", icon='EVENT_A')
    _button_drawn = True


def _header_begin(self, context):
    """Перед отрисовкой шапки: сбросить отметку этого прохода."""
    global _button_drawn
    _button_drawn = False


def _header_end(self, context):
    """После отрисовки шапки: нарисовать кнопку, если её никто не нарисовал раньше."""
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
