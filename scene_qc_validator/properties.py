import bpy
from bpy.types import PropertyGroup
from bpy.props import (
    StringProperty,
    BoolProperty,
    FloatProperty,
    IntProperty,
    EnumProperty,
    CollectionProperty,
    PointerProperty,
)

from . import checks as checks_mod

CATEGORY_ITEMS = [
    ('GEOMETRY', "Geometry", "Mesh topology checks"),
    ('TRANSFORM', "Transform", "Object transform checks"),
    ('UV', "UV", "UV mapping checks"),
    ('NAMING', "Naming", "Object / material naming checks"),
    ('MATERIAL', "Material", "Material assignment checks"),
]

SEVERITY_ITEMS = [
    ('FAIL', "Fail", "Reported as a blocking validation issue"),
    ('INFO', "Info", "Reported as a non-blocking validation note"),
]


def _update_active_result_selection(self, context):
    try:
        from . import operators
        operators.select_result_by_index(context, self.active_result_index)
    except Exception as ex:
        print(f"[Scene QC Validator] Result auto-select failed: {ex}")


def _update_result_mute(self, context):
    settings = context.scene.sqc_settings
    key = (self.object_name, self.check_id)
    existing_index = -1
    for index, item in enumerate(settings.muted):
        if (item.object_name, item.check_id) == key:
            existing_index = index
            break
    if self.muted and existing_index < 0:
        item = settings.muted.add()
        item.object_name = self.object_name
        item.check_id = self.check_id
    elif not self.muted and existing_index >= 0:
        settings.muted.remove(existing_index)
    settings.last_validation_passed = not any(
        result.severity == 'FAIL' and not result.muted
        for result in settings.results
    )


def _update_uv_checker_tiling(self, context):
    try:
        from . import operators
        operators.update_uv_checker_tiling(context.scene.sqc_settings.uv_checker_tiling)
    except Exception as ex:
        print(f"[Scene QC Validator] UV checker tiling update failed: {ex}")


VALIDATION_SCOPE_ITEMS = [
    ('SELECTION', "Selection", "Validate only selected mesh objects"),
    ('VISIBLE_SCENE', "Visible Scene", "Validate every visible mesh object in the active scene"),
    ('ENTIRE_SCENE', "Entire Scene", "Validate every mesh object in the active scene"),
]


class SQC_CheckItem(PropertyGroup):
    """A single toggleable check with its parameters, stored on the Scene
    so it is (de)serialized together with presets."""

    check_id: StringProperty(name="Check ID")
    label: StringProperty(name="Label")
    category: EnumProperty(name="Category", items=CATEGORY_ITEMS)
    description: StringProperty(name="Description")

    enabled: BoolProperty(name="Enabled", default=True)
    severity: EnumProperty(name="Severity", items=SEVERITY_ITEMS, default='FAIL')

    can_fix: BoolProperty(name="Auto-fixable", default=False)
    fix_is_destructive: BoolProperty(
        name="Destructive Fix",
        description="Fix changes topology/data rather than just selecting it",
        default=False,
    )

    # Generic parameter slots so we don't need a bespoke PropertyGroup per check.
    float_param_1: FloatProperty(name="Param 1", default=0.0)
    float_param_2: FloatProperty(name="Param 2", default=0.0)
    int_param_1: IntProperty(name="Param 1", default=0)
    string_param_1: StringProperty(
        name="Param 1",
        description="Comma separated list of allowed prefixes/suffixes, or a regex pattern",
        default="",
    )
    bool_param_1: BoolProperty(name="Param 1", default=True)


class SQC_ResultItem(PropertyGroup):
    """One reported issue after running Validate."""
    check_id: StringProperty()
    check_label: StringProperty()
    category: EnumProperty(items=CATEGORY_ITEMS)
    severity: EnumProperty(items=SEVERITY_ITEMS)
    object_name: StringProperty()
    message: StringProperty()
    can_fix: BoolProperty(default=False)
    fix_is_destructive: BoolProperty(default=False)
    muted: BoolProperty(
        name="Ignore",
        description="Ignore this issue for this object",
        default=False,
        update=_update_result_mute,
    )
    # indices of mesh elements to (re)select on the target object, stored as "v:1,2,3;e:4,5;f:6"
    element_ref: StringProperty(default="")


class SQC_MutedItem(PropertyGroup):
    """A persistent record of a muted (object, check) pair so mutes survive
    re-validation, which rebuilds the results collection from scratch."""
    object_name: StringProperty()
    check_id: StringProperty()


class SQC_Settings(PropertyGroup):
    checks: CollectionProperty(type=SQC_CheckItem)
    results: CollectionProperty(type=SQC_ResultItem)
    muted: CollectionProperty(type=SQC_MutedItem)

    active_check_index: IntProperty(default=0)
    active_result_index: IntProperty(default=0, update=_update_active_result_selection)

    result_filter: EnumProperty(
        name="Show",
        items=[
            ('ALL', "All Results", ""),
            ('FAIL', "Fail Only", ""),
            ('FAIL_INFO', "Fail and Info", ""),
            ('FIXABLE', "Fixable Only", ""),
        ],
        default='ALL',
    )

    validation_scope: EnumProperty(
        name="Validation Scope",
        description="Objects that Validate will process",
        items=VALIDATION_SCOPE_ITEMS,
        default='SELECTION',
    )

    active_project_name: StringProperty(name="Active Project", default="Mutaform_Default")
    active_stage_name: StringProperty(name="Active Stage", default="01_Blockout")
    applied_stage_key: StringProperty(name="Applied Stage Key", default="")
    active_preset_name: StringProperty(name="Active Preset", default="Mutaform_Default")
    new_preset_name: StringProperty(name="New Preset Name", default="My Preset")
    new_project_name: StringProperty(name="New Project Name", default="My Project")
    new_stage_name: StringProperty(name="New Stage Name", default="New Stage")

    checklist_tab: EnumProperty(
        name="Checklist Tab",
        items=[(t[0], t[1], t[2], t[3], t[4]) for t in checks_mod.TAB_ITEMS],
        default='MESH',
    )

    last_validation_passed: BoolProperty(default=False)
    has_run_validation: BoolProperty(default=False)
    show_check_settings: BoolProperty(name="Check Settings", default=False)

    uv_checker_tiling: FloatProperty(
        name="Checker Tiling",
        description="UV checker texture repeat amount",
        default=0.25,
        min=0.25,
        max=50.0,
        soft_min=0.25,
        soft_max=20.0,
        precision=2,
        update=_update_uv_checker_tiling,
    )


CLASSES = (
    SQC_CheckItem,
    SQC_ResultItem,
    SQC_MutedItem,
    SQC_Settings,
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
    if hasattr(bpy.types.Scene, "sqc_settings"):
        del bpy.types.Scene.sqc_settings
    for cls in CLASSES:
        _safe_register_class(cls)
    bpy.types.Scene.sqc_settings = PointerProperty(type=SQC_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "sqc_settings"):
        del bpy.types.Scene.sqc_settings
    for cls in reversed(CLASSES):
        _safe_unregister_class(cls)
