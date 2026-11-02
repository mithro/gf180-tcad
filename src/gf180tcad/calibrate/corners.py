# SPDX-License-Identifier: Apache-2.0
"""Corner fits of the three 1D tunables: their lower and upper bounds over the SPICE corners
(design spec §5.3,
:repo:`Task 16a <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-16-corner-bounds-and-spread-of-the-1d-mos-capacitor-inputs-spec-53-issue-57>`).

**What is fitted.** For each device and each corner ``ff``, ``ss``, ``fs`` and ``sf``
(:data:`FIT_CORNERS`), the same three tunables as the typical fit (``t_ox_eff_nm``,
``n_ch_cm3``, ``dv_fb_v``), at the same calibration geometries, with the same residuals
(:func:`gf180tcad.calibrate.cv.compare`) and optimiser settings (:data:`~gf180tcad.calibrate.cv.LSQ`),
against that corner's ngspice ``cv`` sweeps. The typical corner is the committed Task 12 fit,
read from :repo:`results/tcad/calibration` and never refitted here.

**The corner values.** :repo:`data/pdk_corners.json` holds each corner's values from the pinned
:term:`card` ``sm141064.ngspice`` (its sha256 is :data:`PDK_CORNERS_SHA256`, so a change to the table changes
this module and its generator hash). It also records every bin of each model with its length
and width range: the nfet's L = 0.6 µm calibration gate is in ``nfet_06v0.1``, whose lines for
the applied inputs are those of ``nfet_06v0.0`` (tested). A corner fit applies the corner's XL, XW, overlap factors
and the BSIM4 default CF of its TOXE to the area and overlap bookkeeping as fixed inputs
(:func:`corner_bookkeeping`, :func:`with_corner_card`). It moves the oxide bounds and start by
the corner's TOXE offset and the flat-band bounds and start by its VTH0 offset, in true-sign
gate bias for both devices (:func:`corner_bounds`). The doping bounds stay as at TT. The TT
oxide upper bound is TOXP plus the charge-centroid allowance Δ (:mod:`gf180tcad.tcad.process`);
a corner fit moves that bound by the TOXE offset and keeps the TT Δ, not recomputed at the
corner's TOXP and VTH0.

**Guards** (:class:`~gf180tcad.calibrate.cv.CalibrationLeak`, anti-goal A1): the typical
corner, a validation geometry, a target that is not the corner's own ngspice ``cv`` sweep, and
an output path under ``results/`` outside ``results/tcad/corners`` are refused.

**The summary** (:func:`summary`): per tunable the typical value, the value at each corner, the
lowest and highest with their corners, the spread, and the card's shift beside the fit's.
A lowest or highest value on a bound of its fit is reported as that bound.

``python -m gf180tcad.calibrate.corners run --device D --corner C --out ROOT`` runs the fit as
one sandbox job (``corner-job``, one CPU and 2 GiB) in the 1D results image and writes
``ROOT/<device>/<corner>.json`` and ``ROOT/provenance.json``; ``summary --device D --out ROOT``
writes ``ROOT/<device>/summary.json`` on the host.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

from gf180tcad import io, sandbox
from gf180tcad.calibrate import cv
from gf180tcad.devices import CORNERS, DEVICES, Geometry, geometry_id
from gf180tcad.layout import PROVENANCE_NAME
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.tcad import (
    RESULTS_IMAGE,
    calibration,
    gplugins_commit,
    image_ref,
    meshconv,
    process,
    tree_provenance,
)

#: This entry point, as the generator registry names it.
CORNERS_MAIN = "gf180tcad.calibrate.corners"

#: The corner table, ``data/pdk_corners.json``.
PDK_CORNERS_FILE = REPO_ROOT / "data" / "pdk_corners.json"
#: The table's sha256; a change to the table must change this line.
PDK_CORNERS_SHA256 = "89e24e774af5b828d1801a33198d4f95b44ac87ae38f65c8f0bbfab77dc39b96"

#: The tree root of the corner fits, ``results/tcad/corners``.
CORNERS_ROOT = REPO_ROOT / "results" / "tcad" / "corners"
#: ``results/``: nothing in it but :data:`CORNERS_ROOT` is written.
RESULTS_ROOT = REPO_ROOT / "results"

#: The corners fitted here; typical is the Task 12 fit.
FIT_CORNERS = tuple(c for c in CORNERS if c != cv.TT)

#: Schema of the summary file.
SCHEMA = 1
#: File name of a device's summary, ``<device>/summary.json``.
SUMMARY_NAME = "summary.json"
#: Memory of one corner job (one 1D sweep at a time).
JOB_MEM = "2g"
#: CPUs of one corner job.
JOB_CPUS = 1
#: The image of the corner jobs: the 1D results image.
IMAGE = RESULTS_IMAGE["moscap1d"]
#: The progress log a corner job appends one line per evaluation to.
PROGRESS_NAME = "progress.log"

# Card keys applied to the bookkeeping, by process parameter; kind from the table.
_BOOK = {
    "xl_nm": "xl",
    "xw_nm": "xw",
    "cgso_f_per_m": "cgso",
    "cgdo_f_per_m": "cgdo",
    "cgsl_f_per_m": "cgsl",
    "cgdl_f_per_m": "cgdl",
}
# The card key whose shift moves each tunable (None: unchanged).
_SHIFT_KEY = {"t_ox_eff_nm": "toxe", "n_ch_cm3": None, "dv_fb_v": "vth0"}
# Card units to the tunable's unit.
_SHIFT_SCALE = {"toxe": 1e9, "vth0": 1.0}


# --- the corner table --------------------------------------------------------------------------


def load_table(path: Path | None = None) -> dict:
    """:repo:`data/pdk_corners.json`; ValueError unless its sha256 is :data:`PDK_CORNERS_SHA256`."""
    path = Path(path) if path is not None else PDK_CORNERS_FILE
    data = path.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != PDK_CORNERS_SHA256:
        raise ValueError(f"{path}: sha256 {got}, expected {PDK_CORNERS_SHA256}")
    return json.loads(data)


def _check_corner(corner: str) -> None:
    if corner == cv.TT:
        raise cv.CalibrationLeak("the typical corner is the Task 12 fit; it is never refitted")
    if corner not in FIT_CORNERS:
        raise ValueError(f"unknown corner {corner!r}; one of {FIT_CORNERS}")


def card_shift(device: str, corner: str, key: str) -> float:
    """The corner's offset (card units) or factor of the card key ``key`` of ``device``."""
    d = load_table()["devices"][device]
    row = d["inputs"][key]
    return float(d["corners"][corner][row["param"]]["value"])


