# SPDX-License-Identifier: Apache-2.0
"""The 2D MOS capacitor (gf180tcad.tcad.moscap2d, gf180tcad.tcad.stack) and its committed results.

The host tests check the CLI's refusals and the committed results under results/tcad/moscap2d
and results/tcad/meshconv/moscap2d. The sandbox-marked tests run the TCAD in the TCAD image
(``pytest -m sandbox``): tests/tcad/moscap2d_driver.py, one sandbox job per case in parallel,
and a rerun of the CLI for the byte-identity of a committed job.
"""

import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from gf180tcad import io, sandbox
from gf180tcad.devices import DEVICES as SPICE_DEVICES
from gf180tcad.devices import geometry_id
from gf180tcad.tcad import TCAD_IMAGE, meshconv, moscap2d, process, stack
from gf180tcad.tcad import __main__ as cli
from gf180tcad.tcad.mesh import MeshSpec

REPO = Path(__file__).resolve().parents[2]
TREE = REPO / "results" / "tcad" / "moscap2d"
MESHCONV = REPO / "results" / "tcad" / "meshconv"
DEVICES = process.DEVICES
# The cases of tests/tcad/moscap2d_driver.py (its CASES).
CASES = (
    *(f"uniform_{d}" for d in DEVICES),
    *(f"nosd_{d}" for d in DEVICES),
    *(f"ac_{d}" for d in DEVICES),
    "sd_pfet_05v0",
    "dualgate",
)
CAL = {d: [g for g in SPICE_DEVICES[d].geometries if g.role == "calibration"] for d in DEVICES}


# --- host ------------------------------------------------------------------------------------


def test_dim2_needs_a_geometry(tmp_path, capsys):
    with pytest.raises(cli.BadGeometry, match="--geometry"):
        cli.run_host("nfet_05v0", "start", tmp_path, dim=2, gid=None)
    argv = ["moscap", "--device", "nfet_05v0", "--dim", "2", "--params", "start",
            "--geometry", "w10p0_l0p50", "--out", str(tmp_path / "root")]  # fmt: skip
    assert cli.main(argv) == 2
    assert "no geometry" in capsys.readouterr().err
    assert not (tmp_path / "root").exists()


def test_geometry_ids():
    assert cli.geometry_of("nfet_05v0", "w10p0_l0p60").l_um == 0.6
    with pytest.raises(cli.BadGeometry, match="no geometry"):
        cli.geometry_of("nfet_05v0", "w10p0_l0p50")


def test_job_refuses_outside_the_sandbox(tmp_path):
    with pytest.raises(RuntimeError, match="inside the sandbox"):
        cli.run_job("nfet_05v0", "start", tmp_path, dim=2, gid="w10p0_l0p60")


def test_point_tolerance_keeps_the_oxide():
    """The vertex grid is far below every thickness: a calibrated t_ox (any value in its bounds)
    is meshed within 1e-4 relative, unlike meshwell's 1 nm default (Task 11's artefact)."""
    assert stack.POINT_TOLERANCE_UM <= 1e-6
    for d in DEVICES:
        lo, _ = process.load(d).params["t_ox_eff_nm"].bounds
        assert stack.POINT_TOLERANCE_UM / (lo * 1e-3) < 1e-4


def test_sd_straggle_puts_the_junction_at_xj():
    for d in DEVICES:
        proc = process.load(d)
        v = proc.values()
        s = stack.sd_straggle_um(proc, v["sd_peak_cm3"])
        at_xj = v["sd_peak_cm3"] * math.exp(-(v["xj_um"] ** 2) / (2 * s * s))
        assert math.isclose(at_xj, v["n_ch_cm3"], rel_tol=1e-12)


def test_2d_mesh_converged():
    """The committed 2D study selects a level whose change against the next finer is < 1 %."""
    for d in DEVICES:
        rep = json.loads((MESHCONV / "moscap2d" / d / meshconv.REPORT_NAME).read_bytes())
        assert rep["dim"] == 2 and rep["device"] == d
        assert rep["settings"]["geometry"] == geometry_id(meshconv.geometry_2d(d))
        assert rep["settings"]["with_sd"] is True
        sel = rep["selected"]["level"]
        assert rep["levels"][sel]["max_rel_change"] < meshconv.CRITERION
        assert rep["start"] == MeshSpec.DEFAULT_2D.as_dict()
        spec = meshconv.selected_spec(d, 2)
        assert spec == MeshSpec(**rep["levels"][sel]["spec"])
        assert rep["vg"] == list(cli.job_vg(process.load(d)))


