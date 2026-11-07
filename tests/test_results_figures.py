# SPDX-License-Identifier: Apache-2.0
"""The figures of the generated results pages (gf180tcad.results_figures): deterministic light and
dark twins whose every drawn line, band and marker is the committed data, read here directly from
the files (never from a page), and embedded by docgen as named, cited {figure} pairs."""

import json
import os
import subprocess
import sys
import textwrap

import pytest
from optional import importorskip

importorskip("matplotlib", reason="needs the docs dependency group")

import numpy as np
from test_comparison_figures import literal_digits
from test_explained import numeric_literals

from gf180tcad import docgen, io
from gf180tcad import results_figures as rf
from gf180tcad.devices import CORNERS, DEVICES, geometry_id
from gf180tcad.sandbox import REPO_ROOT

SRC = REPO_ROOT / "src" / "gf180tcad" / "results_figures.py"
RESULTS = REPO_ROOT / "results"
GEOMETRIES = [(d, geometry_id(g)) for d, dev in DEVICES.items() for g in dev.geometries]
# The SPICE grids: A to mA, F to fF, a fraction to %.
MA, FF, PCT = 1e3, 1e15, 1e2


def _csv(*parts) -> dict:
    return io.read_csv(RESULTS.joinpath(*parts))[0]


def _json(*parts) -> dict:
    return json.loads(RESULTS.joinpath(*parts).read_text("utf-8"))


def _artist(fig, gid: str, ax=None):
    axes = [ax] if ax is not None else fig.axes
    found = [a for x in axes for a in (*x.get_lines(), *x.collections) if a.get_gid() == gid]
    assert len(found) == 1, (gid, len(found))
    return found[0]


def _axis(fig, gid: str):
    (ax,) = [a for a in fig.axes if a.get_gid() == gid]
    return ax


def line_is(line, x, y, rel=1e-12) -> bool:
    """Is the drawn ``line`` exactly the curve (x, y)?"""
    xs, ys = np.asarray(line.get_xdata(), float), np.asarray(line.get_ydata(), float)
    x, y = np.asarray(x, float), np.asarray(y, float)
    return (
        xs.shape == x.shape
        and np.allclose(xs, x, rtol=rel, atol=0)
        and np.allclose(ys, y, rtol=rel, atol=0)
    )


def band_is(coll, x, lo, hi, rel=1e-12) -> bool:
    """Does the drawn band ``coll`` (a fill_between) run along (x, lo) and back along (x, hi)?"""
    v = coll.get_paths()[0].vertices
    n = len(x)
    # fill_between: a start point, the n lower points, an end point, the n upper points reversed.
    lower, upper = v[1 : n + 1], v[n + 2 : 2 * n + 2][::-1]
    return (
        len(v) >= 2 * n + 2
        and np.allclose(lower[:, 0], x, rtol=rel, atol=0)
        and np.allclose(lower[:, 1], lo, rtol=rel, atol=0)
        and np.allclose(upper[:, 0], x, rtol=rel, atol=0)
        and np.allclose(upper[:, 1], hi, rtol=rel, atol=0)
    )


def _spice(device, gid, sweep, engine="ngspice", corner="typical"):
    return _csv("spice", engine, corner, device, gid, f"{sweep}.csv")


def _id_series(cols, device):
    """[(x, |Id|)] at vb = 0: one entry for Id-Vg, one per |Vgs| (ascending) for Id-Vd."""
    pol = DEVICES[device].polarity
    m0 = cols["vb"] == 0
    if np.all(cols["vd"][m0] == cols["vd"][m0][0]):  # Id-Vg: one drain voltage
        return [(pol * cols["vg"][m0], np.abs(cols["id"][m0]))]
    out = []
    for v in sorted(set(np.abs(cols["vg"][m0]).tolist())):
        m = m0 & (np.abs(cols["vg"]) == v)
        out.append((pol * cols["vd"][m], np.abs(cols["id"][m])))
    return out


