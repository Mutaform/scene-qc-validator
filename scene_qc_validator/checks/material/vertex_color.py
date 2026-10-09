# -*- coding: utf-8 -*-
"""Vertex Color ID: маска слоёв, записанная в красный канал вершинного цвета.

Правила проекта (ARDENA, «General Medium Poly Pipeline», раздел 8):
меш заливается чистым чёрным, участкам назначается значение ТОЛЬКО в красном
канале, значения идут шагом 0.1 - 0.1 это слой 1, 0.2 слой 2, и так до 1.0,
слой 10. Чёрный - не слой, это фон. Все десять на одном ассете не обязательны,
но одного слоя мало: маска из одного значения ничего не разделяет.

Те же правила уже проверяет набор для UE (`ardena_fbx.py`, коды `FBX.VID.STEP`,
`FBX.VID.GB_NONZERO`, `FBX.VID.LIMIT`), и пороги здесь взяты оттуда, а не
выдуманы заново: допуск на шаг - 0.008 от значения цвета, «ноль» в G/B - это
меньше 0.01, лимит - 10 ID на ассет. Разойтись этим двум наборам нельзя: один
и тот же ассет не должен приниматься в Blender и отклоняться в Unreal.

Про байтовый цвет. У атрибута два представления: FLOAT_COLOR хранит линейные
числа, BYTE_COLOR - восемь бит в sRGB. Через `.color` Blender всегда отдаёт
линейное, и для байтового атрибута авторские 0.1 превратились бы в 0.01 - все
значения разом «не кратны шагу». Поэтому у байтового читаем `color_srgb`:
нужно то число, которое художник набрал в DCC, а не его линейный образ.
"""

from ..common import *

MAX_IDS = 10                 # лимит на ассет, как в ardena_fbx.MAX_VERTEX_IDS
STEP = 0.1
STEP_TOLERANCE = 0.008       # 0.08 шага - тот же допуск, что у набора для UE
BLACK = 0.05                 # ниже этого красный считается фоном, а не слоем
CHANNEL_ZERO = 0.01          # «ноль» в G и B


def _attribute(mesh, name=""):
    """Атрибут цвета: по имени, иначе активный, иначе первый."""
    attributes = getattr(mesh, "color_attributes", None)
    if not attributes:
        return None
    if name:
        return attributes.get(name)
    return attributes.active_color or attributes[0]


def _read(attribute):
    """(reds, greens, blues) значениями, которые набирал художник.

    foreach_get, а не цикл по data: на меше в 11 тысяч граней это разница между
    десятыми долями секунды и несколькими секундами.
    """
    count = len(attribute.data)
    if not count:
        return [], [], []
    # байтовый атрибут хранит sRGB - берём его как есть, см. шапку модуля
    field = "color_srgb" if attribute.data_type == 'BYTE_COLOR' else "color"
    flat = [0.0] * (count * 4)
    try:
        attribute.data.foreach_get(field, flat)
    except (TypeError, RuntimeError):
        attribute.data.foreach_get("color", flat)
    return flat[0::4], flat[1::4], flat[2::4]


def _layers(reds):
    """Номера слоёв, найденные в красном канале. Чёрный - не слой."""
    return sorted({int(round(value / STEP)) for value in reds if value > BLACK})


def check_vertex_color_missing(obj, item):
    """На меше должен быть атрибут вершинного цвета: он несёт маску слоёв."""
    name = item.string_param_1.strip()
    mesh = obj.data
    attribute = _attribute(mesh, name)
    if attribute is not None:
        return []
    present = [a.name for a in getattr(mesh, "color_attributes", ())]
    return [{
        "message": ("No vertex color attribute%s on the mesh"
                    % ((" named '%s'" % name) if name else "")),
        "element_ref": "",
        "values": {"wanted": name, "present": present},
    }]


def check_vertex_color_ids(obj, item):
    """Значения ID: шаг, только красный канал, число разных слоёв."""
    name = item.string_param_1.strip()
    step_tolerance = item.float_param_1 if item.float_param_1 > 0 else STEP_TOLERANCE
    minimum = max(0, item.int_param_1)
    limit = max(0, item.int_param_2)
    require_clean_gb = item.bool_param_1

    attribute = _attribute(obj.data, name)
    if attribute is None:
        return []                       # «нет вовсе» - это vc_missing, не здесь

    reds, greens, blues = _read(attribute)
    if not reds:
        return []

    issues = []
    common = {"attr": attribute.name, "type": attribute.data_type,
              "domain": attribute.domain}

    # --- шаг 0.1
    distinct = sorted({round(value, 4) for value in reds})
    off_step = [value for value in distinct
                if value > BLACK and abs(value - round(value / STEP) * STEP) > step_tolerance]
    if off_step:
        issues.append(dict(common, **{
            "message": ("Vertex ID not a multiple of %.1f: %s"
                        % (STEP, ", ".join("%.3f" % v for v in off_step[:6]))),
            "element_ref": "",
            "values": dict(common, kind="step", step=STEP,
                           values=[round(v, 3) for v in off_step[:6]],
                           count=len(off_step)),
        }))

    # --- ID только в красном
    if require_clean_gb:
        dirty = sum(1 for g, b in zip(greens, blues)
                    if g > CHANNEL_ZERO or b > CHANNEL_ZERO)
        if dirty:
            issues.append(dict(common, **{
                "message": ("Green/Blue vertex color is not zero on %d value(s); "
                            "the ID lives in Red only" % dirty),
                "element_ref": "",
                "values": dict(common, kind="gb", count=dirty, total=len(reds)),
            }))

    # --- значения выше 1.0: кратны шагу, но такого слоя в таблице нет
    layers = _layers(reds)
    beyond = [number for number in layers if number > MAX_IDS]
    if beyond:
        issues.append(dict(common, **{
            "message": ("Vertex ID above %.1f: %s - the table ends at layer %d"
                        % (STEP * MAX_IDS,
                           ", ".join("%.1f" % (n * STEP) for n in beyond[:6]), MAX_IDS)),
            "element_ref": "",
            "values": dict(common, kind="range", layers=beyond,
                           top=MAX_IDS, count=len(beyond)),
        }))

    # --- сколько разных слоёв
    if minimum and len(layers) < minimum:
        issues.append(dict(common, **{
            "message": ("Vertex color carries %d layer id(s), at least %d expected"
                        % (len(layers), minimum)),
            "element_ref": "",
            "values": dict(common, kind="few", layers=layers,
                           count=len(layers), min=minimum),
        }))
    if limit and len(layers) > limit:
        issues.append(dict(common, **{
            "message": ("Vertex color carries %d layer id(s), maximum is %d"
                        % (len(layers), limit)),
            "element_ref": "",
            "values": dict(common, kind="many", layers=layers,
                           count=len(layers), max=limit),
        }))
    return [{"message": i["message"], "element_ref": i["element_ref"],
             "values": i["values"]} for i in issues]


def layer_summary(obj, name=""):
    """«0.1, 0.3, 0.5» для строки разбора. ("", []) - атрибута нет."""
    attribute = _attribute(obj.data, name)
    if attribute is None:
        return "", []
    reds, _g, _b = _read(attribute)
    if not reds:
        return attribute.name, []
    return attribute.name, _layers(reds)
