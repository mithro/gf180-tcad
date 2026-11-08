# SPDX-License-Identifier: Apache-2.0
"""The figures of the limitations pages (gf180tcad.limitations_figures): deterministic light and
dark twins, drawn from the committed files, each embedded as a pair and cited on its page, and
each showing the numbers its page states."""

import ast
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
from matplotlib.collections import PathCollection, PolyCollection
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from test_explained import numeric_literals

from gf180tcad import io
from gf180tcad import limitations_figures as lf
from gf180tcad.calibrate.cv import No2DResult
from gf180tcad.devices import DEVICES, geometry_id
from gf180tcad.explain import figures as ef
from gf180tcad.known import KNOWN_ENGINE_DIFFS
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.spice import xyce
from gf180tcad.tcad import analytic, meshconv, process, stack

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
    "pn-slab",
    "pin-depletion",
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
    for name in lf.plugin_records():
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


# The figures drawn from no results tree: the process files and the meshing and stack code.
NO_ROOT = {"vertex-grid", "sd-profile"}


@pytest.mark.parametrize("name", sorted(set(FIGURES) - NO_ROOT))
def test_figure_data_come_from_the_roots(name, tmp_path):
    """A figure reads the trees it is given: empty trees are a missing-file error (an OSError,
    or calibrate.cv's No2DResult for the 2D cells), never a figure drawn from the committed
    trees."""
    roots = lf.Roots(spice=tmp_path / "spice", older_pdk=tmp_path / "old", tcad=tmp_path / "tcad")
    with pytest.raises((OSError, No2DResult)):
        lf.FIGURES[name]("light", roots)


def test_plugin_root_is_beside_the_spice_tree(tmp_path):
    assert lf.plugin_root() == lf.PLUGIN_ROOT
    roots = lf.Roots(spice=tmp_path / "spice", tcad=tmp_path / "tcad")
    assert lf.plugin_root(roots) == tmp_path / "plugin-history"


def test_validation_files_exist():
    for device in DEVICES:
        assert json.loads((REPO_ROOT / "results" / "tcad" / "validation" / f"{device}.json")
                          .read_text("utf-8"))["two_d"]  # fmt: skip


# --- no number typed into the code: numeric literals and digits in strings -----------------------


def string_digits(source: str, allowed: set[str]) -> list[tuple[int, str]]:
    """(line, text) of each string literal of the module (f-string parts included) that holds a
    digit once the ``allowed`` names are taken out. Skipped: docstrings, raise messages, format
    specs and the :data:`TABLES` (STYLE, UNITS and TOOLS, where each number has its source). A
    number in a label must come from the data, the code that defines it or TOOLS."""
    tree = ast.parse(source)
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            skip |= set(ast.walk(node))
        if isinstance(node, ast.FormattedValue) and node.format_spec is not None:
            skip |= set(ast.walk(node.format_spec))
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                skip.add(first.value)
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        if isinstance(node, ast.Assign | ast.AnnAssign) and any(
            isinstance(t, ast.Name) and t.id in TABLES for t in targets
        ):
            skip |= set(ast.walk(node))
    out = []
    for node in ast.walk(tree):
        if node in skip or not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value.isidentifier():
            continue  # a key or a name (n_ch_cm3, slab90, moscap2d), never a label's number
        text = node.value
        for name in sorted(allowed, key=len, reverse=True):
            text = text.replace(name, "")
        if re.search(r"\d", text):
            out.append((node.lineno, node.value))
    return out


TABLES = ("STYLE", "UNITS", "TOOLS")


def _allowed_names() -> set[str]:
    """Names that hold digits but are identifiers, not numbers: the devices and their geometry
    ids, the plugin-history record files, the figures, the dimensions of the model, the model's
    name and the text encoding."""
    gids = {geometry_id(g) for d in DEVICES.values() for g in d.geometries}
    names = set(DEVICES) | gids | set(lf.PLUGIN_FILES) | set(lf.LATEST_FILES) | set(lf.FIGURES)
    return names | {"1D", "2D", "BSIM4", "utf-8"}


def test_figure_code_has_no_numeric_literals(monkeypatch):
    """Numbers only in STYLE, UNITS and TOOLS (the tools' defaults, each with its source)."""
    monkeypatch.setattr(test_explained, "TABLES", TABLES)
    found = numeric_literals(SRC.read_text(encoding="utf-8"))
    assert not found, f"number literals outside STYLE, UNITS and TOOLS: {found}"


