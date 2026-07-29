"""Overlapped UV validation, repair, selection, and UV Editor display."""

from dataclasses import dataclass, field
import re
import uuid

import bmesh
import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from . import _uv_overlay


# ---------------------------------------------------------------------------
# Validation


_BAKE_UDIM_MIN = 0.0
_BAKE_UDIM_MAX = 1.0
_BAKE_UDIM_AREA_EPSILON = 1e-12


def _clip_uv_polygon_to_bake_udim(uv_points):
    polygon = [
        (float(point[0]), float(point[1]))
        for point in uv_points
    ]

    def clip_to_boundary(points, axis, boundary, keep_greater):
        if not points:
            return []
        clipped = []
        previous = points[-1]
        previous_inside = (
            previous[axis] >= boundary
            if keep_greater
            else previous[axis] <= boundary
        )
        for current in points:
            current_inside = (
                current[axis] >= boundary
                if keep_greater
                else current[axis] <= boundary
            )
            if current_inside != previous_inside:
                axis_delta = current[axis] - previous[axis]
                if axis_delta != 0.0:
                    factor = (
                        (boundary - previous[axis]) / axis_delta
                    )
                    clipped.append((
                        previous[0]
                        + factor * (current[0] - previous[0]),
                        previous[1]
                        + factor * (current[1] - previous[1]),
                    ))
            if current_inside:
                clipped.append(current)
            previous = current
            previous_inside = current_inside
        return clipped

    for axis, boundary, keep_greater in (
        (0, _BAKE_UDIM_MIN, True),
        (0, _BAKE_UDIM_MAX, False),
        (1, _BAKE_UDIM_MIN, True),
        (1, _BAKE_UDIM_MAX, False),
    ):
        polygon = clip_to_boundary(
            polygon, axis, boundary, keep_greater
        )
    return polygon


def _uv_polygon_area(uv_points):
    if len(uv_points) < 3:
        return 0.0
    return abs(sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(
            uv_points, uv_points[1:] + uv_points[:1]
        )
    )) * 0.5


def _cross_2d(first, second):
    return first[0] * second[1] - first[1] * second[0]


def _clip_polygon_to_triangle(subject_polygon, clip_triangle):
    orientation = _cross_2d(
        (
            clip_triangle[1][0] - clip_triangle[0][0],
            clip_triangle[1][1] - clip_triangle[0][1],
        ),
        (
            clip_triangle[2][0] - clip_triangle[0][0],
            clip_triangle[2][1] - clip_triangle[0][1],
        ),
    )
    if abs(orientation) <= _BAKE_UDIM_AREA_EPSILON:
        return []
    orientation_sign = 1.0 if orientation > 0.0 else -1.0
    polygon = list(subject_polygon)

    for edge_index in range(3):
        if not polygon:
            break
        edge_start = clip_triangle[edge_index]
        edge_end = clip_triangle[(edge_index + 1) % 3]
        edge_vector = (
            edge_end[0] - edge_start[0],
            edge_end[1] - edge_start[1],
        )
        clipped = []
        previous = polygon[-1]
        previous_distance = orientation_sign * _cross_2d(
            edge_vector,
            (
                previous[0] - edge_start[0],
                previous[1] - edge_start[1],
            ),
        )
        previous_inside = (
            previous_distance >= -_BAKE_UDIM_AREA_EPSILON
        )

        for current in polygon:
            current_distance = orientation_sign * _cross_2d(
                edge_vector,
                (
                    current[0] - edge_start[0],
                    current[1] - edge_start[1],
                ),
            )
            current_inside = (
                current_distance >= -_BAKE_UDIM_AREA_EPSILON
            )
            if current_inside != previous_inside:
                denominator = previous_distance - current_distance
                if abs(denominator) > _BAKE_UDIM_AREA_EPSILON:
                    factor = previous_distance / denominator
                    clipped.append((
                        previous[0]
                        + factor * (current[0] - previous[0]),
                        previous[1]
                        + factor * (current[1] - previous[1]),
                    ))
            if current_inside:
                clipped.append(current)
            previous = current
            previous_distance = current_distance
            previous_inside = current_inside
        polygon = clipped
    return polygon


def _uv_triangles_overlap(first, second):
    return (
        _uv_polygon_area(
            _clip_polygon_to_triangle(first, second)
        )
        > _BAKE_UDIM_AREA_EPSILON
    )


