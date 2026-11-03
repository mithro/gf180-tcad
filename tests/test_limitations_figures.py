# SPDX-License-Identifier: Apache-2.0
"""The figures of the limitations pages (gf180tcad.limitations_figures): deterministic light and
dark twins, drawn from the committed files, each embedded as a pair and cited on its page, and
each showing the numbers its page states."""

import json
import math
import os
import re
import subprocess
import sys
import textwrap

import pytest
from optional import importorskip

importorskip("matplotlib", reason="needs the docs dependency group")

import numpy as np
import test_explained
from test_explained import numeric_literals

from gf180tcad import limitations_figures as lf
from gf180tcad.devices import DEVICES, geometry_id
from gf180tcad.explain import figures as ef
from gf180tcad.known import KNOWN_ENGINE_DIFFS
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.spice import xyce
from gf180tcad.tcad import meshconv, stack

PAGES = sorted((REPO_ROOT / "docs" / "limitations").glob("*.md"))
SRC = REPO_ROOT / "src" / "gf180tcad" / "limitations_figures.py"

# Every figure (test_figures_listed_here_are_all_the_figures holds the list complete).
FIGURES = [
    "engine-diff",
    "engine-subthreshold",
    "vertex-grid",
    "c-over-cox",
    "twod-validation",
    "twod-metrics",
    "roundoff",
    "sd-profile",
    "mesh-grading",
    "meshconv-1d",
    "meshconv-2d",
]

_RENDER = textwrap.dedent(
    """
    import sys
    from gf180tcad import limitations_figures
    sys.stdout.buffer.write(limitations_figures.FIGURES[sys.argv[1]](sys.argv[2]))
    """
)


def _lines(fig, gid: str):
    """Every line of ``fig`` whose gid is ``gid``."""
    return [ln for ax in fig.axes for ln in ax.get_lines() if ln.get_gid() == gid]


def test_figures_listed_here_are_all_the_figures():
    assert sorted(FIGURES) == sorted(lf.FIGURES)


@pytest.mark.parametrize("figure", FIGURES)
@pytest.mark.parametrize("palette", ["light", "dark"])
def test_svg_deterministic(figure, palette):
    """Two fresh processes with different hash seeds give the same bytes, with text kept as text,
    no date and no host path."""
    runs = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run(
            [sys.executable, "-c", _RENDER, figure, palette],
            env=env, capture_output=True, check=True, timeout=300,
        )  # fmt: skip
        runs.append(r.stdout)
    a, b = runs
    assert a.startswith(b"<?xml") and b"<text" in a and a == b
    assert b"<dc:date>" not in a and str(REPO_ROOT).encode() not in a


def test_figure_code_has_no_numeric_literals(monkeypatch):
    """Numbers only in STYLE, UNITS and TOOLS (the tools' defaults, each with its source)."""
    monkeypatch.setattr(test_explained, "TABLES", ("STYLE", "UNITS", "TOOLS"))
    found = numeric_literals(SRC.read_text(encoding="utf-8"))
    assert not found, f"number literals outside STYLE, UNITS and TOOLS: {found}"


def test_figures_have_dark_twins_and_every_page_embeds_pairs(tmp_path):
    lf.write_all(tmp_path)
    light = sorted(p.name.removesuffix("-light.svg") for p in tmp_path.glob("*-light.svg"))
    dark = sorted(p.name.removesuffix("-dark.svg") for p in tmp_path.glob("*-dark.svg"))
    assert light == dark == sorted(lf.FIGURES)
    for name in light:
        assert (tmp_path / f"{name}-light.svg").read_bytes() != (
            tmp_path / f"{name}-dark.svg"
        ).read_bytes()
    used = set()
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        for name in re.findall(r"/_generated/limitations/([\w-]+)-light\.svg", text):
            assert f"/_generated/limitations/{name}-dark.svg" in text, (page.name, name)
            assert name in lf.FIGURES, (page.name, name)
            used.add(name)
        assert text.count(":figclass: only-light") == text.count(":figclass: only-dark"), page
    assert used == set(lf.FIGURES), f"drawn but on no page: {sorted(set(lf.FIGURES) - used)}"


