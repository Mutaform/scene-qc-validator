import bpy
from bpy.types import UIList

from .. import checks as checks_mod
from .constants import SEVERITY_ICON, CATEGORY_ICON
from .helpers import result_visible


class SQC_UL_checklist(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        sub = row.row(align=True)
        sub.active = item.enabled
        split = sub.split(factor=0.62)
        split.label(text=item.label, icon=CATEGORY_ICON.get(item.category, 'DOT'))
        split.prop(item, "severity", text="")

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        s = context.scene.sqc_settings
        allowed = checks_mod.TAB_CATEGORY_MAP.get(s.checklist_tab, set())
        flt_flags = [
            self.bitflag_filter_item if item.category in allowed else 0
            for item in items
        ]
        flt_neworder = []
        return flt_flags, flt_neworder


class SQC_UL_results(UIList):
    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        s = context.scene.sqc_settings
        flt_flags = [
            self.bitflag_filter_item if result_visible(s, item) else 0
            for item in items
        ]
        flt_neworder = []
        return flt_flags, flt_neworder

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "muted", text="")
        row.alert = (item.severity == 'FAIL' and not item.muted)
        row.label(text="", icon='HIDE_ON' if item.muted else SEVERITY_ICON.get(item.severity, 'DOT'))
        split = row.split(factor=0.4)
        split.label(text=item.object_name)
        split.label(text=item.check_label)
        row.alert = False
        if item.can_fix and not item.muted:
            op = row.operator("sqc.fix_result", text="", icon='TOOL_SETTINGS')
            op.result_index = index
