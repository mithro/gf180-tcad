# SPDX-License-Identifier: Apache-2.0
"""Mesh convergence (gf180tcad.tcad.meshconv) and its CLI (``python -m gf180tcad.tcad meshconv``).

The host tests drive :func:`~gf180tcad.tcad.meshconv.converge` with synthetic curves of known
order, check the CLI's refusals and admission, and check the committed reports and the 1D
C/Cox bound. The sandbox-marked tests run the TCAD in the TCAD image (``pytest -m sandbox``):
tests/tcad/meshconv_driver.py for the convergence to the exact reference, and the CLI for the
byte-identity of the committed tree.
"""

import json
import math
from pathlib import Path

import pytest

from gf180tcad import io, reference, sandbox
from gf180tcad.tcad import TCAD_IMAGE, analytic, meshconv, moscap1d, process
from gf180tcad.tcad import __main__ as cli
from gf180tcad.tcad.mesh import MeshSpec

REPO = Path(__file__).resolve().parents[2]
TREE = REPO / "results" / "tcad" / "meshconv"
MOSCAP1D = REPO / "results" / "tcad" / "moscap1d"
DEVICES = process.DEVICES
VG = (-5.0, -1.0, 0.0, 0.5, 1.0, 5.0)


class Curve:
    """A CVCurve without a simulation."""

    def __init__(self, vg, c, node_count):
        self.vg = tuple(vg)
        self.c_per_area_ff_um2 = tuple(c)
        self.node_count = node_count


def synthetic(exact, a, p, h0=1.0):
    """simulate(spec) = exact * (1 + a * (h/h0)^p) at every bias, h = spec.h_si_surface_nm."""
    calls = []

    def simulate(spec: MeshSpec) -> Curve:
        calls.append(spec)
        h = spec.h_si_surface_nm / h0
        c = [e * (1 + ai * h**p) for e, ai in zip(exact, a, strict=True)]
        return Curve(VG, c, round(100 / h))

    return simulate, calls


EXACT = (2.2, 1.4, 0.9, 0.5, 0.8, 2.1)
START = MeshSpec(h_poly_nm=1.0, h_ox_nm=1.0, h_si_surface_nm=1.0, h_si_bulk_nm=20.0, grading=1.2)


# --- converge (host) -------------------------------------------------------------------------


def test_curve_protocol():
    assert isinstance(Curve(VG, EXACT, 1), meshconv.CVCurve)
    assert set(meshconv.CVCurve.__annotations__) == {"vg", "c_per_area_ff_um2", "node_count"}


def test_levels_default():
    assert meshconv.LEVELS == (1, 2**-0.5, 0.5, 2**-1.5)
    assert meshconv.CRITERION == 0.01


def test_converge_runs_every_level_with_scaled_specs():
    simulate, calls = synthetic(EXACT, [0.01] * 6, 2.0)
    rep = meshconv.converge(simulate, START)
    assert calls == [START.scaled(r) for r in meshconv.LEVELS]
    assert [lv.spec for lv in rep.levels] == calls
    assert [lv.scale for lv in rep.levels] == list(meshconv.LEVELS)
    assert rep.vg == VG


@pytest.mark.parametrize("p", [1.0, 2.0, 3.0])
def test_observed_order_and_richardson_of_a_known_order(p):
    a = [0.02, -0.03, 0.05, 0.1, -0.04, 0.01]
    simulate, _ = synthetic(EXACT, a, p)
    rep = meshconv.converge(simulate, START)
    assert len(rep.orders) == 2  # the triples (0, 1, 2) and (1, 2, 3)
    for o in rep.orders:
        assert all(math.isclose(q, p, rel_tol=1e-9) for q in o.per_bias), o
        assert math.isclose(o.median, p, rel_tol=1e-9)
    assert rep.orders[-1].levels == (1, 2, 3)
    assert math.isclose(rep.richardson_order, p, rel_tol=1e-9)
    for r, e in zip(rep.richardson, EXACT, strict=True):
        assert math.isclose(r, e, rel_tol=1e-9), (r, e)


def test_relative_change_against_the_next_finer_level():
    simulate, _ = synthetic(EXACT, [0.01] * 6, 2.0)
    rep = meshconv.converge(simulate, START)
    for lv, finer in zip(rep.levels, rep.levels[1:], strict=False):
        want = [abs(c / f - 1) for c, f in zip(lv.c_per_area_ff_um2, finer.c_per_area_ff_um2)]
        assert list(lv.rel_change) == want
        assert lv.max_rel_change == max(want)
    assert rep.levels[-1].rel_change is None and rep.levels[-1].max_rel_change is None


