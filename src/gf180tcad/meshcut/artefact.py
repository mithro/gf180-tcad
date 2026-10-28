# SPDX-License-Identifier: Apache-2.0
"""The two files of a reduced mesh artefact and their checks.

An artefact directory, ``results/tcad/meshes/<image>/<device>/<params>/<gid>/``, holds
:data:`gf180tcad.meshcut.ARTEFACT` (the window's arrays, written by
:func:`gf180tcad.meshcut.npz.write_npz`) and :data:`gf180tcad.meshcut.META` (sorted-key JSON,
written by :func:`gf180tcad.io.write_json`). The meta file ties the artefact to its job:

- ``job``: the source job's ``tree`` (``tcad/moscap2d``), ``device``, ``params``,
  ``geometry_id`` and ``cv_meta_sha256``, the sha256 of its committed ``cv.meta.json``;
- ``full_mesh_sha256``, ``full_mesh_node_count``, ``full_mesh_triangle_count``: the full mesh
  it was cut from, whose sha256 is the job's committed ``mesh_sha256``;
- ``window``: the bounds ``x_um`` and ``y_um`` and the ``rule`` that set them
  (:func:`gf180tcad.meshcut.window.rule_bounds` and its arguments);
- ``node_count``, ``triangle_count``, ``boundary_line_count``, ``regions``, ``boundaries``:
  what the npz holds;
- ``npz_sha256``, ``source`` (``cache`` or ``regenerated``), ``units``, ``net_doping`` (how
  ``net_doping_cm3`` was evaluated) and ``format`` (:data:`gf180tcad.meshcut.FORMAT`).

:func:`check_meta` refuses a meta file with a missing, extra or ill-typed field, and
:func:`read` refuses an npz whose sha256 or members disagree with its meta.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path

import numpy as np

from gf180tcad import io, meshcut
from gf180tcad.meshcut import npz
from gf180tcad.meshcut.window import Window

META_KEYS = (
    "boundaries",
    "boundary_line_count",
    "format",
    "full_mesh_node_count",
    "full_mesh_sha256",
    "full_mesh_triangle_count",
    "job",
    "net_doping",
    "node_count",
    "npz_sha256",
    "regions",
    "source",
    "triangle_count",
    "units",
    "window",
)
"""The keys of a meta file, sorted."""
JOB_KEYS = ("cv_meta_sha256", "device", "geometry_id", "params", "tree")
"""The keys of its ``job`` record, sorted."""
WINDOW_KEYS = ("rule", "x_um", "y_um")
"""The keys of its ``window`` record, sorted."""
RULE_KEYS = ("depth_um", "gate_x_um", "kx", "poly_top_um", "surface_um")
"""The keys of the window's ``rule``: the arguments of ``rule_bounds``, sorted."""
SOURCES = ("cache", "regenerated")
"""Where the full mesh came from: pulled from the output cache, or regenerated in the sandbox."""
UNITS = {"net_doping_cm3": "cm^-3", "nodes_cm": "cm", "um_per_mesh_unit": 1e4, "window": "um"}
"""The units of the members and of the window bounds."""
NET_DOPING = (
    "Donors - Acceptors of the 2D job's own profiles (gplugins.devsim.doping, numpy form) at "
    "each node of a silicon region, in that region's frame and bound to that region's bounds "
    "in the full mesh, as assign_doping does; 0 at a node of no silicon region"
)
"""How ``net_doping_cm3`` is evaluated (:func:`gf180tcad.meshcut.job.net_doping`)."""

# Each npz member: its dtype and its shape in terms of the meta's counts.
_MEMBERS = {
    "boundary": (np.uint8, ("boundary_line_count",)),
    "boundary_lines": (np.int32, ("boundary_line_count", 2)),
    "net_doping_cm3": (np.float64, ("node_count",)),
    "node_id": (np.int64, ("node_count",)),
    "nodes_cm": (np.float64, ("node_count", 2)),
    "region": (np.uint8, ("triangle_count",)),
    "triangles": (np.int32, ("triangle_count", 3)),
}
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _fail(msg: str) -> None:
    raise ValueError(f"{meshcut.META}: {msg}")


def _keys(record: object, keys: tuple[str, ...], where: str) -> None:
    if not isinstance(record, dict) or tuple(sorted(record)) != keys:
        got = sorted(record) if isinstance(record, dict) else type(record).__name__
        _fail(f"{where} must have the keys {list(keys)}, has {got}")


