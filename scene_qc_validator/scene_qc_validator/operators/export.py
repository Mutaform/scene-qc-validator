import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from .core import (
    _scope_empty_message,
    _select_only,
    _settings,
    _validation_targets,
    run_validation_logic,
)


def _fbx_axis_value(value):
    if isinstance(value, str):
        return value.replace('NEG_', '-')
    return value


def _fbx_export_kwargs(path, **kwargs):
    object_types = set()
    if kwargs.get('type_empty', True):
        object_types.add('EMPTY')
    if kwargs.get('type_camera', True):
        object_types.add('CAMERA')
    if kwargs.get('type_lamp', True):
        object_types.add('LIGHT')
    if kwargs.get('type_armature', True):
        object_types.add('ARMATURE')
    if kwargs.get('type_mesh', True):
        object_types.add('MESH')
    if kwargs.get('type_other', True):
        object_types.add('OTHER')

    return dict(
        filepath=path,
        check_existing=kwargs.get('check_existing', False),
        filter_glob=kwargs.get('filter_glob', '*.fbx'),
        use_selection=kwargs.get('use_selection', True),
        use_visible=kwargs.get('use_visible', False),
        use_active_collection=kwargs.get('use_active_collection', False),
        global_scale=kwargs.get('global_scale', 1.0),
        apply_unit_scale=kwargs.get('apply_unit_scale', True),
        apply_scale_options=kwargs.get('apply_scale_options', 'FBX_SCALE_NONE'),
        use_space_transform=kwargs.get('use_space_transform', True),
        bake_space_transform=kwargs.get('bake_space_transform', False),
        object_types=object_types,
        use_mesh_modifiers=kwargs.get('use_mesh_modifiers', True),
        use_mesh_modifiers_render=kwargs.get('use_mesh_modifiers_render', True),
        mesh_smooth_type=kwargs.get('mesh_smooth_type', 'OFF'),
        colors_type=kwargs.get('colors_type', 'SRGB'),
        use_subsurf=kwargs.get('use_subsurf', False),
        use_mesh_edges=kwargs.get('use_mesh_edges', False),
        use_tspace=kwargs.get('use_tspace', False),
        use_triangles=kwargs.get('use_triangles', False),
        use_custom_props=kwargs.get('use_custom_props', False),
        add_leaf_bones=kwargs.get('add_leaf_bones', True),
        primary_bone_axis=_fbx_axis_value(kwargs.get('primary_bone_axis', 'Y')),
        secondary_bone_axis=_fbx_axis_value(kwargs.get('secondary_bone_axis', 'X')),
        use_armature_deform_only=kwargs.get('use_armature_deform_only', False),
        armature_nodetype=kwargs.get('armature_nodetype', 'NULL'),
        bake_anim=kwargs.get('bake_anim', True),
        bake_anim_use_all_bones=kwargs.get('bake_anim_use_all_bones', True),
        bake_anim_use_nla_strips=kwargs.get('bake_anim_use_nla_strips', True),
        bake_anim_use_all_actions=kwargs.get('bake_anim_use_all_actions', True),
        bake_anim_force_startend_keying=kwargs.get('bake_anim_force_startend_keying', True),
        bake_anim_step=kwargs.get('bake_anim_step', 1.0),
        bake_anim_simplify_factor=kwargs.get('bake_anim_simplify_factor', 1.0),
        path_mode=kwargs.get('path_mode', 'AUTO'),
        embed_textures=kwargs.get('embed_textures', False),
        batch_mode=kwargs.get('batch_mode', 'OFF'),
        use_batch_own_dir=kwargs.get('use_batch_own_dir', True),
        use_metadata=kwargs.get('use_metadata', True),
        axis_forward=_fbx_axis_value(kwargs.get('axis_forward', '-Z')),
        axis_up=_fbx_axis_value(kwargs.get('axis_up', 'Y')),
    )


def _export_fbx_with_mutaform_preset(path, invoke=False, **kwargs):
    export_kwargs = _fbx_export_kwargs(path, **kwargs)
    if invoke:
        return bpy.ops.export_scene.fbx('INVOKE_DEFAULT', **export_kwargs)
    return bpy.ops.export_scene.fbx(**export_kwargs)


class SQC_OT_validate_and_export(Operator):
    bl_idname = "sqc.validate_and_export"
    bl_label = "Export"
    bl_description = "Runs the checklist; opens FBX export only if there are no blocking Fail results"

    def execute(self, context):
        targets_found, any_fail = run_validation_logic(context)
        if not targets_found:
            self.report({'WARNING'}, _scope_empty_message(_settings(context).validation_scope))
            return {'CANCELLED'}
        if any_fail:
            self.report({'ERROR'}, "Export blocked: resolve Fail results first")
            return {'CANCELLED'}
        targets = _validation_targets(context)
        _select_only(context, targets)
        bpy.ops.export_scene.fbx('INVOKE_DEFAULT')
        return {'FINISHED'}


class SQC_OT_export_fbx(Operator):
    bl_idname = "sqc.export_fbx"
    bl_label = "Export FBX"

    filepath: StringProperty(subtype='FILE_PATH')

    def invoke(self, context, event):
        import os
        s = _settings(context)
        base = bpy.path.abspath(s.export_directory or "//")
        scene_name = bpy.path.basename(bpy.data.filepath) or "export"
        scene_name = os.path.splitext(scene_name)[0] or "export"
        self.filepath = os.path.join(base, scene_name + ".fbx")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        s = _settings(context)
        targets = _validation_targets(context)
        if not targets:
            self.report({'WARNING'}, _scope_empty_message(s.validation_scope))
            return {'CANCELLED'}
        _select_only(context, targets)
        bpy.ops.export_scene.fbx('INVOKE_DEFAULT')
        return {'FINISHED'}
