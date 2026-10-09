# -*- coding: utf-8 -*-
"""Связь страницы отчёта с Blender: кнопки «Исправить» в браузере.

Отчёт - обычная HTML-страница, сама она до Blender не дотянется. Поэтому Blender
держит маленький приёмник на 127.0.0.1, а страница ходит к нему: спрашивает, не
изменился ли отчёт, и передаёт нажатие кнопки. Blender чинит, заново прогоняет
проверку и переписывает страницу - открытая вкладка подхватывает новую версию сама.

Что сделано ради чужих машин:
  - порт не зашит: его выдаёт система, и он вписывается в страницу при каждой
    записи, так что два Blender рядом не мешают друг другу;
  - слушается только 127.0.0.1: снаружи приёмник не виден, брандмауэр не
    спрашивает, прав администратора не нужно;
  - страница открывается как файл и остаётся читаемой, если связи нет (Blender
    закрыт, отчёт переслали художнику) - кнопки тогда просто выключены;
  - приёмник не поднялся - это не ошибка проверки: страница пишется как раньше.

Что сделано ради безопасности:
  - в страницу вписан одноразовый ключ этого запуска; без него приёмник не
    отвечает, и посторонняя вкладка ничего не запустит;
  - действия только из списка ACTIONS, произвольный код передать нельзя;
  - заголовок Host сверяется: прийти под чужим именем нельзя.

Потоки. Запросы принимает фоновый поток, а трогать данные Blender можно только из
главного: обработчик запроса НЕ зовёт bpy, он кладёт задание в очередь, которую
разбирает таймер в главном потоке.

Состояние лежит в builtins, а не в модуле: аддон перезагружается (разработка,
переустановка расширения), и приёмник должен это переживать, а не подниматься
заново на другом порту. Обработчик и таймер ходят за кодом через sys.modules,
поэтому после перезагрузки работает уже новый код.
"""

import builtins
import hmac
import http.server
import json
import secrets
import socket
import sys
import threading
import time
import traceback
import urllib.parse

import bpy

TAG = "[Scene QC Validator live]"
ACTIONS = ("fix_all", "fix_code", "select", "show_vc")
STATE_KEY = "_SQC_VALIDATOR_LIVE"
TICK = 0.25          # с: как часто главный поток заглядывает в очередь
START_DELAY = 0.25   # с: дать ответу «принято» уйти в браузер до начала работы


def _defaults():
    return {
        "server": None, "thread": None, "port": None, "token": None,
        "lock": threading.Lock(), "jobs": [], "running": False,
        "rev": 0, "page": None, "last": None, "context": None,
        "tick": None, "failed": False, "seen": 0.0,
    }


def _state():
    """Состояние приёмника. Живёт в builtins и переживает перезагрузку аддона.

    Недостающие ключи достраиваются: после обновления в памяти остаётся словарь,
    собранный прошлой версией, и новое поле там просто отсутствует. Без этого
    приёмник, поднятый до обновления, роняет первую же проверку.
    """
    state = getattr(builtins, STATE_KEY, None)
    if state is None:
        state = _defaults()
        setattr(builtins, STATE_KEY, state)
    else:
        for key, value in _defaults().items():
            state.setdefault(key, value)
    return state


def is_running():
    state = _state()
    return bool(state["server"] and state["port"])


def live_info():
    """Что вписывается в страницу, или None - тогда страница без кнопок."""
    state = _state()
    if not is_running():
        return None
    return {"port": state["port"], "token": state["token"], "rev": state["rev"]}


def begin_revision():
    """Номер следующей версии страницы - до того, как её отрисуют.

    Страница должна уехать с тем же номером, который потом отдаст /state: иначе
    открытая вкладка будет видеть расхождение и перекачивать её по кругу.
    """
    state = _state()
    if not is_running():
        return None
    state["rev"] += 1
    return live_info()


def set_page(path):
    _state()["page"] = path


def page_watched(within=6.0):
    """Открыта ли страница отчёта прямо сейчас, на видимой вкладке.

    Открытая вкладка сама подхватывает новую версию, и открывать ей вторую -
    значит за пять проверок завалить художника вкладками. Страница сообщает о
    себе в /state, поэтому «видно» здесь - это «спрашивала недавно».
    """
    state = _state()
    return is_running() and (time.time() - state["seen"]) < within


# ---------------------------------------------------------------- приёмник