# --- the engine cross-check ---------------------------------------------------------------------


def test_engine_diff_figure_draws_the_known_failures():
    """The cases above the threshold are exactly the known ones at every nfet geometry, with the
    page's values, and the drawn markers are the computed engine differences."""
    d = lf.engine_diffs()
    above = {(dev, sweep) for (dev, _gid, sweep), v in d.items() if v > xyce.ENGINE_DIFF_THRESHOLD}
    assert above == set(KNOWN_ENGINE_DIFFS)
    assert sum(v > xyce.ENGINE_DIFF_THRESHOLD for v in d.values()) == 12
    # The stock column of the engine-cross-check page's two tables, W10/L0.6.
    assert round(d[("nfet_05v0", "w10p0_l0p60", "idvg_lin")], 5) == 5.62e-3
    assert round(d[("nfet_05v0", "w10p0_l0p60", "idvg_sat")], 5) == 6.05e-3
    fig = lf.engine_diff_figure("light")
    for device in ("nfet_05v0", "pfet_05v0"):
        for sweep in ("idvg_lin", "idvg_sat", "idvd"):
            (line,) = _lines(fig, f"{device} {sweep}")
            want = [d[(device, geometry_id(g), sweep)] for g in lf._geometries(device)]
            assert np.array_equal(line.get_ydata(), want)


def test_subthreshold_figure_shows_the_constant_offset():
    """In subthreshold (the page's 1 nA to 1 µA span of Vg) Xyce is 0.58 to 0.59 % higher."""
    c = lf.evidence_curves()
    m = (c["vg"] >= 0.28) & (c["vg"] <= 0.56)
    assert np.all((c["rel"][m] > 0.0058) & (c["rel"][m] < 0.0059))
    fig = lf.engine_subthreshold_figure("light")
    (line,) = _lines(fig, "relative difference")
    assert np.array_equal(line.get_ydata(), c["rel"] * 100, equal_nan=True)


# --- the 2D MOS capacitor -----------------------------------------------------------------------


def test_vertex_grid_meshes_15p2_nm_as_15_nm():
    """The moscap2d page: a 15.2 nm oxide on the 1 nm grid is meshed 15.0 nm thick, Cox 1.3 % too
    large; on the fix's grid it is meshed within 1e-4 relative."""
    v = lf.vertex_grid()
    assert v["t_ox_nm"] == 15.2 and math.isclose(v["default_nm"], 15.0)
    assert round(v["default_cox_error"] * 100, 1) == 1.3
    assert abs(v["fix_nm"] / v["t_ox_nm"] - 1) < 1e-4
    assert v["fix_grid_nm"] == stack.POINT_TOLERANCE_UM * 1e3


def test_c_over_cox_figure_draws_the_committed_curves():
    """1D below 1 at ±5 V with the mesh-convergence page's values; the 2D cells above 1 per drawn
    area at Lmin; the Lmin AC points on the QS curve within 1e-5; L = 2 µm QS only, resumed."""
    page_1d = {"nfet_05v0": (0.98099, 0.97302), "pfet_05v0": (0.95135, 0.97915)}
    for device, (at_m5, at_p5) in page_1d.items():
        k = lf.c_over_cox(device)
        pol = DEVICES[device].polarity
        one = dict(zip(np.round(k["one_d"]["u"] * pol, 6), k["one_d"]["ratio"], strict=True))
        assert round(one[-5.0], 5) == at_m5 and round(one[5.0], 5) == at_p5
        assert k["one_d"]["ratio"].max() < 1  # the mesh-convergence page: below 1 at every bias
        lmin, l2 = lf.CCOX_CELLS[device]
        q = dict(zip(np.round(k[lmin]["u"], 6), k[lmin]["ratio"], strict=True))
        assert q[-5.0] > 1 and q[5.0] > 1
        assert len(k[lmin]["u_ac"]) == 21
        for u, r in zip(k[lmin]["u_ac"], k[lmin]["ratio_ac"], strict=True):
            assert abs(r / q[round(u, 6)] - 1) < 1e-5
        assert len(k[l2]["u_ac"]) == 0 and k[l2]["resumed"] == {"qs": 4}
    fig = lf.c_over_cox_figure("light")
    (line,) = _lines(fig, "nfet_05v0 w10p0_l0p60 AC")
    assert np.array_equal(line.get_ydata(), lf.c_over_cox("nfet_05v0")["w10p0_l0p60"]["ratio_ac"])


