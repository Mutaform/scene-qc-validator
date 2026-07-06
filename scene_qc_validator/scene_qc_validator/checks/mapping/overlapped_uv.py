from ..common import *


def _uv_bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_overlaps(a, b, tolerance):
    return not (
        a[2] <= b[0] + tolerance or
        b[2] <= a[0] + tolerance or
        a[3] <= b[1] + tolerance or
        b[3] <= a[1] + tolerance
    )


def _triangle_area(points):
    a, b, c = points
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) * 0.5


def _clean_points(points, tolerance):
    cleaned = []
    for point in points:
        if not cleaned or abs(point[0] - cleaned[-1][0]) > tolerance or abs(point[1] - cleaned[-1][1]) > tolerance:
            cleaned.append(point)
    if len(cleaned) > 1:
        first = cleaned[0]
        last = cleaned[-1]
        if abs(first[0] - last[0]) <= tolerance and abs(first[1] - last[1]) <= tolerance:
            cleaned.pop()
    return cleaned


def _triangulate_points(points, tolerance):
    points = _clean_points(points, tolerance)
    if len(points) < 3:
        return []
    vectors = [mathutils.Vector((point[0], point[1], 0.0)) for point in points]
    try:
        indices = mathutils.geometry.tessellate_polygon([vectors])
    except Exception:
        indices = [(0, i, i + 1) for i in range(1, len(points) - 1)]
    triangles = []
    for tri in indices:
        triangle = tuple(points[i] for i in tri)
        if _triangle_area(triangle) > tolerance:
            triangles.append(triangle)
    return triangles


def _project(points, axis):
    values = [point[0] * axis[0] + point[1] * axis[1] for point in points]
    return min(values), max(values)


def _triangle_overlaps(a, b, tolerance):
    axes = []
    for tri in (a, b):
        for i, point in enumerate(tri):
            next_point = tri[(i + 1) % 3]
            edge = (next_point[0] - point[0], next_point[1] - point[1])
            axis = (-edge[1], edge[0])
            length = (axis[0] * axis[0] + axis[1] * axis[1]) ** 0.5
            if length > tolerance:
                axes.append((axis[0] / length, axis[1] / length))
    for axis in axes:
        min_a, max_a = _project(a, axis)
        min_b, max_b = _project(b, axis)
        if min(max_a, max_b) - max(min_a, min_b) <= tolerance:
            return False
    return True


def _polygons_overlap(a_triangles, b_triangles, tolerance):
    for tri_a in a_triangles:
        bbox_a = _uv_bbox(tri_a)
        for tri_b in b_triangles:
            if not _bbox_overlaps(bbox_a, _uv_bbox(tri_b), tolerance):
                continue
            if _triangle_overlaps(tri_a, tri_b, tolerance):
                return True
    return False


def _mesh_layer_entries(obj, layer, tolerance):
    uv_data = layer.data
    if len(uv_data) < len(obj.data.loops):
        return None
    entries = []
    for poly in obj.data.polygons:
        if poly.loop_total < 3:
            continue
        points = [tuple(uv_data[loop_index].uv) for loop_index in poly.loop_indices]
        triangles = _triangulate_points(points, tolerance)
        if not triangles:
            continue
        bbox = _uv_bbox(points)
        if bbox[2] - bbox[0] <= tolerance or bbox[3] - bbox[1] <= tolerance:
            continue
        entries.append((bbox[0], bbox[2], bbox, triangles, poly.index))
    return entries


def _bmesh_uv_layers(bm):
    return [(name, bm.loops.layers.uv[name]) for name in bm.loops.layers.uv.keys()]


def _bmesh_layer_entries(bm, uv_layer, tolerance):
    bm.faces.ensure_lookup_table()
    entries = []
    for face in bm.faces:
        if len(face.loops) < 3:
            continue
        points = [tuple(loop[uv_layer].uv) for loop in face.loops]
        triangles = _triangulate_points(points, tolerance)
        if not triangles:
            continue
        bbox = _uv_bbox(points)
        if bbox[2] - bbox[0] <= tolerance or bbox[3] - bbox[1] <= tolerance:
            continue
        entries.append((bbox[0], bbox[2], bbox, triangles, face.index))
    return entries


