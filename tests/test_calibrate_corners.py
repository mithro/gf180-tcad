# SPDX-License-Identifier: Apache-2.0
"""Task 16a: the corner fits of the three 1D tunables (gf180tcad.calibrate.corners, spec §5.3).

As in tests/test_calibrate_cv.py, the fits here run on the host with the exact 1D C-V
(:func:`gf180tcad.tcad.analytic.lf_cv_uniform`) standing in for DEVSIM, on synthetic SPICE
targets. The corner table data/pdk_corners.json is checked against the committed process files
here and against the card in the image by the sandbox-marked test.
"""

import ast
import hashlib
import json
import math
import re
from pathlib import Path
from types import MappingProxyType

import pytest
from test_calibrate_cv import (
    CORNER_SHAPE,
    GRID,
    Recorder,
    analytic_cv,
    cal_geometries,
    val_geometries,
)

from gf180tcad import sandbox
from gf180tcad.calibrate import corners, cv
from gf180tcad.devices import CORNERS, DEVICES, geometry_id
from gf180tcad.tcad import calibration, process

NFET = "nfet_05v0"
PFET = "pfet_05v0"
REPO = Path(__file__).resolve().parents[1]
TABLE = REPO / "data" / "pdk_corners.json"
CARD_IN_IMAGE = "$PDK_ROOT/gf180mcuD/libs.tech/ngspice/sm141064.ngspice"

# The card's corner offsets that spec §5.3 quotes (V for VTH0, nm for TOXE, XL, XW).
SPEC_OFFSETS = {
    (NFET, "ff"): {"vth0": -0.1298, "toxe": -1.0, "xl": -42.0, "xw": 50.0},
    (NFET, "ss"): {"vth0": 0.1193, "toxe": 1.0, "xl": 70.0, "xw": -50.0},
    (PFET, "ff"): {"vth0": 0.1245, "toxe": -1.0, "xl": -46.5, "xw": 50.0},
    (PFET, "ss"): {"vth0": -0.1225, "toxe": 1.0, "xl": 69.0, "xw": -50.0},
}
SPEC_FACTORS = {"ff": 0.9, "ss": 1.1}
BOOKKEEPING = (
    "xl_nm", "xw_nm", "cgso_f_per_m", "cgdo_f_per_m", "cgsl_f_per_m", "cgdl_f_per_m",
    "cf_f_per_m",
)  # fmt: skip


# --- the corner table --------------------------------------------------------------------------


def test_table_sha256_is_pinned_in_the_module():
    """The table is not a hashed generator file, so the module pins its sha256: a change to the
    table must change corners.py, which the corners entry point's generator_sha256 covers."""
    assert hashlib.sha256(TABLE.read_bytes()).hexdigest() == corners.PDK_CORNERS_SHA256
    assert corners.PDK_CORNERS_FILE == TABLE


def test_table_refused_when_changed(tmp_path):
    bad = tmp_path / "pdk_corners.json"
    bad.write_bytes(TABLE.read_bytes().replace(b"-0.1298", b"-0.1299"))
    with pytest.raises(ValueError, match="sha256"):
        corners.load_table(bad)


def test_table_agrees_with_the_process_files():
    """Same card file and sha256 as the process files; each applied input's card line is the
    process file's line for that key, and its corner parameter is one of that line's ``.param``
    lines in ``.lib typical``; at typical every offset is 0 and every factor 1."""
    t = corners.load_table()
    for device in process.DEVICES:
        proc = process.load(device)
        assert t["card"] == {"file": proc.card.file, "sha256": proc.card.sha256}
        d = t["devices"][device]
        assert (d["model"], d["model_line"]) == (proc.card.model, proc.card.model_line)
        assert set(d["corners"]) == set(CORNERS)
        by_key = {p.bsim_name or p.card_key: p for p in proc.params.values() if p.card_line}
        for key, row in d["inputs"].items():
            if key in by_key and by_key[key].card_key == key:
                p = by_key[key]
                assert row["card_line"] == p.card_line, (device, key)
                lines = {d["corners"]["typical"][row["param"]]["line"]}
                assert lines <= set(p.card_params), (device, key)
            typical = d["corners"]["typical"][row["param"]]["value"]
            assert typical == {"offset": 0.0, "factor": 1.0}[row["kind"]], (device, key)
        params = {row["param"] for row in d["inputs"].values()}
        for corner, values in d["corners"].items():
            assert set(values) == params, (device, corner)
    assert t["lib_lines"] == {c: t["lib_lines"][c] for c in CORNERS}