def test_selected_level_criterion():
    """The selected level is the coarsest whose change against the next finer one is < 1 %."""
    # error amp*h^2 with h = 1, 1/sqrt(2), 1/2, ...: the changes are about amp/2, amp/4, amp/8
    for amp, want in ((0.001, 0), (0.03, 1), (0.05, 2), (0.2, None)):
        simulate, _ = synthetic(EXACT, [amp] * 6, 2.0)
        rep = meshconv.converge(simulate, START)
        assert rep.selected == want, (amp, [lv.max_rel_change for lv in rep.levels])
        if want is None:
            with pytest.raises(meshconv.NotConverged):
                rep.selected_spec  # noqa: B018
            continue
        assert rep.levels[want].max_rel_change < meshconv.CRITERION
        assert all(lv.max_rel_change >= meshconv.CRITERION for lv in rep.levels[:want])
        assert rep.selected_spec == START.scaled(meshconv.LEVELS[want])


def test_one_bias_over_the_criterion_rejects_a_level():
    a = [0.001] * 6
    a[3] = 0.05  # one bias converges slowly
    simulate, _ = synthetic(EXACT, a, 2.0)
    assert meshconv.converge(simulate, START).selected == 2


def test_order_undefined_where_the_levels_agree_exactly():
    a = [0.01, 0.0, 0.01, 0.01, 0.01, 0.01]  # bias 1 does not depend on the mesh
    simulate, _ = synthetic(EXACT, a, 2.0)
    rep = meshconv.converge(simulate, START)
    for o in rep.orders:
        assert o.per_bias[1] is None
        assert math.isclose(o.median, 2.0, rel_tol=1e-9)  # median of the defined ones
    assert rep.richardson[1] == EXACT[1]


def oscillating(exact, a, p):
    """exact * (1 + a * (-1)^i * h^p) on level i: the sign alternates level to level."""

    def simulate(spec: MeshSpec) -> Curve:
        h = spec.h_si_surface_nm
        i = round(math.log(h) / math.log(2**-0.5))
        c = [e * (1 + ai * (-1) ** i * h**p) for e, ai in zip(exact, a, strict=True)]
        return Curve(VG, c, round(100 / h))

    return simulate


def test_oscillation_flagged_per_bias():
    """d12 * d23 < 0 (the change reverses sign between the triples' levels) is flagged."""
    a = [0.01] * 6
    rep = meshconv.converge(oscillating(EXACT, a, 2.0), START)
    for o in rep.orders:
        assert o.oscillating == (True,) * 6
        assert o.median is None  # Richardson needs monotone convergence
    assert rep.richardson is None and rep.richardson_order is None
    mono, _ = synthetic(EXACT, a, 2.0)
    for o in meshconv.converge(mono, START).orders:
        assert o.oscillating == (False,) * 6


def test_oscillating_biases_left_out_of_the_median():
    a = [0.01] * 6
    sim_mono, _ = synthetic(EXACT, a, 2.0)
    sim_osc = oscillating(EXACT, [0.01] * 6, 1.0)

    def simulate(spec):
        m, o = sim_mono(spec), sim_osc(spec)
        c = list(m.c_per_area_ff_um2)
        c[2] = o.c_per_area_ff_um2[2]  # bias 2 oscillates with another order
        return Curve(VG, c, m.node_count)

    rep = meshconv.converge(simulate, START)
    for o in rep.orders:
        assert o.oscillating[2] is True and o.per_bias[2] is not None
        assert math.isclose(o.median, 2.0, rel_tol=1e-9)


def test_order_undefined_below_the_noise_floor():
    """A difference within NOISE_K * rel_tol * |C| is solver noise: the order is undefined."""
    assert meshconv.NOISE_K == 1e4
    a = [0.01] * 6
    a[1] = 1e-9  # changes of ~1e-9 relative, below 1e4 * 1e-10 = 1e-6
    simulate, _ = synthetic(EXACT, a, 2.0)
    rep = meshconv.converge(simulate, START, rel_tol=1e-10)
    for o in rep.orders:
        assert o.per_bias[1] is None and o.oscillating[1] is None
        assert math.isclose(o.median, 2.0, rel_tol=1e-9)
    assert rep.noise_floor_rel == 1e-6
    # with a tighter solver tolerance the same changes are above the floor
    rep = meshconv.converge(simulate, START, rel_tol=1e-16)
    assert all(math.isclose(o.per_bias[1], 2.0, rel_tol=1e-5) for o in rep.orders)


