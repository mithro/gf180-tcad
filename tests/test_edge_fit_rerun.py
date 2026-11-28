# SPDX-License-Identifier: Apache-2.0
"""The checks of plan Task E3 ("Design", Decisions 1 and 4) that need the committed poly length
bias fit (results/tcad/edgefit) and the calibrated 2D cells rerun at it.

- The fit's frozen inputs are the δ = 0 cells as committed at the fit's commit (``git show``), and
  δ re-derives from them and the edge-sensitivity record alone.
- Each rerun cell gains slope × δ on both plateaus, within the per-cell tolerance: the 2D mesh
  selection criterion (``meshconv.CRITERION`` of Cgg) plus the record's bound on the bias's
  non-linearity at δ.
- Per device, the live edge split's gap (SPICE C_edge minus 2D C_edge) at each plateau is the
  frozen residual, within Σ|wᵢ| × the per-cell tolerance plus 2 % of slope × δ (wᵢ: the
  least-squares intercept's weights over the lengths).
"""

import hashlib
import json
import math
import subprocess

import numpy as np
import pytest

from gf180tcad import io
from gf180tcad.calibrate import edge
from gf180tcad.devices import DEVICES
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.tcad import edgefit, meshconv

# The relative tolerance of a refit against the frozen fit: the least squares runs through
# numpy's BLAS/LAPACK, whose last bits differ between hosts: on the CI runner by up to 6e-15
# relative (run 46080249276). The rows (inputs) and the applied δ are compared exactly.
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


DEVICE_IDS = tuple(edge.RECORD_CELLS)
CELLS = REPO_ROOT / "results" / "tcad" / "moscap2d"
# 2 % of slope × δ: the record's linearity (bias60 is twice bias30 within 2 %,
# tests/test_edge_sensitivity.py::test_bias_variants_mesh_the_longer_poly).
LINEARITY = 0.02


def _fit(device: str) -> dict:
    fit = edgefit.read(device)
    assert fit is not None, f"{device}: no committed fit under results/tcad/edgefit"
    return fit


def _show(commit: str, rel: str) -> bytes:
    return subprocess.run(["git", "show", f"{commit}:{rel}"], cwd=REPO_ROOT, check=True,
                          capture_output=True).stdout  # fmt: skip


def _cell_rel(device: str, gid: str, name: str) -> str:
    return f"results/tcad/moscap2d/{device}/{edge.CELL_PARAMS}/{gid}/{name}"


def _plateaus(device: str, cols: dict, w_um: float) -> list[float]:
    pol = DEVICES[device].polarity
    u = pol * cols["vg"]
    return [float(cols["cgg_total"][np.flatnonzero(u == x)[0]]) / w_um for x in edge.EDGE_U_V]


def _frozen_rows(device: str, tmp_path) -> list[dict]:
    """The fit's rows rebuilt from the δ = 0 cells at the fit's commit (cell sha256 checked) and
    the live SPICE reference, which E3 does not change."""
    fit = _fit(device)
    root = tmp_path / "tcad"
    for row in fit["cells"]:
        data = _show(fit["commit"], _cell_rel(device, row["gid"], "cv.csv"))
        assert hashlib.sha256(data).hexdigest() == row["cv_csv_sha256"], row["gid"]
        dest = root / "moscap2d" / device / edge.CELL_PARAMS / row["gid"] / "cv.csv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return [edge.cell_row(device, g, tcad_root=root) for g in edge.wide_geometries(device, root)]


@pytest.mark.parametrize("device", DEVICE_IDS)
def test_fit_inputs_are_the_cells_at_the_fit_commit(device, tmp_path):
    """The frozen rows are the δ = 0 cells at the fit's commit and today's SPICE curves, and δ
    re-derives from them and the record (the record's sha256 the fit names)."""
    fit = _fit(device)
    subprocess.run(["git", "merge-base", "--is-ancestor", fit["commit"], "HEAD"], cwd=REPO_ROOT,
                   check=True)  # fmt: skip
    rows = _frozen_rows(device, tmp_path)
    assert rows == fit["cells"]
    rec_path = edge.record_path(device)
    assert hashlib.sha256(rec_path.read_bytes()).hexdigest() == fit["record"]["sha256"]
    again = edge.fit(device, json.loads(rec_path.read_text("utf-8")), rows)
    assert again[edgefit.PARAM] == fit[edgefit.PARAM]
    assert _same(again["least_squares"], fit["least_squares"])


def _nonlinearity_ff_per_um(device: str, fit: dict) -> float:
    """The record's bound on how far the gain at δ departs from slope × δ: the quadratic through
    0, bias30 and bias60 at each plateau, against the fitted line, at the applied δ."""
    rec = json.loads(edge.record_path(device).read_text("utf-8"))["variants"]
    pol = DEVICES[device].polarity

    def at(v):
        by_u = {pol * vg: c for vg, c in zip(v["vg"], v["cgg_ff_per_um"], strict=True)}
        return [by_u[u] for u in edge.EDGE_U_V]

    base, g30, g60 = at(rec["base"]), at(rec["bias30"]), at(rec["bias60"])
    delta, slope = fit[edgefit.PARAM], fit["slope_ff_per_um_per_nm"]
    worst = 0.0
    for b, c30, c60 in zip(base, g30, g60, strict=True):
        y30, y60 = c30 - b, c60 - b
        quad = (y60 - 2 * y30) / (2 * 30.0**2)
        lin = (y30 - quad * 30.0**2) / 30.0
        worst = max(worst, abs(lin * delta + quad * delta**2 - slope * delta))
    return worst


def _per_cell_tolerance(device: str, fit: dict, c_ff_per_um: float) -> float:
    return meshconv.CRITERION * c_ff_per_um + _nonlinearity_ff_per_um(device, fit)


