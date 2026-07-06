import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from .core import _settings, _validation_targets


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
    select_mode = 'FACE' if 'f' in kinds else ('EDGE' if 'e' in kinds else 'VERT')

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
    _select_elements(obj, r.element_ref)
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
