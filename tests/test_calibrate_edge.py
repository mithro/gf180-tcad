# SPDX-License-Identifier: Apache-2.0
"""The poly length bias fit (gf180tcad.calibrate.edge): it reproduces the edge study's least
squares from the δ = 0 cells it was made from, freezes its inputs, and refuses an uncommitted
checkout."""

import hashlib
import json
import math
import subprocess

import numpy as np
import pytest

from gf180tcad import limitations_figures as lf
from gf180tcad.calibrate import edge
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.tcad import edgefit

# The relative tolerance of a refit against the frozen fit: the least squares runs through
# numpy's LAPACK, whose last bits differ between hosts (CI's runner against the project's host).
REFIT_REL = 1e-12


def _same(a, b, rel: float = REFIT_REL) -> bool:
    """``a`` equals ``b``, floats to ``rel`` (relative), everything else exactly."""
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isclose(
            a, b, rel_tol=rel, abs_tol=0.0)  # fmt: skip
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k], rel) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y, rel) for x, y in zip(a, b, strict=True))
    return a == b


DEVICES = tuple(edge.RECORD_CELLS)


def _frozen_tree(device: str, tmp_path):
    """A TCAD tree of the δ = 0 cells the committed fit was made from: each cell's cv.csv at the
    fit's commit (``git show``), its sha256 checked against the fit file."""
    fit = edgefit.read(device)
    assert fit is not None, f"{device}: no committed fit under results/tcad/edgefit"
    root = tmp_path / "tcad"
    for row in fit["cells"]:
        rel = f"results/tcad/moscap2d/{device}/{edge.CELL_PARAMS}/{row['gid']}/cv.csv"
        data = subprocess.run(["git", "show", f"{fit['commit']}:{rel}"], cwd=REPO_ROOT,
                              check=True, capture_output=True).stdout  # fmt: skip
        assert hashlib.sha256(data).hexdigest() == row["cv_csv_sha256"], row["gid"]
        dest = root / "moscap2d" / device / edge.CELL_PARAMS / row["gid"] / "cv.csv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return fit, root


@pytest.mark.parametrize("device", DEVICES)
def test_fit_is_the_edge_study_s_least_squares(device, tmp_path):
    """On the δ = 0 cells it was made from, the fit is the committed fit file, and it gives the
    δ, slope, targets and residuals of limitations_figures.edge_fit (the numbers the docs
    print), to round-off."""
    committed, root = _frozen_tree(device, tmp_path)
    d = edge.build(device, tcad_root=root, commit=committed["commit"])
    # the applied δ is on the layout grid, so it must match exactly; the rest to round-off
    assert d[edgefit.PARAM] == committed[edgefit.PARAM]
    assert _same(json.loads(json.dumps(d)), committed)
    ref = lf.edge_fit(device, edge.RECORD_CELLS[device])
    ls = d["least_squares"]
    assert math.isclose(ls[edgefit.PARAM], ref["delta_nm"], rel_tol=1e-12)
    # the applied δ is the least-squares one on the layout grid
    assert d[edgefit.PARAM] == round(ref["delta_nm"] / edge.LAYOUT_GRID_NM) * edge.LAYOUT_GRID_NM
    assert abs(d[edgefit.PARAM] - ref["delta_nm"]) <= edge.LAYOUT_GRID_NM / 2
    assert math.isclose(d["slope_ff_per_um_per_nm"], ref["slope"], rel_tol=1e-12)
    for got, want in zip(d["targets_ff_per_um"], ref["targets"], strict=True):
        assert math.isclose(got, want, rel_tol=1e-9, abs_tol=1e-12)
    for got, want in zip(ls["residual_ff_per_um"], ref["residual"], strict=True):
        assert math.isclose(got, want, rel_tol=1e-9, abs_tol=1e-12)
    # the residual at the applied δ moves by slope × the rounding, at most half a grid step
    slope = d["slope_ff_per_um_per_nm"]
    for got, want in zip(d["residual_ff_per_um"], ls["residual_ff_per_um"], strict=True):
        assert math.isclose(got - want, slope * (ls[edgefit.PARAM] - d[edgefit.PARAM]),
                            rel_tol=1e-9, abs_tol=1e-15)  # fmt: skip


@pytest.mark.parametrize("device", DEVICES)
def test_fit_rederives_from_its_frozen_inputs(device):
    """δ comes back from the file's own rows and the record alone, with no live cell."""
    d = edge.build(device, commit="0" * 40)
    rec = json.loads(edge.record_path(device).read_text("utf-8"))
    again = edge.fit(device, rec, d["cells"])
    assert again[edgefit.PARAM] == d[edgefit.PARAM]
    lengths = [r["l_um"] for r in d["cells"]]
    assert lengths == sorted(lengths)
    assert len(d["cells"]) >= 3 and all(len(r["cv_csv_sha256"]) == 64 for r in d["cells"])


@pytest.mark.parametrize("device", DEVICES)
def test_intercept_weights_give_the_intercepts(device):
    """Σ wᵢ cᵢ is the fitted edge; Σ wᵢ = 1 (a constant shift moves the edge by itself)."""
    d = edge.build(device, commit="0" * 40)
    w = np.array(d["intercept_weights"])
    assert math.isclose(w.sum(), 1.0, abs_tol=1e-12)
    for k, key in enumerate(("spice", "two_d")):
        for i in range(len(edge.EDGE_U_V)):
            c = np.array([r[key][i] for r in d["cells"]])
            want = d["spice_edge_ff_per_um" if k == 0 else "two_d_edge_ff_per_um"][i]
            assert math.isclose(float(w @ c), want, rel_tol=1e-9, abs_tol=1e-12)


def test_a_record_without_bias_variants_is_refused():
    rec = {"variants": {"base": {"vg": [-5.0, 5.0], "cgg_ff_per_um": [1.0, 1.0]}}}
    with pytest.raises(ValueError, match="no bias<nm> variant"):
        edge.record_slope(rec, "nfet_05v0")


def test_two_lengths_are_refused():
    rows = [{"l_um": 1.0, "spice": [1, 1], "two_d": [1, 1]}] * 2
    with pytest.raises(ValueError, match="needs 3"):
        edge.fit("nfet_05v0", {"variants": {}}, rows)


def test_a_dirty_checkout_is_refused(monkeypatch):
    monkeypatch.setattr(edge, "_git", lambda *a, **k: " M src/x.py\n")
    with pytest.raises(edge.DirtyCheckout, match="uncommitted"):
        edge.clean_commit()


def test_run_writes_the_fit_and_its_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(edge, "clean_commit", lambda: "1" * 40)
    path = edge.run("nfet_05v0", tmp_path)
    d = json.loads(path.read_text("utf-8"))
    assert d["commit"] == "1" * 40 and d["schema"] == edgefit.SCHEMA
    assert edgefit.read("nfet_05v0", tmp_path)[edgefit.PARAM] == d[edgefit.PARAM]
    prov = json.loads((tmp_path / "provenance.json").read_text("utf-8"))
    assert prov["generator"] == edge.EDGE_MAIN and prov["images"] == {}


def test_main_reports_a_dirty_checkout(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(edge, "_git", lambda *a, **k: " M data/x.toml\n")
    assert edge.main(["--device", "nfet_05v0", "--out", str(tmp_path)]) == 2
    assert "uncommitted" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())
