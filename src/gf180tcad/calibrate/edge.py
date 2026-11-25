# SPDX-License-Identifier: Apache-2.0
"""Fit the poly length bias δ of the 2D cells and freeze it (issue #189, plan Task E3).

Run as::

    uv run --locked python -m gf180tcad.calibrate.edge --device nfet_05v0 --out results/tcad/edgefit

Over the widest calibrated 2D cells, Cgg per unit width is a line in the gate length L,
``Cgg / W = C_edge + C_area · L`` (least squares, the edge split of
:func:`gf180tcad.comparison_figures.edge_split`). At each plateau, u = −5 V and +5 V, the target
is the SPICE ``C_edge`` minus the 2D ``C_edge``. A poly longer by δ at each end adds
``slope · δ`` on both plateaus. The slope is the least-squares line through the origin of the
edge-sensitivity record's ``bias<nm>`` variants (``results/edge-sensitivity``). δ minimises the
squared misses of the two targets, so ``slope · δ`` is their mean.

The file written, ``<out>/<device>.json``, holds δ and every input it was made from:

- the record's sha256;
- per length, the SPICE and 2D Cgg per unit width at both plateaus, and the 2D cell's
  ``cv.csv`` sha256;
- the commit.

So the fit can be re-derived after the cells it read are replaced. The command refuses a
checkout with uncommitted changes under the paths it reads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from gf180tcad import io
from gf180tcad.devices import DEVICES, Geometry, geometry_id
from gf180tcad.layout import PROVENANCE_NAME
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.tcad import edgefit, process, provenance

#: This module, the generator of the ``tcad/edgefit`` tree.
EDGE_MAIN = "gf180tcad.calibrate.edge"
#: The plateaus (u = polarity × Vg, V) the fit uses, accumulation first.
EDGE_U_V = (-5.0, 5.0)
#: The SPICE results: the typical ngspice ``cv`` sweeps.
SPICE_ROOT = REPO_ROOT / "results" / "spice"
#: The engine and corner of the SPICE curves.
SPICE_ENGINE, SPICE_CORNER = "ngspice", "typical"
#: The 2D cells: the calibrated ones.
TCAD_ROOT = REPO_ROOT / "results" / "tcad"
#: The parameter set of the 2D cells the fit reads.
CELL_PARAMS = "calibrated"
#: The edge-sensitivity records, one per device, and the cell each was made on.
RECORD_ROOT = REPO_ROOT / "results" / "edge-sensitivity"
#: The cell of each device's edge-sensitivity record.
RECORD_CELLS = {"nfet_05v0": "w10p0_l0p60", "pfet_05v0": "w10p0_l0p50"}
#: The checkout paths the fit reads; uncommitted changes under them are refused.
READ_PATHS = ("src", "data", "results/spice", "results/tcad/moscap2d", "results/edge-sensitivity")
#: fF per F.
FF_PER_F = 1e15


class DirtyCheckout(RuntimeError):
    """The checkout has uncommitted changes under :data:`READ_PATHS`."""


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def wide_geometries(device: str, tcad_root: Path = TCAD_ROOT) -> list[Geometry]:
    """The widest geometries of ``device`` with a committed :data:`CELL_PARAMS` 2D cell, by
    rising L (as :func:`gf180tcad.comparison_figures.edge_geometries`)."""
    wide = max(g.w_um for g in DEVICES[device].geometries)
    root = Path(tcad_root) / "moscap2d" / device / CELL_PARAMS
    gs = [
        g
        for g in DEVICES[device].geometries
        if g.w_um == wide and (root / geometry_id(g) / "cv.csv").is_file()
    ]
    return sorted(gs, key=lambda g: g.l_um)


def _at_plateaus(u: np.ndarray, c: np.ndarray, where: Path) -> list[float]:
    out = []
    for target in EDGE_U_V:
        (i,) = np.flatnonzero(u == target)
        out.append(float(c[i]))
    if len(out) != len(EDGE_U_V):  # pragma: no cover - flatnonzero unpacking raises first
        raise ValueError(f"{where}: no row at u = {EDGE_U_V}")
    return out


def cell_row(
    device: str, g: Geometry, spice_root: Path = SPICE_ROOT, tcad_root: Path = TCAD_ROOT
) -> dict:
    """One length's inputs: Cgg per unit width (fF/µm) of the SPICE curve and of the 2D cell at
    each plateau of :data:`EDGE_U_V`, and the cell's ``cv.csv`` sha256."""
    pol = DEVICES[device].polarity
    gid = geometry_id(g)
    spice_csv = Path(spice_root) / SPICE_ENGINE / SPICE_CORNER / device / gid / "cv.csv"
    s = io.read_csv(spice_csv)[0]
    cell_csv = Path(tcad_root) / "moscap2d" / device / CELL_PARAMS / gid / "cv.csv"
    t = io.read_csv(cell_csv)[0]
    return {
        "cv_csv_sha256": hashlib.sha256(cell_csv.read_bytes()).hexdigest(),
        "gid": gid,
        "l_um": g.l_um,
        "spice": _at_plateaus(pol * s["vg"], s["cgg"] * FF_PER_F / g.w_um, spice_csv),
        "two_d": _at_plateaus(pol * t["vg"], t["cgg_total"] / g.w_um, cell_csv),
        "w_um": g.w_um,
    }


def intercepts(rows: Sequence[dict], key: str) -> list[float]:
    """``C_edge`` at each plateau: the intercept of the least-squares line in L of ``key``
    (``spice`` or ``two_d``) over ``rows``."""
    lengths = np.array([r["l_um"] for r in rows])
    values = np.array([r[key] for r in rows])
    _, edge = np.polyfit(lengths, values, 1)
    return [float(e) for e in edge]


