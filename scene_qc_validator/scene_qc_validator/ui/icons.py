import os

import bpy.utils.previews


_preview_icons = None


def _asset_path(filename):
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", filename)


def register():
    global _preview_icons
    if _preview_icons is not None:
        return
    _preview_icons = bpy.utils.previews.new()
    _preview_icons.load("checker_grid", _asset_path("icon_checker_grid.png"), 'IMAGE')
    _preview_icons.load("checker_lines", _asset_path("icon_checker_lines.png"), 'IMAGE')


def unregister():
    global _preview_icons
    if _preview_icons is None:
        return
    bpy.utils.previews.remove(_preview_icons)
    _preview_icons = None


def icon_id(name):
    if _preview_icons is None:
        return 0
    icon = _preview_icons.get(name)
    return icon.icon_id if icon else 0