@pytest.mark.parametrize(("device", "corner"), sorted(SPEC_OFFSETS))
def test_table_holds_the_spec_values(device, corner):
    """The pinned card's ff and ss values are those spec §5.3 quotes from upstream."""
    for key, nm_or_v in SPEC_OFFSETS[(device, corner)].items():
        scale = 1.0 if key == "vth0" else 1e9
        assert math.isclose(corners.card_shift(device, corner, key) * scale, nm_or_v), key
    for key in ("cgso", "cgdo", "cgsl", "cgdl"):
        assert corners.card_shift(device, corner, key) == SPEC_FACTORS[corner], key


def test_pfet_toxp_follows_toxe():
    """The pfet card sets no TOXP (BSIM4: TOXP = TOXE), so only the nfet has a TOXP line."""
    t = corners.load_table()["devices"]
    assert "toxp" in t[NFET]["inputs"] and "toxp" not in t[PFET]["inputs"]
    assert process.load(PFET).params["toxp_nm"].card_key == "toxe"


# --- the corner's bounds and card values -------------------------------------------------------


@pytest.mark.parametrize("device", process.DEVICES)
@pytest.mark.parametrize("corner", corners.FIT_CORNERS)
def test_corner_bounds_shift_oxide(device, corner):
    tt = process.load(device).params["t_ox_eff_nm"].bounds
    dtox_nm = corners.card_shift(device, corner, "toxe") * 1e9
    lo, hi = corners.corner_bounds(device, corner)["t_ox_eff_nm"]
    assert (lo, hi) == (tt[0] + dtox_nm, tt[1] + dtox_nm)
    assert corners.corner_bounds(device, corner)["n_ch_cm3"] == tuple(
        process.load(device).params["n_ch_cm3"].bounds
    )


@pytest.mark.parametrize("device", process.DEVICES)
def test_corner_bounds_shift_flatband(device):
    """ff and ss move the flat-band bounds by +dVTH0 in true-sign gate bias, for both devices:
    the nfet ff bounds towards negative Vg, the pfet ff bounds towards positive Vg."""
    tt = process.load(device).params["dv_fb_v"].bounds
    for corner in corners.FIT_CORNERS:
        dvth0 = corners.card_shift(device, corner, "vth0")
        lo, hi = corners.corner_bounds(device, corner)["dv_fb_v"]
        assert (lo, hi) == (tt[0] + dvth0, tt[1] + dvth0), corner
    ff = corners.corner_bounds(device, "ff")["dv_fb_v"][0]
    assert (ff < tt[0]) == (device == NFET)


def test_corner_bounds_typical_refused():
    with pytest.raises(cv.CalibrationLeak):
        corners.corner_bounds(NFET, "typical")
    with pytest.raises(ValueError):
        corners.corner_bounds(NFET, "tt")


@pytest.mark.parametrize("device", process.DEVICES)
def test_corner_bookkeeping_uses_corner_card(device):
    """The area and overlap bookkeeping of an ss fit uses the ss XL, XW and overlap values (and
    the BSIM4 default CF of the ss TOXE); the TT process description is unchanged."""
    before = process.load(device)
    book = corners.corner_bookkeeping(device, "ss")
    assert set(book) == set(BOOKKEEPING)
    v = before.values()
    assert math.isclose(book["xl_nm"], v["xl_nm"] + corners.card_shift(device, "ss", "xl") * 1e9)
    assert math.isclose(book["xw_nm"], v["xw_nm"] + corners.card_shift(device, "ss", "xw") * 1e9)
    for name in ("cgso", "cgdo", "cgsl", "cgdl"):
        assert book[f"{name}_f_per_m"] == v[f"{name}_f_per_m"] * 1.1, name
    toxe_m = before.card_values()["toxe"] + corners.card_shift(device, "ss", "toxe")
    cf = process.cf_default_f_per_m({**before.card_values(), "toxe": toxe_m})
    assert book["cf_f_per_m"] == cf and cf < v["cf_f_per_m"]
    proc = corners.corner_process(device, "ss")
    assert {k: proc.values()[k] for k in BOOKKEEPING} == book
    card = proc.card_values()
    assert math.isclose(card["xl"], book["xl_nm"] * 1e-9) and card["cgso"] == book["cgso_f_per_m"]
    assert process.load(device) == before
    assert {k: v[k] for k in BOOKKEEPING} == {
        k: x for k, x in corners.corner_bookkeeping(device, "typical").items()
    }