def test_figure_strings_type_no_numbers():
    found = string_digits(SRC.read_text(encoding="utf-8"), _allowed_names())
    assert not found, f"numbers typed into strings (derive them from the data): {found}"


def test_positive_control_string_digits():
    src = (
        '"""Module docstring at 25 C."""\n'
        'TOOLS = {"version": "4.6.1"}\n'
        'NAMES = {"a": "2D, calibrated at 25 C"}\n'
        "def f(ax, g):\n"
        '    """At 1 MHz."""\n'
        "    ax.plot([], label='ngspice (BSIM4 4.5)')\n"
        "    ax.set_xlabel(f'Vg (V), Vds = {g:g} V, Vbs = 0')\n"
        "    ax.text(0, 0, 'nfet_05v0 2D')\n"
        "    ax.plot([], g['n_ch_cm3'])\n"
        "    ax.text(0, 0, f'{g:.0e}')\n"
        "    raise ValueError('2 things')\n"
    )
    found = sorted(line for line, _ in string_digits(src, {"nfet_05v0", "2D"}))
    assert found == [3, 6, 7]


# --- the drawn data: every artist of every figure against the committed files ------------------
#
# Each check_<figure> draws nothing itself: it reads the committed files here, independently of
# gf180tcad.limitations_figures, and compares every line, scatter, fill and bar of the figure (found
# by its gid) with them. Drawn.done() fails on an artist no check compared, so a new curve cannot
# go untested, and test_every_drawn_artist_is_checked doubles each artist in turn and requires
# the check to fail.

DEV = ("nfet_05v0", "pfet_05v0")
SWEEPS = ("idvg_lin", "idvg_sat", "idvd")


def _csv(*parts) -> dict:
    return io.read_csv(REPO_ROOT.joinpath("results", *parts))[0]


def _json(*parts) -> dict:
    return json.loads(REPO_ROOT.joinpath("results", *parts).read_text("utf-8"))


def _close(a, b, rel=1e-12) -> bool:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape == b.shape and np.allclose(a, b, rtol=rel, atol=0, equal_nan=True)


def _by_falling_w_l(device: str):
    return sorted(DEVICES[device].geometries, key=lambda g: (-g.w_um, -g.l_um))


def _artists(fig) -> list:
    """Every drawn artist of ``fig``: the lines, collections and patches of its axes."""
    return [a for ax in fig.axes for a in (*ax.get_lines(), *ax.collections, *ax.patches)]


class Drawn:
    """The artists of a figure by gid, remembering which ones a check has compared."""

    def __init__(self, fig):
        self.fig, self.seen = fig, set()

    def __call__(self, gid: str, ax=None):
        axes = [ax] if ax is not None else self.fig.axes
        found = [a for x in axes for a in (*x.get_lines(), *x.collections, *x.patches)
                 if a.get_gid() == gid]  # fmt: skip
        assert len(found) == 1, (gid, len(found))
        self.seen.add(id(found[0]))
        return found[0]

    def line(self, gid: str, x, y, ax=None):
        ln = self(gid, ax)
        assert _close(ln.get_xdata(), x), (gid, "x")
        assert _close(ln.get_ydata(), y), (gid, "y")

    def hline(self, gid: str, y, ax=None):
        ln = self(gid, ax)
        assert _close(ln.get_ydata(), [y, y]), gid

    def vline(self, gid: str, x, ax=None):
        ln = self(gid, ax)
        assert _close(ln.get_xdata(), [x, x]), gid

    def points(self, gid: str, x, y, ax=None):
        """A scatter's points."""
        off = self(gid, ax).get_offsets()
        assert _close(off[:, 0], x) and _close(off[:, 1], y), gid

    def hspan(self, gid: str, lo, hi, ax=None):
        r = self(gid, ax)
        assert _close([r.get_y(), r.get_y() + r.get_height()], [lo, hi]), gid

    def fill(self, gid: str, x, lo, hi, ax=None):
        """A fill_between of lo to hi over x: its outline is exactly those points."""
        got = np.unique(np.asarray(self(gid, ax).get_paths()[0].vertices, float), axis=0)
        x = np.asarray(x, float)
        want = np.unique(np.concatenate([np.column_stack([x, np.broadcast_to(lo, x.shape)]),
                                         np.column_stack([x, np.broadcast_to(hi, x.shape)])]),
                         axis=0)  # fmt: skip
        assert got.shape == want.shape and _close(got, want), gid

    def done(self):
        missing = [a.get_gid() for a in _artists(self.fig) if id(a) not in self.seen]
        assert not missing, f"drawn but compared with no file: {missing}"