def _triangle_intersects_bake_udim(uv_points):
    return (
        _uv_polygon_area(
            _clip_uv_polygon_to_bake_udim(uv_points)
        )
        > _BAKE_UDIM_AREA_EPSILON
    )


def _faces_intersecting_bake_udim(
    obj, uv_layer_name, face_indices
):
    if not face_indices:
        return set()
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    uv_layer = bm.loops.layers.uv.get(uv_layer_name)
    if uv_layer is None:
        return set()

    matching_face_indices = set()
    for triangle in bm.calc_loop_triangles():
        face_index = triangle[0].face.index
        if face_index not in face_indices:
            continue
        if _triangle_intersects_bake_udim(
            [loop[uv_layer].uv for loop in triangle]
        ):
            matching_face_indices.add(face_index)
    return matching_face_indices


def _selected_edit_face_indices(obj):
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    return {face.index for face in bm.faces if face.select}


def _uv_points_match(first, second, tolerance):
    return (first - second).length <= tolerance


def _expand_faces_to_uv_islands(
    obj, uv_layer_name, seed_face_indices, tolerance=1e-5
):
    if not seed_face_indices:
        return set()

    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    uv_layer = bm.loops.layers.uv.get(uv_layer_name)
    if uv_layer is None:
        return set(seed_face_indices)

    connected_faces = {face.index: set() for face in bm.faces}
    for edge in bm.edges:
        if len(edge.link_faces) != 2:
            continue
        first_face, second_face = edge.link_faces
        first_loop = next(
            loop for loop in first_face.loops if loop.edge == edge
        )
        second_loop = next(
            loop for loop in second_face.loops if loop.edge == edge
        )
        if (
            _uv_points_match(
                first_loop[uv_layer].uv,
                second_loop.link_loop_next[uv_layer].uv,
                tolerance,
            )
            and _uv_points_match(
                first_loop.link_loop_next[uv_layer].uv,
                second_loop[uv_layer].uv,
                tolerance,
            )
        ):
            connected_faces[first_face.index].add(second_face.index)
            connected_faces[second_face.index].add(first_face.index)

    island_face_indices = set(seed_face_indices)
    pending_face_indices = list(seed_face_indices)
    while pending_face_indices:
        face_index = pending_face_indices.pop()
        for connected_face_index in connected_faces.get(face_index, ()):
            if connected_face_index not in island_face_indices:
                island_face_indices.add(connected_face_index)
                pending_face_indices.append(connected_face_index)

    for face_index in island_face_indices:
        bm.faces[face_index].select = True
    bmesh.update_edit_mesh(
        obj.data, loop_triangles=False, destructive=False
    )
    return island_face_indices


def _uv_islands_from_faces(
    bm, uv_layer, face_indices, tolerance=1e-5
):
    bm.faces.ensure_lookup_table()
    candidate_indices = {
        face_index
        for face_index in face_indices
        if 0 <= face_index < len(bm.faces)
    }
    connected_faces = {
        face_index: set() for face_index in candidate_indices
    }

    for edge in bm.edges:
        if len(edge.link_faces) != 2:
            continue
        first_face, second_face = edge.link_faces
        if (
            first_face.index not in candidate_indices
            or second_face.index not in candidate_indices
        ):
            continue
        first_loop = next(
            loop for loop in first_face.loops if loop.edge == edge
        )
        second_loop = next(
            loop for loop in second_face.loops if loop.edge == edge
        )
        if (
            _uv_points_match(
                first_loop[uv_layer].uv,
                second_loop.link_loop_next[uv_layer].uv,
                tolerance,
            )
            and _uv_points_match(
                first_loop.link_loop_next[uv_layer].uv,
                second_loop[uv_layer].uv,
                tolerance,
            )
        ):
            connected_faces[first_face.index].add(second_face.index)
            connected_faces[second_face.index].add(first_face.index)

    islands = []
    unvisited = set(candidate_indices)
    while unvisited:
        seed = min(unvisited)
        island = {seed}
        pending = [seed]
        unvisited.remove(seed)
        while pending:
            face_index = pending.pop()
            for neighbour in connected_faces[face_index]:
                if neighbour not in unvisited:
                    continue
                unvisited.remove(neighbour)
                island.add(neighbour)
                pending.append(neighbour)
        islands.append(tuple(sorted(island)))
    return islands


@dataclass
class _UVIslandOverlapData:
    face_indices: tuple
    triangles: tuple
    triangle_bounds: tuple
    bounds: tuple