def _check_sweep(ax, device, gid, sweep, scale, floor=None, xyce=True):
    """Each series' typical line, Xyce line and corner band on ``ax`` against the CSVs."""

    def y(a):
        return a * scale if floor is None else np.maximum(a * scale, floor)

    per = [_id_series(_spice(device, gid, sweep, corner=c), device) for c in CORNERS]
    xs = _id_series(_spice(device, gid, sweep, "xyce"), device) if xyce else None
    for k, (x, tt) in enumerate(per[CORNERS.index("typical")]):
        assert line_is(_artist(None, f"typical {k}", ax), x, y(tt)), (device, gid, sweep, k)
        stack = [y(p[k][1]) for p in per]
        band = _artist(None, f"corners {k}", ax)
        assert band_is(band, x, np.min(stack, axis=0), np.max(stack, axis=0)), (sweep, k)
        if xyce:
            assert line_is(_artist(None, f"xyce {k}", ax), x, y(xs[k][1])), (sweep, k)


@pytest.mark.parametrize(("device", "gid"), GEOMETRIES)
@pytest.mark.parametrize("sweep", ["idvg_lin", "idvg_sat"])
def test_idvg_figure_draws_the_csvs(device, gid, sweep):
    fig = rf.idvg_figure(device, gid, sweep, "light")
    lin, log = fig.axes[:2]
    _check_sweep(lin, device, gid, sweep, MA)
    _check_sweep(log, device, gid, sweep, 1, floor=rf.STYLE["id_floor_a"])
    vd = set(np.abs(_spice(device, gid, sweep)["vd"]).tolist())
    assert fig._suptitle.get_text().endswith(f"|Vds| = {vd.pop():g} V")


@pytest.mark.parametrize(("device", "gid"), GEOMETRIES)
def test_idvd_figure_draws_the_csvs(device, gid):
    fig = rf.idvd_figure(device, gid, "light")
    _check_sweep(fig.axes[0], device, gid, "idvd", MA)


@pytest.mark.parametrize(("device", "gid"), GEOMETRIES)
def test_cv_figure_draws_the_csvs(device, gid):
    pol = DEVICES[device].polarity
    fig = rf.cv_figure(device, gid, "light")
    ax = fig.axes[0]
    curves = []
    for c in CORNERS:
        cols = _spice(device, gid, "cv", corner=c)
        order = np.argsort(pol * cols["vg"], kind="stable")
        curves.append(((pol * cols["vg"])[order], cols["cgg"][order] * FF))
    x, tt = curves[CORNERS.index("typical")]
    assert line_is(_artist(fig, "typical 0"), x, tt)
    ys = [c[1] for c in curves]
    assert band_is(_artist(fig, "corners 0"), x, np.min(ys, axis=0), np.max(ys, axis=0))
    assert not [a for a in ax.get_lines() if (a.get_gid() or "").startswith("xyce")]


def _engine_diff(device, gid, sweep):
    """The definition of the summary page's equation, on the two CSVs read here."""
    a = np.abs(_spice(device, gid, sweep)["id"])
    b = np.abs(_spice(device, gid, sweep, "xyce")["id"])
    den = np.maximum(a, b)
    keep = den > 1e-12
    return float(np.max(np.abs(a - b)[keep] / den[keep])) if keep.any() else 0.0


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_engine_diff_figure_draws_every_geometry(palette):
    from gf180tcad.spice.xyce import ENGINE_DIFF_THRESHOLD

    fig = rf.engine_diff_figure(palette)
    for device, dev in DEVICES.items():
        ax = _axis(fig, device)
        for sweep in rf.DIFF_SWEEPS:
            want = [_engine_diff(device, geometry_id(g), sweep) * PCT for g in dev.geometries]
            want = np.maximum(want, rf.STYLE["diff_floor_pct"])
            line = _artist(fig, f"{device} {sweep}", ax)
            assert line_is(line, np.arange(len(dev.geometries)), want, rel=1e-9), (device, sweep)
        thr = _artist(fig, "threshold", ax).get_ydata()
        assert np.allclose(thr, ENGINE_DIFF_THRESHOLD * PCT)


