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
from gf180tcad.tcad import calibration, calibration_file

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


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, check=True, capture_output=True,
                          text=True).stdout  # fmt: skip


def _at(commit: str, path: str) -> bytes:
    """The bytes of ``path`` at ``commit``."""
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=REPO_ROOT, check=True,
                          capture_output=True).stdout  # fmt: skip


@pytest.mark.parametrize(("device", "gid"), CELLS)
def test_record_pins_what_the_runs_used(device, gid):
    """The record is a frozen input of the poly length bias fit (plan Task E3, "Design"): its pins
    are the ones of the commit its runs used (run.py's pins.json, which record.py requires to
    agree), not today's. That commit is on this branch's history (a rebase would drop it), and
    at it the image pin, the plugin gitlink, variant.py and the 2D writer's generator_sha256 (the
    committed moscap2d provenance) are the record's. The 1D calibration is today's: a new 1D
    calibration makes the record, and the fit made from it, stale. Drift of the physics since
    the commit is caught by the sandbox rerun below, which is evidence of every restamp."""
    rec = lf.edge_record(device, gid)
    assert (rec["schema"], rec["device"], rec["geometry"], rec["params"]) == (
        2, device, gid, "calibrated")  # fmt: skip
    assert rec["generator"] == "gf180tcad.tcad.__main__"
    commit = rec["commit"]
    subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=REPO_ROOT,
                   check=True)  # fmt: skip
    prov = json.loads(_at(commit, "results/tcad/moscap2d/provenance.json"))
    assert (prov["generator"], prov["generator_sha256"]) == (
        rec["generator"], rec["generator_sha256"])  # fmt: skip
    assert rec["image"] == _at(commit, "docker/TCAD_IMAGE").decode("utf-8").strip()
    tree = _git("ls-tree", commit, "third_party/gplugins").split()
    assert rec["gplugins_commit"] == tree[2]
    variant = _at(commit, "experiments/edge-sensitivity/variant.py")
    assert rec["variant_py_sha256"] == hashlib.sha256(variant).hexdigest()
    assert rec["calibration_file_sha256"] == _sha256(calibration_file(device))
    assert rec["calibration_values"] == calibration.read(calibration_file(device), device)
    # once the fit is committed (plan Task E3b), it names this record as its input
    from gf180tcad.tcad import edgefit

    fit = edgefit.read(device)
    if fit is not None:
        path = lf.EDGE_ROOT / f"{device}-{gid}.json"
        assert fit["record"] == {"cell": gid, "file": path.name, "sha256": _sha256(path)}


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
    # every run sweeps from accumulation, as the committed jobs do: u = -5 V first
    for v in lf.edge_record(device, gid)["variants"].values():
        assert [pol * vg for vg in v["vg"]] == list(lf.STYLE["edge_u_v"])
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


@pytest.mark.parametrize(("device", "gid"), CELLS)
def test_edge_gains_are_at_u(device, gid):
    """Each variant's gain at u = -5 V is Cgg minus the base's at Vg = -5 V × polarity, read
    from the raw record (the pfet's u = -5 V is Vg = +5 V)."""
    rec = lf.edge_record(device, gid)["variants"]
    pol = DEVICES[device].polarity
    base = dict(zip(rec["base"]["vg"], rec["base"]["cgg_ff_per_um"], strict=True))
    for name, (lo, hi) in lf.edge_gains(device, gid).items():
        c = dict(zip(rec[name]["vg"], rec[name]["cgg_ff_per_um"], strict=True))
        assert lo == c[-5.0 * pol] - base[-5.0 * pol], name
        assert hi == c[5.0 * pol] - base[5.0 * pol], name
    if device == "pfet_05v0":
        assert pol == -1 and rec["base"]["vg"] == [5.0, -5.0]


def test_edge_fit_needs_a_bias_variant(monkeypatch):
    monkeypatch.setattr(lf, "edge_gains", lambda *a, **k: {"plugs": (0.0, 0.0)})
    with pytest.raises(ValueError, match="no bias<nm> variant"):
        lf.edge_fit(*CELLS[0])


@pytest.mark.sandbox
@pytest.mark.parametrize(("device", "gid"), CELLS)
def test_rerun_reproduces_the_record(device, gid, tmp_path):
    """A rerun of each record's base and bias30 variants in the sandbox, on today's code, gives
    the record's values exactly (about 50 minutes each, one 16 GiB job at a time). The variants
    build from δ = 0 whatever fit is committed, so this holds across a restamp; it is the
    evidence of every restamp that the records are still what today's code computes. Of the
    pins it compares the image, the plugin commit and the calibration; the generator and
    variant.py hashes are the record's commit's (test_record_pins_what_the_runs_used)."""
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
        pins = json.loads((work / device / gid / v / "pins.json").read_bytes())
        rec = lf.edge_record(device, gid)
        for key in ("image", "gplugins_commit", "calibration_file_sha256",
                    "calibration_values"):  # fmt: skip
            assert pins[key] == rec[key], (v, key)