def test_two_d_metrics_are_the_validation_files():
    """Every compared 2D cell lies below SPICE on both plateaus (issue #77) and has its depletion
    crossing below SPICE's (issue #108); the Disagree cells are the five of the limitations
    index."""
    rows = lf.two_d_metrics()
    assert len(rows) == 10
    assert all(r["acc"] < 0 and r["inv"] < 0 and r["dv_dep_mv"] < 0 for r in rows)
    disagree = {
        (r["device"], geometry_id(r["geometry"])) for r in rows if r["verdict"] == "Disagree"
    }
    assert disagree == {
        ("nfet_05v0", "w10p0_l0p60"), ("nfet_05v0", "w10p0_l0p70"), ("nfet_05v0", "w1p6_l0p70"),
        ("pfet_05v0", "w10p0_l1p00"), ("pfet_05v0", "w10p0_l2p00"),
    }  # fmt: skip
    for r in rows:
        rec = lf.validation_record(r["device"])["two_d"][geometry_id(r["geometry"])]
        assert r["dv_dep_mv"] == rec["metrics"]["dv_dep_v"] * 1e3
        assert abs(r["acc"]) == rec["metrics"]["plateau_acc_max_rel"] * 100
        assert abs(r["inv"]) == rec["metrics"]["plateau_inv_max_rel"] * 100


def test_two_d_validation_marks_the_recorded_crossings():
    fig = lf.two_d_validation_figure("light")
    for (device, gid), ax in zip(lf.VALIDATION_CELLS, fig.axes, strict=False):
        rec = lf.validation_record(device)["two_d"][gid]
        (dot,) = [ln for ln in ax.get_lines() if ln.get_gid() == "2D u_dep"]
        assert dot.get_xdata()[0] == rec["tcad_crossings"]["u_dep"]
        (ring,) = [ln for ln in ax.get_lines() if ln.get_gid() == "SPICE u_dep"]
        assert ring.get_xdata()[0] == rec["spice_regions"]["u_dep"]
        assert rec["verdict"] == "Disagree"


def test_roundoff_points_are_below_the_criterion():
    """Each accepted solve's update is above what the criterion asks for at its smallest |psi|
    and below the acceptance bound, as the moscap2d page describes (1.6e-16 V, bound 4.2e-15 V)."""
    k = lf.roundoff_points()
    assert len(k["points"]) == 3 and k["rel_tol"] == 1e-10
    for p in k["points"]:
        need = k["rel_tol"] * (p["min_abs_psi"] + lf.TOOLS["devsim_rel_offset_v"])
        assert need < p["abs_error"] < p["roundoff_bound"]
        assert round(p["abs_error"], 17) in (1.6e-16, 1.5e-16)
        assert round(p["roundoff_bound"], 16) == 4.2e-15


def test_sd_profile_straggles_are_the_pages():
    """The moscap2d page: 44.5, 42.0 and 39.9 nm for 5e19, 1e20 and 2e20 cm⁻³; every vertical
    profile meets the body doping at XJ."""
    k = lf.sd_profiles()
    assert [p["peak"] for p in k["peaks"]] == [5e19, 1e20, 2e20]
    assert [round(p["straggle_um"] * 1e3, 1) for p in k["peaks"]] == [44.5, 42.0, 39.9]
    for p in k["peaks"]:
        at_xj = p["peak"] * math.exp(-(k["xj_um"] ** 2) / (2 * p["straggle_um"] ** 2))
        assert math.isclose(at_xj, k["n_body"], rel_tol=1e-12)