class _Handler(http.server.BaseHTTPRequestHandler):
    """Вся логика - в _handle текущей копии модуля: после перезагрузки аддона
    работающий приёмник подхватывает новый код без перезапуска."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _go(self, method):
        try:
            sys.modules[__name__]._handle(self, method)
        except Exception:
            try:
                _send(self, 500, b"{}")
            except Exception:
                pass

    def do_GET(self):
        self._go("GET")

    def do_POST(self):
        self._go("POST")

    def do_OPTIONS(self):
        self._go("OPTIONS")


def _send(handler, status, body, content_type="application/json; charset=utf-8"):
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    # страница открыта как файл, для браузера это «чужой источник»
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "*")
    handler.send_header("Access-Control-Allow-Private-Network", "true")
    handler.end_headers()
    if body:
        handler.wfile.write(body)


def _json(handler, status, data):
    _send(handler, status, json.dumps(data, ensure_ascii=False).encode("utf-8"))


def _handle(handler, method):
    state = _state()
    if method == "OPTIONS":
        return _send(handler, 204, b"")

    url = urllib.parse.urlsplit(handler.path)
    query = urllib.parse.parse_qs(url.query)

    def arg(key):
        return (query.get(key) or [""])[0]

    if method == "POST":
        try:
            handler.rfile.read(int(handler.headers.get("Content-Length") or 0))
        except Exception:
            pass

    host = (handler.headers.get("Host") or "").rsplit(":", 1)[0]
    if host not in ("127.0.0.1", "localhost"):
        return _json(handler, 403, {"error": "host"})
    token = state["token"] or ""
    if not token or not hmac.compare_digest(arg("t"), token):
        return _json(handler, 403, {"error": "token"})

    if url.path == "/state" and method == "GET":
        if arg("v") == "1":
            state["seen"] = time.time()
        return _json(handler, 200, {
            "rev": state["rev"],
            "busy": bool(state["running"] or state["jobs"]),
            "last": state["last"],
        })

    if url.path == "/report" and method == "GET":
        try:
            with open(state["page"], "rb") as page:
                return _send(handler, 200, page.read(), "text/html; charset=utf-8")
        except Exception:
            return _json(handler, 404, {"error": "report"})

    if url.path == "/run" and method == "POST":
        action = arg("a")
        if action not in ACTIONS:
            return _json(handler, 400, {"error": "action"})
        with state["lock"]:
            if state["running"] or state["jobs"]:
                return _json(handler, 409, {"error": "busy"})
            state["jobs"].append({
                "id": arg("id")[:40], "action": action,
                # obj - либо одно имя (показать в Blender), либо объекты строки
                # отчёта через запятую, поэтому запас большой
                "code": arg("code")[:64], "obj": arg("obj")[:4000],
                "queued": time.time(),
            })
        return _json(handler, 200, {"queued": True})

    return _json(handler, 404, {"error": "path"})


# ---------------------------------------------------------------- очередь


def _tick_entry():
    """Зарегистрирован в таймерах Blender. Код берётся из текущего модуля, чтобы
    перезагрузка аддона не оставила в таймере старую копию."""
    module = sys.modules.get(__name__)
    if module is None:
        return None
    try:
        module._tick()
    except Exception:
        print("%s tick: %s" % (TAG, traceback.format_exc()))
    return TICK


def _tick():
    state = _state()
    if state["running"] or not state["jobs"]:
        return
    if time.time() - state["jobs"][0]["queued"] < START_DELAY:
        return
    state["running"] = True
    try:
        with state["lock"]:
            job = state["jobs"].pop(0)
        _execute(job)
    finally:
        state["running"] = False


def _execute(job):
    """Выполняется в главном потоке: чиним, перепроверяем, переписываем страницу."""
    state = _state()
    from .operators import stage_check
    try:
        result = stage_check.run_action(
            bpy.context, job["action"], job.get("code") or "", job.get("obj") or ""
        )
    except Exception as error:
        print("%s %s: %s" % (TAG, job["action"], traceback.format_exc()))
        result = {"ok": False, "text": "Действие остановилось с ошибкой: %s" % error}
    state["last"] = {
        "id": job.get("id", ""),
        "action": job["action"],
        "ok": bool(result.get("ok")),
        "text": result.get("text") or "",
    }





# ---------------------------------------------------------------- запуск


def start():
    """Поднять приёмник, если он ещё не поднят. Молча отступает при неудаче."""
    state = _state()
    if is_running():
        return True
    if state["failed"]:
        return False
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        server.daemon_threads = True
        server.timeout = 1
    except OSError as error:
        state["failed"] = True
        print("%s приёмник не поднялся: %s" % (TAG, error))
        return False
    state["server"] = server
    state["port"] = server.server_address[1]
    state["token"] = secrets.token_urlsafe(24)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.3},
                              name="sqc-live", daemon=True)
    thread.start()
    state["thread"] = thread
    if not bpy.app.timers.is_registered(_tick_entry):
        bpy.app.timers.register(_tick_entry, first_interval=TICK, persistent=True)
    state["tick"] = _tick_entry
    print("%s слушает 127.0.0.1:%d" % (TAG, state["port"]))
    return True


def stop():
    state = _state()
    server = state["server"]
    if server is not None:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
    tick = state["tick"]
    for candidate in (tick, _tick_entry):
        if candidate is not None and bpy.app.timers.is_registered(candidate):
            try:
                bpy.app.timers.unregister(candidate)
            except Exception:
                pass
    state.update({"server": None, "thread": None, "port": None, "token": None,
                  "tick": None, "jobs": [], "running": False, "seen": 0.0})


def unregister():
    stop()
