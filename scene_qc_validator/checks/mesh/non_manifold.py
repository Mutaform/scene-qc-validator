from ..common import *


COINCIDENT_VERTEX_TOLERANCE = 1e-7


def _face_fans(vert):
    """Group a vertex's linked faces into topologically connected fans."""
    unvisited = set(vert.link_faces)
    fans = []
    while unvisited:
        fan = set()
        stack = [unvisited.pop()]
        while stack:
            face = stack.pop()
            fan.add(face)
            for edge in face.edges:
                if vert not in edge.verts:
                    continue
                for adjacent_face in edge.link_faces:
                    if adjacent_face in unvisited:
                        unvisited.remove(adjacent_face)
                        stack.append(adjacent_face)
        fans.append(fan)
    return fans


def _non_manifold_vertex_indices(bm):
    """Return vertices whose adjacent faces form more than one fan.

    A boundary vertex has one *open* fan, which is valid for the validator.
    A vertex where separate shells touch only at that point has two or more
    disconnected fans and is non-manifold (the case detected by Maya Cleanup).
    """
    bad = []
    for vert in bm.verts:
        if len(_face_fans(vert)) > 1:
            bad.append(vert.index)
    return bad


def _vertex_islands(bm):
    """Return topological vertex islands without relying on Object Mode."""
    islands = []
    visited = set()
    for seed in bm.verts:
        if seed in visited:
            continue
        island = {seed}
        stack = [seed]
        visited.add(seed)
        while stack:
            vert = stack.pop()
            for edge in vert.link_edges:
                neighbour = edge.other_vert(vert)
                if neighbour not in visited:
                    visited.add(neighbour)
                    island.add(neighbour)
                    stack.append(neighbour)
        islands.append(island)
    return islands


def _coincident_vertex_indices(bm, tolerance=COINCIDENT_VERTEX_TOLERANCE):
    """Return vertices belonging to unwelded geometry at the same position.

    These duplicate vertices make parts of a mesh look connected while their
    topology remains split. Maya Cleanup reports this class of defect as
    non-manifold geometry. A tiny tolerance only absorbs floating-point noise;
    it does not treat nearby intentional vertices as duplicates.
    """
    buckets = {}
    bad = set()
    tolerance_sq = tolerance * tolerance
    island_by_vert = {
        vert: island_index
        for island_index, island in enumerate(_vertex_islands(bm))
        for vert in island
    }

    for vert in bm.verts:
        cell = tuple(round(coordinate / tolerance) for coordinate in vert.co)
        for x in range(cell[0] - 1, cell[0] + 2):
            for y in range(cell[1] - 1, cell[1] + 2):
                for z in range(cell[2] - 1, cell[2] + 2):
                    for other in buckets.get((x, y, z), []):
                        if (
                            island_by_vert[vert] == island_by_vert[other]
                            and (vert.co - other.co).length_squared <= tolerance_sq
                        ):
                            bad.add(vert.index)
                            bad.add(other.index)
        buckets.setdefault(cell, []).append(vert)

    return sorted(bad)


def _editable_bmesh(obj):
    """Return a BMesh and whether it is Blender's live edit BMesh."""
    if obj.mode == 'EDIT' or obj.data.is_editmode:
        if bpy.context.view_layer.objects.active != obj:
            bpy.context.view_layer.objects.active = obj
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        return bm, True
    return _bmesh_from_obj(obj), False


def _finish_edit(obj, bm, is_edit_bmesh):
    if is_edit_bmesh:
        bmesh.update_edit_mesh(obj.data)
    else:
        _write_bmesh(obj, bm)


def _split_one_disconnected_face_fan(bm):
    """Separate one vertex's independent face fans without moving vertices."""
    for vert in bm.verts:
        fans = _face_fans(vert)
        if len(fans) <= 1:
            continue
        for fan in fans[1:]:
            fan_edges = list({
                edge
                for face in fan
                for edge in face.edges
                if vert in edge.verts
            })
            bmesh.utils.vert_separate(vert, fan_edges)
        return True
    return False


def _weld_each_island(bm):
    """Weld duplicates only within each topological island.

    This is the BMesh equivalent of selecting one Edit Mode sub-object at a
    time before running Merge by Distance. Other islands are a strict mask and
    cannot be welded to the current island.
    """
    changed = False
    for island in _vertex_islands(bm):
        if len(island) < 2:
            continue
        before = len(island)
        bmesh.ops.remove_doubles(
            bm, verts=list(island), dist=COINCIDENT_VERTEX_TOLERANCE
        )
        if len(island) != before:
            changed = True
    return changed


def check_non_manifold(obj, item):
    bm, is_edit_bmesh = _editable_bmesh(obj)
    # bmesh.Edge.is_manifold is False for boundary edges too. Open geometry is
    # common and intentional in production assets, so only flag edges shared
    # by three or more faces.
    non_manifold_edges = [e.index for e in bm.edges if len(e.link_faces) > 2]
    non_manifold_vertices = _non_manifold_vertex_indices(bm)
    coincident_vertices = _coincident_vertex_indices(bm)
    if not is_edit_bmesh:
        bm.free()

    issues = []
    if non_manifold_edges:
        issues.append({
            "message": f"{len(non_manifold_edges)} edge(s) shared by 3 or more faces",
            "element_ref": "e:" + ",".join(map(str, non_manifold_edges)),
            "can_fix": True,
        })
    if non_manifold_vertices:
        issues.append({
            "message": f"{len(non_manifold_vertices)} vertex/vertices with disconnected face fans",
            "element_ref": "v:" + ",".join(map(str, non_manifold_vertices)),
            "can_fix": True,
        })
    if coincident_vertices:
        issues.append({
            "message": f"Unwelded geometry: {len(coincident_vertices)} vertex/vertices share positions",
            "element_ref": "v:" + ",".join(map(str, coincident_vertices)),
            "can_fix": True,
        })
    return issues


def fix_non_manifold(obj, item, result):
    """Split invalid fans, then weld each resulting Edit Mode sub-object.

    No vertex is moved and no face is removed. The per-island weld is masked
    from all other islands, so separate sub-objects cannot be accidentally
    welded together.
    """
    bm, is_edit_bmesh = _editable_bmesh(obj)
    has_issues = (
        bool(_coincident_vertex_indices(bm))
        or any(len(edge.link_faces) > 2 for edge in bm.edges)
        or bool(_non_manifold_vertex_indices(bm))
    )
    if not has_issues:
        if not is_edit_bmesh:
            bm.free()
        return False

    radial_edges = [edge for edge in bm.edges if len(edge.link_faces) > 2]
    if radial_edges:
        bmesh.ops.split_edges(bm, edges=radial_edges)

    max_passes = max(1, len(bm.verts) * 4)
    for _ in range(max_passes):
        if not _split_one_disconnected_face_fan(bm):
            break

    _weld_each_island(bm)
    _finish_edit(obj, bm, is_edit_bmesh)
    return True