def _uv_island_overlap_data(bm, uv_layer, islands):
    face_to_island = {
        face_index: island_index
        for island_index, island in enumerate(islands)
        for face_index in island
    }
    island_triangles = [[] for _island in islands]

    for triangle in bm.calc_loop_triangles():
        island_index = face_to_island.get(triangle[0].face.index)
        if island_index is None:
            continue
        clipped_polygon = _clip_uv_polygon_to_bake_udim(
            [loop[uv_layer].uv for loop in triangle]
        )
        if (
            _uv_polygon_area(clipped_polygon)
            <= _BAKE_UDIM_AREA_EPSILON
        ):
            continue
        first_point = clipped_polygon[0]
        for point_index in range(1, len(clipped_polygon) - 1):
            island_triangles[island_index].append((
                first_point,
                clipped_polygon[point_index],
                clipped_polygon[point_index + 1],
            ))

    overlap_data = []
    for face_indices, triangles in zip(islands, island_triangles):
        if not triangles:
            overlap_data.append(
                _UVIslandOverlapData(
                    face_indices,
                    (),
                    (),
                    (0.0, 0.0, 0.0, 0.0),
                )
            )
            continue
        points = [
            point for triangle in triangles for point in triangle
        ]
        overlap_data.append(_UVIslandOverlapData(
            face_indices=face_indices,
            triangles=tuple(triangles),
            triangle_bounds=tuple(
                (
                    min(point[0] for point in triangle),
                    min(point[1] for point in triangle),
                    max(point[0] for point in triangle),
                    max(point[1] for point in triangle),
                )
                for triangle in triangles
            ),
            bounds=(
                min(point[0] for point in points),
                min(point[1] for point in points),
                max(point[0] for point in points),
                max(point[1] for point in points),
            ),
        ))
    return overlap_data


def _bounds_overlap(first, second):
    return not (
        first[2] <= second[0]
        or second[2] <= first[0]
        or first[3] <= second[1]
        or second[3] <= first[1]
    )


def _uv_islands_overlap(first, second):
    if (
        not first.triangles
        or not second.triangles
        or not _bounds_overlap(first.bounds, second.bounds)
    ):
        return False

    grid_divisions = max(
        8,
        min(
            128,
            int(max(
                len(first.triangles),
                len(second.triangles),
            ) ** 0.5),
        ),
    )

    def grid_cells(bounds):
        minimum_x = max(
            0, min(grid_divisions - 1, int(
                bounds[0] * grid_divisions
            ))
        )
        minimum_y = max(
            0, min(grid_divisions - 1, int(
                bounds[1] * grid_divisions
            ))
        )
        maximum_x = max(
            0, min(grid_divisions - 1, int(
                bounds[2] * grid_divisions
            ))
        )
        maximum_y = max(
            0, min(grid_divisions - 1, int(
                bounds[3] * grid_divisions
            ))
        )
        return (
            (x_index, y_index)
            for x_index in range(minimum_x, maximum_x + 1)
            for y_index in range(minimum_y, maximum_y + 1)
        )

    second_grid = {}
    for triangle_index, bounds in enumerate(
        second.triangle_bounds
    ):
        for cell in grid_cells(bounds):
            second_grid.setdefault(cell, set()).add(
                triangle_index
            )

    for first_triangle, first_bounds in zip(
        first.triangles, first.triangle_bounds
    ):
        candidate_indices = set()
        for cell in grid_cells(first_bounds):
            candidate_indices.update(second_grid.get(cell, ()))
        for second_index in candidate_indices:
            if (
                _bounds_overlap(
                    first_bounds,
                    second.triangle_bounds[second_index],
                )
                and _uv_triangles_overlap(
                    first_triangle,
                    second.triangles[second_index],
                )
            ):
                return True
    return False


def _uv_island_faces_to_shift(bm, uv_layer, face_indices):
    islands = _uv_islands_from_faces(
        bm, uv_layer, face_indices
    )
    if len(islands) < 2:
        return set()

    overlap_data = _uv_island_overlap_data(
        bm, uv_layer, islands
    )
    overlap_graph = [set() for _island in islands]
    for first_index, first in enumerate(overlap_data):
        for second_index in range(
            first_index + 1, len(overlap_data)
        ):
            if _uv_islands_overlap(
                first, overlap_data[second_index]
            ):
                overlap_graph[first_index].add(second_index)
                overlap_graph[second_index].add(first_index)

    kept_islands = []
    moved_faces = set()
    for island_index, island in enumerate(islands):
        if any(
            kept_index in overlap_graph[island_index]
            for kept_index in kept_islands
        ):
            moved_faces.update(island)
        else:
            kept_islands.append(island_index)
    return moved_faces