def test_observed_order_noise_floor():
    assert meshconv.observed_order(1.0, 1.0 + 1e-7, 1.0 + 2e-7, 2**0.5, floor=1e-6) is None
    assert meshconv.observed_order(1.0, 1.1, 1.15, 2**0.5, floor=1e-6) is not None
    assert meshconv.observed_order(1.0, 1.0, 1.1, 2**0.5) is None  # exactly zero: undefined


def test_converge_refuses_bad_input():
    simulate, _ = synthetic(EXACT, [0.01] * 6, 2.0)
    for levels in ((1, 0.5), (1, 0.5, 0.5), (0.5, 1, 2**-0.5), (1, 0.7, 0.5)):
        with pytest.raises(ValueError):
            meshconv.converge(simulate, START, levels=levels)

    def other_vg(spec):
        c = simulate(spec)
        return Curve(c.vg if spec == START else c.vg[::-1], c.c_per_area_ff_um2, c.node_count)

    with pytest.raises(ValueError, match="bias"):
        meshconv.converge(other_vg, START)


def test_report_deterministic(tmp_path):
    """Two reports of the same curves are byte-identical (repr floats, sorted keys)."""
    outs = []
    for name in ("a", "b"):
        simulate, _ = synthetic(EXACT, [0.002, -0.003, 0.005, 0.01, -0.004, 0.001], 2.0)
        rep = meshconv.converge(simulate, START)
        d = tmp_path / name
        meshconv.write(rep, d, device="nfet_05v0", dim=1, settings={"rel_tol": 1e-10})
        outs.append(d)
    names = sorted(p.name for p in outs[0].iterdir())
    assert names == [meshconv.REPORT_NAME, meshconv.SELECTED_NAME]
    for n in names:
        assert (outs[0] / n).read_bytes() == (outs[1] / n).read_bytes()
    data = json.loads((outs[0] / meshconv.REPORT_NAME).read_bytes())
    assert "runtime" not in json.dumps(data) and "time" not in json.dumps(sorted(data))
    sel = json.loads((outs[0] / meshconv.SELECTED_NAME).read_bytes())
    assert MeshSpec(**sel) == rep.selected_spec


def test_report_contents(tmp_path):
    simulate, _ = synthetic(EXACT, [0.03] * 6, 2.0)
    rep = meshconv.converge(simulate, START)
    meshconv.write(rep, tmp_path, device="nfet_05v0", dim=1, settings={"rel_tol": 1e-10})
    data = json.loads((tmp_path / meshconv.REPORT_NAME).read_bytes())
    assert data["device"] == "nfet_05v0" and data["dim"] == 1 and data["params"] == "start"
    assert data["criterion"] == 0.01 and data["settings"] == {"rel_tol": 1e-10}
    assert data["start"] == START.as_dict() and data["vg"] == list(VG)
    assert data["selected"] == {"level": 1, "scale": 2**-0.5}
    assert [lv["node_count"] for lv in data["levels"]] == [lv.node_count for lv in rep.levels]
    lv0 = data["levels"][0]
    assert set(lv0) == {
        "c_per_area_ff_um2", "extended_fallback", "max_rel_change", "node_count",
        "rel_change", "roundoff_accepted", "scale", "spec",
    }  # fmt: skip
    assert lv0["extended_fallback"] == []
    assert data["levels"][-1]["rel_change"] is None
    assert data["observed_order"][-1]["levels"] == [1, 2, 3]
    assert math.isclose(data["observed_order"][-1]["median"], 2.0, rel_tol=1e-9)
    assert set(data["richardson"]) == {"c_per_area_ff_um2", "levels", "order"}
    assert set(data["observed_order"][-1]) == {"levels", "median", "oscillating", "per_bias"}
    assert data["observed_order"][-1]["oscillating"] == [False] * len(VG)
    assert data["noise_floor"] == {"k": meshconv.NOISE_K, "rel_tol": 1e-10, "rel": 1e-6}


