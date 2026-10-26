# SPDX-License-Identifier: Apache-2.0
"""The 2D MOS capacitor (gf180tcad.tcad.moscap2d, gf180tcad.tcad.stack) and its committed results.

The host tests check the CLI's refusals and the committed results under results/tcad/moscap2d
and results/tcad/meshconv/moscap2d. The sandbox-marked tests run the TCAD in the TCAD image
(``pytest -m sandbox``): tests/tcad/moscap2d_driver.py, one sandbox job per case in parallel,
and a rerun of the CLI for the byte-identity of a committed job.
"""

import hashlib
import json
import math
import re
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
    "sd_pfet_05v0_lmin",
    "sd_pfet_05v0_l2",
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


def _synthetic_cv(method: str) -> moscap2d.MoscapCV2D:
    ac = method == "ac"
    return moscap2d.MoscapCV2D(
        device="nfet_05v0",
        geometry=cli.geometry_of("nfet_05v0", "w10p0_l0p60"),
        vg=(-5.0, 0.0, 5.0),
        c_per_area_ff_um2=(2.2, 0.9, 2.1),
        cgg_ff_per_um=(1.32, 0.54, 1.26),
        cgx={"body": (1.3, 0.5, 0.1), "drain": (0.01, 0.02, 0.6)} if ac else {},
        points=tuple(moscap2d.Point(True, 3 + i, 1e-11 * i, 1e-13) for i in range(3)),
        method=method,
        freq_hz=1e6 if ac else None,
        with_sd=True,
        mesh=MeshSpec.DEFAULT_2D.scaled(0.5**0.5, refine_grading=True),
        node_count=224640,
        l_um=0.6,
        w_um=10.0,
        t_ox_nm=15.2,
        meshed_t_ox_nm=15.200000000000001,
        meshed_l_um=0.6,
        rel_tol=1e-10,
        sd_peak_cm3=None if ac else 1e20,
        constants=process.CONSTANTS,
        extended_fallback=() if ac else (1,),
        roundoff_accepted=() if ac else ({"index": 2, "vg": 4.999, "region": "ild"},),
    )


@pytest.mark.parametrize("method", ["qs", "ac"])
def test_result_json_round_trip(method):
    """A QS or AC sweep survives its JSON file exactly (the split jobs hand it to combine)."""
    cv = _synthetic_cv(method)
    back = moscap2d.from_dict(json.loads(json.dumps(moscap2d.to_dict(cv))))
    assert back == cv


def _point(i: int) -> dict:
    return {"i": i, "cgg": 1e-12 * (i + 1), "cgx": {}, "point": [True, 4, 1e-11, 1e-13],
            "fallback": False, "roundoff": []}  # fmt: skip


def test_sweep_state_resumes_after_the_last_handoff(tmp_path):
    """Each point is saved, then the hand-off state it leaves; a resume keeps the points up to
    the last hand-off and recomputes the rest (here point 2 was saved but not its hand-off)."""
    header = {"method": "qs", "vg": [-5.0, 0.0, 5.0], "mesh_sha256": "ab"}
    st = moscap2d.SweepState(tmp_path / "s", header)
    assert st.resume() == ([], None)
    st.save(_point(0), {"i": 0, "v_gate": -4.999, "potential": {"body": [0.1, 0.2]}})
    st.save(_point(1), {"i": 1, "v_gate": 0.001, "potential": {"body": [0.3, 0.4]}})
    st.save_point(_point(2))  # interrupted before its hand-off
    st2 = moscap2d.SweepState(tmp_path / "s", header)
    points, handoff = st2.resume()
    assert [p["i"] for p in points] == [0, 1]
    assert handoff == {"i": 1, "v_gate": 0.001, "potential": {"body": [0.3, 0.4]}}
    with pytest.raises(moscap2d.StaleState, match="mesh_sha256"):
        moscap2d.SweepState(tmp_path / "s", {**header, "mesh_sha256": "cd"})
    # every resume that kept points is recorded (the results disclose them)
    assert moscap2d.resume_count(tmp_path / "s") == 1
    moscap2d.SweepState(tmp_path / "s", header).resume()
    assert moscap2d.resume_count(tmp_path / "s") == 2
    assert moscap2d.resume_count(tmp_path / "missing") == 0


