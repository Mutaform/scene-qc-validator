# -*- coding: utf-8 -*-
"""Самообновление аддонов Mutaform: решения и сеть. Без bpy.

Перенос рабочей схемы из ARDENA Tools (`ardena_updater.py`), которая, в свою
очередь, пришла из QC Bake for Maya. Описание канала и то, почему он устроен
именно так, - в `_Studio memory/maya-addon-updater.md` и
`_Studio memory/blender-extensions-without-github.md`.

Почему вообще свой апдейтер, когда у Blender есть встроенные репозитории.
Встроенный клиент ходит по адресу обычным GET. Публичная ссылка Яндекс.Диска на
такой запрос отвечает 302 на веб-интерфейс, а не файлом: чтобы получить архив,
нужен двухшаговый резолв через `cloud-api.yandex.net`. Встроенный клиент так не
умеет, и научить его нечем. Значит, сетевую половину пишем сами - а установку
по-прежнему делает сам Blender, оператором `extensions.package_install_files`.

Здесь нет ни одного импорта bpy намеренно: все решения - «новее ли версия»,
«можно ли доверять манифесту», «безопасен ли адрес» - проверяются обычным
Python, без запуска Blender.

Три правила, которые нарушать нельзя: этот код ставит то, что скачал.
  * Ничего не ставится само. Инструмент сообщает, ставит художник кнопкой.
  * Только https, и архив сверяется с sha256 из манифеста ДО установки.
  * Непонятное - это отказ, а не догадка: версия «latest» или манифест чужого
    аддона означают ошибку публикующей стороны, и действовать на них опаснее,
    чем промолчать.
"""

import hashlib
import json
import re

USER_AGENT = "MutaformUpdater"
MANIFEST_NAME = "version.json"
REQUIRED_KEYS = ("id", "version", "download")

# Хосты публичных ссылок Яндекса. Их несколько и они разные: обычный Диск отдаёт
# disk.yandex.ru, Яндекс 360 - disk.360.yandex.ru, короткие ссылки - yadi.sk.
# Проверять «disk.yandex.» было бы ошибкой: ссылку 360 такая проверка не узнаёт.
_YANDEX_HOSTS = ("yandex.ru/d/", "yandex.com/d/", "yadi.sk/d/",
                 "yandex.ru/i/", "yadi.sk/i/")

_VERSION_PART = re.compile(r"^\d+$")


# ---------------------------------------------------------------- решения


def parse_version(text):
    """Версия как кортеж чисел, или None.

    Намеренно строго: манифест со словом «latest» - ошибка публикующей стороны,
    а догадки о том, что имелось в виду, кончаются понижением версии.
    """
    if not isinstance(text, str):
        return None
    parts = text.strip().lstrip("vV").split(".")
    if not 1 <= len(parts) <= 4:
        return None
    if not all(_VERSION_PART.match(p) for p in parts):
        return None
    return tuple(int(p) for p in parts)


def is_newer(remote, local):
    """Строго новее. Короткие версии дополняются нулями: 1.5 новее 1.4.9 и равна
    1.5.0. Неразбираемое - False: отказ действовать на непонятной версии
    безопаснее, чем установка непонятно чего."""
    r, l = parse_version(remote), parse_version(local)
    if r is None or l is None:
        return False
    n = max(len(r), len(l))
    return r + (0,) * (n - len(r)) > l + (0,) * (n - len(l))


def is_safe_url(url):
    """https и только. Проверка не формальность: дальше скачанное ставится, а
    манифест по http кто угодно в сети может переписать."""
    return isinstance(url, str) and url.lower().startswith("https://")


def is_yandex_public(url):
    """Публичная ссылка на папку Яндекс.Диска, а не прямой адрес файла."""
    return (isinstance(url, str) and is_safe_url(url)
            and any(h in url.lower() for h in _YANDEX_HOSTS))


def validate_manifest(data, expect_id):
    """(manifest, None) или (None, причина).

    `download` - либо https-ссылка (обычный веб-сервер), либо путь внутри
    опубликованной папки (Яндекс.Диск: адрес там временный, клиент получает его
    сам). Требование «итоговый адрес обязан быть https» остаётся в любом случае,
    см. `resolve_download`.
    """
    if not isinstance(data, dict):
        return None, "Манифест не является объектом JSON."
    missing = [k for k in REQUIRED_KEYS if not data.get(k)]
    if missing:
        return None, "В манифесте нет полей: %s." % ", ".join(missing)
    if data["id"] != expect_id:
        return None, "Манифест для «%s», а не «%s»." % (data["id"], expect_id)
    if parse_version(data["version"]) is None:
        return None, "«%s» - не версия, которую апдейтер понимает." % data["version"]

    download_to = data["download"]
    if not isinstance(download_to, str) or not download_to.strip():
        return None, "Поле download пустое."
    low = download_to.lower()
    if low.startswith("http") and not is_safe_url(download_to):
        return None, "Ссылка на скачивание не https."
    if not low.startswith("https://") and not download_to.startswith("/"):
        return None, "download должен быть https-ссылкой или путём внутри папки (с «/»)."

    digest = data.get("sha256")
    if digest is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", str(digest)):
        return None, "sha256 в манифесте не похож на контрольную сумму."
    return data, None


