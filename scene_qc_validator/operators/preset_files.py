from bpy.props import StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

from .core import _settings, ensure_checks_initialized, presets_mod


class SQC_OT_save_preset(Operator):
    bl_idname = "sqc.save_preset"
    bl_label = "Save Preset"
    bl_description = "Save the current checklist configuration as a new preset"
    bl_options = {'REGISTER'}

    preset_name: StringProperty(name="Name", default="New Preset")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "preset_name")

    def execute(self, context):
        s = _settings(context)
        name = self.preset_name
        if not name.strip():
            self.report({'WARNING'}, "Preset name can't be empty")
            return {'CANCELLED'}
        presets_mod.save_preset(name, s.checks)
        s.active_preset_name = name
        self.report({'INFO'}, f"Saved preset '{name}'")
        return {'FINISHED'}


class SQC_OT_load_preset(Operator):
    bl_idname = "sqc.load_preset"
    bl_label = "Load Preset"

    preset_name: StringProperty()

    def execute(self, context):
        ensure_checks_initialized(context)
        s = _settings(context)
        if presets_mod.load_preset(self.preset_name, s.checks):
            s.active_preset_name = self.preset_name
            self.report({'INFO'}, f"Loaded preset '{self.preset_name}'")
            return {'FINISHED'}
        self.report({'WARNING'}, f"Preset '{self.preset_name}' not found")
        return {'CANCELLED'}


class SQC_OT_delete_preset(Operator):
    bl_idname = "sqc.delete_preset"
    bl_label = "Delete Preset"

    preset_name: StringProperty()

    def execute(self, context):
        if presets_mod.delete_preset(self.preset_name):
            self.report({'INFO'}, f"Deleted preset '{self.preset_name}'")
            return {'FINISHED'}
        self.report({'WARNING'}, "Cannot delete this preset")
        return {'CANCELLED'}


class SQC_OT_export_preset_file(Operator, ExportHelper):
    bl_idname = "sqc.export_preset_file"
    bl_label = "Export Preset"
    bl_description = "Export the current checklist configuration to a shareable JSON file"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        s = _settings(context)
        safe_name = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in s.active_preset_name).strip()
        self.filepath = (safe_name or "Scene_QC_Preset") + ".json"
        return super().invoke(context, event)

    def execute(self, context):
        ensure_checks_initialized(context)
        s = _settings(context)
        try:
            presets_mod.export_preset_file(self.filepath, s.active_preset_name, s.checks)
        except OSError as ex:
            self.report({'ERROR'}, f"Preset export failed: {ex}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Exported preset to {self.filepath}")
        return {'FINISHED'}


class SQC_OT_import_preset_file(Operator, ImportHelper):
    bl_idname = "sqc.import_preset_file"
    bl_label = "Import Preset"
    bl_description = "Import a checklist preset JSON file and apply it to the current scene"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        ensure_checks_initialized(context)
        s = _settings(context)
        name = presets_mod.import_preset_file(self.filepath, s.checks)
        if not name:
            self.report({'ERROR'}, "Preset import failed or file is not a valid Scene QC preset")
            return {'CANCELLED'}
        s.active_preset_name = name
        s.has_run_validation = False
        s.results.clear()
        self.report({'INFO'}, f"Imported preset '{name}'")
        return {'FINISHED'}
