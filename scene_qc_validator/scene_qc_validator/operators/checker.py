import json
import os

import bpy
from bpy.props import EnumProperty
from bpy.types import Operator


BACKUP_PROP = "_sqc_uv_checker_backup"
CHECKER_UV_NAME = "SQC_UV_Checker_Tiling"

CHECKER_TYPES = {
    'SQUARE': {
        "label": "Square Checker",
        "material": "SQC_UV_Checker_Square",
        "image": "SQC_UV_Checker_Square_Image",
        "asset": "uv_checker_square.jpg",
    },
    'LINE': {
        "label": "Line Checker",
        "material": "SQC_UV_Checker_Line",
        "image": "SQC_UV_Checker_Line_Image",
        "asset": "uv_checker_line.jpg",
    },
}


def _addon_root():
    return os.path.dirname(os.path.dirname(__file__))


def _checker_targets(context):
    targets = [obj for obj in context.selected_objects if obj.type == 'MESH']
    if not targets and context.object and context.object.type == 'MESH':
        targets = [context.object]
    return targets


def _switch_to_object_mode(context):
    active = context.view_layer.objects.active
    mode = active.mode if active else 'OBJECT'
    if active and mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass
    return active, mode


def _restore_mode(context, snapshot):
    active, mode = snapshot
    if active and context.scene.objects.get(active.name):
        context.view_layer.objects.active = active
    if active and mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode=mode)
        except RuntimeError:
            pass


def _load_checker_image(checker_type):
    info = CHECKER_TYPES[checker_type]
    path = os.path.join(_addon_root(), "assets", info["asset"])
    image = bpy.data.images.get(info["image"])
    if image is None or image.filepath != path:
        image = bpy.data.images.load(path, check_existing=True)
        image.name = info["image"]
    image.filepath = path
    image.source = 'FILE'
    try:
        image.reload()
    except RuntimeError:
        pass
    return image


def _checker_tiling_node(material):
    if not material or not material.use_nodes:
        return None
    nodes = material.node_tree.nodes
    tiling = nodes.get("SQC Checker Tiling")
    if tiling:
        return tiling
    for node in nodes:
        if node.bl_idname == "ShaderNodeVectorMath" and node.label == "Checker Tiling":
            return node
    return None


def _checker_image_nodes(material):
    if not material or not material.use_nodes:
        return []
    return [
        node for node in material.node_tree.nodes
        if node.bl_idname == "ShaderNodeTexImage" and node.image
        and node.image.name.startswith("SQC_UV_Checker_")
    ]


def _tag_checker_update(material):
    if material:
        material["sqc_uv_checker_tiling"] = material.get("sqc_uv_checker_tiling", 1.0)
        material.update_tag()
        if material.node_tree:
            material.node_tree.update_tag()
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and any(slot.material == material for slot in obj.material_slots):
            obj.data.update_tag()
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                if area.spaces.active.shading.type == 'SOLID':
                    try:
                        area.spaces.active.shading.color_type = 'TEXTURE'
                    except TypeError:
                        pass
                area.tag_redraw()


def _tag_object_update(obj):
    obj.data.update_tag()
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                if area.spaces.active.shading.type == 'SOLID':
                    try:
                        area.spaces.active.shading.color_type = 'TEXTURE'
                    except TypeError:
                        pass
                area.tag_redraw()


def _set_mapping_tiling(material, tiling):
    if not material or not material.use_nodes:
        return
    material["sqc_uv_checker_tiling"] = tiling
    tiling_node = _checker_tiling_node(material)
    if tiling_node:
        tiling_node.inputs["Scale"].default_value = tiling
    for image_node in _checker_image_nodes(material):
        image_node.extension = 'REPEAT'
        image_node.texture_mapping.scale[0] = 1.0
        image_node.texture_mapping.scale[1] = 1.0
        image_node.texture_mapping.scale[2] = 1.0
    _tag_checker_update(material)


def update_uv_checker_tiling(tiling):
    for checker_type, info in CHECKER_TYPES.items():
        material = bpy.data.materials.get(info["material"])
        if material and _checker_tiling_node(material) is None:
            material = _checker_material(checker_type, tiling)
        _set_mapping_tiling(material, tiling)
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        backup = _read_backup(obj)
        if backup:
            _apply_checker_uv(obj, tiling, backup)


