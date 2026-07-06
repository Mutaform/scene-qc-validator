import bpy
from bpy.types import Operator

from .core import _refresh_pass_state, _set_result_muted, _settings


class SQC_OT_toggle_result_mute(Operator):
    bl_idname = "sqc.toggle_result_mute"
    bl_label = "Ignore Issue"
    bl_description = "Ignore or restore this issue for this object"

    result_index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        s = _settings(context)
        idx = self.result_index if self.result_index >= 0 else s.active_result_index
        if idx < 0 or idx >= len(s.results):
            return {'CANCELLED'}
        r = s.results[idx]
        _set_result_muted(s, r, not r.muted)
        _refresh_pass_state(s)
        state = "Ignored" if r.muted else "Restored"
        self.report({'INFO'}, f"{state}: {r.check_label} on {r.object_name}")
        return {'FINISHED'}
