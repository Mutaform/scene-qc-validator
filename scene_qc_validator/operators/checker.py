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
    name = active.name if active else ""
    mode = active.mode if active else 'OBJECT'
    if active and mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass
    return name, mode


def _restore_mode(context, snapshot):
    name, mode = snapshot
    obj = context.scene.objects.get(name) if name else None
    if obj:
        context.view_layer.objects.active = obj
    if obj and mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode=mode)
        except RuntimeError:
            pass


def _tag_texture_viewports():
    """Redraw every 3D viewport and switch SOLID shading to texture colour so
    the checker material is visible."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            if area.spaces.active.shading.type == 'SOLID':
                try:
                    area.spaces.active.shading.color_type = 'TEXTURE'
                except TypeError:
                    pass
            area.tag_redraw()


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
    _tag_texture_viewports()


def _tag_object_update(obj):
    obj.data.update_tag()
    _tag_texture_viewports()


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


def _settings():
    return getattr(bpy.context.scene, "sqc_settings", None)


def uv_set_number():
    """The panel's "UV set" number, shared with the UV overlays."""
    settings = _settings()
    return getattr(settings, "overlap_visual_uv_set_number", 1) if settings else 1


def checker_rotated():
    """Whether the panel's quarter-turn toggle is pressed."""
    settings = _settings()
    return bool(getattr(settings, "uv_checker_rotated", False)) if settings else False


def _checker_tiling():
    settings = _settings()
    return getattr(settings, "uv_checker_tiling", 1.0) if settings else 1.0


def _reapply_to_worn_checkers(tiling, number, rotated):
    """Rebuild the checker UVs on every mesh currently wearing a checker."""
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        backup = _read_backup(obj)
        if backup:
            _apply_checker_uv(obj, tiling, backup, number, rotated)


def refresh_uv_checker():
    """Re-copy the checker UVs from whatever the panel says right now.

    Used by the controls that only change how the artist's layout is copied
    into SQC_UV_Checker_Tiling - "UV set" and the quarter turn - and leave the
    material alone. Tiling goes through update_uv_checker_tiling instead,
    because the material nodes carry that value too.
    """
    _reapply_to_worn_checkers(
        _checker_tiling(), uv_set_number(), checker_rotated(),
    )


def update_uv_checker_tiling(tiling):
    for checker_type, info in CHECKER_TYPES.items():
        material = bpy.data.materials.get(info["material"])
        if material and _checker_tiling_node(material) is None:
            material = _checker_material(checker_type, tiling)
        _set_mapping_tiling(material, tiling)
    _reapply_to_worn_checkers(tiling, uv_set_number(), checker_rotated())


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


def source_uv_layer(obj, number):
    """The UV layer the checker copies, and whether it is the one asked for.

    The number is the panel's "UV set": one-based, counted the way Show
    Overlaps counts it. The checker's own `SQC_UV_Checker_Tiling` layer stays
    out of the count - it is added on top of the artist's channels, and
    counting it would shift every number by one the moment the checker went on.

    A mesh without that many channels falls back to its first one and says so
    through ``exact=False``, rather than refusing: the same call also carries
    tiling changes, and the caller reports the substitution.
    """
    layers = [
        layer for layer in obj.data.uv_layers
        if layer.name != CHECKER_UV_NAME
    ]
    if not layers:
        return None, True
    index = max(0, (number or 1) - 1)
    if index < len(layers):
        return layers[index], True
    return layers[0], False


def _turned(flat, tiling):
    """The layout given a quarter turn about the middle of its own bounds.

    Turning the UVs is how the texture turns: the viewport reads the checker
    channel directly in Solid shading, so a rotation node in the material
    would only show up in Material Preview. The turn is taken about the centre
    of the layout rather than the UV origin so the islands stay where they
    were - with a repeating texture the difference is invisible, but it keeps
    a mesh packed far from the origin from flying off.
    """
    us, vs = flat[0::2], flat[1::2]
    cu = (min(us) + max(us)) * 0.5
    cv = (min(vs) + max(vs)) * 0.5
    out = [0.0] * len(flat)
    out[0::2] = [(cu + (v - cv)) * tiling for v in vs]
    out[1::2] = [(cv - (u - cu)) * tiling for u in us]
    return out


def _apply_checker_uv(obj, tiling, backup, number, rotated=False):
    if not obj.data.uv_layers:
        return False
    source, _exact = source_uv_layer(obj, number)
    if source is None:
        return False

    checker = obj.data.uv_layers.get(CHECKER_UV_NAME)
    if checker is None:
        checker = obj.data.uv_layers.new(name=CHECKER_UV_NAME, do_init=False)
    # foreach, not a Python loop over the loops: this runs on every tick of
    # the tiling slider, and the bed in the test scene has 44 908 of them.
    flat = [0.0] * (len(source.data) * 2)
    source.data.foreach_get("uv", flat)
    if rotated:
        flat = _turned(flat, tiling)
    elif tiling != 1.0:
        flat = [value * tiling for value in flat]
    checker.data.foreach_set("uv", flat)
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


def _assign_checker(
    obj, checker_type, material, backup=None, number=1, rotated=False,
):
    backup = backup or _write_backup(obj, checker_type)
    if len(obj.material_slots) == 0:
        obj.data.materials.append(material)
    else:
        for index in range(len(obj.material_slots)):
            obj.material_slots[index].material = material
    backup["checker_type"] = checker_type
    _apply_checker_uv(
        obj, material.get("sqc_uv_checker_tiling", 1.0), backup, number,
        rotated,
    )
    obj[BACKUP_PROP] = json.dumps(backup)


def _purge_unused_checker_materials():
    """Drop checker material/image datablocks that no object references any
    more, so toggling the checker off leaves no leftovers in the scene. A
    checker still applied to another object keeps a non-zero user count and is
    left untouched."""
    for info in CHECKER_TYPES.values():
        material = bpy.data.materials.get(info["material"])
        if material is not None and material.users == 0:
            bpy.data.materials.remove(material)
        image = bpy.data.images.get(info["image"])
        if image is not None and image.users == 0:
            bpy.data.images.remove(image)


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
        number = context.scene.sqc_settings.overlap_visual_uv_set_number
        rotated = context.scene.sqc_settings.uv_checker_rotated
        checker_mat = _checker_material(self.checker_type, tiling)
        restored = 0
        applied = 0
        short = 0

        try:
            for obj in targets:
                backup = _read_backup(obj)
                if backup and backup.get("checker_type") == self.checker_type:
                    _restore_materials(obj, backup)
                    restored += 1
                else:
                    _, exact = source_uv_layer(obj, number)
                    _assign_checker(
                        obj, self.checker_type, checker_mat, backup, number,
                        rotated,
                    )
                    applied += 1
                    if not exact:
                        short += 1
        finally:
            _restore_mode(context, mode_snapshot)

        _purge_unused_checker_materials()

        if applied and restored:
            self.report({'INFO'}, f"Applied checker to {applied}, restored {restored}")
        elif applied:
            self.report({'INFO'}, f"Applied checker to {applied} object(s)")
        else:
            self.report({'INFO'}, f"Restored {restored} object(s)")
        if short:
            # Said out loud: the checker would be showing a channel the artist
            # did not ask for, and a silent substitution in a QC tool is a lie.
            self.report(
                {'WARNING'},
                f"UV set {number} is missing on {short} object(s) - "
                "showing UV set 1 there",
            )
        return {'FINISHED'}