def _checker_material(checker_type, tiling):
    info = CHECKER_TYPES[checker_type]
    mat = bpy.data.materials.get(info["material"])
    if mat is None:
        mat = bpy.data.materials.new(info["material"])
    mat.use_nodes = True
    mat.diffuse_color = (1.0, 1.0, 1.0, 1.0)

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (520, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.location = (60, 80)
    image_node.image = _load_checker_image(checker_type)
    image_node.extension = 'REPEAT'
    image_node.interpolation = 'Closest'
    tiling_node = nodes.new("ShaderNodeVectorMath")
    tiling_node.operation = 'SCALE'
    tiling_node.name = "SQC Checker Tiling"
    tiling_node.label = "Checker Tiling"
    tiling_node.location = (-160, 80)
    texcoord = nodes.new("ShaderNodeTexCoord")
    texcoord.location = (-360, 80)

    links.new(texcoord.outputs["UV"], tiling_node.inputs["Vector"])
    links.new(tiling_node.outputs["Vector"], image_node.inputs["Vector"])
    links.new(image_node.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    _set_mapping_tiling(mat, tiling)
    return mat


def _read_backup(obj):
    raw = obj.get(BACKUP_PROP)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data.get("materials"), list):
        return None
    return data


def _write_backup(obj, checker_type):
    active_uv = obj.data.uv_layers.active
    data = {
        "checker_type": checker_type,
        "materials": [slot.material.name if slot.material else "" for slot in obj.material_slots],
        "material_indices": [poly.material_index for poly in obj.data.polygons],
        "active_uv_name": active_uv.name if active_uv else "",
        "active_uv_index": obj.data.uv_layers.active_index if obj.data.uv_layers else -1,
    }
    obj[BACKUP_PROP] = json.dumps(data)
    return data


def _remove_checker_uv(obj):
    layer = obj.data.uv_layers.get(CHECKER_UV_NAME)
    if layer:
        obj.data.uv_layers.remove(layer)


def _restore_active_uv(obj, backup):
    if not obj.data.uv_layers:
        return
    active_name = backup.get("active_uv_name", "")
    if active_name and obj.data.uv_layers.get(active_name):
        obj.data.uv_layers.active = obj.data.uv_layers[active_name]
        return
    active_index = backup.get("active_uv_index", -1)
    if isinstance(active_index, int) and 0 <= active_index < len(obj.data.uv_layers):
        obj.data.uv_layers.active_index = active_index


def _apply_checker_uv(obj, tiling, backup):
    if not obj.data.uv_layers:
        return False
    source_name = backup.get("active_uv_name", "")
    source = obj.data.uv_layers.get(source_name) if source_name else None
    if source is None:
        source = obj.data.uv_layers.active
    if source and source.name == CHECKER_UV_NAME:
        source = next((layer for layer in obj.data.uv_layers if layer.name != CHECKER_UV_NAME), None)
    if source is None:
        return False

    checker = obj.data.uv_layers.get(CHECKER_UV_NAME)
    if checker is None:
        checker = obj.data.uv_layers.new(name=CHECKER_UV_NAME, do_init=False)
    for src_loop, checker_loop in zip(source.data, checker.data):
        checker_loop.uv = src_loop.uv * tiling
    obj.data.uv_layers.active = checker
    try:
        checker.active_render = True
    except AttributeError:
        pass
    _tag_object_update(obj)
    return True


def _restore_materials(obj, backup):
    _remove_checker_uv(obj)
    _restore_active_uv(obj, backup)
    materials = backup["materials"]
    restored_materials = [bpy.data.materials.get(name) if name else None for name in materials]
    obj.data.materials.clear()
    for material in restored_materials:
        obj.data.materials.append(material)
    material_indices = backup.get("material_indices")
    if restored_materials and isinstance(material_indices, list):
        for poly, material_index in zip(obj.data.polygons, material_indices):
            poly.material_index = min(max(int(material_index), 0), max(len(materials) - 1, 0))
    if BACKUP_PROP in obj:
        del obj[BACKUP_PROP]


def _assign_checker(obj, checker_type, material, backup=None):
    backup = backup or _write_backup(obj, checker_type)
    if len(obj.material_slots) == 0:
        obj.data.materials.append(material)
    else:
        for index in range(len(obj.material_slots)):
            obj.material_slots[index].material = material
    backup["checker_type"] = checker_type
    _apply_checker_uv(obj, material.get("sqc_uv_checker_tiling", 1.0), backup)
    obj[BACKUP_PROP] = json.dumps(backup)


class SQC_OT_toggle_uv_checker(Operator):
    bl_idname = "sqc.toggle_uv_checker"
    bl_label = "Toggle UV Checker"
    bl_description = "Toggle a temporary UV checker material on selected mesh objects"

    checker_type: EnumProperty(
        items=[
            ('SQUARE', "Square Checker", ""),
            ('LINE', "Line Checker", ""),
        ],
        default='SQUARE',
    )

    def execute(self, context):
        targets = _checker_targets(context)
        if not targets:
            self.report({'WARNING'}, "Select at least one mesh object")
            return {'CANCELLED'}

        mode_snapshot = _switch_to_object_mode(context)
        tiling = context.scene.sqc_settings.uv_checker_tiling
        checker_mat = _checker_material(self.checker_type, tiling)
        restored = 0
        applied = 0

        try:
            for obj in targets:
                backup = _read_backup(obj)
                if backup and backup.get("checker_type") == self.checker_type:
                    _restore_materials(obj, backup)
                    restored += 1
                else:
                    _assign_checker(obj, self.checker_type, checker_mat, backup)
                    applied += 1
        finally:
            _restore_mode(context, mode_snapshot)

        if applied and restored:
            self.report({'INFO'}, f"Applied checker to {applied}, restored {restored}")
        elif applied:
            self.report({'INFO'}, f"Applied checker to {applied} object(s)")
        else:
            self.report({'INFO'}, f"Restored {restored} object(s)")
        return {'FINISHED'}
