# SPDX-License-Identifier: Apache-2.0
"""The 1D MOS capacitor (gf180tcad.tcad.moscap1d) and its CLI (python -m gf180tcad.tcad).

The sandbox-marked tests run the TCAD in the image the 1D results are generated with
(``RESULTS_IMAGE["moscap1d"]``, the dev-HEAD image; ``pytest -m sandbox``): one container runs
tests/tcad/moscap1d_driver.py for the physics tests, and the CLI runs twice for the
byte-identity test. test_stable_and_dev_images_agree runs the 1D CLIs on both images. The others
run on the host, from committed files.
"""

import json
import math
import shutil
from pathlib import Path

import pytest

from gf180tcad import io, sandbox
from gf180tcad.devices import Geometry
from gf180tcad.tcad import (
    RESULTS_IMAGE,
    analytic,
    calibration,
    image_ref,
    meshconv,
    moscap1d,
    process,
)
from gf180tcad.tcad import __main__ as cli
from gf180tcad.tcad.mesh import MeshSpec
from gf180tcad.tcad.process import CONSTANTS

REPO = Path(__file__).resolve().parents[2]
SPICE = REPO / "results" / "spice" / "ngspice" / "typical"
TREE = REPO / "results" / "tcad" / "moscap1d"
DEVICES = process.DEVICES
W10L10 = Geometry(10.0, 10.0, "calibration")
W10L2 = Geometry(10.0, 2.0, "calibration")
SHIFT_VG = (-3.0, -1.0, -0.2, 0.3, 0.8, 2.0)  # as tests/tcad/moscap1d_driver.py


def _cv(device: str, c: float, vg=(0.0,)) -> moscap1d.MoscapCV:
    """A constant-C MoscapCV (no simulation)."""
    pts = tuple(moscap1d.Point(True, 1, 0.0, 0.0) for _ in vg)
    stack = moscap1d.stack_of(process.load(device))
    return moscap1d.MoscapCV(
        device, tuple(vg), (c,) * len(vg), pts, "qs", CONSTANTS, MeshSpec.DEFAULT_1D,
        stack, moscap1d.REL_TOL, 1,
    )  # fmt: skip


def _spice(device: str, gid: str) -> dict:
    return json.loads((SPICE / device / gid / "metrics.json").read_bytes())["metrics"]


# --- units and areas (host) ------------------------------------------------------------------


def test_units():
    assert analytic.f_per_cm2_to_ff_per_um2(1.0) == 1e7  # 1 F/cm^2 = 1e15 fF / 1e8 um^2
    cox = analytic.f_per_cm2_to_ff_per_um2(analytic.cox_f_per_cm2(15.2, 3.9, CONSTANTS))
    assert math.isclose(cox, 2.2718, rel_tol=1e-4)
    card = process.load("nfet_05v0").card_values()
    leff, weff = moscap1d.cv_geometry_um(card, W10L10)
    assert math.isclose(leff * weff, 98.92, rel_tol=1e-12)  # (L - 2*DLC)*W, DLC = 54 nm
    _, intrinsic, _, _ = _cv("nfet_05v0", cox).area_scaled(W10L10)
    assert math.isclose(intrinsic[0], 224.73, rel_tol=1e-4)


def test_pfet_area_uses_dwc():
    """The pfet card sets no DWC, so BSIM4's WeffCV uses DWC = WINT = 49 nm."""
    card = process.load("pfet_05v0").card_values()
    leff, weff = moscap1d.cv_geometry_um(card, W10L10)
    assert math.isclose(leff, 10 - 2 * 0.0074, rel_tol=1e-12)
    assert math.isclose(weff, 10 - 2 * 0.049, rel_tol=1e-12)


def test_area_scaled_total_is_the_sum():
    cv = _cv("pfet_05v0", 2.0, vg=(-5.0, 0.0, 5.0))
    vg, a, b, t = cv.area_scaled(W10L2)
    assert vg == (-5.0, 0.0, 5.0)
    assert t == tuple(x + y for x, y in zip(a, b, strict=True))
    with pytest.raises(ValueError, match="is not"):
        cv.area_scaled(W10L2, process.load("nfet_05v0"))


