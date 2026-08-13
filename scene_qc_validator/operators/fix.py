import bpy
from bpy.types import Operator

from .core import (
    _scope_empty_message,
    _settings,
    checks_mod,
    revalidate_object_check,
    run_validation_logic,
)
from ..checks.mapping import unaligned_uv_edges


class SQC_OT_fix_result(Operator):
    bl_idname = "sqc.fix_result"
    bl_label = "Fix Me"

    result_index: bpy.props.IntProperty(default=-1)

    _timer = None
    _object_name = ""
    _check_label = ""
    _check_item = None
    _issues = None
    _allowed_layers = None
    _texture_size = 4096
    _pass_index = 0
    _was_edit_mode = False
    _uv_snapshot = None

    def _result_context(self, context):
        settings = _settings(context)
        index = (
            self.result_index
            if self.result_index >= 0
            else settings.active_result_index
        )
        if index < 0 or index >= len(settings.results):
            return None
        result = settings.results[index]
        definition = checks_mod.get_check_definition(
            result.check_id
        )
        check_item = next(
            (
                check
                for check in settings.checks
                if check.check_id == result.check_id
            ),
            None,
        )
        obj = context.scene.objects.get(result.object_name)
        if not (
            definition
            and definition.get("fix")
            and check_item
            and obj
        ):
            return None
        return result, definition, check_item, obj

    def _redraw(self, context):
        if context.screen is None:
            return
        for area in context.screen.areas:
            area.tag_redraw()

    def _restore_mode(self, context):
        obj = context.scene.objects.get(self._object_name)
        if not obj or not self._was_edit_mode:
            return
        context.view_layer.objects.active = obj
        obj.select_set(True)
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

    def _restore_snapshot(self, context):
        obj = context.scene.objects.get(self._object_name)
        if not obj or not self._uv_snapshot:
            return
        if obj.mode != 'OBJECT':
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='OBJECT')
        for layer_name, positions in self._uv_snapshot.items():
            layer = obj.data.uv_layers.get(layer_name)
            if layer is None or len(layer.data) != len(positions):
                continue
            for loop_index, position in enumerate(positions):
                layer.data[loop_index].uv = position
        obj.data.update()

    def _finish(
        self,
        context,
        cancelled=False,
        remaining_count=0,
    ):
        settings = _settings(context)
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        context.window_manager.progress_end()

        if cancelled:
            self._restore_snapshot(context)
        self._restore_mode(context)

        settings.fix_in_progress = False
        settings.fix_progress = 0.0 if cancelled else 1.0
        settings.fix_progress_text = ""

        if not cancelled and self._check_item is not None:
            revalidate_object_check(
                context, self._object_name, self._check_item.check_id
            )
        self._redraw(context)

        if cancelled:
            self.report({'WARNING'}, "Auto-fix cancelled")
            return {'CANCELLED'}
        if remaining_count:
            self.report(
                {'WARNING'},
                (
                    f"Auto-fix stopped with {remaining_count} "
                    "UV edge(s) remaining"
                ),
            )
        else:
            self.report(
                {'INFO'},
                f"Fixed: {self._check_label} on {self._object_name}",
            )
        return {'FINISHED'}

    def invoke(self, context, _event):
        result_context = self._result_context(context)
        if result_context is None:
            self.report(
                {'WARNING'},
                "This issue has no automatic fix",
            )
            return {'CANCELLED'}
        result, _definition, check_item, obj = result_context
        if result.check_id != "uv_unaligned_edges":
            return self.execute(context)

        settings = _settings(context)
        if settings.fix_in_progress:
            self.report({'WARNING'}, "An auto-fix is already running")
            return {'CANCELLED'}

        self._object_name = obj.name
        self._check_label = result.check_label
        self._check_item = check_item
        self._issues = [{
            "message": result.message,
            "element_ref": result.element_ref,
        }]
        self._allowed_layers = {
            unaligned_uv_edges._parse_element_reference(
                result.element_ref
            ).get("uv", "")
        }
        self._allowed_layers.discard("")
        if not self._allowed_layers:
            self.report({'WARNING'}, "No UV set found in result")
            return {'CANCELLED'}

        self._was_edit_mode = obj.mode == 'EDIT'
        if self._was_edit_mode:
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='OBJECT')

        self._uv_snapshot = {}
        for layer_name in self._allowed_layers:
            layer = obj.data.uv_layers.get(layer_name)
            if layer is not None:
                self._uv_snapshot[layer_name] = [
                    (float(loop_uv.uv.x), float(loop_uv.uv.y))
                    for loop_uv in layer.data
                ]

        self._texture_size = (
            unaligned_uv_edges.unaligned_fix_texture_size()
        )
        self._pass_index = 0
        initial_count = (
            unaligned_uv_edges.unaligned_fix_issue_count(
                self._issues
            )
        )

        settings.fix_in_progress = True
        settings.fix_progress = 0.0
        settings.fix_progress_text = (
            f"Auto-fix: {initial_count} UV edge(s)"
        )
        context.window_manager.progress_begin(
            0,
            unaligned_uv_edges.MAX_FIX_PASSES,
        )
        self._timer = context.window_manager.event_timer_add(
            0.01,
            window=context.window,
        )
        context.window_manager.modal_handler_add(self)
        self._redraw(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            return self._finish(context, cancelled=True)
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        obj = context.scene.objects.get(self._object_name)
        if obj is None:
            return self._finish(context, cancelled=True)

        changed = unaligned_uv_edges.fix_unaligned_uv_edges_pass(
            obj,
            self._check_item,
            self._issues,
            self._allowed_layers,
            self._texture_size,
        )
        self._pass_index += 1
        self._issues = (
            unaligned_uv_edges.unaligned_fix_remaining_issues(
                obj,
                self._check_item,
                self._allowed_layers,
            )
        )
        remaining_count = (
            unaligned_uv_edges.unaligned_fix_issue_count(
                self._issues
            )
        )

        settings = _settings(context)
        settings.fix_progress = (
            self._pass_index
            / unaligned_uv_edges.MAX_FIX_PASSES
        )
        settings.fix_progress_text = (
            f"Pass {self._pass_index} / "
            f"{unaligned_uv_edges.MAX_FIX_PASSES}"
            f"  •  {remaining_count} edge(s) remaining"
        )
        context.window_manager.progress_update(self._pass_index)
        self._redraw(context)

        if remaining_count == 0:
            return self._finish(context)
        if (
            not changed
            or self._pass_index
            >= unaligned_uv_edges.MAX_FIX_PASSES
        ):
            return self._finish(
                context,
                remaining_count=remaining_count,
            )
        return {'RUNNING_MODAL'}

    def execute(self, context):
        result_context = self._result_context(context)
        if result_context is None:
            self.report({'WARNING'}, "This issue has no automatic fix")
            return {'CANCELLED'}
        r, d, check_item, obj = result_context
        check_id = r.check_id
        check_label = r.check_label
        object_name = obj.name
        try:
            d["fix"](obj, check_item, r)
        except Exception as e:
            self.report({'ERROR'}, f"Fix failed: {e}")
            return {'CANCELLED'}
        # Refresh just this object+check so the fixed issue leaves the list
        # right away instead of lingering until the next manual Validate.
        revalidate_object_check(context, object_name, check_id)
        self.report({'INFO'}, f"Fixed: {check_label} on {object_name}")
        return {'FINISHED'}

    def cancel(self, context):
        if _settings(context).fix_in_progress:
            self._finish(context, cancelled=True)


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
