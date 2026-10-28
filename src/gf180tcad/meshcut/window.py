# SPDX-License-Identifier: Apache-2.0
"""The gate window of a 2D mesh: a rule for its bounds and the cut that keeps whole elements.

:func:`rule_bounds` turns the gate's edges into the window: in x, from the gate's left edge
minus ``kx`` gate lengths to its right edge plus ``kx`` gate lengths; in y, from ``depth_um``
below the silicon surface to the poly top. :func:`cut` keeps every triangle whose centroid
lies in the window (bounds included) and nothing else: no element is split, resampled,
smoothed or decimated. The kept nodes are the ones those triangles use, renumbered in
ascending order of their id in the full mesh, with their coordinates copied unconverted.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from gf180tcad.meshcut import UM_PER_MSH_UNIT
from gf180tcad.meshcut.msh import Mesh


def rule_bounds(
    *,
    gate_x_um: tuple[float, float],
    poly_top_um: float,
    surface_um: float,
    kx: float,
    depth_um: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """The window ``(x_um, y_um)`` around a gate from ``gate_x_um[0]`` to ``gate_x_um[1]``."""
    left, right = gate_x_um
    if not right > left:
        raise ValueError(f"the gate's right edge {right!r} is not right of its left edge {left!r}")
    if kx < 0 or depth_um < 0:
        raise ValueError(f"kx {kx!r} and depth_um {depth_um!r} must not be negative")
    if not poly_top_um > surface_um - depth_um:
        raise ValueError(f"the poly top {poly_top_um!r} is not above the window bottom")
    length = right - left
    return (left - kx * length, right + kx * length), (surface_um - depth_um, poly_top_um)


@dataclass(frozen=True)
class Window:
    """The cut: ``nodes_cm`` (n, 2) float64 in the mesh file's unit, ``node_id`` (n,) int64,
    ``triangles`` (m, 3) int32 and ``boundary_lines`` (k, 2) int32 indices into the nodes,
    ``region`` (m,) uint8 into ``regions`` and ``boundary`` (k,) uint8 into ``boundaries``,
    and the bounds ``x_um``, ``y_um`` it was cut with. ``net_doping_cm3`` (n,) float64 is the
    job's net doping at each node (:func:`gf180tcad.meshcut.job.net_doping`), None until
    :meth:`with_net_doping` sets it."""

    nodes_cm: np.ndarray
    node_id: np.ndarray
    triangles: np.ndarray
    region: np.ndarray
    regions: tuple[str, ...]
    boundary_lines: np.ndarray
    boundary: np.ndarray
    boundaries: tuple[str, ...]
    x_um: tuple[float, float]
    y_um: tuple[float, float]
    net_doping_cm3: np.ndarray | None = None

    def arrays(self) -> dict[str, np.ndarray]:
        """The npz members of the artefact (``net_doping_cm3`` only once it is set)."""
        out = {
            "boundary": self.boundary,
            "boundary_lines": self.boundary_lines,
            "node_id": self.node_id,
            "nodes_cm": self.nodes_cm,
            "region": self.region,
            "triangles": self.triangles,
        }
        if self.net_doping_cm3 is not None:
            out["net_doping_cm3"] = self.net_doping_cm3
        return out

    def with_net_doping(self, values: np.ndarray) -> Window:
        """This window with ``net_doping_cm3`` set to ``values`` (cm^-3), one per node."""
        values = np.asarray(values, dtype=np.float64)
        if values.shape != (len(self.node_id),):
            raise ValueError(
                f"net doping needs one value per node ({len(self.node_id)}), got {values.shape}"
            )
        return replace(self, net_doping_cm3=values)


def _tag_index(mesh: Mesh, dim: int) -> dict[int, int]:
    tags = sorted(t for d, t in mesh.names if d == dim)
    if len(tags) > 256:
        raise ValueError(f"{len(tags)} physical groups of dimension {dim}; uint8 holds 256")
    return {t: k for k, t in enumerate(tags)}


def cut(
    mesh: Mesh,
    *,
    x_um: tuple[float, float],
    y_um: tuple[float, float],
    um_per_unit: float = UM_PER_MSH_UNIT,
) -> Window:
    """Keep the triangles of ``mesh`` whose centroid lies in ``x_um`` x ``y_um`` (closed)."""
    centroid = mesh.nodes[mesh.triangles].mean(axis=1) * um_per_unit
    inside = (
        (centroid[:, 0] >= x_um[0])
        & (centroid[:, 0] <= x_um[1])
        & (centroid[:, 1] >= y_um[0])
        & (centroid[:, 1] <= y_um[1])
    )
    kept = np.flatnonzero(inside)
    if len(kept) == 0:
        raise ValueError(f"no element has its centroid in x = {x_um} um, y = {y_um} um")
    tris = mesh.triangles[kept]
    used = np.unique(tris)  # node indices, ascending; the nodes are in ascending id order
    renumber = np.full(len(mesh.nodes), -1, dtype=np.int64)
    renumber[used] = np.arange(len(used))
    new_tris = renumber[tris]

    region_of = _tag_index(mesh, 2)
    region = np.array([region_of[int(t)] for t in mesh.triangle_tag[kept]], dtype=np.uint8)

    # the mesh's own line elements that are edges of a kept triangle
    pairs = np.concatenate([new_tris[:, [0, 1]], new_tris[:, [1, 2]], new_tris[:, [2, 0]]])
    edge_set = {(int(a), int(b)) for a, b in np.sort(pairs, axis=1)}
    line_nodes = renumber[mesh.lines].reshape(-1, 2)
    keep_line = [
        k
        for k, (a, b) in enumerate(line_nodes.tolist())
        if a >= 0 and b >= 0 and (min(a, b), max(a, b)) in edge_set
    ]
    boundary_of = _tag_index(mesh, 1)
    boundary = [boundary_of[int(mesh.line_tag[k])] for k in keep_line]
    return Window(
        nodes_cm=mesh.nodes[used].copy(),
        node_id=mesh.node_id[used].copy(),
        triangles=new_tris.astype(np.int32),
        region=region,
        regions=mesh.region_names(),
        boundary_lines=line_nodes[keep_line].astype(np.int32).reshape(-1, 2),
        boundary=np.array(boundary, dtype=np.uint8),
        boundaries=mesh.boundary_names(),
        x_um=x_um,
        y_um=y_um,
    )
