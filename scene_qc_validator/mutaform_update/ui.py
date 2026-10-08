# -*- coding: utf-8 -*-
"""Сторона Blender: тихая проверка на запуске, окно посреди экрана, установка.

Правила поведения перенесены из ARDENA Tools и QC Bake for Maya, каждое оплачено
поломкой (`_Studio memory/maya-addon-updater.md`):

  * Аддон НИКОГДА не ставит обновление сам. Сообщает; ставит художник кнопкой.
  * Проверять при каждом запуске Blender, без «умной» экономии запросов. Любая
    экономия рано или поздно даёт единственный исход, который важен: инструмент
    знает, что устарел, и молчит. Один маленький GET на запуск - не та цена.
  * Молчать, когда автопроверка прошла и всё в порядке. Проверка по кнопке
    отвечает всегда: кнопка без видимого отклика читается как сломанная.
  * `bpy.app.online_access` выключен - молчать совсем. Это не техническое
    препятствие, а прямо выраженная воля художника; так же поступает сам Blender
    (`bl_extension_notify.py`).

Потоки. Сеть - в фоновом потоке, иначе Blender замирает на старте у каждого, у
кого Диск отвечает медленно. Трогать данные Blender из фонового потока нельзя,
поэтому поток только складывает результат, а разбирает его таймер в главном.

Установка идёт из таймера, а не из `execute` оператора. `package_install_files`
снимает регистрацию аддона, подменяет файлы и регистрирует заново - то есть
сносит и тот модуль, в котором выполняется вызов. Из таймера это переживается:
кадр уже запущенной функции живёт до конца сам по себе, а живого оператора в
этот момент нет.

Имена операторов собираются с id аддона внутри: модуль встраивается в несколько
аддонов студии, и два одинаковых `mutaform.update_check` в одном Blender -
конфликт регистрации.
"""

import os
import tempfile
import threading
import time

import bpy

from . import core

TAG = "[Mutaform update]"

# Через сколько секунд после запуска спрашивать хранилище. Blender в первые
# секунды грузит сцену и остальные аддоны - лезть в сеть в этот момент значит
# соревноваться с ними за внимание пользователя.
START_DELAY = 6.0
TICK = 0.4

CONFIG = {
    "addon_id": "",        # id в манифесте version.json
    "package": "",         # bl_ext.<репозиторий>.<аддон> - куда ставить
    "version": "0",        # установленная версия
    "title": "",           # как называть аддон в окне
    "public_key": "",      # публичная ссылка на папку с релизами
    "manifest_path": "",   # путь к version.json внутри этой папки
}

_state = {
    "manifest": None,      # найденное обновление, новее установленного
    "error": None,
    "busy": False,
    "stage": "",           # "", "check", "download", "install", "done", "failed"
    "message": "",
    "archive": None,
    "offered": False,      # окно в этой сессии уже показывали
    "verbose": False,      # проверка запущена кнопкой: отвечать и когда всё в порядке
    "asked": False,        # окно показано и ждёт ответа - см. Offer.execute
}
_classes = []
_timers = set()


def _log(message):
    print("%s %s" % (TAG, message))


def state():
    return _state


def pending():
    """Манифест обновления, если оно есть и новее установленного. Иначе None."""
    manifest = _state["manifest"]
    if not manifest:
        return None
    if not core.is_newer(manifest["version"], CONFIG["version"]):
        return None
    return manifest


# ---------------------------------------------------------------- таймеры


def _add_timer(function, first_interval):
    _timers.add(function)
    if not bpy.app.timers.is_registered(function):
        bpy.app.timers.register(function, first_interval=first_interval)


def _drop_timers():
    for function in list(_timers):
        try:
            if bpy.app.timers.is_registered(function):
                bpy.app.timers.unregister(function)
        except (ValueError, RuntimeError):
            # свой же таймер, выполняющийся прямо сейчас: он снимется сам,
            # вернув None - это нормальный путь при установке обновления
            pass
    _timers.clear()


# ---------------------------------------------------------------- проверка


def _can_reach_network():
    """Blender 4.2+ держит сетевой доступ аддонов за настройкой пользователя."""
    if not getattr(bpy.app, "online_access", True):
        return False, "Доступ в сеть выключен в настройках Blender - проверка пропущена."
    if not CONFIG["public_key"]:
        return False, "Канал обновлений не настроен."
    return True, ""


def _check_thread():
    manifest, error = core.fetch_manifest(
        CONFIG["public_key"], CONFIG["addon_id"], CONFIG["manifest_path"])
    _state["manifest"] = manifest
    _state["error"] = error
    _state["busy"] = False


def check(verbose=False):
    """Спросить хранилище в фоне. Возвращает False, если спрашивать нельзя."""
    if _state["busy"]:
        return True
    allowed, why = _can_reach_network()
    if not allowed:
        _state["error"] = why
        if verbose:
            _state["stage"], _state["message"] = "failed", why
        else:
            _log(why)
        return False
    _state["busy"] = True
    _state["verbose"] = verbose
    _state["stage"] = "check"
    _state["error"] = None
    threading.Thread(target=_check_thread, name="mutaform-update-check",
                     daemon=True).start()
    _add_timer(_after_check, TICK)
    return True


