# SPDX-License-Identifier: Apache-2.0
"""A strict reader of gmsh MSH 2.2 ASCII meshes, as gplugins writes the 2D jobs' ``mesh.msh``.

It reads the four sections ``$MeshFormat``, ``$PhysicalNames``, ``$Nodes`` and ``$Elements``
and refuses anything else it would have to interpret: another format version, the binary
file type, element types other than 1 (two-node line) and 2 (three-node triangle), a node
with a non-zero z, a node or physical tag that is not declared, a count that disagrees with
its block. Gmsh's file format is described in the gmsh reference manual, section "MSH file
format version 2 (Legacy)" (https://gmsh.info/doc/texinfo/gmsh.html).

Coordinates are parsed with ``float()``, which rounds the decimal text correctly, so each
coordinate is the exact double the file names.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

LINE = 1
TRIANGLE = 2
_NODES_PER_TYPE = {LINE: 2, TRIANGLE: 3}


class MshError(ValueError):
    """The file is not an MSH 2.2 ASCII mesh this reader accepts."""


@dataclass(frozen=True)
class Mesh:
    """A 2D mesh: node coordinates (file units), node ids, and elements as node indices.

    ``nodes`` is float64 (n, 2) in ascending ``node_id`` order; ``triangles`` (m, 3) and
    ``lines`` (k, 2) are int64 indices into ``nodes``; ``triangle_tag`` and ``line_tag`` hold
    each element's physical tag; ``names`` maps ``(dimension, tag)`` to the physical name.
    """

    nodes: np.ndarray
    node_id: np.ndarray
    triangles: np.ndarray
    triangle_tag: np.ndarray
    lines: np.ndarray
    line_tag: np.ndarray
    names: dict[tuple[int, int], str]

    def region_names(self) -> tuple[str, ...]:
        """The 2D physical names (regions), in tag order."""
        return tuple(self.names[k] for k in sorted(self.names) if k[0] == 2)

    def boundary_names(self) -> tuple[str, ...]:
        """The 1D physical names (interfaces and outer boundaries), in tag order."""
        return tuple(self.names[k] for k in sorted(self.names) if k[0] == 1)


def _section(lines: list[str], name: str) -> list[str]:
    try:
        start = lines.index(f"${name}")
        end = lines.index(f"$End{name}", start)
    except ValueError:
        raise MshError(f"no ${name} ... $End{name} section") from None
    return lines[start + 1 : end]


def _counted(body: list[str], name: str) -> list[str]:
    if not body:
        raise MshError(f"${name}: no count line")
    try:
        count = int(body[0])
    except ValueError:
        raise MshError(f"${name}: bad count line {body[0]!r}") from None
    rows = body[1:]
    if count != len(rows):
        raise MshError(f"${name}: count {count} but {len(rows)} lines")
    return rows


def _format(lines: list[str]) -> None:
    body = _section(lines, "MeshFormat")
    if len(body) != 1 or len(body[0].split()) != 3:
        raise MshError(
            f"$MeshFormat: expected one line 'version file-type data-size', got {body!r}"
        )
    version, file_type, data_size = body[0].split()
    if version != "2.2":
        raise MshError(f"$MeshFormat: version {version}, only 2.2 is read")
    if file_type != "0":
        raise MshError(f"$MeshFormat: file-type {file_type}, only 0 (ASCII) is read")
    if data_size != "8":
        raise MshError(f"$MeshFormat: data size {data_size}, only 8 is read")


def _names(lines: list[str]) -> dict[tuple[int, int], str]:
    names: dict[tuple[int, int], str] = {}
    for row in _counted(_section(lines, "PhysicalNames"), "PhysicalNames"):
        parts = row.split(maxsplit=2)
        if len(parts) != 3 or not (parts[2].startswith('"') and parts[2].endswith('"')):
            raise MshError(f"$PhysicalNames: bad line {row!r}")
        key = (int(parts[0]), int(parts[1]))
        if key in names:
            raise MshError(f"$PhysicalNames: duplicate {key}")
        names[key] = parts[2][1:-1]
    return names


def _nodes(lines: list[str]) -> tuple[np.ndarray, np.ndarray]:
    rows = _counted(_section(lines, "Nodes"), "Nodes")
    ids = np.empty(len(rows), dtype=np.int64)
    xy = np.empty((len(rows), 2), dtype=np.float64)
    for k, row in enumerate(rows):
        parts = row.split()
        if len(parts) != 4:
            raise MshError(f"$Nodes: bad line {row!r}")
        z = float(parts[3])
        if z != 0.0:
            raise MshError(f"$Nodes: node {parts[0]} has z = {parts[3]}, a 2D mesh has z = 0")
        ids[k] = int(parts[0])
        xy[k, 0] = float(parts[1])
        xy[k, 1] = float(parts[2])
    order = np.argsort(ids, kind="stable")
    ids, xy = ids[order], xy[order]
    if len(ids) > 1 and np.any(ids[1:] == ids[:-1]):
        raise MshError(f"$Nodes: duplicate node id {int(ids[1:][ids[1:] == ids[:-1]][0])}")
    return ids, xy


def _elements(
    lines: list[str], names: dict[tuple[int, int], str]
) -> dict[int, tuple[list[list[int]], list[int]]]:
    out: dict[int, tuple[list[list[int]], list[int]]] = {LINE: ([], []), TRIANGLE: ([], [])}
    for row in _counted(_section(lines, "Elements"), "Elements"):
        parts = [int(p) for p in row.split()]
        if len(parts) < 3:
            raise MshError(f"$Elements: bad line {row!r}")
        typ, ntags = parts[1], parts[2]
        if typ not in _NODES_PER_TYPE:
            raise MshError(
                f"$Elements: element type {typ} (element {parts[0]}); only 1 and 2 are read"
            )
        if ntags < 1:
            raise MshError(f"$Elements: element {parts[0]} has no physical tag")
        nodes = parts[3 + ntags :]
        if len(nodes) != _NODES_PER_TYPE[typ]:
            raise MshError(
                f"$Elements: element {parts[0]} of type {typ} has {len(nodes)} nodes, "
                f"expected {_NODES_PER_TYPE[typ]}"
            )
        tag = parts[3]
        if (typ, tag) not in names:
            raise MshError(
                f"$Elements: element {parts[0]} has physical tag {tag}, not in $PhysicalNames"
            )
        out[typ][0].append(nodes)
        out[typ][1].append(tag)
    return out


def _indices(ids: np.ndarray, refs: list[list[int]], width: int) -> np.ndarray:
    a = np.array(refs, dtype=np.int64).reshape(-1, width)
    idx = np.searchsorted(ids, a)
    bad = (idx >= len(ids)) | (ids[np.minimum(idx, len(ids) - 1)] != a)
    if np.any(bad):
        raise MshError(f"$Elements: unknown node id {int(a[bad][0])}")
    return idx


def read(path: Path | str) -> Mesh:
    """Read ``path`` (MSH 2.2 ASCII); raise :class:`MshError` on anything else."""
    lines = Path(path).read_text(encoding="ascii").splitlines()
    _format(lines)
    names = _names(lines)
    ids, xy = _nodes(lines)
    elements = _elements(lines, names)
    tris, tri_tag = elements[TRIANGLE]
    segs, seg_tag = elements[LINE]
    return Mesh(
        nodes=xy,
        node_id=ids,
        triangles=_indices(ids, tris, 3),
        triangle_tag=np.array(tri_tag, dtype=np.int64),
        lines=_indices(ids, segs, 2),
        line_tag=np.array(seg_tag, dtype=np.int64),
        names=names,
    )
