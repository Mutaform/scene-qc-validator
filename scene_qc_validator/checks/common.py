import re
import bmesh
import bpy
import mathutils


def _bmesh_from_obj(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    return bm


def _write_bmesh(obj, bm):
    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()


def _mesh_objects(objects):
    return [o for o in objects if o.type == 'MESH']


def _parse_name_list(text):
    return [t.strip() for t in text.split(",") if t.strip()]


def _strip_blender_numeric_suffix(name):
    return re.sub(r"\.\d{3}$", "", name)


def _clean_asset_name(name):
    name = _strip_blender_numeric_suffix(name)
    name = re.sub(r"^(SM|SK|M)_", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "Asset"


def _unique_id_name(collection, desired, current=None):
    if current and desired == current.name:
        return desired
    if collection.get(desired) is None:
        return desired
    index = 1
    while True:
        candidate = f"{desired}_{index:02d}"
        if collection.get(candidate) is None or (current and candidate == current.name):
            return candidate
        index += 1


def _object_project_name(obj):
    base = _clean_asset_name(obj.name)
    prefix = "SK" if obj.type == 'ARMATURE' or base.lower().startswith(("sk_", "skel", "skeleton", "rig")) else "SM"
    return _unique_id_name(bpy.data.objects, f"{prefix}_{base}", obj)


def _material_project_name(mat):
    base = _clean_asset_name(mat.name)
    return _unique_id_name(bpy.data.materials, f"M_{base}", mat)


__all__ = [name for name in globals() if not name.startswith("__")]