def _count(value: object, where: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail(f"{where} must be a count (an int >= 0), is {value!r}")


def _number(value: object, where: str) -> None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        _fail(f"{where} must be a number, is {value!r}")


def _sha(value: object, where: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _fail(f"{where} must be a sha256 (64 lower-case hex digits), is {value!r}")


def _names(value: object, where: str) -> None:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        _fail(f"{where} must be a list of names, is {value!r}")


def _pair(value: object, where: str) -> None:
    if not isinstance(value, list) or len(value) != 2:
        _fail(f"{where} must be a pair [low, high], is {value!r}")
    for v in value:
        _number(v, where)
    if not value[0] < value[1]:
        _fail(f"{where} must have low < high, is {value!r}")


def check_meta(meta: Mapping) -> None:
    """Raise ValueError unless ``meta`` is a complete, well-typed artefact meta record."""
    _keys(meta, META_KEYS, "the meta")
    if meta["format"] != meshcut.FORMAT:
        _fail(f"format {meta['format']!r}, this reader reads {meshcut.FORMAT}")
    _keys(meta["job"], JOB_KEYS, "job")
    _sha(meta["job"]["cv_meta_sha256"], "job.cv_meta_sha256")
    for k in ("device", "geometry_id", "params", "tree"):
        if not isinstance(meta["job"][k], str) or not meta["job"][k]:
            _fail(f"job.{k} must be a name, is {meta['job'][k]!r}")
    for k in ("full_mesh_sha256", "npz_sha256"):
        _sha(meta[k], k)
    for k in (
        "boundary_line_count", "full_mesh_node_count", "full_mesh_triangle_count", "node_count",
        "triangle_count",
    ):  # fmt: skip
        _count(meta[k], k)
    _names(meta["regions"], "regions")
    _names(meta["boundaries"], "boundaries")
    if meta["source"] not in SOURCES:
        _fail(f"source must be one of {list(SOURCES)}, is {meta['source']!r}")
    if meta["units"] != UNITS:
        _fail(f"units must be {UNITS}, are {meta['units']!r}")
    if meta["net_doping"] != NET_DOPING:
        _fail(f"net_doping must be {NET_DOPING!r}")
    _keys(meta["window"], WINDOW_KEYS, "window")
    _pair(meta["window"]["x_um"], "window.x_um")
    _pair(meta["window"]["y_um"], "window.y_um")
    rule = meta["window"]["rule"]
    _keys(rule, RULE_KEYS, "window.rule")
    for k in ("depth_um", "kx", "poly_top_um", "surface_um"):
        _number(rule[k], f"window.rule.{k}")
    _pair(rule["gate_x_um"], "window.rule.gate_x_um")


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(
    out_dir: Path,
    win: Window,
    *,
    job: Mapping[str, str],
    full_mesh_sha256: str,
    full_mesh_node_count: int,
    full_mesh_triangle_count: int,
    rule: Mapping[str, object],
    source: str,
) -> dict:
    """Write the artefact of ``win`` (which must carry ``net_doping_cm3``) and its meta into
    ``out_dir``; return the meta record, checked with :func:`check_meta`."""
    if win.net_doping_cm3 is None:
        raise ValueError("the window has no net_doping_cm3; set it with with_net_doping")
    out_dir = Path(out_dir)
    npz.write_npz(out_dir / meshcut.ARTEFACT, win.arrays())
    meta = {
        "boundaries": list(win.boundaries),
        "boundary_line_count": len(win.boundary_lines),
        "format": meshcut.FORMAT,
        "full_mesh_node_count": int(full_mesh_node_count),
        "full_mesh_sha256": full_mesh_sha256,
        "full_mesh_triangle_count": int(full_mesh_triangle_count),
        "job": dict(job),
        "net_doping": NET_DOPING,
        "node_count": len(win.node_id),
        "npz_sha256": _sha256(out_dir / meshcut.ARTEFACT),
        "regions": list(win.regions),
        "source": source,
        "triangle_count": len(win.triangles),
        "units": dict(UNITS),
        "window": {
            "rule": {k: list(v) if isinstance(v, tuple) else v for k, v in rule.items()},
            "x_um": list(win.x_um),
            "y_um": list(win.y_um),
        },
    }
    # the record as it reads back (tuples become lists), checked before it is written
    meta = json.loads(json.dumps(meta))
    check_meta(meta)
    io.write_json(out_dir / meshcut.META, meta)
    return meta


def read_meta(job_dir: Path) -> dict:
    """The checked meta record of the artefact in ``job_dir``."""
    meta = json.loads((Path(job_dir) / meshcut.META).read_bytes())
    check_meta(meta)
    return meta


def read(job_dir: Path) -> Window:
    """The :class:`~gf180tcad.meshcut.window.Window` of the artefact in ``job_dir``
    (``results/tcad/meshes/<image>/<device>/<params>/<gid>``), with ``net_doping_cm3``.

    Raises ValueError if the meta is not complete and well typed, if the npz's sha256 is not
    the meta's ``npz_sha256``, or if a member is missing or has another dtype or shape than
    the meta's counts give.
    """
    job_dir = Path(job_dir)
    meta = read_meta(job_dir)
    path = job_dir / meshcut.ARTEFACT
    got = _sha256(path)
    if got != meta["npz_sha256"]:
        raise ValueError(f"{path}: sha256 {got}, the meta's npz_sha256 is {meta['npz_sha256']}")
    arrays = npz.read_npz(path)
    if sorted(arrays) != sorted(_MEMBERS):
        raise ValueError(f"{path}: members {sorted(arrays)}, expected {sorted(_MEMBERS)}")
    for name, (dtype, shape) in _MEMBERS.items():
        want = tuple(meta[s] if isinstance(s, str) else s for s in shape)
        a = arrays[name]
        if a.dtype != np.dtype(dtype) or a.shape != want:
            raise ValueError(
                f"{path}: member {name} is {a.dtype} {a.shape}, the meta gives "
                f"{np.dtype(dtype)} {want}"
            )
    return Window(
        nodes_cm=arrays["nodes_cm"],
        node_id=arrays["node_id"],
        triangles=arrays["triangles"],
        region=arrays["region"],
        regions=tuple(meta["regions"]),
        boundary_lines=arrays["boundary_lines"],
        boundary=arrays["boundary"],
        boundaries=tuple(meta["boundaries"]),
        x_um=tuple(meta["window"]["x_um"]),
        y_um=tuple(meta["window"]["y_um"]),
        net_doping_cm3=arrays["net_doping_cm3"],
    )