@pytest.mark.parametrize("device", DEVICE_IDS)
def test_each_rerun_cell_gains_slope_times_delta(device):
    """Every W10 cell the fit read is rerun at the committed fit (its meta's edge_fit), and its
    Cgg per unit width rose by slope × δ at each plateau, within the per-cell tolerance. This is
    also the check that the gain does not depend on L: the record measured it at one L only."""
    fit = _fit(device)
    want = fit["slope_ff_per_um_per_nm"] * fit[edgefit.PARAM]
    for row in fit["cells"]:
        job = CELLS / device / edge.CELL_PARAMS / row["gid"]
        meta = json.loads((job / "cv.meta.json").read_bytes())
        assert meta.get("edge_fit") == {
            edgefit.PARAM: fit[edgefit.PARAM], "sha256": edgefit.sha256(device),
        }, row["gid"]  # fmt: skip
        now = _plateaus(device, io.read_csv(job / "cv.csv")[0], row["w_um"])
        for u, c, c0 in zip(edge.EDGE_U_V, now, row["two_d"], strict=True):
            tol = _per_cell_tolerance(device, fit, c)
            assert abs((c - c0) - want) <= tol, (row["gid"], u, c - c0, want, tol)


@pytest.mark.parametrize("device", DEVICE_IDS)
def test_live_edge_gap_is_the_frozen_residual(device):
    """The edge split of the rerun cells leaves, at each plateau, the gap the fit predicted (its
    frozen residual at the applied δ), within Σ|wᵢ| × the largest per-cell tolerance plus 2 % of
    slope × δ."""
    fit = _fit(device)
    rows = [edge.cell_row(device, g) for g in edge.wide_geometries(device)]
    assert [r["gid"] for r in rows] == [r["gid"] for r in fit["cells"]]
    spice, two_d = edge.intercepts(rows, "spice"), edge.intercepts(rows, "two_d")
    weights = np.abs(edge.intercept_weights(rows)).sum()
    shift = fit["slope_ff_per_um_per_nm"] * fit[edgefit.PARAM]
    for i, u in enumerate(edge.EDGE_U_V):
        gap = spice[i] - two_d[i]
        per_cell = max(_per_cell_tolerance(device, fit, r["two_d"][i]) for r in rows)
        bound = weights * per_cell + LINEARITY * shift
        assert abs(gap - fit["residual_ff_per_um"][i]) <= bound, (u, gap, bound)


@pytest.mark.parametrize("device", DEVICE_IDS)
def test_page_check_is_this_check(device):
    """The numbers docs/limitations/moscap2d.md prints for the rerun check
    (limitations_figures.edge_rerun) are the gains, tolerances, gap and bound of the tests
    above."""
    from gf180tcad import limitations_figures as lf

    fit = _fit(device)
    got = lf.edge_rerun(device)
    want = fit["slope_ff_per_um_per_nm"] * fit[edgefit.PARAM]
    assert got["want"] == pytest.approx(want, rel=1e-12)
    assert got["applied_nm"] == fit[edgefit.PARAM]
    assert got["nonlinearity"] == pytest.approx(_nonlinearity_ff_per_um(device, fit), rel=1e-9)
    for row, cell in zip(fit["cells"], got["cells"], strict=True):
        job = CELLS / device / edge.CELL_PARAMS / row["gid"]
        now = _plateaus(device, io.read_csv(job / "cv.csv")[0], row["w_um"])
        assert cell["gid"] == row["gid"]
        assert cell["gain"] == pytest.approx(
            [c - c0 for c, c0 in zip(now, row["two_d"])], rel=1e-12
        )
        assert cell["tol"] == pytest.approx([_per_cell_tolerance(device, fit, c) for c in now],
                                            rel=1e-9)  # fmt: skip
    rows = [edge.cell_row(device, g) for g in edge.wide_geometries(device)]
    spice, two_d = edge.intercepts(rows, "spice"), edge.intercepts(rows, "two_d")
    assert got["gap"] == pytest.approx([a - b for a, b in zip(spice, two_d)], rel=1e-12)
    assert got["residual"] == list(fit["residual_ff_per_um"])
    weights = np.abs(edge.intercept_weights(rows)).sum()
    assert got["weights"] == pytest.approx(weights, rel=1e-12)
    for i in range(len(edge.EDGE_U_V)):
        per_cell = max(_per_cell_tolerance(device, fit, r["two_d"][i]) for r in rows)
        assert got["bound"][i] == pytest.approx(weights * per_cell + LINEARITY * want, rel=1e-9)


@pytest.mark.parametrize("device", DEVICE_IDS)
def test_the_bound_is_set_by_the_longest_cell(device):
    """docs/limitations/moscap2d.md: the per-device bound is set by the W10/L2 cell, whose 1 % of
    Cgg is the largest per-cell tolerance and, times Σ|wᵢ|, most (over half) of the bound."""
    fit = _fit(device)
    rows = [edge.cell_row(device, g) for g in edge.wide_geometries(device)]
    weights = np.abs(edge.intercept_weights(rows)).sum()
    shift = fit["slope_ff_per_um_per_nm"] * fit[edgefit.PARAM]
    for i in range(len(edge.EDGE_U_V)):
        tols = {r["gid"]: _per_cell_tolerance(device, fit, r["two_d"][i]) for r in rows}
        assert max(tols, key=tols.get) == "w10p0_l2p00"
        longest = next(r for r in rows if r["gid"] == "w10p0_l2p00")
        bound = weights * max(tols.values()) + LINEARITY * shift
        assert weights * meshconv.CRITERION * longest["two_d"][i] > bound / 2
