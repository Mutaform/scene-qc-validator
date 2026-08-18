"""Check registry for Scene QC Validator."""

from .mesh.ngons import check_ngons, fix_ngons
from .mesh.non_manifold import check_non_manifold, fix_non_manifold
from .mesh.zero_area import check_zero_area_faces, fix_zero_area_faces
from .mesh.zero_length import check_zero_length_edges, fix_zero_length_edges
from .mesh.has_soft_edges import check_has_soft_edges, fix_has_soft_edges
from .mesh.non_planar import check_non_planar_faces, fix_non_planar_faces
from .mesh.concave_faces import check_concave_faces, fix_concave_faces
from .mesh.duplicate_faces import check_duplicate_faces, fix_duplicate_faces
from .mesh.loose_geometry import check_loose_geometry, fix_loose_geometry
from .mesh.animation import check_animation_keys, fix_animation_keys

from .objects.unapplied_transform import (
    check_unapplied_transform, fix_unapplied_transform,
)
from .objects.pivot_world_origin import (
    check_pivot_world_origin, fix_pivot_world_origin,
)
from .objects.pivot_center import check_pivot_center
from .objects.object_name_pattern import (
    check_object_name_pattern, fix_object_name_pattern,
)
from .objects.nanite_closed_geometry import check_nanite_closed_geometry

from .mapping.missing_uv import check_missing_uv
from .mapping.uv_set_count import check_uv_set_count
from .mapping.uv_set_names import check_uv_set_names, fix_uv_set_names
from .mapping.single_uv_tile import check_single_uv_tile
from .mapping.no_hard_edge_on_uv_borders import (
    check_no_hard_edge_on_uv_borders, fix_no_hard_edge_on_uv_borders,
)
from .mapping.random_sharp import check_random_sharp, fix_random_sharp
from .mapping.overlapped_uv import check_uv_overlap, fix_uv_overlap
from .mapping.padding import check_padding
from .mapping.unaligned_uv_edges import (
    check_unaligned_uv_edges, fix_unaligned_uv_edges,
)

from .material.missing_material import check_missing_material
from .material.material_count import check_material_count
from .material.material_name import check_material_name, fix_material_name


TAB_ITEMS = [
    ('MESH', "Mesh", "Geometry and topology checks", 'MESH_DATA', 0),
    ('OBJECTS', "Objects", "Transform and naming checks", 'OBJECT_DATA', 1),
    ('MAPPING', "Mapping", "UV checks", 'UV', 2),
    ('MATERIAL', "Material", "Material checks", 'MATERIAL', 3),
]

TAB_CATEGORY_MAP = {
    'MESH': {'GEOMETRY'},
    'OBJECTS': {'TRANSFORM', 'NAMING', 'NANITE'},
    'MAPPING': {'UV'},
    'MATERIAL': {'MATERIAL'},
}

CHECKLIST_HIDDEN_IDS = {
    "uv_padding",
}