def _kind(device: str, key: str) -> str:
    return load_table()["devices"][device]["inputs"][key]["kind"]


def corner_bookkeeping(device: str, corner: str) -> dict[str, float]:
    """The corner's area and overlap bookkeeping values: ``xl_nm``, ``xw_nm`` (card value plus
    offset), ``cgso/cgdo/cgsl/cgdl_f_per_m`` (card value times factor) and ``cf_f_per_m`` (the
    BSIM4 default CF of the corner's TOXE). At ``typical`` they are the :term:`process file`'s values."""
    proc = process.load(device)
    v = proc.values()
    out = {}
    for name, key in _BOOK.items():
        p = proc.params[name]
        s = card_shift(device, corner, key)
        if _kind(device, key) == "offset":
            out[name] = (v[name] / p.card_scale + s) * p.card_scale if s else v[name]
        else:
            out[name] = v[name] * s if s != 1.0 else v[name]
    dtox = card_shift(device, corner, "toxe")
    card = proc.card_values()
    out["cf_f_per_m"] = (
        process.cf_default_f_per_m({**card, "toxe": card["toxe"] + dtox})
        if dtox
        else v["cf_f_per_m"]
    )
    return out


def tunable_shifts(device: str, corner: str) -> dict[str, float]:
    """How far the corner moves each tunable's start and bounds: the TOXE offset (nm) for the
    oxide, the VTH0 offset (V, true-sign gate bias) for the :term:`flat band`, 0 for the doping."""
    return {
        n: card_shift(device, corner, k) * _SHIFT_SCALE[k] if k else 0.0
        for n, k in _SHIFT_KEY.items()
    }


