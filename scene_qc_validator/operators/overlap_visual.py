from dataclasses import dataclass, field

import bpy
from bpy.types import Operator

from ..checks.mapping import overlapped_uv


@dataclass
class _OverlapReviewSnapshot:
    active_object_name: str = ""
    selected_object_names: tuple = ()
    mode: str = 'OBJECT'
    uv_select_sync: bool = False
    edit_selection: dict = field(default_factory=dict)
    active_uv_layers: dict = field(default_factory=dict)


@dataclass
class _OverlapReviewRuntime:
    active: bool = False
    source: str = ""
    target_object_name: str = ""
    target_uv_layer_name: str = ""
    snapshot: _OverlapReviewSnapshot | None = None


_overlap_review = _OverlapReviewRuntime()


def is_overlap_review_active():
    return _overlap_review.active


def is_overlap_result_active(object_name, uv_layer_name):
    return (
        _overlap_review.active
        and _overlap_review.source == 'RESULT'
        and _overlap_review.target_object_name == object_name
        and _overlap_review.target_uv_layer_name == uv_layer_name
    )


def _capture_review_snapshot(context, review_targets):
    active_object = context.active_object
    edit_selection = {}
    if active_object and active_object.mode == 'EDIT':
        edit_selection = {
            obj.name: overlapped_uv._OverlapSelectionState.capture(
                obj
            )
            for obj in context.objects_in_mode_unique_data
            if obj.type == 'MESH'
        }
    return _OverlapReviewSnapshot(
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


def restore_overlap_review(context):
    snapshot = _overlap_review.snapshot
    overlapped_uv.disable_overlap_visual()
    if snapshot is None:
        _overlap_review.active = False
        _overlap_review.source = ""
        _overlap_review.target_object_name = ""
        _overlap_review.target_uv_layer_name = ""
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
            "[Scene QC Validator] Overlap review restore "
            f"failed: {error}"
        )
        return False
    finally:
        _overlap_review.active = False
        _overlap_review.source = ""
        _overlap_review.target_object_name = ""
        _overlap_review.target_uv_layer_name = ""
        _overlap_review.snapshot = None


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


def _begin_overlap_review(
    context,
    source_object,
    targets,
    source,
    uv_layer_names=None,
):
    if _overlap_review.active:
        restore_overlap_review(context)
    elif overlapped_uv.is_overlap_visual_enabled():
        overlapped_uv.disable_overlap_visual()

    # An overlap review and a padding review both drive mode/selection with
    # their own snapshots, so only one may run at a time.
    from . import padding_visual
    if padding_visual.is_padding_review_active():
        padding_visual.restore_padding_review(context)

    snapshot = _capture_review_snapshot(context, targets)
    try:
        _set_object_mode(context)
        _deselect_all_objects(context)
        for obj in targets:
            target_uv_layer_name = (
                uv_layer_names.get(obj.name, "")
                if uv_layer_names
                else ""
            )
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

        source_uv_layer_name = (
            uv_layer_names.get(source_object.name, "")
            if uv_layer_names
            else ""
        )
        uv_layer = (
            source_object.data.uv_layers.get(source_uv_layer_name)
            if source_uv_layer_name
            else source_object.data.uv_layers.active
        )
        if uv_layer is None:
            raise RuntimeError("Active mesh has no UV map")
        if not overlapped_uv.enable_overlap_visual(
            source_object, uv_layer.name
        ):
            raise RuntimeError("Could not enable overlap visual")

        _overlap_review.active = True
        _overlap_review.source = source
        _overlap_review.target_object_name = source_object.name
        _overlap_review.target_uv_layer_name = uv_layer.name
        _overlap_review.snapshot = snapshot
        return True
    except (ReferenceError, RuntimeError) as error:
        _overlap_review.snapshot = snapshot
        restore_overlap_review(context)
        print(
            "[Scene QC Validator] Overlap review start "
            f"failed: {error}"
        )
        return False


def begin_material_overlap_review(
    context, source_object, uv_set_number
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
    if not _begin_overlap_review(
        context,
        source_object,
        matching_targets,
        'MATERIAL',
        uv_layer_names,
    ):
        return False, "Could not start overlap review"
    return True, (
        f"Reviewing {len(matching_targets)} object(s) using "
        f"UV set {uv_set_number}"
    )


def begin_object_overlap_review(
    context, source_object, uv_set_number
):
    uv_layer_index = uv_set_number - 1
    if len(source_object.data.uv_layers) <= uv_layer_index:
        return False, (
            f"UV set {uv_set_number} is missing on the active mesh"
        )
    uv_layer_name = source_object.data.uv_layers[
        uv_layer_index
    ].name
    if not _begin_overlap_review(
        context,
        source_object,
        [source_object],
        'OBJECT',
        {source_object.name: uv_layer_name},
    ):
        return False, "Could not start overlap review"
    return True, (
        f"Reviewing {source_object.name} using "
        f"UV set {uv_set_number}"
    )


def refresh_material_overlap_review(context, uv_set_number):
    if (
        not _overlap_review.active
        or _overlap_review.source != 'MATERIAL'
    ):
        return True

    source_object = context.scene.objects.get(
        _overlap_review.target_object_name
    )
    if (
        source_object is None
        or source_object.type != 'MESH'
        or len(source_object.data.uv_layers) < uv_set_number
    ):
        return False

    success, _message = begin_material_overlap_review(
        context,
        source_object,
        uv_set_number,
    )
    return success


def toggle_result_overlap_review(
    context, source_object, uv_layer_name
):
    if is_overlap_result_active(
        source_object.name, uv_layer_name
    ):
        return restore_overlap_review(context)
    if _overlap_review.active:
        restore_overlap_review(context)
    return _begin_overlap_review(
        context,
        source_object,
        [source_object],
        'RESULT',
        {source_object.name: uv_layer_name},
    )


def unregister_overlap_review():
    if _overlap_review.active:
        restore_overlap_review(bpy.context)


class SQC_OT_toggle_overlap_visual(Operator):
    bl_idname = "sqc.toggle_overlap_visual"
    bl_label = "Show Overlaps"
    bl_description = "Review UDIM 1001 UV overlaps"

    def execute(self, context):
        if _overlap_review.active:
            restore_overlap_review(context)
            return {'FINISHED'}

        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}

        settings = context.scene.sqc_settings
        begin_review = (
            begin_material_overlap_review
            if settings.overlap_visual_use_material_scope
            else begin_object_overlap_review
        )
        success, message = begin_review(
            context,
            obj,
            settings.overlap_visual_uv_set_number,
        )
        self.report(
            {'INFO'} if success else {'WARNING'},
            message,
        )
        return {'FINISHED'} if success else {'CANCELLED'}