def test_corner_process_shifts_tunables():
    proc = corners.corner_process(PFET, "ff")
    shifts = corners.tunable_shifts(PFET, "ff")
    tt = process.load(PFET)
    for n in process.TUNABLES:
        assert proc.params[n].value == tt.params[n].value + shifts[n], n
        assert proc.params[n].bounds == corners.corner_bounds(PFET, "ff")[n], n
    assert shifts["n_ch_cm3"] == 0.0


def test_with_corner_card_refuses_tunables():
    proc = process.load(NFET)
    for name in ("t_ox_eff_nm", "toxe_nm", "ngate_cm3", "vth0_v"):
        with pytest.raises(ValueError, match="reference-bookkeeping"):
            corners.with_corner_card(proc, {name: 1.0})
    with pytest.raises(KeyError):
        corners.with_corner_card(proc, {"no_such": 1.0})
    out = corners.with_corner_card(proc, {"xl_nm": 7.0})
    assert out.values()["xl_nm"] == 7.0 and proc.values()["xl_nm"] == 0.0
    with pytest.raises(ValueError):
        proc.with_values({"xl_nm": 7.0})  # with_values keeps refusing fixed parameters


# --- the guards --------------------------------------------------------------------------------


def corner_targets(device, corner, truth, geometries, grid=GRID):
    """Synthetic targets whose ``corner`` curve is the 1D model at ``truth`` with that corner's
    bookkeeping; the other corners are the TT shape of test_calibrate_cv (CORNER_SHAPE)."""
    tt = process.load(device)
    cproc = corners.corner_process(device, corner)
    pol = 1 if tt.polarity == "n" else -1
    vg = tuple(pol * x + 0.0 for x in grid)
    out = {}
    for g in geometries:
        curves = {}
        meta = {"engine": "ngspice", "device": device, "geometry_id": geometry_id(g), "sweep": "cv"}
        for c, (scale, shift) in CORNER_SHAPE.items():
            if c == corner:
                m = analytic_cv(device, truth, vg)
                total = m.area_scaled(g, cproc)[3]
            else:
                m = analytic_cv(device, {**truth, "dv_fb_v": truth["dv_fb_v"] + pol * shift}, vg)
                total = tuple(scale * x for x in m.area_scaled(g, tt)[3])
            curves[c] = cv.Curve(vg, tuple(total), MappingProxyType({**meta, "corner": c}))
        out[geometry_id(g)] = cv.Target(g, curves[corner], MappingProxyType(curves))
    return out


# A truth inside the ss bounds of the nfet: oxide 1 nm and the flat band 0.1193 V up from TT's.
SS_TRUTH = {"t_ox_eff_nm": 16.9, "n_ch_cm3": 2.1e17, "dv_fb_v": 0.06 + 0.1193}


@pytest.fixture(scope="module")
def ss_fit():
    targets = corner_targets(NFET, "ss", SS_TRUTH, cal_geometries())
    held = corner_targets(NFET, "ss", SS_TRUTH, val_geometries())
    sim = Recorder()
    res = corners.calibrate_corner(
        NFET, "ss", geometries=cal_geometries(), targets=targets, held_out=held, simulate=sim
    )
    return res, sim, (targets, held)


def test_typical_refused():
    targets = corner_targets(NFET, "ss", SS_TRUTH, cal_geometries())
    with pytest.raises(cv.CalibrationLeak, match="typical"):
        corners.calibrate_corner(NFET, "typical", geometries=cal_geometries(), targets=targets)


def test_validation_geometry_refused():
    g = next(x for x in DEVICES[NFET].geometries if x.role == "validation")
    with pytest.raises(cv.CalibrationLeak):
        corners.calibrate_corner(NFET, "ss", geometries=(g,), targets={}, simulate=Recorder())