def _overlapped_faces(entries, tolerance, max_pairs):
    if not entries:
        return set(), 0, False

    min_u = min(entry[2][0] for entry in entries)
    min_v = min(entry[2][1] for entry in entries)
    max_u = max(entry[2][2] for entry in entries)
    max_v = max(entry[2][3] for entry in entries)
    layout_area = max((max_u - min_u) * (max_v - min_v), tolerance)
    cell_size = max((layout_area / max(len(entries), 1)) ** 0.5 * 2.0, tolerance * 10.0, 1e-6)

    cells = {}
    checked_pairs = set()
    bad_faces = set()
    pair_count = 0
    stopped = False

    for index, entry in enumerate(entries):
        bbox = entry[2]
        min_cell_x = int((bbox[0] - min_u) // cell_size)
        max_cell_x = int((bbox[2] - min_u) // cell_size)
        min_cell_y = int((bbox[1] - min_v) // cell_size)
        max_cell_y = int((bbox[3] - min_v) // cell_size)

        for cell_x in range(min_cell_x, max_cell_x + 1):
            for cell_y in range(min_cell_y, max_cell_y + 1):
                cell_key = (cell_x, cell_y)
                for other_index in cells.get(cell_key, []):
                    pair_key = (other_index, index)
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)

                    other = entries[other_index]
                    bbox_a = other[2]
                    triangles_a = other[3]
                    face_a = other[4]
                    bbox_b = entry[2]
                    triangles_b = entry[3]
                    face_b = entry[4]

                    if not _bbox_overlaps(bbox_a, bbox_b, tolerance):
                        continue
                    if face_a in bad_faces and face_b in bad_faces:
                        continue

                    pair_count += 1
                    if max_pairs > 0 and pair_count > max_pairs:
                        stopped = True
                        break
                    if _polygons_overlap(triangles_a, triangles_b, tolerance):
                        bad_faces.add(face_a)
                        bad_faces.add(face_b)
                if stopped:
                    break
                cells.setdefault(cell_key, []).append(index)
            if stopped:
                break
        if stopped:
            break
        if len(bad_faces) >= len(entries):
            break
    return bad_faces, pair_count, stopped


def _check_layers(layer_entries, regex, tolerance, max_pairs):
    issues = []
    any_match = False
    for layer_name, entries in layer_entries:
        if not regex.match(layer_name):
            continue
        any_match = True
        if entries is None:
            issues.append({
                "message": f"{layer_name} has incomplete UV data",
                "element_ref": f"uv:{layer_name}",
            })
            continue
        bad_faces, pair_count, stopped = _overlapped_faces(entries, tolerance, max_pairs)
        if bad_faces:
            face_indices = sorted(bad_faces)
            message = f"{len(face_indices)} face(s) with overlapping UVs on UV set: {layer_name}"
            if stopped:
                message += f". Stopped after {max_pairs} candidate pairs"
            issues.append({
                "message": message,
                "element_ref": f"uv:{layer_name};f:" + ",".join(map(str, face_indices)),
            })
        elif stopped:
            issues.append({
                "message": f"Overlapped UV check stopped after {max_pairs} candidate pairs on UV set: {layer_name}",
                "element_ref": f"uv:{layer_name}",
            })
    return any_match, issues


def _selected_edit_faces(obj):
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    return {face.index for face in bm.faces if face.select}


def _native_overlap_issues(obj, regex, required):
    context = bpy.context
    view_layer = context.view_layer
    previous_active = view_layer.objects.active
    previous_selection = list(context.selected_objects)
    previous_mode = previous_active.mode if previous_active else 'OBJECT'
    previous_sync = context.scene.tool_settings.use_uv_select_sync
    previous_uv_name = obj.data.uv_layers.active.name if obj.data.uv_layers.active else ""

    issues = []
    any_match = False

    try:
        if previous_active and previous_active.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for selected in list(context.selected_objects):
            selected.select_set(False)
        obj.select_set(True)
        view_layer.objects.active = obj

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        context.scene.tool_settings.use_uv_select_sync = True

        for layer in obj.data.uv_layers:
            layer_name = layer.name
            if not regex.match(layer_name):
                continue
            any_match = True
            obj.data.uv_layers.active = layer
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.uv.select_all(action='DESELECT')
            bpy.ops.uv.select_overlap()
            face_indices = sorted(_selected_edit_faces(obj))
            if face_indices:
                issues.append({
                    "message": f"{len(face_indices)} face(s) with overlapping UVs on UV set: {layer_name}",
                    "element_ref": f"uv:{layer_name};f:" + ",".join(map(str, face_indices)),
                })

        bpy.ops.mesh.select_all(action='DESELECT')
    finally:
        try:
            context.scene.tool_settings.use_uv_select_sync = previous_sync
            if obj.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            if previous_uv_name and obj.data.uv_layers.get(previous_uv_name):
                obj.data.uv_layers.active = obj.data.uv_layers[previous_uv_name]
            for selected in list(context.selected_objects):
                selected.select_set(False)
            for selected in previous_selection:
                if selected.name in context.scene.objects:
                    selected.select_set(True)
            if previous_active and previous_active.name in context.scene.objects:
                view_layer.objects.active = previous_active
                if previous_mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode=previous_mode)
        except Exception:
            pass

    if not any_match and required:
        return True, [{"message": f"No UV set matches regex '{regex.pattern}'", "element_ref": ""}]
    return True, issues


def check_uv_overlap(obj, item):
    if not obj.data.uv_layers:
        return []

    pattern = item.string_param_1 or ".+"
    required = item.bool_param_1
    tolerance = item.float_param_1 if item.float_param_1 > 0 else 1e-10
    max_pairs = item.int_param_1 if item.int_param_1 > 0 else 250000
    try:
        regex = re.compile(pattern)
    except re.error as ex:
        return [{"message": f"Invalid UV set regex '{pattern}': {ex}", "element_ref": ""}]

    try:
        ok, issues = _native_overlap_issues(obj, regex, required)
        if ok:
            return issues
    except Exception:
        pass

    if obj.data.is_editmode:
        bm = bmesh.from_edit_mesh(obj.data)
        layer_entries = [
            (layer_name, _bmesh_layer_entries(bm, uv_layer, tolerance))
            for layer_name, uv_layer in _bmesh_uv_layers(bm)
        ]
    else:
        layer_entries = [
            (layer.name, _mesh_layer_entries(obj, layer, tolerance))
            for layer in obj.data.uv_layers
        ]

    any_match, issues = _check_layers(layer_entries, regex, tolerance, max_pairs)
    if not any_match and required:
        return [{"message": f"No UV set matches regex '{pattern}'", "element_ref": ""}]
    return issues
