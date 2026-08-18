"""Nanite closed geometry check.

Unreal's Nanite expects ingested geometry to read as sealed. A shell is
acceptable when it is watertight, or when its open border is pushed inside
neighbouring geometry so the opening leaves no visible gap or hole. A shell
that ends in mid-air, or that only partially reaches the surface it should sit
in, produces exactly the artefacts this check reports.

Coverage is decided per border sample point: the point is covered when at
least one neighbouring shell reports it as lying on or behind its surface.
Testing against the nearest point of each neighbour keeps the test local, so
neighbouring geometry does not need to be watertight itself - a flat panel
still correctly reports "behind me" for a knob pushed into it.
"""

from ..common import *

from mathutils import Vector
from mathutils.bvhtree import BVHTree


# The shared float_param_1 slot is drawn with two decimals, so the tolerance is
# authored in millimetres and converted to Blender units here.
DEFAULT_TOLERANCE_MM = 1.0

# Cached world-space shells per object, so a scene-wide validation run does not
# rebuild the same neighbour geometry once per validated object. The key is a
# cheap fingerprint of the mesh, so any edit invalidates the entry by itself.
_SHELL_CACHE = {}
_CACHE_LIMIT = 64


def _mesh_fingerprint(obj):
    mesh = obj.data
    vertex_count = len(mesh.vertices)
    sample = []
    if vertex_count:
        step = max(1, vertex_count // 8)
        for index in range(0, vertex_count, step):
            sample.append(tuple(round(c, 6) for c in mesh.vertices[index].co))
    return (
        vertex_count,
        len(mesh.polygons),
        tuple(round(value, 6) for row in obj.matrix_world for value in row),
        tuple(sample),
    )


def _world_bmesh(obj):
    """Return a private BMesh in world space with positional indices.

    Indices must match the live Edit Mode BMesh, because that is what the
    result selection operator indexes into.
    """
    mesh = obj.data
    if mesh.is_editmode:
        bm = bmesh.from_edit_mesh(mesh).copy()
    else:
        bm = bmesh.new()
        bm.from_mesh(mesh)
    bm.transform(obj.matrix_world)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    return bm


def _face_islands(bm):
    """Group faces into topologically connected shells."""
    visited = set()
    islands = []
    for seed in bm.faces:
        if seed.index in visited:
            continue
        visited.add(seed.index)
        stack = [seed]
        island = [seed]
        while stack:
            face = stack.pop()
            for edge in face.edges:
                for linked in edge.link_faces:
                    if linked.index not in visited:
                        visited.add(linked.index)
                        stack.append(linked)
                        island.append(linked)
        islands.append(island)
    return islands


def _build_shells(bm):
    """Describe every shell: its BVH input, its border, and its bounds."""
    shells = []
    for island in _face_islands(bm):
        coordinates = []
        index_map = {}
        polygons = []
        for face in island:
            polygon = []
            for vert in face.verts:
                if vert.index not in index_map:
                    index_map[vert.index] = len(coordinates)
                    coordinates.append(vert.co.copy())
                polygon.append(index_map[vert.index])
            polygons.append(polygon)

        border_edges = {}
        for face in island:
            for edge in face.edges:
                if len(edge.link_faces) == 1:
                    border_edges[edge.index] = edge

        # Sampling both ends and the midpoint catches a border that only
        # partially reaches into the surrounding geometry.
        samples = []
        for edge_index, edge in border_edges.items():
            start = edge.verts[0].co
            end = edge.verts[1].co
            samples.append((edge_index, start.copy()))
            samples.append((edge_index, end.copy()))
            samples.append((edge_index, (start + end) * 0.5))

        shells.append({
            "coordinates": coordinates,
            "polygons": polygons,
            "border_edges": sorted(border_edges),
            "samples": samples,
            "min": Vector((
                min(c.x for c in coordinates),
                min(c.y for c in coordinates),
                min(c.z for c in coordinates),
            )),
            "max": Vector((
                max(c.x for c in coordinates),
                max(c.y for c in coordinates),
                max(c.z for c in coordinates),
            )),
            "tree": None,
        })
    return shells


def _shell_tree(shell):
    if shell["tree"] is None:
        shell["tree"] = BVHTree.FromPolygons(
            shell["coordinates"], shell["polygons"], all_triangles=False
        )
    return shell["tree"]


def _object_shells(obj, use_cache=True):
    mesh = obj.data
    if not mesh.polygons and not mesh.is_editmode:
        return []

    # An Edit Mode mesh cannot be fingerprinted reliably, since the Mesh
    # datablock lags behind the live BMesh.
    use_cache = use_cache and not mesh.is_editmode
    key = obj.name
    if use_cache:
        cached = _SHELL_CACHE.get(key)
        fingerprint = _mesh_fingerprint(obj)
        if cached and cached[0] == fingerprint:
            return cached[1]

    bm = _world_bmesh(obj)
    shells = _build_shells(bm)
    bm.free()

    if use_cache:
        if len(_SHELL_CACHE) >= _CACHE_LIMIT:
            _SHELL_CACHE.clear()
        _SHELL_CACHE[key] = (fingerprint, shells)
    return shells


def _bounds_overlap(first, second, padding):
    return (
        first["min"].x - padding <= second["max"].x
        and second["min"].x - padding <= first["max"].x
        and first["min"].y - padding <= second["max"].y
        and second["min"].y - padding <= first["max"].y
        and first["min"].z - padding <= second["max"].z
        and second["min"].z - padding <= first["max"].z
    )


def _neighbour_objects(obj, ignore_pattern):
    """Mesh objects whose geometry may seal this object's open borders."""
    try:
        ignore = re.compile(ignore_pattern) if ignore_pattern else None
    except re.error:
        ignore = None

    scene = bpy.context.scene
    neighbours = []
    for other in scene.objects:
        if other is obj or other.type != 'MESH':
            continue
        if ignore is not None and ignore.match(other.name):
            continue
        if not other.data.polygons and not other.data.is_editmode:
            continue
        try:
            if not other.visible_get():
                continue
        except RuntimeError:
            pass
        neighbours.append(other)
    return neighbours


def _signed_distance(shell, point):
    """Distance from point to the shell surface, negative when behind it."""
    location, normal, _index, _distance = _shell_tree(shell).find_nearest(point)
    if location is None:
        return None
    return (point - location).dot(normal)


def check_nanite_closed_geometry(obj, item):
    tolerance_mm = item.float_param_1 if item.float_param_1 > 0.0 else DEFAULT_TOLERANCE_MM
    tolerance = tolerance_mm * 0.001
    own_shells = _object_shells(obj)
    if not own_shells:
        return []
    if not any(shell["border_edges"] for shell in own_shells):
        return []

    neighbour_shells = list(own_shells)
    if item.bool_param_1:
        for other in _neighbour_objects(obj, item.string_param_1):
            neighbour_shells.extend(_object_shells(other))

    stranded_shells = 0
    stranded_edges = set()
    gapped_shells = 0
    gapped_edges = set()
    largest_gap = 0.0

    for shell in own_shells:
        if not shell["border_edges"]:
            continue
        padding = max(tolerance, (shell["max"] - shell["min"]).length * 0.05)
        candidates = [
            other for other in neighbour_shells
            if other is not shell and _bounds_overlap(shell, other, padding)
        ]

        exposed_edges = set()
        exposed_samples = 0
        for edge_index, point in shell["samples"]:
            closest = None
            for candidate in candidates:
                distance = _signed_distance(candidate, point)
                if distance is None:
                    continue
                if closest is None or distance < closest:
                    closest = distance
                if closest < tolerance:
                    break
            if closest is not None and closest < tolerance:
                continue
            exposed_edges.add(edge_index)
            exposed_samples += 1
            if closest is not None and closest > largest_gap:
                largest_gap = closest

        if not exposed_edges:
            continue
        if exposed_samples == len(shell["samples"]):
            stranded_shells += 1
            stranded_edges |= exposed_edges
        else:
            gapped_shells += 1
            gapped_edges |= exposed_edges

    issues = []
    if stranded_shells:
        issues.append({
            "message": (
                f"{stranded_shells} open shell(s) sealed by nothing: "
                f"{len(stranded_edges)} border edge(s) face empty space"
            ),
            "element_ref": "e:" + ",".join(map(str, sorted(stranded_edges))),
        })
    if gapped_shells:
        issues.append({
            "message": (
                f"{gapped_shells} open shell(s) not fully embedded: "
                f"{len(gapped_edges)} border edge(s), gap up to "
                f"{largest_gap * 1000.0:.2f} mm"
            ),
            "element_ref": "e:" + ",".join(map(str, sorted(gapped_edges))),
        })
    return issues
