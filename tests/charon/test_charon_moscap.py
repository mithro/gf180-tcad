# SPDX-License-Identifier: Apache-2.0
"""The Charon MOS capacitor jobs (gf180tcad.charon): the DEVSIM job's inputs, the DEVSIM result
layout plus the backend key, the host command, and (sandbox-marked, in the Charon image) the C-V
against the exact Poisson-Boltzmann reference and DEVSIM, and two runs byte for byte."""

import json
import math

import numpy as np
import pytest

from gf180tcad import charon, io, sandbox
from gf180tcad.charon import __main__ as charon_main
from gf180tcad.charon import moscap as charon_moscap
from gf180tcad.tcad import image_ref, meshconv, moscap1d, process

REPO = sandbox.REPO_ROOT
DEVSIM_1D = REPO / "results" / "tcad" / "moscap1d"


def _devsim_meta(device: str, params: str) -> dict:
    return json.loads((DEVSIM_1D / device / params / moscap1d.PER_AREA_META).read_text("utf-8"))


def _fake_cv(device="nfet_05v0", params="start"):
    from gf180tcad.tcad.__main__ import load_params

    proc, cal = load_params(device, params)
    stack = moscap1d.stack_of(proc)
    vg = (-1.0, 0.0, 1.0)
    pts = tuple(moscap1d.Point(True, 7, 1e-3, math.nan) for _ in vg)
    cv = charon_moscap.CharonCV(
        device=device, vg=vg, c_per_area_ff_um2=(2.0, 1.0, 2.0), points=pts,
        constants=process.CONSTANTS, mesh=meshconv.selected_spec(device, 1), stack=stack,
        node_count=686, strip_node_count=1372, mesh_sha256="0" * 64,
        settings={"srh_lifetime_s": 1e-15, "substeps": 5},
    )  # fmt: skip
    return cv, proc, cal


def test_writes_devsim_layout_plus_backend_key(tmp_path):
    cv, proc, cal = _fake_cv()
    charon_moscap.write(cv, tmp_path, proc=proc, params="start", mesh_source="m", image="img",
                        calibration_sha256=cal)  # fmt: skip
    cols, meta = io.read_csv(tmp_path / moscap1d.PER_AREA_CSV)
    devsim_cols, devsim_csv_meta = io.read_csv(
        DEVSIM_1D / "nfet_05v0" / "start" / moscap1d.PER_AREA_CSV
    )
    assert list(cols) == list(devsim_cols) == list(moscap1d.CSV_COLUMNS)
    assert meta["backend"] == "charon"
    assert set(meta) == set(devsim_csv_meta) | {"backend"}
    m = json.loads((tmp_path / moscap1d.PER_AREA_META).read_text())
    devsim_meta = _devsim_meta("nfet_05v0", "start")
    assert m["backend"] == "charon"
    added = {"backend", "charon", "mesh_sha256"}
    dropped = {"mesh_1d_note"}  # the DEVSIM oxide-spacing note
    assert set(m) == (set(devsim_meta) - dropped) | added
    for k in ("constants", "device", "dim", "dv_fb_shift", "mesh", "mesh_1d_spacing_um", "params",
              "stack", "tunables", "unit"):  # fmt: skip
        assert m[k] == devsim_meta[k], k


def test_meta_records_charon_settings(tmp_path):
    cv, proc, cal = _fake_cv()
    charon_moscap.write(cv, tmp_path, proc=proc, params="start", mesh_source="m", image="img",
                        calibration_sha256=cal)  # fmt: skip
    m = json.loads((tmp_path / moscap1d.PER_AREA_META).read_text())
    assert m["charon"] == {"srh_lifetime_s": 1e-15, "substeps": 5, "image": "img",
                           "strip_node_count": 1372}  # fmt: skip
    assert m["mesh_sha256"] == "0" * 64
    cols, _ = io.read_csv(tmp_path / moscap1d.PER_AREA_CSV)
    assert all(math.isnan(v) for v in cols["abs_error"])


def test_job_reads_back_with_the_devsim_reader(tmp_path):
    cv, proc, cal = _fake_cv()
    charon_moscap.write(cv, tmp_path, proc=proc, params="start", mesh_source="m", image="img",
                        calibration_sha256=cal)  # fmt: skip
    cols, _ = io.read_csv(tmp_path / moscap1d.PER_AREA_CSV)
    assert list(cols["vg"]) == list(cv.vg)
    assert list(cols["c_per_area"]) == list(cv.c_per_area_ff_um2)