def check_engine_diff(fig):
    forced = json.loads(
        (REPO_ROOT / "data" / "spice" / "engine-forced-bsim46.json").read_text("utf-8")
    )
    d = Drawn(fig)
    for ax, device in zip(fig.axes, DEV, strict=True):
        gs = _by_falling_w_l(device)
        assert [t.get_text() for t in ax.get_xticklabels()] == [lf._label(g) for g in gs]
        ticks = ax.get_xticks()
        for sweep in SWEEPS:
            want = [
                xyce.engine_diff(
                    _csv("spice", "ngspice", "typical", device, geometry_id(g), f"{sweep}.csv"),
                    _csv("spice", "xyce", "typical", device, geometry_id(g), f"{sweep}.csv"),
                )
                for g in gs
            ]
            ln = d(f"{device} {sweep}", ax)
            assert _close(ln.get_ydata(), want), sweep
            # Each marker sits beside its geometry's tick, within half a tick spacing.
            assert np.all(np.abs(ln.get_xdata() - ticks) < 1 / 2), sweep
            if device == forced["device"]:  # the card forced to 4.6 (#161), hollow, same x
                at46 = d(f"{device} {sweep} at 4.6", ax)
                want46 = [forced["cases"][geometry_id(g)][sweep]["forced_4p6"] for g in gs]
                assert np.array_equal(at46.get_ydata(), want46), sweep
                assert np.allclose(at46.get_xdata() - ln.get_xdata(),
                                   lf.STYLE["forced_offset"], rtol=0, atol=1e-12), sweep  # fmt: skip
                assert at46.get_markerfacecolor() == "none", sweep
        d.hline("threshold", xyce.ENGINE_DIFF_THRESHOLD, ax)
    d.done()


def check_engine_subthreshold(fig):
    d = Drawn(fig)
    top, bottom = fig.axes
    a = _csv("spice", "ngspice", "typical", "nfet_05v0", "w10p0_l0p60", "idvg_sat.csv")
    b = _csv("spice", "xyce", "typical", "nfet_05v0", "w10p0_l0p60", "idvg_sat.csv")
    keep = a["vb"] == 0
    vg, x, y = a["vg"][keep], a["id"][keep], b["id"][keep]
    d.line("ngspice", vg, np.abs(x), top)
    d.line("xyce", vg, np.abs(y), top)
    d.hline("floor", xyce.ENGINE_DIFF_FLOOR, top)
    den = np.maximum(np.abs(x), np.abs(y))
    rel = [(q - p) / m if m > xyce.ENGINE_DIFF_FLOOR else np.nan for p, q, m in zip(x, y, den)]
    d.line("relative difference", vg, np.asarray(rel) * 100, bottom)
    d.hline("threshold +1", xyce.ENGINE_DIFF_THRESHOLD * 100, bottom)
    d.hline("threshold -1", -xyce.ENGINE_DIFF_THRESHOLD * 100, bottom)
    (vd,) = set(a["vd"][keep])
    assert bottom.get_xlabel() == f"Vg (V), Vds = {vd:g} V, Vbs = 0 V"
    d.done()


def check_vertex_grid(fig):
    d = Drawn(fig)
    t = process.load("nfet_05v0").values()["t_ox_eff_nm"]
    (ax,) = fig.axes
    half = lf.STYLE["box_width"] / 2
    grids = {"default": lf.TOOLS["meshwell_point_tolerance_um"] * 1e3,
             "fix": stack.POINT_TOLERANCE_UM * 1e3}  # fmt: skip
    for x0, (key, grid) in enumerate(grids.items()):
        d.fill(f"meshed {key}", [x0 - half, x0 + half], 0, round(t / grid) * grid, ax)
        d.line(f"drawn {key}", [x0 - half, x0 + half], [t, t], ax)
    lo, hi = lf.STYLE["grid_span_nm"]
    g = grids["default"]
    for n in range(math.ceil(lo / g), math.floor(hi / g) + 1):
        d.line(f"grid line {n * g:g}", [-half, half], [n * g] * 2, ax)
    d.done()


