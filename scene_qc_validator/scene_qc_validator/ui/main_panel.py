from bpy.types import Panel

from .helpers import addon_version


class SQC_PT_main(Panel):
    """Top-level panel: always-visible essentials - status, Validate, Export."""
    bl_label = "Scene QC Validator by Mutaform Studio"
    bl_idname = "SQC_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "QC Validator"

    def draw_header_preset(self, context):
        version = self.layout.row(align=True)
        version.alignment = 'RIGHT'
        version.enabled = False
        version.label(text=f"ver {addon_version()}")

    def draw(self, context):
        layout = self.layout
        s = context.scene.sqc_settings

        if len(s.checks) == 0:
            col = layout.column(align=True)
            col.label(text="Checklist not initialized yet", icon='INFO')
            col.operator("sqc.init_checks", text="Initialize Checklist", icon='FILE_REFRESH')
            return

        # --- Status banner ---
        if s.has_run_validation:
            fail_count = sum(1 for r in s.results if r.severity == 'FAIL' and not r.muted)
            muted_count = sum(1 for r in s.results if r.muted)
            info_count = sum(1 for r in s.results if r.severity == 'INFO' and not r.muted)
            banner = layout.box()
            row = banner.row()
            if s.last_validation_passed:
                row.label(text="All checks passed", icon='CHECKMARK')
            else:
                row.alert = True
                msg = f"{fail_count} failing check{'s' if fail_count != 1 else ''}"
                if info_count:
                    msg += f"  \u2022  {info_count} info"
                row.label(text=msg, icon='ERROR')
        else:
            layout.label(text="Not validated yet", icon='DOT')

        layout.prop(s, "validation_scope", text="Scope")

        # --- Validate ---
        col = layout.column(align=True)
        col.scale_y = 1.4
        col.operator("sqc.run_validate", text="Validate")

        layout.separator()

        # --- Export ---
        col = layout.column(align=True)
        col.label(text="Export To:")
        col.prop(s, "export_directory", text="")

        export_row = layout.row()
        export_row.scale_y = 1.4
        if s.has_run_validation and not s.last_validation_passed:
            export_row.enabled = False
            export_row.operator("sqc.validate_and_export", text="Resolve Fails to Export", icon='CANCEL')
        else:
            export_row.operator("sqc.validate_and_export", text="Export", icon='EXPORT')
