"""Shared lifecycle for simultaneously active UV review overlays."""
from dataclasses import dataclass, field

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