def _cox_ff_um2(device: str) -> float:
    s = _json("tcad", "moscap1d", device, "start", "per_area.meta.json")["stack"]
    return analytic.f_per_cm2_to_ff_per_um2(analytic.cox_f_per_cm2(s["t_ox_nm"], s["eps_ox"]))


def check_c_over_cox(fig):
    d = Drawn(fig)
    for ax, device in zip(fig.axes, DEV, strict=True):
        pol, cox = DEVICES[device].polarity, _cox_ff_um2(device)
        one = _csv("tcad", "moscap1d", device, "start", "per_area.csv")
        d.line(f"{device} 1D", pol * one["vg"], one["c_per_area"] / cox, ax)
        for gid in lf.CCOX_CELLS[device]:
            l_um = _json("tcad", "moscap2d", device, "start", gid, "cv.meta.json")["l_um"]
            qs = _csv("tcad", "moscap2d", device, "start", gid, "cv.csv")
            d.line(f"{device} {gid} QS", pol * qs["vg"], qs["cgg_per_um"] / l_um / cox, ax)
            cgx = REPO_ROOT / "results/tcad/moscap2d" / device / "start" / gid / "cgx.csv"
            if cgx.is_file():
                ac = _csv("tcad", "moscap2d", device, "start", gid, "cgx.csv")
                d.line(f"{device} {gid} AC", pol * ac["vg"], ac["cgg_per_um"] / l_um / cox, ax)
        d.hline("C = Cox", 1, ax)
    d.done()


def check_two_d_validation(fig):
    from gf180tcad.devices import CORNERS

    d = Drawn(fig)
    for ax, (device, gid) in zip(fig.axes, lf.VALIDATION_CELLS, strict=True):
        pol = DEVICES[device].polarity
        curves = []
        for corner in CORNERS:
            cols = _csv("spice", "ngspice", corner, device, gid, "cv.csv")
            order = np.argsort(pol * cols["vg"], kind="stable")
            curves.append((corner, (pol * cols["vg"])[order], cols["cgg"][order] * 1e15))
        (u,) = {tuple(c[1]) for c in curves}
        stack_ = np.array([c[2] for c in curves])
        d.fill("corners", u, stack_.min(axis=0), stack_.max(axis=0), ax)
        d.line("typical", u, {c[0]: c[2] for c in curves}["typical"], ax)
        cal = _csv("tcad", "moscap2d", device, "calibrated", gid, "cv.csv")
        order = np.argsort(pol * cal["vg"], kind="stable")
        d.line("2D", (pol * cal["vg"])[order], cal["cgg_total"][order], ax)
        rec = _json("tcad", "validation", f"{device}.json")["two_d"][gid]
        c_mid = rec["spice_regions"]["c_mid"]
        d.hline("c_mid", c_mid, ax)
        d.line("SPICE u_dep", [rec["spice_regions"]["u_dep"]], [c_mid], ax)
        d.line("2D u_dep", [rec["tcad_crossings"]["u_dep"]], [c_mid], ax)
    d.done()


def _metric_rows() -> list[tuple[str, dict]]:
    rows = []
    for device in DEV:
        two_d = _json("tcad", "validation", f"{device}.json")["two_d"]
        for g in _by_falling_w_l(device):
            rec = two_d.get(geometry_id(g))
            if rec is not None and rec["status"] == "compared":
                rows.append((device, rec))
    return rows


def _hollow(coll) -> list[bool]:
    """Per point of a scatter, whether its face is transparent."""
    faces = coll.get_facecolors()
    return [bool(f[3] == 0) for f in np.broadcast_to(faces, (len(coll.get_offsets()), 4))]


def check_two_d_metrics(fig):
    d = Drawn(fig)
    top, bottom = fig.axes
    rows = _metric_rows()
    x = np.arange(len(rows))
    (tol,) = {r["verdicts"]["dv_dep"]["tolerance_v"] for _d, r in rows}
    d.hspan("tolerance", -tol * 1e3, tol * 1e3, top)
    d.points("dv_dep", x, [r["metrics"]["dv_dep_v"] * 1e3 for _d, r in rows], top)
    assert _hollow(d("dv_dep", top)) == [
        r["verdicts"]["dv_dep"]["verdict"] == "Same process" for _d, r in rows
    ]
    d.hline("zero dv_dep", 0, top)
    (ptol,) = {r["verdicts"][f"plateau_{p}"]["tolerance"] for _d, r in rows for p in ("acc", "inv")}
    d.hspan("plateau tolerance", -ptol * 100, ptol * 100, bottom)
    for part in ("acc", "inv"):
        want = [max(r["residuals"][f"plateau_{part}_rel"], key=abs) * 100 for _d, r in rows]
        assert [abs(w) for w in want] == pytest.approx(
            [r["metrics"][f"plateau_{part}_max_rel"] * 100 for _d, r in rows], rel=1e-12
        )
        d.points(f"plateau {part}", x, want, bottom)
        assert _hollow(d(f"plateau {part}", bottom)) == [
            r["verdicts"][f"plateau_{part}"]["verdict"] == "Same process" for _d, r in rows
        ]
    d.hline("zero plateau", 0, bottom)
    d.done()


