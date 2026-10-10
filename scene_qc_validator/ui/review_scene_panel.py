from bpy.types import Panel

from .. import operators as operators_mod


def _material_usage_for_scope(context):
    materials = {}
    targets = operators_mod.review_scope_objects(context)
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
            reviewed = operators_mod.isolated_material_name(context)
            box = layout.box()
            for entry in material_entries:
                mat = entry["material"]
                objects = sorted(entry["objects"], key=str.casefold)
                row = box.row(align=True)
                split = row.split(factor=0.68, align=True)
                name = split.row(align=True)
                name.alignment = 'LEFT'
                select_op = name.operator(
                    "sqc.select_material_objects",
                    text=mat.name,
                    icon='MATERIAL',
                    emboss=False,
                )
                select_op.material_name = mat.name
                right = split.row(align=True)
                right.label(text=f"{len(objects)} obj / {entry['slot_count']} slot")
                op = right.operator(
                    "sqc.select_material_users",
                    text="",
                    icon='UV',
                    depress=(reviewed == mat.name),
                )
                op.material_name = mat.name
            if reviewed:
                note = box.row()
                note.enabled = False
                note.label(
                    text=f"Reviewing UVs of {reviewed}",
                    icon='INFO',
                )

