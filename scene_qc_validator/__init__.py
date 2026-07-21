"""
Scene QC Validator by Mutaform LLC
Mesh/scene validation checklist with presets.
Developed by Mutaform Studio.

Packaged as a Blender Extension (blender_manifest.toml) for Blender 4.2+ / 5.1.
"""

import bpy

from . import properties
from . import operators
from . import ui

_MODULES = (properties, operators, ui)


def _init_checks_for_open_scenes():
    """Runs outside of any UI draw() context so it's safe to write Scene
    data. Panel draw() must never mutate scene data directly (Blender
    disallows writes to ID data-blocks while drawing), so initialization
    happens here instead - once at register time, and again whenever a
    .blend file is opened."""
    try:
        for scene in bpy.data.scenes:
            operators.ensure_checks_initialized_for_scene(scene)
    except Exception as e:
        print(f"[Scene QC Validator] Deferred checklist init failed: {e}")


def _timer_init():
    _init_checks_for_open_scenes()
    return None  # don't repeat the timer


def _on_load_post(dummy):
    _init_checks_for_open_scenes()


def register():
    for m in _MODULES:
        m.register()
    bpy.app.timers.register(_timer_init, first_interval=0.1)
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)


def unregister():
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    for m in reversed(_MODULES):
        m.unregister()