def corner_bounds(device: str, corner: str) -> dict[str, tuple[float, float]]:
    """The TT bounds of the tunables, each moved by :func:`tunable_shifts`."""
    _check_corner(corner)
    proc = process.load(device)
    s = tunable_shifts(device, corner)
    return {n: tuple(b + s[n] for b in proc.params[n].bounds) for n in process.TUNABLES}


def with_corner_card(
    proc: process.ProcessDescription, mapping: Mapping[str, float]
) -> process.ProcessDescription:
    """A copy of ``proc`` with ``reference-bookkeeping`` parameters replaced; KeyError for an
    unknown name and ValueError for any other role (tunables go through ``with_values``)."""
    params = dict(proc.params)
    for name, value in mapping.items():
        if name not in params:
            raise KeyError(f"{proc.device}: no parameter {name!r}")
        p = params[name]
        if p.role != "reference-bookkeeping":
            raise ValueError(
                f"{proc.device}: {name} has role {p.role!r}; a corner card replaces "
                "reference-bookkeeping parameters only"
            )
        params[name] = replace(p, value=float(value))
    return replace(proc, params=MappingProxyType(params))


def corner_process(device: str, corner: str) -> process.ProcessDescription:
    """The process description of a corner fit: the corner's bookkeeping, and each tunable's
    start and bounds moved by :func:`tunable_shifts`."""
    bounds = corner_bounds(device, corner)
    s = tunable_shifts(device, corner)
    proc = with_corner_card(process.load(device), corner_bookkeeping(device, corner))
    params = dict(proc.params)
    for n in process.TUNABLES:
        p = params[n]
        params[n] = replace(p, value=p.value + s[n], bounds=bounds[n])
    return replace(proc, params=MappingProxyType(params))


# --- targets and guards ------------------------------------------------------------------------


def load_corner_target(
    device: str, geometry: Geometry, corner: str, root: Path | None = None
) -> cv.Target:
    """The ``corner`` curve of ``geometry`` as the target, with all five corners beside it."""
    gid = geometry_id(geometry)
    curves = {c: cv.load_curve(device, gid, c, root) for c in CORNERS}
    return cv.Target(geometry, curves[corner], MappingProxyType(curves))


def check_corner_target(device: str, corner: str, target: cv.Target) -> None:
    """CalibrationLeak unless ``target`` is the ngspice cv sweep of ``corner`` at its geometry,
    with the five corners of the same sweep beside it."""
    gid = geometry_id(target.geometry)
    want = {"engine": cv.ENGINE, "corner": corner, "sweep": cv.SWEEP, "device": device,
            "geometry_id": gid}  # fmt: skip
    got = {k: target.tt.meta.get(k) for k in want}
    if got != want:
        raise cv.CalibrationLeak(f"{device} {gid}: the target must be {want}, got {got}")
    if set(target.corners) != set(CORNERS) or target.corners[corner] != target.tt:
        raise cv.CalibrationLeak(f"{device} {gid}: the corners are not the five of the sweep")
    for c, curve in target.corners.items():
        if {k: curve.meta.get(k) for k in want} != {**want, "corner": c}:
            raise cv.CalibrationLeak(f"{device} {gid}: corner {c!r} is another sweep")
        if curve.vg != target.tt.vg:
            raise ValueError(f"{device} {gid}: corner {c!r} has another vg grid")


def check_out(out: Path) -> None:
    """CalibrationLeak for a path under ``results/`` that is not under ``results/tcad/corners``
    (a scratch directory elsewhere is allowed)."""
    p = Path(out).resolve()
    results, root = RESULTS_ROOT.resolve(), CORNERS_ROOT.resolve()
    inside = p == results or results in p.parents
    if inside and not (p == root or root in p.parents):
        raise cv.CalibrationLeak(
            f"{out}: corner fits write only under results/tcad/corners, never elsewhere in results/"
        )