def check_roundoff(fig):
    d = Drawn(fig)
    (ax,) = fig.axes
    rep = _json("tcad", "meshconv", "moscap2d", "nfet_05v0", "report.json")
    pts = [p for lv in rep["levels"] for p in lv["roundoff_accepted"]]
    crit = d("criterion", ax)
    psi = np.asarray(crit.get_xdata(), float)
    offset = lf.TOOLS["devsim_rel_offset_v"]
    assert _close(crit.get_ydata(), rep["settings"]["rel_tol"] * (psi + offset))
    (bound,) = {p["roundoff_bound"] for p in pts}
    d.hline("roundoff bound", bound, ax)
    d.line("accepted", [p["min_abs_psi"] for p in pts], [p["abs_error"] for p in pts], ax)
    d.done()


def check_sd_profile(fig):
    d = Drawn(fig)
    top, bottom = fig.axes
    proc = process.load("pfet_05v0")
    v = proc.values()
    for f in lf.STYLE["sd_factors"]:
        peak = v["sd_peak_cm3"] * f
        s = stack.sd_straggle_um(proc, peak)
        lat = stack.LATERAL_STRAGGLE_RATIO * s
        vert = d(f"vertical {peak:.0e}", top)
        y_um = np.asarray(vert.get_xdata(), float) / 1e3
        assert _close(vert.get_ydata(), peak * np.exp(-(y_um**2) / (2 * s**2)))
        surf = d(f"surface {peak:.0e}", bottom)
        x_um = np.asarray(surf.get_xdata(), float) / 1e3
        want = [peak * (1 - math.erf(x / (math.sqrt(2) * lat))) / 2 for x in x_um]
        assert _close(surf.get_ydata(), want)
    for ax in (top, bottom):
        d.hline("body doping", v["n_ch_cm3"], ax)
    d.vline("XJ", v["xj_um"] * 1e3, top)
    d.vline("gate edge", 0, bottom)
    d.done()


def check_mesh_grading(fig):
    d = Drawn(fig)
    (ax,) = fig.axes
    rep = _json("tcad", "meshconv", "moscap2d", "nfet_05v0", "report.json")
    st = rep["start"]
    for i, lv in enumerate(rep["levels"]):
        r, sp = lv["scale"], lv["spec"]
        ref = d(f"level {i} refined", ax)
        dist = np.asarray(ref.get_xdata(), float)
        want = np.minimum(sp["h_si_surface_nm"] + (sp["grading"] - 1) * dist, sp["h_si_bulk_nm"])
        assert _close(ref.get_ydata(), want), i
        fixed = np.minimum(st["h_si_surface_nm"] * r + (st["grading"] - 1) * dist,
                           st["h_si_bulk_nm"] * r)  # fmt: skip
        d.line(f"level {i} fixed", dist, fixed, ax)
    d.done()


def _check_meshconv(fig, dim: int):
    d = Drawn(fig)
    cols = 2 if dim == 2 else 1
    for row, device in enumerate(DEV):
        rep = _json("tcad", "meshconv", f"moscap{dim}d", device, "report.json")
        pol = DEVICES[device].polarity
        ax = fig.axes[row * cols]
        u = pol * np.asarray(rep["vg"])
        for i, lv in enumerate(rep["levels"]):
            if lv["rel_change"] is not None:
                d.line(f"{device} level {i}", u, np.abs(lv["rel_change"]), ax)
        d.hline("criterion", rep["criterion"], ax)
        if dim == 2:
            ax2 = fig.axes[row * cols + 1]
            for i, lv in enumerate(rep["levels"]):
                cur = lv.get("agreement_1d_curve")
                if cur:
                    d.line(f"{device} agreement {i}", pol * np.asarray(cur["vg"]),
                           np.abs(cur["rel"]), ax2)  # fmt: skip
            crit = rep["selected"]["criteria"]["agreement_1d"]["max"]
            d.hline("agreement criterion", crit, ax2)
    d.done()


