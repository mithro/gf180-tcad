# SPDX-License-Identifier: Apache-2.0
"""Task 12: the C-V calibration of the 1D TCAD MOS capacitor (gf180tcad.calibrate.cv).

The fits here run on the host, on synthetic SPICE targets made from the 1D model's exact
reference, :func:`gf180tcad.tcad.analytic.lf_cv_uniform`: the exact Poisson-Boltzmann
low-frequency C-V of the model the 1D TCAD solves, which the TCAD matches within 0.1 % at every
bias (tests/tcad/test_moscap1d.py::test_matches_exact_poisson_boltzmann). The same simulator
stands in for DEVSIM in the fits, so a fit takes seconds, not the minutes of a sandbox run. The
SPICE bookkeeping (DLC, overlaps, fringe) is the real one (``MoscapCV.area_scaled``). A coarser
0.1 V grid than the SPICE cv sweep's 50 mV keeps the fits fast.
"""

import dataclasses
import json
import math
from types import MappingProxyType

import pytest

from gf180tcad import io, specwindow
from gf180tcad.calibrate import cv
from gf180tcad.devices import CORNERS, DEVICES, Geometry, geometry_id
from gf180tcad.tcad import analytic, calibration, moscap1d, process
from gf180tcad.tcad.mesh import MeshSpec
from gf180tcad.tcad.process import CONSTANTS

NFET = "nfet_05v0"
PFET = "pfet_05v0"
GRID = tuple((i - 50) / 10 for i in range(101))  # -5..5 V, 0.1 V
TRUTH = {"t_ox_eff_nm": 15.9, "n_ch_cm3": 2.1e17, "dv_fb_v": 0.06}
# A pfet truth inside the pfet bounds (data/process/pfet_05v0.toml), with a negative flat-band
# offset, so the pfet sign path (polarity -1, u = -Vg) is fitted too.
PFET_TRUTH = {"t_ox_eff_nm": 15.9, "n_ch_cm3": 2.1e17, "dv_fb_v": -0.06}
# The five synthetic corners: (C scale, gate-bias shift in V); typical is the truth itself.
CORNER_SHAPE = {
    "typical": (1.0, 0.0),
    "ff": (0.98, -0.04),
    "ss": (1.02, 0.04),
    "fs": (0.99, -0.02),
    "sf": (1.01, 0.03),
}


def cal_geometries(device=NFET):
    return tuple(g for g in DEVICES[device].geometries if g.role == "calibration")


def val_geometries(device=NFET):
    return tuple(g for g in DEVICES[device].geometries if g.role == "validation")


def analytic_cv(device, values, vg):
    """The exact 1D C-V (a MoscapCV) of ``device`` at the tunable ``values`` (any, unbounded)."""
    proc = process.load(device)
    v = {**proc.values(), **values}
    st = moscap1d.Stack(proc.polarity, v["n_ch_cm3"], v["ngate_cm3"], v["t_ox_eff_nm"], v["epsrox"])
    c = analytic.lf_cv_uniform(
        st.body_net_cm3, st.t_ox_nm, st.gate_net_cm3, [x - v["dv_fb_v"] for x in vg],
        eps_ox=st.eps_ox,
    )  # fmt: skip
    pts = tuple(moscap1d.Point(True, 1, 0.0, 0.0) for _ in vg)
    return moscap1d.MoscapCV(
        device, tuple(vg), c, pts, "qs", CONSTANTS, MeshSpec.DEFAULT_1D, st, moscap1d.REL_TOL, 1
    )


class Recorder:
    """The analytic simulator, recording the tunable values of every call."""

    def __init__(self):
        self.calls = []

    def __call__(self, proc, vg):
        values = {n: proc.values()[n] for n in process.TUNABLES}
        self.calls.append(values)
        return analytic_cv(proc.device, values, vg)


def synthetic_targets(device, truth, geometries, grid=GRID):
    """Targets whose five corners are the truth's Cgg, scaled and shifted (CORNER_SHAPE)."""
    proc = process.load(device)
    pol = 1 if proc.polarity == "n" else -1
    vg = tuple(pol * x + 0.0 for x in grid)  # the SPICE order: from accumulation
    out = {}
    for g in geometries:
        corners = {}
        for corner, (scale, shift) in CORNER_SHAPE.items():
            m = analytic_cv(device, {**truth, "dv_fb_v": truth["dv_fb_v"] + pol * shift}, vg)
            _, _, _, total = m.area_scaled(g, proc)
            meta = {
                "engine": "ngspice", "corner": corner, "device": device,
                "geometry_id": geometry_id(g), "sweep": "cv",
            }  # fmt: skip
            corners[corner] = cv.Curve(vg, tuple(scale * c for c in total), MappingProxyType(meta))
        out[geometry_id(g)] = cv.Target(g, corners["typical"], MappingProxyType(corners))
    return out


