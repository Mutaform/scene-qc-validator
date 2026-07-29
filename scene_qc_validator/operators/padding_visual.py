"""Material-driven review wrapper for the UV padding preview.

Mirrors :mod:`operators.overlap_visual`: one click gathers every visible mesh
that uses the active object's material, snapshots the current scene state,
enters multi-object Edit Mode with everything selected, and turns on the
padding overlay. Clicking again restores the captured state. The padding
geometry/lifecycle in :mod:`checks.mapping.padding` is left untouched — this
module only orchestrates selection and mode around its enable/disable API.
"""

from dataclasses import dataclass, field

import bpy
from bpy.types import Operator

from ..checks.mapping import overlapped_uv
from ..checks.mapping import padding


@dataclass
class _PaddingReviewSnapshot:
    active_object_name: str = ""
    selected_object_names: tuple = ()
    mode: str = 'OBJECT'
    uv_select_sync: bool = False
    edit_selection: dict = field(default_factory=dict)
    active_uv_layers: dict = field(default_factory=dict)


@dataclass
class _PaddingReviewRuntime:
    active: bool = False
    source_object_name: str = ""
    snapshot: _PaddingReviewSnapshot | None = None


_padding_review = _PaddingReviewRuntime()


def is_padding_review_active():
    return _padding_review.active


def _capture_review_snapshot(context, review_targets):
    active_object = context.active_object
    edit_selection = {}
    if active_object and active_object.mode == 'EDIT':
        edit_selection = {
            obj.name: overlapped_uv._OverlapSelectionState.capture(obj)
            for obj in context.objects_in_mode_unique_data
            if obj.type == 'MESH'
        }
    return _PaddingReviewSnapshot(
        active_object_name=(
            active_object.name if active_object else ""
        ),
        selected_object_names=tuple(
            obj.name for obj in context.selected_objects
        ),
        mode=active_object.mode if active_object else 'OBJECT',
        uv_select_sync=(
            context.scene.tool_settings.use_uv_select_sync
        ),
        edit_selection=edit_selection,
        active_uv_layers={
            obj.name: (
                obj.data.uv_layers.active.name
                if obj.data.uv_layers.active is not None
                else ""
            )
            for obj in review_targets
            if obj.type == 'MESH'
        },
    )


def _set_object_mode(context):
    active_object = context.active_object
    if active_object and active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def _deselect_all_objects(context):
    for obj in list(context.selected_objects):
        obj.select_set(False)


def _material_review_targets(context, source_object):
    material = source_object.active_material
    if material is None:
        return [], None
    targets = [
        obj
        for obj in context.scene.objects
        if (
            obj.type == 'MESH'
            and obj.visible_get(view_layer=context.view_layer)
            and obj.data.uv_layers.active is not None
            and any(
                slot.material == material
                for slot in obj.material_slots
            )
        )
    ]
    return targets, material


def restore_padding_review(context):
    snapshot = _padding_review.snapshot
    padding.disable_padding_visual()
    if snapshot is None:
        _padding_review.active = False
        _padding_review.source_object_name = ""
        return True

    try:
        _set_object_mode(context)
        _deselect_all_objects(context)

        selected_objects = []
        for object_name in snapshot.selected_object_names:
            obj = context.scene.objects.get(object_name)
            if obj is not None and obj.name in context.view_layer.objects:
                obj.select_set(True)
                selected_objects.append(obj)

        active_object = context.scene.objects.get(
            snapshot.active_object_name
        )
        if (
            active_object is not None
            and active_object.name in context.view_layer.objects
        ):
            context.view_layer.objects.active = active_object
            if active_object not in selected_objects:
                active_object.select_set(True)

            if snapshot.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=snapshot.mode)
                if snapshot.mode == 'EDIT':
                    for obj in context.objects_in_mode_unique_data:
                        selection = snapshot.edit_selection.get(
                            obj.name
                        )
                        if selection is not None:
                            overlapped_uv._OverlapSelectionState.restore(
                                obj, selection
                            )

        context.scene.tool_settings.use_uv_select_sync = (
            snapshot.uv_select_sync
        )
        for object_name, uv_layer_name in (
            snapshot.active_uv_layers.items()
        ):
            obj = context.scene.objects.get(object_name)
            if obj is None or obj.type != 'MESH':
                continue
            uv_layer = obj.data.uv_layers.get(uv_layer_name)
            if uv_layer is not None:
                obj.data.uv_layers.active = uv_layer
        return True
    except (ReferenceError, RuntimeError) as error:
        print(
            "[Scene QC Validator] Padding review restore "
            f"failed: {error}"
        )
        return False
    finally:
        _padding_review.active = False
        _padding_review.source_object_name = ""
        _padding_review.snapshot = None