def test_qs_only_combine(tmp_path, monkeypatch):
    """``--method combine-qs`` (L = 2 um: the AC drift-diffusion solve fails in UMFPACK 5.1 at
    its size) writes cv.csv, the mesh and the meta from the QS sweep alone, and the meta says
    why there is no AC and how often the sweep was resumed."""
    monkeypatch.setattr(cli.meshconv, "selected_spec", lambda d, dim: MeshSpec.DEFAULT_2D)
    out = tmp_path / "job"
    out.mkdir()
    io.write_json(out / "qs.json", moscap2d.to_dict(_synthetic_cv("qs")))
    (out / moscap2d.MESH_FILE).write_text("mesh", encoding="utf-8")
    st = out / "state_qs"
    st.mkdir()
    (st / moscap2d.STATE_RESUMES).write_text('{"kept": 57}\n{"kept": 97}\n', encoding="utf-8")
    cli.run_job_2d("nfet_05v0", "start", "w10p0_l0p60", out, method="combine-qs")
    assert not (out / moscap2d.CGX_CSV).exists()
    cols, meta = io.read_csv(out / moscap2d.CV_CSV)
    assert meta["method"] == "qs" and list(cols["c_per_area"]) == [2.2, 0.9, 2.1]
    info = json.loads((out / moscap2d.META_JSON).read_bytes())
    assert info["ac"] == moscap2d.AC_INFEASIBLE and "UMFPACK" in info["ac"]
    assert info["ac_points"] == 0 and info["contacts"] == ["gate"]
    assert info["resumed"] == {"qs": 2}


def test_moscap_split_methods(tmp_path, monkeypatch):
    """``moscap --dim 2 --method qs|ac`` runs that sweep in the scratch dir (``--resume``) and
    keeps it; ``--method combine`` writes the job files from both and removes the scratch."""
    calls = []

    def fake_run(cmd, *, out_dir, image, mem, cpus):
        calls.append((cmd, Path(out_dir), mem))
        method = cmd[cmd.index("--method") + 1]
        if method in ("combine", "both"):
            for name in (moscap2d.CV_CSV, moscap2d.CGX_CSV, moscap2d.MESH_FILE, moscap2d.META_JSON):
                (Path(out_dir) / name).write_text(name, encoding="utf-8")

        class R:
            stdout = ""

        return R()

    monkeypatch.setattr(cli.sandbox, "run", fake_run)
    monkeypatch.setattr(cli, "gplugins_commit", lambda: "x")
    monkeypatch.setattr(cli.meshconv, "selected_spec", lambda d, dim: MeshSpec.DEFAULT_2D)
    monkeypatch.setattr(cli, "tree_provenance", lambda root, images=None: {"p": 1})
    scratch, root = tmp_path / "scratch", tmp_path / "root"
    scratch.mkdir()
    gid = "w10p0_l2p00"
    for m in ("qs", "ac"):
        cli.run_host("nfet_05v0", "start", root, dim=2, gid=gid, method=m, resume=scratch,
                     mem="12g")  # fmt: skip
    assert [(c[0][c[0].index("--method") + 1], c[1], c[2]) for c in calls] == [
        ("qs", scratch, "12g"),
        ("ac", scratch, "12g"),
    ]
    assert scratch.is_dir() and not root.exists()
    cli.run_host("nfet_05v0", "start", root, dim=2, gid=gid, method="combine", resume=scratch)
    job = moscap2d.job_dir(root, "nfet_05v0", "start", cli.geometry_of("nfet_05v0", gid))
    assert sorted(p.name for p in job.iterdir()) == sorted(
        [moscap2d.CV_CSV, moscap2d.CGX_CSV, moscap2d.MESH_FILE, moscap2d.META_JSON]
    )
    assert not scratch.exists()
    with pytest.raises(ValueError, match="--method"):
        cli.run_host("nfet_05v0", "start", root, dim=1, method="qs")


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
        assert rep["levels"][sel]["agreement_1d"] < 5e-3
        crit = rep["selected"]["criteria"]
        assert crit["selected"] == sel
        assert sel == max(crit["agreement_1d"]["level"], crit["convergence"]["level"])
        assert rep["refine_grading"] is True
        assert rep["excluded_levels"][0]["level"] == 3
        assert rep["start"] == MeshSpec.DEFAULT_2D.as_dict()
        spec = meshconv.selected_spec(d, 2)
        assert spec == MeshSpec(**rep["levels"][sel]["spec"])
        assert rep["vg"] == list(cli.job_vg(process.load(d)))


