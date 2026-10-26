# SPDX-License-Identifier: Apache-2.0
"""Calibrate the 1D :term:`TCAD` :term:`MOS capacitor <MOSCAP>` against the :term:`SPICE`
:term:`Cgg`–Vg, and validate the frozen result
(:repo:`Task 12 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-12-calibrate-against-spice-cggvg>`).

**What is fitted.** The three tunables of the process file (:data:`gf180tcad.tcad.process.TUNABLES`:
``t_ox_eff_nm``, ``n_ch_cm3``, ``dv_fb_v``), 3 of the 8-parameter budget of design spec §5.2.
Their start values and bounds come only from :func:`gf180tcad.tcad.process.load`; nothing
here redefines them, and the process files are never written. The model is the 1D MOS
capacitor (:func:`gf180tcad.tcad.moscap1d.simulate`) on the selected 1D mesh, area-scaled per
geometry with the fixed :term:`DLC` and :term:`BSIM4` overlap bookkeeping
(:meth:`gf180tcad.tcad.moscap1d.MoscapCV.area_scaled`). The targets are the :term:`TT`
ngspice ``cv`` sweeps of the three calibration geometries (W = 10 µm at L = 10, 2 µm
and :term:`Lmin`, ``role == "calibration"`` in :mod:`gf180tcad.devices`).

**Guards** (:class:`CalibrationLeak`, design spec anti-goal A1): a geometry that is not a
calibration geometry, a target that is not the TT ngspice ``cv`` sweep of its geometry, and a
parameter that is not a free tunable are refused before anything is simulated.

**The metric** (:func:`regions`, :func:`metrics`), in u = polarity · Vg with the SPICE TT curve
of each geometry defining the regions:

- u_fb: where SPICE C falls to 0.9 · C_acc, C_acc = C(u = −5 V); u_t: where SPICE C, rising
  from its minimum C_min, reaches (C_min + C_inv)/2, C_inv = C(u = +5 V);
- accumulation plateau u ≤ u_fb − 1 V, inversion plateau u ≥ u_t + 1 V: the maximum
  |ΔCgg|/Cgg_SPICE over each, ≤ 5 % (spec §5.2);
- the two mid-capacitance crossings, where C passes C_mid = (C_min + C_acc)/2 on the depletion
  side (u_dep, below the minimum) and the inversion side (u_inv, above it), linearly
  interpolated between grid points. Each curve, TCAD or SPICE, crosses its own C_mid, so the
  ΔV are shifts of the transition, not echoes of a plateau error. ΔV_dep and ΔV_inv are each
  ≤ 50 mV, a tolerance that is a proposal (no published standard exists);
- the depletion error, max |ΔC|/C for u_fb − 1 V < u < u_t + 1 V, is reported and never enters a
  verdict (the deliberate deviation from spec §5.2: :repo:`docs/comparison/cv-agreement.md`).

**Verdicts** (spec §5.1, :func:`verdicts`): Agree within the tolerance; else "Same process" when
inside the window; else Disagree. A plateau's window, at each plateau bias, is
:func:`gf180tcad.specwindow.window` of the five-corner envelope (:func:`envelope_cv`) and the
public 6 V Cox spec mapped to Cgg through the same bookkeeping (Cox_min/max times the
capacitance area, plus the parasitic term; in 2D, times the drawn area). A crossing's window is
the min-max of that crossing over the five corners (:func:`crossing_window`). A geometry's
verdict is the worst of its four.

**The fit** (:func:`calibrate_cv`): ``scipy.optimize.least_squares`` with the fixed settings
:data:`LSQ` and ``x_scale`` the bound widths, on the residuals: the plateau relative errors at
every plateau grid point plus ΔV_dep/50 mV and ΔV_inv/50 mV, at each calibration geometry.
A value within 1e-3 of a bound (relative to the bound width) is reported in ``bound_hits``.

**The files** (:meth:`CalibrationResult.write`): ``results/tcad/calibration/<device>.json`` is
the calibration file of :mod:`gf180tcad.tcad.calibration` (its schema unchanged: ``schema``,
``device``, ``values``), read by ``--params calibrated``. The full result (bounds, bound hits,
budget, residuals, regions, verdicts) is beside it in ``<device>.result.json``
(:data:`RESULT_SUFFIX`), which records the calibration file's sha256 and ``param_sha256``.
:func:`validate_cv` accepts only a result loaded from that committed pair (:func:`load_frozen`).

This module imports scipy and the plugin lazily, so it imports on the host. It is TCAD code,
not one of the SPICE generator modules (:data:`gf180tcad.reference.GENERATOR_MODULES`).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from pathlib import Path
from types import MappingProxyType

from gf180tcad import io, specwindow
from gf180tcad.devices import CORNERS, DEVICES, Geometry, geometry_id
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.tcad import CALIBRATION_DIR, calibration, meshconv, moscap1d, process
from gf180tcad.tcad.analytic import cox_f_per_cm2, f_per_cm2_to_ff_per_um2

SPICE_ROOT = REPO_ROOT / "results" / "spice"
CALIBRATION_ROOT = REPO_ROOT / CALIBRATION_DIR
VALIDATION_ROOT = REPO_ROOT / "results" / "tcad" / "validation"
MOSCAP2D_ROOT = REPO_ROOT / "results" / "tcad" / "moscap2d"
RESULT_SUFFIX = ".result.json"
SCHEMA = 1

# The reference every target must be (spec §5.2: ngspice is the only Cgg reference; Xyce has no
# cv analysis).
ENGINE, TT, SWEEP = "ngspice", "typical", "cv"

BUDGET = 8  # free parameters per device type (spec §5.2)
PLATEAU_TOL = 0.05  # max |dCgg|/Cgg over each plateau (spec §5.2)
DV_TOL_V = 0.05  # each mid-capacitance crossing (a proposal: no published standard)
PLATEAU_OFFSET_V = 1.0  # plateaus start 1 V beyond u_fb and u_t
FB_FRACTION = 0.9  # u_fb: SPICE C = 0.9 * C_acc
U_END_V = 5.0  # the grid spans u = -5..+5 V: C_acc = C(u = -5 V), C_inv = C(u = +5 V)
BOUND_HIT_REL = 1e-3  # a value this close to a bound, relative to the bound width, is a hit

# The optimiser settings, fixed (with x_scale = the bound widths and x0 = the start values).
LSQ = MappingProxyType(
    {
        "method": "trf",
        "jac": "2-point",
        "diff_step": 1e-4,
        "ftol": 1e-10,
        "xtol": 1e-10,
        "gtol": 1e-10,
        "max_nfev": 200,
    }
)

VERDICTS = ("Agree", "Same process", "Disagree")
COX_METRIC = "cox_ff_per_um2"

# Mismatch causes (spec §6) the held-out results are tagged with before any comparison: the
# narrow 1.6/0.7 device (no STI narrow-width physics in a cross-section; L = 0.7 um is the card's
# L-bin edge) and Lmin (dominated by the overlap bookkeeping and the short-L bin).
NARROW_CAUSES = ("geometry-2d", "spice-fit")
LMIN_CAUSES = ("spice-fit",)


class CalibrationLeak(ValueError):
    """A calibration input that would leak validation data or tune a fixed parameter."""


class NotFrozen(CalibrationLeak):
    """A calibration result that is not the committed, hash-matching calibration file."""


# --- the SPICE reference ----------------------------------------------------------------------


@dataclass(frozen=True)
class Curve:
    """One SPICE Cgg-Vg curve: gate bias (V, true sign, file order) and Cgg (fF), with the
    ``# key: value`` header of its ``cv.csv``."""

    vg: tuple[float, ...]
    cgg_ff: tuple[float, ...]
    meta: Mapping[str, str]


