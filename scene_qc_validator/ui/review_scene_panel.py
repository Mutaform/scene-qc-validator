import json

from bpy.types import Panel

from .. import operators as operators_mod
from . import icons


CHECKER_BACKUP_PROP = "_sqc_uv_checker_backup"


def _material_usage_for_scope(context):
    materials = {}
    targets = operators_mod._validation_targets(context)
    for obj in targets:
        seen_on_object = set()
        for slot in obj.material_slots:
            mat = slot.material
            if not mat:
                continue
            entry = materials.setdefault(mat.name, {
                "material": mat,
                "slot_count": 0,
                "objects": set(),
            })
            entry["slot_count"] += 1
            if mat.name not in seen_on_object:
                entry["objects"].add(obj.name)
                seen_on_object.add(mat.name)
    return targets, [materials[name] for name in sorted(materials.keys(), key=str.casefold)]


def _active_checker_type(context):
    checker_types = set()
    targets = [obj for obj in context.selected_objects if obj.type == 'MESH']
    if not targets and context.object and context.object.type == 'MESH':
        targets = [context.object]
    for obj in targets:
        raw = obj.get(CHECKER_BACKUP_PROP)
        if not raw:
            continue
        try:
            backup = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        checker_type = backup.get("checker_type")
        if checker_type:
            checker_types.add(checker_type)
    return checker_types.pop() if len(checker_types) == 1 else ""


class SQC_PT_scene_review(Panel):
    bl_label = "Review Scene"
    bl_idname = "SQC_PT_scene_review"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "QC Validator"
    bl_parent_id = "SQC_PT_main"
    bl_order = 10
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return len(context.scene.sqc_settings.checks) > 0

    def draw(self, context):
        layout = self.layout
        s = context.scene.sqc_settings
        targets, material_entries = _material_usage_for_scope(context)

        header = layout.row(align=True)
        header.label(text="Materials", icon='MATERIAL')
        header.label(text=f"{len(material_entries)} material(s) on {len(targets)} mesh object(s)")

        if not targets:
            layout.label(text="No mesh objects in current scope", icon='INFO')
        elif not material_entries:
            layout.label(text="No materials assigned", icon='INFO')
        else:
            box = layout.box()
            for entry in material_entries:
                mat = entry["material"]
                objects = sorted(entry["objects"], key=str.casefold)
                row = box.row(align=True)
                split = row.split(factor=0.68, align=True)
                split.label(text=mat.name, icon='MATERIAL')
                right = split.row(align=True)
                right.label(text=f"{len(objects)} obj / {entry['slot_count']} slot")
                op = right.operator("sqc.select_material_users", text="", icon='RESTRICT_SELECT_OFF')
                op.material_name = mat.name

        layout.separator()
        checker = layout.box()
        checker.label(text="UV Checker", icon='TEXTURE')
        checker.prop(s, "uv_checker_tiling", slider=True)
        active_checker = _active_checker_type(context)
        row = checker.row(align=True)
        op = row.operator(
            "sqc.toggle_uv_checker",
            text="Square Checker",
            icon_value=icons.icon_id("checker_grid"),
            depress=(active_checker == 'SQUARE'),
        )
        op.checker_type = 'SQUARE'
        op = row.operator(
            "sqc.toggle_uv_checker",
            text="Line Checker",
            icon_value=icons.icon_id("checker_lines"),
            depress=(active_checker == 'LINE'),
        )
        op.checker_type = 'LINE'