def _native_overlap_issues(
    obj, uv_name_pattern, uv_map_required, expand_uv_islands=True
):
    context = bpy.context
    view_layer = context.view_layer
    previous_active_object = view_layer.objects.active
    previous_selected_objects = list(context.selected_objects)
    previous_mode = (
        previous_active_object.mode
        if previous_active_object
        else 'OBJECT'
    )
    previous_uv_sync = context.scene.tool_settings.use_uv_select_sync
    previous_uv_name = (
        obj.data.uv_layers.active.name
        if obj.data.uv_layers.active
        else ""
    )
    previous_edit_objects = ()
    previous_selection_states = {}
    if previous_mode == 'EDIT':
        previous_edit_objects = tuple(
            edit_object
            for edit_object in context.objects_in_mode_unique_data
            if edit_object.type == 'MESH'
        )
        previous_selection_states = {
            edit_object.name: _OverlapSelectionState.capture(
                edit_object
            )
            for edit_object in previous_edit_objects
        }

    issues = []
    matched_uv_map = False

    try:
        if (
            previous_active_object
            and previous_active_object.mode != 'OBJECT'
        ):
            bpy.ops.object.mode_set(mode='OBJECT')

        for selected_object in list(context.selected_objects):
            selected_object.select_set(False)
        obj.select_set(True)
        view_layer.objects.active = obj

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        context.scene.tool_settings.use_uv_select_sync = True

        for uv_layer in obj.data.uv_layers:
            uv_layer_name = uv_layer.name
            if not uv_name_pattern.match(uv_layer_name):
                continue
            matched_uv_map = True
            obj.data.uv_layers.active = uv_layer
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.uv.select_all(action='DESELECT')
            bpy.ops.uv.select_overlap(extend=False)
            overlap_face_indices = _selected_edit_face_indices(obj)
            overlap_face_indices = _faces_intersecting_bake_udim(
                obj, uv_layer_name, overlap_face_indices
            )
            if expand_uv_islands:
                overlap_face_indices = _expand_faces_to_uv_islands(
                    obj, uv_layer_name, overlap_face_indices
                )
            sorted_face_indices = sorted(overlap_face_indices)
            if sorted_face_indices:
                issues.append({
                    "message": (
                        f"{len(sorted_face_indices)} face(s) with "
                        "overlapping UVs in UDIM 1001 on UV set: "
                        f"{uv_layer_name}"
                    ),
                    "element_ref": (
                        f"uv:{uv_layer_name};f:"
                        + ",".join(map(str, sorted_face_indices))
                    ),
                })

        bpy.ops.mesh.select_all(action='DESELECT')
    finally:
        try:
            context.scene.tool_settings.use_uv_select_sync = (
                previous_uv_sync
            )
            if obj.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            if (
                previous_uv_name
                and obj.data.uv_layers.get(previous_uv_name)
            ):
                obj.data.uv_layers.active = (
                    obj.data.uv_layers[previous_uv_name]
                )
            for selected_object in list(context.selected_objects):
                selected_object.select_set(False)
            for selected_object in previous_selected_objects:
                if selected_object.name in context.scene.objects:
                    selected_object.select_set(True)
            if (
                previous_active_object
                and previous_active_object.name in context.scene.objects
            ):
                view_layer.objects.active = previous_active_object
                if previous_mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode=previous_mode)
                for edit_object in previous_edit_objects:
                    if (
                        edit_object.name in context.scene.objects
                        and edit_object.mode == 'EDIT'
                        and edit_object.name
                        in previous_selection_states
                    ):
                        _OverlapSelectionState.restore(
                            edit_object,
                            previous_selection_states[
                                edit_object.name
                            ],
                        )
        except Exception as error:
            print(
                "[Scene QC Validator] Overlapped UV selection "
                f"restore failed: {error}"
            )

    if not matched_uv_map and uv_map_required:
        issues.append({
            "message": (
                "No UV set matches regex "
                f"'{uv_name_pattern.pattern}'"
            ),
            "element_ref": "",
        })
    return issues


