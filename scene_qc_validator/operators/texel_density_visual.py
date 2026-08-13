"""GPU-only UV texel-density review, sharing the UV review session lifecycle."""
from dataclasses import dataclass, field
import math
import uuid

import bmesh
import bpy
import gpu
from bpy.types import Operator
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from ..checks.mapping import _uv_overlay
from . import uv_review_session


@dataclass
class _Runtime:
    active: bool = False
    source_object_name: str = ""
    targets: dict = field(default_factory=dict)
    gizmos: dict = field(default_factory=dict)
    draw_handles: dict = field(default_factory=dict)
    build_pending: bool = False
    building: bool = False
    generation: int = 0
    depsgraph_handler_registered: bool = False
    load_handler_registered: bool = False
    selection_signature: tuple = ()
    selection_timer_registered: bool = False

    def invalidate(self):
        self.generation += 1
        self.build_pending = False


_review = _Runtime()


# A tint, not a replacement: selected UVs must retain their density colour.
_SELECTED_COLOR = (0.0, 1.0, 0.0, 0.32)
_SELECTED_ELEMENT_COLOR = (1.0, 0.35, 0.0, 1.0)


def is_texel_density_review_active():
    return _review.active


def _tag_redraw():
    if bpy.context.screen:
        for area in bpy.context.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.tag_redraw()


def _color(ratio):
    amount = min(1.0, abs(math.log(max(ratio, 1e-12), 2.0)) / 2.0)
    green = (193 / 255, 237 / 255, 211 / 255, 1.0)  # #C1EDD3
    end = (0.95, 0.08, 0.08, 1.0) if ratio < 1 else (0.05, 0.18, 0.98, 1.0)
    return tuple(green[i] * (1 - amount) + end[i] * amount for i in range(4))


def _face_selected(face, uv_layer, uv_sync):
    if uv_sync:
        return face.select
    return all(loop.uv_select_vert for loop in face.loops)


def _selection_signature():
    """Selection-only edits do not always produce a depsgraph geometry
    update, so a lightweight signature is polled to trigger rebuilds."""
    signature = []
    uv_sync = bpy.context.scene.tool_settings.use_uv_select_sync
    for name, uv_name in _review.targets.items():
        obj = bpy.context.scene.objects.get(name)
        if obj is None or obj.mode != 'EDIT':
            continue
        bm = bmesh.from_edit_mesh(obj.data)
        uv = bm.loops.layers.uv.get(uv_name) or bm.loops.layers.uv.active
        if uv is None:
            continue
        signature.append((name, tuple(
            (
                face.index,
                tuple(
                    (
                        (loop.vert.select if uv_sync else loop.uv_select_vert),
                        (loop.edge.select if uv_sync else loop.uv_select_edge),
                    )
                    for loop in face.loops
                ),
            )
            for face in bm.faces
            if _face_selected(face, uv, uv_sync)
            or any(
                (loop.vert.select if uv_sync else loop.uv_select_vert)
                or (loop.edge.select if uv_sync else loop.uv_select_edge)
                for loop in face.loops
            )
        )))
    return tuple(signature)


