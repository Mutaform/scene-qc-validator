import json
import os
import bpy


LEGACY_FLOAT_PARAMS = {
    "geo_zero_area": {
        "float_param_1": (0.0001, 1e-10),
    },
}

# The studio checklist. Other bundled projects are client ones.
FACTORY_DEFAULT_PROJECT = "Mutaform_Default"


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
            "int_param_2": c.int_param_2,
            "string_param_1": c.string_param_1,
            "string_param_2": c.string_param_2,
            "bool_param_1": c.bool_param_1,
            "bool_param_2": c.bool_param_2,
        }
        for c in checks_collection
    ]


PARAM_SLOTS = ("float_param_1", "float_param_2", "int_param_1", "int_param_2",
               "string_param_1", "string_param_2", "bool_param_1", "bool_param_2")


def _registry_defaults(check_id):
    """Умолчания проверки из реестра - то, чем должен быть пустой слот.

    Пресет, в котором ключа нет, обязан получить именно их. Раньше такой слот
    оставался с тем, что лежало в нём от ПРОШЛОГО загруженного проекта: в
    Mutaform_Default нет `string_param_2` у имени материала, и после работы с
    ARDENA туда перетекал её шаблон `MI_{asset}` - студийный ассет начинало
    чинить в клиентское имя (найдено 2026-10-10). Касается любого слота, не
    только этого.
    """
    from . import checks as checks_mod

    definition = next(
        (d for d in checks_mod.CHECK_DEFINITIONS if d["id"] == check_id), None)
    if definition is None:
        return {}
    return {slot: definition[slot] for slot in PARAM_SLOTS if slot in definition}


def _apply_checks(data, checks_collection):
    lookup = {c.check_id: c for c in checks_collection}
    for entry in data.get("checks", []):
        c = lookup.get(entry.get("check_id"))
        if not c:
            continue
        if c.check_id == "uv_padding" and "int_param_2" in entry:
            # Padding rescales itself when the texture size changes, so that an
            # artist switching 4096 -> 2048 in the panel keeps the same relative
            # border. A preset states both numbers outright, so point the item
            # at the size it is arriving from and let the two values land as
            # written - otherwise "16 px at 2048" loads as 8 px.
            c.padding_last_texture_size = entry["int_param_2"]
        legacy_float_params = LEGACY_FLOAT_PARAMS.get(c.check_id, {})
        c.enabled = entry.get("enabled", c.enabled)
        c.severity = entry.get("severity", c.severity)
        # Пресет, где ключа нет, получает умолчание реестра, а не остаток от
        # прошлого проекта - см. _registry_defaults.
        defaults = _registry_defaults(c.check_id)

        def taken(slot):
            if slot in entry:
                return entry[slot]
            if slot in defaults:
                return defaults[slot]
            return getattr(c, slot)

        float_param_1 = taken("float_param_1")
        if "float_param_1" in legacy_float_params:
            old, new = legacy_float_params["float_param_1"]
            if abs(float_param_1 - old) < 1e-7:
                float_param_1 = new
        c.float_param_1 = float_param_1
        c.float_param_2 = taken("float_param_2")
        c.int_param_1 = taken("int_param_1")
        c.int_param_2 = taken("int_param_2")
        c.string_param_1 = taken("string_param_1")
        c.string_param_2 = taken("string_param_2")
        c.bool_param_1 = taken("bool_param_1")
        c.bool_param_2 = taken("bool_param_2")


def load_stage(project_name, stage_name, checks_collection, settings=None):
    data = _read_project(project_name)
    if not data:
        return False
    for stage in data.get("stages", []):
        if stage.get("name") == stage_name:
            _apply_checks(stage, checks_collection)
            if settings is not None:
                # Always written, blank included: switching to a project that
                # ignores nothing must drop the previous project's rule.
                settings.ignore_objects_regex = data.get("ignore_objects", "")
            return True
    return False


def save_project(project_name, stage_name, checks_collection, ignore_objects=None):
    project_name = project_name.strip()
    stage_name = stage_name.strip()
    if not project_name or not stage_name:
        return False
    data = _read_project(project_name) or {"name": project_name, "stages": []}
    data["name"] = project_name
    if ignore_objects is not None:
        data["ignore_objects"] = ignore_objects
    checks = _serialize_checks(checks_collection)
    for stage in data["stages"]:
        if stage.get("name") == stage_name:
            stage["checks"] = checks
            return _write_project(data)
    data["stages"].append({"name": stage_name, "checks": checks})
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
    """Project a scene falls back to when its own one is gone.

    The studio checklist wins over the alphabet: bundling a project whose name
    sorts before it (ARDENA) must not turn that client's rules into the default
    every new scene starts with.
    """
    names = list_projects()
    if FACTORY_DEFAULT_PROJECT in names:
        return FACTORY_DEFAULT_PROJECT
    return names[0] if names else ""


def load_preset(name, checks_collection, settings=None):
    stages = project_stage_names(name)
    if not stages:
        return False
    return load_stage(name, stages[0], checks_collection, settings)


def save_preset(name, checks_collection):
    return save_project(name, "Default", checks_collection)


def delete_preset(name):
    return delete_project(name)


def export_preset_file(filepath, name, checks_collection):
    return export_project_file(filepath, name)


def import_preset_file(filepath, checks_collection):
    return import_project_file(filepath)