def check_uv_overlap(obj, item):
    if not obj.data.uv_layers:
        return []

    uv_name_expression = item.string_param_1 or ".+"
    try:
        uv_name_pattern = re.compile(uv_name_expression)
    except re.error as error:
        return [{
            "message": (
                f"Invalid UV set regex '{uv_name_expression}': {error}"
            ),
            "element_ref": "",
        }]

    try:
        return _native_overlap_issues(
            obj,
            uv_name_pattern,
            item.bool_param_1,
            expand_uv_islands=True,
        )
    except Exception as error:
        return [{
            "message": f"Native UV overlap check failed: {error}",
            "element_ref": "",
        }]


def fix_uv_overlap(obj, item, result):
    """Keep one UV island from each overlap stack in UDIM 1001."""
    issues = (
        [{
            "message": result.message,
            "element_ref": result.element_ref,
        }]
        if result is not None and result.element_ref
        else check_uv_overlap(obj, item)
    )
    if not issues:
        return False

    changed = False
    if obj.data.is_editmode:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        for issue in issues:
            reference = dict(
                part.split(":", 1)
                for part in issue["element_ref"].split(";")
                if ":" in part
            )
            uv_layer = bm.loops.layers.uv.get(
                reference.get("uv", "")
            )
            if uv_layer is None:
                continue
            face_indices = {
                int(index)
                for index in reference.get("f", "").split(",")
                if index
            }
            for face_index in _uv_island_faces_to_shift(
                bm, uv_layer, face_indices
            ):
                for loop in bm.faces[face_index].loops:
                    loop[uv_layer].uv.x += 1.0
                    changed = True
        if changed:
            bmesh.update_edit_mesh(obj.data)
        return changed

    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        for issue in issues:
            reference = dict(
                part.split(":", 1)
                for part in issue["element_ref"].split(";")
                if ":" in part
            )
            uv_layer = bm.loops.layers.uv.get(
                reference.get("uv", "")
            )
            if uv_layer is None:
                continue
            face_indices = {
                int(index)
                for index in reference.get("f", "").split(",")
                if index
            }
            for face_index in _uv_island_faces_to_shift(
                bm, uv_layer, face_indices
            ):
                for loop in bm.faces[face_index].loops:
                    loop[uv_layer].uv.x += 1.0
                    changed = True
        if changed:
            bm.to_mesh(obj.data)
            obj.data.update()
    finally:
        bm.free()
    return changed


# ---------------------------------------------------------------------------
# UV Editor overlap display


_OVERLAP_VISUAL_COLOR = (
    0x41 / 255.0,
    0xF2 / 255.0,
    0x38 / 255.0,
    0.30,
)
_OVERLAP_VISUAL_BUILD_DELAY = 0.08
_OVERLAP_VISUAL_MODAL_RETRY_DELAY = 0.05


@dataclass
class _OverlapVisualRuntime:
    enabled: bool = False
    targets: dict = field(default_factory=dict)
    build_pending: bool = False
    building: bool = False
    depsgraph_handler_registered: bool = False
    load_handler_registered: bool = False
    generation: int = 0
    gizmos: dict = field(default_factory=dict)
    draw_handles: dict = field(default_factory=dict)

    def invalidate_pending_builds(self):
        self.generation += 1
        self.build_pending = False


_overlap_visual = _OverlapVisualRuntime()


def _report_overlap_visual_error(operation, error):
    print(
        "[Scene QC Validator] Overlapped UV visual "
        f"{operation} failed: {error}"
    )


@dataclass(frozen=True)
class _MeshSelectionSnapshot:
    uv_layer_name: str
    vert_indices: tuple
    edge_indices: tuple
    face_indices: tuple
    uv_loops: tuple