def test_parasitic_hand_values():
    """Deep accumulation and inversion limits of the BSIM4 overlap equations (W10/L10)."""
    card = process.load("nfet_05v0").card_values()
    cgbo = 1e-13 * 9.892e-6 * 1e15
    acc, inv = moscap1d.parasitic_ff(card, [-50.0, 50.0], W10L10)
    # inversion: CGSO + CGSL + CF per side; deep accumulation: the CGSL term vanishes
    assert math.isclose(inv, 2 * (1e-10 + 1.5e-10 + card["cf"]) * 1e-5 * 1e15 + cgbo, rel_tol=1e-3)
    assert math.isclose(acc, 2 * (1e-10 + card["cf"]) * 1e-5 * 1e15 + cgbo, rel_tol=0.05)
    # the pfet's accumulation is at +vg (NMOS convention type*vg)
    pc = process.load("pfet_05v0").card_values()
    p_acc, p_inv = moscap1d.parasitic_ff(pc, [5.0, -5.0], W10L10)
    assert p_acc < p_inv


def test_spice_intrinsic_slope():
    """The brief's SPICE per-area slopes (Cgg(L10) - Cgg(L2))/(8 um * W) from metrics.json."""
    want = {"nfet_05v0": (2.106, 2.083), "pfet_05v0": (2.195, 2.064)}
    for device, (acc, inv) in want.items():
        a, b = _spice(device, "w10p0_l10p00"), _spice(device, "w10p0_l2p00")
        assert round((a["cgg_acc_ff"] - b["cgg_acc_ff"]) / 80, 3) == acc
        assert round((a["cgg_inv_ff"] - b["cgg_inv_ff"]) / 80, 3) == inv


def spice_intercept_ff(device: str, key: str) -> float:
    """The SPICE Cgg minus the L10/L2 slope times LeffCV: the L-independent part (fF)."""
    card = process.load(device).card_values()
    a, b = _spice(device, "w10p0_l10p00")[key], _spice(device, "w10p0_l2p00")[key]
    l10, _ = moscap1d.cv_geometry_um(card, W10L10)
    l2, _ = moscap1d.cv_geometry_um(card, W10L2)
    return a - (a - b) / (l10 - l2) * l10


@pytest.mark.parametrize("device", DEVICES)
def test_parasitics_match_spice_intercept(device):
    """Bookkeeping sanity: the BSIM4 overlap terms are within 25 % of the SPICE intercept."""
    proc = process.load(device)
    pol = 1 if proc.polarity == "n" else -1
    card = proc.card_values()
    for key, vg in (("cgg_acc_ff", -5.0 * pol), ("cgg_inv_ff", 5.0 * pol)):
        (par,) = moscap1d.parasitic_ff(card, [vg], W10L10)
        spice = spice_intercept_ff(device, key)
        assert abs(par - spice) <= 0.25 * spice, (device, key, par, spice)


def test_nfet_intercept_brief_value():
    assert round(spice_intercept_ff("nfet_05v0", "cgg_acc_ff"), 1) == 4.0


# --- the stack (host) ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("device", "body", "gate"), [("nfet_05v0", -1.7e17, 1e20), ("pfet_05v0", 1.7e17, -3.6e19)]
)
def test_stack_of_the_start_values(device, body, gate):
    s = moscap1d.stack_of(process.load(device))
    assert (s.body_net_cm3, s.gate_net_cm3) == (body, gate)
    assert s.t_ox_nm == {"nfet_05v0": 15.2, "pfet_05v0": 15.6}[device]
    assert s.eps_ox == 3.9
    assert s.body_dopant == ("acceptor" if body < 0 else "donor")
    assert s.gate_dopant == ("donor" if gate > 0 else "acceptor")


def test_stack_validated():
    with pytest.raises(ValueError):
        moscap1d.Stack("x", 1e17, 1e20, 15.0, 3.9)
    with pytest.raises(ValueError):
        moscap1d.Stack("n", -1e17, 1e20, 15.0, 3.9)


# --- CLI (host) ------------------------------------------------------------------------------


def test_cli_requires_known_choices(capsys):
    for argv in (
        ["moscap", "--device", "nfet_05v0", "--dim", "3", "--params", "start", "--out", "x"],
        ["moscap", "--device", "nfet_03v3", "--dim", "1", "--params", "start", "--out", "x"],
        ["moscap", "--device", "nfet_05v0", "--dim", "1", "--params", "fitted", "--out", "x"],
    ):
        with pytest.raises(SystemExit):
            cli.main(argv)


