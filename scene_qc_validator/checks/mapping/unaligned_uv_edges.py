from collections import defaultdict, deque
import math

from ..common import *


_UV_KEY_TOLERANCE = 1e-7
_AXIS_CANDIDATE_ANGLE = 5.0
_DEFAULT_ANGLE_TOLERANCE = 0.1
_DEFAULT_RECTILINEAR_RATIO = 0.75
_MAX_FIX_LENGTH_CHANGE = 0.04
_MAX_FIX_AREA_CHANGE = 0.04
_MAX_FIX_TEXEL_DISPLACEMENT = 16.0
_DEFAULT_FIX_TEXTURE_SIZE = 4096
MAX_FIX_PASSES = 4


def _uv_point_key(uv):
    return (
        round(float(uv.x) / _UV_KEY_TOLERANCE),
        round(float(uv.y) / _UV_KEY_TOLERANCE),
    )


def _uv_segment_key(edge_index, uv_a, uv_b):
    point_a = _uv_point_key(uv_a)
    point_b = _uv_point_key(uv_b)
    return edge_index, tuple(sorted((point_a, point_b)))


def _axis_deviation_degrees(uv_a, uv_b):
    delta_u = float(uv_b.x - uv_a.x)
    delta_v = float(uv_b.y - uv_a.y)
    length = math.hypot(delta_u, delta_v)
    if length <= _UV_KEY_TOLERANCE:
        return length, 0.0
    angle = math.degrees(math.atan2(delta_v, delta_u)) % 180.0
    deviation = min(angle, abs(90.0 - angle), 180.0 - angle)
    return length, deviation


def _layer_border_records(mesh, layer):
    uv_data = layer.data
    segment_uses = defaultdict(list)

    for polygon in mesh.polygons:
        loop_indices = polygon.loop_indices
        loop_count = len(loop_indices)
        for offset, loop_index in enumerate(loop_indices):
            next_loop_index = loop_indices[(offset + 1) % loop_count]
            edge_index = mesh.loops[loop_index].edge_index
            uv_a = uv_data[loop_index].uv
            uv_b = uv_data[next_loop_index].uv
            length, deviation = _axis_deviation_degrees(uv_a, uv_b)
            if length <= _UV_KEY_TOLERANCE:
                continue
            key = _uv_segment_key(edge_index, uv_a, uv_b)
            segment_uses[key].append(
                (
                    polygon.index,
                    edge_index,
                    loop_index,
                    length,
                    deviation,
                )
            )

    return segment_uses


def _face_islands(mesh, segment_uses):
    adjacency = [[] for _polygon in mesh.polygons]
    for uses in segment_uses.values():
        if len(uses) != 2:
            continue
        face_a = uses[0][0]
        face_b = uses[1][0]
        if face_a == face_b:
            continue
        adjacency[face_a].append(face_b)
        adjacency[face_b].append(face_a)

    island_by_face = [-1] * len(mesh.polygons)
    island_count = 0
    for polygon in mesh.polygons:
        if island_by_face[polygon.index] != -1:
            continue
        island_by_face[polygon.index] = island_count
        queue = deque([polygon.index])
        while queue:
            face_index = queue.popleft()
            for neighbor in adjacency[face_index]:
                if island_by_face[neighbor] != -1:
                    continue
                island_by_face[neighbor] = island_count
                queue.append(neighbor)
        island_count += 1
    return island_by_face, island_count


def _unaligned_edges_for_layer(
    mesh,
    layer,
    angle_tolerance,
    rectilinear_ratio,
):
    if len(layer.data) < len(mesh.loops):
        return set(), 0

    segment_uses = _layer_border_records(mesh, layer)
    island_by_face, island_count = _face_islands(
        mesh, segment_uses
    )
    perimeter = [0.0] * island_count
    axis_length = [0.0] * island_count
    candidates = [[] for _index in range(island_count)]

    for uses in segment_uses.values():
        if len(uses) == 2:
            continue
        for (
            face_index,
            edge_index,
            _loop_index,
            length,
            deviation,
        ) in uses:
            island_index = island_by_face[face_index]
            perimeter[island_index] += length
            if deviation <= _AXIS_CANDIDATE_ANGLE:
                axis_length[island_index] += length
                if deviation > angle_tolerance:
                    candidates[island_index].append(
                        (face_index, edge_index)
                    )

    bad_segments = set()
    checked_islands = 0
    for island_index in range(island_count):
        total_length = perimeter[island_index]
        if total_length <= _UV_KEY_TOLERANCE:
            continue
        if (
            axis_length[island_index] / total_length
            < rectilinear_ratio
        ):
            continue
        checked_islands += 1
        bad_segments.update(candidates[island_index])

    return bad_segments, checked_islands


