# SPDX-License-Identifier: Apache-2.0
"""The figures of the comparison pages (gf180tcad.comparison_figures): deterministic light and
dark twins, drawn from the committed files, each embedded as a pair and cited on its page."""

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

from test_explained import numeric_literals

from gf180tcad import comparison_figures as cf
from gf180tcad.devices import DEVICES, geometry_id
from gf180tcad.sandbox import REPO_ROOT

PAGES = sorted((REPO_ROOT / "docs" / "comparison").glob("*.md"))
SRC = REPO_ROOT / "src" / "gf180tcad" / "comparison_figures.py"

# Every figure (test_figures_listed_here_are_all_the_figures holds the list complete).
FIGURES = [
    "process-cell",
    "instance-plan",
    "geometries",
    "meshconv",
    "cv-fit",
    "cv-validation",
    "cv-metric",
    "pfet-edge",
    "edge-capacitance",
    "start-stack",
    "cgg-split",
    "centroid",
    "pdk-sweeps",
]

_RENDER = textwrap.dedent(
    """
    import sys
    from gf180tcad import comparison_figures
    sys.stdout.buffer.write(comparison_figures.FIGURES[sys.argv[1]](sys.argv[2]))
    """
)


def test_figures_listed_here_are_all_the_figures():
    assert sorted(FIGURES) == sorted(cf.FIGURES)


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


def test_figure_code_has_no_numeric_literals():
    found = numeric_literals(SRC.read_text(encoding="utf-8"))
    assert not found, f"number literals outside STYLE and UNITS: {found}"


def test_figures_have_dark_twins_and_every_page_embeds_pairs(tmp_path):
    cf.write_all(tmp_path)
    light = sorted(p.name.removesuffix("-light.svg") for p in tmp_path.glob("*-light.svg"))
    dark = sorted(p.name.removesuffix("-dark.svg") for p in tmp_path.glob("*-dark.svg"))
    assert light == dark == sorted(cf.FIGURES)
    for name in light:
        assert (tmp_path / f"{name}-light.svg").read_bytes() != (
            tmp_path / f"{name}-dark.svg"
        ).read_bytes()
    used = set()
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        for name in re.findall(r"/_generated/comparison/([\w-]+)-light\.svg", text):
            assert f"/_generated/comparison/{name}-dark.svg" in text, (page.name, name)
            assert name in cf.FIGURES, (page.name, name)
            used.add(name)
        assert text.count(":figclass: only-light") == text.count(":figclass: only-dark"), page
    assert used == set(cf.FIGURES), f"drawn but on no page: {sorted(set(cf.FIGURES) - used)}"


def test_instance_plan_reads_the_netlist_template():
    """The source/drain length is the template's AS / W: the xschem symbol's diffusion length,
    _DIFF of the netlist module; W and L are the plan geometry's."""
    from gf180tcad.spice.netlist import _DIFF

    e = cf.instance_extents()
    g = _plan_geometry()
    assert (e["w_um"], e["l_um"]) == (g.w_um, g.l_um)
    assert math.isclose(e["sd_um"], float(_DIFF), rel_tol=1e-12)


def _result(device: str) -> dict:
    path = REPO_ROOT / "results" / "tcad" / "calibration" / f"{device}.result.json"
    return json.loads(path.read_text("utf-8"))


def test_metric_figure_marks_the_calibration_regions():
    """The u_fb, u_t, C_mid and crossings drawn are the ones the calibration recorded."""
    _u, _c, r = cf.metric_regions()
    rec = _result(cf.METRIC_DEVICE)["per_geometry"][cf.METRIC_GEOMETRY]["spice_regions"]
    for key in ("u_fb", "u_t", "c_mid", "u_dep", "u_inv", "c_acc", "c_inv"):
        assert math.isclose(getattr(r, key), rec[key], rel_tol=1e-12), key


def test_pfet_edge_marks_the_recorded_crossings():
    """Each SPICE u_dep is the one its committed record holds: the calibration result file for a
    calibration geometry, the validation file for a held-out one."""
    curves = cf.edge_curves()
    printed = _page_u_dep()
    assert [c["geometry"].l_um for c in curves] == list(printed)
    for c in curves:
        rec = _record("pfet_05v0", geometry_id(c["geometry"]))
        assert math.isclose(c["u_dep"], rec["spice_regions"]["u_dep"], rel_tol=1e-12)
    # Page consistency: the cv-agreement page prints these five values (mismatch analysis).
    assert [round(c["u_dep"], 3) for c in curves] == list(printed.values())


