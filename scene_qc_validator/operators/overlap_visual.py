"""Toggle wrapper for the UDIM 1001 UV-overlap review overlay.

Orchestrates selection/mode around :mod:`checks.mapping.overlapped_uv`; the
shared :mod:`operators.uv_review_session` owns entering Edit Mode and restoring
the artist's state when the last overlay is switched off.
"""

from dataclasses import dataclass

import bpy
from bpy.types import Operator

from ..checks.mapping import overlapped_uv
from . import uv_review_session


@dataclass
class _OverlapReviewRuntime:
    active: bool = False
    source: str = ""
    target_object_name: str = ""
    target_uv_layer_name: str = ""


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


def restore_overlap_review(context):
    overlapped_uv.disable_overlap_visual()
    uv_review_session.stop_following_active_material('OVERLAP')
    restored = uv_review_session.release(context, 'OVERLAP')
    _overlap_review.active = False
    _overlap_review.source = ""
    _overlap_review.target_object_name = ""
    _overlap_review.target_uv_layer_name = ""
    return restored


def _begin_overlap_review(
    context,
    source_object,
    targets,
    source,
    uv_layer_names=None,
    material=None,
):
    if _overlap_review.active:
        restore_overlap_review(context)
    elif overlapped_uv.is_overlap_visual_enabled():
        overlapped_uv.disable_overlap_visual()

    try:
        uv_review_session.enter_review_edit(
            context, 'OVERLAP', source_object, targets, uv_layer_names
        )
        # One material is one texture set: keeping both the UV Editor and the
        # overlap test on its faces stops a second material's islands from
        # showing up beside them or counting as overlapping them.
        material_slots = uv_review_session.material_slot_map(
            targets, material
        )
        if material is not None:
            uv_review_session.isolate_material_faces(context, material)
        uv_layer = source_object.data.uv_layers.active
        if uv_layer is None:
            raise RuntimeError("Active mesh has no UV map")
        if not overlapped_uv.enable_overlap_visual(
            source_object, uv_layer.name, material_slots
        ):
            raise RuntimeError("Could not enable overlap visual")

        _overlap_review.active = True
        _overlap_review.source = source
        _overlap_review.target_object_name = source_object.name
        _overlap_review.target_uv_layer_name = uv_layer.name
        uv_review_session.follow_active_material(
            'OVERLAP', source_object, material, refresh_review_material
        )
        return True
    except (ReferenceError, RuntimeError) as error:
        restore_overlap_review(context)
        print(
            "[Scene QC Validator] Overlap review start "
            f"failed: {error}"
        )
        return False


def begin_material_overlap_review(
    context, source_object, uv_set_number
):
    (
        matching_targets,
        uv_layer_names,
        material,
        error,
    ) = uv_review_session.material_review_targets(
        context, source_object, uv_set_number
    )
    if error:
        return False, error
    if not _begin_overlap_review(
        context,
        source_object,
        matching_targets,
        'MATERIAL',
        uv_layer_names,
        material,
    ):
        return False, "Could not start overlap review"
    return True, (
        f"Reviewing {material.name} on {len(matching_targets)} "
        f"object(s) using UV set {uv_set_number}"
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
    # A multi-material mesh is reviewed one texture set at a time, so a single
    # object review still follows the active material slot.
    material = uv_review_session.multi_material_scope(source_object)
    if not _begin_overlap_review(
        context,
        source_object,
        [source_object],
        'OBJECT',
        {source_object.name: uv_layer_name},
        material,
    ):
        return False, "Could not start overlap review"
    subject = (
        f"{source_object.name} / {material.name}"
        if material is not None
        else source_object.name
    )
    return True, f"Reviewing {subject} using UV set {uv_set_number}"


def refresh_review_material(context, material):
    """Re-aim the running review at the object's newly active material slot.

    Stays inside the open Edit Mode whenever the same meshes carry the new
    material; only a different set of material users forces a restart.
    """
    if not _overlap_review.active or _overlap_review.source == 'RESULT':
        return
    source_object = context.scene.objects.get(
        _overlap_review.target_object_name
    )
    if source_object is None or source_object.type != 'MESH':
        return
    uv_set_number = (
        context.scene.sqc_settings.overlap_visual_uv_set_number
    )
    if _overlap_review.source == 'MATERIAL':
        targets, _names, _material, error = (
            uv_review_session.material_review_targets(
                context, source_object, uv_set_number
            )
        )
        if error:
            restore_overlap_review(context)
            return
    else:
        targets = [source_object]

    material_slots = uv_review_session.rescope_material(
        context, targets, material
    )
    if material_slots is None:
        begin_review = (
            begin_material_overlap_review
            if _overlap_review.source == 'MATERIAL'
            else begin_object_overlap_review
        )
        begin_review(context, source_object, uv_set_number)
        return
    overlapped_uv.rescope_overlap_visual(material_slots)
    uv_review_session.follow_active_material(
        'OVERLAP', source_object, material, refresh_review_material
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
    bl_description = (
        "Review UDIM 1001 UV overlaps. On a multi-material mesh it covers "
        "the active material slot and follows it when you pick another"
    )

    def execute(self, context):
        obj = context.active_object
        if _overlap_review.active:
            # Treat a click with another active mesh as a direct hand-off:
            # restore the old temporary review, then immediately start the
            # requested object's review.  Clicking the same object remains a
            # normal toggle-off action.
            if (
                obj is None
                or obj.type != 'MESH'
                or obj.name == _overlap_review.target_object_name
            ):
                restore_overlap_review(context)
                return {'FINISHED'}
            requested_object_name = obj.name
            restore_overlap_review(context)
            obj = context.scene.objects.get(requested_object_name)

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
