# SPDX-License-Identifier: Apache-2.0
"""The 2D mesh-convergence check at the fitted poly length bias (plan Task E3, Decision 5).

The records (``results/meshconv-fitted/<device>.json``, written by
``experiments/meshconv-fitted/record.py``) rerun the committed 2D study's three levels at each
device's Lmin cell with the calibrated values and the committed fit. The level the committed
study selected must still change by less than ``meshconv.CRITERION`` against the next finer
level; if it does not, the mesh is reselected (the plan stops E3b there).
"""

import hashlib
import json
import subprocess

import numpy as np
import pytest

from gf180tcad import limitations_figures as lf
from gf180tcad.devices import geometry_id
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.tcad import calibration, calibration_file, edgefit, meshconv, moscap1d, moscap2d
from gf180tcad.tcad.mesh import MeshSpec

DEVICES = ("nfet_05v0", "pfet_05v0")


def _rec(device: str) -> dict:
    return lf.meshconv_fitted(device)


def _at(commit: str, path: str) -> bytes:
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=REPO_ROOT, check=True,
                          capture_output=True).stdout  # fmt: skip


def test_records_are_the_two_devices():
    files = sorted(p.name for p in lf.MESHCONV_FITTED_ROOT.glob("*.json"))
    assert files == [f"{d}.json" for d in DEVICES]


@pytest.mark.parametrize("device", DEVICES)
def test_selected_level_still_meets_the_criterion(device):
    """The level the committed 2D study selected changes by less than the criterion against the
    next finer level at every bias, at the fitted bias."""
    rec = _rec(device)
    committed = json.loads(
        (
            REPO_ROOT / meshconv.job_dir(meshconv.TREE_ROOT, device, 2) / meshconv.REPORT_NAME
        ).read_bytes()
    )
    sel = committed["selected"]["level"]
    lv = rec["report"]["levels"][sel]
    assert rec["check"] == {
        "criterion": meshconv.CRITERION,
        "selected_level": sel,
        "max_rel_change": lv["max_rel_change"],
        "meets_criterion": True,
    }
    assert max(lv["rel_change"]) == lv["max_rel_change"] < meshconv.CRITERION


@pytest.mark.parametrize("device", DEVICES)
def test_report_is_the_levels(device):
    """The record's report is meshconv.converge over its own level curves, at the committed
    study's levels and start spec, with no 1D-agreement criterion."""
    rec = _rec(device)
    rep = rec["report"]
    assert rep["params"] == "calibrated" and rep["dim"] == 2 and rep["device"] == device
    levels = meshconv.levels(2)
    curves = {}
    for i, (scale, lv) in enumerate(zip(levels, rep["levels"], strict=True)):
        spec = meshconv.START[2].scaled(scale, refine_grading=meshconv.REFINE_GRADING[2])
        assert lv["scale"] == scale and MeshSpec(**lv["spec"]) == spec, i
        curves[spec] = type("Curve", (), {
            "vg": tuple(rep["vg"]),
            "c_per_area_ff_um2": tuple(lv["c_per_area_ff_um2"]),
            "node_count": lv["node_count"],
            "extended_fallback": tuple(lv["extended_fallback"]),
            "roundoff_accepted": tuple(lv["roundoff_accepted"]),
        })()  # fmt: skip
    again = meshconv.converge(
        curves.__getitem__, meshconv.START[2], levels, rel_tol=moscap1d.REL_TOL,
        refine_grading=meshconv.REFINE_GRADING[2],
    )  # fmt: skip
    want = meshconv.report_dict(again, device=device, dim=2, settings={})
    del want["settings"], want["excluded_levels"]
    want["params"] = "calibrated"
    assert json.loads(json.dumps(want)) == rep


@pytest.mark.parametrize("device", DEVICES)
def test_selected_level_is_the_committed_cell(device):
    """The selected level is the committed calibrated cell's mesh at the same geometry: its node
    count is the cell's, and its C per area is the cell's bit for bit (the record's ``cell``;
    docs/limitations/mesh-convergence.md says so). Both sweeps save each point and hand the
    state on in the same way."""
    rec = _rec(device)
    gid = geometry_id(meshconv.geometry_2d(device))
    assert rec["geometry"] == gid
    job = REPO_ROOT / "results" / "tcad" / "moscap2d" / device / "calibrated" / gid
    vg, c, meta = moscap2d.read_cv(job)
    sel = rec["check"]["selected_level"]
    lv = rec["report"]["levels"][sel]
    assert MeshSpec(**lv["spec"]) == MeshSpec(**meta["mesh"])
    assert lv["node_count"] == meta["node_count"] == rec["cell"]["node_count"]
    assert rec["cell"]["edge_fit"] == meta["edge_fit"] == rec["edge_fit"]
    assert tuple(vg) == tuple(rec["report"]["vg"])
    diff = max(abs(a / b - 1) for a, b in zip(lv["c_per_area_ff_um2"], c, strict=True))
    assert rec["cell"]["max_rel_diff"] == diff
    assert diff == 0.0
    assert list(lv["c_per_area_ff_um2"]) == list(c)


@pytest.mark.parametrize("device", DEVICES)
def test_record_pins_what_the_runs_used(device):
    """The runs' pins: the commit is on this branch's history, and at it the image pin, the
    plugin gitlink, level.py and the 2D writer's generator_sha256 are the record's. The fit and
    the 1D calibration are today's."""
    rec = _rec(device)
    commit = rec["commit"]
    subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=REPO_ROOT,
                   check=True)  # fmt: skip
    prov = json.loads(_at(commit, "results/tcad/moscap2d/provenance.json"))
    assert (rec["generator"], rec["generator_sha256"]) == (
        prov["generator"], prov["generator_sha256"])  # fmt: skip
    assert rec["image"] == _at(commit, "docker/TCAD_IMAGE").decode("utf-8").strip()
    tree = subprocess.run(["git", "ls-tree", commit, "third_party/gplugins"], cwd=REPO_ROOT,
                          check=True, capture_output=True, text=True).stdout.split()  # fmt: skip
    assert rec["gplugins_commit"] == tree[2]
    level = _at(commit, "experiments/meshconv-fitted/level.py")
    assert rec["level_py_sha256"] == hashlib.sha256(level).hexdigest()
    assert rec["edge_fit_sha256"] == edgefit.sha256(device)
    assert rec["edge_fit"] == {
        edgefit.PARAM: edgefit.read(device)[edgefit.PARAM], "sha256": edgefit.sha256(device),
    }  # fmt: skip
    cal = calibration_file(device)
    assert rec["calibration_file_sha256"] == hashlib.sha256(cal.read_bytes()).hexdigest()
    assert rec["calibration_values"] == calibration.read(cal, device)


@pytest.mark.parametrize("device", DEVICES)
def test_page_prints_the_records(device):
    """The mesh-convergence page prints the records' numbers through substitutions."""
    subs = {k: v for k, v in lf.substitutions().items() if k.startswith("lim_mcfit_")}
    page = (REPO_ROOT / "docs/limitations/mesh-convergence.md").read_text("utf-8")
    for key in subs:
        assert f"{{{{ {key} }}}}" in page, key
    dev = device.split("_")[0]
    rec = _rec(device)
    for i, lv in enumerate(rec["report"]["levels"]):
        assert subs[f"lim_mcfit_{dev}_nodes_{i}"] == f"{lv['node_count']:,}"
        if lv["max_rel_change"] is not None:
            assert np.isclose(float(subs[f"lim_mcfit_{dev}_change_{i}"]),
                              lv["max_rel_change"] * 100, atol=5e-4)  # fmt: skip
