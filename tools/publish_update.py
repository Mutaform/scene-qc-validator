# -*- coding: utf-8 -*-
"""Выпуск канала обновлений Scene QC Validator: архив + манифест, одним скриптом.

Почему одним: манифест, разошедшийся с лежащим рядом архивом, рекламирует
обновление, которое не ставится, - и предлагает его вечно. Поэтому версия
читается ИЗ СОБРАННОГО АРХИВА, sha256 считается по готовому файлу, и в конце всё
сверяется заново.

Архив в канал уезжает тот же самый, что лежит в `Zip Addon/`, байт в байт:
отдельная сборка «для канала» однажды разойдётся с той, что отдали художнику.

Пишем прямо в синхронизируемую папку Диска - свои локальные правки уходят в
облако сразу, отдельного «залить» не нужно
(см. `_Studio memory/yandex-disk-360-sharing.md`).

Запуск (из корня репозитория):

    python tools/publish_update.py
    python tools/publish_update.py --notes "Что нового одной строкой"
    python tools/publish_update.py --out <папка>     положить куда-то ещё

ИМЕНА ФАЙЛОВ НЕ МЕНЯТЬ: путь к архиву записан в манифест, а путь к манифесту
зашит в аддон.

ПАПКУ НЕ РАСПУБЛИКОВЫВАТЬ. Повторная публикация даёт новый ключ, и все
установленные копии разом теряют канал - доставить им новый адрес будет нечем.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                        # <проект>/Git
PROJECT = os.path.dirname(ROOT)                     # <проект>
ZIP_DIR = os.path.join(PROJECT, "Zip Addon")
DIST_DIR = os.path.join(PROJECT, "Dev", "dist")
ADDON_ID = "scene_qc_validator"
FALLBACK_DIR = os.path.join(PROJECT, "Dev", "publish", ADDON_ID)

# Папка студии на Яндекс.Диске, синхронизируемая клиентом. Опубликована она
# сама, поэтому в манифесте пути считаются от её корня. Публикация привязана к
# папке, а не к пути: папку переносили внутри Auto_Update_Tools, и ссылка это
# пережила - менять надо только путь здесь.
YANDEX_DIR = os.path.join(
    "D:\\", "Yandex.Disk360",
    "Yandex.Disk-SharedResources-d.yurchenko@mutaform.com",
    "d_6gJuQcCF3P29fw", "Auto_Update_Tools", "blender", "qc_validator_blender")
PUBLIC_KEY = "https://disk.360.yandex.ru/d/xG-PvFCrx2HDsQ"

ARCHIVE_NAME = "%s_update.zip" % ADDON_ID           # постоянное имя: путь в манифесте не меняется
MANIFEST_NAME = "version.json"


def latest_build():
    """Последний собранный архив. Сначала Zip Addon - то, что реально отдали."""
    for folder in (ZIP_DIR, DIST_DIR):
        found = glob.glob(os.path.join(folder, "%s_by_mutaform_studio_v*.zip" % ADDON_ID))
        if found:
            return max(found, key=os.path.getmtime)
    sys.exit("Нет собранного архива. Сначала: powershell tools/build_release.ps1")


def version_in(archive):
    """Версия из манифеста внутри архива, без распаковки и без импорта."""
    with zipfile.ZipFile(archive) as zf:
        name = next((n for n in zf.namelist()
                     if n.endswith("blender_manifest.toml")), None)
        if not name:
            sys.exit("В архиве нет blender_manifest.toml - это не расширение Blender.")
        text = zf.read(name).decode("utf-8-sig", "replace")
    found = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not found:
        sys.exit("В манифесте архива нет строки version.")
    return found.group(1)


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--notes", default="", help="одна строка о том, что изменилось")
    parser.add_argument("--out", default="", help="куда класть; по умолчанию папка Диска")
    args = parser.parse_args()

    out_dir = args.out or (YANDEX_DIR if os.path.isdir(YANDEX_DIR) else FALLBACK_DIR)
    synced = os.path.normcase(out_dir) == os.path.normcase(YANDEX_DIR)
    if out_dir == FALLBACK_DIR:
        print("ПАПКИ ДИСКА НЕТ (%s)" % YANDEX_DIR)
        print("пишу в %s - залить руками\n" % FALLBACK_DIR)

    build = latest_build()
    version = version_in(build)
    print("архив:  %s" % os.path.basename(build))
    print("версия: %s" % version)

    os.makedirs(out_dir, exist_ok=True)
    archive = os.path.join(out_dir, ARCHIVE_NAME)
    shutil.copyfile(build, archive)

    manifest = {
        "id": ADDON_ID,
        "version": version,
        "download": "/%s" % ARCHIVE_NAME,
        "sha256": sha256_of(archive),
        "notes": args.notes.strip(),
    }
    manifest_path = os.path.join(out_dir, MANIFEST_NAME)
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=1)
        handle.write("\n")

    # сверка заново, по тому, что легло на диск: ради этого скрипт и один
    problems = []
    if version_in(archive) != manifest["version"]:
        problems.append("версия в манифесте разошлась с архивом")
    if sha256_of(archive) != manifest["sha256"]:
        problems.append("sha256 не сошёлся")
    with open(manifest_path, encoding="utf-8") as handle:
        if json.load(handle) != manifest:
            problems.append("манифест на диске не совпал с собранным")
    if problems:
        sys.exit("НЕ ПУБЛИКОВАТЬ: " + "; ".join(problems))

    print("\nготово, в %s:" % out_dir)
    print("  %s  (%.1f МБ)" % (ARCHIVE_NAME, os.path.getsize(archive) / (1 << 20)))
    print("  %s" % MANIFEST_NAME)
    if synced:
        print("\nЭто синхронизируемая папка: в облако уйдёт само, ждать не нужно.")
        print("Канал: %s" % PUBLIC_KEY)
    else:
        print("\nПоложить обе в опубликованную папку студии. Имена не менять.")


if __name__ == "__main__":
    main()
