"""Shared lifecycle for simultaneously active UV review overlays."""
from dataclasses import dataclass, field

import bmesh
import bpy

from ..checks.mapping import overlapped_uv


@dataclass
class _Snapshot:
    active_object_name: str = ""
    selected_object_names: tuple = ()
    mode: str = 'OBJECT'
    uv_select_sync: bool = False
    edit_selection: dict = field(default_factory=dict)
    active_uv_layers: dict = field(default_factory=dict)


@dataclass
class _Session:
    active_kinds: set = field(default_factory=set)
    snapshot: _Snapshot | None = None


_session = _Session()


def active_kinds():
    return frozenset(_session.active_kinds)


def acquire(context, kind):
    if kind in _session.active_kinds:
        return
    if not _session.active_kinds:
        active = context.active_object
        edit_selection = {}
        if active and active.mode == 'EDIT':
            edit_selection = {
                obj.name: overlapped_uv._OverlapSelectionState.capture(obj)
                for obj in context.objects_in_mode_unique_data
                if obj.type == 'MESH'
            }
        _session.snapshot = _Snapshot(
            active_object_name=active.name if active else "",
            selected_object_names=tuple(
                obj.name for obj in context.selected_objects
            ),
            mode=active.mode if active else 'OBJECT',
            uv_select_sync=context.scene.tool_settings.use_uv_select_sync,
            edit_selection=edit_selection,
            active_uv_layers={
                obj.name: obj.data.uv_layers.active.name
                for obj in context.scene.objects
                if obj.type == 'MESH' and obj.data.uv_layers.active
            },
        )
    _session.active_kinds.add(kind)


def release(context, kind):
    _session.active_kinds.discard(kind)
    if _session.active_kinds:
        return True
    snapshot = _session.snapshot
    _session.snapshot = None
    if snapshot is None:
        return True
    try:
        active = context.active_object
        if active and active.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(context.selected_objects):
            obj.select_set(False)
        for name in snapshot.selected_object_names:
            obj = context.scene.objects.get(name)
            if obj is not None and obj.name in context.view_layer.objects:
                obj.select_set(True)
        active = context.scene.objects.get(snapshot.active_object_name)
        if active is not None and active.name in context.view_layer.objects:
            active.select_set(True)
            context.view_layer.objects.active = active
            if snapshot.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=snapshot.mode)
                if snapshot.mode == 'EDIT':
                    for obj in context.objects_in_mode_unique_data:
                        selection = snapshot.edit_selection.get(obj.name)
                        if selection is not None:
                            overlapped_uv._OverlapSelectionState.restore(
                                obj, selection
                            )
        context.scene.tool_settings.use_uv_select_sync = (
            snapshot.uv_select_sync
        )
        for name, uv_name in snapshot.active_uv_layers.items():
            obj = context.scene.objects.get(name)
            if obj is None:
                continue
            uv_layer = obj.data.uv_layers.get(uv_name)
            if uv_layer is not None:
                obj.data.uv_layers.active = uv_layer
        return True
    except (ReferenceError, RuntimeError) as error:
        print(f"[Scene QC Validator] UV review restore failed: {error}")
        return False


def material_targets(context, source_object):
    """Every visible mesh that shares ``source_object``'s active material and
    carries an active UV map. Returns ``(targets, material)``; ``material`` is
    ``None`` when the source object has no active material."""
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


def material_review_targets(context, source_object, uv_set_number):
    """Meshes for a material-scoped review, with the UV layer each should show.

    Returns ``(targets, uv_layer_names, material, error)``; ``error`` is a
    ready-to-report message when no review can be started, and the other values
    are then empty.
    """
    targets, material = material_targets(context, source_object)
    if material is None:
        return [], {}, None, "Active object has no active material"
    if not targets:
        return [], {}, None, "No visible UV meshes use the active material"
    uv_layer_index = uv_set_number - 1
    if len(source_object.data.uv_layers) <= uv_layer_index:
        return [], {}, material, (
            f"UV set {uv_set_number} is missing on the active mesh"
        )
    matching_targets = [
        obj for obj in targets
        if len(obj.data.uv_layers) > uv_layer_index
    ]
    if not matching_targets:
        return [], {}, material, (
            f"UV set {uv_set_number} is missing on all visible "
            "material users"
        )
    uv_layer_names = {
        obj.name: obj.data.uv_layers[uv_layer_index].name
        for obj in matching_targets
    }
    return matching_targets, uv_layer_names, material, ""


# ---------------------------------------------------------------------------
# Material scope
#
# A material is a texture set: its UVs are the only ones an overlap, padding or
# texel-density review may take into account. On a mesh carrying several
# materials the other slots' islands would otherwise be measured, drawn over
# and shown in the UV Editor next to the ones under review.


def material_slot_indices(obj, material):
    """Slot indices on ``obj`` that carry ``material``."""
    return frozenset(
        index
        for index, slot in enumerate(obj.material_slots)
        if slot.material == material
    )


def multi_material_scope(obj):
    """The active material when ``obj`` carries more than one, else ``None``.

    A mesh with a single material has nothing to separate out, so its reviews
    keep covering the whole mesh exactly as they always did.
    """
    materials = {
        slot.material for slot in obj.material_slots if slot.material
    }
    if len(materials) < 2:
        return None
    return obj.active_material


def activate_material_slot(obj, material):
    """Make ``material``'s first slot the active one on ``obj``.

    The overlay reviews scope themselves to the active object's active
    material, so pointing the slot at the material the artist just picked is
    what makes a following Show Overlaps / Padding / Texel Density click
    review that same material.
    """
    for index, slot in enumerate(obj.material_slots):
        if slot.material == material:
            obj.active_material_index = index
            return True
    return False