def _after_check():
    if _state["busy"]:
        return TICK
    _timers.discard(_after_check)
    update = pending()
    if _state["error"]:
        _state["stage"] = "failed" if _state["verbose"] else ""
        _state["message"] = _state["error"]
        _log(_state["error"])
    elif update:
        _state["stage"] = ""
        _offer(update)
    else:
        # тишина, когда всё в порядке: окно «обновлений нет» на каждом запуске
        # Blender - это шум, который учатся закрывать не читая
        _state["stage"] = "done" if _state["verbose"] else ""
        _state["message"] = "Установлена последняя версия (%s)." % CONFIG["version"]
        if _state["verbose"]:
            _report(_state["message"], 'INFO')
    return None


def _startup_check():
    check(verbose=False)
    return None


# ---------------------------------------------------------------- окно


def _offer(manifest):
    """Показать окно посреди экрана. Один раз за сессию - дальше напоминает панель."""
    if _state["offered"]:
        return
    _state["offered"] = True
    if getattr(bpy.context, "window", None) is None:
        # окна нет (Blender в фоне, рендер-ферма): показывать нечего, и звать
        # оператор нельзя - без окна Blender выполнит его сразу, минуя диалог
        _log("окна нет, обновление %s не предлагается" % manifest.get("version"))
        return
    try:
        getattr(bpy.ops.mutaform, _opname("offer"))('INVOKE_DEFAULT')
    except Exception as error:
        # окно не открылось - это не повод терять сам факт обновления:
        # его покажет панель
        _log("окно обновления не открылось: %s" % error)


def _report(message, kind='INFO'):
    """Строка в статус-баре. Окно поверх окна не ставим."""
    _log(message)
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
    except AttributeError:
        pass


# ---------------------------------------------------------------- установка


def _download_thread():
    manifest = _state["manifest"]
    url, error = core.resolve_download(manifest, CONFIG["public_key"])
    if error:
        _state["error"] = error
        _state["busy"] = False
        return
    target = os.path.join(tempfile.gettempdir(),
                          "%s_update_%d.zip" % (CONFIG["addon_id"], int(time.time())))
    path, error = core.download(url, target, manifest.get("sha256"))
    _state["archive"] = path
    _state["error"] = error
    _state["busy"] = False


def start_install():
    """Скачать и поставить. Вызывается кнопкой из окна или из панели."""
    if _state["busy"] or not pending():
        return
    allowed, why = _can_reach_network()
    if not allowed:
        _state["stage"], _state["message"] = "failed", why
        return
    _state["busy"] = True
    _state["stage"] = "download"
    _state["message"] = "Скачивание…"
    _state["error"] = None
    threading.Thread(target=_download_thread, name="mutaform-update-download",
                     daemon=True).start()
    _add_timer(_after_download, TICK)


def _after_download():
    if _state["busy"]:
        return TICK
    _timers.discard(_after_download)
    if _state["error"] or not _state["archive"]:
        _state["stage"] = "failed"
        _state["message"] = _state["error"] or "Архив не скачался."
        _report(_state["message"], 'ERROR')
        return None
    _state["stage"] = "install"
    _state["message"] = "Установка…"
    # установка - отдельным таймером: package_install_files сносит и этот модуль,
    # и делать это посреди уже запущенного вызова не стоит
    _add_timer(_install_now, 0.1)
    return None


def _repo_module():
    """Репозиторий расширений, в котором аддон стоит сейчас.

    `__package__` у расширения выглядит как `bl_ext.<репозиторий>.<аддон>`.
    Ставим туда же, где аддон уже лежит: иначе в Blender окажутся две копии, и
    включённой будет не та, которую обновили.
    """
    parts = (CONFIG["package"] or "").split(".")
    if len(parts) >= 3 and parts[0] == "bl_ext":
        return parts[1]
    return "user_default"


def _install_now():
    _timers.discard(_install_now)
    archive = _state["archive"]
    version = (_state["manifest"] or {}).get("version", "?")
    try:
        bpy.ops.extensions.package_install_files(
            filepath=archive,
            repo=_repo_module(),
            enable_on_install=True,
            overwrite=True,
        )
    except Exception as error:
        _state["stage"] = "failed"
        _state["message"] = "Установка не удалась: %s" % error
        _report(_state["message"], 'ERROR')
        return None
    finally:
        try:
            os.remove(archive)
        except OSError:
            pass
    _state["stage"] = "done"
    _state["message"] = "Версия %s установлена." % version
    _state["manifest"] = None
    _report(_state["message"], 'INFO')
    return None


# ---------------------------------------------------------------- операторы


def _opname(suffix):
    """Имя оператора с id аддона внутри: модуль живёт в нескольких аддонах."""
    return "update_%s_%s" % (CONFIG["addon_id"], suffix)