def check_meshconv_1d(fig):
    _check_meshconv(fig, 1)


def check_meshconv_2d(fig):
    _check_meshconv(fig, 2)


def _plugin() -> dict[str, dict]:
    out = {}
    for file in ("v0.8.0.json", "v0.8.0-mesh0p5.json"):
        rec = _json("plugin-history", file)
        name = rec["gplugins_tag"] + ("" if rec["mesh_scale"] == 1 else f" × {rec['mesh_scale']:g}")
        out[name] = rec
    return out


def check_pn_slab(fig):
    d = Drawn(fig)
    top, bottom = fig.axes
    recs = _plugin()
    w = lf.STYLE["bar_width"]
    slots = []
    for name, rec in recs.items():
        dd = rec["ddcomponent"]
        steps = [{"v": 0.0, **dd["equilibrium"]}, *dd["bias"]]
        b = [s["v"] for s in steps]
        d.line(f"{name} anode-cathode", b, [s["anode_minus_cathode_v"] for s in steps], top)
        d.line(f"{name} drop", b, [s["junction"]["drop_v"] for s in steps], top)
        for region in ("core", "slab90"):
            for s in steps:
                bar = d(f"{name} {region} {s['v']:g}", bottom)
                lo, hi = s["potential_range_by_region"][region]
                assert _close([bar.get_y(), bar.get_height(), bar.get_width()], [lo, hi - lo, w])
                slots.append(round((bar.get_x() + w / 2 - s["v"]) / w, 9))
    # Each record and region has its own slot beside the bias, the same at every step.
    assert len(set(slots)) == len(recs) * 2
    # The latest-stack records (#162): the measured drop of the connected rib, each mesh.
    for file in ("latest.json", "latest-mesh0p5.json"):
        rec = json.loads((REPO_ROOT / "results" / "plugin-history" / file).read_text("utf-8"))
        slab = rec["pn_slab"]
        scale = rec["mesh_scale"]
        name = rec["gplugins_tag"] + ("" if scale == 1 else f" × {scale:g}")
        drops = [s["junction"]["drop_v"] for s in (slab["equilibrium"], *slab["bias"])]
        d.line(f"{name} drop", slab["bias_v"], drops, top)
    d.done()


def check_pin_depletion(fig):
    d = Drawn(fig)
    (ax,) = fig.axes
    for name, rec in _plugin().items():
        pts = rec["pin"]["bias"]
        d.line(name, [p["v"] for p in pts], [p["depletion_width_um"] for p in pts], ax)
    d.done()


CHECKS = {
    "engine-diff": (lf.engine_diff_figure, check_engine_diff),
    "engine-subthreshold": (lf.engine_subthreshold_figure, check_engine_subthreshold),
    "vertex-grid": (lf.vertex_grid_figure, check_vertex_grid),
    "c-over-cox": (lf.c_over_cox_figure, check_c_over_cox),
    "twod-validation": (lf.two_d_validation_figure, check_two_d_validation),
    "twod-metrics": (lf.two_d_metrics_figure, check_two_d_metrics),
    "roundoff": (lf.roundoff_figure, check_roundoff),
    "sd-profile": (lf.sd_profile_figure, check_sd_profile),
    "mesh-grading": (lf.mesh_grading_figure, check_mesh_grading),
    "meshconv-1d": (lf.meshconv_1d_figure, check_meshconv_1d),
    "meshconv-2d": (lf.meshconv_2d_figure, check_meshconv_2d),
    "pn-slab": (lf.pn_slab_figure, check_pn_slab),
    "pin-depletion": (lf.pin_depletion_figure, check_pin_depletion),
}


def test_every_figure_has_a_drawn_data_check():
    assert sorted(CHECKS) == sorted(lf.FIGURES)


@pytest.mark.parametrize("palette", ["light", "dark"])
@pytest.mark.parametrize("figure", FIGURES)
def test_drawn_data_are_the_committed_files(figure, palette):
    draw, check = CHECKS[figure]
    check(draw(palette))


def _is_vertical(line) -> bool:
    """An axvline: x in data, y spanning the axes."""
    return line.get_transform() == line.axes.get_xaxis_transform()


