# -*- coding: utf-8 -*-
"""Пробелы и кириллица в именах: глазами не видно, а в движке ломается.

Два случая, и оба коварны тем, что имя ВЫГЛЯДИТ правильным:

    S_TAR_DK_Estate_GuestRoom_ Bed_01     лишний пробел после подчёркивания
    S_TAR_DK_Estаte_GuestRoom_Bеd_01      «а» и «е» здесь кириллические

Кириллическая «а» (U+0430) и латинская «a» (U+0061) рисуются одинаково, но
это разные символы. Поиск по имени в движке такой ассет не находит, материал
не привязывается к своему мешу, а художник смотрит на имя и не понимает, в чём
претензия. Шаблон имени (`nm_object_pattern`) такое, конечно, отвергает - но
говорит «не подходит под шаблон», и дальше начинается гадание.

Поэтому отдельная проверка: она показывает НОМЕР символа, сам символ и его
латинского двойника, а кнопка «Исправить» переписывает имя. Пробелы убираются
по-разному: рядом с подчёркиванием они лишние, а одиночный пробел между
словами становится подчёркиванием - иначе слова склеятся.

Чиним только то, у чего есть однозначный двойник. Буква без пары (ж, ы, ё)
остаётся в находке: заменить её нечем, и придумывать за художника нельзя.
"""

import re

from ..common import *

# Кириллица и греческие буквы, которые рисуются как латинские.
HOMOGLYPHS = {
    "а": "a", "А": "A", "в": "b", "В": "B", "е": "e", "Е": "E", "ё": "e",
    "Ё": "E", "к": "k", "К": "K", "М": "M", "Н": "H", "о": "o", "О": "O",
    "р": "p", "Р": "P", "с": "c", "С": "C", "Т": "T", "у": "y", "У": "Y",
    "х": "x", "Х": "X", "і": "i", "І": "I", "ј": "j", "Ј": "J", "ѕ": "s",
    "Ѕ": "S", "һ": "h", "Ү": "Y", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z",
    "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P",
    "Τ": "T", "Υ": "Y", "Χ": "X", "α": "a", "ε": "e", "ι": "i", "κ": "k",
    "ο": "o", "ρ": "p", "τ": "t", "χ": "x", "ν": "v", "γ": "y",
}
SPACES = (" ", " ", " ", " ", "\t")


def _kind(char):
    if char in SPACES:
        return "space"
    if char in HOMOGLYPHS:
        return "twin"
    if ord(char) > 127:
        return "other"
    return ""


def problems(name):
    """[(позиция с единицы, символ, вид, латинский двойник)] по имени."""
    found = []
    for index, char in enumerate(name):
        kind = _kind(char)
        if kind:
            found.append((index + 1, char, kind, HOMOGLYPHS.get(char, "")))
    return found


def repaired(name):
    """Имя, как оно должно выглядеть. None - чинить нечем.

    Пробелы рядом с подчёркиванием лишние, одиночный становится
    подчёркиванием: «Guest Room» это «Guest_Room», а «_ Bed» это «_Bed».
    """
    text = name.strip()
    for space in SPACES:
        text = text.replace(space, " ")
    text = re.sub(r"\s*_\s*", "_", text)
    text = re.sub(r"\s+", "_", text)
    text = "".join(HOMOGLYPHS.get(char, char) for char in text)
    if any(ord(char) > 127 for char in text) or not text:
        return None                 # остались символы без двойника
    return text if text != name else None


def _targets(obj, item):
    """[(что это, имя, объект-владелец)] - объект и его материалы."""
    out = [("объекта", obj.name, obj)]
    if getattr(item, "bool_param_1", True):
        seen = set()
        for slot in obj.material_slots:
            material = slot.material
            if material is None or material.name in seen:
                continue
            seen.add(material.name)
            out.append(("материала", material.name, material))
    return out


def check_name_characters(obj, item):
    issues = []
    for what, name, _owner in _targets(obj, item):
        found = problems(name)
        if not found:
            continue
        spaces = [p for p in found if p[2] == "space"]
        twins = [p for p in found if p[2] == "twin"]
        other = [p for p in found if p[2] == "other"]
        want = repaired(name)
        issues.append({
            "message": ("%s name %r has %d space(s) and %d non-ASCII character(s)"
                        % (what, name, len(spaces), len(twins) + len(other))),
            "element_ref": "",
            "values": {"what": what, "name": name, "want": want or "",
                       "spaces": [p[0] for p in spaces],
                       "twins": [[p[0], p[1], p[3]] for p in twins],
                       "other": [[p[0], p[1]] for p in other]},
        })
    return issues


def fix_name_characters(obj, item, result):
    """Переписать имена: убрать пробелы, заменить двойников на латиницу.

    Занятое имя не переписываем: Blender дописал бы «.001» и поменял одну беду
    на другую. Но и молчать нельзя - если не вышло вообще ничего, поднимаем
    ошибку, и страница отчёта скажет «не получилось: имя занято» вместо
    «чинить нечего».
    """
    changed, blocked = False, []
    for _what, name, owner in _targets(obj, item):
        want = repaired(name)
        if not want:
            continue
        collection = bpy.data.materials if isinstance(owner, bpy.types.Material) \
            else bpy.data.objects
        taken = collection.get(want)
        if taken is not None and taken is not owner:
            blocked.append(want)
            continue
        owner.name = want
        changed = True
    if blocked and not changed:
        raise RuntimeError("имя «%s» уже занято" % blocked[0])
    return changed
