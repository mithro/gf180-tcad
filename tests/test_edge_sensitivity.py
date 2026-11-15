# SPDX-License-Identifier: Apache-2.0
"""The edge-sensitivity records of issue #189 (experiments/edge-sensitivity/): what each record
pins, its base against the committed calibrated 2D cell, and the least-squares poly length bias
that limitations_figures.edge_fit derives from it."""

import hashlib
import json
import math
import subprocess
import sys

import numpy as np
import pytest

from gf180tcad import io
from gf180tcad import limitations_figures as lf
from gf180tcad.comparison_figures import edge_split
from gf180tcad.devices import DEVICES
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.tcad import calibration_file

HERE = REPO_ROOT / "experiments" / "edge-sensitivity"
CELLS = list(lf.EDGE_CELLS)

# The fitted bias per side (nm) and the residual misfit at each plateau (fF/µm) that the docs
# state (docs/limitations/moscap2d.md, "What the 2D edge needs").
FITTED = {"nfet_05v0": (40.2, 0.109), "pfet_05v0": (61.5, 0.030)}


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cell_cv(device: str, gid: str) -> dict:
    cols, _ = io.read_csv(
        REPO_ROOT / "results" / "tcad" / "moscap2d" / device / "calibrated" / gid / "cv.csv"
    )
    return cols


def test_records_are_the_listed_cells():
    files = sorted(p.name for p in lf.EDGE_ROOT.glob("*.json"))
    assert files == sorted(f"{d}-{g}.json" for d, g in CELLS)


@pytest.mark.parametrize(("device", "gid"), CELLS)
def test_record_pins_what_the_runs_used(device, gid):
    """The record names the image, the plugin commit, variant.py and the calibration file that
    its runs used, and each is the one committed now: a change to any makes the record stale."""
    rec = lf.edge_record(device, gid)
    assert (rec["schema"], rec["device"], rec["geometry"], rec["params"]) == (
        1, device, gid, "calibrated")  # fmt: skip
    assert rec["image"] == (REPO_ROOT / "docker" / "TCAD_IMAGE").read_text("utf-8").strip()
    tree = subprocess.run(["git", "ls-tree", "HEAD", "third_party/gplugins"], cwd=REPO_ROOT,
                          check=True, capture_output=True, text=True).stdout.split()  # fmt: skip
    assert rec["gplugins_commit"] == tree[2]
    assert rec["variant_py_sha256"] == _sha256(HERE / "variant.py")
    assert rec["calibration_file_sha256"] == _sha256(calibration_file(device))


@pytest.mark.parametrize(("device", "gid"), CELLS)
def test_record_base_is_the_committed_cell(device, gid):
    """The harness's base variant solves the committed cell: the same node count and meshed
    length, and its Cgg per unit width at each plateau within 1e-9 of the committed cv.csv (the
    variant starts each bias from equilibrium, the committed sweep from the bias before)."""
    base = lf.edge_record(device, gid)["variants"]["base"]
    cv = _cell_cv(device, gid)
    meta = json.loads(
        (
            REPO_ROOT / "results/tcad/moscap2d" / device / "calibrated" / gid / "cv.meta.json"
        ).read_text("utf-8")
    )
    assert base["node_count"] == meta["node_count"]
    assert base["meshed_l_um"] == meta["meshed_l_um"]
    assert base["bias_um"] == 0.0 and not base["plugs"] and base["ldd"] is None
    pol = DEVICES[device].polarity
    assert sorted(pol * v for v in base["vg"]) == list(lf.STYLE["edge_u_v"])
    for vg, c in zip(base["vg"], base["cgg_ff_per_um"], strict=True):
        (i,) = np.flatnonzero(cv["vg"] == vg)
        assert math.isclose(c, cv["cgg_per_um"][i], rel_tol=1e-9), (vg, c)


@pytest.mark.parametrize(("device", "gid"), CELLS)
def test_bias_variants_mesh_the_longer_poly(device, gid):
    """Each bias<nm> variant meshes a poly 2 × nm longer than the drawn length, and its gain is
    linear in the bias: bias60's is twice bias30's within 2 %, on both plateaus."""
    rec = lf.edge_record(device, gid)["variants"]
    l_um = rec["base"]["meshed_l_um"]
    for name, v in rec.items():
        if name.startswith("bias") and name[len("bias") :].isdigit():
            nm = float(name[len("bias") :])
            assert math.isclose(v["bias_um"], nm / 1000, abs_tol=1e-12)
            assert math.isclose(v["meshed_l_um"], l_um + 2 * nm / 1000, abs_tol=1e-9)
    gains = lf.edge_gains(device, gid)
    for lo30, lo60 in zip(gains["bias30"], gains["bias60"], strict=True):
        assert math.isclose(lo60, 2 * lo30, rel_tol=0.02)


