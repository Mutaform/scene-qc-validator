"""
Scene QC Validator by Mutaform LLC
Mesh/scene validation checklist with presets.
Developed by Mutaform Studio.

Packaged as a Blender Extension (blender_manifest.toml) for Blender 4.2+ / 5.1.
"""

import bpy

from . import checks
from . import live
from . import mutaform_update
from . import properties
from . import operators
from . import ui

_MODULES = (properties, operators, ui)

# Канал обновлений: опубликованная папка студии на Яндекс.Диске, по подпапке на
# аддон. Ссылка зашита намеренно - встроенные репозитории Blender публичную
# ссылку Яндекса читать не умеют (отвечает 302 на веб-интерфейс), а просить
# художника настраивать путь у себя значит получить десять разных настроек.
#
# ПАПКУ НЕ РАСПУБЛИКОВЫВАТЬ. Повторная публикация даёт новый ключ, и все
# установленные копии разом теряют канал - доставить им новый адрес будет нечем.
# Папка студии: Auto_Update_Tools/qc_validator_blender. Опубликована она сама,
# поэтому манифест лежит в её корне.
UPDATE_CHANNEL = "https://disk.360.yandex.ru/d/xG-PvFCrx2HDsQ"
UPDATE_MANIFEST = "/version.json"


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
    mutaform_update.setup(
        addon_id="scene_qc_validator",
        package=__package__,
        version=ui.helpers.addon_version(),
        title="Scene QC Validator",
        public_key=UPDATE_CHANNEL,
        manifest_path=UPDATE_MANIFEST,
    )
    mutaform_update.register()
    # таблицы описаний сведены руками: расхождение с определениями проверок
    # проявилось бы в отчёте у художника, поэтому сверяем на старте
    checks.warn_registry_mismatch()
    bpy.app.timers.register(_timer_init, first_interval=0.1)
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)


def unregister():
    # приёмник держит порт и фоновый поток - гасим раньше всего остального
    live.unregister()
    mutaform_update.unregister()
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    for m in reversed(_MODULES):
        m.unregister()