def test_wrong_corner_target_refused():
    """A target that is not the corner's own ngspice cv curve is refused before simulating."""
    targets = corner_targets(NFET, "ss", SS_TRUTH, cal_geometries())
    sim = Recorder()
    with pytest.raises(cv.CalibrationLeak):
        corners.calibrate_corner(NFET, "ff", geometries=cal_geometries(), targets=targets,
                                 simulate=sim)  # fmt: skip
    assert sim.calls == []


@pytest.mark.parametrize(
    "out",
    ["results/tcad/calibration", "results/tcad/validation", "results/tcad/moscap1d", "results"],
)
def test_corner_cannot_write_calibration_dir(ss_fit, out):
    res = ss_fit[0]
    with pytest.raises(cv.CalibrationLeak):
        res.write(REPO / out)
    with pytest.raises(cv.CalibrationLeak):
        corners.check_out(REPO / out)
    corners.check_out(REPO / "results" / "tcad" / "corners")  # the tree itself is allowed


# --- the fit -----------------------------------------------------------------------------------


def test_recovers_known_params_at_a_corner(ss_fit):
    res, sim, _ = ss_fit
    r = res.result
    assert res.corner == "ss" and r.device == NFET
    assert math.isclose(r.values["t_ox_eff_nm"], SS_TRUTH["t_ox_eff_nm"], rel_tol=5e-3)
    assert math.isclose(r.values["n_ch_cm3"], SS_TRUTH["n_ch_cm3"], rel_tol=5e-3)
    assert abs(r.values["dv_fb_v"] - SS_TRUTH["dv_fb_v"]) <= 1e-3
    assert r.bound_hits == {} and r.verdict == "Agree"
    assert r.bounds == corners.corner_bounds(NFET, "ss")
    assert r.start == {n: corners.corner_process(NFET, "ss").params[n].value
                       for n in process.TUNABLES}  # fmt: skip
    for n, v in r.start.items():  # least_squares moves a start on a bound just inside it
        assert math.isclose(sim.calls[0][n], v, rel_tol=1e-9), n
    assert {k: r.optimiser[k] for k in cv.LSQ} == dict(cv.LSQ)
    d = res.to_dict()
    assert d["reference"] == {"corner": "ss", "engine": "ngspice", "sweep": "cv"}
    assert d["corner"]["bookkeeping"] == corners.corner_bookkeeping(NFET, "ss")
    assert d["corner"]["tunable_shifts"] == corners.tunable_shifts(NFET, "ss")
    assert d["corner"]["pdk_corners_sha256"] == corners.PDK_CORNERS_SHA256
    assert set(d["held_out"]) == {
        geometry_id(g) for g in DEVICES[NFET].geometries if g.role == "validation"
    }
    for gid, c in d["held_out"].items():
        g = next(x for x in DEVICES[NFET].geometries if geometry_id(x) == gid)
        assert c["causes"] == cv.causes(NFET, g) and c["verdict"] in cv.VERDICTS


def test_never_simulated_outside_the_corner_bounds(ss_fit):
    _, sim, _ = ss_fit
    b = corners.corner_bounds(NFET, "ss")
    for call in sim.calls:
        for n, v in call.items():
            assert b[n][0] <= v <= b[n][1], (n, v)


def test_corner_fits_deterministic(ss_fit, tmp_path):
    res, _, (targets, held) = ss_fit
    again = corners.calibrate_corner(
        NFET,
        "ss",
        geometries=cal_geometries(),
        targets=targets,
        held_out=held,
        simulate=Recorder(),
    )
    res.write(tmp_path / "a")
    again.write(tmp_path / "b")
    name = Path(NFET) / "ss.json"
    assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    assert json.loads((tmp_path / "a" / name).read_bytes()) == res.to_dict()


# --- the summary -------------------------------------------------------------------------------