# --- the fit -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class CornerFit:
    """One corner fit: the fit as a :class:`~gf180tcad.calibrate.cv.CalibrationResult`, the
    corner, its card inputs and the held-out comparisons."""

    corner: str
    result: cv.CalibrationResult
    bookkeeping: dict[str, float]
    shifts: dict[str, float]
    held_out: dict[str, dict]

    def to_dict(self) -> dict:
        d = self.result.to_dict()
        d["reference"] = {"corner": self.corner, "engine": cv.ENGINE, "sweep": cv.SWEEP}
        d["corner"] = {
            "bookkeeping": dict(self.bookkeeping),
            "name": self.corner,
            "pdk_corners_sha256": PDK_CORNERS_SHA256,
            "tunable_shifts": dict(self.shifts),
        }
        d["held_out"] = self.held_out
        return d

    def write(self, out: Path) -> Path:
        """Write ``out/<device>/<corner>.json``; CalibrationLeak for a path :func:`check_out`
        refuses."""
        check_out(out)
        path = Path(out) / self.result.device / f"{self.corner}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        io.write_json(path, self.to_dict())
        return path


#: A 1D simulator: the process description and the gate biases to a C-V.
Simulate = Callable[[process.ProcessDescription, Sequence[float]], object]


def calibrate_corner(
    device: str,
    corner: str,
    *,
    geometries: Sequence[Geometry],
    params: Sequence[str] = process.TUNABLES,
    targets: Mapping[str, cv.Target] | None = None,
    held_out: Mapping[str, cv.Target] | None = None,
    simulate: Simulate | None = None,
    log: Callable[[str], None] | None = None,
) -> CornerFit:
    """Fit ``params`` of ``device`` to the ``corner`` ngspice Cgg-Vg of the calibration
    ``geometries`` with the corner's card (:func:`corner_process`), then compare the fitted 1D
    C-V with the corner curves of the held-out geometries.

    ``targets`` and ``held_out`` (geometry id to target) default to the committed SPICE
    reference; ``simulate`` to the 1D DEVSIM MOS capacitor. Everything is checked before any
    simulation.
    """
    from scipy.optimize import least_squares

    _check_corner(corner)
    cv._check_geometries(device, geometries)
    proc = corner_process(device, corner)
    cv._check_params(proc, params)
    params = tuple(params)
    if targets is None:
        targets = {geometry_id(g): load_corner_target(device, g, corner) for g in geometries}
    chosen = []
    for g in geometries:
        t = targets.get(geometry_id(g))
        if t is None:
            raise ValueError(f"{device}: no target for {geometry_id(g)}")
        if t.geometry != g:
            raise cv.CalibrationLeak(f"{device}: the target of {geometry_id(g)} is {t.geometry}")
        check_corner_target(device, corner, t)
        chosen.append(t)
    vg = chosen[0].tt.vg
    if any(t.tt.vg != vg for t in chosen):
        raise ValueError(f"{device}: the targets' vg grids differ")
    val = tuple(g for g in DEVICES[device].geometries if g.role == "validation")
    if held_out is None:
        held_out = {geometry_id(g): load_corner_target(device, g, corner) for g in val}
    if set(held_out) != {geometry_id(g) for g in val}:
        raise ValueError(f"{device}: held-out targets {sorted(held_out)}, expected {val}")
    for gid, t in held_out.items():
        if geometry_id(t.geometry) != gid or t.geometry.role != "validation":
            raise cv.CalibrationLeak(f"{device}: the held-out target of {gid} is {t.geometry}")
        check_corner_target(device, corner, t)
        if t.tt.vg != vg:
            raise ValueError(f"{device} {gid}: the held-out vg grid differs")
    cox = cv.cox_spec(device)
    simulate = simulate if simulate is not None else cv.devsim_simulator(device)
    start = {n: proc.params[n].value for n in process.TUNABLES}
    bounds = {n: tuple(proc.params[n].bounds) for n in process.TUNABLES}
    lo = [bounds[n][0] for n in params]
    hi = [bounds[n][1] for n in params]
    count = [0]

    def values_of(x) -> dict[str, float]:
        clipped = [min(max(float(v), a), b) for v, a, b in zip(x, lo, hi, strict=True)]
        return {**start, **dict(zip(params, clipped, strict=True))}

    def evaluate(values):
        p = proc.with_values(values)
        m = simulate(p, vg)
        comps, res = {}, []
        for t in chosen:
            comp, r = cv._compare_1d(p, m, t, cox)
            comps[geometry_id(t.geometry)] = comp
            res += r
        return p, m, comps, res

    def fun(x):
        values = values_of(x)
        _, _, _, res = evaluate(values)
        count[0] += 1
        if log is not None:
            cost = 0.5 * math.fsum(r * r for r in res)
            log(f"evaluation {count[0]}: {json.dumps(values, sort_keys=True)} cost {cost!r}")
        return res

    fit = least_squares(
        fun,
        [start[n] for n in params],
        bounds=(lo, hi),
        x_scale=[b - a for a, b in zip(lo, hi, strict=True)],
        **cv.LSQ,
    )
    values = values_of(fit.x)
    p, m, comps, res = evaluate(values)
    hits = {}
    for n, a, b in zip(params, lo, hi, strict=True):
        tol = cv.BOUND_HIT_REL * (b - a)
        if abs(values[n] - a) <= tol:
            hits[n] = "lower"
        elif abs(values[n] - b) <= tol:
            hits[n] = "upper"
    optimiser = {
        **dict(cv.LSQ),
        "cost": 0.5 * math.fsum(r * r for r in res),
        "message": str(fit.message),
        "nfev": int(fit.nfev),
        "njev": int(fit.njev) if fit.njev is not None else None,
        "optimality": float(fit.optimality),
        "residuals": len(res),
        "status": int(fit.status),
        "x0": [start[n] for n in params],
        "x_scale": [b - a for a, b in zip(lo, hi, strict=True)],
    }
    result = cv.CalibrationResult(
        device=device,
        params=params,
        values=values,
        start=start,
        bounds=bounds,
        bound_hits=hits,
        budget_used=len(params),
        budget=cv.BUDGET,
        geometries=tuple(c["geometry"] for c in comps.values()),
        optimiser=optimiser,
        per_geometry=comps,
        verdict=cv.worst(c["verdict"] for c in comps.values()),
        cox_check=cv._cox_check(p, m, cox),
        model=cv._model_dict(m),
        param_sha256=calibration.param_sha256(values),
    )
    held = {}
    for gid, t in sorted(held_out.items()):
        comp, _ = cv._compare_1d(p, m, t, cox)
        held[gid] = {**comp, "causes": cv.causes(device, t.geometry)}
    return CornerFit(
        corner, result, corner_bookkeeping(device, corner), tunable_shifts(device, corner), held
    )


