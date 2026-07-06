from ..common import *
from collections import defaultdict, deque


def _uv_key(uv, tolerance):
    step = max(tolerance, 1e-9)
    return (round(uv.x / step), round(uv.y / step))


def _uv_edge_key(a, b, tolerance):
    key_a = _uv_key(a, tolerance)
    key_b = _uv_key(b, tolerance)
    return tuple(sorted((key_a, key_b)))


def _outside_uv_island_faces(obj, layer, tolerance, min_allowed, max_allowed):
    uv_data = layer.data
    face_edges = {}
    edge_faces = defaultdict(list)
    outside_faces = set()
    min_u = min_v = float("inf")
    max_u = max_v = float("-inf")

    for poly in obj.data.polygons:
        loop_indices = list(poly.loop_indices)
        edges = []
        face_is_outside = False
        for offset, loop_index in enumerate(loop_indices):
            next_loop_index = loop_indices[(offset + 1) % len(loop_indices)]
            uv = uv_data[loop_index].uv
            next_uv = uv_data[next_loop_index].uv
            min_u = min(min_u, uv.x)
            min_v = min(min_v, uv.y)
            max_u = max(max_u, uv.x)
            max_v = max(max_v, uv.y)
            edges.append(_uv_edge_key(uv, next_uv, tolerance))
            if uv.x < min_allowed or uv.x > max_allowed or uv.y < min_allowed or uv.y > max_allowed:
                face_is_outside = True
        face_edges[poly.index] = edges
        for edge in edges:
            edge_faces[edge].append(poly.index)
        if face_is_outside:
            outside_faces.add(poly.index)

    selected_faces = set()
    visited = set()
    for start_face in outside_faces:
        if start_face in visited:
            continue
        island = set()
        queue = deque([start_face])
        visited.add(start_face)
        while queue:
            face_index = queue.popleft()
            island.add(face_index)
            for edge in face_edges.get(face_index, []):
                for neighbor in edge_faces.get(edge, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
        selected_faces.update(island)

    return selected_faces, (min_u, min_v, max_u, max_v)


def check_single_uv_tile(obj, item):
    """Ensure every UV set stays inside the first UDIM square."""
    uv_layers = obj.data.uv_layers
    if not uv_layers:
        return []

    tolerance = item.float_param_1 if item.float_param_1 > 0 else 0.001
    min_allowed = 0.0 - tolerance
    max_allowed = 1.0 + tolerance
    issues = []

    for layer in uv_layers:
        uv_data = layer.data
        if len(uv_data) < len(obj.data.loops):
            issues.append({
                "message": f"{layer.name} have are shells outside the square",
                "element_ref": f"uv:{layer.name}",
            })
            continue

        shell_faces, bounds = _outside_uv_island_faces(obj, layer, tolerance, min_allowed, max_allowed)
        if shell_faces:
            face_indices = sorted(shell_faces)
            min_u, min_v, max_u, max_v = bounds
            bounds_text = f"U {min_u:.4f}..{max_u:.4f}, V {min_v:.4f}..{max_v:.4f}"
            issues.append({
                "message": f"{layer.name} have shells outside the square ({len(face_indices)} face(s), {bounds_text})",
                "element_ref": f"uv:{layer.name};f:" + ",".join(map(str, face_indices)),
            })

    return issues
