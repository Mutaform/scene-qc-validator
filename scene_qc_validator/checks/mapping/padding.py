"""Interactive UV-padding preview for the Mapping checklist.

Draws a coloured strip just outside every UV-shell border so an artist can
judge whether the islands leave enough padding for the target texture size.
A border is any edge whose UV winding breaks between its two faces; each such
edge is extruded outward in UV space by the configured margin and the result
is drawn as a GPU overlay in the UV Editor.
"""

from dataclasses import dataclass, field
import math
import uuid

import bmesh
import bpy
import gpu
from bpy.props import EnumProperty, IntProperty
from bpy.types import Operator
from gpu_extras.batch import batch_for_shader

from . import _uv_overlay


_PADDING_COLOR = (0.392157, 0.392157, 0.392157, 1.0)
_BUILD_DELAY = 0.05
# Re-poll interval while a modal operator blocks a safe rebuild.
_MODAL_RETRY_DELAY = 0.05
# Angular resolution of a rounded corner join (radians per fan segment).
_CORNER_ARC_STEP = math.pi / 12.0
# Longest miter (in margins) before a very sharp concave corner is left square.
_MITER_LIMIT = 4.0


def check_padding(_obj, _item):
    """Padding is an interactive visual review in the MVP."""
    return []


@dataclass
class _PaddingRuntime:
    enabled: bool = False
    margin_uv: float = 0.0
    targets: dict = field(default_factory=dict)
    gizmos: dict = field(default_factory=dict)
    draw_handles: dict = field(default_factory=dict)
    build_pending: bool = False
    building: bool = False
    generation: int = 0
    depsgraph_handler_registered: bool = False
    load_handler_registered: bool = False

    def invalidate(self):
        self.generation += 1
        self.build_pending = False


_padding = _PaddingRuntime()


def is_padding_visual_enabled():
    return _padding.enabled


def _margin_uv(padding_px, texture_size):
    """Convert a pixel padding at a texture size into a 0-1 UV-space margin."""
    return max(0.0, padding_px) / max(1.0, texture_size)


def refresh_padding_visual(
    _context, padding_px, texture_size
):
    if not _padding.enabled:
        return
    _padding.margin_uv = _margin_uv(padding_px, texture_size)
    _padding.invalidate()
    _request_rebuild()
    _tag_uv_editor_redraw()


def _face_is_flipped(face, uv_layer):
    """Return True when the face winds clockwise (mirrored) in UV space.

    Sums the 2D cross product of consecutive UV edge vectors around the face,
    which is twice its signed area. A non-negative result means the island is
    mirrored, so its border strip has to grow toward the opposite side.
    """
    signed_area = sum(
        (loop.link_loop_next[uv_layer].uv - loop[uv_layer].uv).cross(
            loop[uv_layer].uv - loop.link_loop_prev[uv_layer].uv
        )
        for loop in face.loops
    )
    return signed_area >= 0


def _uv_splits_across_edge(loop, uv_layer):
    """True when this loop's UV does not line up with the matching UV on the
    face across its edge, i.e. the shared edge is a seam in UV space."""
    across = loop.link_loop_radial_next.link_loop_next
    return loop[uv_layer].uv != across[uv_layer].uv


def _edge_is_uv_border(edge, uv_layer):
    """A UV-shell footprint border: a seam / mesh boundary (UVs split across the
    edge) OR a fold where two faces share a UV-matched edge but lie on the same
    side of it (stacked/overlapping), so the footprint still has an edge here."""
    loops = edge.link_loops
    if not loops:
        return False
    if (_uv_splits_across_edge(loops[0], uv_layer)
            or _uv_splits_across_edge(loops[-1], uv_layer)):
        return True
    if len(loops) == 2:
        return _loops_fold_across_edge(loops[0], loops[1], uv_layer)
    return False


def _loops_fold_across_edge(loop_a, loop_b, uv_layer):
    """True when two faces share a UV-matched edge but sit on the same side of
    it (a fold/overlap), so it still bounds the shell footprint."""
    origin = loop_a[uv_layer].uv
    edge_dir = loop_a.link_loop_next[uv_layer].uv - origin
    corner_a = loop_a.link_loop_next.link_loop_next[uv_layer].uv - origin
    corner_b = loop_b.link_loop_next.link_loop_next[uv_layer].uv - origin
    side_a = edge_dir.x * corner_a.y - edge_dir.y * corner_a.x
    side_b = edge_dir.x * corner_b.y - edge_dir.y * corner_b.x
    return side_a * side_b > 0.0