def test_calibrated_refused_without_calibration(tmp_path, capsys):
    assert not (REPO / "results" / "tcad" / "calibration" / "nfet_05v0.json").exists()
    argv = ["moscap", "--device", "nfet_05v0", "--dim", "1", "--params", "calibrated"]
    assert cli.main([*argv, "--out", str(tmp_path / "root")]) == 2
    assert "results/tcad/calibration/nfet_05v0.json" in capsys.readouterr().err
    assert not (tmp_path / "root").exists()


def test_job_refuses_outside_the_sandbox(tmp_path):
    with pytest.raises(RuntimeError, match="inside the sandbox"):
        cli.run_job("nfet_05v0", "start", tmp_path)


# --- the committed start results (host) ------------------------------------------------------


@pytest.mark.parametrize("device", DEVICES)
def test_committed_start_results(device):
    job = TREE / device / "start"
    cols, meta = io.read_csv(job / moscap1d.PER_AREA_CSV)
    assert tuple(cols) == moscap1d.CSV_COLUMNS
    assert meta == {
        "device": device,
        "dim": "1",
        "method": "qs",
        "params": "start",
        "units": moscap1d.CSV_UNITS,
    }
    # the SPICE cv grid in its order (pfet: +5 to -5 V), no point dropped
    spice, _ = io.read_csv(SPICE / device / "w10p0_l10p00" / "cv.csv")
    assert tuple(cols["vg"]) == tuple(spice["vg"]) == cli.job_vg(process.load(device))
    assert all(0 <= r <= moscap1d.REL_TOL for r in cols["rel_error"])
    assert all(a <= moscap1d.ABS_TOL for a in cols["abs_error"])
    # iterations are written as integers
    text = (job / moscap1d.PER_AREA_CSV).read_text(encoding="utf-8").splitlines()
    rows = [ln.split(",") for ln in text if ln and not ln.startswith("#")][1:]
    assert all(r[-1].isdigit() for r in rows)
    cv = moscap1d.read(job)
    assert cv.mesh == meshconv.selected_spec(device, 1) and cv.constants == CONSTANTS
    stack = moscap1d.stack_of(process.load(device))
    cox = analytic.f_per_cm2_to_ff_per_um2(analytic.cox_f_per_cm2(stack.t_ox_nm, stack.eps_ox))
    assert all(0 < c < cox for c in cv.c_per_area_ff_um2)
    assert cv.stack == stack and cv.rel_tol == moscap1d.REL_TOL
    info = json.loads((job / moscap1d.PER_AREA_META).read_bytes())
    proc = process.load(device)
    # start results say where each start value comes from, never "calibrated"
    assert "tunables_provenance" not in info and "calibrated" not in json.dumps(info["tunables"])
    assert info["tunables"] == {
        n: {
            "origin": "start",
            "start_kind": proc.params[n].start_kind,
            "start_source": proc.params[n].start_source,
            "value": proc.params[n].value,
        }
        for n in process.TUNABLES
    }
    starts = {n: proc.params[n].value for n in process.TUNABLES}
    assert info["param_sha256"] == calibration.param_sha256(starts)
    # 1D oxide spacing is min(h_ox, neighbours): the effective spacing is recorded
    spacing = cv.mesh.spacing_um(moscap1d.POLY, moscap1d.OXIDE, moscap1d.BODY)
    assert info["mesh_1d_spacing_um"] == {k: list(v) for k, v in spacing.items()}


# --- in the TCAD image -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def driver(tmp_path_factory) -> dict:
    out = tmp_path_factory.mktemp("driver")
    sandbox.run(
        ["python3", "/work/src/tests/tcad/moscap1d_driver.py"],
        out_dir=out, image=image_ref(RESULTS_IMAGE["moscap1d"]), mem="2g", cpus=1,
    )  # fmt: skip
    return json.loads((out / "driver.json").read_bytes())


@pytest.mark.sandbox
@pytest.mark.parametrize("device", DEVICES)
def test_matches_exact_poisson_boltzmann(driver, device):
    d = driver[device]
    assert all(d["converged"]) and len(d["tcad"]) == len(process.CV_VG)
    worst = max(abs(t / e - 1) for t, e in zip(d["tcad"], d["exact"], strict=True))
    assert worst < 1e-3, worst
    # the LF minimum (and its location) too
    i = min(range(len(d["tcad"])), key=d["tcad"].__getitem__)
    j = min(range(len(d["exact"])), key=d["exact"].__getitem__)
    assert i == j
    assert abs(d["tcad"][i] / d["exact"][j] - 1) < 1e-3