def _fake_fit(device, corner, values, hits=None):
    """A corner result file's content with the given values (the summary reads only these keys)."""
    b = corners.corner_bounds(device, corner)
    return {
        "bound_hits": hits or {},
        "bounds": {k: list(v) for k, v in b.items()},
        "corner": {"name": corner, "pdk_corners_sha256": corners.PDK_CORNERS_SHA256},
        "device": device,
        "held_out": {"w1p6_l0p70": {"verdict": "Agree"}},
        "per_geometry": {"w10p0_l10p00": {"verdict": "Agree"}},
        "reference": {"corner": corner, "engine": "ngspice", "sweep": "cv"},
        "values": values,
        "verdict": "Agree",
    }


def _write_fits(root, device, fits):
    (root / device).mkdir(parents=True, exist_ok=True)
    for corner, data in fits.items():
        (root / device / f"{corner}.json").write_text(json.dumps(data), encoding="utf-8")


def _synthetic_fits(device):
    """Corner values: the typical fit plus each corner's card shift, and n_ch spread by 10 %."""
    tt = cv.load_frozen(device).values
    out = {}
    for i, c in enumerate(corners.FIT_CORNERS):
        s = corners.tunable_shifts(device, c)
        out[c] = _fake_fit(device, c, {
            "dv_fb_v": tt["dv_fb_v"] + s["dv_fb_v"],
            "n_ch_cm3": tt["n_ch_cm3"] * (0.9 + 0.05 * i),
            "t_ox_eff_nm": tt["t_ox_eff_nm"] + s["t_ox_eff_nm"],
        })  # fmt: skip
    return out


def test_typical_row_is_task12_value(tmp_path):
    for device in process.DEVICES:
        _write_fits(tmp_path, device, _synthetic_fits(device))
        s = corners.summary(device, root=tmp_path)
        committed = json.loads((cv.CALIBRATION_ROOT / f"{device}.json").read_bytes())
        for n in process.TUNABLES:
            assert s["tunables"][n]["typical"] == committed["values"][n], n
        cal = cv.CALIBRATION_ROOT / f"{device}.json"
        assert s["typical_source"]["calibration_file_sha256"] == calibration.sha256_file(cal)


def test_summary_min_max_and_corner(tmp_path):
    fits = _synthetic_fits(NFET)
    _write_fits(tmp_path, NFET, fits)
    s = corners.summary(NFET, root=tmp_path)
    tt = cv.load_frozen(NFET).values
    tox = s["tunables"]["t_ox_eff_nm"]
    assert (tox["min_corner"], tox["max_corner"]) == ("ff", "ss")
    assert tox["min"] == fits["ff"]["values"]["t_ox_eff_nm"]
    assert tox["max"] == fits["ss"]["values"]["t_ox_eff_nm"]
    assert tox["spread"] == tox["max"] - tox["min"]
    assert tox["min_at_bound"] is None and tox["max_at_bound"] is None
    assert tox["values"] == {
        "typical": tt["t_ox_eff_nm"],
        **{c: fits[c]["values"]["t_ox_eff_nm"] for c in corners.FIT_CORNERS},
    }
    nch = s["tunables"]["n_ch_cm3"]
    assert nch["min_corner"] == "ff" and nch["card_shift"] is None
    fb = s["tunables"]["dv_fb_v"]  # nfet: ff lowers the flat band, ss raises it
    assert (fb["min_corner"], fb["max_corner"]) == ("ff", "ss")
    assert set(s["corners"]) == set(CORNERS)
    assert s["corners"]["ss"]["verdict"] == "Agree"
    assert s["corners"]["ss"]["held_out"] == {"w1p6_l0p70": "Agree"}
    assert s["pdk_corners_sha256"] == corners.PDK_CORNERS_SHA256


def test_min_max_on_a_bound_reported_as_bound(tmp_path):
    fits = _synthetic_fits(NFET)
    lo = corners.corner_bounds(NFET, "ff")["t_ox_eff_nm"][0]
    fits["ff"]["values"]["t_ox_eff_nm"] = lo + 1e-6  # within 1e-3 of the bound width: a hit
    fits["ff"]["bound_hits"] = {"t_ox_eff_nm": "lower"}
    _write_fits(tmp_path, NFET, fits)
    tox = corners.summary(NFET, root=tmp_path)["tunables"]["t_ox_eff_nm"]
    assert tox["min_corner"] == "ff"
    assert tox["min"] == lo and tox["min_at_bound"] == "lower"
    assert tox["max_at_bound"] is None


