from ..common import *


def _seam_edges_without_sharp_from_edit_mesh(obj):
    previous_active = bpy.context.view_layer.objects.active
    previous_selected = list(bpy.context.selected_objects)
    previous_mode = bpy.context.object.mode if bpy.context.object else 'OBJECT'

    try:
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for selected in bpy.context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        bad = [edge.index for edge in bm.edges if edge.seam and edge.smooth]
        bmesh.update_edit_mesh(obj.data)
        return bad
    finally:
        try:
            if bpy.context.object and bpy.context.object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass
        for selected in bpy.context.selected_objects:
            selected.select_set(False)
        for selected in previous_selected:
            if bpy.context.scene.objects.get(selected.name):
                selected.select_set(True)
        if previous_active and bpy.context.scene.objects.get(previous_active.name):
            bpy.context.view_layer.objects.active = previous_active
        if previous_mode != 'OBJECT' and bpy.context.object:
            try:
                bpy.ops.object.mode_set(mode=previous_mode)
            except RuntimeError:
                pass


def check_seams_is_marked_sharp(obj, item):
    bad = _seam_edges_without_sharp_from_edit_mesh(obj)
    if bad:
        return [{
            "message": f"Object {obj.name} have seams that should be marked as sharp",
            "element_ref": "e:" + ",".join(map(str, bad)),
        }]
    return []



def fix_seams_is_marked_sharp(obj, item, result):
    previous_active = bpy.context.view_layer.objects.active
    previous_selected = list(bpy.context.selected_objects)
    previous_mode = bpy.context.object.mode if bpy.context.object else 'OBJECT'
    changed = False

    try:
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for selected in bpy.context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        for edge in bm.edges:
            if edge.seam and edge.smooth:
                edge.smooth = False
                changed = True
        bmesh.update_edit_mesh(obj.data)
    finally:
        try:
            if bpy.context.object and bpy.context.object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass
        for selected in bpy.context.selected_objects:
            selected.select_set(False)
        for selected in previous_selected:
            if bpy.context.scene.objects.get(selected.name):
                selected.select_set(True)
        if previous_active and bpy.context.scene.objects.get(previous_active.name):
            bpy.context.view_layer.objects.active = previous_active
        if previous_mode != 'OBJECT' and bpy.context.object:
            try:
                bpy.ops.object.mode_set(mode=previous_mode)
            except RuntimeError:
                pass

    return changed
