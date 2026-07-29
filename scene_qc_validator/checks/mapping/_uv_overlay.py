"""Shared GPU-overlay helpers for UV-Editor previews.

The overlap and padding previews both draw filled shapes on top of the UV
Editor. Everything they genuinely share lives here so each preview only has to
build its own batch geometry and pick a colour:

* :class:`OverlayShape` - a drawable (batch, shader) pair;
* :func:`uv_to_region_matrix` - the UV(0-1) -> region-pixel matrix;
* :func:`draw_shapes` - draw a list of shapes in that space;
* :func:`is_modal_operation_running` - guard so a rebuild waits for modal ops.
"""

import ctypes
from ctypes import c_char, c_int, c_short, c_void_p, Structure
from dataclasses import dataclass

import gpu
from mathutils import Matrix


@dataclass
class OverlayShape:
    batch: object
    shader: object


# ---------------------------------------------------------------------------
# Modal-operator guard
#
# A GPU batch must not be rebuilt while a modal operator (transform, knife, ...)
# is mid-flight. Blender exposes no Python flag for that, so we read the active
# window's cursor state directly from the wmWindow C struct. The field layout
# shifts between Blender versions, hence the version-gated fields below.


class _ListBase(Structure):
    _fields_ = (("first", c_void_p), ("last", c_void_p))


def _window_manager_fields():
    import bpy
    fields = [
        ("next", c_void_p),
        ("prev", c_void_p),
    ]
    if bpy.app.version < (5, 1, 0):
        fields.extend((
            ("ghostwin", c_void_p),
            ("gpuctx", c_void_p),
        ))
    fields.extend((
        ("parent", c_void_p),
        ("scene", c_void_p),
        ("new_scene", c_void_p),
        ("view_layer_name", c_char * 64),
        ("unpinned_scene", c_void_p),
        ("workspace_hook", c_void_p),
        ("global_areas", _ListBase * 3),
        ("screen", c_void_p),
        ("winid", c_int),
        ("pos", c_short * 2),
        ("size", c_short * 2),
        ("windowstate", c_char),
        ("active", c_char),
        ("cursor", c_short),
        ("lastcursor", c_short),
        ("modalcursor", c_short),
        ("grabcursor", c_short),
    ))
    return fields


class _WindowManagerState(Structure):
    _fields_ = tuple(_window_manager_fields())


def is_modal_operation_running(context):
    """True while a modal operator holds the cursor (transform, knife, ...).

    Errs on the side of caution: any failure to read the struct is reported as
    "running" so callers postpone their rebuild instead of risking a crash.
    """
    try:
        window = context.window
        while window.parent is not None:
            window = window.parent
        window_state = ctypes.cast(
            window.as_pointer(),
            ctypes.POINTER(_WindowManagerState),
        ).contents
        return (
            window_state.modalcursor != 0
            or window_state.grabcursor != 0
        )
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Drawing


def uv_to_region_matrix(context):
    """Return the UV(0-1) -> region-pixel matrix for the current UV Editor.

    Returns ``None`` when there is no usable viewport/region to draw into.
    """
    viewport = gpu.state.viewport_get()
    width = viewport[2]
    height = viewport[3]
    region = context.region
    if width <= 0 or height <= 0 or region is None:
        return None

    uv_to_view = region.view2d.view_to_region
    origin_x, origin_y = uv_to_view(0, 0, clip=False)
    top_x, top_y = uv_to_view(1.0, 1.0, clip=False)
    return Matrix((
        (
            (top_x - origin_x) / width * 2,
            0,
            0,
            2.0 * -((width - origin_x - 0.5 * width) / width),
        ),
        (
            0,
            (top_y - origin_y) / height * 2,
            0,
            2.0 * -((height - origin_y - 0.5 * height) / height),
        ),
        (0, 0, 1.0, 0),
        (0, 0, 0, 1.0),
    ))


def draw_shapes(context, shapes, color):
    """Draw ``shapes`` (OverlayShape list) in UV space with a flat ``color``."""
    matrix = uv_to_region_matrix(context)
    if matrix is None:
        return

    gpu.state.blend_set('ALPHA')
    with gpu.matrix.push_pop():
        gpu.matrix.load_matrix(matrix)
        with gpu.matrix.push_pop_projection():
            gpu.matrix.load_projection_matrix(Matrix.Identity(4))
            for shape in shapes:
                shape.shader.bind()
                shape.shader.uniform_float("color", color)
                shape.batch.draw(shape.shader)
    gpu.state.blend_set('NONE')
