"""Validate that every UV-shell border is marked sharp."""

from ..common import *
from .random_sharp import _uv_border_edges, _uv_border_edges_from_bmesh


def check_no_hard_edge_on_uv_borders(obj, item):
    if obj.data.is_editmode:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        uv_borders = _uv_border_edges_from_bmesh(bm, 0.001)
        bad = [
            edge.index
            for edge in bm.edges
            if edge.index in uv_borders and edge.smooth
        ]
    else:
        uv_borders = _uv_border_edges(obj, 0.001)
        bad = [
            edge.index
            for edge in obj.data.edges
            if edge.index in uv_borders and not edge.use_edge_sharp
        ]

    if bad:
        return [{
            "message": f"{len(bad)} UV-shell border edge(s) are not marked sharp",
            "element_ref": "e:" + ",".join(map(str, bad)),
        }]
    return []


def fix_no_hard_edge_on_uv_borders(obj, item, result):
    """Mark only UV-shell border edges sharp; existing seams are untouched."""
    if obj.data.is_editmode:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        uv_borders = _uv_border_edges_from_bmesh(bm, 0.001)
        changed = False
        for edge in bm.edges:
            if edge.index in uv_borders and edge.smooth:
                edge.smooth = False
                changed = True
        if changed:
            bmesh.update_edit_mesh(obj.data)
        return changed

    uv_borders = _uv_border_edges(obj, 0.001)
    changed = False
    for edge in obj.data.edges:
        if edge.index in uv_borders and not edge.use_edge_sharp:
            edge.use_edge_sharp = True
            changed = True
    if changed:
        obj.data.update()
    return changed
