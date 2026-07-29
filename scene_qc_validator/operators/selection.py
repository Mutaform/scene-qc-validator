import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from .core import _settings, _validation_targets
from . import random_sharp_highlight


def _parse_element_ref(element_ref):
    parsed = {}
    for part in element_ref.split(";"):
        if not part or ":" not in part:
            continue
        kind, value = part.split(":", 1)
        parsed.setdefault(kind, []).append(value)
    return parsed


def _parse_indices(values):
    indices = []
    for value in values:
        indices.extend(int(i) for i in value.split(",") if i != "")
    return indices


def _activate_uv_layer(obj, uv_layer_name):
    if not uv_layer_name:
        return
    uv_index = obj.data.uv_layers.find(uv_layer_name)
    if uv_index >= 0:
        obj.data.uv_layers.active_index = uv_index


def _parse_uv_segments(values):
    segments = []
    for value in values:
        for encoded_segment in value.split("|"):
            if not encoded_segment:
                continue
            face_index, edge_index = encoded_segment.split(",", 1)
            segments.append((int(face_index), int(edge_index)))
    return segments


def _select_uv_segments(obj, uv_layer_name, encoded_segments):
    segments = set(_parse_uv_segments(encoded_segments))
    if not segments:
        return

    bpy.context.scene.tool_settings.use_uv_select_sync = False
    bpy.context.scene.tool_settings.uv_select_mode = 'EDGE'
    mesh = obj.data
    attributes = mesh.attributes

    uv_vertex_selection = attributes.get(".uv_select_vert")
    if uv_vertex_selection is None:
        uv_vertex_selection = attributes.new(
            ".uv_select_vert",
            'BOOLEAN',
            'CORNER',
        )
    uv_edge_selection = attributes.get(".uv_select_edge")
    if uv_edge_selection is None:
        uv_edge_selection = attributes.new(
            ".uv_select_edge",
            'BOOLEAN',
            'CORNER',
        )
    uv_face_selection = attributes.get(".uv_select_face")
    if uv_face_selection is None:
        uv_face_selection = attributes.new(
            ".uv_select_face",
            'BOOLEAN',
            'FACE',
        )

    uv_vertex_selection.data.foreach_set(
        "value",
        [False] * len(uv_vertex_selection.data),
    )
    uv_edge_selection.data.foreach_set(
        "value",
        [False] * len(uv_edge_selection.data),
    )
    uv_face_selection.data.foreach_set(
        "value",
        [False] * len(uv_face_selection.data),
    )

    for polygon in mesh.polygons:
        polygon.select = False

    for face_index, edge_index in segments:
        if face_index >= len(mesh.polygons):
            continue
        polygon = mesh.polygons[face_index]
        polygon.select = True
        loop_indices = polygon.loop_indices
        loop_count = len(loop_indices)
        for offset, loop_index in enumerate(loop_indices):
            if mesh.loops[loop_index].edge_index != edge_index:
                continue
            next_loop_index = loop_indices[
                (offset + 1) % loop_count
            ]
            uv_vertex_selection.data[loop_index].value = True
            uv_vertex_selection.data[next_loop_index].value = True
            uv_edge_selection.data[loop_index].value = True
            break
    mesh.update()


def _select_elements(obj, element_ref):
    if obj.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    if obj.type != 'MESH' or not element_ref:
        return

    parsed = _parse_element_ref(element_ref)
    uv_layer_name = parsed.get("uv", [""])[0]
    if uv_layer_name:
        uv_index = obj.data.uv_layers.find(uv_layer_name)
        if uv_index >= 0:
            obj.data.uv_layers.active_index = uv_index

    kinds = set(parsed.keys())
    is_uv_segment_result = "uvseg" in kinds
    if is_uv_segment_result:
        _select_uv_segments(
            obj,
            uv_layer_name,
            parsed.get("uvseg", []),
        )
        bpy.ops.object.mode_set(mode='EDIT')
        return

    select_mode = (
        'FACE'
        if 'f' in kinds
        else ('EDGE' if 'e' in kinds else 'VERT')
    )

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type=select_mode)
    bpy.ops.mesh.select_all(action='DESELECT')
    import bmesh
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    face_indices = _parse_indices(parsed.get("f", []))
    for i in _parse_indices(parsed.get("v", [])):
        if i < len(bm.verts):
            bm.verts[i].select = True
    for i in _parse_indices(parsed.get("e", [])):
        if i < len(bm.edges):
            bm.edges[i].select = True
    for i in face_indices:
        if i < len(bm.faces):
            bm.faces[i].select = True
    _activate_uv_layer(obj, uv_layer_name)
    bmesh.update_edit_mesh(obj.data)


def select_result_by_index(context, index):
    s = _settings(context)
    if index < 0 or index >= len(s.results):
        return False
    r = s.results[index]
    obj = context.scene.objects.get(r.object_name)
    if not obj:
        return False
    from . import overlap_visual
    if r.check_id == "uv_overlap":
        random_sharp_highlight.clear_highlight()
        parsed = _parse_element_ref(r.element_ref)
        uv_layer_name = parsed.get("uv", [""])[0]
        return overlap_visual.toggle_result_overlap_review(
            context, obj, uv_layer_name
        )
    if overlap_visual.is_overlap_review_active():
        overlap_visual.restore_overlap_review(context)
    _select_elements(obj, r.element_ref)
    if r.check_id == "uv_random_sharp":
        parsed = _parse_element_ref(r.element_ref)
        random_sharp_highlight.set_highlight(obj, _parse_indices(parsed.get("e", [])))
    else:
        random_sharp_highlight.clear_highlight()
    return True


class SQC_OT_select_result(Operator):
    bl_idname = "sqc.select_result"
    bl_label = "Select"

    def execute(self, context):
        s = _settings(context)
        if s.active_result_index < 0 or s.active_result_index >= len(s.results):
            return {'CANCELLED'}
        if not select_result_by_index(context, s.active_result_index):
            self.report({'WARNING'}, "Object no longer exists")
            return {'CANCELLED'}
        return {'FINISHED'}


class SQC_OT_select_material_users(Operator):
    bl_idname = "sqc.select_material_users"
    bl_label = "Select Material Users"
    bl_description = "Select all validated-scope mesh objects that use this material"

    material_name: StringProperty()

    def execute(self, context):
        mat = bpy.data.materials.get(self.material_name)
        if not mat:
            self.report({'WARNING'}, "Material no longer exists")
            return {'CANCELLED'}
        targets = [
            obj for obj in _validation_targets(context)
            if any(slot.material == mat for slot in obj.material_slots)
        ]
        if not targets:
            self.report({'WARNING'}, "No objects in current scope use this material")
            return {'CANCELLED'}
        if context.object and context.object.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                pass
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in targets:
            obj.select_set(True)
        context.view_layer.objects.active = targets[0]
        self.report({'INFO'}, f"Selected {len(targets)} object(s) using {mat.name}")
        return {'FINISHED'}