def _cgg(device, gid, params):
    """[u, intrinsic, parasitic, total] of the committed 1D C per area, through the card values
    of the process file, by MoscapCV.area_scaled (the calibration's own function)."""
    from gf180tcad.tcad import moscap1d, process

    g = rf.geometry(device, gid)
    m = moscap1d.read(RESULTS / "tcad" / "moscap1d" / device / params)
    vg, *parts = m.area_scaled(g, process.load(device))
    u = DEVICES[device].polarity * np.asarray(vg)
    order = np.argsort(u, kind="stable")
    return [u[order], *(np.asarray(p)[order] for p in parts)]


def _record(device, gid):
    cal = _json("tcad", "calibration", f"{device}.result.json")["per_geometry"]
    return cal[gid] if gid in cal else _json("tcad", "validation", f"{device}.json")["one_d"][gid]


@pytest.mark.parametrize(("device", "gid"), GEOMETRIES)
def test_cgg_figure_draws_the_committed_tcad_and_record(device, gid):
    fig = rf.cgg_figure(device, gid, "light")
    top, bottom = fig.axes[:2]
    for params in ("calibrated", "start"):
        u, *_parts, total = _cgg(device, gid, params)
        assert line_is(_artist(fig, f"tcad {params}"), u, total, rel=1e-9), params
    pol = DEVICES[device].polarity
    cols = _spice(device, gid, "cv")
    order = np.argsort(pol * cols["vg"], kind="stable")
    assert line_is(
        _artist(fig, "typical 0", top), (pol * cols["vg"])[order], cols["cgg"][order] * FF
    )
    rec = _record(device, gid)
    for side in ("acc", "inv"):
        pu = rec["residuals"][f"plateau_{side}_u"]
        rel = np.asarray(rec["residuals"][f"plateau_{side}_rel"]) * PCT
        assert line_is(_artist(fig, f"plateau {side}", bottom), pu, rel)
        tol = rec["verdicts"][f"plateau_{side}"]["tolerance"] * PCT
        for edge, sign in (("upper", 1), ("lower", -1)):
            assert line_is(_artist(fig, f"tolerance {side} {edge}", bottom),
                           [min(pu), max(pu)], [sign * tol] * 2)  # fmt: skip


@pytest.mark.parametrize(("device", "gid"), GEOMETRIES)
def test_split_figure_draws_the_bookkeeping(device, gid):
    fig = rf.split_figure(device, gid, "light")
    u, intrinsic, parasitic, total = _cgg(device, gid, "calibrated")
    for name, y in (("intrinsic", intrinsic), ("parasitic", parasitic), ("total", total)):
        assert line_is(_artist(fig, name), u, y, rel=1e-9), name
    pol = DEVICES[device].polarity
    cols = _spice(device, gid, "cv")
    o = np.argsort(pol * cols["vg"], kind="stable")
    assert line_is(_artist(fig, "typical"), (pol * cols["vg"])[o], cols["cgg"][o] * FF)
    assert np.allclose(intrinsic + parasitic, total, rtol=1e-12)


TWO_D = sorted(
    {(p.parts[-3], p.parts[-1]) for p in (RESULTS / "tcad" / "moscap2d").glob("*/*/*")}
)  # (device, gid) with any committed 2D cell


@pytest.mark.parametrize(("device", "gid"), TWO_D)
def test_two_d_figure_draws_each_cell_and_its_stack(device, gid):
    pol = DEVICES[device].polarity
    fig = rf.two_d_figure(device, gid, "light")
    drawn = [ax.get_gid() for ax in fig.axes if ax.get_gid()]
    committed = [p for p in ("calibrated", "start")
                 if (RESULTS / "tcad/moscap2d" / device / p / gid / "cv.csv").is_file()]  # fmt: skip
    assert drawn == committed
    for params in committed:
        ax = _axis(fig, params)
        cell = _csv("tcad", "moscap2d", device, params, gid, "cv.csv")
        o = np.argsort(pol * cell["vg"], kind="stable")
        assert line_is(_artist(fig, "cell", ax), (pol * cell["vg"])[o], cell["c_per_area"][o])
        stack = _csv("tcad", "moscap1d", device, params, "per_area.csv")
        o = np.argsort(pol * stack["vg"], kind="stable")
        assert line_is(_artist(fig, "stack", ax), (pol * stack["vg"])[o], stack["c_per_area"][o])


