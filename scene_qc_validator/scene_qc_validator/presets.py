import json
import os
import bpy


LEGACY_FLOAT_PARAMS = {
    "geo_zero_area": {
        "float_param_1": (0.0001, 1e-10),
    },
}


def _presets_dir():
    """Per-user, per-addon storage folder that survives addon updates."""
    base = bpy.utils.extension_path_user(__package__, path="presets", create=True)
    return base


def list_presets():
    d = _presets_dir()
    names = []
    for fname in os.listdir(d):
        if fname.endswith(".json"):
            names.append(fname[:-5])
    if "Default" not in names:
        names.insert(0, "Default")
    else:
        names.remove("Default")
        names.insert(0, "Default")
    return names


def preset_path(name):
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip()
    return os.path.join(_presets_dir(), f"{safe}.json")


def _serialize_checks(name, checks_collection):
    return {
        "name": name,
        "checks": [
            {
                "check_id": c.check_id,
                "enabled": c.enabled,
                "severity": c.severity,
                "float_param_1": c.float_param_1,
                "float_param_2": c.float_param_2,
                "int_param_1": c.int_param_1,
                "string_param_1": c.string_param_1,
                "bool_param_1": c.bool_param_1,
            }
            for c in checks_collection
        ],
    }


def _apply_checks(data, checks_collection):
    lookup = {c.check_id: c for c in checks_collection}
    for entry in data.get("checks", []):
        c = lookup.get(entry.get("check_id"))
        if not c:
            continue
        legacy_float_params = LEGACY_FLOAT_PARAMS.get(c.check_id, {})
        c.enabled = entry.get("enabled", c.enabled)
        c.severity = entry.get("severity", c.severity)
        float_param_1 = entry.get("float_param_1", c.float_param_1)
        if "float_param_1" in legacy_float_params:
            old, new = legacy_float_params["float_param_1"]
            if abs(float_param_1 - old) < 1e-7:
                float_param_1 = new
        c.float_param_1 = float_param_1
        c.float_param_2 = entry.get("float_param_2", c.float_param_2)
        c.int_param_1 = entry.get("int_param_1", c.int_param_1)
        c.string_param_1 = entry.get("string_param_1", c.string_param_1)
        c.bool_param_1 = entry.get("bool_param_1", c.bool_param_1)


def save_preset(name, checks_collection):
    data = _serialize_checks(name, checks_collection)
    with open(preset_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_preset(name, checks_collection):
    path = preset_path(name)
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _apply_checks(data, checks_collection)
    return True


def export_preset_file(filepath, name, checks_collection):
    """Write the current checklist config to an arbitrary path so it can be
    shared (e.g. committed to a project repo or sent to a teammate)."""
    data = _serialize_checks(name, checks_collection)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def import_preset_file(filepath, checks_collection):
    """Load a preset from an arbitrary .json path, apply it to the checklist,
    and also copy it into the local preset store so it shows in the menu.
    Returns the preset name on success, or None on failure."""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if "checks" not in data:
        return None
    _apply_checks(data, checks_collection)
    name = data.get("name") or os.path.splitext(os.path.basename(filepath))[0]
    # persist into the local store so it's selectable later
    try:
        save_preset(name, checks_collection)
    except OSError:
        pass
    return name


def delete_preset(name):
    if name == "Default":
        return False
    path = preset_path(name)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def ensure_default_preset(checks_collection):
    path = preset_path("Default")
    if not os.path.exists(path):
        save_preset("Default", checks_collection)