def mutate(artist):
    """Double what ``artist`` draws (its y, or x for a vertical line; add 1 where that is 0, so
    the change is never nothing). Returns the function that undoes it."""

    def changed(v):
        v = np.asarray(v, float)
        return np.where(v == 0, v + 1, v * 2)

    if isinstance(artist, Line2D):
        if _is_vertical(artist):
            old = artist.get_xdata()
            artist.set_xdata(changed(old))
            return lambda: artist.set_xdata(old)
        old = artist.get_ydata()
        artist.set_ydata(changed(old))
        return lambda: artist.set_ydata(old)
    if isinstance(artist, Rectangle):
        y, h = artist.get_y(), artist.get_height()
        artist.set_y(float(changed(y)))
        artist.set_height(float(changed(h)))
        return lambda: (artist.set_y(y), artist.set_height(h))
    if isinstance(artist, PathCollection):
        old = artist.get_offsets().copy()
        new = old.copy()
        new[:, 1] = changed(old[:, 1])
        artist.set_offsets(new)
        return lambda: artist.set_offsets(old)
    if isinstance(artist, PolyCollection):
        path = artist.get_paths()[0]
        old = path.vertices.copy()
        path.vertices[:, 1] = changed(old[:, 1])
        return lambda: path.vertices.__setitem__(slice(None), old)
    raise TypeError(f"no mutation for {type(artist).__name__} {artist.get_gid()}")


def mutation_results(figure: str) -> list[tuple[str, bool]]:
    """``(gid, caught)`` for each drawn artist of ``figure`` doubled in turn and checked."""
    draw, check = CHECKS[figure]
    fig = draw("light")
    check(fig)
    out = []
    for artist in _artists(fig):
        undo = mutate(artist)
        try:
            check(fig)
            caught = False
        except AssertionError:
            caught = True
        undo()
        out.append((str(artist.get_gid()), caught))
    check(fig)
    return out


@pytest.mark.parametrize("figure", FIGURES)
def test_every_drawn_artist_is_checked(figure):
    """Doubling any one line, scatter, fill or bar of the figure makes its check fail."""
    results = mutation_results(figure)
    assert results and all(caught for _gid, caught in results), [
        gid for gid, caught in results if not caught
    ]


def test_positive_control_mutate_changes_zero_lines():
    fig = Figure()
    ax = fig.subplots()
    line = ax.axhline(0, gid="zero")
    undo = mutate(line)
    assert list(line.get_ydata()) == [1, 1]
    undo()
    assert list(line.get_ydata()) == [0, 0]
    edge = ax.axvline(0, gid="edge")
    mutate(edge)
    assert list(edge.get_xdata()) == [1, 1]


# --- the numbers the pages print by substitution -------------------------------------------------


def test_page_numbers_are_the_committed_files():
    """The moscap2d page's round-off and C/Cox numbers (issue #159): substituted from the report
    and the start cell's cv.csv, read here directly, and no longer typed on the page."""
    subs = lf.substitutions()
    rep = _json("tcad", "meshconv", "moscap2d", "nfet_05v0", "report.json")
    (p,) = rep["levels"][lf.ROUNDOFF_LEVEL]["roundoff_accepted"]
    assert subs["lim_roundoff_min_psi"] == "2.1e-7" and float(
        subs["lim_roundoff_min_psi"]
    ) == float(f"{p['min_abs_psi']:.1e}")
    assert subs["lim_roundoff_region"] == p["region"] == "oxide"
    assert float(subs["lim_roundoff_update"]) == float(f"{p['abs_error']:.1e}")
    assert float(subs["lim_roundoff_bound"]) == float(f"{p['roundoff_bound']:.1e}")
    qs = _csv("tcad", "moscap2d", "nfet_05v0", "start", "w10p0_l0p60", "cv.csv")
    l_um = _json("tcad", "moscap2d", "nfet_05v0", "start", "w10p0_l0p60", "cv.meta.json")["l_um"]
    ratio = qs["cgg_per_um"] / l_um / _cox_ff_um2("nfet_05v0")
    assert subs["lim_ccox_acc"] == f"{ratio[np.argmin(qs['vg'])]:.3f}" == "1.068"
    assert subs["lim_ccox_inv"] == f"{ratio[np.argmax(qs['vg'])]:.3f}" == "1.087"
    page = (REPO_ROOT / "docs/limitations/moscap2d.md").read_text("utf-8")
    for key in subs:
        assert f"{{{{ {key} }}}}" in page, key
    for old in ("2.7e-8", "1.071", "1.090"):
        assert old not in page, old


