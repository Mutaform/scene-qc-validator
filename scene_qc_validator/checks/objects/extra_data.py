# -*- coding: utf-8 -*-
"""Лишние данные на статик-меше: модификаторы, шейп-кейсы, вертекс-группы.

В движок едет то, что лежит в FBX, а не то, что видно в вьюпорте. Поэтому:

  * **модификатор** - это обещание геометрии, которого в файле нет. Экспорт
    может применить его, а может и нет, и тогда ассет приедет непохожим на
    то, что художник согласовывал. Отдельно и важное: ВСЕ замеры валидатора
    идут по базовому мешу, а не по результату модификаторов, - значит с
    неприменённым Mirror или Subdivision число треугольников, плотность
    текселя и паддинг показывают не то, что уедет;
  * **шейп-кейсы** статик-мешу не нужны: анимации у него нет, а в FBX они
    уедут лишними морф-таргетами;
  * **вертекс-группы** нужны скину, а не статике: это следы риггинга или
    временных выделений, в движке их никто не прочитает.

Что именно спрашивать, задаётся списком в настройке - как у «трансформация не
применена»: проект может решить, что на блокауте модификаторы ещё можно.

Автофикса нет намеренно. Применить модификатор - изменить геометрию, удалить -
потерять работу; шейп-кейс удаляется без возврата. Такое решение принимает
художник, а не кнопка.
"""

from ..common import *

KINDS = ("modifiers", "shape_keys", "vertex_groups")
DEFAULT_KINDS = "modifiers,shape_keys,vertex_groups"


def _wanted(item):
    text = (getattr(item, "string_param_1", "") or "").strip() or DEFAULT_KINDS
    asked = {part.strip().lower() for part in text.split(",") if part.strip()}
    return [kind for kind in KINDS if kind in asked]


def found_extra(obj, kinds=KINDS):
    """{вид: [имена]} - что лежит на объекте из перечисленного."""
    out = {}
    if "modifiers" in kinds and obj.modifiers:
        out["modifiers"] = [m.name for m in obj.modifiers]
    if "shape_keys" in kinds:
        keys = getattr(obj.data, "shape_keys", None)
        blocks = list(keys.key_blocks) if keys is not None else []
        if blocks:
            out["shape_keys"] = [b.name for b in blocks]
    if "vertex_groups" in kinds and obj.vertex_groups:
        out["vertex_groups"] = [g.name for g in obj.vertex_groups]
    return out


def check_extra_data(obj, item):
    if obj.type != 'MESH':
        return []
    kinds = _wanted(item)
    found = found_extra(obj, kinds)
    if not found:
        return []
    return [{
        "message": ("Static mesh carries %s"
                    % ", ".join("%d %s" % (len(names), kind)
                                for kind, names in sorted(found.items()))),
        "element_ref": "",
        "values": {kind: names[:8] for kind, names in found.items()},
    }]