def _build_shapes(objects):
    faces, total_uv, total_world = [], 0.0, 0.0
    uv_sync = bpy.context.scene.tool_settings.use_uv_select_sync
    all_edges, border_edges = [], []
    # Keep every BMesh wrapper alive until the second pass below: dropping
    # the last Python reference garbage-collects the wrapper and invalidates
    # the BMFace references held in ``faces`` (multi-object builds crashed
    # with "BMesh data of type BMFace has been removed").
    edit_meshes = []
    for obj in objects:
        bm = bmesh.from_edit_mesh(obj.data)
        edit_meshes.append(bm)
        uv = (
            bm.loops.layers.uv.get(_review.targets.get(obj.name, ''))
            or bm.loops.layers.uv.active
        )
        if not uv:
            continue
        for face in bm.faces:
            world = face.calc_area()
            area = abs(sum(
                loop[uv].uv.cross(loop.link_loop_next[uv].uv)
                for loop in face.loops
            )) * .5
            if world > 1e-12 and area > 1e-12:
                faces.append(
                    (face, uv, area, world, _face_selected(face, uv, uv_sync))
                )
                total_uv += area
                total_world += world
                for loop in face.loops:
                    all_edges.extend((
                        loop[uv].uv.to_3d(),
                        loop.link_loop_next[uv].uv.to_3d(),
                    ))
        # A mesh boundary or a UV discontinuity is the outline of a UV island.
        for edge in bm.edges:
            loops = edge.link_loops
            if not loops:
                continue
            is_border = len(loops) == 1
            if not is_border:
                first = loops[0]
                across = first.link_loop_radial_next.link_loop_next
                is_border = first[uv].uv != across[uv].uv
            if is_border:
                for loop in loops:
                    border_edges.extend((
                        loop[uv].uv.to_3d(),
                        loop.link_loop_next[uv].uv.to_3d(),
                    ))
    if not faces or total_world <= 0:
        return []
    average = total_uv / total_world
    pos, colors, selected_pos = [], [], []
    selected_vertices, selected_edges = [], []
    for face, uv, area, world, selected in faces:
        color = _color((area / world) / average)
        loops = list(face.loops)
        for i in range(1, len(loops) - 1):
            for loop in (loops[0], loops[i], loops[i + 1]):
                point = loop[uv].uv.to_3d()
                pos.append(point)
                colors.append(color)
                if selected:
                    selected_pos.append(point)
        for loop in loops:
            vertex_selected = (
                loop.vert.select if uv_sync else loop.uv_select_vert
            )
            edge_selected = (
                loop.edge.select if uv_sync else loop.uv_select_edge
            )
            if vertex_selected:
                selected_vertices.append(loop[uv].uv.to_3d())
            if edge_selected:
                selected_edges.extend((
                    loop[uv].uv.to_3d(),
                    loop.link_loop_next[uv].uv.to_3d(),
                ))
    if not pos:
        return []
    shader = gpu.shader.from_builtin('SMOOTH_COLOR')
    shapes = [(
        'fill',
        batch_for_shader(shader, 'TRIS', {'pos': pos, 'color': colors}),
        shader,
    )]
    line_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    if selected_pos:
        shapes.append((
            'selection',
            batch_for_shader(line_shader, 'TRIS', {'pos': selected_pos}),
            line_shader,
            _SELECTED_COLOR,
        ))
    if all_edges:
        shapes.append((
            'line',
            batch_for_shader(line_shader, 'LINES', {'pos': all_edges}),
            line_shader,
            (0.0, 0.0, 0.0, 1.0),
            1.0,
        ))
    if border_edges:
        shapes.append((
            'line',
            batch_for_shader(line_shader, 'LINES', {'pos': border_edges}),
            line_shader,
            (0.0, 1.0, 0.0, 1.0),
            2.0,
        ))
    if selected_edges:
        # Polyline shader expands and smooths the line in screen space,
        # avoiding the stair-step artefacts of wide GL lines.
        smooth_shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        shapes.append((
            'polyline',
            batch_for_shader(smooth_shader, 'LINES', {'pos': selected_edges}),
            smooth_shader,
            _SELECTED_ELEMENT_COLOR,
            2.5,
        ))
    if selected_vertices:
        shapes.append((
            'point',
            batch_for_shader(line_shader, 'POINTS', {'pos': selected_vertices}),
            line_shader,
            _SELECTED_ELEMENT_COLOR,
            6.0,
        ))
    return shapes


class SQC_GT_TexelDensityVisual(bpy.types.Gizmo):
    bl_idname = 'SQC_GT_texel_density_visual'
    bl_target_properties = ()
    __slots__ = ('shapes', 'build_requested')

    def setup(self):
        self.shapes = []
        self.build_requested = True

    def draw(self, context):
        pass

    def test_select(self, context, location):
        return -1

    def request_build(self):
        self.build_requested = True

    def draw_overlay(self, context):
        if not _review.active:
            return
        if self.build_requested:
            _schedule_build(context, self)
            self.build_requested = False
        matrix = _uv_overlay.uv_to_region_matrix(context)
        if not self.shapes or matrix is None:
            return
        gpu.state.blend_set('ALPHA')
        with gpu.matrix.push_pop():
            gpu.matrix.load_matrix(matrix)
            with gpu.matrix.push_pop_projection():
                gpu.matrix.load_projection_matrix(Matrix.Identity(4))
                for shape in self.shapes:
                    if shape[0] == 'fill':
                        _, batch, shader = shape
                        shader.bind()
                        batch.draw(shader)
                    elif shape[0] == 'selection':
                        _, batch, shader, color = shape
                        shader.bind()
                        shader.uniform_float('color', color)
                        batch.draw(shader)
                    elif shape[0] == 'point':
                        _, batch, shader, color, size = shape
                        gpu.state.point_size_set(size)
                        shader.bind()
                        shader.uniform_float('color', color)
                        batch.draw(shader)
                    elif shape[0] == 'polyline':
                        _, batch, shader, color, width = shape
                        viewport = gpu.state.viewport_get()
                        shader.bind()
                        shader.uniform_float(
                            'viewportSize', (viewport[2], viewport[3])
                        )
                        shader.uniform_float('lineWidth', width)
                        shader.uniform_float('color', color)
                        batch.draw(shader)
                    else:
                        _, batch, shader, color, width = shape
                        gpu.state.line_width_set(width)
                        shader.bind()
                        shader.uniform_float('color', color)
                        batch.draw(shader)
                gpu.state.line_width_set(1.0)
                gpu.state.point_size_set(1.0)
        gpu.state.blend_set('NONE')