def test_docs_conf_registers_the_substitutions():
    conf = (REPO_ROOT / "docs/conf.py").read_text("utf-8")
    assert "limitations_figures" in conf and ".substitutions()" in conf


def test_forced_record_stock_is_the_figures_filled_markers():
    """The record's stock values are the engine differences of the committed results, which the
    figure draws as the filled nfet markers (review of #179)."""
    record = json.loads(
        (REPO_ROOT / "data" / "spice" / "engine-forced-bsim46.json").read_text("utf-8")
    )
    d = lf.engine_diffs()
    for gid, sweeps in record["cases"].items():
        for sweep, v in sweeps.items():
            assert v["stock"] == pytest.approx(d[(record["device"], gid, sweep)], rel=1e-12), (
                gid,
                sweep,
            )


def _shown(text: str, value: float) -> bool:
    """Whether ``text`` (as the page writes a number, such as 5.62e-3 or 3.9e-5) is ``value``
    rounded to the significant digits the page shows."""
    mantissa = text.split("e")[0].replace(".", "").lstrip("0")
    return float(text) == float(f"{value:.{max(len(mantissa), 1) - 1}e}")


def test_engine_page_forced_values_are_the_record():
    """Issue #161: the engine-cross-check page's stock and forced-4.6 values are those of
    data/spice/engine-forced-bsim46.json, rounded as the page shows them."""
    record = json.loads(
        (REPO_ROOT / "data" / "spice" / "engine-forced-bsim46.json").read_text("utf-8")
    )
    cases = record["cases"]
    page = (REPO_ROOT / "docs" / "limitations" / "engine-cross-check.md").read_text("utf-8")
    nfet = DEVICES[record["device"]]
    by_wl = {(f"{g.w_um:g}", f"{g.l_um:g}"): geometry_id(g) for g in nfet.geometries}
    rows = 0
    for sweep in ("idvg_lin", "idvg_sat"):
        table = page.split(f"The `{sweep}` sweep:", 1)[1].split("\n\n", 2)[1]
        for line in table.splitlines()[2:]:
            w, l, stock, at46 = (c.strip() for c in line.strip("|").split("|"))
            got = cases[by_wl[(w, l)]][sweep]
            assert _shown(stock, got["stock"]), (sweep, w, l, stock, got)
            assert _shown(at46, got["forced_4p6"]), (sweep, w, l, at46, got)
            rows += 1
    assert rows == 2 * len(nfet.geometries)
    # the bisection table at W = 10 um, L = 0.6 um: the stock (4.5) and forced (4.6) values
    l06 = cases[geometry_id(nfet.geometries[0])]
    assert "At W = 10 µm, L = 0.6 µm the record" in page
    assert (nfet.geometries[0].w_um, nfet.geometries[0].l_um) == (10, 0.6)
    table = page.split("| Sweep | ngspice 4.5 (PDK as published) | ngspice 4.6 |", 1)[1]
    table = table.split("\n\n", 1)[0].strip().splitlines()[1:]
    assert len(table) == 3
    for line in table:
        sweep, stock, at46 = (c.strip().strip("`") for c in line.strip().strip("|").split("|"))
        assert _shown(stock, l06[sweep]["stock"]), (sweep, stock)
        assert _shown(at46, l06[sweep]["forced_4p6"]), (sweep, at46)
    remaining = re.search(r"At Vds = 5 V the remaining (\S+) is", page)
    assert remaining and _shown(remaining[1], l06["idvg_sat"]["forced_4p6"])
    # the summary: the forced values' range of each sweep
    m = re.search(r"every nfet geometry agrees: `idvg_lin` (\S+) to\s+(\S+), `idvg_sat` (\S+) to "
                  r"(\S+), `idvd` (\S+) to (\S+)\.", page)  # fmt: skip
    assert m, "summary sentence"
    for k, sweep in enumerate(("idvg_lin", "idvg_sat", "idvd")):
        vals = [cases[gid][sweep]["forced_4p6"] for gid in cases]
        assert _shown(m[2 * k + 1].rstrip(","), min(vals)), (sweep, m[2 * k + 1])
        assert _shown(m[2 * k + 2].rstrip(","), max(vals)), (sweep, m[2 * k + 2])