def _page_u_dep() -> dict[float, float]:
    """L (µm) -> the SPICE u_dep (V) that the committed C-V page prints for the pfet, in the
    page's order (mismatch analysis)."""
    page = (REPO_ROOT / "docs/comparison/cv-agreement.md").read_text("utf-8")
    segment = " ".join(page[page.index("it is at u_dep = ") : page.index(", a spread")].split())
    pairs = re.findall(r"−([\d.]+) V for (?:L = |Lmin \()?([\d.]+) µm", segment)
    assert len(pairs) == 5, segment
    return {float(l_um): -float(u) for u, l_um in pairs}


def _plan_geometry():
    (g,) = [g for g in DEVICES[cf.PLAN_DEVICE].geometries if geometry_id(g) == cf.PLAN_GEOMETRY]
    return g


def test_centroid_figure_marks_the_allowance_maximum():
    """The marked point is the largest accumulation X_DC in the window, as the process file's
    allowance computes it, and lies on the drawn curve."""
    for device in DEVICES:
        k = cf.centroid_curves(device)
        cen = k["centroid"]
        u_max = cen.vg_at_max_v * k["polarity"]
        drawn = dict(zip(k["u"].tolist(), k["x_acc_nm"].tolist(), strict=True))
        assert math.isclose(drawn[u_max], cen.x_dc_acc_max_m * 1e9, rel_tol=1e-12)
        window = [x for u, x in drawn.items() if u <= -cen.plateau_v]
        assert math.isclose(max(window), cen.x_dc_acc_max_m * 1e9, rel_tol=1e-12)


def test_meshconv_points_skip_the_finest_level():
    for dim in (1, 2):
        for device in DEVICES:
            report = cf.meshconv_report(dim, device)
            nodes, change = cf.meshconv_points(report)
            assert len(nodes) == len(report["levels"]) - 1 == len(change)
            assert all(c < report["criterion"] for c in change)


def test_pdk_sweeps_are_one_curve_per_body_bias():
    for device in DEVICES:
        new = cf.pdk_sweep_curves(device, cf.SPICE_ROOT)
        old = cf.pdk_sweep_curves(device, cf.OLDER_PDK_ROOT)
        assert len(new) == len(old) == 3
        for (a, b), (c, d) in zip(new, old, strict=True):
            assert a.tolist() == c.tolist() and b.tolist() == d.tolist()


_DOCS_GROUP_ONLY = textwrap.dedent(
    """
    import sys
    for name in ("gdsfactory", "gplugins", "shapely", "gf180mcu", "devsim"):
        sys.modules[name] = None
    from pathlib import Path
    from gf180tcad import comparison_figures
    comparison_figures.write_all(Path(sys.argv[1]))
    print(sorted(p.name for p in Path(sys.argv[1]).iterdir()))
    """
)