# ---------------------------------------------------------------- сеть


def _open(url, timeout):
    import urllib.request
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout)


def yandex_href(public_key, path, timeout=15):
    """Прямой адрес файла в опубликованной папке. (url, None) или (None, причина).

    Адрес принадлежит Яндексу, живёт недолго и непрозрачен. Правило: всегда
    резолвить заново, никогда не хранить - ни в манифесте, ни в настройках.
    """
    import urllib.parse
    api = ("https://cloud-api.yandex.net/v1/disk/public/resources/download"
           "?public_key=%s&path=%s"
           % (urllib.parse.quote(public_key, safe=""), urllib.parse.quote(path)))
    try:
        with _open(api, timeout) as response:
            data = json.loads(response.read().decode("utf-8-sig", "replace"))
    except Exception as error:
        return None, "Не удалось получить ссылку на файл: %s" % error
    href = data.get("href")
    if not is_safe_url(href):
        return None, "Хранилище вернуло адрес, который не https."
    return href, None


def fetch_manifest(source, expect_id, path=None, timeout=15):
    """Манифест из канала. (manifest, None) или (None, причина).

    `source` - либо публичная ссылка на папку Яндекс.Диска, либо прямой
    https-адрес самого version.json. `path` - где манифест лежит внутри
    опубликованной папки: одна папка на все аддоны студии, по подпапке на аддон.

    Никогда не бросает: проверка идёт в фоне, и ноутбук без сети должен дать
    тихое сообщение в консоль, а не ошибку посреди работы.
    """
    import urllib.error

    if not source:
        return None, ("Канал обновлений не настроен: пустая ссылка на папку. "
                      "Впишите публичную ссылку в вызов setup().")
    url = source
    if is_yandex_public(source):
        url, error = yandex_href(source, path or ("/" + MANIFEST_NAME), timeout)
        if error:
            return None, error
    if not is_safe_url(url):
        return None, "Адрес обновлений должен быть https."

    try:
        with _open(url, timeout) as response:
            # utf-8-sig, не utf-8: почти любой windows-инструмент пишет BOM, а
            # json.loads его не переваривает - апдейтер отверг бы собственный манифест
            raw = response.read().decode("utf-8-sig", "replace")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None, "По этому адресу манифест ещё не опубликован (404)."
        return None, "Сервер обновлений ответил HTTP %s." % error.code
    except Exception as error:
        return None, "Не удалось связаться с сервером обновлений: %s" % error

    try:
        data = json.loads(raw)
    except ValueError as error:
        return None, "Манифест - не валидный JSON: %s" % error
    return validate_manifest(data, expect_id)


def resolve_download(manifest, source, timeout=15):
    """Итоговый https-адрес архива. (url, None) или (None, причина)."""
    download_to = manifest["download"]
    if is_safe_url(download_to):
        return download_to, None
    public_key = manifest.get("public_key") or (source if is_yandex_public(source) else None)
    if not public_key:
        return None, "В манифесте путь вместо ссылки, но неизвестна опубликованная папка."
    return yandex_href(public_key, download_to, timeout)


def download(url, destination, expected_sha=None, timeout=300):
    """Скачать архив и сверить сумму. (path, None) или (None, причина).

    Сумма сверяется ДО записи на диск: файл, не совпавший с манифестом, не должен
    даже лежать рядом с установкой.
    """
    if not is_safe_url(url):
        return None, "Ссылка на скачивание должна быть https."
    try:
        with _open(url, timeout) as response:
            payload = response.read()
    except Exception as error:
        return None, "Скачивание не удалось: %s" % error

    if expected_sha:
        actual = hashlib.sha256(payload).hexdigest()
        if actual.lower() != str(expected_sha).lower():
            return None, ("Скачанное не совпадает с контрольной суммой из манифеста - "
                          "это не тот файл, который публиковали. Ничего не установлено.")
    try:
        with open(destination, "wb") as handle:
            handle.write(payload)
    except OSError as error:
        return None, "Не удалось записать скачанное: %s" % error
    return destination, None
