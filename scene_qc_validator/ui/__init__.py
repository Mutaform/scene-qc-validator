from . import icons
from .lists import SQC_UL_checklist, SQC_UL_results
from .presets_menu import SQC_MT_presets
from .main_panel import SQC_PT_main
from .review_scene_panel import SQC_PT_scene_review
from .checklist_panel import SQC_PT_checklist
from .results_panel import SQC_PT_results
from . import header
from .header import SQC_PT_header_menu


CLASSES = (
    SQC_UL_checklist,
    SQC_UL_results,
    SQC_MT_presets,
    SQC_PT_main,
    SQC_PT_scene_review,
    SQC_PT_checklist,
    SQC_PT_results,
    SQC_PT_header_menu,
)


def _safe_register_class(cls):
    import bpy
    try:
        bpy.utils.unregister_class(cls)
    except RuntimeError:
        pass
    bpy.utils.register_class(cls)


def _safe_unregister_class(cls):
    import bpy
    try:
        bpy.utils.unregister_class(cls)
    except RuntimeError:
        pass


def register():
    import bpy
    icons.register()
    for cls in CLASSES:
        _safe_register_class(cls)
    header.install()


def unregister():
    import bpy
    header.remove()
    for cls in reversed(CLASSES):
        _safe_unregister_class(cls)
    icons.unregister()
