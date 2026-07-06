import bpy
from bpy.types import Operator

from .core import (
    _scope_empty_message,
    _settings,
    checks_mod,
    ensure_checks_initialized,
    run_validation_logic,
)


class SQC_OT_init_checks(Operator):
    bl_idname = "sqc.init_checks"
    bl_label = "Initialize Checklist"

    def execute(self, context):
        ensure_checks_initialized(context)
        return {'FINISHED'}


class SQC_OT_select_all_checks(Operator):
    bl_idname = "sqc.select_all_checks"
    bl_label = "Select All"
    enable: bpy.props.BoolProperty(default=True)
    current_tab_only: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        s = _settings(context)
        if self.current_tab_only:
            allowed = checks_mod.TAB_CATEGORY_MAP.get(s.checklist_tab, set())
            for c in s.checks:
                if c.category in allowed:
                    c.enabled = self.enable
        else:
            for c in s.checks:
                c.enabled = self.enable
        return {'FINISHED'}


class SQC_OT_run_validate(Operator):
    bl_idname = "sqc.run_validate"
    bl_label = "Validate"
    bl_description = "Run enabled checks against the configured validation scope"

    def execute(self, context):
        targets_found, any_fail = run_validation_logic(context)
        if not targets_found:
            self.report({'WARNING'}, _scope_empty_message(_settings(context).validation_scope))
            return {'CANCELLED'}
        if any_fail:
            self.report({'WARNING'}, "Validation found blocking issues")
        else:
            self.report({'INFO'}, "Validation passed")
        return {'FINISHED'}