class _OverlapSelectionState:
    @staticmethod
    def capture(obj):
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        uv_layer = bm.loops.layers.uv.active
        uv_loops = ()
        if uv_layer is not None:
            uv_loops = tuple(
                (
                    face.index,
                    loop_index,
                    loop.uv_select_vert,
                    loop.uv_select_edge,
                )
                for face in bm.faces
                for loop_index, loop in enumerate(face.loops)
                if loop.uv_select_vert or loop.uv_select_edge
            )
        return _MeshSelectionSnapshot(
            uv_layer.name if uv_layer is not None else "",
            tuple(vert.index for vert in bm.verts if vert.select),
            tuple(edge.index for edge in bm.edges if edge.select),
            tuple(face.index for face in bm.faces if face.select),
            uv_loops,
        )

    @staticmethod
    def restore(obj, snapshot):
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        for vert in bm.verts:
            vert.select = False
        for edge in bm.edges:
            edge.select = False
        for face in bm.faces:
            face.select = False
        for vert_index in snapshot.vert_indices:
            if vert_index < len(bm.verts):
                bm.verts[vert_index].select = True
        for edge_index in snapshot.edge_indices:
            if edge_index < len(bm.edges):
                bm.edges[edge_index].select = True
        for face_index in snapshot.face_indices:
            if face_index < len(bm.faces):
                bm.faces[face_index].select = True

        uv_layer = bm.loops.layers.uv.get(snapshot.uv_layer_name)
        if uv_layer is not None:
            for face in bm.faces:
                for loop in face.loops:
                    loop.uv_select_vert = False
                    loop.uv_select_edge = False
            for (
                face_index,
                loop_index,
                select_vert,
                select_edge,
            ) in snapshot.uv_loops:
                if face_index >= len(bm.faces):
                    continue
                face = bm.faces[face_index]
                if loop_index >= len(face.loops):
                    continue
                loop = face.loops[loop_index]
                loop.uv_select_vert = select_vert
                loop.uv_select_edge = select_edge
        bm.select_flush_mode()


class _NativeOverlapSelection:
    def __init__(self, context, objects):
        self.objects = tuple(objects)
        self.uv_select_sync = (
            context.tool_settings.use_uv_select_sync
        )
        self.captured_selections = {
            obj.name: _OverlapSelectionState.capture(obj)
            for obj in self.objects
        }
        if bpy.ops.uv.select_all.poll():
            bpy.ops.uv.select_all(action='DESELECT')
        if bpy.ops.uv.select_overlap.poll():
            bpy.ops.uv.select_overlap(extend=False)

    def restore(self):
        if bpy.ops.uv.select_all.poll():
            bpy.ops.uv.select_all(action='DESELECT')
        for obj in self.objects:
            snapshot = self.captured_selections.get(obj.name)
            if snapshot is not None and obj.mode == 'EDIT':
                _OverlapSelectionState.restore(obj, snapshot)


class SQC_GT_OverlapUVVisual(bpy.types.Gizmo):
    bl_idname = "SQC_GT_overlap_uv_visual"
    bl_target_properties = ()

    __slots__ = ("shapes", "build_requested")

    def setup(self):
        if not hasattr(self, "shapes"):
            self.shapes = []
            self.build_requested = True

    def draw(self, context):
        return

    def draw_select(self, context, select_id):
        self.draw_overlay(context)

    def test_select(self, context, location):
        return -1

    def request_build(self):
        self.build_requested = True

    def draw_overlay(self, context):
        if not _overlap_visual.enabled:
            return
        if self.build_requested:
            _schedule_overlap_visual_build(context, self)
            self.build_requested = False
        if not self.shapes:
            return
        _uv_overlay.draw_shapes(
            context, self.shapes, _OVERLAP_VISUAL_COLOR
        )


class SQC_GGT_OverlapUVVisual(bpy.types.GizmoGroup):
    bl_idname = "SQC_GGT_overlap_uv_visual"
    bl_label = "UV Overlap Overlay"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'EXCLUDE_MODAL', 'SCALE'}

    @classmethod
    def poll(cls, context):
        return (
            _overlap_visual.enabled
            and context.mode == 'EDIT_MESH'
            and context.active_object is not None
            and context.active_object.type == 'MESH'
        )

    def setup(self, context):
        self.visual_gizmo = self.gizmos.new(
            "SQC_GT_overlap_uv_visual"
        )
        self.visual_gizmo.hide_select = True
        area_pointer = context.area.as_pointer()
        _overlap_visual.gizmos[area_pointer] = self.visual_gizmo

        draw_id = str(uuid.uuid4())
        _overlap_visual.draw_handles[draw_id] = (
            bpy.types.SpaceImageEditor.draw_handler_add(
                self._draw_post_pixel,
                (draw_id,),
                'WINDOW',
                'POST_PIXEL',
            )
        )

    def _draw_post_pixel(self, draw_id):
        try:
            context = bpy.context
            if self.poll(context):
                self.visual_gizmo.draw_overlay(context)
        except ReferenceError:
            draw_handle = _overlap_visual.draw_handles.pop(
                draw_id, None
            )
            if draw_handle is not None:
                bpy.types.SpaceImageEditor.draw_handler_remove(
                    draw_handle, 'WINDOW'
                )

    def refresh(self, context):
        pass


