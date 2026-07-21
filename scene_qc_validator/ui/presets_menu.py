import bpy

from .. import presets as presets_mod


class SQC_MT_presets(bpy.types.Menu):
    bl_label = "Projects"
    bl_idname = "SQC_MT_presets"

    def draw(self, context):
        layout = self.layout
        s = context.scene.sqc_settings
        for name in presets_mod.list_projects():
            if presets_mod.is_factory_project(name):
                op = layout.operator(
                    "sqc.load_project",
                    text=name,
                    depress=(name == s.active_project_name),
                )
                op.project_name = name
                continue

            row = layout.row(align=True)
            split = row.split(factor=0.9, align=True)
            op = split.operator(
                "sqc.load_project",
                text=name,
                depress=(name == s.active_project_name),
            )
            op.project_name = name
            op = split.operator("sqc.delete_project", text="", icon='X')
            op.project_name = name