@pytest.mark.parametrize("device", DEVICES)
def test_committed_start_results(device):
    """Every calibration geometry has its start job, on the selected 2D mesh."""
    proc = process.load(device)
    for g in CAL[device]:
        if (
            g.l_um >= 10.0
        ):  # the L = 10 um cell is not simulated in 2D (docs/limitations/moscap2d.md)
            continue
        job = moscap2d.job_dir(TREE, device, "start", g)
        # mesh.msh is git-ignored (a local regeneration may leave one); its sha256 is checked below
        names = {p.name for p in job.iterdir()} - {moscap2d.MESH_FILE}
        # L = 2 um is QS-only: its AC solve exceeds the UMFPACK size limit (AC_INFEASIBLE)
        qs_only = g.l_um >= 2.0
        base = {moscap2d.CV_CSV, moscap2d.META_JSON}
        assert names == (base if qs_only else base | {moscap2d.CGX_CSV})
        cols, meta = io.read_csv(job / moscap2d.CV_CSV)
        assert meta["dim"] == "2" and meta["method"] == "qs" and meta["params"] == "start"
        assert tuple(cols["vg"]) == cli.job_vg(proc)
        info = json.loads((job / moscap2d.META_JSON).read_bytes())
        assert info["mesh"] == meshconv.selected_spec(device, 2).as_dict()
        assert info["mesh_source"] == cli.mesh_source(device, 2)
        assert re.fullmatch(r"[0-9a-f]{64}", info["mesh_sha256"])
        mesh = job / moscap2d.MESH_FILE
        if mesh.exists():  # a local regeneration: its sha256 must equal the committed one
            assert hashlib.sha256(mesh.read_bytes()).hexdigest() == info["mesh_sha256"]
        assert info["l_um"] == g.l_um and info["w_um"] == g.w_um and info["with_sd"] is True
        assert abs(info["meshed_t_ox_nm"] - info["t_ox_nm"]) <= stack.POINT_TOLERANCE_UM * 1e3
        assert "calibrated" not in json.dumps(info["tunables"])
        # every point meets rel_tol, except the recorded round-off acceptances (index, and
        # their potential update at round-off, far below abs_tol)
        accepted = {r["index"] for r in info["sweep"]["qs_roundoff_accepted"]}
        for i, r in enumerate(cols["rel_error"]):
            assert r <= 1e-10 or i in accepted, (i, r)
        for r in info["sweep"]["qs_roundoff_accepted"]:
            assert r["abs_error"] <= r["roundoff_bound"] < 1e-12
        # the per-area and per-device columns are the same numbers
        for a, b, t in zip(cols["c_per_area"], cols["cgg_per_um"], cols["cgg_total"], strict=True):
            assert math.isclose(b, a * g.l_um, rel_tol=1e-12)
            assert math.isclose(t, b * g.w_um, rel_tol=1e-12)
        if qs_only:
            assert info["ac"] == moscap2d.AC_INFEASIBLE and info["ac_points"] == 0
            continue
        gx, gmeta = io.read_csv(job / moscap2d.CGX_CSV)
        assert gmeta["method"] == "ac" and float(gmeta["freq_hz"]) == 1e6
        others = sorted(k[1:-8] for k in gx if k.startswith("c") and k.endswith("g_per_um")
                        and k != "cgg_per_um")  # fmt: skip
        assert others == ["body", "drain", "source"]
        assert max(abs(e) for e in gx["sum_rel_error"]) < 1e-3  # charge conservation