def test_card_cross_check_reported(tmp_path):
    """The oxide and flat-band shifts of the fit are set beside the card's TOXE and VTH0 shifts,
    with their difference, at every corner."""
    fits = _synthetic_fits(NFET)
    fits["ss"]["values"]["t_ox_eff_nm"] += 0.25
    _write_fits(tmp_path, NFET, fits)
    s = corners.summary(NFET, root=tmp_path)
    tox = s["tunables"]["t_ox_eff_nm"]
    for c in corners.FIT_CORNERS:
        card = corners.card_shift(NFET, c, "toxe") * 1e9
        assert tox["card_shift"][c] == card
        tcad = fits[c]["values"]["t_ox_eff_nm"] - cv.load_frozen(NFET).values["t_ox_eff_nm"]
        assert tox["tcad_shift"][c] == tcad
        assert tox["shift_difference"][c] == tcad - card
    assert math.isclose(tox["shift_difference"]["ss"], 0.25, abs_tol=1e-9)
    fb = s["tunables"]["dv_fb_v"]
    assert fb["card_shift"]["ss"] == corners.card_shift(NFET, "ss", "vth0")


def test_summary_refuses_a_stale_or_foreign_fit(tmp_path):
    fits = _synthetic_fits(NFET)
    fits["ss"]["corner"]["pdk_corners_sha256"] = "0" * 64
    _write_fits(tmp_path, NFET, fits)
    with pytest.raises(ValueError, match="pdk_corners"):
        corners.summary(NFET, root=tmp_path)
    fits = _synthetic_fits(NFET)
    fits["ss"]["reference"]["corner"] = "ff"
    _write_fits(tmp_path, NFET, fits)
    with pytest.raises(ValueError, match="ss"):
        corners.summary(NFET, root=tmp_path)


# --- the command line ----------------------------------------------------------------------------


def test_jobs_refuse_outside_the_sandbox(tmp_path):
    with pytest.raises(RuntimeError, match="sandbox"):
        corners.run_job(NFET, "ss", tmp_path)


def test_cli_refuses_typical_and_unknown():
    for argv in (
        ["run", "--device", NFET, "--corner", "typical", "--out", "x"],
        ["run", "--device", "nfet_03v3", "--corner", "ss", "--out", "x"],
        ["summary", "--device", NFET],
    ):
        with pytest.raises(SystemExit):
            corners.main(argv)


def test_cli_refuses_a_calibration_out(capsys):
    argv = ["run", "--device", NFET, "--corner", "ss", "--out", str(cv.CALIBRATION_ROOT)]
    assert corners.main(argv) == 2
    assert "results/tcad/corners" in capsys.readouterr().err


def test_host_side_writes_the_tree(tmp_path, monkeypatch):
    """``run`` copies the job's corner file into ROOT/<device>/ and stamps ROOT/provenance.json
    with the corners entry point; ``summary`` then writes ROOT/<device>/summary.json."""
    from gf180tcad import tcad

    def fake_job(cmd, scratch, what):
        device, corner = cmd[cmd.index("--device") + 1], cmd[cmd.index("--corner") + 1]
        data = _synthetic_fits(device)[corner]
        (Path(scratch) / device).mkdir(parents=True, exist_ok=True)
        (Path(scratch) / device / f"{corner}.json").write_text(json.dumps(data), "utf-8")
        return ""

    monkeypatch.setattr(corners, "_sandbox_job", fake_job)
    root = tmp_path / "out"
    for c in corners.FIT_CORNERS:
        assert corners.main(["run", "--device", NFET, "--corner", c, "--out", str(root)]) == 0
    assert corners.main(["summary", "--device", NFET, "--out", str(root)]) == 0
    prov = json.loads((root / "provenance.json").read_bytes())
    assert prov == tcad.tree_provenance(root, {"moscap1d": "dev"}, generator=corners.CORNERS_MAIN)
    assert prov["generator"] == "gf180tcad.calibrate.corners"
    assert sorted(p.name for p in (root / NFET).iterdir()) == sorted(
        [f"{c}.json" for c in corners.FIT_CORNERS] + ["summary.json"]
    )


# --- the card in the image (Docker) -------------------------------------------------------------