@dataclass(frozen=True)
class Target:
    """The TT curve of one geometry (the target) and its five corners (the windows)."""

    geometry: Geometry
    tt: Curve
    corners: Mapping[str, Curve]


def load_curve(
    device: str, gid: str, corner: str = TT, root: Path | None = None, engine: str = ENGINE
) -> Curve:
    """The committed ``<engine>/<corner>/<device>/<gid>/cv.csv`` under ``root`` as a Curve.

    Read bit-exactly with :func:`gf180tcad.io.read_csv`; Cgg is converted from F to fF.
    """
    path = Path(root or SPICE_ROOT) / engine / corner / device / gid / "cv.csv"
    cols, meta = io.read_csv(path)
    if meta.get("units") != "vg=V cgg=F":
        raise ValueError(f"{path}: units {meta.get('units')!r}, expected 'vg=V cgg=F'")
    vg = tuple(float(v) for v in cols["vg"])
    cgg = tuple(float(c) * 1e15 for c in cols["cgg"])
    return Curve(vg, cgg, MappingProxyType(dict(meta)))


def load_target(device: str, geometry: Geometry, root: Path | None = None) -> Target:
    """The TT target and the five corners of ``geometry`` from the committed SPICE reference."""
    gid = geometry_id(geometry)
    corners = {c: load_curve(device, gid, c, root) for c in CORNERS}
    return Target(geometry, corners[TT], MappingProxyType(corners))


def envelope_of(curves: Mapping[str, Curve]) -> tuple[tuple[float, ...], tuple, tuple]:
    """``(vg, lo, hi)``: the per-bias min and max of Cgg (fF) over ``curves``.

    Pure min/max selection; every curve must have the identical ``vg`` grid.
    """
    if not curves:
        raise ValueError("no curves")
    first = next(iter(curves.values()))
    for name, c in curves.items():
        if c.vg != first.vg:
            raise ValueError(f"corner {name!r}: its vg grid differs")
    cols = list(zip(*(c.cgg_ff for c in curves.values()), strict=True))
    return first.vg, tuple(min(x) for x in cols), tuple(max(x) for x in cols)


def envelope_cv(device: str, gid: str, root: Path | None = None) -> tuple[tuple, tuple, tuple]:
    """``(vg, lo, hi)``: the five-corner Cgg envelope (fF) of ``device`` at geometry ``gid``,
    from each corner's ``results/spice/ngspice/<corner>/<device>/<gid>/cv.csv``."""
    return envelope_of({c: load_curve(device, gid, c, root) for c in CORNERS})