def test_two_d_figure_refuses_a_geometry_without_a_cell():
    missing = [(d, g) for d, g in GEOMETRIES if (d, g) not in TWO_D]
    assert missing
    with pytest.raises(ValueError, match="no committed 2D cell"):
        rf.two_d_figure(*missing[0], "light")


@pytest.mark.parametrize("device", DEVICES)
@pytest.mark.parametrize("structure", ["moscap1d", "moscap2d"])
def test_meshconv_figure_draws_the_report(device, structure):
    pol = DEVICES[device].polarity
    report = _json("tcad", "meshconv", structure, device, "report.json")
    fig = rf.meshconv_figure(device, structure, "light")
    u = pol * np.asarray(report["vg"])
    o = np.argsort(u, kind="stable")
    for i, lv in enumerate(report["levels"]):
        assert line_is(_artist(fig, f"level {i}"), u[o], np.asarray(lv["c_per_area_ff_um2"])[o])
        if lv["rel_change"] is None:
            assert not [a for a in fig.axes[1].get_lines() if a.get_gid() == f"change {i}"]
        else:
            r = np.maximum(np.abs(np.asarray(lv["rel_change"])[o]), rf.STYLE["change_floor"])
            assert line_is(_artist(fig, f"change {i}"), u[o], r)
    assert np.allclose(_artist(fig, "criterion").get_ydata(), report["criterion"])


@pytest.mark.parametrize("device", DEVICES)
def test_stack_figure_labels_are_the_committed_stack(device):
    """The oxide thickness and the body doping drawn are the calibrated 1D metadata's."""
    meta = _json("tcad", "moscap1d", device, "calibrated", "per_area.meta.json")["stack"]
    texts = " ".join(t.get_text().replace("\xa0", " ") for t in
                     rf.stack_figure(device, "light").axes[0].texts)  # fmt: skip
    assert f"{meta['t_ox_nm']:.4g} nm" in texts, texts
    mant, _exp = f"{meta['n_ch_cm3']:e}".split("e")
    assert f"{float(mant):.3g} × 10" in texts, texts


def test_positive_control_a_doubled_curve_fails():
    """A ×2 mutation of a drawn curve or band no longer matches the files."""
    device, gid = GEOMETRIES[0]
    fig = rf.cv_figure(device, gid, "light")
    line = _artist(fig, "typical 0")
    x, y = line.get_xdata(), line.get_ydata()
    assert line_is(line, x, y)
    line.set_ydata(2 * np.asarray(y))
    assert not line_is(line, x, y)
    band = _artist(fig, "corners 0")
    v = band.get_paths()[0].vertices
    n = len(x)
    lo, hi = v[1 : n + 1, 1].copy(), v[n + 2 : 2 * n + 2, 1][::-1].copy()
    assert band_is(band, x, lo, hi)
    assert not band_is(band, x, 2 * lo, hi) and not band_is(band, x, lo, 2 * hi)


# --- determinism, the code rules and the pages ----------------------------------------------

# One of each kind of figure: (stem, function, args).
KINDS = {
    "idvg": ("idvg_figure", ("nfet_05v0", "w10p0_l0p60", "idvg_lin")),
    "idvd": ("idvd_figure", ("pfet_05v0", "w10p0_l0p50")),
    "cv": ("cv_figure", ("nfet_05v0", "w10p0_l0p60")),
    "engine": ("engine_diff_figure", ()),
    "cgg": ("cgg_figure", ("nfet_05v0", "w10p0_l0p70")),
    "split": ("split_figure", ("pfet_05v0", "w10p0_l2p00")),
    "two_d": ("two_d_figure", ("nfet_05v0", "w10p0_l0p60")),
    "meshconv": ("meshconv_figure", ("pfet_05v0", "moscap2d")),
    "stack": ("stack_figure", ("nfet_05v0",)),
}

_RENDER = textwrap.dedent(
    """
    import json, sys
    from gf180tcad import results_figures as rf
    args = json.loads(sys.argv[2])
    sys.stdout.buffer.write(rf.svg(getattr(rf, sys.argv[1]), *args, palette=sys.argv[3]))
    """
)


