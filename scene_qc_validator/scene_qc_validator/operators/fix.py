import bpy
from bpy.types import Operator

from .core import _scope_empty_message, _settings, checks_mod, run_validation_logic


class SQC_OT_fix_result(Operator):
    bl_idname = "sqc.fix_result"
    bl_label = "Fix Me"

    result_index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        s = _settings(context)
        idx = self.result_index if self.result_index >= 0 else s.active_result_index
        if idx < 0 or idx >= len(s.results):
            return {'CANCELLED'}
        r = s.results[idx]
        d = checks_mod.get_check_definition(r.check_id)
        check_item = next((c for c in s.checks if c.check_id == r.check_id), None)
        obj = context.scene.objects.get(r.object_name)
        if not (d and d.get("fix") and check_item and obj):
            self.report({'WARNING'}, "This issue has no automatic fix")
            return {'CANCELLED'}
        try:
            d["fix"](obj, check_item, r)
        except Exception as e:
            self.report({'ERROR'}, f"Fix failed: {e}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Fixed: {r.check_label} on {obj.name}")
        return {'FINISHED'}


class SQC_OT_fix_all(Operator):
    bl_idname = "sqc.fix_all"
    bl_label = "Fix All"
    bl_description = "Apply all available automatic fixes, re-validating until no fixable issues remain"

    max_passes: bpy.props.IntProperty(default=8, min=1, max=25)

    def execute(self, context):
        s = _settings(context)
        total_fixed = 0
        targets_found, any_fail = run_validation_logic(context)
        if not targets_found:
            self.report({'WARNING'}, _scope_empty_message(s.validation_scope))
            return {'CANCELLED'}

        for _pass_index in range(self.max_passes):
            fixable = [
                (i, r.object_name, r.check_id)
                for i, r in enumerate(s.results)
                if r.can_fix and not r.muted
            ]
            if not fixable:
                break

            fixed_this_pass = 0
            for _idx, object_name, check_id in fixable:
                d = checks_mod.get_check_definition(check_id)
                check_item = next((c for c in s.checks if c.check_id == check_id), None)
                obj = context.scene.objects.get(object_name)
                if not (d and d.get("fix") and check_item and obj):
                    continue
                try:
                    if d["fix"](obj, check_item, None):
                        fixed_this_pass += 1
                except Exception as ex:
                    print(f"[Scene QC Validator] Fix All failed for {check_id} on {object_name}: {ex}")

            total_fixed += fixed_this_pass
            targets_found, any_fail = run_validation_logic(context)
            if fixed_this_pass == 0:
                break

        remaining_fixable = sum(1 for r in s.results if r.can_fix and not r.muted)
        remaining_fail = sum(1 for r in s.results if r.severity == 'FAIL' and not r.muted)
        if remaining_fixable:
            self.report({'WARNING'}, f"Applied {total_fixed} fix(es). {remaining_fixable} fixable issue(s) remain.")
        elif remaining_fail:
            self.report({'INFO'}, f"Applied {total_fixed} fix(es). Non-fixable issues remain, see Results.")
        else:
            self.report({'INFO'}, f"Applied {total_fixed} fix(es). All fixable checks are clean.")
        return {'FINISHED'}