@pytest.mark.parametrize(("device", "gid"), CELLS)
def test_edge_fit_is_the_least_squares_bias(device, gid):
    """Re-derived from the record's raw Cgg and the edge split: the slope is the least-squares
    line through the origin of every bias<nm> variant's gain at both plateaus; δ makes slope × δ
    the mean of the two plateaus' edge gaps (SPICE minus 2D), so the residuals are equal and
    opposite. The fitted δ and residual are the ones the docs state."""
    rec = lf.edge_record(device, gid)["variants"]
    base = dict(zip(rec["base"]["vg"], rec["base"]["cgg_ff_per_um"], strict=True))
    xs, ys = [], []
    for name, v in rec.items():
        if name.startswith("bias") and name[len("bias") :].isdigit():
            for vg, c in zip(v["vg"], v["cgg_ff_per_um"], strict=True):
                xs.append(float(name[len("bias") :]))
                ys.append(c - base[vg])
    x, y = np.array(xs), np.array(ys)
    slope = float(np.linalg.lstsq(x[:, None], y, rcond=None)[0][0])
    split = edge_split(device)
    gaps = []
    for u in lf.STYLE["edge_u_v"]:
        (i,) = np.flatnonzero(split["u"] == u)
        gaps.append(float(split["spice"]["edge"][i] - split["two_d"]["edge"][i]))
    delta = sum(gaps) / 2 / slope

    fit = lf.edge_fit(device, gid)
    assert math.isclose(fit["slope"], slope, rel_tol=1e-12)
    assert np.allclose(fit["targets"], gaps, rtol=1e-12)
    assert math.isclose(fit["delta_nm"], delta, rel_tol=1e-12)
    lo, hi = fit["residual"]
    assert math.isclose(lo, -hi, rel_tol=1e-9)
    want_delta, want_residual = FITTED[device]
    assert f"{fit['delta_nm']:.1f}" == f"{want_delta:.1f}"
    assert f"{abs(hi):.3f}" == f"{want_residual:.3f}"


def test_edge_fit_needs_a_bias_variant(monkeypatch):
    monkeypatch.setattr(lf, "edge_gains", lambda *a, **k: {"plugs": (0.0, 0.0)})
    with pytest.raises(ValueError, match="no bias<nm> variant"):
        lf.edge_fit(*CELLS[0])


@pytest.mark.sandbox
def test_rerun_reproduces_the_record(tmp_path):
    """A rerun of the nfet's base and bias30 variants in the sandbox gives the record's values
    exactly (about 50 minutes each, one 16 GiB job at a time)."""
    device, gid = CELLS[0]
    work = tmp_path / "work"
    variants = ["base", "bias30"]
    r = subprocess.run([sys.executable, str(HERE / "run.py"), str(work), device, gid, *variants],
                       cwd=REPO_ROOT, check=False)  # fmt: skip
    assert r.returncode == 0
    want = lf.edge_record(device, gid)["variants"]
    for v in variants:
        got = json.loads((work / device / gid / v / "result.json").read_bytes())
        for key in ("vg", "cgg_ff_per_um", "node_count", "meshed_l_um", "bias_um"):
            assert got[key] == want[v][key], (v, key)


def test_page_prints_the_fit():
    """The moscap2d page's "What the 2D edge needs" numbers are substitutions from the fit and the
    nfet record, and its extension range is the record's extension peaks."""
    subs = lf.substitutions()
    page = (REPO_ROOT / "docs/limitations/moscap2d.md").read_text("utf-8")
    for device, gid in CELLS:
        dev = device.split("_")[0]
        fit = lf.edge_fit(device, gid)
        assert subs[f"lim_edge_{dev}_slope"] == f"{fit['slope']:.5f}"
        assert subs[f"lim_edge_{dev}_delta"] == f"{fit['delta_nm']:.1f}"
        assert subs[f"lim_edge_{dev}_residual"] == f"{abs(fit['residual'][0]):.3f}"
        row = (f"| {dev} | {{{{ lim_edge_{dev}_slope }}}} | {{{{ lim_edge_{dev}_delta }}}} | "
               f"±{{{{ lim_edge_{dev}_residual }}}} |")  # fmt: skip
        assert row in page, row
    gains = lf.edge_gains(*CELLS[0])
    for variant in ("plugs", "bias30"):
        for side, g in zip(("acc", "inv"), gains[variant], strict=True):
            key = f"lim_edge_{variant}_{side}"
            assert subs[key] == f"{g:.3f}".replace("-", "\u2212")
            assert f"{{{{ {key} }}}}" in page, key
    peaks = sorted(v["ldd"]["peak"] for v in lf.edge_record(*CELLS[0])["variants"].values()
                   if v["ldd"])  # fmt: skip
    assert (peaks[0], peaks[-1]) == (1e18, 2e19)
    assert "1e18 to 2e19 cm⁻³" in page
    index = (REPO_ROOT / "docs/limitations/index.md").read_text("utf-8")
    assert "too little edge capacitance ({ref}`moscap2d-edge`" in index
