import bpy

from .. import checks as checks_mod
from .. import presets as presets_mod


CHECK_ID_MIGRATIONS = {
    "mat_allowed_types": "mat_material_name",
}

DEPRECATED_CHECK_IDS = {
    "geo_triangles_percentage",
    "nm_material_pattern",
    "uv_flipped",
}

DEFAULT_CHECK_PARAMS = {
    "geo_zero_area": {
        "float_param_1": 1e-10,
    },
    "mat_material_name": {
        "string_param_1": r"^m_[A-Za-z0-9_]+(?:_\d{2})?$",
    },
}

LEGACY_CHECK_PARAMS = {
    "geo_zero_area": {
        "float_param_1": 0.0001,
    },
    "mat_material_name": {
        "string_param_1": r"^m_[A-Za-z0-9_]+_01$",
    },
}


def _settings(context):
    return context.scene.sqc_settings


def _sync_check_item_metadata(item, definition):
    item.label = definition["label"]
    item.category = definition["category"]
    item.description = definition["description"]
    item.can_fix = definition.get("can_fix", False)
    item.fix_is_destructive = definition.get("fix_is_destructive", False)


def _add_check_item(collection, definition):
    item = collection.add()
    item.check_id = definition["id"]
    _sync_check_item_metadata(item, definition)
    item.enabled = definition.get("enabled", True)
    item.severity = definition.get("severity", 'FAIL')
    item.float_param_1 = definition.get("float_param_1", 0.0)
    item.float_param_2 = definition.get("float_param_2", 0.0)
    item.int_param_1 = definition.get("int_param_1", 0)
    item.string_param_1 = definition.get("string_param_1", "")
    item.bool_param_1 = definition.get("bool_param_1", True)
    return item


def ensure_checks_initialized_for_scene(scene):
    """Initialize all check items for a Scene without needing a full Context."""
    s = scene.sqc_settings
    for item in s.checks:
        item.check_id = CHECK_ID_MIGRATIONS.get(item.check_id, item.check_id)
        defaults = DEFAULT_CHECK_PARAMS.get(item.check_id, {})
        legacy = LEGACY_CHECK_PARAMS.get(item.check_id, {})
        if legacy.get("string_param_1") and item.string_param_1 == legacy["string_param_1"]:
            item.string_param_1 = defaults["string_param_1"]
        if defaults.get("string_param_1") and not item.string_param_1:
            item.string_param_1 = defaults["string_param_1"]
        if "float_param_1" in legacy and abs(item.float_param_1 - legacy["float_param_1"]) < 1e-7:
            item.float_param_1 = defaults["float_param_1"]
        if "float_param_1" in defaults and item.float_param_1 <= 0:
            item.float_param_1 = defaults["float_param_1"]
    seen = set()
    for index in range(len(s.checks) - 1, -1, -1):
        check_id = s.checks[index].check_id
        if check_id in DEPRECATED_CHECK_IDS or check_id in seen:
            s.checks.remove(index)
        else:
            seen.add(check_id)
    for index in range(len(s.results) - 1, -1, -1):
        if s.results[index].check_id in DEPRECATED_CHECK_IDS:
            s.results.remove(index)
    for index in range(len(s.muted) - 1, -1, -1):
        if s.muted[index].check_id in DEPRECATED_CHECK_IDS:
            s.muted.remove(index)
    existing = {item.check_id: item for item in s.checks}
    for d in checks_mod.CHECK_DEFINITIONS:
        item = existing.get(d["id"])
        if item:
            _sync_check_item_metadata(item, d)
        else:
            _add_check_item(s.checks, d)
    if len(s.checks) > 0:
        presets_mod.ensure_default_preset(s.checks)


def ensure_checks_initialized(context):
    ensure_checks_initialized_for_scene(context.scene)


def _muted_keys(settings):
    return {(item.object_name, item.check_id) for item in settings.muted}


def _set_result_muted(settings, result_item, muted):
    key = (result_item.object_name, result_item.check_id)
    existing = next((item for item in settings.muted if (item.object_name, item.check_id) == key), None)
    if muted and existing is None:
        item = settings.muted.add()
        item.object_name = result_item.object_name
        item.check_id = result_item.check_id
    elif not muted and existing is not None:
        index = next((i for i, item in enumerate(settings.muted) if item == existing), -1)
        if index >= 0:
            settings.muted.remove(index)
    result_item.muted = muted


def _refresh_pass_state(settings):
    settings.last_validation_passed = not any(
        r.severity == 'FAIL' and not r.muted
        for r in settings.results
    )


def _validation_targets(context, scope=None):
    s = _settings(context)
    scope = scope or s.validation_scope
    if scope == 'SELECTION':
        objects = context.selected_objects
    elif scope == 'VISIBLE_SCENE':
        objects = [o for o in context.scene.objects if o.visible_get()]
    else:
        objects = context.scene.objects
    return [o for o in objects if o.type == 'MESH']


def _scope_empty_message(scope):
    if scope == 'SELECTION':
        return "No selected mesh objects"
    if scope == 'VISIBLE_SCENE':
        return "No visible mesh objects in scene"
    return "No mesh objects in scene"


def _select_only(context, objects):
    previous_active = context.view_layer.objects.active
    previous_selection = list(context.selected_objects)
    for obj in previous_selection:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    context.view_layer.objects.active = objects[0] if objects else None
    return previous_active, previous_selection


def _restore_selection(context, snapshot):
    previous_active, previous_selection = snapshot
    for obj in context.selected_objects:
        obj.select_set(False)
    for obj in previous_selection:
        if context.scene.objects.get(obj.name):
            obj.select_set(True)
    if previous_active and context.scene.objects.get(previous_active.name):
        context.view_layer.objects.active = previous_active


def run_validation_logic(context):
    """Run enabled checks and return (targets_found, any_fail)."""
    ensure_checks_initialized(context)
    s = _settings(context)
    s.results.clear()

    targets = _validation_targets(context)
    if not targets:
        s.has_run_validation = True
        s.last_validation_passed = False
        return False, False

    muted_keys = _muted_keys(s)
    enabled_checks = []
    for check_item in s.checks:
        if not check_item.enabled:
            continue
        d = checks_mod.get_check_definition(check_item.check_id)
        if d:
            enabled_checks.append((check_item, d))

    any_fail = False
    for obj in targets:
        for check_item, d in enabled_checks:
            try:
                issues = d["run"](obj, check_item) or []
            except Exception as e:
                issues = [{"message": f"Check error: {e}", "element_ref": ""}]
            for issue in issues:
                r = s.results.add()
                r.check_id = check_item.check_id
                r.check_label = check_item.label
                r.category = check_item.category
                r.severity = check_item.severity
                r.object_name = obj.name
                r.message = issue.get("message", "")
                r.element_ref = issue.get("element_ref", "")
                r.can_fix = check_item.can_fix
                r.fix_is_destructive = check_item.fix_is_destructive
                r.muted = (r.object_name, r.check_id) in muted_keys
                if check_item.severity == 'FAIL' and not r.muted:
                    any_fail = True

    s.has_run_validation = True
    s.last_validation_passed = not any_fail
    return True, any_fail