def test_write_refuses_an_unconverged_report(tmp_path):
    simulate, _ = synthetic(EXACT, [0.2] * 6, 2.0)
    rep = meshconv.converge(simulate, START)
    with pytest.raises(meshconv.NotConverged):
        meshconv.write(rep, tmp_path, device="nfet_05v0", dim=1, settings={})
    assert not any(tmp_path.iterdir())


# --- admission and CLI (host) ----------------------------------------------------------------


def test_admission_budget_is_the_spice_one():
    assert meshconv.BUDGET_BYTES == reference.BUDGET_BYTES
    meshconv.check_admission(64, "2g")
    with pytest.raises(meshconv.AdmissionError):
        meshconv.check_admission(9, "16g")
    with pytest.raises(meshconv.AdmissionError):
        meshconv.check_admission(0, "2g")


def test_dim2_simulator_settings():
    """The 2D study: the PDK cell at Lmin with its S/D, from DEFAULT_2D, settings recorded."""
    _, settings = meshconv.simulator("nfet_05v0", 2)
    assert settings["geometry"] == "w10p0_l0p60" and settings["with_sd"] is True
    assert settings["rel_tol"] == moscap1d.REL_TOL and settings["method"] == "qs"
    assert meshconv.START == {1: MeshSpec.DEFAULT_1D, 2: MeshSpec.DEFAULT_2D}
    assert meshconv.geometry_2d("pfet_05v0").l_um == 0.5
    with pytest.raises(ValueError):
        meshconv.check_dim(3)


def test_meshconv_cli_refuses_too_many_jobs(tmp_path, capsys):
    argv = ["meshconv", "--device", "nfet_05v0", "--dim", "1", "--out", str(tmp_path / "r")]
    assert cli.main([*argv, "--jobs", "100"]) == 2
    assert "128 GiB" in capsys.readouterr().err
    assert not (tmp_path / "r").exists()


def test_meshconv_job_refuses_outside_the_sandbox(tmp_path):
    with pytest.raises(RuntimeError, match="inside the sandbox"):
        cli.run_meshconv_level("nfet_05v0", 1, 0, tmp_path)
    with pytest.raises(RuntimeError, match="inside the sandbox"):
        cli.run_meshconv_assemble("nfet_05v0", 1, tmp_path)


def test_selected_spec_reads_selected_json(tmp_path):
    spec = MeshSpec.DEFAULT_1D.scaled(0.5)
    d = tmp_path / "moscap1d" / "nfet_05v0"
    d.mkdir(parents=True)
    io.write_json(d / meshconv.SELECTED_NAME, spec.as_dict())
    assert meshconv.selected_spec("nfet_05v0", 1, root=tmp_path) == spec
    with pytest.raises(FileNotFoundError, match="meshconv"):
        meshconv.selected_spec("pfet_05v0", 1, root=tmp_path)


# --- the committed results (host) ------------------------------------------------------------


@pytest.mark.parametrize("device", DEVICES)
def test_committed_report(device):
    job = TREE / "moscap1d" / device
    assert sorted(p.name for p in job.iterdir()) == [meshconv.REPORT_NAME, meshconv.SELECTED_NAME]
    data = json.loads((job / meshconv.REPORT_NAME).read_bytes())
    assert data["device"] == device and data["dim"] == 1 and data["params"] == "start"
    assert data["start"] == MeshSpec.DEFAULT_1D.as_dict()
    assert [lv["scale"] for lv in data["levels"]] == list(meshconv.LEVELS)
    assert tuple(data["vg"]) == cli.job_vg(process.load(device))
    counts = [lv["node_count"] for lv in data["levels"]]
    assert counts == sorted(counts) and len(set(counts)) == len(counts)
    sel = data["selected"]["level"]
    assert data["levels"][sel]["max_rel_change"] < meshconv.CRITERION
    assert all(lv["max_rel_change"] >= meshconv.CRITERION for lv in data["levels"][:sel])
    spec = MeshSpec(**json.loads((job / meshconv.SELECTED_NAME).read_bytes()))
    assert spec == MeshSpec.DEFAULT_1D.scaled(meshconv.LEVELS[sel])
    assert spec == meshconv.selected_spec(device, 1)