class SQC_GGT_TexelDensityVisual(bpy.types.GizmoGroup):
    bl_idname = 'SQC_GGT_texel_density_visual'
    bl_label = 'UV Texel Density Preview'
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'EXCLUDE_MODAL', 'SCALE'}

    @classmethod
    def poll(cls, context):
        return (
            _review.active
            and context.mode == 'EDIT_MESH'
            and context.active_object
            and context.active_object.type == 'MESH'
        )

    def setup(self, context):
        self.visual_gizmo = self.gizmos.new('SQC_GT_texel_density_visual')
        self.visual_gizmo.hide_select = True
        _review.gizmos[context.area.as_pointer()] = self.visual_gizmo
        key = str(uuid.uuid4())
        _review.draw_handles[key] = (
            bpy.types.SpaceImageEditor.draw_handler_add(
                self._draw_post_pixel, (key,), 'WINDOW', 'POST_PIXEL'
            )
        )

    def _draw_post_pixel(self, key):
        try:
            context = bpy.context
            if self.poll(context):
                self.visual_gizmo.draw_overlay(context)

                # Composite the overlap preview after texel density.
                # Independent POST_PIXEL handlers are otherwise ordered by
                # activation time, which lets the opaque density fill cover
                # the overlap color.
                from ..checks.mapping import overlapped_uv
                overlap_gizmo = overlapped_uv._overlap_visual.gizmos.get(
                    context.area.as_pointer()
                )
                if (
                    overlapped_uv.is_overlap_visual_enabled()
                    and overlap_gizmo is not None
                ):
                    overlap_gizmo.draw_overlay(context)
        except ReferenceError:
            handle = _review.draw_handles.pop(key, None)
            if handle is not None:
                bpy.types.SpaceImageEditor.draw_handler_remove(
                    handle, 'WINDOW'
                )

    def refresh(self, context):
        pass


TEXEL_DENSITY_VISUAL_CLASSES = (
    SQC_GT_TexelDensityVisual,
    SQC_GGT_TexelDensityVisual,
)


def _request_rebuild():
    for key, gizmo in list(_review.gizmos.items()):
        try:
            gizmo.request_build()
        except ReferenceError:
            _review.gizmos.pop(key, None)


def _schedule_build(context, gizmo):
    if _review.build_pending or not _review.active:
        return
    _review.build_pending = True
    generation = _review.generation
    window, area, region = context.window, context.area, context.region

    def build():
        if generation != _review.generation:
            return None
        if not _review.active:
            _review.build_pending = False
            return None
        if _uv_overlay.is_modal_operation_running(bpy.context):
            return .05
        _review.build_pending = False
        try:
            with bpy.context.temp_override(
                window=window, area=area, region=region
            ):
                objects = [
                    obj
                    for name in _review.targets
                    if (obj := bpy.context.scene.objects.get(name))
                    and obj.mode == 'EDIT'
                ]
                _review.building = True
                gizmo.shapes = _build_shapes(objects)
        finally:
            _review.building = False
            _tag_redraw()
        return None

    bpy.app.timers.register(build, first_interval=.08)


@bpy.app.handlers.persistent
def _depsgraph(_scene, depsgraph):
    if not _review.active or _review.building:
        return
    meshes = {
        obj.data
        for name in _review.targets
        if (obj := bpy.context.scene.objects.get(name))
        and obj.mode == 'EDIT'
    }
    if any(
        isinstance(u.id, bpy.types.Mesh)
        and (u.id in meshes or getattr(u.id, 'original', None) in meshes)
        and u.is_updated_geometry
        for u in depsgraph.updates
    ):
        _request_rebuild()
        _tag_redraw()