@pytest.mark.sandbox
@pytest.mark.parametrize("device", DEVICES)
def test_flatband_exact(driver, device):
    """At flat band, C = Cox, eps_si/L_D (body) and eps_si/L_D (gate) in series."""
    d = driver[device]
    assert abs(d["c_fb_tcad"] / d["c_fb_series"] - 1) < 1e-3
    assert round(d["vfb"], 3) == {"nfet_05v0": -1.029, "pfet_05v0": 1.003}[device]


@pytest.mark.sandbox
def test_mirror(driver):
    m = driver["mirror"]
    for a, b in zip(m["a_at_minus_vg"], m["b"], strict=True):
        assert math.isclose(b, a, rel_tol=1e-9), (a, b)


@pytest.mark.sandbox
@pytest.mark.parametrize("device", DEVICES)
def test_dv_fb_rigid_shift(driver, device):
    d = driver[device]
    assert process.load(device).values()["dv_fb_v"] == 0.0  # the start has no shift
    assert d["shifted_vg"] == list(SHIFT_VG)  # reported at the requested vg
    assert d["unshifted_vg"] == [v - 0.1 for v in SHIFT_VG]
    for a, b in zip(d["shifted"], d["unshifted"], strict=True):
        assert math.isclose(a, b, rel_tol=1e-12), (a, b)


def _run_cli(root: Path, device: str) -> None:
    argv = ["moscap", "--device", device, "--dim", "1", "--params", "start", "--out", str(root)]
    assert cli.main(argv) == 0


@pytest.mark.sandbox
def test_byte_identical(tmp_path):
    """Two runs give byte-identical files, equal to the committed ones."""
    roots = [tmp_path / "a", tmp_path / "b"]
    for root in roots:
        for device in DEVICES:
            _run_cli(root, device)
    files = sorted(p.relative_to(roots[0]) for p in roots[0].rglob("*") if p.is_file())
    assert [p.as_posix() for p in files] == [
        "nfet_05v0/start/per_area.csv",
        "nfet_05v0/start/per_area.meta.json",
        "pfet_05v0/start/per_area.csv",
        "pfet_05v0/start/per_area.meta.json",
        "provenance.json",
    ]
    for rel in files:
        assert (roots[0] / rel).read_bytes() == (roots[1] / rel).read_bytes(), rel
        assert (roots[0] / rel).read_bytes() == (TREE / rel).read_bytes(), rel


@pytest.mark.sandbox
def test_rerun_replaces_the_job_dir(tmp_path):
    root = tmp_path / "root"
    stale = root / "nfet_05v0" / "start" / "stale.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")
    _run_cli(root, "nfet_05v0")
    assert not stale.exists()
    assert (root / "nfet_05v0" / "start" / moscap1d.PER_AREA_CSV).is_file()
    shutil.rmtree(root)


@pytest.mark.sandbox
def test_stable_and_dev_images_agree(tmp_path):
    """The drift guard between the two TCAD stacks: the 1D data files, mesh convergence and
    moscap1d, are byte-identical whether made on the stable or the dev-HEAD image. Only
    provenance.json differs, and it names the image that made them."""
    trees = {}
    for image in ("stable", "dev"):
        mc, mo = tmp_path / image / "meshconv", tmp_path / image / "moscap1d"
        for device in DEVICES:
            argv = ["meshconv", "--device", device, "--dim", "1", "--out", str(mc)]
            assert cli.main([*argv, "--image", image]) == 0
            argv = ["moscap", "--device", device, "--dim", "1", "--params", "start"]
            assert cli.main([*argv, "--out", str(mo), "--image", image]) == 0
        for root in (mc, mo):
            prov = json.loads((root / "provenance.json").read_bytes())
            assert {k: v["name"] for k, v in prov["images"].items()} == {"moscap1d": image}
        trees[image] = {
            p.relative_to(tmp_path / image).as_posix(): p.read_bytes()
            for p in (tmp_path / image).rglob("*")
            if p.is_file() and p.name != "provenance.json"
        }
    assert sorted(trees["stable"]) == sorted(trees["dev"])
    assert len(trees["dev"]) == 4 * len(DEVICES)
    for rel, data in trees["stable"].items():
        assert data == trees["dev"][rel], rel