def _make_classes():
    addon_id = CONFIG["addon_id"]
    title = CONFIG["title"] or addon_id

    class Offer(bpy.types.Operator):
        bl_idname = "mutaform.%s" % _opname("offer")
        bl_label = "Доступно обновление"
        bl_options = {'REGISTER', 'INTERNAL'}

        def invoke(self, context, event):
            window = context.window
            if window is None:
                return {'CANCELLED'}
            # окно Blender открывает у курсора, экранного центра для него нет.
            # Переставляем курсор в середину окна - тогда и окно встанет там же,
            # а не в углу, куда художник не смотрит
            window.cursor_warp(window.x + window.width // 2,
                               window.y + window.height // 2)
            _state["asked"] = True
            # заголовок и подпись кнопки задаются здесь: иначе Blender берёт
            # bl_label в шапку и «OK» на кнопку - из «OK» не видно, что он сделает
            return context.window_manager.invoke_props_dialog(
                self, width=460, title="Mutaform · обновление",
                confirm_text="Обновить")

        def draw(self, context):
            manifest = pending() or {}
            layout = self.layout
            layout.scale_y = 1.1

            head = layout.row()
            head.alert = True
            head.label(text="%s устарел" % title, icon='ERROR')

            box = layout.box()
            row = box.row()
            row.label(text="Установлена:")
            row.label(text=CONFIG["version"])
            row = box.row()
            row.label(text="Доступна:")
            sub = row.row()
            sub.alert = True
            sub.label(text=str(manifest.get("version", "?")))

            notes = (manifest.get("notes") or "").strip()
            if notes:
                column = layout.column(align=True)
                column.scale_y = 0.85
                for line in _wrap(notes, 72):
                    column.label(text=line)

            layout.separator()
            layout.label(text="Blender поставит обновление сам, перезапуск не нужен.",
                         icon='INFO')

        def execute(self, context):
            # сюда попадают двумя путями: художник нажал «Обновить» в окне -
            # и тогда invoke уже отработал; либо Blender выполнил оператор
            # напрямую, не сумев показать окно (вызов из таймера без окна,
            # фоновый режим). Второй путь поставил бы обновление сам, никого не
            # спросив, - а это первое правило схемы, которое нарушать нельзя
            if not _state["asked"]:
                _log("окно не показывалось - установка не запускается")
                return {'CANCELLED'}
            _state["asked"] = False
            start_install()
            return {'FINISHED'}

    class Install(bpy.types.Operator):
        bl_idname = "mutaform.%s" % _opname("install")
        bl_label = "Обновить аддон"
        bl_description = "Скачать и установить новую версию"

        @classmethod
        def poll(cls, context):
            return pending() is not None and not _state["busy"]

        def execute(self, context):
            start_install()
            return {'FINISHED'}

    class Check(bpy.types.Operator):
        bl_idname = "mutaform.%s" % _opname("check")
        bl_label = "Проверить обновления"
        bl_description = "Спросить у сервера студии, есть ли новая версия"

        def execute(self, context):
            _state["offered"] = False
            if not check(verbose=True):
                self.report({'WARNING'}, _state["message"] or "Проверка недоступна")
                return {'CANCELLED'}
            self.report({'INFO'}, "Проверяю обновления…")
            return {'FINISHED'}

    return [Offer, Install, Check]


def _wrap(text, width):
    """Перенос по словам: у строк в окне Blender нет переноса."""
    lines, current = [], ""
    for word in text.split():
        candidate = (current + " " + word).strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:6]


# ---------------------------------------------------------------- панель


def draw_banner(layout):
    """Строка в панели аддона. True - что-то нарисовано.

    Окно показывается один раз за сессию, а закрыть его можно не читая. Поэтому
    пока обновление не поставлено, о нём напоминает панель - постоянно и на виду.
    """
    stage = _state["stage"]
    if stage in ("download", "install"):
        row = layout.row()
        row.enabled = False
        row.label(text=_state["message"], icon='SORTTIME')
        return True
    if stage == "failed":
        box = layout.box()
        box.alert = True
        box.label(text=_state["message"], icon='ERROR')
        box.operator("mutaform.%s" % _opname("check"), text="Повторить", icon='FILE_REFRESH')
        return True

    update = pending()
    if not update:
        if stage == "done" and _state["message"]:
            row = layout.row()
            row.enabled = False
            row.label(text=_state["message"], icon='CHECKMARK')
            return True
        return False

    box = layout.box()
    box.alert = True
    box.label(text="Доступно обновление: %s → %s" % (CONFIG["version"], update["version"]),
              icon='ERROR')
    row = box.row()
    row.scale_y = 1.3
    row.operator("mutaform.%s" % _opname("install"),
                 text="Обновить аддон", icon='IMPORT')
    return True


def has_pending():
    return pending() is not None


# ---------------------------------------------------------------- регистрация


def register():
    global _classes
    _classes = _make_classes()
    for cls in _classes:
        bpy.utils.register_class(cls)
    if CONFIG["public_key"]:
        _add_timer(_startup_check, START_DELAY)
    else:
        # канал не настроен - молчим совсем. Строка в консоли на каждом запуске
        # Blender у аддона, который ещё не подключили, это шум; кнопка
        # «Проверить обновления» скажет причину тому, кто спросит
        _log("канал обновлений не настроен, автопроверка выключена")


def unregister():
    _drop_timers()
    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    _classes.clear()
