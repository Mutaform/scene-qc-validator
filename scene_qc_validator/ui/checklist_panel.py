from bpy.types import Panel

from .. import checks as checks_mod
from .. import presets as presets_mod


def _stage_button_text(stage_name):
    if len(stage_name) > 3 and stage_name[:2].isdigit() and stage_name[2] == "_":
        return stage_name[3:]
    return stage_name


class SQC_PT_checklist(Panel):
    """Sub-panel: preset management + the full checklist configuration."""
    bl_label = "Checklist"
    bl_idname = "SQC_PT_checklist"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "QC Validator"
    bl_parent_id = "SQC_PT_main"
    bl_order = 20
    bl_options = set()

    @classmethod
    def poll(cls, context):
        return len(context.scene.sqc_settings.checks) > 0

    def draw(self, context):
        layout = self.layout
        s = context.scene.sqc_settings

        # Project row
        row = layout.row(align=True)
        row.label(text="Project:", icon='PRESET')
        row.menu("SQC_MT_presets", text=s.active_project_name or "Select Project")
        row.operator("sqc.save_project", text="", icon='ADD')
        row.operator("sqc.import_project_file", text="", icon='IMPORT')
        row.operator("sqc.export_project_file", text="", icon='EXPORT')

        stages = presets_mod.project_stage_names(s.active_project_name)
        if stages:
            columns = min(max(len(stages), 1), 5)
            flow = layout.grid_flow(row_major=True, columns=columns, even_columns=True, even_rows=True, align=True)
            for stage_name in stages:
                op = flow.operator(
                    "sqc.load_stage",
                    text=_stage_button_text(stage_name),
                    depress=(stage_name == s.active_stage_name),
                )
                op.project_name = s.active_project_name
                op.stage_name = stage_name
            tools = layout.row(align=True)
            tools.alignment = 'RIGHT'
            tools.scale_y = 0.75
            tools.operator("sqc.save_stage", text="", icon='FILE_TICK')
            tools.operator("sqc.save_project", text="", icon='DUPLICATE')
            if not presets_mod.is_factory_project(s.active_project_name):
                tools.operator("sqc.delete_stage", text="", icon='X')
        else:
            layout.label(text="No stages in selected project", icon='INFO')

        row = layout.row(align=True)
        row.prop(
            s,
            "show_check_settings",
            text="Check Settings",
            icon='TRIA_DOWN' if s.show_check_settings else 'TRIA_RIGHT',
            emboss=False,
        )
        if not s.show_check_settings:
            return

        check_box = layout.box()
        tabs = check_box.row(align=True)
        tabs.prop(s, "checklist_tab", expand=True)

        allowed = checks_mod.TAB_CATEGORY_MAP.get(s.checklist_tab, set())
        tab_checks = [c for c in s.checks if c.category in allowed]
        tab_enabled = sum(1 for c in tab_checks if c.enabled)
        check_box.label(text=f"{tab_enabled} of {len(tab_checks)} enabled in this tab")

        row = check_box.row(align=True)
        row.operator("sqc.select_all_checks", text="Select All").enable = True
        row.operator("sqc.select_all_checks", text="Deselect All").enable = False

        check_box.template_list("SQC_UL_checklist", "", s, "checks", s, "active_check_index", rows=8)

        if 0 <= s.active_check_index < len(s.checks):
            item = s.checks[s.active_check_index]
            info = check_box.box()
            info.label(text=item.description, icon='INFO')
            self._draw_params(info, item)

    def _draw_params(self, layout, item):
        cid = item.check_id
        sub = layout.column()
        sub.use_property_split = True
        sub.use_property_decorate = False
        if cid in ("geo_zero_area", "geo_zero_length", "geo_non_planar", "tr_world_origin", "uv_single_tile", "uv_random_sharp"):
            sub.prop(item, "float_param_1", text="Tolerance")
        elif cid == "tr_unapplied":
            sub.prop(item, "string_param_1", text="Flags (loc,rot,scale)")
        elif cid == "uv_set_count":
            sub.prop(item, "int_param_1", text="Max UV Sets")
        elif cid == "uv_overlap":
            sub.prop(item, "string_param_1", text="UV Set Regex")
            sub.prop(item, "bool_param_1", text="Required")
            sub.prop(item, "float_param_1", text="Tolerance")
            sub.prop(item, "int_param_1", text="Max Pairs")
        elif cid == "nm_object_pattern":
            sub.prop(item, "string_param_1", text="Regex Pattern")
        elif cid == "mat_material_name":
            sub.prop(item, "string_param_1", text="Allowed Patterns")