def _parse_element_reference(element_ref):
    reference = {}
    for part in element_ref.split(";"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        reference[key] = value
    return reference


def _parse_uv_segments(value):
    segments = set()
    for encoded_segment in value.split("|"):
        if not encoded_segment:
            continue
        face_index, edge_index = encoded_segment.split(",", 1)
        segments.add((int(face_index), int(edge_index)))
    return segments


def _polygon_uv_area(mesh, positions, polygon_index):
    loop_indices = mesh.polygons[polygon_index].loop_indices
    area = 0.0
    for offset, loop_index in enumerate(loop_indices):
        next_loop_index = loop_indices[
            (offset + 1) % len(loop_indices)
        ]
        uv_a = positions[loop_index]
        uv_b = positions[next_loop_index]
        area += uv_a[0] * uv_b[1] - uv_b[0] * uv_a[1]
    return area * 0.5


def _proposal_is_safe(
    mesh,
    original_positions,
    proposed_positions,
    affected_faces,
    maximum_uv_displacement,
):
    texel_safe = maximum_uv_displacement > 0.0
    for face_index in affected_faces:
        original_area = _polygon_uv_area(
            mesh,
            original_positions,
            face_index,
        )
        proposed_area = _polygon_uv_area(
            mesh,
            proposed_positions,
            face_index,
        )
        if abs(original_area) <= 1e-15:
            return False
        if original_area * proposed_area <= 0.0:
            return False
        if (
            abs(proposed_area / original_area - 1.0)
            > _MAX_FIX_AREA_CHANGE
            and not texel_safe
        ):
            return False

        loop_indices = mesh.polygons[face_index].loop_indices
        for offset, loop_index in enumerate(loop_indices):
            next_loop_index = loop_indices[
                (offset + 1) % len(loop_indices)
            ]
            original_a = original_positions[loop_index]
            original_b = original_positions[next_loop_index]
            proposed_a = proposed_positions[loop_index]
            proposed_b = proposed_positions[next_loop_index]
            original_length = math.hypot(
                original_b[0] - original_a[0],
                original_b[1] - original_a[1],
            )
            proposed_length = math.hypot(
                proposed_b[0] - proposed_a[0],
                proposed_b[1] - proposed_a[1],
            )
            if original_length <= _UV_KEY_TOLERANCE:
                return False
            if (
                abs(proposed_length / original_length - 1.0)
                > _MAX_FIX_LENGTH_CHANGE
                and not texel_safe
            ):
                return False
    return True


def _axis_border_components(mesh, layer, target_segments):
    segment_uses = _layer_border_records(mesh, layer)
    island_by_face, _island_count = _face_islands(
        mesh,
        segment_uses,
    )
    uv_data = layer.data
    graph = defaultdict(lambda: defaultdict(set))
    component_targets = defaultdict(set)
    node_positions = {}
    loops_by_node = defaultdict(set)

    for polygon in mesh.polygons:
        island_index = island_by_face[polygon.index]
        for loop_index in polygon.loop_indices:
            uv = uv_data[loop_index].uv
            node = (island_index, _uv_point_key(uv))
            node_positions[node] = (float(uv.x), float(uv.y))
            loops_by_node[node].add(loop_index)

    for uses in segment_uses.values():
        if len(uses) == 2:
            continue
        for (
            face_index,
            edge_index,
            loop_index,
            _length,
            deviation,
        ) in uses:
            if deviation > _AXIS_CANDIDATE_ANGLE:
                continue
            polygon = mesh.polygons[face_index]
            loop_indices = polygon.loop_indices
            offset = list(loop_indices).index(loop_index)
            next_loop_index = loop_indices[
                (offset + 1) % len(loop_indices)
            ]
            uv_a = uv_data[loop_index].uv
            uv_b = uv_data[next_loop_index].uv
            orientation = (
                "H"
                if abs(uv_b.x - uv_a.x) >= abs(uv_b.y - uv_a.y)
                else "V"
            )
            island_index = island_by_face[face_index]
            node_a = (island_index, _uv_point_key(uv_a))
            node_b = (island_index, _uv_point_key(uv_b))
            graph_key = (island_index, orientation)
            graph[graph_key][node_a].add(node_b)
            graph[graph_key][node_b].add(node_a)
            if (face_index, edge_index) in target_segments:
                component_targets[graph_key].update((node_a, node_b))

    components = []
    for graph_key, adjacency in graph.items():
        target_nodes = component_targets.get(graph_key, set())
        if not target_nodes:
            continue
        visited = set()
        for start_node in adjacency:
            if start_node in visited:
                continue
            queue = deque([start_node])
            component = set()
            while queue:
                node = queue.popleft()
                if node in visited:
                    continue
                visited.add(node)
                component.add(node)
                queue.extend(adjacency[node] - visited)
            if not component.intersection(target_nodes):
                continue
            if any(len(adjacency[node]) > 2 for node in component):
                continue
            components.append((
                graph_key[1],
                component,
                node_positions,
                loops_by_node,
            ))
    return components


def _signed_axis_offset_degrees(uv_a, uv_b):
    angle = math.degrees(
        math.atan2(uv_b.y - uv_a.y, uv_b.x - uv_a.x)
    )
    nearest_axis = round(angle / 90.0) * 90.0
    return (angle - nearest_axis + 45.0) % 90.0 - 45.0


def _rotate_uniformly_misaligned_islands(
    mesh,
    layer,
    target_segments,
    angle_tolerance,
):
    segment_uses = _layer_border_records(mesh, layer)
    island_by_face, _island_count = _face_islands(
        mesh,
        segment_uses,
    )
    target_islands = {
        island_by_face[face_index]
        for face_index, _edge_index in target_segments
        if face_index < len(island_by_face)
    }
    if not target_islands:
        return False

    uv_data = layer.data
    offsets_by_island = defaultdict(list)
    for uses in segment_uses.values():
        if len(uses) == 2:
            continue
        for (
            face_index,
            _edge_index,
            loop_index,
            length,
            deviation,
        ) in uses:
            island_index = island_by_face[face_index]
            if (
                island_index not in target_islands
                or deviation > _AXIS_CANDIDATE_ANGLE
            ):
                continue
            loop_indices = mesh.polygons[face_index].loop_indices
            offset = list(loop_indices).index(loop_index)
            next_loop_index = loop_indices[
                (offset + 1) % len(loop_indices)
            ]
            signed_offset = _signed_axis_offset_degrees(
                uv_data[loop_index].uv,
                uv_data[next_loop_index].uv,
            )
            offsets_by_island[island_index].append(
                (signed_offset, length)
            )

    changed = False
    maximum_spread = max(angle_tolerance * 0.5, 0.02)
    for island_index in target_islands:
        offsets = offsets_by_island.get(island_index, [])
        if len(offsets) < 4:
            continue
        total_length = sum(length for _offset, length in offsets)
        if total_length <= _UV_KEY_TOLERANCE:
            continue
        mean_offset = sum(
            offset * length
            for offset, length in offsets
        ) / total_length
        if abs(mean_offset) <= angle_tolerance:
            continue
        if max(
            abs(offset - mean_offset)
            for offset, _length in offsets
        ) > maximum_spread:
            continue

        island_loops = [
            loop_index
            for polygon in mesh.polygons
            if island_by_face[polygon.index] == island_index
            for loop_index in polygon.loop_indices
        ]
        unique_points = {}
        for loop_index in island_loops:
            uv = uv_data[loop_index].uv
            unique_points[_uv_point_key(uv)] = (
                float(uv.x),
                float(uv.y),
            )
        if not unique_points:
            continue
        center_u = sum(
            uv[0] for uv in unique_points.values()
        ) / len(unique_points)
        center_v = sum(
            uv[1] for uv in unique_points.values()
        ) / len(unique_points)
        radians = math.radians(-mean_offset)
        cosine = math.cos(radians)
        sine = math.sin(radians)
        for loop_index in island_loops:
            uv = uv_data[loop_index].uv
            delta_u = float(uv.x) - center_u
            delta_v = float(uv.y) - center_v
            uv.x = center_u + delta_u * cosine - delta_v * sine
            uv.y = center_v + delta_u * sine + delta_v * cosine
        changed = True
    return changed


def _straighten_layer_segments(
    mesh,
    layer,
    target_segments,
    texture_size,
):
    if not target_segments or len(layer.data) < len(mesh.loops):
        return False

    original_positions = [
        (float(loop_uv.uv.x), float(loop_uv.uv.y))
        for loop_uv in layer.data
    ]
    proposed_positions = list(original_positions)
    face_by_loop = [-1] * len(mesh.loops)
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            face_by_loop[loop_index] = polygon.index
    changed = False

    for (
        orientation,
        component,
        node_positions,
        loops_by_node,
    ) in _axis_border_components(mesh, layer, target_segments):
        axis_index = 1 if orientation == "H" else 0
        aligned_coordinate = sum(
            node_positions[node][axis_index]
            for node in component
        ) / len(component)

        component_proposal = list(proposed_positions)
        affected_faces = set()
        maximum_uv_displacement = 0.0
        for node in component:
            for loop_index in loops_by_node[node]:
                position = list(component_proposal[loop_index])
                position[axis_index] = aligned_coordinate
                component_proposal[loop_index] = tuple(position)
                affected_faces.add(face_by_loop[loop_index])
                maximum_uv_displacement = max(
                    maximum_uv_displacement,
                    math.dist(
                        proposed_positions[loop_index],
                        component_proposal[loop_index],
                    ),
                )

        texel_displacement_limit = (
            _MAX_FIX_TEXEL_DISPLACEMENT
            / max(1, texture_size)
        )
        permitted_uv_displacement = (
            maximum_uv_displacement
            if maximum_uv_displacement <= texel_displacement_limit
            else 0.0
        )

        if not _proposal_is_safe(
            mesh,
            proposed_positions,
            component_proposal,
            affected_faces,
            permitted_uv_displacement,
        ):
            continue
        proposed_positions = component_proposal
        changed = True

    if not changed:
        return False
    for loop_index, position in enumerate(proposed_positions):
        layer.data[loop_index].uv = position
    return True


def check_unaligned_uv_edges(obj, item):
    if not obj.data.uv_layers:
        return []

    mesh = obj.data
    temporary_mesh = None
    if obj.data.is_editmode:
        edit_bmesh = bmesh.from_edit_mesh(obj.data)
        edit_bmesh.verts.index_update()
        edit_bmesh.edges.index_update()
        edit_bmesh.faces.index_update()
        snapshot_bmesh = edit_bmesh.copy()
        temporary_mesh = bpy.data.meshes.new(
            "SQC_UnalignedUVSnapshot"
        )
        try:
            snapshot_bmesh.to_mesh(temporary_mesh)
        finally:
            snapshot_bmesh.free()
        mesh = temporary_mesh

    try:
        angle_tolerance = (
            item.float_param_1
            if item.float_param_1 > 0.0
            else _DEFAULT_ANGLE_TOLERANCE
        )
        rectilinear_ratio = (
            item.float_param_2
            if 0.0 < item.float_param_2 <= 1.0
            else _DEFAULT_RECTILINEAR_RATIO
        )

        issues = []
        for layer in mesh.uv_layers:
            if layer.name.startswith("SQC_"):
                continue
            bad_segments, checked_islands = (
                _unaligned_edges_for_layer(
                    mesh,
                    layer,
                    angle_tolerance,
                    rectilinear_ratio,
                )
            )
            if not bad_segments:
                continue
            ordered_segments = sorted(bad_segments)
            issues.append({
                "message": (
                    f"{len(ordered_segments)} UV border edge(s) are "
                    f"slightly off-axis on {layer.name} "
                    f"({checked_islands} rectilinear shell(s) checked)"
                ),
                "element_ref": (
                    f"uv:{layer.name};uvseg:"
                    + "|".join(
                        f"{face_index},{edge_index}"
                        for face_index, edge_index
                        in ordered_segments
                    )
                ),
            })
        return issues
    finally:
        if temporary_mesh is not None:
            bpy.data.meshes.remove(temporary_mesh)


def unaligned_fix_texture_size():
    texture_size = _DEFAULT_FIX_TEXTURE_SIZE
    try:
        padding_item = next(
            check
            for check in bpy.context.scene.sqc_settings.checks
            if check.check_id == "uv_padding"
        )
        if padding_item.int_param_2 > 0:
            texture_size = padding_item.int_param_2
    except (AttributeError, StopIteration):
        pass
    return texture_size


def unaligned_fix_remaining_issues(obj, item, allowed_layers):
    return [
        issue
        for issue in check_unaligned_uv_edges(obj, item)
        if _parse_element_reference(
            issue["element_ref"]
        ).get("uv", "") in allowed_layers
    ]


def unaligned_fix_issue_count(issues):
    return sum(
        len(_parse_uv_segments(
            _parse_element_reference(
                issue["element_ref"]
            ).get("uvseg", "")
        ))
        for issue in issues
    )


def fix_unaligned_uv_edges_pass(
    obj,
    item,
    issues,
    allowed_layers,
    texture_size,
):
    targets_by_layer = defaultdict(set)
    for issue in issues:
        reference = _parse_element_reference(
            issue["element_ref"]
        )
        layer_name = reference.get("uv", "")
        segments = _parse_uv_segments(
            reference.get("uvseg", "")
        )
        if layer_name in allowed_layers and segments:
            targets_by_layer[layer_name].update(segments)
    if not targets_by_layer:
        return False

    changed = False
    for layer_name, target_segments in targets_by_layer.items():
        layer = obj.data.uv_layers.get(layer_name)
        if layer is None:
            continue
        layer_changed = _rotate_uniformly_misaligned_islands(
            obj.data,
            layer,
            target_segments,
            (
                item.float_param_1
                if item.float_param_1 > 0.0
                else _DEFAULT_ANGLE_TOLERANCE
            ),
        )
        remaining_segments, _checked_islands = (
            _unaligned_edges_for_layer(
                obj.data,
                layer,
                (
                    item.float_param_1
                    if item.float_param_1 > 0.0
                    else _DEFAULT_ANGLE_TOLERANCE
                ),
                (
                    item.float_param_2
                    if 0.0 < item.float_param_2 <= 1.0
                    else _DEFAULT_RECTILINEAR_RATIO
                ),
            )
        )
        remaining_targets = target_segments.intersection(
            remaining_segments
        )
        layer_changed |= _straighten_layer_segments(
            obj.data,
            layer,
            remaining_targets,
            texture_size,
        )
        changed |= layer_changed
    if changed:
        obj.data.update()
    return changed


def fix_unaligned_uv_edges(obj, item, result):
    was_edit_mode = obj.mode == 'EDIT'
    if was_edit_mode:
        if bpy.context.view_layer.objects.active != obj:
            bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='OBJECT')

    try:
        issues = (
            [{
                "message": result.message,
                "element_ref": result.element_ref,
            }]
            if result is not None and result.element_ref
            else check_unaligned_uv_edges(obj, item)
        )
        if not issues:
            return False

        changed = False
        texture_size = unaligned_fix_texture_size()
        allowed_layers = {
            _parse_element_reference(
                issue["element_ref"]
            ).get("uv", "")
            for issue in issues
        }
        allowed_layers.discard("")

        for _pass_index in range(MAX_FIX_PASSES):
            changed_this_pass = fix_unaligned_uv_edges_pass(
                obj,
                item,
                issues,
                allowed_layers,
                texture_size,
            )

            if not changed_this_pass:
                break
            changed = True
            issues = unaligned_fix_remaining_issues(
                obj,
                item,
                allowed_layers,
            )
            if not issues:
                break
        if changed:
            obj.data.update()
        return changed
    finally:
        if was_edit_mode:
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.mode_set(mode='EDIT')