# The committed 1 MHz AC Cgg against the QS Cgg of the same job: measured at most 3.3e-7
# relative (nfet 10/0.6 at +1 V; pfet 10/0.5, 3.0e-7 at -1 V), pinned with a 30x margin.
# docs/limitations/index.md (QS, not HF) cites this test.
AC_FOLLOWS_QS_REL = 1e-5


def test_committed_ac_follows_qs():
    """At every AC bias of every committed cgx.csv, the 1 MHz Cgg equals the QS Cgg of cv.csv
    at that bias within AC_FOLLOWS_QS_REL: the S/D supply the inversion charge at 1 MHz."""
    jobs = sorted(TREE.glob(f"*/start/*/{moscap2d.CGX_CSV}"))
    assert {j.parent.parent.parent.name for j in jobs} == set(DEVICES)
    for job in jobs:
        gx, _ = io.read_csv(job)
        cols, _ = io.read_csv(job.with_name(moscap2d.CV_CSV))
        qs = dict(zip(cols["vg"].tolist(), cols["cgg_per_um"].tolist(), strict=True))
        assert len(gx["vg"]) == 21
        for v, c in zip(gx["vg"].tolist(), gx["cgg_per_um"].tolist(), strict=True):
            assert abs(c / qs[v] - 1) < AC_FOLLOWS_QS_REL, (job, v, c, qs[v])


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


class SdSensitivity(AssertionError):
    """pfet Cgg moves by >= 0.1 % for a factor of 2 in sd_peak_cm3 (the xfail signature)."""


# At Lmin the S/D peak is load-bearing (Task 11 report): with XJ fixed the peak sets the
# straggle (44.5 / 42.0 / 39.9 nm for 5e19 / 1e20 / 2e20) and so how far the p+ edge reaches
# under the 0.5 um gate, an edge effect of about 1/L. Measured worst change against 1e20, in
# depletion: -1.52 % (5e19) and +1.25 % (2e20); accumulation -0.56 % / +0.50 %; inversion
# -0.030 % / +0.032 %. Strict: an unexpected pass fails, and only SdSensitivity xfails.
_SD_LMIN_REASON = (
    "sd_peak_cm3 is load-bearing at Lmin (0.5 um): Cgg moves -1.52 % / +1.25 % (worst, "
    "depletion) for 5e19 / 2e20 against 1e20; fixed XJ couples peak and straggle"
)


@pytest.mark.sandbox
@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            "sd_pfet_05v0_lmin",
            marks=pytest.mark.xfail(strict=True, raises=SdSensitivity, reason=_SD_LMIN_REASON),
        ),
        "sd_pfet_05v0_l2",
    ],
)
def test_pfet_sd_doping_insensitive(driver, case):
    """pfet Cgg changes by < 0.1 % at every bias for sd_peak_cm3 in {5e19, 1e20, 2e20}."""
    d = driver[case]
    ref = d[repr(1e20)]["c_per_area"]
    for peak in (5e19, 2e20):
        worst = max(abs(a / b - 1) for a, b in zip(d[repr(peak)]["c_per_area"], ref, strict=True))
        if not worst < 1e-3:
            raise SdSensitivity(f"{case}: sd_peak_cm3 {peak!r}: worst |dC/C| {worst!r} >= 1e-3")


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


