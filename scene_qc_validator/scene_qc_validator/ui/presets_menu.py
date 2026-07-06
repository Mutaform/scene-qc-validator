import bpy

from .. import presets as presets_mod


class SQC_MT_presets(bpy.types.Menu):
    bl_label = "Presets"
    bl_idname = "SQC_MT_presets"

    def draw(self, context):
        layout = self.layout
        s = context.scene.sqc_settings
        for name in presets_mod.list_presets():
            row = layout.row(align=True)
            row.operator("sqc.load_preset", text=name, depress=(name == s.active_preset_name)).preset_name = name
            if name != "Default":
                row.operator("sqc.delete_preset", text="", icon='X').preset_name = name