def test_figures_draw_without_the_simulators(tmp_path):
    """docgen draws them in the docs build, which has no simulator installed."""
    r = subprocess.run(
        [sys.executable, "-c", _DOCS_GROUP_ONLY, str(tmp_path)],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip
    assert r.returncode == 0, r.stderr[-3000:]
    assert "-dark.svg" in r.stdout and "-light.svg" in r.stdout


# --- the drawn data: each figure's artists (found by their gid) against the committed files ---


def _artist(fig, gid: str, ax=None):
    axes = [ax] if ax is not None else fig.axes
    found = [a for x in axes for a in (*x.get_lines(), *x.patches, *x.collections)
             if a.get_gid() == gid]  # fmt: skip
    assert len(found) == 1, (gid, len(found))
    return found[0]


def _axis(fig, gid: str):
    (ax,) = [a for a in fig.axes if a.get_gid() == gid]
    return ax


def _span(patch) -> tuple[float, float]:
    """The x extent of an axvspan (a Rectangle in data x, axes y)."""
    x0 = float(patch.get_x())
    return min(x0, x0 + patch.get_width()), max(x0, x0 + patch.get_width())


def _csv(*parts) -> dict:
    from gf180tcad import io

    return io.read_csv(REPO_ROOT.joinpath("results", *parts))[0]


def _close(a, b, rel=1e-12):
    import numpy as np

    return np.allclose(np.asarray(a, float), np.asarray(b, float), rtol=rel, atol=0)


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_metric_figure_draws_the_recorded_regions(palette):
    """Every line, marker and span of the metric figure is where the calibration result file
    puts it, and the curve is the committed typical cv.csv."""
    from gf180tcad.calibrate.cv import PLATEAU_OFFSET_V

    fig = cf.cv_metric_figure(palette)
    rec = _result(cf.METRIC_DEVICE)["per_geometry"][cf.METRIC_GEOMETRY]["spice_regions"]
    for name in ("u_fb", "u_t"):
        x = _artist(fig, name).get_xdata()
        assert _close([x[0], x[1]], [rec[name]] * 2), name
    assert _close(_artist(fig, "c_mid").get_ydata(), [rec["c_mid"]] * 2)
    dots = _artist(fig, "crossings")
    assert _close(dots.get_xdata(), [rec["u_dep"], rec["u_inv"]])
    assert _close(dots.get_ydata(), [rec["c_mid"]] * 2)
    cols = _csv("spice", "ngspice", "typical", cf.METRIC_DEVICE, cf.METRIC_GEOMETRY, "cv.csv")
    line = _artist(fig, "typical")
    assert _close(line.get_xdata(), sorted(cols["vg"])) and _close(
        line.get_ydata(), cols["cgg"][cols["vg"].argsort()] * 1e15
    )
    u0, u1 = min(cols["vg"]), max(cols["vg"])
    acc = _span(_artist(fig, "accumulation plateau"))
    inv = _span(_artist(fig, "inversion plateau"))
    assert _close(acc, (u0, rec["u_fb"] - PLATEAU_OFFSET_V))
    assert _close(inv, (rec["u_t"] + PLATEAU_OFFSET_V, u1))


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_meshconv_figure_draws_the_reports(palette):
    """Each line is the report's node counts and largest |change| per level, read here
    directly from report.json; the dotted line is the reports' criterion."""
    fig = cf.meshconv_figure(palette)
    for dim in (1, 2):
        for device in DEVICES:
            path = REPO_ROOT / "results/tcad/meshconv" / f"moscap{dim}d" / device / "report.json"
            report = json.loads(path.read_text("utf-8"))
            levels = [lv for lv in report["levels"] if lv["rel_change"] is not None]
            line = _artist(fig, f"{dim}D {device}")
            assert list(line.get_xdata()) == [lv["node_count"] for lv in levels]
            want = [max(abs(x) for x in lv["rel_change"]) for lv in levels]
            assert _close(line.get_ydata(), want)
            assert _close(_artist(fig, "criterion").get_ydata(), [report["criterion"]] * 2)
    # Every point lies above a labelled decade tick: the axis starts at the decade below the
    # smallest point.
    (ax,) = fig.axes
    lowest = min(y for line in ax.get_lines() for y in line.get_ydata())
    bottom = ax.get_ylim()[0]
    assert bottom <= lowest < bottom * 10
    assert any(math.isclose(t, bottom) for t in ax.get_yticks())


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_centroid_figure_draws_the_allowance(palette):
    """The dots are the largest X_DC of the committed process-data table at the files'
    plateau_v, and each times EPSROX/eps_si, rounded up, is the delta_nm the process file records;
    the windows start at plateau_v and the inversion lines are the table's suprema."""
    import tomllib

    from gf180tcad.tcad import process

    fig = cf.centroid_figure(palette)
    largest = _process_table("X_DC, accumulation plateau edge (polarity·Vg = −2 V) (nm)")
    inv = _process_table("X_DC, inversion supremum (nm)")
    for k, device in enumerate(("nfet_05v0", "pfet_05v0")):
        toml = tomllib.loads((REPO_ROOT / "data/process" / f"{device}.toml").read_text("utf-8"))
        table = toml["centroid_allowance"]
        edge = table["plateau_v"]
        dot = _artist(fig, f"largest {device}")
        y = float(dot.get_ydata()[0])
        assert list(dot.get_xdata()) == [-edge]
        assert round(y, 3) == largest[k]
        epsrox = process.load(device).card_values()["epsrox"]
        assert process.round_up_nm(y * epsrox / process.CONSTANTS.eps_si) == table["delta_nm"]
        assert round(_artist(fig, f"inversion {device}").get_ydata()[0], 3) == inv[k]
        assert _span(_artist(fig, "accumulation window"))[1] == -edge
        assert _span(_artist(fig, "inversion window"))[0] == edge


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_pfet_edge_figure_draws_the_recorded_crossings(palette):
    """Each marker sits at the u_dep of its geometry's committed record (calibration result file
    or validation file), which the page also prints; each solid line is the committed typical
    cv.csv over its value at the grid's first point."""
    fig = cf.pfet_edge_figure(palette)
    wide = [g for g in DEVICES["pfet_05v0"].geometries if g.w_um == 10]
    by_l = {g.l_um: geometry_id(g) for g in wide}
    printed = {by_l[l_um]: u for l_um, u in _page_u_dep().items()}
    for gid, u_dep in printed.items():
        x = _artist(fig, f"u_dep {gid}").get_xdata()[0]
        assert _close([x], [_record("pfet_05v0", gid)["spice_regions"]["u_dep"]])
        assert round(x, 3) == u_dep  # page consistency
        cols = _csv("spice", "ngspice", "typical", "pfet_05v0", gid, "cv.csv")
        order = (-cols["vg"]).argsort()
        c = cols["cgg"][order]
        line = _artist(fig, f"typical {gid}")
        assert _close(line.get_xdata(), -cols["vg"][order]) and _close(line.get_ydata(), c / c[0])


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_instance_plan_draws_the_template_extents(palette):
    """Source and drain are W tall and AS / W long (the template's diffusion length), either
    side of a gate L long."""
    from gf180tcad.spice.netlist import _DIFF

    g = _plan_geometry()
    fig = cf.instance_plan_figure(palette)
    for name in ("source", "drain"):
        line = _artist(fig, name)
        xs, ys = line.get_xdata(), line.get_ydata()
        assert math.isclose(max(xs) - min(xs), float(_DIFF), rel_tol=1e-12)
        assert math.isclose(max(ys) - min(ys), g.w_um, rel_tol=1e-12)
    gate = _artist(fig, "gate").get_xdata()
    assert math.isclose(max(gate) - min(gate), g.l_um, rel_tol=1e-12)
    src, drn = _artist(fig, "source").get_xdata(), _artist(fig, "drain").get_xdata()
    assert math.isclose(max(src), min(gate)) and math.isclose(min(drn), max(gate))


@pytest.mark.parametrize("figure", ["cv_fit_figure", "cv_validation_figure"])
def test_cv_grid_draws_the_committed_curves(figure):
    """Each panel is one geometry of its role: the typical line and the corner band are the
    committed cv.csv files, read here directly; the dashed line is the fitted 1D curve."""
    from gf180tcad.devices import CORNERS

    role = "calibration" if figure == "cv_fit_figure" else "validation"
    fig = getattr(cf, figure)("light")
    for device, dev in DEVICES.items():
        pol = dev.polarity
        for g in (g for g in dev.geometries if g.role == role):
            gid = geometry_id(g)
            ax = _axis(fig, f"{device} {gid}")
            assert ax.get_title() == f"{device.split('_')[0]} W{g.w_um:g}/L{g.l_um:g}"
            curves = {}
            for corner in CORNERS:
                cols = _csv("spice", "ngspice", corner, device, gid, "cv.csv")
                order = (pol * cols["vg"]).argsort()
                curves[corner] = (pol * cols["vg"][order], cols["cgg"][order] * 1e15)
            u, tt = curves["typical"]
            line = _artist(fig, "typical", ax)
            assert _close(line.get_xdata(), u) and _close(line.get_ydata(), tt)
            band = _artist(fig, "corners", ax).get_paths()[0].vertices
            lo = min(c[1].min() for c in curves.values())
            hi = max(c[1].max() for c in curves.values())
            assert math.isclose(band[:, 1].min(), lo) and math.isclose(band[:, 1].max(), hi)
            sim = _artist(fig, "simulated", ax)
            assert len(sim.get_xdata()) == len(u)


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_cgg_split_draws_the_bookkeeping(palette):
    """The intrinsic part is the committed 1D C per area times (L + XL - 2 DLC)(W + XW - 2 DWC)
    from the process file's card values; the total is SPICE x (1 + the recorded error) at every
    plateau bias; the parts add up; and the C-V page prints the drawn parasitic and total at
    u = -5 V."""
    from gf180tcad.tcad import process

    fig = cf.cgg_split_figure(palette)
    u = _artist(fig, "total").get_xdata().tolist()
    total, intr, par = (
        dict(zip(u, _artist(fig, k).get_ydata().tolist(), strict=True))
        for k in ("total", "intrinsic", "parasitic")
    )
    for x in u:
        assert math.isclose(total[x], intr[x] + par[x], rel_tol=1e-9)
    dev = DEVICES[cf.SPLIT_DEVICE]
    (g,) = [g for g in dev.geometries if geometry_id(g) == cf.SPLIT_GEOMETRY]
    cv = process.load(cf.SPLIT_DEVICE).card_values()
    area_um2 = (
        (g.l_um * 1e-6 + cv["xl"] - 2 * cv["dlc"])
        * (g.w_um * 1e-6 + cv["xw"] - 2 * cv["dwc"])
        * 1e12
    )
    cols = _csv("tcad", "moscap1d", cf.SPLIT_DEVICE, "calibrated", "per_area.csv")
    per_area = dict(
        zip((dev.polarity * cols["vg"]).tolist(), cols["c_per_area"].tolist(), strict=True)
    )
    for x in u:
        assert math.isclose(intr[x], per_area[x] * area_um2, rel_tol=1e-9), x
    tt = _typical(cf.SPLIT_DEVICE, cf.SPLIT_GEOMETRY)
    for x, rel in _residual_curve(_record(cf.SPLIT_DEVICE, cf.SPLIT_GEOMETRY)).items():
        assert math.isclose(total[x], tt[x] * (1 + rel), rel_tol=1e-9), x
    page = (REPO_ROOT / "docs/comparison/cv-agreement.md").read_text("utf-8")
    end = min(u)
    assert f"it is {par[end]:.2f} of {total[end]:.2f} fF" in page


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_geometry_markers_are_the_roles(palette):
    fig = cf.geometries_figure(palette)
    for device, dev in DEVICES.items():
        for role in ("calibration", "validation"):
            line = _artist(fig, f"{device} {role}")
            got = sorted(zip(line.get_xdata(), line.get_ydata(), strict=True))
            want = sorted((g.l_um, g.w_um) for g in dev.geometries if g.role == role)
            assert got == want


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_pdk_sweeps_draw_both_trees(palette):
    """Each panel draws the committed idvg_lin.csv of each tree, per body bias, read directly."""
    import numpy as np

    fig = cf.pdk_sweeps_figure(palette)
    gid = cf.PDK_GEOMETRY
    for device in DEVICES:
        ax = _axis(fig, device)
        for tree, name in (("spice", "image"), ("spice-pdk-d658698", "d658698")):
            cols = _csv(tree, "ngspice", "typical", device, gid, "idvg_lin.csv")
            for k, vb in enumerate(dict.fromkeys(cols["vb"].tolist())):
                keep = cols["vb"] == vb
                line = _artist(fig, f"{name} {k}", ax)
                assert _close(line.get_xdata(), np.abs(cols["vg"][keep]))
                assert _close(line.get_ydata(), np.abs(cols["id"][keep]) * 1e6)


def test_start_stack_labels_are_the_process_file():
    """The stack's oxide and body labels give the start values of the nfet process file."""
    import tomllib

    toml = tomllib.loads((REPO_ROOT / "data/process/nfet_05v0.toml").read_text("utf-8"))
    texts = [
        t.get_text().replace("\xa0", " ") for t in cf.start_stack_figure("light").axes[0].texts
    ]
    t_ox = toml["param"]["t_ox_eff_nm"]["value"]
    n_ch = toml["param"]["n_ch_cm3"]["value"]
    assert any(f"{t_ox:g} nm" in t for t in texts), texts
    mant, _exp = f"{n_ch:e}".split("e")
    assert any(f"{float(mant):g} × 10" in t and "acceptors" in t for t in texts), texts


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_process_cell_marks_the_channel_and_the_doping(palette):
    """The arrow points at the body's surface under the gate, and each doped part's label gives
    its type and doping from the cell model; the cell is drawn at the scales of the parts-cell
    figure, so the caption's statement {{ x_fig_parts_cell_scale }} is this figure's."""
    from gf180tcad.explain import figures as ef
    from gf180tcad.explain import model

    c = cf.process_cell_model()
    fig = cf.process_cell_figure(palette)
    (ax,) = fig.axes
    texts = {t.get_gid(): t for t in ax.texts if t.get_gid()}
    arrow = texts["channel"]
    x, y = arrow.xy
    gate = ef.cell_extents(c)["gate"]
    assert gate.x0 < x < gate.x1 and 0 < y < c.xj_um
    assert arrow.get_text() == "channel"
    want = {"source": c.n_sd_cm3, "drain": c.n_sd_cm3, "gate": c.n_gate_cm3, "body": c.n_body_cm3}
    for part, n in want.items():
        text = texts[f"doping {part}"].get_text()
        kind = "p-type" if (part == "body") == (c.polarity == "n") else "n-type"
        assert text.startswith(kind), (part, text)
        assert ef._short(n, "cm⁻³", ef.STYLE["label_digits"]["doping"]) in text, (part, text)
    statement = model.exaggeration(c.scales, c.drawn)
    assert statement == ef.substitutions()["x_fig_parts_cell_scale"]


def literal_digits(source: str, allowed: set[str]) -> list[tuple[int, str]]:
    """(line, text) of each string literal inside a function (f-string parts included) that holds
    a digit once the ``allowed`` names are taken out; docstrings and raise messages are skipped.
    A number in a drawn label must come from the data, not be typed into its text."""
    import ast

    tree = ast.parse(source)
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            skip |= set(ast.walk(node))
        if isinstance(node, ast.FormattedValue) and node.format_spec is not None:
            skip |= set(ast.walk(node.format_spec))  # ".0%", ":g": formats, not numbers
        if isinstance(node, ast.FunctionDef) and node.body and isinstance(node.body[0], ast.Expr):
            skip.add(node.body[0].value)
    out = []
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        for node in ast.walk(fn):
            if (
                node in skip
                or not isinstance(node, ast.Constant)
                or not isinstance(node.value, str)
            ):
                continue
            text = node.value
            for name in sorted(allowed, key=len, reverse=True):
                text = text.replace(name, "")
            if re.search(r"\d", text):
                out.append((node.lineno, node.value))
    return out


def _allowed_names() -> set[str]:
    """Names that hold digits but are identifiers, not numbers: the devices, their geometry ids,
    the older PDK's commit, the text encoding, the compact model's name and the 2D cells'
    dimension (the edge-capacitance legend)."""
    gids = {geometry_id(g) for d in DEVICES.values() for g in d.geometries}
    return set(DEVICES) | gids | {"d658698", "utf-8", "BSIM4", "2D"}


def test_drawn_labels_type_no_numbers():
    found = literal_digits(SRC.read_text(encoding="utf-8"), _allowed_names())
    assert not found, f"numbers typed into strings (derive them from the data): {found}"


def test_positive_control_literal_digits():
    src = (
        "def f(ax, g):\n"
        "    ax.set_title('nfet W10/L10')\n"
        "    ax.set_ylabel(f'C(u = {g} V) at -5 V')\n"
        "    ax.text(0, 0, 'nfet_05v0')\n"
        "    raise ValueError('2 things')\n"
        "    ax.text(0, 0, f'{g:.0%}')\n"
    )
    assert [line for line, _ in literal_digits(src, {"nfet_05v0"})] == [2, 3]


# The figures drawn from no results tree: the two explainer-model drawings (the committed TCAD
# tree through gf180tcad.explain.model), the process-file plot and the two drawn from code.
NO_ROOT = {"process-cell", "start-stack", "centroid", "geometries", "instance-plan"}


@pytest.mark.parametrize("name", sorted(set(FIGURES) - NO_ROOT))
def test_figures_read_the_trees_they_are_given(name, tmp_path):
    """Given empty trees, every figure that reads results fails: none falls back to the
    committed trees behind docgen.generate's back."""
    empty = cf.Roots(spice=tmp_path, older_pdk=tmp_path, tcad=tmp_path)
    with pytest.raises(OSError):
        cf.FIGURES[name]("light", empty)


def test_default_roots_are_the_committed_trees():
    assert cf.DEFAULT_ROOTS == cf.Roots(
        REPO_ROOT / "results/spice", REPO_ROOT / "results/spice-pdk-d658698",
        REPO_ROOT / "results/tcad",
    )  # fmt: skip


@pytest.mark.parametrize("figure", ["cv_fit_figure", "cv_validation_figure"])
def test_cv_grid_ticks_are_text_size(figure):
    """The six panels' tick text is the page's text size (9 px or more at 400 px wide)."""
    from gf180tcad.explain import figures as ef

    fig = getattr(cf, figure)("light")
    for ax in fig.axes:
        for label in (*ax.get_xticklabels(), *ax.get_yticklabels()):
            assert label.get_fontsize() == ef.STYLE["text_pt"]


# --- the drawn data, part 2: the simulated curves, against the committed result files --------


def _residual_curve(rec: dict) -> dict[float, float]:
    """u -> (TCAD - SPICE) / SPICE at each plateau bias of a calibration or validation record."""
    r = rec["residuals"]
    out = {}
    for side in ("acc", "inv"):
        out.update(zip(r[f"plateau_{side}_u"], r[f"plateau_{side}_rel"], strict=True))
    return out


def _record(device: str, gid: str) -> dict:
    """The committed per-geometry record: the calibration result file for a calibration geometry,
    the validation file's 1D entry for a held-out one."""
    per = _result(device)["per_geometry"]
    if gid in per:
        return per[gid]
    path = REPO_ROOT / "results/tcad/validation" / f"{device}.json"
    return json.loads(path.read_text("utf-8"))["one_d"][gid]


def _typical(device: str, gid: str) -> dict[float, float]:
    """u -> SPICE typical Cgg (fF), read from the committed cv.csv."""
    pol = DEVICES[device].polarity
    cols = _csv("spice", "ngspice", "typical", device, gid, "cv.csv")
    return dict(zip((pol * cols["vg"]).tolist(), (cols["cgg"] * 1e15).tolist(), strict=True))


@pytest.mark.parametrize("figure", ["cv_fit_figure", "cv_validation_figure"])
def test_cv_grid_simulated_line_is_the_recorded_fit(figure):
    """At every plateau bias the dashed line is SPICE x (1 + the recorded relative error), and
    its two mid-capacitance crossings are the recorded TCAD crossings."""
    from gf180tcad.calibrate.cv import crossings

    role = "calibration" if figure == "cv_fit_figure" else "validation"
    fig = getattr(cf, figure)("light")
    for device, dev in DEVICES.items():
        for g in (g for g in dev.geometries if g.role == role):
            gid = geometry_id(g)
            rec = _record(device, gid)
            sim = _artist(fig, "simulated", _axis(fig, f"{device} {gid}"))
            drawn = dict(zip(sim.get_xdata().tolist(), sim.get_ydata().tolist(), strict=True))
            tt = _typical(device, gid)
            for u, rel in _residual_curve(rec).items():
                assert math.isclose(drawn[u], tt[u] * (1 + rel), rel_tol=1e-9), (device, gid, u)
            got = crossings(tuple(drawn), tuple(drawn.values()))
            want = (rec["tcad_crossings"]["u_dep"], rec["tcad_crossings"]["u_inv"])
            assert _close(got, want, rel=1e-9), (device, gid)


def test_pfet_edge_simulated_lines_are_the_recorded_fit():
    """Each dashed line is the fitted curve over its value at u = -5 V: 1 there, and at every
    other accumulation-plateau bias the ratio of SPICE x (1 + recorded error) at the two biases;
    its crossing of its own mid level is the recorded TCAD u_dep."""
    from gf180tcad.calibrate.cv import crossings

    fig = cf.pfet_edge_figure("light")
    for g in (g for g in DEVICES["pfet_05v0"].geometries if g.w_um == 10):
        gid = geometry_id(g)
        rec = _record("pfet_05v0", gid)
        line = _artist(fig, f"simulated {gid}")
        drawn = dict(zip(line.get_xdata().tolist(), line.get_ydata().tolist(), strict=True))
        tt, res = _typical("pfet_05v0", gid), _residual_curve(rec)
        u0 = min(drawn)
        assert drawn[u0] == 1.0
        ref = tt[u0] * (1 + res[u0])
        for u, rel in res.items():
            assert math.isclose(drawn[u], tt[u] * (1 + rel) / ref, rel_tol=1e-9), (gid, u)
        u_dep, _ = crossings(tuple(drawn), tuple(drawn.values()))
        assert math.isclose(u_dep, rec["tcad_crossings"]["u_dep"], rel_tol=1e-9), gid


def _process_table(row: str) -> tuple[float, float]:
    """The nfet and pfet values of one row of the charge-centroid table on the committed
    process-data page."""
    page = (REPO_ROOT / "docs/comparison/process-data.md").read_text("utf-8")
    (line,) = [ln for ln in page.splitlines() if ln.startswith(f"| {row} |")]
    cells = [c.strip().strip("*") for c in line.strip("|").split("|")]
    return float(cells[1]), float(cells[2])


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_centroid_curves_are_the_card_formula(palette):
    """Each solid line is X_DC of eqs. 7.3.2-7.3.3 on the committed card values at every drawn u,
    and it passes through the page table's values at the plateau edge and at u = -5 V."""
    from gf180tcad.tcad import process

    fig = cf.centroid_figure(palette)
    edge = _process_table("X_DC, accumulation plateau edge (polarity·Vg = −2 V) (nm)")
    end = _process_table("X_DC, accumulation end (polarity·Vg = −5 V) (nm)")
    for k, device in enumerate(("nfet_05v0", "pfet_05v0")):
        cv = process.load(device).card_values()
        pol = cv["type"]
        line = _artist(fig, f"accumulation {device}")
        u, x = line.get_xdata(), line.get_ydata()
        want = [process.ctm_x_dc_acc_m(pol * v, cv) * 1e9 for v in u]
        assert _close(x, want, rel=1e-12), device
        drawn = dict(zip(u.tolist(), x.tolist(), strict=True))
        assert round(drawn[-2.0], 3) == edge[k] and round(drawn[-5.0], 3) == end[k], device


# --- the edge capacitance (issues #77, #74) -------------------------------------------------------


def _cells(device):
    """``{L: (u, C per width)}`` of the committed calibrated 2D cells at W = 10 um, read
    directly from their cv.csv."""
    import numpy as np

    pol = DEVICES[device].polarity
    out = {}
    for path in sorted(
        (REPO_ROOT / "results/tcad/moscap2d" / device / "calibrated").glob("w10p0_*/cv.csv")
    ):
        cols = _csv(*path.relative_to(REPO_ROOT / "results").parts)
        u = pol * cols["vg"]
        order = np.argsort(u)
        out[float(path.parent.name.split("_l")[1].replace("p", "."))] = (
            u[order],
            cols["cgg_total"][order] / 10.0,
        )
    return out


@pytest.mark.parametrize("device", ["nfet_05v0", "pfet_05v0"])
def test_edge_split_is_the_least_squares_line_through_the_cells(device):
    """The 2D line at every bias is the least-squares line through the cells' own cv.csv (an
    independent solve), and the lengths are every W = 10 um cell."""
    import numpy as np

    cells = _cells(device)
    s = cf.edge_split(device)
    assert s["lengths"].tolist() == sorted(cells)
    ls = np.array(sorted(cells))
    a = np.vstack([np.ones_like(ls), ls]).T
    for i, u in enumerate(s["u"]):
        y = np.array([np.interp(u, *cells[length]) for length in ls])
        (edge, area), *_ = np.linalg.lstsq(a, y, rcond=None)
        assert math.isclose(s["two_d"]["edge"][i], edge, abs_tol=1e-9), u
        assert math.isclose(s["two_d"]["area"][i], area, abs_tol=1e-9), u
    # the 2D cells lie on their line to 1e-3 fF/um at every bias
    assert float(np.max(s["two_d"]["rms"])) < 1e-3


@pytest.mark.parametrize("device", ["nfet_05v0", "pfet_05v0"])
def test_edge_split_extrinsic_is_linear_in_l(device):
    """The BSIM4 extrinsic terms are exactly a line in L (overlap and fringe per width, plus CGBO
    times L), so their residual is round-off."""
    import numpy as np

    s = cf.edge_split(device)
    assert float(np.max(s["extrinsic"]["rms"])) < 1e-12


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_edge_figure_draws_the_split(palette):
    fig = cf.edge_figure(palette)
    for device in ("nfet_05v0", "pfet_05v0"):
        s = cf.edge_split(device)
        for key in ("edge", "area"):
            for line in ("spice", "two_d"):
                art = _artist(fig, f"{device} {line} {key}")
                assert art.get_xdata().tolist() == s["u"].tolist()
                assert art.get_ydata().tolist() == s[line][key].tolist()
        art = _artist(fig, f"{device} extrinsic edge")
        assert art.get_ydata().tolist() == s["extrinsic"]["edge"].tolist()


def _edge_numbers() -> dict:
    """The numbers the C-V page prints from the edge split."""
    import numpy as np

    from gf180tcad.tcad import process

    out = {"rows": [], "area": [], "gap": []}
    for device in ("nfet_05v0", "pfet_05v0"):
        s = cf.edge_split(device)
        for side, u in (("accumulation", -5.0), ("inversion", 5.0)):
            i = int(np.flatnonzero(s["u"] == u)[0])
            e = {k: float(s[k]["edge"][i]) for k in ("spice", "two_d", "extrinsic")}
            a = {k: float(s[k]["area"][i]) for k in ("spice", "two_d")}
            out["rows"].append((device, side, u, e, a))
            out["area"].append(abs(a["two_d"] / a["spice"] - 1) * 100)
            out["gap"].append(e["spice"] - e["two_d"])
            if device == "nfet_05v0":
                dlc_um = process.load(device).card_values()["dlc"] * 1e6
                out.setdefault("check", []).append(
                    abs(e["extrinsic"] - 2 * dlc_um * a["spice"] - e["spice"])
                )
                if u == 5.0:
                    out["nfet_total"] = (
                        10 * (e["spice"] + a["spice"] * 0.6),
                        10 * (e["two_d"] + a["two_d"] * 0.6),
                    )
    return out


def test_cv_page_prints_the_edge_split():
    """The edge-capacitance section's table and sentences are the split's values."""
    n = _edge_numbers()
    page = (REPO_ROOT / "docs/comparison/cv-agreement.md").read_text("utf-8")
    for device, side, u, e, a in n["rows"]:
        row = (
            f"| {device.split('_')[0]} | {side} | {u:+g} | {e['spice']:.3f} | {e['two_d']:.3f} | "
            f"{e['extrinsic']:.3f} | {a['spice']:.3f} | {a['two_d']:.3f} |"
        ).replace("-", "−")
        assert row in page, row
    assert f"agrees within {max(n['area']):.1f} %" in page
    assert f"{min(n['gap']):.2f} to {max(n['gap']):.2f} fF/µm below SPICE" in page
    spice, two_d = n["nfet_total"]
    assert f"give {spice:.2f} fF (SPICE) and {two_d:.2f} fF (2D)" in page
    assert f"to within {max(n['check']):.4f} fF/µm" in page
    assert max(n["check"]) < 1e-3