def check_target(device: str, target: Target) -> None:
    """Raise :class:`CalibrationLeak` unless ``target`` is the TT ngspice cv sweep of its
    geometry, and ValueError unless its corners are the five corners of the same sweep."""
    gid = geometry_id(target.geometry)
    want = {"engine": ENGINE, "corner": TT, "sweep": SWEEP, "device": device, "geometry_id": gid}
    got = {k: target.tt.meta.get(k) for k in want}
    if got != want:
        raise CalibrationLeak(f"{device} {gid}: the target must be {want}, got {got}")
    if set(target.corners) != set(CORNERS):
        raise ValueError(f"{device} {gid}: corners {sorted(target.corners)}, expected {CORNERS}")
    for corner, c in target.corners.items():
        meta = {k: c.meta.get(k) for k in want}
        if meta != {**want, "corner": corner}:
            raise ValueError(f"{device} {gid}: corner {corner!r} is {meta}")
        if c.vg != target.tt.vg:
            raise ValueError(f"{device} {gid}: corner {corner!r} has another vg grid")
    if target.corners[TT] != target.tt:
        raise ValueError(f"{device} {gid}: the typical corner is not the target")


# --- the metric -------------------------------------------------------------------------------


def _crossing(u: Sequence[float], c: Sequence[float], level: float, i0: int, step: int) -> float:
    """The u where ``c`` first passes ``level`` walking from index ``i0`` by ``step``.

    Linearly interpolated between the two grid points either side of the crossing. Raises
    ValueError if the curve never crosses.
    """
    above = c[i0] >= level
    k = i0 + step
    while 0 <= k < len(u):
        if (c[k] >= level) != above:
            a, b = k - step, k
            t = (level - c[a]) / (c[b] - c[a])
            return u[a] + t * (u[b] - u[a])
        k += step
    raise ValueError(f"the curve never crosses C = {level!r} from index {i0} (step {step})")


def _argmin(c: Sequence[float]) -> int:
    return min(range(len(c)), key=c.__getitem__)


@dataclass(frozen=True)
class Regions:
    """The regions of a C-V curve (u in V, C in fF): see the module docstring."""

    u_fb: float
    u_t: float
    u_min: float
    c_acc: float
    c_min: float
    c_inv: float
    c_mid: float
    u_dep: float
    u_inv: float


def _check_u(u: Sequence[float]) -> None:
    if any(not a < b for a, b in pairwise(u)):
        raise ValueError("u must be strictly increasing")


def _check_ends(u: Sequence[float]) -> None:
    """Raise ValueError unless the ascending grid ``u`` runs from -:data:`U_END_V` to
    +:data:`U_END_V`: C_acc and C_inv are read at its two ends."""
    if not u or not (
        math.isclose(u[0], -U_END_V, abs_tol=1e-9) and math.isclose(u[-1], U_END_V, abs_tol=1e-9)
    ):
        span = f"{u[0]!r}..{u[-1]!r} V" if u else "empty"
        raise ValueError(
            f"the grid must span u = -{U_END_V:g}..+{U_END_V:g} V (C_acc and C_inv are read at its "
            f"ends), got {span}"
        )


def crossings(u: Sequence[float], c: Sequence[float]) -> tuple[float, float]:
    """``(u_dep, u_inv)``: where ``c`` (u ascending) passes its own (C_min + C_acc)/2 below and
    above its minimum (C_acc = C at u = -5 V, the grid's first point)."""
    _check_u(u)
    _check_ends(u)
    i = _argmin(c)
    mid = (c[i] + c[0]) / 2
    return _crossing(u, c, mid, i, -1), _crossing(u, c, mid, i, +1)


def regions(u: Sequence[float], c: Sequence[float]) -> Regions:
    """The :class:`Regions` of the SPICE curve ``c`` on the ascending grid ``u``, which must run
    from u = -5 V (C_acc) to u = +5 V (C_inv); else ValueError."""
    _check_u(u)
    _check_ends(u)
    i = _argmin(c)
    c_acc, c_min, c_inv = c[0], c[i], c[-1]
    u_dep, u_inv = crossings(u, c)
    return Regions(
        u_fb=_crossing(u, c, FB_FRACTION * c_acc, 0, +1),
        u_t=_crossing(u, c, (c_min + c_inv) / 2, i, +1),
        u_min=u[i],
        c_acc=c_acc,
        c_min=c_min,
        c_inv=c_inv,
        c_mid=(c_min + c_acc) / 2,
        u_dep=u_dep,
        u_inv=u_inv,
    )


@dataclass(frozen=True)
class Metrics:
    """The comparison of one TCAD curve with its SPICE target (u ascending)."""

    acc_u: tuple[float, ...]
    inv_u: tuple[float, ...]
    plateau_acc_max_rel: float
    plateau_inv_max_rel: float
    dv_dep_v: float
    dv_inv_v: float
    depletion_max_rel: float
    u_dep_tcad: float
    u_inv_tcad: float
    acc_index: tuple[int, ...] = ()
    inv_index: tuple[int, ...] = ()
    acc_rel: tuple[float, ...] = ()
    inv_rel: tuple[float, ...] = ()

    def residuals(self) -> list[float]:
        """The least-squares residuals of this geometry."""
        return [*self.acc_rel, *self.inv_rel, self.dv_dep_v / DV_TOL_V, self.dv_inv_v / DV_TOL_V]