@pytest.fixture(scope="module")
def fit():
    targets = synthetic_targets(NFET, TRUTH, cal_geometries())
    sim = Recorder()
    res = cv.calibrate_cv(NFET, geometries=cal_geometries(), targets=targets, simulate=sim)
    return res, sim, targets


# --- the fit ---------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pfet_fit():
    targets = synthetic_targets(PFET, PFET_TRUTH, cal_geometries(PFET))
    return cv.calibrate_cv(
        PFET, geometries=cal_geometries(PFET), targets=targets, simulate=Recorder()
    )


@pytest.mark.parametrize("device", [NFET, PFET])
def test_recovers_known_params(device, request):
    res = (
        request.getfixturevalue("fit")[0] if device == NFET else request.getfixturevalue("pfet_fit")
    )
    truth = TRUTH if device == NFET else PFET_TRUTH
    proc = process.load(device)
    for n, v in truth.items():  # the truth is a fair one: inside the bounds
        lo, hi = proc.params[n].bounds
        assert lo < v < hi, (n, v)
    assert res.device == device
    assert math.isclose(res.values["t_ox_eff_nm"], truth["t_ox_eff_nm"], rel_tol=5e-3)
    assert math.isclose(res.values["n_ch_cm3"], truth["n_ch_cm3"], rel_tol=5e-3)
    assert abs(res.values["dv_fb_v"] - truth["dv_fb_v"]) <= 1e-3
    assert res.bound_hits == {}
    for gid, comp in res.per_geometry.items():  # the regions in u = polarity * Vg, ordered
        r = comp["spice_regions"]
        assert r["u_fb"] < r["u_dep"] < r["u_min"] < r["u_inv"], gid
        assert r["c_min"] < r["c_acc"] and r["c_min"] < r["c_inv"], gid
    cc = res.cox_check  # accumulation and inversion plateaus taken from the right ends
    assert cc["c_per_area_acc_ff_per_um2"] > 0.9 * cc["c_ox_ff_per_um2"]
    assert cc["c_per_area_inv_ff_per_um2"] > 0.9 * cc["c_ox_ff_per_um2"]
    assert res.budget_used == 3 and res.budget == 8
    assert res.verdict == "Agree"
    for gid, comp in res.per_geometry.items():
        assert comp["verdict"] == "Agree", gid
    assert res.param_sha256 == calibration.param_sha256(res.values)


def test_budget_used_counts_the_fitted_params():
    """budget_used is the number of parameters fitted, not the number of tunables."""
    truth = {**TRUTH, "dv_fb_v": 0.0}
    targets = synthetic_targets(NFET, truth, cal_geometries(), grid=GRID[::2])
    res = cv.calibrate_cv(
        NFET, geometries=cal_geometries(), params=("t_ox_eff_nm", "n_ch_cm3"), targets=targets,
        simulate=Recorder(),
    )  # fmt: skip
    assert res.params == ("t_ox_eff_nm", "n_ch_cm3")
    assert res.budget_used == 2 and res.budget == cv.BUDGET
    assert res.values["dv_fb_v"] == res.start["dv_fb_v"]


def test_validation_geometry_raises():
    geoms = (*cal_geometries(), val_geometries()[0])
    with pytest.raises(cv.CalibrationLeak, match="validation"):
        cv.calibrate_cv(NFET, geometries=geoms, simulate=Recorder())
    # a calibration-role copy of a held-out geometry is no way around the guard either
    sneaky = Geometry(10.0, 0.7, "calibration")
    with pytest.raises(cv.CalibrationLeak):
        cv.calibrate_cv(NFET, geometries=(*cal_geometries(), sneaky), simulate=Recorder())


@pytest.mark.parametrize(
    ("key", "value"),
    [("sweep", "idvg_lin"), ("corner", "ff"), ("engine", "xyce"), ("geometry_id", "w10p0_l0p70")],
)
def test_non_cv_target_raises(key, value):
    targets = synthetic_targets(NFET, TRUTH, cal_geometries(), grid=GRID[::10])
    gid, t = next(iter(targets.items()))
    bad = dataclasses.replace(t.tt, meta=MappingProxyType({**t.tt.meta, key: value}))
    targets[gid] = dataclasses.replace(t, tt=bad)
    sim = Recorder()
    with pytest.raises(cv.CalibrationLeak):
        cv.calibrate_cv(NFET, geometries=cal_geometries(), targets=targets, simulate=sim)
    assert sim.calls == []  # refused before any simulation


