import bpy

from .core import (
    _restore_selection,
    _scope_empty_message,
    _select_only,
    _settings,
    _validation_targets,
    checks_mod,
    ensure_checks_initialized,
    ensure_checks_initialized_for_scene,
    presets_mod,
    run_validation_logic,
)
from .checklist import (
    SQC_OT_init_checks,
    SQC_OT_run_validate,
    SQC_OT_select_all_checks,
)
from .checker import (
    SQC_OT_toggle_uv_checker,
    update_uv_checker_tiling,
)
from .export import (
    SQC_OT_export_fbx,
    SQC_OT_validate_and_export,
)
from .fix import SQC_OT_fix_all, SQC_OT_fix_result
from .preset_files import (
    SQC_OT_delete_preset,
    SQC_OT_export_preset_file,
    SQC_OT_import_preset_file,
    SQC_OT_load_preset,
    SQC_OT_save_preset,
)
from .results import SQC_OT_toggle_result_mute
from .selection import (
    SQC_OT_select_material_users,
    SQC_OT_select_result,
    _select_elements,
    select_result_by_index,
)


CLASSES = (
    SQC_OT_init_checks,
    SQC_OT_select_all_checks,
    SQC_OT_run_validate,
    SQC_OT_toggle_result_mute,
    SQC_OT_select_result,
    SQC_OT_fix_result,
    SQC_OT_fix_all,
    SQC_OT_save_preset,
    SQC_OT_load_preset,
    SQC_OT_delete_preset,
    SQC_OT_export_preset_file,
    SQC_OT_import_preset_file,
    SQC_OT_select_material_users,
    SQC_OT_toggle_uv_checker,
    SQC_OT_validate_and_export,
    SQC_OT_export_fbx,
)


def _safe_register_class(cls):
    try:
        bpy.utils.unregister_class(cls)
    except RuntimeError:
        pass
    bpy.utils.register_class(cls)


def _safe_unregister_class(cls):
    try:
        bpy.utils.unregister_class(cls)
    except RuntimeError:
        pass


def register():
    for cls in CLASSES:
        _safe_register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        _safe_unregister_class(cls)