def metrics(
    u: Sequence[float], c_tcad: Sequence[float], c_spice: Sequence[float], r: Regions | None = None
) -> Metrics:
    """Plateau errors, both crossing shifts and the depletion error of ``c_tcad`` against
    ``c_spice`` on the ascending grid ``u`` (the regions ``r`` default to the SPICE curve's)."""
    r = r if r is not None else regions(u, c_spice)
    rel = [(t - s) / s for t, s in zip(c_tcad, c_spice, strict=True)]
    acc = tuple(i for i, x in enumerate(u) if x <= r.u_fb - PLATEAU_OFFSET_V)
    inv = tuple(i for i, x in enumerate(u) if x >= r.u_t + PLATEAU_OFFSET_V)
    dep = [i for i, x in enumerate(u) if r.u_fb - PLATEAU_OFFSET_V < x < r.u_t + PLATEAU_OFFSET_V]
    if not acc or not inv:
        raise ValueError(f"an empty plateau: {len(acc)} accumulation, {len(inv)} inversion points")
    u_dep, u_inv = crossings(u, c_tcad)
    return Metrics(
        acc_u=tuple(u[i] for i in acc),
        inv_u=tuple(u[i] for i in inv),
        plateau_acc_max_rel=max(abs(rel[i]) for i in acc),
        plateau_inv_max_rel=max(abs(rel[i]) for i in inv),
        dv_dep_v=u_dep - r.u_dep,
        dv_inv_v=u_inv - r.u_inv,
        depletion_max_rel=max((abs(rel[i]) for i in dep), default=0.0),
        u_dep_tcad=u_dep,
        u_inv_tcad=u_inv,
        acc_index=acc,
        inv_index=inv,
        acc_rel=tuple(rel[i] for i in acc),
        inv_rel=tuple(rel[i] for i in inv),
    )


def _sorted_u(vg: Sequence[float], polarity: int) -> tuple[list[int], tuple[float, ...]]:
    order = sorted(range(len(vg)), key=lambda i: polarity * vg[i])
    u = tuple(polarity * vg[i] + 0.0 for i in order)
    _check_u(u)
    return order, u


def crossing_window(corners: Mapping[str, Curve], polarity: int, which: str) -> specwindow.Window:
    """The "Same process" window of crossing ``which`` (``u_dep`` or ``u_inv``): the min-max of
    that crossing over the corner curves. There is no published spec for it."""
    if which not in ("u_dep", "u_inv"):
        raise ValueError(f"which must be 'u_dep' or 'u_inv', got {which!r}")
    vals = []
    for c in corners.values():
        order, u = _sorted_u(c.vg, polarity)
        dep, inv = crossings(u, [c.cgg_ff[i] for i in order])
        vals.append(dep if which == "u_dep" else inv)
    return specwindow.Window(which, min(vals), max(vals), "envelope")


def crossing_verdict(dv_v: float, u_tcad: float, window: specwindow.Window | None) -> str:
    """Agree if |ΔV| ≤ 50 mV, else "Same process" if the TCAD crossing is in ``window``."""
    if abs(dv_v) <= DV_TOL_V:
        return "Agree"
    if window is not None and window.contains(u_tcad):
        return "Same process"
    return "Disagree"


def worst(verdicts: Iterable[str]) -> str:
    """The worst of ``verdicts`` (Agree < Same process < Disagree)."""
    return max(verdicts, key=VERDICTS.index)


def _window_dict(w: specwindow.Window) -> dict:
    return {"lo": w.lo, "hi": w.hi, "source": w.source}


def _plateau_verdict(max_rel: float, values: Sequence[float], u: Sequence[float], windows) -> dict:
    out = {"max_rel": max_rel, "tolerance": PLATEAU_TOL}
    if max_rel <= PLATEAU_TOL:
        out["verdict"] = "Agree"
    else:
        out["verdict"] = "Disagree"
    if windows is not None:
        inside = [w.contains(v) for w, v in zip(windows, values, strict=True)]
        # the point the window is tightest relative to the TCAD value
        k = max(
            range(len(windows)),
            key=lambda j: (
                max(windows[j].lo - values[j], values[j] - windows[j].hi)
                / max(abs(values[j]), 1e-300)
            ),
        )
        out["window"] = {
            "all_inside": all(inside),
            "sources": sorted({w.source for w in windows}),
            "tightest": {"u": u[k], "c_tcad": values[k], **_window_dict(windows[k])},
        }
        if out["verdict"] == "Disagree" and all(inside):
            out["verdict"] = "Same process"
    return out


def verdicts(m: Metrics, plateau_windows, crossing_windows) -> dict[str, dict]:
    """The four verdicts of one geometry: both plateaus and both crossings (never depletion).

    ``plateau_windows`` is ``{"acc": (values, windows), "inv": (values, windows)}`` (the TCAD
    Cgg and the :class:`gf180tcad.specwindow.Window` at each plateau point) and
    ``crossing_windows`` ``{"u_dep": Window, "u_inv": Window}``; either may be None (no window:
    outside the tolerance is then Disagree).
    """
    out = {}
    for name, max_rel, us in (
        ("plateau_acc", m.plateau_acc_max_rel, m.acc_u),
        ("plateau_inv", m.plateau_inv_max_rel, m.inv_u),
    ):
        key = name.removeprefix("plateau_")
        values, windows = plateau_windows[key] if plateau_windows else ((), None)
        out[name] = _plateau_verdict(max_rel, values, us, windows)
    for name, dv, u_t, which in (
        ("dv_dep", m.dv_dep_v, m.u_dep_tcad, "u_dep"),
        ("dv_inv", m.dv_inv_v, m.u_inv_tcad, "u_inv"),
    ):
        w = crossing_windows[which] if crossing_windows else None
        out[name] = {
            "dv_v": dv,
            "tolerance_v": DV_TOL_V,
            "u_tcad": u_t,
            "verdict": crossing_verdict(dv, u_t, w),
            "window": None if w is None else _window_dict(w),
        }
    return out


