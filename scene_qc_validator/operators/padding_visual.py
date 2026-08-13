"""Toggle wrapper for the UV-padding preview overlay.

Orchestrates selection/mode around :mod:`checks.mapping.padding`; the shared
:mod:`operators.uv_review_session` owns entering Edit Mode and restoring the
artist's state when the last overlay is switched off. The padding
geometry/lifecycle in :mod:`checks.mapping.padding` is left untouched.
"""

from dataclasses import dataclass

import bpy
from bpy.types import Operator

from ..checks.mapping import padding
from . import uv_review_session


@dataclass
class _PaddingReviewRuntime:
    active: bool = False
    source_object_name: str = ""


_padding_review = _PaddingReviewRuntime()


def is_padding_review_active():
    return _padding_review.active


def restore_padding_review(context):
    padding.disable_padding_visual()
    restored = uv_review_session.release(context, 'PADDING')
    _padding_review.active = False
    _padding_review.source_object_name = ""
    return restored


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

    try:
        uv_review_session.enter_review_edit(
            context, 'PADDING', source_object, targets, uv_layer_names
        )
        if not padding.enable_padding_visual(
            context, padding_px, texture_size
        ):
            raise RuntimeError("Could not enable padding visual")

        _padding_review.active = True
        _padding_review.source_object_name = source_object.name
        return True
    except (ReferenceError, RuntimeError) as error:
        restore_padding_review(context)
        print(
            "[Scene QC Validator] Padding review start "
            f"failed: {error}"
        )
        return False


def begin_material_padding_review(
    context, source_object, uv_set_number, padding_px, texture_size
):
    targets, material = uv_review_session.material_targets(
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
        obj = context.active_object
        if _padding_review.active:
            if (
                obj is None
                or obj.type != 'MESH'
                or obj.name == _padding_review.source_object_name
            ):
                restore_padding_review(context)
                return {'FINISHED'}
            requested_object_name = obj.name
            restore_padding_review(context)
            obj = context.scene.objects.get(requested_object_name)

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