@pytest.mark.parametrize("params", [("t_ox_eff_nm", "ngate_cm3"), ("t_ox_eff_nm", "dlc"),
                                    ("t_ox_eff_nm", "no_such"), ("t_ox_eff_nm", "t_ox_eff_nm")])  # fmt: skip
def test_fixed_param_raises(params):
    sim = Recorder()
    with pytest.raises(cv.CalibrationLeak):
        cv.calibrate_cv(NFET, geometries=cal_geometries(), params=params, simulate=sim)
    assert sim.calls == []


def test_bounds_enforced_and_hits_reported():
    """A truth below the TOXE lower bound: the fit stops on the bound and reports it."""
    truth = {**TRUTH, "t_ox_eff_nm": 14.6}
    targets = synthetic_targets(NFET, truth, cal_geometries())
    sim = Recorder()
    res = cv.calibrate_cv(NFET, geometries=cal_geometries(), targets=targets, simulate=sim)
    lo, hi = process.load(NFET).params["t_ox_eff_nm"].bounds
    assert abs(res.values["t_ox_eff_nm"] - lo) <= 1e-3 * (hi - lo)
    assert res.bound_hits["t_ox_eff_nm"] == "lower"
    proc = process.load(NFET)
    for call in sim.calls:  # never simulated outside the bounds
        for n, v in call.items():
            b = proc.params[n].bounds
            assert b[0] <= v <= b[1], (n, v)
    for n, v in res.values.items():
        assert proc.params[n].bounds[0] <= v <= proc.params[n].bounds[1]