# --- the Cox spec (TCAD only) ------------------------------------------------------------------


def cox_spec(device: str, spec: Mapping | None = None) -> dict:
    """The public 6 V Cox spec entry of ``device`` (``per_area``, metric :data:`COX_METRIC`).

    Its values are published as positive magnitudes for both devices and are compared as
    published (:func:`gf180tcad.specwindow.spec_range` assumes negative pfet values, so it is
    not used for this entry).
    """
    spec = spec if spec is not None else specwindow.load_spec()
    found = [
        e
        for e in spec["entries"]
        if e.get("per_area") and e["device"] == device and e["metric"] == COX_METRIC
    ]
    if len(found) != 1:
        raise ValueError(f"{device}: expected one {COX_METRIC} entry, found {len(found)}")
    return found[0]


def _spec_cgg_windows(spec_lo, spec_hi, area_um2, parasitic, envelope, idx) -> list:
    """The plateau windows at the indices ``idx``: the Cox spec as Cgg (fF) hulled with the
    corner envelope."""
    lo, hi = envelope
    return [
        specwindow.window(
            "cgg_ff",
            (spec_lo * area_um2 + parasitic[i], spec_hi * area_um2 + parasitic[i]),
            (lo[i], hi[i]),
        )
        for i in idx
    ]


def compare(
    target: Target,
    vg: Sequence[float],
    c_tcad: Sequence[float],
    polarity: int,
    *,
    spec_area_um2: float | None = None,
    parasitic_ff: Sequence[float] | None = None,
    cox: Mapping | None = None,
) -> tuple[dict, list[float]]:
    """``(comparison, residuals)`` of the TCAD Cgg ``c_tcad`` (fF, at ``vg`` in the target's
    order) against ``target``.

    The plateau windows map the Cox spec ``cox`` to Cgg as Cox * ``spec_area_um2`` +
    ``parasitic_ff`` (per bias, file order); without ``cox`` the window is the envelope alone.
    """
    if tuple(vg) != target.tt.vg:
        raise ValueError(f"{geometry_id(target.geometry)}: the TCAD vg grid is not the target's")
    order, u = _sorted_u(vg, polarity)
    ct = [c_tcad[i] for i in order]
    cs = [target.tt.cgg_ff[i] for i in order]
    r = regions(u, cs)
    m = metrics(u, ct, cs, r)
    _, elo, ehi = envelope_of(target.corners)
    env = ([elo[i] for i in order], [ehi[i] for i in order])
    par = [parasitic_ff[i] for i in order] if parasitic_ff is not None else [0.0] * len(u)
    pw = {}
    for key, idx in (("acc", m.acc_index), ("inv", m.inv_index)):
        if cox is not None:
            spec = (float(cox["min"]), float(cox["max"]))
            windows = _spec_cgg_windows(*spec, spec_area_um2, par, env, idx)
        else:
            windows = [specwindow.Window("cgg_ff", env[0][i], env[1][i], "envelope") for i in idx]
        pw[key] = ([ct[i] for i in idx], windows)
    cw = {w: crossing_window(target.corners, polarity, w) for w in ("u_dep", "u_inv")}
    v = verdicts(m, pw, cw)
    g = target.geometry
    comp = {
        "geometry": {"geometry_id": geometry_id(g), "l_um": g.l_um, "role": g.role, "w_um": g.w_um},
        "metrics": {
            "depletion_max_rel": m.depletion_max_rel,
            "dv_dep_v": m.dv_dep_v,
            "dv_inv_v": m.dv_inv_v,
            "plateau_acc_max_rel": m.plateau_acc_max_rel,
            "plateau_acc_points": len(m.acc_index),
            "plateau_inv_max_rel": m.plateau_inv_max_rel,
            "plateau_inv_points": len(m.inv_index),
        },
        "residuals": {
            "dv_dep_scaled": m.dv_dep_v / DV_TOL_V,
            "dv_inv_scaled": m.dv_inv_v / DV_TOL_V,
            "plateau_acc_rel": list(m.acc_rel),
            "plateau_acc_u": list(m.acc_u),
            "plateau_inv_rel": list(m.inv_rel),
            "plateau_inv_u": list(m.inv_u),
        },
        "spice_regions": asdict(r),
        "tcad_crossings": {"u_dep": m.u_dep_tcad, "u_inv": m.u_inv_tcad},
        "verdict": worst(x["verdict"] for x in v.values()),
        "verdicts": v,
    }
    return comp, m.residuals()


# --- the 1D model -------------------------------------------------------------------------------

Simulate = Callable[[process.ProcessDescription, Sequence[float]], moscap1d.MoscapCV]


def devsim_simulator(device: str, log: Callable[[str], None] | None = None) -> Simulate:
    """The 1D DEVSIM MOS capacitor on the device's selected 1D mesh (runs in the TCAD image)."""
    mesh = meshconv.selected_spec(device, 1)

    def simulate(proc: process.ProcessDescription, vg: Sequence[float]) -> moscap1d.MoscapCV:
        return moscap1d.simulate(proc, vg=vg, method="qs", mesh=mesh)

    return simulate


def _polarity(proc: process.ProcessDescription) -> int:
    return 1 if proc.polarity == "n" else -1


