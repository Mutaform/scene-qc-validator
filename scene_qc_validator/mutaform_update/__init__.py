# -*- coding: utf-8 -*-
"""Самообновление аддонов Mutaform с папки студии на Яндекс.Диске.

Модуль переносимый: папку `mutaform_update/` копируют в любой аддон студии как
есть. Внутри нет ни одного имени, завязанного на конкретный аддон - всё, что
отличается, приходит через `setup()`.

Встраивание в аддон:

```python
from . import mutaform_update

def register():
    mutaform_update.setup(
        addon_id="scene_qc_validator",     # id в version.json
        package=__package__,               # куда ставить: bl_ext.<репо>.<аддон>
        version=addon_version(),           # что стоит сейчас
        title="Scene QC Validator",        # как назвать в окне
        public_key=CHANNEL,                # публичная ссылка на папку с релизами
        manifest_path="/scene_qc_validator/version.json",
    )
    mutaform_update.register()

def unregister():
    mutaform_update.unregister()
```

И одна строка в панели аддона, чтобы обновление не потерялось, если окно закрыли:

```python
mutaform_update.draw_banner(layout)
```

Аддону, который ходит в сеть, положено объявить это в своём манифесте:

```toml
[permissions]
network = "Проверка обновлений на сервере студии"
```

Устройство канала и почему не встроенные репозитории Blender - в `core.py`
и в `_Studio memory/blender-extensions-without-github.md`.
"""

from . import core
from . import ui

__all__ = ["setup", "register", "unregister", "draw_banner", "has_pending", "check"]


def setup(addon_id, package, version, public_key,
          manifest_path=None, title=""):
    """Настроить канал. Зовётся до register(), из register() самого аддона."""
    ui.CONFIG.update({
        "addon_id": addon_id,
        "package": package,
        "version": str(version),
        "title": title or addon_id,
        "public_key": public_key,
        "manifest_path": manifest_path or ("/%s/%s" % (addon_id, core.MANIFEST_NAME)),
    })


def register():
    ui.register()


def unregister():
    ui.unregister()


def draw_banner(layout):
    return ui.draw_banner(layout)


def has_pending():
    return ui.has_pending()


def check(verbose=False):
    return ui.check(verbose=verbose)