def _collect_uv_border_edges(bm, uv_layer, uv_sync):
    """Return the set of visible UV-shell border edges.

    An edge is a border when its UV winding breaks between its two faces; it is
    kept when at least one of those faces is currently shown in the UV Editor.
    Iterating edges once (instead of every face's edges, twice per border edge)
    keeps this cheap on dense meshes. The winding is no longer stored here — it
    is read per loop from its own face in :func:`_segment_normal`.
    """
    border_edges = set()
    for edge in bm.edges:
        loops = edge.link_loops
        if not loops or not _edge_is_uv_border(edge, uv_layer):
            continue
        for loop in loops:
            face = loop.face
            if not (face.hide or (not uv_sync and not face.select)):
                border_edges.add(edge)
                break
    return border_edges


def _segment_normal(loop, uv_layer, face_flip=None):
    """Outward unit normal of a border loop's UV segment.

    The winding is read from the loop's own face, not a per-edge flag: a seam
    edge is shared by two faces that may have opposite UV winding, so each side
    must be flipped independently or one of them grows inward. ``face_flip`` is
    an optional per-build cache so a face's signed area is not recomputed for
    each of its border segments.
    """
    normal = (
        loop[uv_layer].uv - loop.link_loop_next[uv_layer].uv
    ).orthogonal()
    normal.normalize()
    face = loop.face
    if face_flip is None:
        flipped = _face_is_flipped(face, uv_layer)
    else:
        flipped = face_flip.get(face)
        if flipped is None:
            flipped = _face_is_flipped(face, uv_layer)
            face_flip[face] = flipped
    if flipped:
        normal.negate()
    return normal


def _loop_is_visible(loop, uv_sync):
    return (
        (uv_sync and not loop.face.hide)
        or (loop.face.select and loop.link_loop_next.face.select)
    )


def _next_border_loop(loop, border_edges):
    """Walk the UV-island boundary to the border segment following ``loop``.

    Rotates around the segment's end vertex (``link_loop_radial_next.
    link_loop_next``) until another border edge turns up, so the two segments
    that truly meet at a corner are paired even where UV islands touch and
    several segments share one UV coordinate.
    """
    walker = loop.link_loop_next
    for _ in range(256):
        if walker.edge in border_edges:
            return walker
        walker = walker.link_loop_radial_next.link_loop_next
    return None


def _add_round_join(
    coordinates, triangle_indices, position, normal_a, normal_b, margin_uv
):
    """Fan a rounded corner between two segment offsets, the short way around,
    so the band's outer edge stays continuous and curves round smoothly."""
    dot = max(-1.0, min(1.0, normal_a.dot(normal_b)))
    cross = normal_a.x * normal_b.y - normal_a.y * normal_b.x
    sweep = math.atan2(cross, dot)
    steps = max(1, math.ceil(abs(sweep) / _CORNER_ARC_STEP))
    step_cos = math.cos(sweep / steps)
    step_sin = math.sin(sweep / steps)

    center_index = len(coordinates)
    coordinates.append(position.to_tuple(5))
    arm = normal_a.copy()
    prev_index = len(coordinates)
    coordinates.append((position + arm * margin_uv).to_tuple(5))
    for _ in range(steps):
        arm.x, arm.y = (
            arm.x * step_cos - arm.y * step_sin,
            arm.x * step_sin + arm.y * step_cos,
        )
        point_index = len(coordinates)
        coordinates.append((position + arm * margin_uv).to_tuple(5))
        triangle_indices.append((center_index, prev_index, point_index))
        prev_index = point_index


def _is_convex_corner(edge_dir, next_dir, normal):
    """True when the boundary turns away from the outward-normal side.

    Convex corners get a rounded fan; concave corners are mitered so the two
    strips meet at a point instead of overlapping.
    """
    turn = edge_dir.x * next_dir.y - edge_dir.y * next_dir.x
    outward = edge_dir.x * normal.y - edge_dir.y * normal.x
    return turn * outward < 0.0