def _compare_1d(
    proc: process.ProcessDescription, m: moscap1d.MoscapCV, target: Target, cox: Mapping
) -> tuple[dict, list[float]]:
    """:func:`compare` of the 1D C-V ``m`` area-scaled to the target's geometry."""
    g = target.geometry
    _, _, par, total = m.area_scaled(g, proc)
    leff, weff = moscap1d.cv_geometry_um(proc.card_values(), g)
    return compare(
        target, m.vg, total, _polarity(proc), spec_area_um2=leff * weff, parasitic_ff=par, cox=cox
    )


def _cox_check(proc: process.ProcessDescription, m: moscap1d.MoscapCV, cox: Mapping) -> dict:
    """The TCAD-only check of the 1D per-area plateau values (and the oxide's own Cox) against
    the public Cox spec."""
    pol = _polarity(proc)
    order, _ = _sorted_u(m.vg, pol)
    acc, inv = m.c_per_area_ff_um2[order[0]], m.c_per_area_ff_um2[order[-1]]
    v = proc.values()
    c_ox = f_per_cm2_to_ff_per_um2(cox_f_per_cm2(v["t_ox_eff_nm"], v["epsrox"]))
    lo, hi = float(cox["min"]), float(cox["max"])
    return {
        "c_ox_ff_per_um2": c_ox,
        "c_per_area_acc_ff_per_um2": acc,
        "c_per_area_inv_ff_per_um2": inv,
        "inside": all(lo <= x <= hi for x in (c_ox, acc, inv)),
        "spec": {
            "max": hi,
            "min": lo,
            "section": cox["section"],
            "source_url": cox["source_url"],
            "typ": float(cox["typ"]),
        },
    }


def _model_dict(m: moscap1d.MoscapCV) -> dict:
    return {
        "bookkeeping": "1D: C per area times LeffCV*WeffCV plus the BSIM4 capMod=2 overlap, "
        "fringe and gate-bulk terms (moscap1d.MoscapCV.area_scaled; DLC and parasitics fixed)",
        "dim": 1,
        "mesh": m.mesh.as_dict(),
        "method": m.method,
        "node_count": m.node_count,
        "rel_tol": m.rel_tol,
    }


# --- the calibration ----------------------------------------------------------------------------


def _checked_targets(
    device: str, targets: Mapping[str, Target], geometries: Sequence[Geometry]
) -> list[Target]:
    """The targets of ``geometries`` (by geometry id), each checked (:func:`check_target`) and
    required to be the target of that geometry; ValueError if one is missing."""
    chosen = []
    for g in geometries:
        t = targets.get(geometry_id(g))
        if t is None:
            raise ValueError(f"{device}: no target for {geometry_id(g)}")
        if t.geometry != g:
            raise CalibrationLeak(f"{device}: the target of {geometry_id(g)} is {t.geometry}")
        check_target(device, t)
        chosen.append(t)
    return chosen


def _check_geometries(device: str, geometries: Sequence[Geometry]) -> None:
    allowed = {g for g in DEVICES[device].geometries if g.role == "calibration"}
    if not geometries:
        raise CalibrationLeak(f"{device}: no calibration geometry")
    for g in geometries:
        if g.role != "calibration":
            raise CalibrationLeak(f"{device}: {geometry_id(g)} has role {g.role!r} (validation)")
        if g not in allowed:
            raise CalibrationLeak(f"{device}: {geometry_id(g)} is not a calibration geometry")
    if len(set(geometries)) != len(geometries):
        raise CalibrationLeak(f"{device}: a geometry is listed twice")


def _check_params(proc: process.ProcessDescription, params: Sequence[str]) -> None:
    if not params or len(set(params)) != len(params):
        raise CalibrationLeak(f"{proc.device}: parameters must be distinct, got {params}")
    for p in params:
        if p not in process.TUNABLES or p not in proc.params or proc.params[p].fixed:
            raise CalibrationLeak(f"{proc.device}: {p!r} is not a free tunable")


@dataclass(frozen=True)
class CalibrationResult:
    """A finished fit (:func:`calibrate_cv`); ``source`` is the calibration file it was
    loaded from (:func:`load_frozen`), None for a fresh fit."""

    device: str
    params: tuple[str, ...]
    values: dict[str, float]
    start: dict[str, float]
    bounds: dict[str, tuple[float, float]]
    bound_hits: dict[str, str]
    budget_used: int
    budget: int
    geometries: tuple[dict, ...]
    optimiser: dict
    per_geometry: dict[str, dict]
    verdict: str
    cox_check: dict
    model: dict
    param_sha256: str
    source: Path | None = field(default=None, compare=False)

    def to_dict(self) -> dict:
        return {
            "bound_hits": dict(self.bound_hits),
            "bounds": {k: list(v) for k, v in self.bounds.items()},
            "budget": self.budget,
            "budget_used": self.budget_used,
            "cox_check": self.cox_check,
            "device": self.device,
            "geometries": list(self.geometries),
            "model": self.model,
            "optimiser": self.optimiser,
            "param_sha256": self.param_sha256,
            "params": list(self.params),
            "per_geometry": self.per_geometry,
            "reference": {"corner": TT, "engine": ENGINE, "sweep": SWEEP},
            "schema": SCHEMA,
            "start": dict(self.start),
            "values": dict(self.values),
            "verdict": self.verdict,
        }

    @classmethod
    def from_dict(cls, d: Mapping, source: Path | None = None) -> CalibrationResult:
        if d.get("schema") != SCHEMA:
            raise ValueError(f"calibration result schema {d.get('schema')!r}, expected {SCHEMA}")
        return cls(
            device=d["device"],
            params=tuple(d["params"]),
            values=dict(d["values"]),
            start=dict(d["start"]),
            bounds={k: tuple(v) for k, v in d["bounds"].items()},
            bound_hits=dict(d["bound_hits"]),
            budget_used=d["budget_used"],
            budget=d["budget"],
            geometries=tuple(d["geometries"]),
            optimiser=dict(d["optimiser"]),
            per_geometry=dict(d["per_geometry"]),
            verdict=d["verdict"],
            cox_check=dict(d["cox_check"]),
            model=dict(d["model"]),
            param_sha256=d["param_sha256"],
            source=source,
        )

    def write(self, out: Path) -> None:
        """Write ``out/<device>.json`` (:func:`gf180tcad.tcad.calibration.write`) and
        ``out/<device>.result.json``, which records the first file's sha256."""
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        cal = out / f"{self.device}.json"
        calibration.write(cal, self.device, self.values)
        io.write_json(
            out / f"{self.device}{RESULT_SUFFIX}",
            {**self.to_dict(), "calibration_file_sha256": calibration.sha256_file(cal)},
        )