@pytest.mark.parametrize("kind", sorted(KINDS))
@pytest.mark.parametrize("palette", ["light", "dark"])
def test_svg_deterministic(kind, palette):
    """Two fresh processes with different hash seeds give the same bytes, with text kept as
    text, no date and no host path."""
    name, args = KINDS[kind]
    runs = []
    for seed in ("1", "2"):
        r = subprocess.run(
            [sys.executable, "-c", _RENDER, name, json.dumps(args), palette],
            env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, check=True,
            timeout=300,
        )  # fmt: skip
        runs.append(r.stdout)
    a, b = runs
    assert a.startswith(b"<?xml") and b"<text" in a and a == b
    assert b"<dc:date>" not in a and str(REPO_ROOT).encode() not in a


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_twins_differ(kind):
    name, args = KINDS[kind]
    draw = getattr(rf, name)
    assert rf.svg(draw, *args, palette="light") != rf.svg(draw, *args, palette="dark")


@pytest.mark.parametrize("kind", sorted(set(KINDS) - {"stack"}))
def test_figures_read_the_trees_they_are_given(kind, tmp_path):
    """Given empty trees, every figure that reads results fails: none falls back to the
    committed trees behind docgen.generate's back. The stack reads the committed tree through
    the explainer model, as the explainer's stack drawings do."""
    name, args = KINDS[kind]
    # a tree with no 2D cell is refused by name rather than read
    expected = ValueError if kind == "two_d" else OSError
    with pytest.raises(expected):
        getattr(rf, name)(*args, "light", rf.Roots(spice=tmp_path, tcad=tmp_path))


def test_default_roots_are_the_committed_trees():
    assert rf.DEFAULT_ROOTS == rf.Roots(RESULTS / "spice", RESULTS / "tcad")


def test_figure_code_has_no_numeric_literals():
    found = numeric_literals(SRC.read_text(encoding="utf-8"))
    assert not found, f"number literals outside STYLE and UNITS: {found}"


def test_drawn_labels_type_no_numbers():
    gids = {geometry_id(g) for d in DEVICES.values() for g in d.geometries}
    # identifiers: the devices, geometry ids, folder names and the report's key of the C per area
    allowed = set(DEVICES) | gids | {"utf-8", "moscap1d", "moscap2d", "c_per_area_ff_um2"}
    found = literal_digits(SRC.read_text(encoding="utf-8"), allowed)
    assert not found, f"numbers typed into strings (derive them from the data): {found}"


@pytest.fixture(scope="module")
def generated(generated_pages):
    """The session's generated pages (tests/conftest.py)."""
    return generated_pages


def test_every_generated_svg_is_a_cited_named_twin(generated):
    """Every SVG docgen writes next to a results or TCAD page is one of a light/dark pair that
    the page embeds as adjacent {figure}s with one caption, the light one named and cited."""
    import re

    for tree in ("results", "tcad"):
        for page in sorted((generated / tree).rglob("*.md")):
            if page.name == docgen.CORNER_FRAGMENT:
                continue
            text = page.read_text("utf-8")
            assert "![" not in text, page
            blocks = re.findall(r"```\{figure\} (\S+)\n(.*?)\n```", text, flags=re.DOTALL)
            assert len(blocks) % 2 == 0, page
            for (light, lbody), (dark, dbody) in zip(blocks[::2], blocks[1::2], strict=True):
                assert light.endswith("-light.svg") and dark == light.replace("-light", "-dark")
                assert (page.parent / light).is_file() and (page.parent / dark).is_file()
                (name,) = re.findall(r"^:name: (\S+)$", lbody, flags=re.MULTILINE)
                assert ":name:" not in dbody
                assert lbody.split("\n\n", 1)[1] == dbody.split("\n\n", 1)[1]  # one caption
                assert f"{{numref}}`{name}`" in text, (page, name)
        drawn = {p.name for p in (generated / tree).rglob("*.svg")}
        embedded = {
            m for p in (generated / tree).rglob("*.md")
            for m in re.findall(r"```\{figure\} (\S+)", p.read_text("utf-8"))
        }  # fmt: skip
        assert drawn == embedded, sorted(drawn ^ embedded)