def _arith(expr: str) -> float:
    """A ``.param`` value: numbers, + - *, unary minus and parentheses only."""

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and type(n.value) in (int, float):
            return float(n.value)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -ev(n.operand)
        if isinstance(n, ast.BinOp) and type(n.op) in (ast.Add, ast.Sub, ast.Mult):
            a, b = ev(n.left), ev(n.right)
            return {ast.Add: a + b, ast.Sub: a - b, ast.Mult: a * b}[type(n.op)]
        raise ValueError(f"cannot evaluate {expr!r}")

    return ev(ast.parse(expr, mode="eval"))


def _section_end(lines: list[str], start: int, pattern: str) -> int:
    return next(n for n in range(start + 1, len(lines) + 1) if re.match(pattern, lines[n - 1]))


def check_corner_table(card: bytes) -> None:
    """Every entry of data/pdk_corners.json is the card's own line, and nothing is missing: each
    ``.lib <corner>`` line; per device and corner, each corner parameter's ``.param`` line inside
    that section with its expression and value; per device, every line of its model that uses a
    corner parameter, as an input or another line, with its expression and kind."""
    t = json.loads(TABLE.read_bytes())
    assert hashlib.sha256(card).hexdigest() == t["card"]["sha256"]
    lines = card.decode("utf-8").splitlines()
    for corner, n in t["lib_lines"].items():
        assert lines[n - 1].strip() == f".lib {corner}", corner
    for device, d in t["devices"].items():
        start = d["model_line"]
        assert lines[start - 1].split()[:2] == [".model", d["model"]], device
        model = range(start, _section_end(lines, start, r"\.model |\.endl"))
        params = set(d["corners"]["typical"])
        for corner, values in d["corners"].items():
            lib = t["lib_lines"][corner]
            sec = range(lib, _section_end(lines, lib, r"\.endl"))
            found = {}
            for n in sec:
                if lines[n - 1].strip().startswith(".param "):
                    k, e = process.parse_card_assignment(lines[n - 1])
                    if k in params:
                        found[k] = {"expr": e, "line": n, "value": _arith(e)}
            assert found == values, (device, corner)
        rows = {**d["inputs"], **d["other_lines"]}
        uses = {}
        for n in model:
            if lines[n - 1].startswith("+"):
                k, e = process.parse_card_assignment(lines[n - 1])
                if process.card_expr_names(e) & params:
                    uses[k] = (n, e)
        assert {k: (r["card_line"], r["expr"]) for k, r in rows.items()} == uses, device
        for k, r in rows.items():
            num = r"-?[0-9.]+(?:[eE][-+]?[0-9]+)?"
            p = re.escape(r["param"])
            kind = ("offset" if re.fullmatch(rf"{num}\+{p}", r["expr"]) else
                    "factor" if re.fullmatch(rf"{num}\*{p}", r["expr"]) else "other")  # fmt: skip
            assert r["kind"] == kind, (device, k)


@pytest.mark.sandbox
def test_corner_table_matches_pinned_pdk(tmp_path):
    out = tmp_path / "card"
    out.mkdir()
    sandbox.run(["sh", "-c", f'cp "{CARD_IN_IMAGE}" /work/out/card'], out_dir=out, mem="1g", cpus=1)
    check_corner_table((out / "card").read_bytes())


# --- the figure of the corner-fit section (docs/reproduce/index.md) --------------------------


def test_corner_figure_reads_the_committed_curves():
    """The figure draws the five committed ngspice cv curves of its geometry, unaltered."""
    from gf180tcad.explain import figures

    curves = figures.corner_cv_curves(figures.CORNER_DEVICE, figures.CORNER_GEOMETRY)
    assert list(curves) == list(CORNERS)
    g = next(x for x in DEVICES[NFET].geometries if geometry_id(x) == figures.CORNER_GEOMETRY)
    for c, (u, cgg) in curves.items():
        ref = cv.load_curve(NFET, geometry_id(g), c)
        assert sorted(zip(u.tolist(), cgg.tolist())) == sorted(zip(ref.vg, ref.cgg_ff)), c
    assert set(figures.CORNER_HIGHLIGHT) <= set(corners.FIT_CORNERS)
    light, dark = figures.corner_cv("light"), figures.corner_cv("dark")
    assert light.startswith(b"<?xml") and light != dark