# --- the summary -------------------------------------------------------------------------------


def _extreme(values: Mapping[str, float], pick) -> str:
    """The corner (first in :data:`CORNERS` order on a tie) of the lowest or highest value."""
    best = pick(values[c] for c in CORNERS)
    return next(c for c in CORNERS if values[c] == best)


def summary(device: str, root: Path | None = None, calibration_root: Path | None = None) -> dict:
    """The corner bounds of ``device``'s tunables from the corner fits under ``root`` (default
    :data:`CORNERS_ROOT`) and the committed typical fit (``calibration_root``).

    Per tunable: ``typical``, ``values`` per corner, ``min``/``max`` with ``min_corner``/
    ``max_corner`` and ``min_at_bound``/``max_at_bound`` (``"lower"``, ``"upper"`` or None; a
    value on a bound is reported as that bound), ``spread`` (max - min), and, for the oxide and
    the flat band, the card's shift (``card_shift``), the fit's (``tcad_shift``, value minus
    typical) and ``shift_difference`` per corner. Per corner: the verdicts. ValueError for a
    corner file of another device, corner or corner table.
    """
    root = Path(root) if root is not None else CORNERS_ROOT
    tt = cv.load_frozen(device, calibration_root)
    fits = {}
    for c in FIT_CORNERS:
        path = root / device / f"{c}.json"
        d = json.loads(path.read_bytes())
        if d.get("device") != device or d.get("reference", {}).get("corner") != c:
            raise ValueError(f"{path}: not the {c} fit of {device}")
        if d.get("corner", {}).get("pdk_corners_sha256") != PDK_CORNERS_SHA256:
            raise ValueError(f"{path}: made with another data/pdk_corners.json")
        fits[c] = d
    bounds = {cv.TT: {n: tuple(b) for n, b in tt.bounds.items()}}
    hits = {cv.TT: dict(tt.bound_hits)}
    values = {cv.TT: dict(tt.values)}
    for c, d in fits.items():
        bounds[c] = {n: tuple(b) for n, b in d["bounds"].items()}
        hits[c] = dict(d["bound_hits"])
        values[c] = dict(d["values"])
    tunables = {}
    for n in process.TUNABLES:
        per = {c: values[c][n] for c in CORNERS}
        row: dict = {"typical": per[cv.TT], "values": per}
        for side, pick in (("min", min), ("max", max)):
            c = _extreme(per, pick)
            hit = hits[c].get(n)
            v = per[c]
            if hit is not None:
                v = bounds[c][n][0 if hit == "lower" else 1]
            row[side], row[f"{side}_corner"], row[f"{side}_at_bound"] = v, c, hit
        row["spread"] = row["max"] - row["min"]
        key = _SHIFT_KEY[n]
        if key is None:
            row["card_shift"] = row["tcad_shift"] = row["shift_difference"] = None
        else:
            card = {c: card_shift(device, c, key) * _SHIFT_SCALE[key] for c in FIT_CORNERS}
            tcad = {c: per[c] - per[cv.TT] for c in FIT_CORNERS}
            row["card_shift"], row["tcad_shift"] = card, tcad
            row["shift_difference"] = {c: tcad[c] - card[c] for c in FIT_CORNERS}
        tunables[n] = row
    corners_out = {
        cv.TT: {
            "bound_hits": hits[cv.TT],
            "per_geometry": {g: c["verdict"] for g, c in tt.per_geometry.items()},
            "verdict": tt.verdict,
        }
    }
    for c, d in fits.items():
        corners_out[c] = {
            "bound_hits": hits[c],
            "held_out": {g: x["verdict"] for g, x in d["held_out"].items()},
            "per_geometry": {g: x["verdict"] for g, x in d["per_geometry"].items()},
            "verdict": d["verdict"],
        }
    return {
        "corners": corners_out,
        "device": device,
        "pdk_corners_sha256": PDK_CORNERS_SHA256,
        "schema": SCHEMA,
        "tunables": tunables,
        "typical_source": {
            "calibration_file_sha256": calibration.sha256_file(tt.source),
            "param_sha256": tt.param_sha256,
        },
    }