@pytest.mark.parametrize("device", DEVICES)
def test_moscap1d_start_uses_the_selected_mesh(device):
    """From Task 10 on, every 1D result uses results/tcad/meshconv/moscap1d/<device>/selected.json."""
    cv = moscap1d.read(MOSCAP1D / device / "start")
    assert cv.mesh == meshconv.selected_spec(device, 1)
    info = json.loads((MOSCAP1D / device / "start" / moscap1d.PER_AREA_META).read_bytes())
    assert info["mesh_source"] == f"results/tcad/meshconv/moscap1d/{device}/selected.json"
    assert info["node_count"] == cv.node_count > 0


@pytest.mark.parametrize("device", DEVICES)
def test_1d_c_over_cox_below_one_at_5v(device):
    """Step 4: in 1D, C/Cox < 1 at |Vg| = 5 V in accumulation and in inversion.

    Classical accumulation and inversion layers add a series capacitance to Cox, so C/Cox > 1
    is impossible in 1D; the spike's C/Cox = 1.0039 at -5 V is a 2D artefact (Task 11).
    """
    cv = moscap1d.read(MOSCAP1D / device / "start")
    s = cv.stack
    cox = analytic.f_per_cm2_to_ff_per_um2(analytic.cox_f_per_cm2(s.t_ox_nm, s.eps_ox))
    at = dict(zip(cv.vg, cv.c_per_area_ff_um2, strict=True))
    for v in (-5.0, 5.0):
        assert 0.9 < at[v] / cox < 1, (device, v, at[v] / cox)


# --- in the TCAD image -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def driver(tmp_path_factory) -> dict:
    out = tmp_path_factory.mktemp("meshconv-driver")
    sandbox.run(
        ["python3", "/work/src/tests/tcad/meshconv_driver.py"],
        out_dir=out, image=TCAD_IMAGE, mem="2g", cpus=1,
    )  # fmt: skip
    return json.loads((out / "driver.json").read_bytes())


@pytest.mark.sandbox
def test_converges_to_exact(driver):
    """Uniform doping (the nfet stack): the finest level is within 0.05 % of the exact
    Poisson-Boltzmann C-V, and the median observed order is second order (1.5 to 2.5).

    The driver starts from DEFAULT_1D, the production start, on a 21-point bias grid.
    """
    rep = driver["report"]
    finest = rep["levels"][-1]["c_per_area_ff_um2"]
    worst = max(abs(c / e - 1) for c, e in zip(finest, driver["exact"], strict=True))
    assert worst < 5e-4, worst
    p = rep["observed_order"][-1]["median"]
    assert 1.5 <= p <= 2.5, p
    counts = [lv["node_count"] for lv in rep["levels"]]
    assert counts == sorted(counts)


@pytest.mark.sandbox
def test_meshconv_byte_identical(tmp_path):
    """A rerun of ``meshconv --dim 1`` gives the committed tree byte for byte."""
    root = tmp_path / "root"
    for device in DEVICES:
        argv = ["meshconv", "--device", device, "--dim", "1", "--out", str(root)]
        assert cli.main(argv) == 0
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert files == sorted(
        [
            f"moscap1d/{d}/{n}"
            for d in DEVICES
            for n in (meshconv.REPORT_NAME, meshconv.SELECTED_NAME)
        ]
        + ["provenance.json"]
    )
    for rel in files:
        assert (root / rel).read_bytes() == (TREE / rel).read_bytes(), rel


def test_meshconv_resume_keeps_finished_levels(tmp_path, monkeypatch):
    """``--resume`` reruns only the levels without a level.json in the old scratch directory."""
    scratch = tmp_path / "scratch"
    for i in (0, 2, 3):
        (scratch / f"level{i}").mkdir(parents=True)
        (scratch / f"level{i}" / cli.LEVEL_NAME).write_text("{}", encoding="utf-8")
    (scratch / "level1").mkdir()
    (scratch / "level1" / "job.log").write_text("failed", encoding="utf-8")
    ran = []

    def fake_job(cmd, out_dir, mem):
        ran.append(cmd[cmd.index("--level") + 1] if "--level" in cmd else "assemble")
        raise RuntimeError("stop after the level jobs")

    monkeypatch.setattr(cli, "_sandbox_job", fake_job)
    monkeypatch.setattr(cli, "gplugins_commit", lambda: "x")
    with pytest.raises(RuntimeError, match="stop after"):
        cli.run_meshconv("nfet_05v0", 2, tmp_path / "root", resume=scratch)
    assert ran == ["1"]
    assert not (scratch / "level1" / "job.log").exists()  # the failed level starts afresh