def _begin_padding_review(
    context,
    source_object,
    targets,
    uv_layer_names,
    padding_px,
    texture_size,
):
    if _padding_review.active:
        restore_padding_review(context)
    elif padding.is_padding_visual_enabled():
        padding.disable_padding_visual()

    # A padding review and an overlap review both drive mode/selection with
    # their own snapshots, so only one may run at a time.
    from . import overlap_visual
    if overlap_visual.is_overlap_review_active():
        overlap_visual.restore_overlap_review(context)

    snapshot = _capture_review_snapshot(context, targets)
    try:
        _set_object_mode(context)
        _deselect_all_objects(context)
        for obj in targets:
            target_uv_layer_name = uv_layer_names.get(obj.name, "")
            target_uv_layer = (
                obj.data.uv_layers.get(target_uv_layer_name)
                if target_uv_layer_name
                else obj.data.uv_layers.active
            )
            if target_uv_layer is None:
                raise RuntimeError(
                    "The requested UV set is missing on a mesh"
                )
            obj.data.uv_layers.active = target_uv_layer
            obj.select_set(True)
        context.view_layer.objects.active = source_object

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.select_all(action='SELECT')
        if bpy.ops.uv.select_all.poll():
            bpy.ops.uv.select_all(action='SELECT')

        if not padding.enable_padding_visual(
            context, padding_px, texture_size
        ):
            raise RuntimeError("Could not enable padding visual")

        _padding_review.active = True
        _padding_review.source_object_name = source_object.name
        _padding_review.snapshot = snapshot
        return True
    except (ReferenceError, RuntimeError) as error:
        _padding_review.snapshot = snapshot
        restore_padding_review(context)
        print(
            "[Scene QC Validator] Padding review start "
            f"failed: {error}"
        )
        return False


def begin_material_padding_review(
    context, source_object, uv_set_number, padding_px, texture_size
):
    targets, material = _material_review_targets(
        context, source_object
    )
    if material is None:
        return False, "Active object has no active material"
    if not targets:
        return False, (
            "No visible UV meshes use the active material"
        )
    uv_layer_index = uv_set_number - 1
    if len(source_object.data.uv_layers) <= uv_layer_index:
        return False, (
            f"UV set {uv_set_number} is missing on the active mesh"
        )
    matching_targets = [
        obj for obj in targets
        if len(obj.data.uv_layers) > uv_layer_index
    ]
    if not matching_targets:
        return False, (
            f"UV set {uv_set_number} is missing on all visible "
            "material users"
        )
    uv_layer_names = {
        obj.name: obj.data.uv_layers[uv_layer_index].name
        for obj in matching_targets
    }
    if not _begin_padding_review(
        context,
        source_object,
        matching_targets,
        uv_layer_names,
        padding_px,
        texture_size,
    ):
        return False, "Could not start padding review"
    return True, (
        f"Previewing padding on {len(matching_targets)} object(s) "
        f"using UV set {uv_set_number}"
    )


def begin_object_padding_review(
    context, source_object, uv_set_number, padding_px, texture_size
):
    uv_layer_index = uv_set_number - 1
    if len(source_object.data.uv_layers) <= uv_layer_index:
        return False, (
            f"UV set {uv_set_number} is missing on the active mesh"
        )
    uv_layer_name = source_object.data.uv_layers[
        uv_layer_index
    ].name
    if not _begin_padding_review(
        context,
        source_object,
        [source_object],
        {source_object.name: uv_layer_name},
        padding_px,
        texture_size,
    ):
        return False, "Could not start padding review"
    return True, (
        f"Previewing padding on {source_object.name} using "
        f"UV set {uv_set_number}"
    )


def unregister_padding_review():
    if _padding_review.active:
        restore_padding_review(bpy.context)


def _padding_check_item(context):
    return next(
        (
            check
            for check in context.scene.sqc_settings.checks
            if check.check_id == "uv_padding"
        ),
        None,
    )


class SQC_OT_TogglePaddingVisual(Operator):
    bl_idname = "sqc.toggle_padding_visual"
    bl_label = "Show Padding"
    bl_description = "Preview UV-island padding in the UV Editor"

    def execute(self, context):
        if _padding_review.active:
            restore_padding_review(context)
            return {'FINISHED'}

        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}

        item = _padding_check_item(context)
        padding_px = item.int_param_1 if item else 16
        texture_size = item.int_param_2 if item else 4096
        settings = context.scene.sqc_settings
        begin_review = (
            begin_material_padding_review
            if settings.padding_visual_use_material_scope
            else begin_object_padding_review
        )
        success, message = begin_review(
            context,
            obj,
            settings.overlap_visual_uv_set_number,
            padding_px,
            texture_size,
        )
        self.report(
            {'INFO'} if success else {'WARNING'},
            message,
        )
        return {'FINISHED'} if success else {'CANCELLED'}