def material_slot_map(targets, material):
    """``{object name: frozenset of slot indices}`` limiting a review to one
    material's faces, or ``None`` when there is no material to limit it to."""
    if material is None:
        return None
    return {
        obj.name: material_slot_indices(obj, material)
        for obj in targets
    }


def isolate_material_faces(context, material):
    """Leave only ``material``'s faces - and only their UVs - selected in the
    open multi-object Edit Mode.

    With UV sync selection off the UV Editor draws the UVs of selected faces
    only, so this is what keeps a review's UV Editor down to the material being
    reviewed. Returns the number of faces in scope.
    """
    context.scene.tool_settings.use_uv_select_sync = False
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='DESELECT')
    face_count = 0
    for obj in context.objects_in_mode_unique_data:
        if obj.type != 'MESH':
            continue
        slot_indices = material_slot_indices(obj, material)
        bm = bmesh.from_edit_mesh(obj.data)
        has_uv = bm.loops.layers.uv.active is not None
        for face in bm.faces:
            in_scope = face.material_index in slot_indices
            if in_scope:
                face.select_set(True)
                face_count += 1
            if has_uv:
                face.uv_select_set(in_scope)
        bmesh.update_edit_mesh(obj.data)
    return face_count


def rescope_material(context, targets, material):
    """Re-aim an open review at ``material`` without leaving Edit Mode.

    Returns the new slot map when the meshes already being edited are exactly
    ``targets``, so only the face isolation has to be redone; ``None`` when the
    object set itself changed and the caller has to restart its review.
    """
    edit_names = {
        obj.name
        for obj in context.objects_in_mode_unique_data
        if obj.type == 'MESH'
    }
    if not targets or edit_names != {obj.name for obj in targets}:
        return None
    isolate_material_faces(context, material)
    return material_slot_map(targets, material)


# ---------------------------------------------------------------------------
# Following the active material slot
#
# Picking another slot in the Properties editor (or in the Review Scene
# material list) is how an artist says "show me that texture set instead", so a
# running review re-aims itself at it. Blender has no notification for the
# active slot, hence the small poll while at least one review is open.


_MATERIAL_WATCH_INTERVAL = 0.25

# kind -> {"object": name, "material": name, "handler": callable}
_material_watch = {}
_material_watch_running = False


def follow_active_material(kind, source_object, material, handler):
    """Call ``handler(context, material)`` when ``source_object``'s active
    material slot changes while ``kind``'s review is open."""
    if material is None:
        stop_following_active_material(kind)
        return
    _material_watch[kind] = {
        "object": source_object.name,
        "material": material.name,
        "handler": handler,
    }
    _ensure_material_watch_timer()


def stop_following_active_material(kind):
    _material_watch.pop(kind, None)


def followed_material_name():
    """Material the open reviews are scoped to, or "" when none is."""
    for entry in _material_watch.values():
        return entry["material"]
    return ""


def _ensure_material_watch_timer():
    global _material_watch_running
    if _material_watch_running:
        return
    _material_watch_running = True
    bpy.app.timers.register(
        _material_watch_tick,
        first_interval=_MATERIAL_WATCH_INTERVAL,
    )


def _material_watch_tick():
    global _material_watch_running
    if not _material_watch:
        _material_watch_running = False
        return None
    context = bpy.context
    if context.mode != 'EDIT_MESH':
        return _MATERIAL_WATCH_INTERVAL
    for kind, entry in list(_material_watch.items()):
        obj = context.scene.objects.get(entry["object"])
        if obj is None or obj.type != 'MESH':
            continue
        material = obj.active_material
        if material is None or material.name == entry["material"]:
            continue
        # Record the new material before handing over: a handler that fails
        # must not be retried on every tick.
        entry["material"] = material.name
        try:
            entry["handler"](context, material)
        except (ReferenceError, RuntimeError) as error:
            print(
                "[Scene QC Validator] Could not follow the active "
                f"material for {kind}: {error}"
            )
    return _MATERIAL_WATCH_INTERVAL


def enter_review_edit(context, kind, source_object, targets, uv_layer_names=None):
    """Acquire the shared session and put ``targets`` into multi-object Edit
    Mode with ``source_object`` active and each target's chosen UV layer active.

    Reuses an already-open edit context when another overlay set one up (so
    starting a second overlay does not disturb the artist's selection). Raises
    ``RuntimeError`` if a requested UV layer is missing on a target.
    """
    edit_names = (
        {
            obj.name
            for obj in context.objects_in_mode_unique_data
            if obj.type == 'MESH'
        }
        if context.mode == 'EDIT_MESH'
        else set()
    )
    reuse = (
        bool(active_kinds())
        and source_object.name in edit_names
        and all(obj.name in edit_names for obj in targets)
    )
    acquire(context, kind)
    if not reuse:
        active = context.active_object
        if active and active.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(context.selected_objects):
            obj.select_set(False)
    for obj in targets:
        layer_name = uv_layer_names.get(obj.name, "") if uv_layer_names else ""
        uv_layer = (
            obj.data.uv_layers.get(layer_name)
            if layer_name
            else obj.data.uv_layers.active
        )
        if uv_layer is None:
            raise RuntimeError("The requested UV set is missing on a mesh")
        obj.data.uv_layers.active = uv_layer
        if not reuse:
            obj.select_set(True)
    if not reuse:
        context.view_layer.objects.active = source_object
        bpy.ops.object.mode_set(mode='EDIT')
    return reuse


def reset():
    _session.active_kinds.clear()
    _session.snapshot = None
    _material_watch.clear()