def intercept_weights(rows: Sequence[dict]) -> list[float]:
    """The weights wᵢ with ``C_edge = Σ wᵢ · cᵢ`` for the least-squares line over the rows'
    lengths: how a change in one cell moves the fitted edge."""
    lengths = np.array([r["l_um"] for r in rows])
    a = np.column_stack([np.ones_like(lengths), lengths])
    return [float(w) for w in np.linalg.pinv(a)[0]]


def record_slope(record: dict, device: str) -> float:
    """The gain per nm of poly length bias (fF/µm per nm): the line through the origin of the
    record's ``bias<nm>`` variants, both plateaus."""
    pol = DEVICES[device].polarity
    variants = record["variants"]

    def at(v: dict) -> list[float]:
        by_u = {pol * vg: c for vg, c in zip(v["vg"], v["cgg_ff_per_um"], strict=True)}
        return [by_u[u] for u in EDGE_U_V]

    base = at(variants["base"])
    xs, ys = [], []
    for name, v in variants.items():
        if name.startswith("bias") and name[len("bias") :].isdigit():
            gains = [c - b for c, b in zip(at(v), base, strict=True)]
            xs += [float(name[len("bias") :])] * len(gains)
            ys += gains
    if not xs:
        raise ValueError(f"{device}: no bias<nm> variant in the edge-sensitivity record")
    x, y = np.array(xs), np.array(ys)
    return float(x @ y / (x @ x))


def fit(device: str, record: dict, rows: Sequence[dict]) -> dict:
    """δ (nm) and the quantities it comes from, from a record and the per-length rows."""
    if len(rows) < 3:
        raise ValueError(f"{device}: {len(rows)} gate lengths; the line needs 3 (two to fit one)")
    spice, two_d = intercepts(rows, "spice"), intercepts(rows, "two_d")
    targets = [s - t for s, t in zip(spice, two_d, strict=True)]
    slope = record_slope(record, device)
    delta = float(np.mean(targets)) / slope
    return {
        "residual_ff_per_um": [t - slope * delta for t in targets],
        "slope_ff_per_um_per_nm": slope,
        "spice_edge_ff_per_um": spice,
        "targets_ff_per_um": targets,
        "two_d_edge_ff_per_um": two_d,
        edgefit.PARAM: delta,
    }


def record_path(device: str, root: Path = RECORD_ROOT) -> Path:
    """The edge-sensitivity record of ``device``."""
    return Path(root) / f"{device}-{RECORD_CELLS[device]}.json"


def build(
    device: str,
    *,
    spice_root: Path = SPICE_ROOT,
    tcad_root: Path = TCAD_ROOT,
    record_root: Path = RECORD_ROOT,
    commit: str,
) -> dict:
    """The fit file's content for ``device`` (no checkout check: :func:`run` does that)."""
    rec_path = record_path(device, record_root)
    record = json.loads(rec_path.read_text(encoding="utf-8"))
    rows = [cell_row(device, g, spice_root, tcad_root) for g in wide_geometries(device, tcad_root)]
    proc = process.load(device)
    p = proc.params[edgefit.PARAM]
    out = {
        "cells": rows,
        "cell_params": CELL_PARAMS,
        "commit": commit,
        "device": device,
        "edge_u_v": list(EDGE_U_V),
        "intercept_weights": intercept_weights(rows),
        "record": {
            "cell": RECORD_CELLS[device],
            "file": rec_path.name,
            "sha256": hashlib.sha256(rec_path.read_bytes()).hexdigest(),
        },
        "schema": edgefit.SCHEMA,
        "spice": {"corner": SPICE_CORNER, "engine": SPICE_ENGINE},
        **fit(device, record, rows),
    }
    lo, hi = p.bounds
    if not lo <= out[edgefit.PARAM] <= hi:
        raise ValueError(f"{device}: fitted δ {out[edgefit.PARAM]!r} nm is outside [{lo}, {hi}]")
    return out


def clean_commit(repo_root: Path = REPO_ROOT) -> str:
    """HEAD, or :class:`DirtyCheckout` if anything under :data:`READ_PATHS` is uncommitted."""
    dirty = _git("status", "--porcelain", "--", *READ_PATHS, cwd=repo_root)
    if dirty:
        raise DirtyCheckout(f"uncommitted changes under {READ_PATHS}:\n{dirty}")
    return _git("rev-parse", "HEAD", cwd=repo_root).strip()


def run(device: str, out_root: Path) -> Path:
    """Fit ``device`` from the committed checkout and write ``<out_root>/<device>.json`` and the
    tree's ``provenance.json``."""
    out_root = Path(out_root)
    data = build(device, commit=clean_commit())
    out_root.mkdir(parents=True, exist_ok=True)
    path = edgefit.fit_file(device, out_root)
    io.write_json(path, data)
    io.write_json(out_root / PROVENANCE_NAME, provenance(images={}, generator=EDGE_MAIN))
    return path


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=f"python -m {EDGE_MAIN}", description=__doc__.split("\n")[0])
    ap.add_argument("--device", choices=process.DEVICES, required=True)
    ap.add_argument("--out", type=Path, required=True, help="tree root: results/tcad/edgefit")
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    try:
        path = run(a.device, a.out)
    except (DirtyCheckout, FileNotFoundError, ValueError) as e:
        print(f"edge fit: {e}", file=sys.stderr)
        return 2
    print(f"{a.device}: wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
