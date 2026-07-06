from bpy.types import Panel

from .constants import SEVERITY_ICON
from .helpers import addon_version, result_visible


class SQC_PT_results(Panel):
    """Sub-panel: validation results list and per-issue actions."""
    bl_label = "Results"
    bl_idname = "SQC_PT_results"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "QC Validator"
    bl_parent_id = "SQC_PT_main"
    bl_order = 30
    bl_options = set()

    @classmethod
    def poll(cls, context):
        return len(context.scene.sqc_settings.checks) > 0

    def draw(self, context):
        layout = self.layout
        s = context.scene.sqc_settings

        if not s.has_run_validation:
            layout.label(text="Run Validate to see results here", icon='INFO')
            return

        row = layout.row(align=True)
        row.prop(s, "result_filter", text="")
        has_fixable = any(r.can_fix for r in s.results)
        if has_fixable:
            row.operator("sqc.fix_all", text="Fix All", icon='TOOL_SETTINGS')

        if len(s.results) == 0:
            row = layout.row(align=True)
            split = row.split(factor=0.58, align=True)
            split.label(text="No issues found", icon='CHECKMARK')
            version = split.row(align=True)
            version.alignment = 'RIGHT'
            version.enabled = False
            version.label(text=f"ver - {addon_version()}")
            return

        filtered_count = self._filtered_indices(s)
        layout.label(text=f"{len(filtered_count)} issue(s) shown")
        layout.template_list("SQC_UL_results", "", s, "results", s, "active_result_index", rows=8)

        if 0 <= s.active_result_index < len(s.results):
            r = s.results[s.active_result_index]
            info = layout.box()
            info_row = info.row()
            info_row.alert = (r.severity == 'FAIL' and not r.muted)
            info_row.label(text=r.message, icon='HIDE_ON' if r.muted else SEVERITY_ICON.get(r.severity, 'DOT'))
            row = info.row(align=True)
            mute_op = row.operator("sqc.toggle_result_mute", text="Restore" if r.muted else "Ignore", icon='HIDE_OFF' if r.muted else 'HIDE_ON')
            mute_op.result_index = s.active_result_index
            row.operator("sqc.select_result", text="Select", icon='RESTRICT_SELECT_OFF')
            if r.can_fix and not r.muted:
                fix_op = row.operator("sqc.fix_result", text="Fix Me", icon='TOOL_SETTINGS')
                fix_op.result_index = s.active_result_index

    def _filtered_indices(self, s):
        return [i for i, r in enumerate(s.results) if result_visible(s, r)]