# --- mesh convergence ---------------------------------------------------------------------------


def test_mesh_grading_fixed_levels_share_the_bulk_slope():
    """With the grading fixed, every level has the same size beyond a few nm; refined, each level
    is the start size times its scale (the moscap2d page's size_r(d) = r·size(d))."""
    k = lf.grading_curves()
    assert [lv["scale"] for lv in k["levels"]] == list(meshconv.LEVELS_BY_DIM[2])
    d = k["d_nm"]
    far = (d > 50) & (d < 250)
    base = k["levels"][0]["refined"]
    for lv in k["levels"]:
        assert np.allclose(lv["fixed"][far], base[far], rtol=0.05)
        assert np.allclose(lv["refined"], base * lv["scale"], rtol=1e-12)


@pytest.mark.parametrize("dim", [1, 2])
def test_meshconv_figures_draw_the_reports(dim):
    """The largest change of each level is the report's, and the mesh-convergence page's table."""
    page = {
        1: {"nfet_05v0": [3.7e-5, 3.0e-5, 1.5e-5], "pfet_05v0": [3.8e-5, 2.9e-5, 1.4e-5]},
        2: {"nfet_05v0": [0.00256, 0.00092], "pfet_05v0": [0.00170, 0.00076]},
    }[dim]
    k = lf.meshconv_curves(dim)
    for device, want in page.items():
        got = [float(np.max(lv["change"])) for lv in k[device]["levels"]]
        digits = 6 if dim == 1 else 5
        assert [round(g, digits) for g in got] == want
        assert k[device]["selected"] == (0 if dim == 1 else 1)


# --- the plugin history ---------------------------------------------------------------------------


def test_pn_slab_figure_draws_the_records():
    """The junction drop stays at 0.83450 V at every step of both records while anode − cathode
    falls by 0.1 V a step: the plugin-history page's ramp tables."""
    for name in lf.PLUGIN_RECORDS:
        steps = lf.pn_slab_steps(name)
        assert [s["bias"] for s in steps] == [0.0, 0.1, 0.2]
        assert {round(s["drop"], 5) for s in steps} == {0.8345}
        amc = [round(s["anode_minus_cathode"], 4) for s in steps]
        assert amc == [0.9587, 0.8587, 0.7587]
    fig = lf.pn_slab_figure("light")
    (line,) = _lines(fig, "v0.8.0 drop")
    assert np.array_equal(line.get_ydata(), [s["drop"] for s in lf.pn_slab_steps("v0.8.0")])


def test_pin_widths_are_the_pages():
    k = lf.pin_widths()
    for pts in k.values():
        assert [(b, round(w, 3)) for b, w in pts] == [(0.0, 0.069), (-1.0, 0.138)]


def test_page_figures_render_in_both_palettes():
    for name in lf.FIGURES:
        for palette in ef.PALETTES:
            assert lf.FIGURES[name](palette).startswith(b"<?xml"), name


def test_figure_data_come_from_the_roots(tmp_path):
    """A figure reads the trees it is given: an empty TCAD tree is a FileNotFoundError, never a
    figure drawn from the committed tree."""
    roots = lf.Roots(spice=tmp_path / "spice", tcad=tmp_path / "tcad")
    with pytest.raises(FileNotFoundError):
        lf.c_over_cox("nfet_05v0", roots)
    with pytest.raises(FileNotFoundError):
        lf.engine_diffs(roots)


def test_validation_files_exist():
    for device in DEVICES:
        assert json.loads((REPO_ROOT / "results" / "tcad" / "validation" / f"{device}.json")
                          .read_text("utf-8"))["two_d"]  # fmt: skip