def _shown(v: float) -> str:
    return f"{v:.3f}".replace("-", "\u2212")


def test_page_prints_the_fit():
    """The moscap2d page's "What the 2D edge needs" numbers are substitutions from the fit and the
    nfet record; every substitution key is on the page; the extension range is the record's
    extension peaks; and the page's claim that no variant adds more at +5 V than at -5 V holds."""
    subs = {k: v for k, v in lf.substitutions().items() if k.startswith("lim_edge_")}
    page = (REPO_ROOT / "docs/limitations/moscap2d.md").read_text("utf-8")
    for key in subs:
        assert f"{{{{ {key} }}}}" in page, key
    for device, gid in CELLS:
        dev = device.split("_")[0]
        fit = lf.edge_fit(device, gid)
        assert subs[f"lim_edge_{dev}_slope"] == f"{fit['slope']:.5f}"
        assert subs[f"lim_edge_{dev}_delta"] == f"{fit['delta_nm']:.1f}"
        acc, inv = fit["residual"]
        assert (subs[f"lim_edge_{dev}_miss_acc"], subs[f"lim_edge_{dev}_miss_inv"]) == (
            _shown(acc), _shown(inv))  # fmt: skip
        # the nfet's fit overfills accumulation, so its miss there is negative
        assert acc < 0 < inv
        row = (f"| {dev} | {{{{ lim_edge_{dev}_slope }}}} | {{{{ lim_edge_{dev}_delta }}}} | "
               f"{{{{ lim_edge_{dev}_miss_acc }}}} | {{{{ lim_edge_{dev}_miss_inv }}}} |")  # fmt: skip
        assert row in page, row
        assert all(hi - lo < 1e-3 for lo, hi in lf.edge_gains(device, gid).values()), device
        step = fit["targets"][1] - fit["targets"][0]
        assert subs[f"lim_edge_{dev}_target_step"] == _shown(step)
    assert "No variant adds as much as 0.001 fF/µm more at +5 V than at −5 V." in page
    gains = lf.edge_gains(*CELLS[0])
    for variant in ("plugs", "bias30"):
        for side, g in zip(("acc", "inv"), gains[variant], strict=True):
            assert subs[f"lim_edge_{variant}_{side}"] == _shown(g)
    variants = lf.edge_record(*CELLS[0])["variants"]
    assert subs["lim_edge_plug_um"] == "0.86" == f"{variants['plugs']['plug_um']:g}"
    ldd = {n: v for n, v in variants.items() if v["ldd"]}
    assert {v["bias_um"] for v in ldd.values()} == {0.065}
    assert {v["ldd"]["spacer_um"] for v in ldd.values()} == {0.1}
    assert (subs["lim_edge_ldd_bias_nm"], subs["lim_edge_ldd_spacer_nm"]) == ("65", "100")
    for i, side in enumerate(("acc", "inv")):
        vals = [gains[n][i] for n in ldd]
        lo, hi = _shown(min(vals)), _shown(max(vals))
        assert subs[f"lim_edge_ldd_{side}"] == (lo if lo == hi else f"{lo} to {hi}")
    peaks = sorted(v["ldd"]["peak"] for v in ldd.values())
    assert (peaks[0], peaks[-1]) == (1e18, 2e19)
    assert "1e18 to 2e19 cm⁻³" in page
    index = (REPO_ROOT / "docs/limitations/index.md").read_text("utf-8")
    assert "too little edge capacitance ({ref}`moscap2d-edge`" in index
    cv = (REPO_ROOT / "docs/comparison/cv-agreement.md").read_text("utf-8")
    assert (
        "None adds as much as 0.001 fF/µm more at +5 V than at −5 V"
        " ({ref}`moscap2d-edge`, [issue #189](https://github.com/mithro/gf180-tcad/issues/189))."
        " The nfet needs {{ lim_edge_nfet_target_step }} fF/µm more there."
    ) in " ".join(cv.split())


def test_page_names_the_extension_shapes():
    """The extension bullet's depths and lateral straggles are the record's."""
    device, gid = CELLS[0]
    shapes = sorted(
        (v["ldd"]["depth_um"], v["ldd"]["lateral"])
        for v in lf.edge_record(device, gid)["variants"].values()
        if v.get("ldd")
    )
    assert shapes == [(0.06, 0.2), (0.06, 0.2), (0.1, 1.0), (0.1, 1.0)]
    page = (REPO_ROOT / "docs/limitations/moscap2d.md").read_text("utf-8")
    assert "Two of the four extensions are 100 nm deep. The other two are 60 nm deep" in page
    assert "straggle of 0.2 times their vertical one" in " ".join(page.split())