OVERLAP_VISUAL_CLASSES = (
    SQC_GT_OverlapUVVisual,
    SQC_GGT_OverlapUVVisual,
)


def is_overlap_visual_enabled():
    return _overlap_visual.enabled


def enable_overlap_visual(obj, uv_layer_name):
    if not obj or obj.type != 'MESH':
        return False
    _overlap_visual.invalidate_pending_builds()
    _overlap_visual.enabled = True
    edit_objects = tuple(
        edit_object
        for edit_object in bpy.context.objects_in_mode_unique_data
        if (
            edit_object.type == 'MESH'
            and edit_object.mode == 'EDIT'
        )
    )
    if obj not in edit_objects:
        edit_objects = (obj,)
    _overlap_visual.targets = {
        edit_object.name: (
            edit_object.data.uv_layers.active.name
            if edit_object.data.uv_layers.active
            else ""
        )
        for edit_object in edit_objects
    }
    _overlap_visual.targets[obj.name] = uv_layer_name
    _ensure_overlap_visual_update_handler()
    _tag_uv_editor_redraw()
    _request_overlap_visual_rebuild()
    return True


def _request_overlap_visual_rebuild():
    for area_pointer, visual_gizmo in list(
        _overlap_visual.gizmos.items()
    ):
        try:
            visual_gizmo.request_build()
        except ReferenceError:
            _overlap_visual.gizmos.pop(area_pointer, None)


def disable_overlap_visual():
    _overlap_visual.invalidate_pending_builds()
    _overlap_visual.enabled = False
    _overlap_visual.targets.clear()
    for area_pointer, visual_gizmo in list(
        _overlap_visual.gizmos.items()
    ):
        try:
            visual_gizmo.shapes.clear()
            visual_gizmo.build_requested = False
        except ReferenceError:
            _overlap_visual.gizmos.pop(area_pointer, None)
    _tag_uv_editor_redraw()


def _schedule_overlap_visual_build(context, visual_gizmo):
    if (
        _overlap_visual.build_pending
        or not _overlap_visual.enabled
    ):
        return

    _overlap_visual.build_pending = True
    build_generation = _overlap_visual.generation
    window = context.window
    area = context.area
    region = context.region

    def delayed_build():
        if build_generation != _overlap_visual.generation:
            return None
        if not _overlap_visual.enabled:
            _overlap_visual.build_pending = False
            return None
        if _uv_overlay.is_modal_operation_running(bpy.context):
            return _OVERLAP_VISUAL_MODAL_RETRY_DELAY
        _overlap_visual.build_pending = False
        try:
            with bpy.context.temp_override(
                window=window,
                area=area,
                region=region,
            ):
                _build_overlap_visual_batch(
                    bpy.context, visual_gizmo
                )
        except (ReferenceError, RuntimeError) as error:
            _report_overlap_visual_error("build", error)
        return None

    bpy.app.timers.register(
        delayed_build,
        first_interval=_OVERLAP_VISUAL_BUILD_DELAY,
    )