CHECK_DEFINITIONS = [
    dict(id="geo_has_soft_edges", label="Too Much Hard Edge", category='GEOMETRY',
         description="Mesh should not have every edge marked hard/sharp",
         run=check_has_soft_edges, fix=fix_has_soft_edges, can_fix=True,
         fix_is_destructive=False),
    dict(id="geo_ngons", label="N-Gons", category='GEOMETRY',
         description="Faces with more than 4 vertices",
         run=check_ngons, fix=fix_ngons, can_fix=True,
         fix_is_destructive=True),
    dict(id="geo_non_manifold", label="Non-Manifold Geometry", category='GEOMETRY',
         description="Fixes invalid topology by splitting face fans, then welding only within each topological island",
         run=check_non_manifold, fix=fix_non_manifold, can_fix=True,
         fix_is_destructive=False),
    dict(id="geo_zero_area", label="Zero Area Faces", category='GEOMETRY',
         description="Faces with area below tolerance",
         run=check_zero_area_faces, fix=fix_zero_area_faces, can_fix=True,
         fix_is_destructive=True, float_param_1=1e-10),
    dict(id="geo_zero_length", label="Zero Length Edges", category='GEOMETRY',
         description="Edges shorter than tolerance",
         run=check_zero_length_edges, fix=fix_zero_length_edges, can_fix=True,
         fix_is_destructive=True, float_param_1=0.0001),
    dict(id="geo_non_planar", label="Non-Planar Faces", category='GEOMETRY',
         description="Faces whose vertices do not lie on one plane",
         run=check_non_planar_faces, fix=fix_non_planar_faces, can_fix=True,
         fix_is_destructive=True, float_param_1=0.00001),
    dict(id="geo_concave_faces", label="Concave Faces", category='GEOMETRY',
         description="Faces with concave corners",
         run=check_concave_faces, fix=fix_concave_faces, can_fix=True,
         fix_is_destructive=True),
    dict(id="geo_duplicate_faces", label="Duplicate Faces", category='GEOMETRY',
         description="Faces sharing the same vertex set",
         run=check_duplicate_faces, fix=fix_duplicate_faces, can_fix=True,
         fix_is_destructive=True),
    dict(id="geo_loose", label="Loose Geometry", category='GEOMETRY',
         description="Vertices or edges not part of any face",
         run=check_loose_geometry, fix=fix_loose_geometry, can_fix=True,
         fix_is_destructive=True),
    dict(id="geo_animation_keys", label="Animation Keys", category='GEOMETRY',
         description="Mesh object, mesh data, or shape keys have animation data",
         run=check_animation_keys, fix=fix_animation_keys, can_fix=True,
         fix_is_destructive=False),

    dict(id="tr_unapplied", label="Unapplied Transform", category='TRANSFORM',
         description="Object has non-default location/rotation/scale",
         run=check_unapplied_transform, fix=fix_unapplied_transform, can_fix=True,
         fix_is_destructive=True, string_param_1="loc,rot,scale"),
    dict(id="tr_world_origin", label="Pivot Not At World Origin", category='TRANSFORM',
         description="Object origin should be at world 0,0,0",
         run=check_pivot_world_origin, fix=fix_pivot_world_origin, can_fix=True,
         fix_is_destructive=False, float_param_1=0.001),
    dict(id="tr_pivot_center", label="Pivot Not Centered", category='TRANSFORM',
         description="Object origin should be centered on its geometry bounds",
         run=check_pivot_center, fix=None, can_fix=False),

    dict(id="uv_missing", label="Missing UV Map", category='UV',
         description="Mesh has no UV map",
         run=check_missing_uv, fix=None, can_fix=False),
    dict(id="uv_set_count", label="UV Sets Count", category='UV',
         description="Too many UV maps on one mesh",
         run=check_uv_set_count, fix=None, can_fix=False, int_param_1=1),
    dict(id="uv_single_tile", label="Shells Outside 0-1 Square", category='UV',
         description="Every UV set must keep all UV shells inside the first 0-1 UDIM square",
         run=check_single_uv_tile, fix=None, can_fix=False,
         float_param_1=0.001),
    dict(id="uv_set_names", label="UV Set Names", category='UV',
         description="Replace Blender default UVMap names with map1, map2, ...",
         run=check_uv_set_names, fix=fix_uv_set_names, can_fix=True,
         fix_is_destructive=False),
    dict(id="uv_overlap", label="Overlapped UV", category='UV',
         description="Finds overlapping UVs in UDIM 1001 and expands hits to complete UV islands",
         run=check_uv_overlap, fix=fix_uv_overlap, can_fix=True,
         string_param_1=".+", bool_param_1=True, float_param_1=1e-10, int_param_1=250000),
    dict(id="uv_padding", label="Padding", category='UV',
         description="Interactive UV-island padding preview in the UV Editor",
         run=check_padding, fix=None, can_fix=False,
         int_param_1=16, int_param_2=4096),
    dict(id="uv_no_hard_edge_on_uv_borders", label="No Hard Edge On UV Borders", category='UV',
         description="Every UV-shell border edge must be marked sharp",
         run=check_no_hard_edge_on_uv_borders, fix=fix_no_hard_edge_on_uv_borders, can_fix=True,
         fix_is_destructive=False),
    dict(id="uv_random_sharp", label="Random Sharp", category='UV',
         description="Sharp edges should match UV border edges",
         run=check_random_sharp, fix=fix_random_sharp, can_fix=True,
         fix_is_destructive=False, float_param_1=0.001),
    dict(id="uv_unaligned_edges", label="Unaligned UV Edges", category='UV',
         description="Find slightly off-axis borders on predominantly rectilinear UV shells",
         run=check_unaligned_uv_edges, fix=fix_unaligned_uv_edges, can_fix=True,
         fix_is_destructive=False,
         float_param_1=0.1, float_param_2=0.75),

    dict(id="obj_nanite_closed_geometry", label="Nanite Closed Geometry",
         category='NANITE',
         description="Open shells must be embedded in other geometry so Nanite sees no gaps or holes",
         run=check_nanite_closed_geometry, fix=None, can_fix=False,
         float_param_1=1.0, bool_param_1=True,
         string_param_1=r"^(UCX|UBX|USP|UCP)_"),

    dict(id="nm_object_pattern", label="Object Name Pattern", category='NAMING',
         description="Object name must match a regex pattern",
         run=check_object_name_pattern, fix=fix_object_name_pattern, can_fix=True,
         fix_is_destructive=False, string_param_1=r"^(SM|SK)_[A-Za-z0-9_]+$"),
    dict(id="mat_missing", label="Missing Material", category='MATERIAL',
         description="Faces or object without an assigned material",
         run=check_missing_material, fix=None, can_fix=False),
    dict(id="mat_material_count", label="Material Count", category='MATERIAL',
         description="Too many materials assigned to one mesh",
         run=check_material_count, fix=None, can_fix=False,
         int_param_1=1),
    dict(id="mat_material_name", label="Material Name", category='MATERIAL',
         description="Material names must match the allowed pattern, for example m_body or m_body_01",
         run=check_material_name, fix=fix_material_name, can_fix=True,
         fix_is_destructive=False,
         string_param_1=r"^m_[A-Za-z0-9_]+(?:_\d{2})?$"),
]


def get_check_definition(check_id):
    for d in CHECK_DEFINITIONS:
        if d["id"] == check_id:
            return d
    return None