def calibrate_cv(
    device: str,
    *,
    geometries: Sequence[Geometry],
    params: Sequence[str] = process.TUNABLES,
    targets: Mapping[str, Target] | None = None,
    simulate: Simulate | None = None,
    log: Callable[[str], None] | None = None,
) -> CalibrationResult:
    """Fit ``params`` of ``device`` to the TT ngspice Cgg-Vg of the calibration ``geometries``.

    ``targets`` (geometry id to :class:`Target`) default to the committed SPICE reference and
    ``simulate`` to :func:`devsim_simulator`. The tunables not in ``params`` stay at their start
    values. Raises :class:`CalibrationLeak` (before any simulation) for a validation geometry, a
    target that is not the TT ngspice cv sweep, or a parameter that is not a free tunable.
    """
    from scipy.optimize import least_squares

    proc = process.load(device)
    _check_geometries(device, geometries)
    _check_params(proc, params)
    params = tuple(params)
    if targets is None:
        targets = {geometry_id(g): load_target(device, g) for g in geometries}
    chosen = _checked_targets(device, targets, geometries)
    vg = chosen[0].tt.vg
    if any(t.tt.vg != vg for t in chosen):
        raise ValueError(f"{device}: the targets' vg grids differ")
    cox = cox_spec(device)
    simulate = simulate if simulate is not None else devsim_simulator(device)
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
            comp, r = _compare_1d(p, m, t, cox)
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
        **LSQ,
    )
    values = values_of(fit.x)
    p, m, comps, res = evaluate(values)
    hits = {}
    for n, a, b in zip(params, lo, hi, strict=True):
        tol = BOUND_HIT_REL * (b - a)
        if abs(values[n] - a) <= tol:
            hits[n] = "lower"
        elif abs(values[n] - b) <= tol:
            hits[n] = "upper"
    optimiser = {
        **dict(LSQ),
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
    return CalibrationResult(
        device=device,
        params=params,
        values=values,
        start=start,
        bounds=bounds,
        bound_hits=hits,
        budget_used=len(params),
        budget=BUDGET,
        geometries=tuple(c["geometry"] for c in comps.values()),
        optimiser=optimiser,
        per_geometry=comps,
        verdict=worst(c["verdict"] for c in comps.values()),
        cox_check=_cox_check(p, m, cox),
        model=_model_dict(m),
        param_sha256=calibration.param_sha256(values),
    )


# --- frozen results and validation ---------------------------------------------------------------


def load_frozen(device: str, root: Path | None = None) -> CalibrationResult:
    """The calibration result of ``device`` from ``root`` (default the committed
    ``results/tcad/calibration``): ``<device>.json`` and ``<device>.result.json``, which must
    agree (the recorded file sha256 and ``param_sha256``); else :class:`NotFrozen`."""
    root = Path(root) if root is not None else CALIBRATION_ROOT
    path = root / f"{device}.json"
    values = calibration.read(path, device)
    data = json.loads((root / f"{device}{RESULT_SUFFIX}").read_bytes())
    if data.get("device") != device:
        raise NotFrozen(f"{device}: the result file is for {data.get('device')!r}")
    if data.get("calibration_file_sha256") != calibration.sha256_file(path):
        raise NotFrozen(f"{path} changed after the fit (its sha256 differs from the result's)")
    if data["values"] != values or data["param_sha256"] != calibration.param_sha256(values):
        raise NotFrozen(f"{path}: the values or their param_sha256 differ from the result's")
    return CalibrationResult.from_dict(data, source=path)


def causes(device: str, geometry: Geometry) -> list[str]:
    """The mismatch causes (spec §6) a validation result is tagged with before comparison."""
    w10 = [g.l_um for g in DEVICES[device].geometries if g.w_um == 10.0]
    if geometry.w_um < 10.0:
        return list(NARROW_CAUSES)
    if geometry.l_um == min(w10):
        return list(LMIN_CAUSES)
    return []


@dataclass(frozen=True)
class ValidationResult:
    """The frozen calibration checked at the held-out geometries (1D) and in 2D."""

    device: str
    values: dict[str, float]
    param_sha256: str
    calibration_file_sha256: str
    one_d: dict[str, dict]
    two_d: dict[str, dict]
    verdict_1d: str
    model: dict

    def to_dict(self) -> dict:
        return {
            "calibration_file_sha256": self.calibration_file_sha256,
            "device": self.device,
            "model": self.model,
            "one_d": self.one_d,
            "param_sha256": self.param_sha256,
            "reference": {"corner": TT, "engine": ENGINE, "sweep": SWEEP},
            "schema": SCHEMA,
            "two_d": self.two_d,
            "values": dict(self.values),
            "verdict_1d": self.verdict_1d,
        }

    def write(self, out: Path) -> None:
        """Write ``out/<device>.json``."""
        Path(out).mkdir(parents=True, exist_ok=True)
        io.write_json(Path(out) / f"{self.device}.json", self.to_dict())


def _check_frozen(device: str, frozen: CalibrationResult, root: Path) -> Path:
    path = root / f"{device}.json"
    if frozen.device != device:
        raise NotFrozen(f"the frozen result is for {frozen.device}, not {device}")
    if frozen.source is None or Path(frozen.source).resolve() != path.resolve():
        raise NotFrozen(f"{device}: the frozen result was not loaded from {path}")
    if calibration.param_sha256(frozen.values) != frozen.param_sha256:
        raise NotFrozen(f"{device}: the values do not match the frozen param_sha256")
    committed = load_frozen(device, root)
    if committed.param_sha256 != frozen.param_sha256:
        raise NotFrozen(f"{device}: param_sha256 differs from the committed {path}")
    return path


def _two_d(
    device: str,
    frozen: CalibrationResult,
    targets: Mapping[str, Target],
    cox: Mapping,
    root: Path,
) -> dict[str, dict]:
    """The 2D checks from the committed calibrated 2D results (``moscap2d/<device>/calibrated``)."""
    from gf180tcad.tcad import moscap2d

    proc = process.load(device)
    out = {}
    for g in DEVICES[device].geometries:
        gid = geometry_id(g)
        job = moscap2d.job_dir(root, device, "calibrated", g)
        if not (job / moscap2d.CV_CSV).is_file():
            out[gid] = {
                "causes": causes(device, g),
                "reason": f"no calibrated 2D result {moscap2d.CV_CSV} in "
                f"results/tcad/moscap2d/{device}/calibrated/{gid}",
                "status": "not run",
            }
            continue
        cols, _ = io.read_csv(job / moscap2d.CV_CSV)
        meta = json.loads((job / moscap2d.META_JSON).read_bytes())
        if meta.get("param_sha256") != frozen.param_sha256:
            raise NotFrozen(f"{job}: not computed with the frozen calibration")
        vg = tuple(float(v) for v in cols["vg"])
        total = tuple(float(c) for c in cols["cgg_total"])
        comp, _ = compare(
            targets[gid], vg, total, _polarity(proc), spec_area_um2=g.w_um * g.l_um,
            parasitic_ff=None, cox=cox,
        )  # fmt: skip
        out[gid] = {**comp, "causes": causes(device, g), "status": "compared"}
    return out


def validate_cv(
    device: str,
    frozen: CalibrationResult,
    *,
    simulate: Simulate | None = None,
    targets: Mapping[str, Target] | None = None,
    calibration_root: Path | None = None,
    moscap2d_root: Path | None = None,
) -> ValidationResult:
    """Check the frozen calibration of ``device`` at the held-out geometries.

    1D: the frozen values at W10/L0.7, W10/L1 and W1.6/L0.7 (``role == "validation"``). 2D: the
    committed calibrated 2D results at every geometry (``python -m gf180tcad.tcad moscap --dim 2
    --params calibrated``, the same ``moscap2d.simulate`` with S/D, QS, on the selected 2D mesh
    and the SPICE grid); a geometry without one is listed as not run. Raises :class:`NotFrozen`
    unless ``frozen`` was loaded from the committed calibration file and its ``param_sha256``
    matches that file.
    """
    root = Path(calibration_root) if calibration_root is not None else CALIBRATION_ROOT
    path = _check_frozen(device, frozen, root)
    proc = process.load(device).with_values(frozen.values)
    held_out = [g for g in DEVICES[device].geometries if g.role == "validation"]
    if targets is None:
        targets = {geometry_id(g): load_target(device, g) for g in DEVICES[device].geometries}
    # every target used: the held-out ones (1D) and, for the 2D checks, all geometries
    _checked_targets(device, targets, DEVICES[device].geometries)
    vg = targets[geometry_id(held_out[0])].tt.vg
    cox = cox_spec(device)
    simulate = simulate if simulate is not None else devsim_simulator(device)
    m = simulate(proc, vg)
    one_d = {}
    for g in held_out:
        comp, _ = _compare_1d(proc, m, targets[geometry_id(g)], cox)
        one_d[geometry_id(g)] = {**comp, "causes": causes(device, g)}
    two_d = _two_d(
        device, frozen, targets, cox,
        Path(moscap2d_root) if moscap2d_root is not None else MOSCAP2D_ROOT,
    )  # fmt: skip
    return ValidationResult(
        device=device,
        values=dict(frozen.values),
        param_sha256=frozen.param_sha256,
        calibration_file_sha256=calibration.sha256_file(path),
        one_d=one_d,
        two_d=two_d,
        verdict_1d=worst(c["verdict"] for c in one_d.values()),
        model=_model_dict(m),
    )