@pytest.mark.parametrize("device", DEVICES)
def test_committed_start_results(device):
    """Every calibration geometry has its start job, on the selected 2D mesh."""
    proc = process.load(device)
    for g in CAL[device]:
        job = moscap2d.job_dir(TREE, device, "start", g)
        names = {p.name for p in job.iterdir()}
        assert names == {moscap2d.CV_CSV, moscap2d.CGX_CSV, moscap2d.MESH_FILE, moscap2d.META_JSON}
        cols, meta = io.read_csv(job / moscap2d.CV_CSV)
        assert meta["dim"] == "2" and meta["method"] == "qs" and meta["params"] == "start"
        assert tuple(cols["vg"]) == cli.job_vg(proc)
        info = json.loads((job / moscap2d.META_JSON).read_bytes())
        assert info["mesh"] == meshconv.selected_spec(device, 2).as_dict()
        assert info["mesh_source"] == cli.mesh_source(device, 2)
        assert info["l_um"] == g.l_um and info["w_um"] == g.w_um and info["with_sd"] is True
        assert abs(info["meshed_t_ox_nm"] - info["t_ox_nm"]) <= stack.POINT_TOLERANCE_UM * 1e3
        assert "calibrated" not in json.dumps(info["tunables"])
        assert all(r <= 1e-10 for r in cols["rel_error"])
        # the per-area and per-device columns are the same numbers
        for a, b, t in zip(cols["c_per_area"], cols["cgg_per_um"], cols["cgg_total"], strict=True):
            assert math.isclose(b, a * g.l_um, rel_tol=1e-12)
            assert math.isclose(t, b * g.w_um, rel_tol=1e-12)
        gx, gmeta = io.read_csv(job / moscap2d.CGX_CSV)
        assert gmeta["method"] == "ac" and float(gmeta["freq_hz"]) == 1e6
        others = sorted(k[1:-7] for k in gx if k.startswith("c") and k.endswith("g_per_um")
                        and k != "cgg_per_um")  # fmt: skip
        assert others == ["body", "drain", "source"]
        assert max(abs(e) for e in gx["sum_rel_error"]) < 1e-3  # charge conservation


# --- in the TCAD image -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def driver(tmp_path_factory) -> dict:
    def run(case: str) -> tuple[str, dict]:
        out = tmp_path_factory.mktemp(case)
        sandbox.run(
            ["python3", "/work/src/tests/tcad/moscap2d_driver.py", case],
            out_dir=out, image=TCAD_IMAGE, mem="8g", cpus=1,
        )  # fmt: skip
        return case, json.loads((out / f"{case}.json").read_bytes())

    meshconv.check_admission(len(CASES), "8g")
    with ThreadPoolExecutor(max_workers=len(CASES)) as pool:
        return dict(pool.map(run, CASES))


@pytest.mark.sandbox
@pytest.mark.parametrize("device", DEVICES)
def test_2d_equals_1d_without_sd(driver, device):
    """Uniform stack, a gate over the whole domain, Neumann sides: 2D Cgg per area = 1D within
    0.5 % at every bias, and the meshed oxide is the requested one."""
    d = driver[f"uniform_{device}"]
    worst = max(abs(a / b - 1) for a, b in zip(d["c_per_area"], d["c1d"], strict=True))
    assert worst < 5e-3, worst
    t_ox = process.load(device).values()["t_ox_eff_nm"]
    assert abs(d["meshed_t_ox_nm"] - t_ox) <= stack.POINT_TOLERANCE_UM * 1e3