@pytest.mark.sandbox
def test_split_and_resumed_jobs_are_byte_identical(tmp_path):
    """The production job split into a QS job and an AC job (run in parallel on one scratch dir)
    and a combine job gives the job files of the one-job run byte for byte. With both sweeps cut
    off after their 2nd point and resumed: the AC and the mesh are byte-identical, and the QS
    agrees within 1e-12. DEVSIM keeps solver state across solves that a hand-off of the node
    values does not carry, so a resumed QS point moves at round-off (about 1e-13). For the same
    reason the per-point QS sweep equals one sweep_cv call within 1e-12 (2e-13 measured), and
    the AC (each point's circuit unknowns start afresh) within the solver tolerance
    (tests/tcad/moscap2d_split_driver.py, a coarse Lmin cell).
    """
    out = tmp_path / "out"
    out.mkdir()

    def step(name: str, sub: str) -> None:
        sandbox.run(
            ["python3", "/work/src/tests/tcad/moscap2d_split_driver.py", name, sub],
            out_dir=out, image=TCAD_IMAGE, mem="2g", cpus=1,
        )  # fmt: skip

    def parallel(*steps) -> None:  # at most two 2 GiB jobs at a time
        with ThreadPoolExecutor(max_workers=len(steps)) as pool:
            list(pool.map(lambda s: step(*s), steps))

    parallel(("both", "both"), ("mono", "mono"))
    parallel(("qs", "split"), ("ac", "split"))  # as production: in parallel on one scratch dir
    parallel(("qs-interrupt", "resumed"), ("ac-interrupt", "resumed"))
    for m in ("qs", "ac"):
        done = [json.loads(x) for x in (out / "resumed" / f"state_{m}" / moscap2d.STATE_POINTS)
                .read_text().splitlines()]  # fmt: skip
        assert [p["i"] for p in done] == [0, 1], m  # cut off after the 2nd point
    parallel(("qs", "resumed"), ("ac", "resumed"))
    parallel(("combine", "split"), ("combine", "resumed"))
    names = (moscap2d.CV_CSV, moscap2d.CGX_CSV, moscap2d.MESH_FILE, moscap2d.META_JSON)
    for name in names:
        assert (out / "split" / name).read_bytes() == (out / "both" / name).read_bytes(), name
    for name in (moscap2d.CGX_CSV, moscap2d.MESH_FILE):
        assert (out / "resumed" / name).read_bytes() == (out / "both" / name).read_bytes(), name
    cols, _ = io.read_csv(out / "both" / moscap2d.CV_CSV)
    res, _ = io.read_csv(out / "resumed" / moscap2d.CV_CSV)
    assert list(res["vg"]) == list(cols["vg"])
    for k in ("c_per_area", "cgg_per_um"):
        assert list(res[k])[:2] == list(cols[k])[:2]  # the points before the cut-off: exact
        for a, b in zip(res[k], cols[k], strict=True):
            assert math.isclose(a, b, rel_tol=1e-12), (k, a, b)
    meta = {s: json.loads((out / s / moscap2d.META_JSON).read_bytes()) for s in ("both", "resumed")}
    assert {k: v for k, v in meta["resumed"].items() if k != "sweep"} == {
        k: v for k, v in meta["both"].items() if k != "sweep"
    }
    for s in ("both", "resumed"):  # the same round-off points (their diagnostics may move)
        meta[s] = [(r["index"], r["vg"]) for r in meta[s]["sweep"]["qs_roundoff_accepted"]]
    assert meta["resumed"] == meta["both"]
    gx, _ = io.read_csv(out / "both" / moscap2d.CGX_CSV)
    mono = json.loads((out / "mono" / "mono.json").read_bytes())
    for a, b in zip(cols["cgg_per_um"], mono["qs"]["cgg"], strict=True):
        assert math.isclose(a, b, rel_tol=1e-12), (a, b)
    for a, b in zip(gx["cgg_per_um"], mono["ac"]["cgg"], strict=True):
        assert math.isclose(a, b, rel_tol=1e-8), (a, b)