def _build_overlap_visual_batch(context, visual_gizmo):
    edit_objects = [
        obj
        for object_name in tuple(_overlap_visual.targets)
        if (
            (obj := context.scene.objects.get(object_name))
            is not None
            and obj.mode == 'EDIT'
        )
    ]
    if not edit_objects:
        visual_gizmo.shapes.clear()
        disable_overlap_visual()
        return

    _overlap_visual.building = True
    overlap_selection = None
    try:
        overlap_selection = _NativeOverlapSelection(
            context, edit_objects
        )
        visual_gizmo.shapes.clear()
        for obj in edit_objects:
            bm = bmesh.from_edit_mesh(obj.data)
            bm.faces.ensure_lookup_table()
            uv_layer = (
                bm.loops.layers.uv.get(
                    _overlap_visual.targets.get(obj.name, "")
                )
                or bm.loops.layers.uv.active
            )
            if not uv_layer:
                continue

            uv_coordinates = []
            for triangle in bm.calc_loop_triangles():
                if (
                    triangle[0].face.hide
                    or not triangle[0].face.select
                    or (
                        not overlap_selection.uv_select_sync
                        and not all(
                            triangle_loop.uv_select_vert
                            for triangle_loop in triangle
                        )
                    )
                ):
                    continue
                clipped_polygon = _clip_uv_polygon_to_bake_udim(
                    [loop[uv_layer].uv for loop in triangle]
                )
                if (
                    _uv_polygon_area(clipped_polygon)
                    <= _BAKE_UDIM_AREA_EPSILON
                ):
                    continue
                first_point = clipped_polygon[0]
                for point_index in range(
                    1, len(clipped_polygon) - 1
                ):
                    uv_coordinates.extend((
                        first_point,
                        clipped_polygon[point_index],
                        clipped_polygon[point_index + 1],
                    ))

            if uv_coordinates:
                unique_coordinates, triangle_indices = np.unique(
                    uv_coordinates,
                    return_inverse=True,
                    axis=0,
                )
                shader = gpu.shader.from_builtin('UNIFORM_COLOR')
                batch = batch_for_shader(
                    shader,
                    'TRIS',
                    {"pos": unique_coordinates.tolist()},
                    indices=triangle_indices.astype(np.int32),
                )
                batch.program_set(shader)
                visual_gizmo.shapes.append(
                    _uv_overlay.OverlayShape(batch, shader)
                )
    finally:
        if overlap_selection is not None:
            overlap_selection.restore()
        _overlap_visual.building = False
        _tag_uv_editor_redraw()


@bpy.app.handlers.persistent
def _overlap_visual_depsgraph_update(_scene, depsgraph):
    if (
        not _overlap_visual.enabled
        or _overlap_visual.building
    ):
        return

    edit_objects = [
        obj
        for object_name in tuple(_overlap_visual.targets)
        if (
            (obj := bpy.context.scene.objects.get(object_name))
            is not None
            and obj.mode == 'EDIT'
        )
    ]
    if not edit_objects:
        disable_overlap_visual()
        return
    target_meshes = {obj.data for obj in edit_objects}

    mesh_changed = any(
        isinstance(update.id, bpy.types.Mesh)
        and (
            update.id in target_meshes
            or getattr(update.id, "original", None)
            in target_meshes
        )
        and update.is_updated_geometry
        for update in depsgraph.updates
    )
    if not mesh_changed:
        return

    _request_overlap_visual_rebuild()
    _tag_uv_editor_redraw()


@bpy.app.handlers.persistent
def _overlap_visual_load_pre(_unused):
    disable_overlap_visual()
    _remove_overlap_visual_draw_handlers()
    _overlap_visual.gizmos.clear()


def _ensure_overlap_visual_update_handler():
    if not _overlap_visual.depsgraph_handler_registered:
        bpy.app.handlers.depsgraph_update_post.append(
            _overlap_visual_depsgraph_update
        )
        _overlap_visual.depsgraph_handler_registered = True
    if not _overlap_visual.load_handler_registered:
        bpy.app.handlers.load_pre.append(
            _overlap_visual_load_pre
        )
        _overlap_visual.load_handler_registered = True


def _tag_uv_editor_redraw():
    screen = getattr(bpy.context, "screen", None)
    if not screen:
        return
    for area in screen.areas:
        if area.type == 'IMAGE_EDITOR':
            area.tag_redraw()


def _remove_overlap_visual_draw_handlers():
    for draw_id, draw_handle in list(
        _overlap_visual.draw_handles.items()
    ):
        try:
            bpy.types.SpaceImageEditor.draw_handler_remove(
                draw_handle, 'WINDOW'
            )
        except (ReferenceError, ValueError):
            pass
        finally:
            _overlap_visual.draw_handles.pop(draw_id, None)


def unregister_overlap_visual():
    disable_overlap_visual()
    if (
        _overlap_visual.depsgraph_handler_registered
        and _overlap_visual_depsgraph_update
        in bpy.app.handlers.depsgraph_update_post
    ):
        bpy.app.handlers.depsgraph_update_post.remove(
            _overlap_visual_depsgraph_update
        )
    _overlap_visual.depsgraph_handler_registered = False
    if (
        _overlap_visual.load_handler_registered
        and _overlap_visual_load_pre
        in bpy.app.handlers.load_pre
    ):
        bpy.app.handlers.load_pre.remove(
            _overlap_visual_load_pre
        )
    _overlap_visual.load_handler_registered = False

    _remove_overlap_visual_draw_handlers()
    _overlap_visual.gizmos.clear()