@pytest.mark.sandbox
@pytest.mark.parametrize("device", DEVICES)
def test_c_over_cox_le_1(driver, device):
    """Without S/D, 2D C/Cox <= 1 at |vg| = 5 V: the uniform stack and the PDK cell whose only
    dielectric path from the gate is the gate oxide. (With the spacer/ILD dielectric the gate's
    fringe adds capacitance outside the drawn area; that is physics, reported, not tested.)"""
    u = driver[f"uniform_{device}"]
    for v, c in zip(u["vg"], u["c_per_area"], strict=True):
        if abs(v) == 5.0:
            assert c / u["cox"] <= 1.0, (v, c / u["cox"])
    n = driver[f"nosd_{device}"]
    for c in n["neumann"]["c_per_area"]:
        assert c / n["cox"] <= 1.0, c / n["cox"]


@pytest.mark.sandbox
@pytest.mark.parametrize("device", DEVICES)
def test_ac_1mhz_recovers_inversion(driver, device):
    """With S/D, 1 MHz AC recovers in inversion as SPICE does: C_inv / C_acc > 0.9."""
    ac = driver[f"ac_{device}"]["ac"]
    c = dict(zip(ac["vg"], ac["cgg_per_um"], strict=True))
    pol = 1.0 if driver[f"ac_{device}"]["polarity"] == "n" else -1.0
    assert c[5.0 * pol] / c[-5.0 * pol] > 0.9, (c[5.0 * pol], c[-5.0 * pol])
    # and close to QS there (the inversion charge comes from the S/D at 1 MHz)
    qs = dict(zip(driver[f"ac_{device}"]["qs"]["vg"], driver[f"ac_{device}"]["qs"]["cgg_per_um"]))
    assert abs(c[5.0 * pol] / qs[5.0 * pol] - 1) < 0.01


@pytest.mark.sandbox
@pytest.mark.parametrize("device", DEVICES)
def test_charge_conservation(driver, device):
    """Cgg = sum of Cxg over every non-gate contact (body, source, drain) within 0.1 %."""
    d = driver[f"ac_{device}"]
    ac = d["ac"]
    assert sorted(ac["cgx"]) == d["non_gate"] == ["body", "drain", "source"]
    assert d["contacts"] == ["body", "drain", "gate", "source"]
    for i, cgg in enumerate(ac["cgg_per_um"]):
        total = math.fsum(ac["cgx"][c][i] for c in d["non_gate"])
        assert abs(total / cgg - 1) < 1e-3, (ac["vg"][i], total, cgg)


@pytest.mark.sandbox
def test_pfet_sd_doping_insensitive(driver):
    """pfet Cgg changes by < 0.1 % at every bias for sd_peak_cm3 in {5e19, 1e20, 2e20}."""
    d = driver["sd_pfet_05v0"]
    ref = d[repr(1e20)]["c_per_area"]
    for peak in (5e19, 2e20):
        worst = max(abs(a / b - 1) for a, b in zip(d[repr(peak)]["c_per_area"], ref, strict=True))
        assert worst < 1e-3, (peak, worst)


@pytest.mark.sandbox
def test_dualgate_required(driver):
    """stack.build accepts both 5 V cells and raises DualgateMissing without Dualgate (55,0)."""
    for device, d in driver["dualgate"].items():
        g = meshconv.geometry_2d(device)
        assert d["refused"] and "Dualgate" in d["refused"]
        assert math.isclose(d["l_um"], g.l_um, abs_tol=1e-9)
        assert math.isclose(d["w_um"], g.w_um, abs_tol=1e-9)
        assert d["contacts"] == ["body", "drain", "gate", "source"]


@pytest.mark.sandbox
def test_byte_identical(tmp_path):
    """A rerun of ``moscap --dim 2`` gives the committed job byte for byte (the smallest one)."""
    device = "pfet_05v0"
    g = meshconv.geometry_2d(device)
    root = tmp_path / "root"
    argv = ["moscap", "--device", device, "--dim", "2", "--params", "start",
            "--geometry", geometry_id(g), "--out", str(root)]  # fmt: skip
    assert cli.main(argv) == 0
    job = moscap2d.job_dir(root, device, "start", g)
    ref = moscap2d.job_dir(TREE, device, "start", g)
    for p in sorted(job.iterdir()):
        assert p.read_bytes() == (ref / p.name).read_bytes(), p.name
