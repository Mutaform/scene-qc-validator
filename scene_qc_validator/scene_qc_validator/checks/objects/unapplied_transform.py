from ..common import *


def check_unapplied_transform(obj, item):
    eps = 1e-4
    flags = item.string_param_1 or "loc,rot,scale"
    check_loc = "loc" in flags
    check_rot = "rot" in flags
    check_scale = "scale" in flags

    bad = []
    if check_loc and obj.location.length > eps:
        bad.append("translation")
    if check_rot:
        if obj.rotation_mode == 'QUATERNION':
            identity = mathutils.Quaternion()
            if (obj.rotation_quaternion - identity).magnitude > eps:
                bad.append("rotation")
        else:
            if obj.rotation_euler.to_quaternion().angle > eps:
                bad.append("rotation")
    if check_scale and (obj.scale - mathutils.Vector((1, 1, 1))).length > eps:
        bad.append("scale")

    if bad:
        return [{
            "message": f"Unapplied {', '.join(bad)}",
            "element_ref": "",
        }]
    return []


def fix_unapplied_transform(obj, item, result):
    flags = item.string_param_1 or "loc,rot,scale"
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.ops.object.transform_apply(
        location="loc" in flags,
        rotation="rot" in flags,
        scale="scale" in flags,
    )
    return True
