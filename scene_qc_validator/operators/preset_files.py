from bpy.props import StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

from .core import _settings, ensure_checks_initialized, presets_mod


class SQC_OT_load_preset(Operator):
    bl_idname = "sqc.load_project"
    bl_label = "Load Project"

    project_name: StringProperty()

    def execute(self, context):
        ensure_checks_initialized(context)
        s = _settings(context)
        stages = presets_mod.project_stage_names(self.project_name)
        if not stages:
            self.report({'WARNING'}, f"Project '{self.project_name}' has no stages")
            return {'CANCELLED'}
        s.active_project_name = self.project_name
        s.active_preset_name = self.project_name
        if s.active_stage_name not in stages:
            s.active_stage_name = stages[0]
        self.report({'INFO'}, f"Loaded project '{self.project_name}'")
        return {'FINISHED'}


class SQC_OT_load_stage(Operator):
    bl_idname = "sqc.load_stage"
    bl_label = "Load Stage"

    project_name: StringProperty()
    stage_name: StringProperty()

    def execute(self, context):
        ensure_checks_initialized(context)
        s = _settings(context)
        if presets_mod.load_stage(self.project_name, self.stage_name, s.checks):
            s.active_project_name = self.project_name
            s.active_preset_name = self.project_name
            s.active_stage_name = self.stage_name
            s.applied_stage_key = f"{self.project_name}::{self.stage_name}"
            s.has_run_validation = False
            s.results.clear()
            self.report({'INFO'}, f"Loaded stage '{self.stage_name}'")
            return {'FINISHED'}
        self.report({'WARNING'}, f"Stage '{self.stage_name}' not found")
        return {'CANCELLED'}


class SQC_OT_save_preset(Operator):
    bl_idname = "sqc.save_project"
    bl_label = "Save Project"
    bl_description = "Save the current checklist as a stage in a project"
    bl_options = {'REGISTER'}

    project_name: StringProperty(name="Project", default="My Project")
    stage_name: StringProperty(name="Stage", default="New Stage")

    def invoke(self, context, event):
        s = _settings(context)
        self.project_name = s.active_project_name if not presets_mod.is_factory_project(s.active_project_name) else f"{s.active_project_name} Custom"
        self.stage_name = s.active_stage_name or "New Stage"
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "project_name")
        self.layout.prop(self, "stage_name")

    def execute(self, context):
        ensure_checks_initialized(context)
        s = _settings(context)
        if presets_mod.save_project(self.project_name, self.stage_name, s.checks):
            s.active_project_name = self.project_name
            s.active_preset_name = self.project_name
            s.active_stage_name = self.stage_name
            s.applied_stage_key = f"{self.project_name}::{self.stage_name}"
            self.report({'INFO'}, f"Saved '{self.stage_name}' in project '{self.project_name}'")
            return {'FINISHED'}
        self.report({'WARNING'}, "Project or stage name is invalid")
        return {'CANCELLED'}


class SQC_OT_save_stage(Operator):
    bl_idname = "sqc.save_stage"
    bl_label = "Save Stage"
    bl_description = "Save the current checklist into the active project stage"

    def execute(self, context):
        ensure_checks_initialized(context)
        s = _settings(context)
        if presets_mod.save_project(s.active_project_name, s.active_stage_name, s.checks):
            s.applied_stage_key = f"{s.active_project_name}::{s.active_stage_name}"
            self.report({'INFO'}, f"Saved stage '{s.active_stage_name}'")
            return {'FINISHED'}
        self.report({'WARNING'}, "Active stage can't be saved")
        return {'CANCELLED'}


class SQC_OT_delete_preset(Operator):
    bl_idname = "sqc.delete_project"
    bl_label = "Delete Project"

    project_name: StringProperty()

    def execute(self, context):
        if presets_mod.delete_project(self.project_name):
            s = _settings(context)
            projects = presets_mod.list_projects()
            s.active_project_name = projects[0] if projects else ""
            s.active_preset_name = s.active_project_name
            stages = presets_mod.project_stage_names(s.active_project_name)
            s.active_stage_name = stages[0] if stages else ""
            self.report({'INFO'}, f"Deleted project '{self.project_name}'")
            return {'FINISHED'}
        self.report({'WARNING'}, "Cannot delete this project")
        return {'CANCELLED'}


class SQC_OT_delete_stage(Operator):
    bl_idname = "sqc.delete_stage"
    bl_label = "Delete Stage"

    def execute(self, context):
        s = _settings(context)
        if presets_mod.delete_stage(s.active_project_name, s.active_stage_name):
            stages = presets_mod.project_stage_names(s.active_project_name)
            s.active_stage_name = stages[0] if stages else ""
            self.report({'INFO'}, "Deleted stage")
            return {'FINISHED'}
        self.report({'WARNING'}, "Cannot delete this stage")
        return {'CANCELLED'}


class SQC_OT_export_preset_file(Operator, ExportHelper):
    bl_idname = "sqc.export_project_file"
    bl_label = "Export Project"
    bl_description = "Export the active project configuration to a shareable JSON file"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        s = _settings(context)
        safe_name = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in s.active_project_name).strip()
        self.filepath = (safe_name or "Scene_QC_Project") + ".json"
        return super().invoke(context, event)

    def execute(self, context):
        s = _settings(context)
        if not presets_mod.export_project_file(self.filepath, s.active_project_name):
            self.report({'ERROR'}, "Project export failed")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Exported project to {self.filepath}")
        return {'FINISHED'}


class SQC_OT_import_preset_file(Operator, ImportHelper):
    bl_idname = "sqc.import_project_file"
    bl_label = "Import Project"
    bl_description = "Import a project checklist JSON file"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        ensure_checks_initialized(context)
        s = _settings(context)
        name = presets_mod.import_project_file(self.filepath)
        if not name:
            self.report({'ERROR'}, "Project import failed or file is not a valid Scene QC project")
            return {'CANCELLED'}
        s.active_project_name = name
        s.active_preset_name = name
        stages = presets_mod.project_stage_names(name)
        s.active_stage_name = stages[0] if stages else ""
        s.applied_stage_key = ""
        s.has_run_validation = False
        s.results.clear()
        self.report({'INFO'}, f"Imported project '{name}'")
        return {'FINISHED'}
