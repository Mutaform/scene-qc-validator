import json
import os
import bpy


LEGACY_FLOAT_PARAMS = {
    "geo_zero_area": {
        "float_param_1": (0.0001, 1e-10),
    },
}


def _addon_dir():
    return os.path.dirname(__file__)


def _projects_dir():
    return bpy.utils.extension_path_user(__package__, path="projects", create=True)


def _bundled_projects_dir():
    return os.path.join(_addon_dir(), "projects")


def _safe_name(name):
    return "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip()


def _json_names_in_dir(directory):
    if not os.path.isdir(directory):
        return []
    return sorted(
        os.path.splitext(fname)[0]
        for fname in os.listdir(directory)
        if fname.endswith(".json")
    )


def bundled_project_names():
    return _json_names_in_dir(_bundled_projects_dir())


def user_project_names():
    return _json_names_in_dir(_projects_dir())


def list_projects():
    bundled = bundled_project_names()
    users = [name for name in user_project_names() if name not in bundled]
    return bundled + sorted(users)


def is_factory_project(name):
    return name in bundled_project_names()


def is_factory_preset(name):
    return is_factory_project(name)


def project_path(name):
    return os.path.join(_projects_dir(), f"{_safe_name(name)}.json")


def bundled_project_path(name):
    return os.path.join(_bundled_projects_dir(), f"{_safe_name(name)}.json")


def _project_read_path(name):
    user_path = project_path(name)
    if os.path.exists(user_path):
        return user_path
    if is_factory_project(name):
        return bundled_project_path(name)
    return user_path


def _read_project(name):
    path = _project_read_path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data.get("stages"), list):
        return None
    return data


def _write_project(data):
    name = data.get("name", "").strip()
    if not name:
        return False
    os.makedirs(_projects_dir(), exist_ok=True)
    with open(project_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return True


def project_stage_names(project_name):
    data = _read_project(project_name)
    if not data:
        return []
    return [
        stage.get("name", "")
        for stage in data.get("stages", [])
        if stage.get("name")
    ]


def _serialize_checks(checks_collection):
    return [
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
    ]


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


def load_stage(project_name, stage_name, checks_collection):
    data = _read_project(project_name)
    if not data:
        return False
    for stage in data.get("stages", []):
        if stage.get("name") == stage_name:
            _apply_checks(stage, checks_collection)
            return True
    return False


def save_project(project_name, stage_name, checks_collection):
    project_name = project_name.strip()
    stage_name = stage_name.strip()
    if not project_name or not stage_name:
        return False
    data = _read_project(project_name) or {"name": project_name, "stages": []}
    data["name"] = project_name
    checks = _serialize_checks(checks_collection)
    for stage in data["stages"]:
        if stage.get("name") == stage_name:
            stage["checks"] = checks
            return _write_project(data)
    data["stages"].append({"name": stage_name, "checks": checks})
    return _write_project(data)


def copy_factory_project_as(project_name, new_name):
    data = _read_project(project_name)
    new_name = new_name.strip()
    if not data or not new_name or is_factory_project(new_name):
        return False
    data = json.loads(json.dumps(data))
    data["name"] = new_name
    return _write_project(data)


def delete_project(project_name):
    if is_factory_project(project_name):
        path = project_path(project_name)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False
    path = project_path(project_name)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def delete_stage(project_name, stage_name):
    data = _read_project(project_name)
    if not data:
        return False
    original_len = len(data.get("stages", []))
    data["stages"] = [
        stage for stage in data.get("stages", [])
        if stage.get("name") != stage_name
    ]
    if len(data["stages"]) == original_len:
        return False
    return _write_project(data)


def export_project_file(filepath, project_name):
    data = _read_project(project_name)
    if not data:
        return False
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return True


def import_project_file(filepath):
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    name = data.get("name") or os.path.splitext(os.path.basename(filepath))[0]
    if not isinstance(data.get("stages"), list):
        return None
    if is_factory_project(name):
        name = f"{name} Custom"
    data["name"] = name
    return name if _write_project(data) else None


def ensure_default_project(checks_collection):
    names = list_projects()
    return names[0] if names else ""


def list_presets():
    return list_projects()


def load_preset(name, checks_collection):
    stages = project_stage_names(name)
    if not stages:
        return False
    return load_stage(name, stages[0], checks_collection)


def save_preset(name, checks_collection):
    return save_project(name, "Default", checks_collection)


def delete_preset(name):
    return delete_project(name)


def export_preset_file(filepath, name, checks_collection):
    return export_project_file(filepath, name)


def import_preset_file(filepath, checks_collection):
    return import_project_file(filepath)


def ensure_default_preset(checks_collection):
    ensure_default_project(checks_collection)