# --- the command line ----------------------------------------------------------------------------


class _Progress:
    def __init__(self, out: Path, prefix: str) -> None:
        self.path = Path(out) / PROGRESS_NAME
        self.prefix = prefix

    def __call__(self, line: str) -> None:
        text = f"{self.prefix}: {line}"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
        print(text, flush=True)


def _write_atomic(path: Path, obj) -> None:
    """:func:`gf180tcad.io.write_json` through a temporary file and a rename, so parallel
    ``run`` invocations never leave a half-written provenance.json."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}")
    io.write_json(tmp, obj)
    os.replace(tmp, path)


def run_job(device: str, corner: str, out: Path) -> None:
    """``corner-job``: the fit inside the sandbox; writes ``out/<device>/<corner>.json``."""
    if not sandbox.in_sandbox():
        raise RuntimeError("corner-job must run inside the sandbox (see tools/sandbox-run)")
    geoms = tuple(g for g in DEVICES[device].geometries if g.role == "calibration")
    res = calibrate_corner(device, corner, geometries=geoms,
                           log=_Progress(out, f"{device} {corner}"))  # fmt: skip
    res.write(Path(out))
    r = res.result
    hits = ", ".join(f"{k} at the {v} bound" for k, v in r.bound_hits.items()) or "no bound hit"
    print(f"{device} {corner}: {r.values} ({hits}); verdict {r.verdict}", flush=True)


def _sandbox_job(cmd: list[str], scratch: Path, what: str) -> str:
    try:
        res = sandbox.run(cmd, out_dir=scratch, image=image_ref(IMAGE), mem=JOB_MEM, cpus=JOB_CPUS)
    except sandbox.SandboxError as e:
        log = scratch / "job.log"
        log.write_text(f"{e.result.stdout or ''}\n{e.result.stderr or ''}", encoding="utf-8")
        raise RuntimeError(f"{what} failed (exit {e.result.returncode}); log: {log}") from e
    (scratch / "job.log").write_text(f"{res.stdout or ''}\n{res.stderr or ''}", encoding="utf-8")
    return res.stdout


def _provenance(root: Path) -> None:
    _write_atomic(
        root / PROVENANCE_NAME, tree_provenance(root, {"moscap1d": IMAGE}, generator=CORNERS_MAIN)
    )


def run_host(device: str, corner: str, root: Path) -> None:
    """``run``: ``corner-job`` in the 1D results image, then the corner file and the tree's
    provenance under ``root``."""
    _check_corner(corner)
    check_out(root)
    meshconv.selected_spec(device, 1)  # refuses a missing mesh-convergence result
    gplugins_commit()  # refuses a dirty or unpinned plugin before anything runs
    root = Path(root)
    scratch = Path(tempfile.mkdtemp(prefix=f"gf180tcad-corner-{device}-{corner}-"))
    print(f"{device} {corner}: progress in {scratch / PROGRESS_NAME}", flush=True)
    cmd = ["python3", "-m", CORNERS_MAIN, "corner-job", "--device", device, "--corner", corner,
           "--out", "/work/out"]  # fmt: skip
    stdout = _sandbox_job(cmd, scratch, "corner-job")
    lines = [ln for ln in stdout.splitlines() if ln.startswith(f"{device} {corner}: ")]
    print(lines[-1] if lines else f"{device} {corner}: done", flush=True)
    (root / device).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(scratch / device / f"{corner}.json", root / device / f"{corner}.json")
    _provenance(root)
    shutil.rmtree(scratch)


def summary_host(device: str, root: Path) -> None:
    """``summary``: ``root/<device>/summary.json`` from the corner files, and the provenance."""
    check_out(root)
    root = Path(root)
    io.write_json(root / device / SUMMARY_NAME, summary(device, root))
    _provenance(root)
    print(f"{device}: wrote {root / device / SUMMARY_NAME}", flush=True)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=f"python -m {CORNERS_MAIN}")
    sub = ap.add_subparsers(dest="command", required=True)
    for name, help_ in (
        ("run", "fit the 1D MOS capacitor to one corner's ngspice Cgg-Vg (host: runs corner-job)"),
        ("corner-job", "internal: the fit, inside the sandbox"),
    ):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--device", choices=process.DEVICES, required=True)
        p.add_argument("--corner", choices=FIT_CORNERS, required=True)
        p.add_argument("--out", type=Path, required=True, help="tree root: results/tcad/corners")
    p = sub.add_parser("summary", help="the corner bounds of one device from its corner files")
    p.add_argument("--device", choices=process.DEVICES, required=True)
    p.add_argument("--out", type=Path, required=True, help="tree root: results/tcad/corners")
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    try:
        if a.command == "run":
            run_host(a.device, a.corner, a.out)
        elif a.command == "corner-job":
            run_job(a.device, a.corner, a.out)
        else:
            summary_host(a.device, a.out)
    except (cv.CalibrationLeak, FileNotFoundError, ValueError) as e:
        print(f"{a.command}: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