def _miter_point(position, normal_a, normal_b, margin_uv):
    """Intersection of the two offset lines at a corner, or None if the corner
    is too sharp (miter longer than the limit) and should stay square."""
    denom = 1.0 + normal_a.dot(normal_b)
    if denom <= 1e-4:
        return None
    miter = (normal_a + normal_b) / denom
    if miter.length > _MITER_LIMIT:
        return None
    return position + miter * margin_uv


def _padding_strip_geometry(bm, uv_layer, border_edges, margin_uv, uv_sync):
    """Build a continuous padding band along the UV-shell borders.

    Each border edge becomes a strip offset outward by ``margin_uv``. Where two
    strips meet, the shared outer corner is computed once so they join cleanly:
    convex corners keep their perpendicular corners and are filled with a
    rounded fan; concave (and straight) corners are mitered to the intersection
    of the two offset lines, so the strips meet at a point instead of piling up
    on top of each other. The offset direction is the edge normal in UV space;
    a mirrored face flips it so the band always grows away from the interior.
    """
    coordinates = []
    triangle_indices = []
    if margin_uv <= 0.0:
        return coordinates, triangle_indices

    # Pass 1: collect visible border segments. ``face_flip`` caches each face's
    # winding so it is not recomputed for every one of its border segments.
    segments = []
    seg_by_loop = {}
    face_flip = {}
    for edge in bm.edges:
        if edge not in border_edges:
            continue
        for loop in edge.link_loops:
            if not _loop_is_visible(loop, uv_sync):
                continue
            seg = {
                "loop": loop,
                "uv": loop[uv_layer].uv.copy(),
                "next_uv": loop.link_loop_next[uv_layer].uv.copy(),
                "normal": _segment_normal(loop, uv_layer, face_flip),
                "outer_start": None,
                "outer_end": None,
                "fan": None,
            }
            segments.append(seg)
            seg_by_loop[loop] = seg

    # Pass 2: resolve each corner's shared outer point (miter or fan).
    for seg in segments:
        normal = seg["normal"]
        vertex = seg["next_uv"]
        if normal.length_squared == 0.0:
            continue
        following = _next_border_loop(seg["loop"], border_edges)
        follow_seg = seg_by_loop.get(following)
        if follow_seg is None or follow_seg["normal"].length_squared == 0.0:
            continue
        follow_normal = follow_seg["normal"]
        edge_dir = vertex - seg["uv"]
        next_dir = follow_seg["next_uv"] - follow_seg["uv"]
        if _is_convex_corner(edge_dir, next_dir, normal):
            seg["outer_end"] = vertex + normal * margin_uv
            follow_seg["outer_start"] = vertex + follow_normal * margin_uv
            seg["fan"] = (normal.copy(), follow_normal.copy())
        else:
            miter = _miter_point(vertex, normal, follow_normal, margin_uv)
            if miter is not None:
                seg["outer_end"] = miter
                follow_seg["outer_start"] = miter

    # Pass 3: emit the strip quads and the convex fans.
    for seg in segments:
        normal = seg["normal"]
        inner_start = seg["uv"]
        inner_end = seg["next_uv"]
        outer_start = seg["outer_start"]
        if outer_start is None:
            outer_start = inner_start + normal * margin_uv
        outer_end = seg["outer_end"]
        if outer_end is None:
            outer_end = inner_end + normal * margin_uv

        base = len(coordinates)
        coordinates.extend((
            inner_start.to_tuple(5),
            inner_end.to_tuple(5),
            outer_start.to_tuple(5),
            outer_end.to_tuple(5),
        ))
        triangle_indices.extend((
            (base, base + 1, base + 2),
            (base + 2, base + 1, base + 3),
        ))

        if seg["fan"] is not None:
            normal_a, normal_b = seg["fan"]
            _add_round_join(
                coordinates,
                triangle_indices,
                seg["next_uv"],
                normal_a,
                normal_b,
                margin_uv,
            )

    return coordinates, triangle_indices


def _padding_batch_for_object(obj, uv_layer_name, margin_uv):
    bm = bmesh.from_edit_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    uv_layer = bm.loops.layers.uv.get(uv_layer_name)
    if uv_layer is None:
        return None

    uv_sync = bpy.context.scene.tool_settings.use_uv_select_sync
    border_edges = _collect_uv_border_edges(bm, uv_layer, uv_sync)
    if not border_edges:
        return None

    coordinates, triangle_indices = _padding_strip_geometry(
        bm, uv_layer, border_edges, margin_uv, uv_sync
    )
    if not coordinates:
        return None

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(
        shader,
        'TRIS',
        {"pos": coordinates},
        indices=triangle_indices,
    )
    batch.program_set(shader)
    return _uv_overlay.OverlayShape(batch, shader)


