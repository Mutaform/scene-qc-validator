"""Material-driven UV review for the Review Scene material list.

Clicking a material selects every scope mesh that uses it and isolates that
material's faces in multi-object Edit Mode, so the UV editor shows this
material's UVs alone instead of every UV of the meshes it happens to share
with other materials. The shared :mod:`operators.uv_review_session` owns the
artist-state snapshot, so switching the isolation back off returns selection,
mode and UV sync to where they were.
"""

from dataclasses import dataclass

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from .core import _validation_targets
from . import uv_review_session


REVIEW_KIND = 'MATERIAL_UV'


@dataclass
class _MaterialUVReviewRuntime:
    material_name: str = ""
    mesh_select_mode: tuple = ()
    scope_object_names: tuple = ()


_review = _MaterialUVReviewRuntime()


def isolated_material_name(context):
    """Name of the material whose faces are isolated right now, else "".

    Leaving Edit Mode by hand ends the review as far as the panel is
    concerned - the face selection is the whole point of the isolation.
    """
    if not _review.material_name or context.mode != 'EDIT_MESH':
        return ""
    return _review.material_name


def review_scope_objects(context):
    """Mesh objects the Review Scene panel should describe.

    While an isolation runs the selection is our own doing, so the panel keeps
    listing the objects that were in scope when the review started - otherwise
    a 'Selection' scope would collapse onto the isolated material's users and
    the artist could not hop to the next material in the list.
    """
    if isolated_material_name(context) and _review.scope_object_names:
        objects = [
            context.scene.objects.get(name)
            for name in _review.scope_object_names
        ]
        return [
            obj for obj in objects
            if obj is not None and obj.type == 'MESH'
        ]
    return _validation_targets(context)


def _uses_material(obj, material):
    return any(slot.material == material for slot in obj.material_slots)


def _editable_targets(context, material, scope_objects):
    """Scope meshes using ``material`` that Edit Mode can actually reach.

    Returns ``(targets, skipped)``; ``skipped`` counts users that are hidden,
    unselectable or outside the view layer.
    """
    targets = []
    skipped = 0
    for obj in scope_objects:
        if not _uses_material(obj, material):
            continue
        if (
            obj.name not in context.view_layer.objects
            or not obj.visible_get(view_layer=context.view_layer)
            or obj.hide_select
        ):
            skipped += 1
            continue
        targets.append(obj)
    return targets, skipped


def stop_isolation(context):
    """End the review and hand the scene back to the artist untouched."""
    mesh_select_mode = _review.mesh_select_mode
    _review.material_name = ""
    _review.mesh_select_mode = ()
    _review.scope_object_names = ()
    restored = uv_review_session.release(context, REVIEW_KIND)
    if mesh_select_mode:
        context.scene.tool_settings.mesh_select_mode = mesh_select_mode
    return restored


def _start_isolation(context, material, targets, scope_objects):
    """Put ``targets`` into Edit Mode with only ``material``'s faces selected.

    Snapshots the artist's state on the first material of a review session;
    hopping to another material afterwards keeps that original snapshot.
    """
    if not isolated_material_name(context):
        uv_review_session.acquire(context, REVIEW_KIND)
        _review.mesh_select_mode = tuple(
            context.scene.tool_settings.mesh_select_mode
        )
        _review.scope_object_names = tuple(
            obj.name for obj in scope_objects
        )

    active = context.active_object
    if active and active.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(context.selected_objects):
        obj.select_set(False)
    for obj in targets:
        obj.select_set(True)
        uv_review_session.activate_material_slot(obj, material)
    context.view_layer.objects.active = targets[0]

    bpy.ops.object.mode_set(mode='EDIT')
    face_count = uv_review_session.isolate_material_faces(
        context, material
    )
    _review.material_name = material.name
    return face_count


class SQC_OT_select_material_users(Operator):
    bl_idname = "sqc.select_material_users"
    bl_label = "Review Material UVs"
    bl_description = (
        "Select the scope meshes that use this material and isolate its faces "
        "in Edit Mode, so the UV editor shows this material's UVs alone. "
        "Click again to restore the previous selection"
    )

    material_name: StringProperty()

    def execute(self, context):
        material = bpy.data.materials.get(self.material_name)
        if material is None:
            self.report({'WARNING'}, "Material no longer exists")
            return {'CANCELLED'}

        if isolated_material_name(context) == material.name:
            stop_isolation(context)
            self.report({'INFO'}, f"Ended UV review of {material.name}")
            return {'FINISHED'}

        scope_objects = review_scope_objects(context)
        targets, skipped = _editable_targets(
            context, material, scope_objects
        )
        if not targets:
            self.report(
                {'WARNING'},
                "No editable object in the current scope uses this material",
            )
            return {'CANCELLED'}

        try:
            face_count = _start_isolation(
                context, material, targets, scope_objects
            )
        except (ReferenceError, RuntimeError) as error:
            stop_isolation(context)
            self.report(
                {'WARNING'},
                f"Could not review {material.name}: {error}",
            )
            return {'CANCELLED'}

        if not face_count:
            self.report(
                {'WARNING'},
                f"{material.name} sits in a slot but on no face",
            )
            return {'FINISHED'}

        message = (
            f"{material.name}: {face_count} face(s) "
            f"on {len(targets)} object(s)"
        )
        if skipped:
            message += f", {skipped} hidden or unselectable user(s) skipped"
        self.report({'INFO'}, message)
        return {'FINISHED'}