@bpy.app.handlers.persistent
def _texel_load_pre(_unused):
    _disable_overlay()
    _review.active = False
    _review.source_object_name = ""
    for key, handle in list(_review.draw_handles.items()):
        try:
            bpy.types.SpaceImageEditor.draw_handler_remove(handle, 'WINDOW')
        except (ReferenceError, ValueError):
            pass
        _review.draw_handles.pop(key, None)
    _review.gizmos.clear()


def _ensure_handlers():
    if not _review.depsgraph_handler_registered:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph)
        _review.depsgraph_handler_registered = True
    if not _review.load_handler_registered:
        bpy.app.handlers.load_pre.append(_texel_load_pre)
        _review.load_handler_registered = True
    if not _review.selection_timer_registered:
        _review.selection_timer_registered = True

        def watch_selection():
            if not _review.active:
                _review.selection_timer_registered = False
                return None
            # Match the overlap renderer's safety rule: never inspect BMesh
            # while a transform/modal tool owns it.
            if _uv_overlay.is_modal_operation_running(bpy.context):
                return 0.05
            signature = _selection_signature()
            if signature != _review.selection_signature:
                _review.selection_signature = signature
                _request_rebuild()
                _tag_redraw()
            return 0.08

        bpy.app.timers.register(watch_selection, first_interval=0.08)


def _disable_overlay():
    _review.invalidate()
    _review.targets.clear()
    _review.selection_signature = ()
    for gizmo in _review.gizmos.values():
        try:
            gizmo.shapes.clear()
            gizmo.build_requested = False
        except ReferenceError:
            pass
    _tag_redraw()


def restore_texel_density_review(context):
    _disable_overlay()
    restored = uv_review_session.release(context, 'TEXEL_DENSITY')
    _review.active = False
    _review.source_object_name = ""
    _tag_redraw()
    return restored


class SQC_OT_ToggleTexelDensityVisual(Operator):
    bl_idname = 'sqc.toggle_texel_density_visual'
    bl_label = 'Show Texel Density'
    bl_description = (
        'Preview UV scale: green is average, red is smaller and blue is larger'
    )

    def execute(self, context):
        source = context.active_object
        if _review.active:
            if (
                source is None
                or source.type != 'MESH'
                or source.name == _review.source_object_name
            ):
                restore_texel_density_review(context)
                return {'FINISHED'}
            requested_object_name = source.name
            restore_texel_density_review(context)
            source = context.scene.objects.get(requested_object_name)
        if (
            not source
            or source.type != 'MESH'
            or not source.data.uv_layers.active
        ):
            self.report({'WARNING'}, 'Select a mesh with an active UV map')
            return {'CANCELLED'}

        settings = context.scene.sqc_settings
        material = source.active_material
        if not settings.texel_density_visual_use_material_scope or material is None:
            targets = [source]
        else:
            targets, _material = uv_review_session.material_targets(
                context, source
            )
        if not targets:
            self.report({'WARNING'}, 'No visible UV meshes to preview')
            return {'CANCELLED'}

        try:
            uv_review_session.enter_review_edit(
                context, 'TEXEL_DENSITY', source, targets
            )
            _review.targets = {
                obj.name: obj.data.uv_layers.active.name for obj in targets
            }
            _review.active = True
            _review.source_object_name = source.name
            _review.selection_signature = _selection_signature()
            _ensure_handlers()
            _request_rebuild()
            _tag_redraw()
            return {'FINISHED'}
        except RuntimeError as error:
            self.report({'WARNING'}, str(error))
            restore_texel_density_review(context)
            return {'CANCELLED'}


def unregister_texel_density_review():
    _disable_overlay()
    _review.active = False
    _review.source_object_name = ""
    if (
        _review.depsgraph_handler_registered
        and _depsgraph in bpy.app.handlers.depsgraph_update_post
    ):
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph)
    _review.depsgraph_handler_registered = False
    if (
        _review.load_handler_registered
        and _texel_load_pre in bpy.app.handlers.load_pre
    ):
        bpy.app.handlers.load_pre.remove(_texel_load_pre)
    _review.load_handler_registered = False
    for key, handle in list(_review.draw_handles.items()):
        try:
            bpy.types.SpaceImageEditor.draw_handler_remove(handle, 'WINDOW')
        except (ReferenceError, ValueError):
            pass
        _review.draw_handles.pop(key, None)
    _review.gizmos.clear()
