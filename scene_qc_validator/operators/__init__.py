import bpy

from .core import (
    _settings,
    _validation_targets,
    checks_mod,
    ensure_checks_initialized,
    ensure_checks_initialized_for_scene,
    presets_mod,
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
from .fix import SQC_OT_fix_all, SQC_OT_fix_result
from .preset_files import (
    SQC_OT_delete_preset,
    SQC_OT_delete_stage,
    SQC_OT_export_preset_file,
    SQC_OT_import_preset_file,
    SQC_OT_load_preset,
    SQC_OT_load_stage,
    SQC_OT_save_preset,
    SQC_OT_save_stage,
)
from .results import SQC_OT_toggle_result_mute
from .selection import (
    SQC_OT_select_material_users,
    SQC_OT_select_result,
    _select_elements,
    select_result_by_index,
)
from . import random_sharp_highlight
from ..checks.mapping import overlapped_uv
from ..checks.mapping import padding
from . import overlap_visual
from .overlap_visual import (
    SQC_OT_toggle_overlap_visual,
)
from . import padding_visual
from .padding_visual import (
    SQC_OT_TogglePaddingVisual,
)


CLASSES = (
    *overlapped_uv.OVERLAP_VISUAL_CLASSES,
    *padding.PADDING_VISUAL_CLASSES,
    SQC_OT_init_checks,
    SQC_OT_select_all_checks,
    SQC_OT_run_validate,
    SQC_OT_toggle_result_mute,
    SQC_OT_select_result,
    SQC_OT_fix_result,
    SQC_OT_fix_all,
    SQC_OT_save_preset,
    SQC_OT_save_stage,
    SQC_OT_load_preset,
    SQC_OT_load_stage,
    SQC_OT_delete_preset,
    SQC_OT_delete_stage,
    SQC_OT_export_preset_file,
    SQC_OT_import_preset_file,
    SQC_OT_select_material_users,
    SQC_OT_toggle_uv_checker,
    SQC_OT_toggle_overlap_visual,
    SQC_OT_TogglePaddingVisual,
    padding.SQC_OT_StepPaddingValue,
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
    random_sharp_highlight.unregister()
    overlap_visual.unregister_overlap_review()
    padding_visual.unregister_padding_review()
    overlapped_uv.unregister_overlap_visual()
    padding.unregister_padding_visual()
    for cls in reversed(CLASSES):
        _safe_unregister_class(cls)
