# -*- coding: utf-8 -*-
"""Вывернутые нормали: в движке это дырка в модели, видно насквозь.

Две разные беды, и путать их нельзя - они и выглядят, и ищутся по-разному.

**Грани смотрят в разные стороны.** Ищется топологией, без эвристик: у
правильно ориентированной поверхности две грани проходят общее ребро в
противоположных направлениях. Если обе идут одинаково - значит одна из них
развёрнута относительно соседки. Такой шов видно и в вьюпорте (чёрная
полоса), и на бейке. Работает одинаково на замкнутых и открытых оболочках.

**Оболочка вывернута целиком.** Нормали согласованы, но смотрят внутрь. По
топологии это не отличить - нужен знаковый объём: у вывернутого замкнутого
объёма он отрицательный. Поэтому судим так только ЗАМКНУТЫЕ оболочки: у
открытой «внутри» не определено, и любой ответ будет выдумкой.

Объём считаем в мировом знаке: он умножается на определитель матрицы объекта,
и отрицательный масштаб переворачивает его. Это не придирка - объект с
масштабом -1 приедет в движок вывернутым, и художник этого в Blender не видит.

Чинит всё это `Recalculate Outside`, поэтому автофикс - ровно он: находка
говорит буквально «вот эти грани он развернёт». При отрицательном масштабе
после пересчёта грани переворачиваются ещё раз, иначе наружу они будут
смотреть только в локальных координатах.
"""

from ..common import *

SHOW_FACES = 2000           # столько индексов кладём в выделение


def _components(bm):
    """Связные оболочки списками граней: обход по рёбрам."""
    seen = set()
    out = []
    for face in bm.faces:
        if face.index in seen:
            continue
        stack, group = [face], []
        seen.add(face.index)
        while stack:
            current = stack.pop()
            group.append(current)
            for edge in current.edges:
                for other in edge.link_faces:
                    if other.index not in seen:
                        seen.add(other.index)
                        stack.append(other)
        out.append(group)
    return out


def _mixed_edges(faces):
    """Рёбра, по которым соседние грани развёрнуты друг против друга."""
    bad = []
    for face in faces:
        for loop in face.loops:
            edge = loop.edge
            if len(edge.link_faces) != 2:
                continue
            other = edge.link_faces[0] if edge.link_faces[1] is face else edge.link_faces[1]
            if other.index <= face.index:
                continue                    # пару считаем один раз
            for other_loop in other.loops:
                if other_loop.edge is edge:
                    # согласованы, если общее ребро проходится в разные стороны
                    if other_loop.vert is loop.vert:
                        bad.append(edge.index)
                    break
    return bad


def _closed(faces):
    return all(len(edge.link_faces) == 2 for face in faces for edge in face.edges)


def _volume(faces):
    """Знаковый объём оболочки в локальных единицах."""
    total = 0.0
    for face in faces:
        points = [vertex.co for vertex in face.verts]
        for index in range(1, len(points) - 1):
            a, b, c = points[0], points[index], points[index + 1]
            total += a.dot(b.cross(c))
    return total / 6.0


def check_flipped_normals(obj, item):
    """Несогласованные грани и оболочки, вывернутые наизнанку."""
    if obj.type != 'MESH':
        return []
    skip_open = bool(getattr(item, "bool_param_1", False))
    bm, owned = _read_bmesh(obj)
    try:
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        if not bm.faces:
            return []
        flip = obj.matrix_world.determinant() < 0
        mixed, inverted_faces, inverted_shells = [], [], 0
        for group in _components(bm):
            closed = _closed(group)
            if not (skip_open and not closed):
                mixed.extend(_mixed_edges(group))
            if not closed:
                continue                    # у открытой оболочки «внутри» нет
            volume = _volume(group)
            if flip:
                volume = -volume
            if volume < 0:
                inverted_shells += 1
                inverted_faces.extend(face.index for face in group)
        issues = []
        if mixed:
            faces = sorted({face.index for index in mixed
                            for face in bm.edges[index].link_faces})
            issues.append({
                "message": ("%d edge(s) where neighbouring faces are wound against "
                            "each other" % len(mixed)),
                "element_ref": "f:" + ",".join(str(i) for i in faces[:SHOW_FACES]),
                "values": {"kind": "mixed", "edges": len(mixed), "faces": len(faces)},
            })
        if inverted_faces:
            issues.append({
                "message": ("%d closed shell(s) are inside out (%d face(s))"
                            % (inverted_shells, len(inverted_faces))),
                "element_ref": "f:" + ",".join(
                    str(i) for i in sorted(inverted_faces)[:SHOW_FACES]),
                "values": {"kind": "inside_out", "shells": inverted_shells,
                           "faces": len(inverted_faces),
                           "mirrored": flip},
            })
        return issues
    finally:
        if owned:
            bm.free()


def fix_flipped_normals(obj, item, result):
    """Recalculate Outside, а при отрицательном масштабе - ещё и разворот."""
    if obj.type != 'MESH':
        return False
    before = check_flipped_normals(obj, item)
    if not before:
        return False
    bm, owned = _read_bmesh(obj)
    try:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        if obj.matrix_world.determinant() < 0:
            # после пересчёта грани смотрят наружу в локальных координатах, а
            # зеркальная матрица выворачивает их обратно уже в мире
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        if owned:
            _write_bmesh(obj, bm)
            owned = False               # _write_bmesh уже освободил
        else:
            bmesh.update_edit_mesh(obj.data)
        return True
    finally:
        if owned:
            bm.free()
