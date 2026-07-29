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


def _update_overlap_visual_uv_set(self, context):
    try:
        from .operators import overlap_visual
        overlap_visual.refresh_material_overlap_review(
            context,
            self.overlap_visual_uv_set_number,
        )
    except Exception as ex:
        print(
            "[Scene QC Validator] Overlap UV set update failed: "
            f"{ex}"
        )


def _refresh_padding_visual(self, context):
    if self.check_id != "uv_padding":
        return
    try:
        from .checks.mapping import padding
        padding.refresh_padding_visual(
            context,
            self.int_param_1,
            self.int_param_2,
        )
    except Exception as ex:
        print(
            "[Scene QC Validator] Padding update failed: "
            f"{ex}"
        )


def _sync_padding_input_fields(self):
    if self.check_id != "uv_padding":
        return
    self.padding_input_syncing = True
    try:
        self.padding_texture_input = str(self.int_param_2)
        self.padding_value_input = str(self.int_param_1)
    finally:
        self.padding_input_syncing = False


def _update_int_param_1(self, context):
    _sync_padding_input_fields(self)
    _refresh_padding_visual(self, context)


def _update_int_param_2(self, context):
    if self.check_id == "uv_padding":
        previous_size = max(
            1, self.padding_last_texture_size
        )
        current_size = max(1, self.int_param_2)
        if current_size != previous_size:
            self.int_param_1 = max(
                0,
                int(round(
                    self.int_param_1
                    * current_size
                    / previous_size
                )),
            )
        self.padding_last_texture_size = current_size
    _sync_padding_input_fields(self)
    _refresh_padding_visual(self, context)


def _update_padding_texture_input(self, context):
    if self.check_id != "uv_padding" or self.padding_input_syncing:
        return
    try:
        value = int(self.padding_texture_input.strip())
    except ValueError:
        return
    if value > 0 and value != self.int_param_2:
        self.int_param_2 = value


def _update_padding_value_input(self, context):
    if self.check_id != "uv_padding" or self.padding_input_syncing:
        return
    try:
        value = int(self.padding_value_input.strip())
    except ValueError:
        return
    value = max(0, value)
    if value != self.int_param_1:
        self.int_param_1 = value


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
    int_param_1: IntProperty(
        name="Param 1",
        default=0,
        update=_update_int_param_1,
    )
    int_param_2: IntProperty(
        name="Param 2",
        default=0,
        update=_update_int_param_2,
    )
    padding_last_texture_size: IntProperty(
        default=4096,
        options={'HIDDEN'},
    )
    padding_texture_input: StringProperty(
        name="Texture Size",
        default="4096",
        update=_update_padding_texture_input,
    )
    padding_value_input: StringProperty(
        name="Padding",
        default="16",
        update=_update_padding_value_input,
    )
    padding_input_syncing: BoolProperty(
        default=False,
        options={'HIDDEN'},
    )
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
    fix_in_progress: BoolProperty(default=False)
    fix_progress: FloatProperty(
        default=0.0,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
    )
    fix_progress_text: StringProperty(default="")
    show_check_settings: BoolProperty(name="Check Settings", default=False)
    overlap_visual_use_material_scope: BoolProperty(
        name="Check All Material Users",
        description=(
            "When enabled, Show Overlaps includes every visible mesh "
            "using the active object's material. When disabled, it "
            "reviews only the active object"
        ),
        default=False,
    )
    padding_visual_use_material_scope: BoolProperty(
        name="Check All Material Users",
        description=(
            "When enabled, Show Padding includes every visible mesh "
            "using the active object's material. When disabled, it "
            "reviews only the active object"
        ),
        default=False,
    )
    overlap_visual_uv_set_number: IntProperty(
        name="UV Set",
        description=(
            "One-based UV set number used by Show Overlaps"
        ),
        default=1,
        min=1,
        max=64,
        update=_update_overlap_visual_uv_set,
    )

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