def test_host_uses_charon_image(tmp_path, monkeypatch):
    seen = {}

    class Res:
        stdout = "nfet_05v0/start: 3 points\n"

    def fake_run(cmd, *, out_dir, image, mem, cpus):
        seen.update(cmd=cmd, image=image, mem=mem, cpus=cpus)
        cv, proc, cal = _fake_cv()
        charon_moscap.write(cv, out_dir, proc=proc, params="start", mesh_source="m",
                            image=image, calibration_sha256=cal)  # fmt: skip
        return Res()

    monkeypatch.setattr(sandbox, "run", fake_run)
    monkeypatch.setattr(charon_main, "gplugins_commit", lambda: "0" * 40)
    monkeypatch.setattr(charon_main, "tree_provenance", lambda *a, **k: {"fake": True})
    charon_main.run_host("nfet_05v0", "start", tmp_path)
    assert seen["image"] == image_ref("charon") == charon.charon_image()
    assert seen["mem"] == "2g" and seen["cpus"] == 1
    assert seen["cmd"][:4] == ["python3", "-m", "gf180tcad.charon", "moscap-job"]
    assert (tmp_path / "nfet_05v0" / "start" / moscap1d.PER_AREA_META).is_file()
    with pytest.raises(NotImplementedError, match="Task E"):
        charon_main.run_host("nfet_05v0", "start", tmp_path, dim=2)


def test_job_refuses_outside_the_sandbox(tmp_path):
    with pytest.raises(RuntimeError, match="inside the sandbox"):
        charon_main.run_job("nfet_05v0", "start", tmp_path)


# --- in the Charon image ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def driver_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("charon_driver")
    sandbox.run(
        ["python3", "/work/src/tests/charon/charon_driver.py"],
        out_dir=out, image=image_ref("charon"), mem="2g", cpus=1,
    )  # fmt: skip
    return out


@pytest.fixture(scope="module")
def driver(driver_dir):
    return json.loads((driver_dir / "driver.json").read_text())


@pytest.mark.sandbox
@pytest.mark.parametrize("device", process.DEVICES)
def test_qs_matches_exact_poisson_boltzmann(driver, device):
    d = driver[device]
    worst = max(abs(t / e - 1) for t, e in zip(d["charon"], d["exact"], strict=True))
    assert worst < 1e-3, worst


@pytest.mark.sandbox
@pytest.mark.parametrize("device", process.DEVICES)
def test_qs_equals_devsim_1d(driver, device):
    d = driver[device]
    rel = np.abs(np.asarray(d["charon"]) / np.asarray(d["devsim"]) - 1)
    assert np.max(rel) < meshconv.CRITERION, float(np.max(rel))


@pytest.mark.sandbox
def test_byte_identical(driver):
    assert driver["nfet_05v0"]["csv_sha256"] == driver["nfet_again_csv_sha256"]


@pytest.mark.sandbox
@pytest.mark.parametrize("device", process.DEVICES)
@pytest.mark.parametrize("params", ("start", "calibrated"))
def test_stack_is_the_devsim_jobs(driver, device, params):
    """The Charon description has the DEVSIM job's nodes, spacings and constants."""
    meta = _devsim_meta(device, params)
    d = driver["stacks"][f"{device}/{params}"]
    assert d["node_count"] == meta["node_count"]
    assert d["spacing"] == meta["mesh_1d_spacing_um"]
    for k, v in meta["constants"].items():
        assert d["constants"][k] == v, k
    assert d["constants"]["eps_ox"] == meta["stack"]["eps_ox"]
    assert len(d["nodes_sha256"]) == 64


@pytest.mark.sandbox
def test_exodus_reads_back_with_meshio(driver, driver_dir):
    """The strip the backend writes reads back with meshio: the same points, a block per layer."""
    import meshio

    m = meshio.read(driver_dir / "strip.exo")
    assert np.array_equal(m.points[:, :2], np.asarray(driver["stacks"]["strip_xy_um"]))
    assert [len(c.data) for c in m.cells] == driver["stacks"]["strip_blocks"]


@pytest.mark.sandbox
@pytest.mark.parametrize("device", process.DEVICES)
def test_meta_records_the_achieved_convergence(driver_dir, device):
    """Each job's meta has the WRMS tolerances and, per side, every grid point's Newton
    iterations, F-norm and WRMS norm, each converged (WRMS norm below 1)."""
    m = json.loads((driver_dir / f"job_{device}" / moscap1d.PER_AREA_META).read_text())
    c = m["charon"]
    assert (c["wrms_rel_tol"], c["wrms_abs_tol"]) == (1e-9, 1e-11)
    assert set(c["newton_per_point"]) == {"sweep_minus", "sweep_plus"}
    for side, pts in c["newton_per_point"].items():
        assert len(pts) == m["points"], side
        assert all(0 < p["iterations"] and p["wrms"] < 1 and p["f_norm"] >= 0 for p in pts), side
