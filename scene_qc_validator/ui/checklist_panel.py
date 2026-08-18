from bpy.types import Panel

from .. import checks as checks_mod
from .. import presets as presets_mod


def _stage_button_text(stage_name):
    if len(stage_name) > 3 and stage_name[:2].isdigit() and stage_name[2] == "_":
        return stage_name[3:]
    return stage_name


def _overlay_toggle_row(
    layout, settings, scope_prop, op_id, text, icon, depress,
    with_controls=True,
):
    """A UV-overlay toggle row: a material-scope checkbox, the toggle button,
    and (optionally) a right-aligned controls area returned to the caller so
    each overlay can add its own fields. Keeps the three overlay rows visually
    consistent."""
    row = layout.row(align=True)
    row.prop(settings, scope_prop, text="")
    if not with_controls:
        row.operator(op_id, text=text, icon=icon, depress=depress)
        return None
    split = row.split(factor=0.5, align=True)
    split.operator(op_id, text=text, icon=icon, depress=depress)
    controls = split.row(align=True)
    controls.alignment = 'RIGHT'
    return controls


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

        if "LP_UVs" in s.active_stage_name:
            from ..operators.overlap_visual import is_overlap_review_active
            from ..operators.padding_visual import is_padding_review_active
            from ..operators.texel_density_visual import (
                is_texel_density_review_active,
            )

            overlap_controls = _overlay_toggle_row(
                layout, s, "overlap_visual_use_material_scope",
                "sqc.toggle_overlap_visual", "Show Overlaps", 'HIDE_OFF',
                is_overlap_review_active(),
            )
            overlap_controls.label(text="UV set")
            overlap_controls.prop(
                s, "overlap_visual_uv_set_number", text="",
            )

            padding_item = next(
                (
                    item for item in s.checks
                    if item.check_id == "uv_padding"
                ),
                None,
            )
            padding_controls = _overlay_toggle_row(
                layout, s, "padding_visual_use_material_scope",
                "sqc.toggle_padding_visual", "Show Padding", 'MOD_UVPROJECT',
                is_padding_review_active(),
            )
            if padding_item is not None:
                # Fixed-width number block, flush right, keeps the 4096 /
                # value fields comfortably sized instead of collapsing.
                padding_block = padding_controls.row(align=True)
                padding_block.ui_units_x = 8.5
                texture_previous = padding_block.operator(
                    "sqc.step_padding_value",
                    text="",
                    icon='TRIA_LEFT',
                )
                texture_previous.target = 'TEXTURE'
                texture_previous.direction = -1
                padding_block.prop(
                    padding_item,
                    "padding_texture_input",
                    text="",
                )
                texture_next = padding_block.operator(
                    "sqc.step_padding_value",
                    text="",
                    icon='TRIA_RIGHT',
                )
                texture_next.target = 'TEXTURE'
                texture_next.direction = 1

                padding_previous = padding_block.operator(
                    "sqc.step_padding_value",
                    text="",
                    icon='TRIA_LEFT',
                )
                padding_previous.target = 'PADDING'
                padding_previous.direction = -1
                padding_block.prop(
                    padding_item,
                    "padding_value_input",
                    text="",
                )
                padding_next = padding_block.operator(
                    "sqc.step_padding_value",
                    text="",
                    icon='TRIA_RIGHT',
                )
                padding_next.target = 'PADDING'
                padding_next.direction = 1

            _overlay_toggle_row(
                layout, s, "texel_density_visual_use_material_scope",
                "sqc.toggle_texel_density_visual", "Show Texel Density",
                'IMAGE_DATA', is_texel_density_review_active(),
                with_controls=False,
            )

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
        tab_checks = [
            c for c in s.checks
            if (
                c.category in allowed
                and c.check_id
                not in checks_mod.CHECKLIST_HIDDEN_IDS
            )
        ]
        tab_enabled = sum(1 for c in tab_checks if c.enabled)
        check_box.label(text=f"{tab_enabled} of {len(tab_checks)} enabled in this tab")

        row = check_box.row(align=True)
        row.operator("sqc.select_all_checks", text="Select All").enable = True
        row.operator("sqc.select_all_checks", text="Deselect All").enable = False

        check_box.template_list("SQC_UL_checklist", "", s, "checks", s, "active_check_index", rows=8)

        if 0 <= s.active_check_index < len(s.checks):
            item = s.checks[s.active_check_index]
            if item.check_id not in checks_mod.CHECKLIST_HIDDEN_IDS:
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
        elif cid == "uv_unaligned_edges":
            sub.prop(
                item,
                "float_param_1",
                text="Angle Tolerance",
            )
            sub.prop(
                item,
                "float_param_2",
                text="Rectilinear Ratio",
            )
        elif cid == "mat_material_count":
            sub.prop(
                item,
                "int_param_1",
                text="Max Materials",
            )
        elif cid == "uv_overlap":
            sub.prop(item, "string_param_1", text="UV Set Regex")
            sub.prop(item, "bool_param_1", text="Required")
            sub.prop(item, "float_param_1", text="Tolerance")
            sub.prop(item, "int_param_1", text="Max Pairs")
        elif cid == "uv_padding":
            sub.prop(
                item,
                "padding_value_input",
                text="Padding (px)",
            )
            sub.prop(
                item,
                "padding_texture_input",
                text="Texture Size",
            )
        elif cid == "obj_nanite_closed_geometry":
            sub.prop(item, "float_param_1", text="Gap Tolerance (mm)")
            sub.prop(item, "bool_param_1", text="Use Scene Geometry")
            sub.prop(item, "string_param_1", text="Ignore Objects Regex")
        elif cid == "nm_object_pattern":
            sub.prop(item, "string_param_1", text="Regex Pattern")
        elif cid == "mat_material_name":
            sub.prop(item, "string_param_1", text="Allowed Patterns")