def test_deterministic(fit, tmp_path):
    res, _, targets = fit
    again = cv.calibrate_cv(NFET, geometries=cal_geometries(), targets=targets, simulate=Recorder())
    res.write(tmp_path / "a")
    again.write(tmp_path / "b")
    for name in (f"{NFET}.json", f"{NFET}{cv.RESULT_SUFFIX}"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_tunables_from_process_file(monkeypatch):
    """Start values and bounds come only from process.load (here a patched description)."""
    real = process.load(NFET)
    p = real.params["t_ox_eff_nm"]
    params = dict(real.params)
    params["t_ox_eff_nm"] = dataclasses.replace(p, value=15.5, bounds=(15.4, 16.5))
    patched = dataclasses.replace(real, params=MappingProxyType(params))
    monkeypatch.setattr(cv.process, "load", lambda device, data_dir=None: patched)
    targets = synthetic_targets(NFET, TRUTH, cal_geometries())
    sim = Recorder()
    res = cv.calibrate_cv(NFET, geometries=cal_geometries(), targets=targets, simulate=sim)
    assert sim.calls[0] == {"t_ox_eff_nm": 15.5, "n_ch_cm3": 1.7e17, "dv_fb_v": 0.0}
    assert res.start == {"t_ox_eff_nm": 15.5, "n_ch_cm3": 1.7e17, "dv_fb_v": 0.0}
    assert res.bounds["t_ox_eff_nm"] == (15.4, 16.5)
    assert res.bounds["n_ch_cm3"] == real.params["n_ch_cm3"].bounds


# --- validation --------------------------------------------------------------------------------


def test_validate_requires_frozen_hash(fit, tmp_path):
    res, _, _ = fit
    res.write(tmp_path)
    frozen = cv.load_frozen(NFET, tmp_path)
    assert frozen.values == res.values and frozen.param_sha256 == res.param_sha256
    targets = synthetic_targets(NFET, TRUTH, DEVICES[NFET].geometries)
    # no 2D results: the committed calibrated 2D tree belongs to the committed calibration
    m2d = tmp_path / "moscap2d"
    out = cv.validate_cv(
        NFET,
        frozen,
        simulate=Recorder(),
        targets=targets,
        calibration_root=tmp_path,
        moscap2d_root=m2d,
    )
    assert out.param_sha256 == res.param_sha256
    assert set(out.one_d) == {geometry_id(g) for g in val_geometries()}
    assert out.one_d["w1p6_l0p70"]["causes"] == ["geometry-2d", "spice-fit"]
    # an edited value no longer matches the committed calibration file
    edited = dataclasses.replace(frozen, values={**frozen.values, "dv_fb_v": 0.07})
    with pytest.raises(cv.NotFrozen):
        cv.validate_cv(
            NFET,
            edited,
            simulate=Recorder(),
            targets=targets,
            calibration_root=tmp_path,
            moscap2d_root=m2d,
        )
    # nor does a calibration file edited after the fit
    calibration.write(tmp_path / f"{NFET}.json", NFET, {**frozen.values, "dv_fb_v": 0.07})
    with pytest.raises(cv.NotFrozen):
        cv.validate_cv(
            NFET,
            frozen,
            simulate=Recorder(),
            targets=targets,
            calibration_root=tmp_path,
            moscap2d_root=m2d,
        )
    with pytest.raises(cv.NotFrozen):
        cv.load_frozen(NFET, tmp_path)


def _write_2d(root, device, geometry, vg, cgg, param_sha256):
    """A calibrated 2D job directory as ``python -m gf180tcad.tcad moscap --dim 2`` writes it
    (the columns and meta key that cv._two_d reads)."""
    from gf180tcad.tcad import moscap2d

    job = moscap2d.job_dir(root, device, "calibrated", geometry)
    job.mkdir(parents=True)
    area = geometry.w_um * geometry.l_um
    io.write_csv(
        job / moscap2d.CV_CSV,
        {
            "vg": vg,
            "c_per_area": [c / area for c in cgg],
            "cgg_per_um": [c / geometry.w_um for c in cgg],
            "cgg_total": cgg,
        },
        {"device": device, "dim": "2", "method": "qs", "params": "calibrated"},
    )
    io.write_json(job / moscap2d.META_JSON, {"device": device, "param_sha256": param_sha256})


def test_validate_two_d(fit, tmp_path):
    """cv._two_d compares the committed calibrated 2D results it finds (drawn-area Cox window, no
    parasitic term), refuses one computed with other values, and lists the rest as not run."""
    res, _, _ = fit
    res.write(tmp_path / "cal")
    frozen = cv.load_frozen(NFET, tmp_path / "cal")
    targets = synthetic_targets(NFET, TRUTH, DEVICES[NFET].geometries)
    by_id = {geometry_id(g): g for g in DEVICES[NFET].geometries}
    done = ("w10p0_l10p00", "w10p0_l0p70")  # a calibration and a held-out geometry
    # 8 % high: outside the 5 % and the +-2 % corner envelope; at W10/L10 (C close to Cox * W*L)
    # inside the drawn-area Cox window, so "Same process" there
    scale = 1.08
    m2d = tmp_path / "moscap2d"
    for gid in done:
        t = targets[gid]
        _write_2d(m2d, NFET, by_id[gid], t.tt.vg, [scale * c for c in t.tt.cgg_ff],
                  frozen.param_sha256)  # fmt: skip
    out = cv.validate_cv(
        NFET, frozen, simulate=Recorder(), targets=targets, calibration_root=tmp_path / "cal",
        moscap2d_root=m2d,
    )  # fmt: skip
    assert set(out.two_d) == set(by_id)
    cox = cv.cox_spec(NFET)
    for gid, entry in out.two_d.items():
        g = by_id[gid]
        assert entry["causes"] == cv.causes(NFET, g), gid
        if gid not in done:
            assert entry["status"] == "not run", gid
            assert f"{NFET}/calibrated/{gid}" in entry["reason"]
            assert "metrics" not in entry
            continue
        assert entry["status"] == "compared", gid
        assert entry["geometry"]["geometry_id"] == gid
        m = entry["metrics"]
        assert math.isclose(m["plateau_acc_max_rel"], scale - 1, rel_tol=1e-9)
        assert math.isclose(m["plateau_inv_max_rel"], scale - 1, rel_tol=1e-9)
        # a uniform scale moves each curve's own C_mid with it: no crossing shift
        assert abs(m["dv_dep_v"]) < 1e-9 and abs(m["dv_inv_v"]) < 1e-9
        # the plateau window is the Cox spec times the drawn area W*L (no parasitic term),
        # hulled with the corner envelope, at the tightest plateau point
        _, elo, ehi = cv.envelope_of(targets[gid].corners)
        vg = targets[gid].tt.vg
        for key in ("plateau_acc", "plateau_inv"):
            v = entry["verdicts"][key]
            assert v["max_rel"] > cv.PLATEAU_TOL
            want_verdict = "Same process" if v["window"]["all_inside"] else "Disagree"
            assert v["verdict"] == want_verdict, (gid, key)
            if gid == "w10p0_l10p00":
                assert v["window"]["all_inside"], key
            tight = v["window"]["tightest"]
            i = vg.index(tight["u"])  # nfet: u = vg
            want = specwindow.window(
                "cgg_ff",
                (cox["min"] * g.w_um * g.l_um, cox["max"] * g.w_um * g.l_um),
                (elo[i], ehi[i]),
            )
            assert (tight["lo"], tight["hi"], tight["source"]) == (want.lo, want.hi, want.source)
            assert tight["lo"] == min(cox["min"] * g.w_um * g.l_um, elo[i])
        assert entry["verdict"] == cv.worst(x["verdict"] for x in entry["verdicts"].values())
    assert out.two_d["w10p0_l10p00"]["verdict"] == "Same process"
    # a calibrated 2D result computed with other values is refused
    meta = m2d / NFET / "calibrated" / done[1] / "cv.meta.json"
    io.write_json(meta, {"device": NFET, "param_sha256": "0" * 64})
    with pytest.raises(cv.NotFrozen, match="not computed with the frozen calibration"):
        cv.validate_cv(
            NFET, frozen, simulate=Recorder(), targets=targets, calibration_root=tmp_path / "cal",
            moscap2d_root=m2d,
        )  # fmt: skip


def test_validate_checks_every_target(fit, tmp_path):
    """validate_cv checks the target of every geometry it may use (the held-out ones in 1D, all
    of them in 2D), not only the held-out ones."""
    res, _, _ = fit
    res.write(tmp_path)
    frozen = cv.load_frozen(NFET, tmp_path)
    targets = synthetic_targets(NFET, TRUTH, DEVICES[NFET].geometries, grid=GRID[::10])
    gid = geometry_id(cal_geometries()[0])
    t = targets[gid]
    bad = dict(targets)
    bad[gid] = dataclasses.replace(
        t, tt=dataclasses.replace(t.tt, meta=MappingProxyType({**t.tt.meta, "sweep": "idvg_lin"}))
    )
    sim = Recorder()
    with pytest.raises(cv.CalibrationLeak):
        cv.validate_cv(NFET, frozen, simulate=sim, targets=bad, calibration_root=tmp_path)
    missing = {k: v for k, v in targets.items() if k != gid}
    with pytest.raises(ValueError, match="no target"):
        cv.validate_cv(NFET, frozen, simulate=sim, targets=missing, calibration_root=tmp_path)
    swapped = {**targets, gid: targets[geometry_id(cal_geometries()[1])]}
    with pytest.raises(cv.CalibrationLeak):
        cv.validate_cv(NFET, frozen, simulate=sim, targets=swapped, calibration_root=tmp_path)
    assert sim.calls == []  # refused before any simulation


# --- the reference windows and the metric ------------------------------------------------------


def test_envelope_cv():
    gid = "w10p0_l10p00"
    vg, lo, hi = cv.envelope_cv(NFET, gid)
    curves = {c: cv.load_curve(NFET, gid, c) for c in CORNERS}
    assert all(curves[c].vg == vg for c in CORNERS)
    for i in range(len(vg)):
        values = [curves[c].cgg_ff[i] for c in CORNERS]
        assert (lo[i], hi[i]) == (min(values), max(values))
    tt = curves["typical"].cgg_ff
    assert all(a <= t <= b for a, t, b in zip(lo, tt, hi, strict=True))
    # the cv.csv values are F; the curves are fF
    cols, meta = io.read_csv(cv.SPICE_ROOT / "ngspice" / "typical" / NFET / gid / "cv.csv")
    assert tt[0] == cols["cgg"][0] * 1e15 and meta["sweep"] == "cv"


def test_envelope_cv_requires_identical_grids():
    a = cv.Curve((0.0, 1.0), (1.0, 2.0), MappingProxyType({}))
    b = cv.Curve((0.0, 1.5), (1.0, 2.0), MappingProxyType({}))
    with pytest.raises(ValueError, match="grid"):
        cv.envelope_of({"typical": a, "ff": b})


def _hand_curve(u, shift_inv=0.0, acc_scale=1.0):
    """Piecewise linear C(u) (fF): plateau 200, linear fall to 80 at 0, rise to 200 at 2 V."""
    out = []
    for x in u:
        if x <= -1.5:
            c = 200.0 * acc_scale
        elif x <= 0.0:
            c = 200.0 - 120.0 * (x + 1.5) / 1.5
        else:
            x = x - shift_inv
            c = 80.0 if x <= 0.0 else min(200.0, 80.0 + 60.0 * x)
        out.append(c)
    return tuple(out)


U = tuple((i - 100) / 20 for i in range(201))


def test_metric_regions():
    spice = _hand_curve(U)
    r = cv.regions(U, spice)
    assert (r.c_acc, r.c_min, r.c_inv) == (200.0, 80.0, 200.0)
    assert math.isclose(r.u_fb, -1.5 + 1.5 * 20 / 120, abs_tol=1e-12)  # C = 180
    assert math.isclose(r.u_t, 1.0, abs_tol=1e-12)  # (80 + 200) / 2 = 140
    assert math.isclose(r.u_dep, -0.75, abs_tol=1e-12) and math.isclose(r.u_inv, 1.0, abs_tol=1e-12)
    # +20 mV only on the inversion side: dV_inv = 20 mV, dV_dep = 0
    m = cv.metrics(U, _hand_curve(U, shift_inv=0.02), spice)
    assert math.isclose(m.dv_inv_v, 0.02, abs_tol=1e-12) and m.dv_dep_v == 0.0
    assert m.plateau_acc_max_rel == 0.0
    # plateaus: u <= u_fb - 1 and u >= u_t + 1; a 3 % low accumulation shows there only
    m = cv.metrics(U, _hand_curve(U, acc_scale=0.97), spice)
    assert math.isclose(m.plateau_acc_max_rel, 0.03, rel_tol=1e-12)
    assert m.plateau_inv_max_rel == 0.0
    assert all(u <= r.u_fb - 1.0 for u in m.acc_u) and all(u >= r.u_t + 1.0 for u in m.inv_u)
    assert len(m.acc_u) == sum(1 for u in U if u <= r.u_fb - 1.0)


def test_regions_require_the_full_grid():
    """C_acc and C_inv are read at the grid's ends, so a grid that does not run from u = -5 V to
    +5 V is refused, not silently misread."""
    spice = _hand_curve(U)
    assert (U[0], U[-1]) == (-cv.U_END_V, cv.U_END_V)
    for lo, hi in ((1, len(U)), (0, len(U) - 1), (10, len(U) - 10)):
        u, c = U[lo:hi], spice[lo:hi]
        with pytest.raises(ValueError, match=r"must span u = -5\.\.\+5 V"):
            cv.regions(u, c)
        with pytest.raises(ValueError, match=r"must span u = -5\.\.\+5 V"):
            cv.crossings(u, c)
    with pytest.raises(ValueError, match="must span"):
        cv.regions((), ())


def test_crossing_windows():
    shifts = {"typical": 0.0, "ff": -0.08, "ss": 0.1, "fs": -0.03, "sf": 0.05}
    curves = {
        c: cv.Curve(U, _hand_curve(U, shift_inv=s), MappingProxyType({})) for c, s in shifts.items()
    }
    w = cv.crossing_window(curves, 1, "u_inv")
    assert isinstance(w, specwindow.Window) and w.source == "envelope"
    assert math.isclose(w.lo, 1.0 - 0.08, abs_tol=1e-12)
    assert math.isclose(w.hi, 1.0 + 0.1, abs_tol=1e-12)
    dep = cv.crossing_window(curves, 1, "u_dep")
    assert math.isclose(dep.lo, -0.75, abs_tol=1e-12) and math.isclose(dep.hi, -0.75, abs_tol=1e-12)
    # 70 mV off: outside +-50 mV but inside the corner window, so "Same process"
    assert cv.crossing_verdict(0.07, 1.07, w) == "Same process"
    assert cv.crossing_verdict(0.02, 1.02, w) == "Agree"
    assert cv.crossing_verdict(0.15, 1.15, w) == "Disagree"


def test_depletion_error_reported(fit):
    res, _, _ = fit
    for gid, comp in res.per_geometry.items():
        d = comp["metrics"]["depletion_max_rel"]
        assert math.isfinite(d) and d >= 0, gid
        assert "depletion" not in comp["verdicts"]
    # a huge depletion error does not change the verdict
    m = cv.Metrics(
        acc_u=(-5.0,), inv_u=(5.0,), plateau_acc_max_rel=0.01, plateau_inv_max_rel=0.01,
        dv_dep_v=0.01, dv_inv_v=-0.01, depletion_max_rel=0.9, u_dep_tcad=-0.74,
        u_inv_tcad=0.99,
    )  # fmt: skip
    verdicts = cv.verdicts(m, plateau_windows=None, crossing_windows=None)
    assert {v["verdict"] for v in verdicts.values()} == {"Agree"}
    assert cv.worst(v["verdict"] for v in verdicts.values()) == "Agree"


def test_result_round_trip(fit, tmp_path):
    res, _, _ = fit
    res.write(tmp_path)
    assert calibration.read(tmp_path / f"{NFET}.json", NFET) == res.values
    data = json.loads((tmp_path / f"{NFET}{cv.RESULT_SUFFIX}").read_bytes())
    assert data["param_sha256"] == res.param_sha256
    assert data["calibration_file_sha256"] == calibration.sha256_file(tmp_path / f"{NFET}.json")
    for comp in data["per_geometry"].values():
        assert set(comp["spice_regions"]) >= {"u_fb", "u_t", "c_min", "c_acc", "c_inv", "u_dep",
                                              "u_inv"}  # fmt: skip


# --- the CLI (host) ------------------------------------------------------------------------------


def test_jobs_refuse_outside_the_sandbox(tmp_path):
    from gf180tcad.calibrate import __main__ as cli

    with pytest.raises(RuntimeError, match="inside the sandbox"):
        cli.run_job(NFET, tmp_path)
    with pytest.raises(RuntimeError, match="inside the sandbox"):
        cli.run_validate_job(NFET, tmp_path)


def test_validate_refuses_an_uncommitted_calibration(tmp_path, monkeypatch, capsys):
    from gf180tcad.calibrate import __main__ as cli

    absent = cv.REPO_ROOT / "results" / "tcad" / "calibration" / "absent" / f"{NFET}.json"
    monkeypatch.setattr(cli, "calibration_file", lambda device: absent)
    argv = ["validate", "--device", NFET, "--out", str(tmp_path / "root")]
    assert cli.main(argv) == 2
    assert "must be committed" in capsys.readouterr().err
    assert not (tmp_path / "root").exists()


def test_cli_requires_known_choices():
    from gf180tcad.calibrate import __main__ as cli

    for argv in (
        ["run", "--device", "nfet_03v3", "--out", "x"],
        ["fit", "--device", NFET, "--out", "x"],
        ["validate", "--device", NFET],
    ):
        with pytest.raises(SystemExit):
            cli.main(argv)


@pytest.mark.parametrize("command", ["run", "validate"])
def test_host_side_writes_the_committed_provenance(tmp_path, monkeypatch, command):
    """With each sandbox job's output replaced by the committed files, the host side of ``run``
    and ``validate`` writes the committed tree's provenance.json byte for byte: both trees are
    stamped by their writer, gf180tcad.calibrate.__main__, and its own hash (issue #34)."""
    import shutil
    from pathlib import Path

    from gf180tcad.calibrate import __main__ as cli

    committed = cv.CALIBRATION_ROOT if command == "run" else cv.VALIDATION_ROOT

    def fake_job(cmd, scratch, what):
        device = cmd[cmd.index("--device") + 1]
        for f in committed.glob(f"{device}*.json"):
            shutil.copyfile(f, Path(scratch) / f.name)
        return ""

    monkeypatch.setattr(cli, "_sandbox_job", fake_job)
    root = tmp_path / "out"
    for device in process.DEVICES:
        assert cli.main([command, "--device", device, "--out", str(root)]) == 0
    prov = json.loads((root / "provenance.json").read_bytes())
    assert prov["generator"] == "gf180tcad.calibrate.__main__"
    assert (root / "provenance.json").read_bytes() == (committed / "provenance.json").read_bytes()


# --- the committed results (host) ----------------------------------------------------------------

DOC = cv.REPO_ROOT / "docs" / "comparison" / "cv-agreement.md"


@pytest.mark.parametrize("device", process.DEVICES)
def test_committed_calibration(device):
    res = cv.load_frozen(device)
    proc = process.load(device)
    assert res.budget_used == 3 and res.budget == cv.BUDGET
    assert set(res.per_geometry) == {geometry_id(g) for g in cal_geometries(device)}
    assert all(c["geometry"]["role"] == "calibration" for c in res.per_geometry.values())
    assert res.start == {n: proc.params[n].value for n in process.TUNABLES}
    for n, v in res.values.items():
        lo, hi = proc.params[n].bounds
        assert res.bounds[n] == (lo, hi) and lo <= v <= hi
        near = min(v - lo, hi - v) <= cv.BOUND_HIT_REL * (hi - lo)
        assert (n in res.bound_hits) == near
    assert res.verdict == cv.worst(c["verdict"] for c in res.per_geometry.values())
    assert {k: res.optimiser[k] for k in cv.LSQ} == dict(cv.LSQ)


@pytest.mark.parametrize("device", process.DEVICES)
def test_committed_validation(device):
    frozen = cv.load_frozen(device)
    data = json.loads((cv.VALIDATION_ROOT / f"{device}.json").read_bytes())
    assert data["param_sha256"] == frozen.param_sha256
    assert data["values"] == frozen.values
    cal = cv.CALIBRATION_ROOT / f"{device}.json"
    assert data["calibration_file_sha256"] == calibration.sha256_file(cal)
    assert set(data["one_d"]) == {geometry_id(g) for g in val_geometries(device)}
    assert set(data["two_d"]) == {geometry_id(g) for g in DEVICES[device].geometries}
    for gid, c in data["one_d"].items():
        g = next(x for x in DEVICES[device].geometries if geometry_id(x) == gid)
        assert c["causes"] == cv.causes(device, g)


def _doc_row(c: dict) -> str:
    m, g = c["metrics"], c["geometry"]
    return (
        f"| {g['w_um']:g} | {g['l_um']:g} | {g['role']} | {100 * m['plateau_acc_max_rel']:.2f} | "
        f"{100 * m['plateau_inv_max_rel']:.2f} | {1000 * m['dv_dep_v']:+.1f} | "
        f"{1000 * m['dv_inv_v']:+.1f} | {100 * m['depletion_max_rel']:.1f} | {c['verdict']} |"
    )


@pytest.mark.parametrize("device", process.DEVICES)
def test_docs_quote_the_committed_results(device):
    """The tables of docs/comparison/cv-agreement.md are the committed numbers."""
    text = DOC.read_text(encoding="utf-8")
    res = cv.load_frozen(device)
    val = json.loads((cv.VALIDATION_ROOT / f"{device}.json").read_bytes())
    for c in [*res.per_geometry.values(), *val["one_d"].values()]:
        assert _doc_row(c) in text, _doc_row(c)
    v = res.values
    lo, hi = res.bounds["t_ox_eff_nm"]
    rows = (
        f"| {{term}}`{device}` | `t_ox_eff_nm` | nm | {v['t_ox_eff_nm']:.3f} | {lo:g} | {hi:g} |",
        f"| {{term}}`{device}` | `n_ch_cm3` | cm⁻³ | {v['n_ch_cm3']:.3e} |".replace("e+", "e"),
        f"| {{term}}`{device}` | `dv_fb_v` | mV | {1000 * v['dv_fb_v']:+.1f} | −200 | +200 |",
    )
    for row in rows:
        assert row in text, row
    assert f"reached | {res.optimiser['nfev']} |" in text
    cc = res.cox_check
    for x in (cc["c_ox_ff_per_um2"], cc["c_per_area_acc_ff_per_um2"]):
        assert f"{x:.3f}" in text
    assert res.bound_hits == {} and "No value is within 1e-3 of a bound" in text


# --- in the TCAD image ---------------------------------------------------------------------------


@pytest.mark.sandbox
def test_calibration_reproduces_the_committed_files(tmp_path):
    """run (in the sandbox) gives the committed calibration files byte for byte (the claim
    "two runs give byte-identical files" of docs/comparison/cv-agreement.md)."""
    from gf180tcad.calibrate import __main__ as cli

    root = tmp_path / "out"
    for device in process.DEVICES:
        assert cli.main(["run", "--device", device, "--out", str(root)]) == 0
    names = [f"{d}{s}" for d in process.DEVICES for s in (".json", cv.RESULT_SUFFIX)]
    for name in (*names, "provenance.json"):
        assert (root / name).read_bytes() == (cv.CALIBRATION_ROOT / name).read_bytes(), name


@pytest.mark.sandbox
def test_validation_reproduces_the_committed_files(tmp_path):
    """validate (in the sandbox) gives the committed validation files byte for byte."""
    from gf180tcad.calibrate import __main__ as cli

    root = tmp_path / "out"  # any name: the provenance is decided by the files' content
    for device in process.DEVICES:
        assert cli.main(["validate", "--device", device, "--out", str(root)]) == 0
    for name in (*(f"{d}.json" for d in process.DEVICES), "provenance.json"):
        assert (root / name).read_bytes() == (cv.VALIDATION_ROOT / name).read_bytes(), name