class SQC_GT_PaddingVisual(bpy.types.Gizmo):
    bl_idname = "SQC_GT_padding_visual"
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
        if not _padding.enabled:
            return
        if self.build_requested:
            _schedule_build(context, self)
            self.build_requested = False
        if not self.shapes:
            return
        _uv_overlay.draw_shapes(context, self.shapes, _PADDING_COLOR)


class SQC_GGT_PaddingVisual(bpy.types.GizmoGroup):
    bl_idname = "SQC_GGT_padding_visual"
    bl_label = "UV Padding Preview"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'EXCLUDE_MODAL', 'SCALE'}

    @classmethod
    def poll(cls, context):
        return (
            _padding.enabled
            and context.mode == 'EDIT_MESH'
            and context.active_object is not None
            and context.active_object.type == 'MESH'
        )

    def setup(self, context):
        self.visual_gizmo = self.gizmos.new(
            "SQC_GT_padding_visual"
        )
        self.visual_gizmo.hide_select = True
        _padding.gizmos[
            context.area.as_pointer()
        ] = self.visual_gizmo

        draw_id = str(uuid.uuid4())
        _padding.draw_handles[draw_id] = (
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
            draw_handle = _padding.draw_handles.pop(
                draw_id, None
            )
            if draw_handle is not None:
                bpy.types.SpaceImageEditor.draw_handler_remove(
                    draw_handle, 'WINDOW'
                )

    def refresh(self, context):
        pass


PADDING_VISUAL_CLASSES = (
    SQC_GT_PaddingVisual,
    SQC_GGT_PaddingVisual,
)


def enable_padding_visual(context, padding_px, texture_size):
    edit_objects = tuple(
        obj
        for obj in context.objects_in_mode_unique_data
        if obj.type == 'MESH' and obj.mode == 'EDIT'
    )
    if not edit_objects:
        return False

    _padding.invalidate()
    _padding.enabled = True
    _padding.margin_uv = _margin_uv(padding_px, texture_size)
    _padding.targets = {
        obj.name: (
            obj.data.uv_layers.active.name
            if obj.data.uv_layers.active is not None
            else ""
        )
        for obj in edit_objects
    }
    _ensure_handlers()
    _tag_uv_editor_redraw()
    _request_rebuild()
    return True


def disable_padding_visual():
    _padding.invalidate()
    _padding.enabled = False
    _padding.targets.clear()
    for area_pointer, gizmo in list(_padding.gizmos.items()):
        try:
            gizmo.shapes.clear()
            gizmo.build_requested = False
        except ReferenceError:
            _padding.gizmos.pop(area_pointer, None)
    _tag_uv_editor_redraw()


def _request_rebuild():
    for area_pointer, gizmo in list(_padding.gizmos.items()):
        try:
            gizmo.request_build()
        except ReferenceError:
            _padding.gizmos.pop(area_pointer, None)


def _schedule_build(context, visual_gizmo):
    if _padding.build_pending or not _padding.enabled:
        return
    _padding.build_pending = True
    generation = _padding.generation
    window, area, region = (
        context.window,
        context.area,
        context.region,
    )

    def delayed_build():
        if generation != _padding.generation:
            return None
        if not _padding.enabled:
            _padding.build_pending = False
            return None
        if _uv_overlay.is_modal_operation_running(bpy.context):
            return _MODAL_RETRY_DELAY
        _padding.build_pending = False
        try:
            with bpy.context.temp_override(
                window=window,
                area=area,
                region=region,
            ):
                _build_visual(visual_gizmo)
        except (ReferenceError, RuntimeError) as error:
            print(
                "[Scene QC Validator] Padding visual build "
                f"failed: {error}"
            )
        return None

    bpy.app.timers.register(
        delayed_build,
        first_interval=_BUILD_DELAY,
    )


def _build_visual(visual_gizmo):
    _padding.building = True
    try:
        visual_gizmo.shapes.clear()
        for object_name, uv_layer_name in (
            _padding.targets.items()
        ):
            obj = bpy.context.scene.objects.get(object_name)
            if obj is None or obj.mode != 'EDIT':
                continue
            shape = _padding_batch_for_object(
                obj,
                uv_layer_name,
                _padding.margin_uv,
            )
            if shape is not None:
                visual_gizmo.shapes.append(shape)
    finally:
        _padding.building = False
        _tag_uv_editor_redraw()


@bpy.app.handlers.persistent
def _padding_depsgraph_update(_scene, depsgraph):
    if not _padding.enabled or _padding.building:
        return
    target_meshes = {
        obj.data
        for object_name in _padding.targets
        if (
            (obj := bpy.context.scene.objects.get(object_name))
            is not None
            and obj.mode == 'EDIT'
        )
    }
    if not target_meshes:
        disable_padding_visual()
        return
    if any(
        isinstance(update.id, bpy.types.Mesh)
        and (
            update.id in target_meshes
            or getattr(update.id, "original", None)
            in target_meshes
        )
        and update.is_updated_geometry
        for update in depsgraph.updates
    ):
        _request_rebuild()
        _tag_uv_editor_redraw()


@bpy.app.handlers.persistent
def _padding_load_pre(_unused):
    disable_padding_visual()
    _remove_draw_handlers()
    _padding.gizmos.clear()


def _ensure_handlers():
    if not _padding.depsgraph_handler_registered:
        bpy.app.handlers.depsgraph_update_post.append(
            _padding_depsgraph_update
        )
        _padding.depsgraph_handler_registered = True
    if not _padding.load_handler_registered:
        bpy.app.handlers.load_pre.append(_padding_load_pre)
        _padding.load_handler_registered = True


def _tag_uv_editor_redraw():
    screen = getattr(bpy.context, "screen", None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type == 'IMAGE_EDITOR':
            area.tag_redraw()


def _remove_draw_handlers():
    for draw_id, draw_handle in list(
        _padding.draw_handles.items()
    ):
        try:
            bpy.types.SpaceImageEditor.draw_handler_remove(
                draw_handle, 'WINDOW'
            )
        except (ReferenceError, ValueError):
            pass
        _padding.draw_handles.pop(draw_id, None)


def unregister_padding_visual():
    disable_padding_visual()
    if (
        _padding.depsgraph_handler_registered
        and _padding_depsgraph_update
        in bpy.app.handlers.depsgraph_update_post
    ):
        bpy.app.handlers.depsgraph_update_post.remove(
            _padding_depsgraph_update
        )
    _padding.depsgraph_handler_registered = False
    if (
        _padding.load_handler_registered
        and _padding_load_pre in bpy.app.handlers.load_pre
    ):
        bpy.app.handlers.load_pre.remove(_padding_load_pre)
    _padding.load_handler_registered = False
    _remove_draw_handlers()
    _padding.gizmos.clear()


def _padding_check_item(context):
    """Return the 'uv_padding' checklist item, or None when it is absent."""
    return next(
        (
            check
            for check in context.scene.sqc_settings.checks
            if check.check_id == "uv_padding"
        ),
        None,
    )


class SQC_OT_StepPaddingValue(Operator):
    bl_idname = "sqc.step_padding_value"
    bl_label = "Change Padding Preview Value"

    target: EnumProperty(
        items=(
            ('TEXTURE', "Texture Size", ""),
            ('PADDING', "Padding", ""),
        ),
    )
    direction: IntProperty(default=1)

    @classmethod
    def description(cls, context, properties):
        if properties.target == 'TEXTURE':
            operation = (
                "Double"
                if properties.direction > 0
                else "Halve"
            )
            return f"{operation} the texture resolution"
        operation = "Increase" if properties.direction > 0 else "Decrease"
        return f"{operation} padding by 1 px"

    def execute(self, context):
        item = _padding_check_item(context)
        if item is None:
            return {'CANCELLED'}

        if self.target == 'TEXTURE':
            value = max(256, item.int_param_2)
            item.int_param_2 = (
                min(16384, value * 2)
                if self.direction > 0
                else max(256, value // 2)
            )
        else:
            value = max(0, item.int_param_1)
            item.int_param_1 = max(
                0,
                value + (1 if self.direction > 0 else -1),
            )
        return {'FINISHED'}
