# SPDX-License-Identifier: Apache-2.0
"""Every figure of the generated results pages (``docs/_generated/``), in a light and a dark twin.

The :term:`SPICE` pages (``results/``) draw the four sweeps of each geometry and the ngspice-against-Xyce
difference of every geometry; the TCAD pages (``tcad/``) draw the 1D C-V of each geometry against
SPICE, its intrinsic and parasitic parts, the committed 2D cells and the mesh-convergence studies.
Each figure is drawn from committed files only: the SPICE reference (``results/spice``) and the
TCAD results (``results/tcad``), through the readers the explainer figures use
(:mod:`gf180tcad.explain.data`). It uses the colours, text size and deterministic SVG settings of
the explainer figures (:mod:`gf180tcad.explain.figures`). :mod:`gf180tcad.docgen` writes each as
``<name>-light.svg`` and ``<name>-dark.svg`` next to its page, and the page embeds both; the
theme shows one.

Each ``*_figure`` function returns the matplotlib figure, its artists named by ``gid``, so the
tests compare every drawn line, band and marker with the committed files; :func:`svg` saves one.
No number is typed below except in :data:`STYLE` (sizes, widths, axis floors) and :data:`UNITS`
(unit conversions), so a figure's data and its labels' numbers come only from the files (tested).
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Callable
from typing import NamedTuple

import matplotlib
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from gf180tcad import io
from gf180tcad.devices import CORNERS, DEVICES, Geometry, geometry_id
from gf180tcad.explain import data
from gf180tcad.explain import figures as ef
from gf180tcad.reference import engine_sweeps
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.spice.xyce import ENGINE_DIFF_THRESHOLD, engine_diff

STYLE = {
    # One panel, or two stacked: the explainer figures' width, so the text keeps its size at
    # 400 px (12 pt across 6.4 in).
    "one_in": (6.4, 4.8),
    "two_in": (6.4, 8.4),
    "line_width": 2.0,
    # The corner band of a family of curves (Id-Vd), in its curve's colour.
    "family_alpha": 0.3,
    # The lower edge of the log-scale drain current panels (A).
    "id_floor_a": 1e-15,
    # The lower edge of the log-scale mesh change panel, below the smallest drawn change.
    "change_floor": 1e-12,
    # The lower edge of the engine difference panels (%): a difference of 0 is drawn there.
    "diff_floor_pct": 1e-6,
    "marker_pt": 8.0,
    "engine_markers": ("o", "s", "^", "v"),
    # Legends below the plot, this many entries per row.
    "legend_cols": 2,
    # The geometry labels of the engine difference panels stand upright.
    "tick_deg": 90,
}

# Unit conversions: A to mA, a fraction to %.
UNITS = {"ma_per_a": 1e3, "pct_per_one": 1e2}

# The committed SPICE reference and TCAD results.
SPICE_ROOT = REPO_ROOT / "results" / "spice"
TCAD_ROOT = REPO_ROOT / "results" / "tcad"


class Roots(NamedTuple):
    """The results trees the figures read: the committed ones unless
    :func:`gf180tcad.docgen.generate` is given others."""

    # Spelled pathlib.Path: the docs link that name (docs/_ext/api_links.py), not a bare Path.
    spice: pathlib.Path = SPICE_ROOT
    tcad: pathlib.Path = TCAD_ROOT


#: The committed trees: the roots every figure reads unless it is given others.
DEFAULT_ROOTS = Roots()

#: The corner of the SPICE reference that both engines run and the TCAD is compared with.
TYPICAL = "typical"
#: The sweeps whose ngspice-against-Xyce difference the summary page draws and tabulates.
DIFF_SWEEPS = ("idvg_lin", "idvg_sat", "idvd", "ioff")
#: The x axis of every TCAD C-V plot.
U_LABEL = "u = polarity × Vg (V)"
#: The 2D cells a geometry can have, in page order.
TWO_D_PARAMS = ("calibrated", "start")


def svg(draw: Callable, *args, palette: str, roots: Roots = DEFAULT_ROOTS) -> bytes:
    """The SVG bytes of ``draw(*args, palette, roots)``, saved inside the palette's rc context."""
    with matplotlib.rc_context(ef._rc(palette)):
        return ef._svg(draw(*args, palette, roots))


def _figure(size: tuple[float, float]) -> Figure:
    fig = Figure(figsize=size, layout="constrained")
    FigureCanvasAgg(fig)
    return fig


def _legend(fig: Figure, handles: list) -> None:
    fig.legend(handles=handles, loc="outside lower center", ncols=STYLE["legend_cols"],
               frameon=False)  # fmt: skip


def geometry(device: str, gid: str) -> Geometry:
    """The geometry ``gid`` of ``device``; KeyError if the device has none of that id."""
    for g in DEVICES[device].geometries:
        if geometry_id(g) == gid:
            return g
    raise KeyError(f"{device} has no geometry {gid}")


def geometry_label(g: Geometry) -> str:
    """``W10/L0.6``: a geometry as the figures label it."""
    return f"W{g.w_um:g}/L{g.l_um:g}"


# --- the SPICE reference ------------------------------------------------------------------------


def has_sweep(engine: str, sweep: str) -> bool:
    """Does ``engine`` run ``sweep`` at all (Xyce has no cv)? Absent by design, not missing."""
    return sweep in engine_sweeps(engine)


def series(cols: dict, sweep: str, pol: int) -> list[tuple[float | None, np.ndarray, np.ndarray]]:
    """Polarity-stripped ``(|Vgs| or None, x, y)`` of one sweep's columns, at a body bias of 0:
    |Id| (A) against |Vgs| (Id-Vg) or |Vds| (Id-Vd, one entry per |Vgs|), or Cgg (fF) against
    u = polarity × Vg (cv)."""
    if sweep == "cv":
        return [(None, *data.spice_cv(cols, pol))]
    zero_vb = cols["vb"] == 0.0
    if not np.any(zero_vb):
        raise ValueError(f"{sweep}: no vb = 0 rows to plot")
    if sweep in ("idvg_lin", "idvg_sat"):
        return [(None, pol * cols["vg"][zero_vb], np.abs(cols["id"][zero_vb]))]
    out = []
    for v in sorted(set(np.abs(cols["vg"][zero_vb]).tolist())):
        m = zero_vb & (np.abs(cols["vg"]) == v)
        out.append((v, pol * cols["vd"][m], np.abs(cols["id"][m])))
    return out


class Sweep(NamedTuple):
    """One sweep of one geometry: each corner's :func:`series` (ngspice), and Xyce's at the
    typical corner (None for a sweep Xyce does not run)."""

    corners: dict[str, list]
    xyce: list | None


def sweep_data(device: str, gid: str, sweep: str, root: pathlib.Path) -> Sweep:
    """The committed :class:`Sweep`; ValueError if the corners or the engines differ in grid."""
    pol = DEVICES[device].polarity
    per = {
        c: series(data.spice_columns(root, "ngspice", c, device, gid, sweep), sweep, pol)
        for c in CORNERS
    }
    xs = None
    if has_sweep("xyce", sweep):
        xs = series(data.spice_columns(root, "xyce", TYPICAL, device, gid, sweep), sweep, pol)
    tt = per[TYPICAL]
    for i, (_v, x, _y) in enumerate(tt):
        for c, s in per.items():
            if not np.array_equal(s[i][1], x):
                raise ValueError(f"{device} {gid} {sweep}: the {c} grid differs")
        if xs is not None and not np.array_equal(xs[i][1], x):
            raise ValueError(f"{device} {gid} {sweep}: the Xyce grid differs")
    return Sweep(per, xs)


def _draw_sweep(ax, s: Sweep, colours: list[str], band: list[str], scale: float,
                floor: float | None, pal: dict) -> None:  # fmt: skip
    """Each series of ``s``: the corner band, the ngspice typical line and the Xyce dashed line,
    gids ``corners k``, ``typical k`` and ``xyce k`` (k counts the series from 0)."""
    lw = STYLE["line_width"]

    def y(a):
        a = a * scale
        return a if floor is None else np.maximum(a, floor)

    for k, (_v, x, ytt) in enumerate(s.corners[TYPICAL]):
        stack = [y(per[k][2]) for per in s.corners.values()]
        ax.fill_between(x, np.min(stack, axis=0), np.max(stack, axis=0), color=band[k],
                        linewidth=0, alpha=STYLE["family_alpha"] if band[k] != pal["band"] else 1,
                        gid=f"corners {k}")  # fmt: skip
    for k, (_v, x, ytt) in enumerate(s.corners[TYPICAL]):
        ax.plot(x, y(ytt), color=colours[k], lw=lw, gid=f"typical {k}")
        if s.xyce is not None:
            ax.plot(x, y(s.xyce[k][2]), color=colours[k], lw=lw, ls="--", gid=f"xyce {k}")


def _engine_keys(pal: dict, colour: str, xyce: bool) -> list:
    keys = [
        Line2D([], [], color=colour, lw=STYLE["line_width"], label="ngspice, typical corner"),
        Patch(color=pal["band"], label=f"ngspice, all {len(CORNERS)} corners"),
    ]
    if xyce:
        keys.insert(1, Line2D([], [], color=colour, lw=STYLE["line_width"], ls="--",
                              label="Xyce, typical corner"))  # fmt: skip
    return keys


def bias(device: str, gid: str, sweep: str, column: str, root: pathlib.Path) -> float:
    """The one |value| of a bias ``column`` (vd or vb) over the rows a sweep's figure draws (the
    typical corner, body at 0 V); ValueError if they hold several."""
    cols = data.spice_columns(root, "ngspice", TYPICAL, device, gid, sweep)
    values = set(np.abs(cols[column][cols["vb"] == 0.0]).tolist())
    if len(values) != 1:
        raise ValueError(f"{device} {gid} {sweep}: {column} takes {sorted(values)}")
    return values.pop()


def idvg_figure(device: str, gid: str, sweep: str, palette: str, roots: Roots = DEFAULT_ROOTS):
    """|Id| against |Vgs| of one Id-Vg sweep (``idvg_lin`` or ``idvg_sat``) at a body bias of 0,
    on a linear axis (mA, top) and a log axis (A, bottom, floored at ``id_floor_a``): the
    ngspice corner band, the ngspice typical line and the Xyce typical line (dashed)."""
    pal = ef.PALETTES[palette]
    s = sweep_data(device, gid, sweep, roots.spice)
    vds = bias(device, gid, sweep, "vd", roots.spice)
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(STYLE["two_in"])
        lin, log = fig.subplots(2, 1)
        _draw_sweep(lin, s, [pal["electron"]], [pal["band"]], UNITS["ma_per_a"], None, pal)
        _draw_sweep(log, s, [pal["electron"]], [pal["band"]], 1, STYLE["id_floor_a"], pal)
        log.set_yscale("log")
        log.set_ylim(bottom=STYLE["id_floor_a"])
        lin.set_ylabel("|Id| (mA)")
        log.set_ylabel("|Id| (A)")
        for ax in (lin, log):
            ax.set_xlabel("|Vgs| (V)")
            ax.grid(True)
        fig.suptitle(f"{geometry_label(geometry(device, gid))}, |Vds| = {vds:g} V")
        _legend(fig, _engine_keys(pal, pal["electron"], s.xyce is not None))
        return fig


def idvd_figure(device: str, gid: str, palette: str, roots: Roots = DEFAULT_ROOTS):
    """|Id| (mA) against |Vds| at a body bias of 0, one colour per |Vgs|: the ngspice corner band
    in that colour, the ngspice typical line and the Xyce typical line (dashed)."""
    pal = ef.PALETTES[palette]
    s = sweep_data(device, gid, "idvd", roots.spice)
    family = [pal[c] for c in ef.STYLE["family"]]
    gates = [v for v, _x, _y in s.corners[TYPICAL]]
    if len(gates) > len(family):
        raise ValueError(f"{device} {gid} idvd: {len(gates)} gate voltages, {len(family)} colours")
    colours = family[: len(gates)]
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(STYLE["one_in"])
        ax = fig.subplots()
        _draw_sweep(ax, s, colours, colours, UNITS["ma_per_a"], None, pal)
        ax.set_xlabel("|Vds| (V)")
        ax.set_ylabel("|Id| (mA)")
        ax.grid(True)
        ax.set_title(geometry_label(geometry(device, gid)))
        keys = [Line2D([], [], color=c, lw=STYLE["line_width"], label=f"|Vgs| = {v:g} V")
                for c, v in zip(colours, gates, strict=True)]  # fmt: skip
        keys += [
            Line2D([], [], color=pal["muted"], lw=STYLE["line_width"], label="ngspice, typical"),
            Line2D([], [], color=pal["muted"], lw=STYLE["line_width"], ls="--",
                   label="Xyce, typical"),
            Patch(color=pal["muted"], alpha=STYLE["family_alpha"], label=f"all {len(CORNERS)} corners"),
        ]  # fmt: skip
        _legend(fig, keys)
        return fig


def cv_figure(device: str, gid: str, palette: str, roots: Roots = DEFAULT_ROOTS):
    """Cgg (fF) against u = polarity × Vgs: the ngspice corner band and typical line (Xyce runs
    no C-V sweep)."""
    pal = ef.PALETTES[palette]
    s = sweep_data(device, gid, "cv", roots.spice)
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(STYLE["one_in"])
        ax = fig.subplots()
        _draw_sweep(ax, s, [pal["electron"]], [pal["band"]], 1, None, pal)
        ax.set_xlabel("polarity × Vgs (V)")
        ax.set_ylabel("Cgg (fF)")
        ax.grid(True)
        ax.set_title(geometry_label(geometry(device, gid)))
        _legend(fig, _engine_keys(pal, pal["electron"], s.xyce is not None))
        return fig


def engine_diffs(device: str, root: pathlib.Path) -> dict[str, list[float]]:
    """``{sweep: [engine_diff of each geometry]}`` of ``device`` at the typical corner, as a
    fraction (:func:`gf180tcad.spice.xyce.engine_diff`), geometries in the device's order."""
    out = {}
    for sweep in DIFF_SWEEPS:
        out[sweep] = [
            engine_diff(
                data.spice_columns(root, "ngspice", TYPICAL, device, geometry_id(g), sweep),
                data.spice_columns(root, "xyce", TYPICAL, device, geometry_id(g), sweep),
            )
            for g in DEVICES[device].geometries
        ]
    return out


def engine_diff_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The ngspice-against-Xyce difference (%) of each sweep at each geometry, one panel per
    device (axis gid: the device), one marker shape per sweep (gid ``<device> <sweep>``), on a
    log axis, with the threshold drawn across (gid ``threshold``)."""
    pal = ef.PALETTES[palette]
    family = [pal[c] for c in ef.STYLE["family"]]
    pct = UNITS["pct_per_one"]
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(STYLE["two_in"])
        axes = fig.subplots(len(DEVICES), 1)
        for ax, (device, dev) in zip(axes, DEVICES.items(), strict=True):
            ax.set_gid(device)
            x = np.arange(len(dev.geometries))
            for k, (sweep, diffs) in enumerate(engine_diffs(device, roots.spice).items()):
                y = np.maximum(np.asarray(diffs) * pct, STYLE["diff_floor_pct"])
                ax.plot(x, y, ls="none", marker=STYLE["engine_markers"][k], color=family[k],
                        markersize=STYLE["marker_pt"], label=sweep,
                        gid=f"{device} {sweep}")  # fmt: skip
            ax.axhline(ENGINE_DIFF_THRESHOLD * pct, color=pal["text"], lw=STYLE["line_width"],
                       ls="--", gid="threshold")  # fmt: skip
            ax.set_yscale("log")
            ax.set_xticks(x, [geometry_label(g) for g in dev.geometries],
                          rotation=STYLE["tick_deg"])  # fmt: skip
            ax.set_ylabel("difference (%)")
            ax.set_title(device)
            ax.grid(True)
        handles, _labels = axes[0].get_legend_handles_labels()
        handles.append(Line2D([], [], color=pal["text"], lw=STYLE["line_width"], ls="--",
                              label=f"threshold {ENGINE_DIFF_THRESHOLD * pct:g} %"))  # fmt: skip
        _legend(fig, handles)
        return fig


# --- the TCAD MOS capacitor -----------------------------------------------------------------------


def comparison(tcad_root: pathlib.Path, device: str, gid: str) -> tuple[dict, str]:
    """``(record, repo path)`` of the committed 1D comparison of one geometry: the calibration
    result file for a calibration geometry, the validation file for a held-out one."""
    cal = f"calibration/{device}.result.json"
    rec = _read_json(pathlib.Path(tcad_root) / cal)["per_geometry"].get(gid)
    if rec is not None:
        return rec, f"results/tcad/{cal}"
    val = f"validation/{device}.json"
    rec = _read_json(pathlib.Path(tcad_root) / val)["one_d"].get(gid)
    if rec is not None:
        return rec, f"results/tcad/{val}"
    raise KeyError(f"{device} {gid}: in neither the calibration nor the validation file")


def _read_json(path: pathlib.Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"missing result file {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def tcad_cgg(tcad_root: pathlib.Path, device: str, gid: str, params: str) -> list[np.ndarray]:
    """``[u, intrinsic, parasitic, total]`` (fF) of one geometry from the committed 1D C per area
    at ``params``, through the fixed BSIM4 bookkeeping (:func:`gf180tcad.explain.data.tcad_cgg`)."""
    m, proc = data.read_moscap(tcad_root, device, params)
    return data.tcad_cgg(m, geometry(device, gid), proc, DEVICES[device].polarity)


def spice_cv(spice_root: pathlib.Path, device: str, gid: str) -> Sweep:
    """The ngspice ``cv`` sweep of one geometry (:func:`sweep_data`)."""
    return sweep_data(device, gid, "cv", spice_root)


def cgg_figure(device: str, gid: str, palette: str, roots: Roots = DEFAULT_ROOTS):
    """Top: the 1D TCAD Cgg of one geometry at the calibrated values (gid ``tcad calibrated``)
    and at the start values (dashed, ``tcad start``), over the ngspice corner band and typical
    line. Bottom: the relative error at each plateau bias as the comparison record holds it
    (``plateau acc``, ``plateau inv``, in %), with each plateau's tolerance drawn over its own
    span (``tolerance <side> upper`` and ``lower``)."""
    pal = ef.PALETTES[palette]
    lw = STYLE["line_width"]
    pct = UNITS["pct_per_one"]
    rec, _src = comparison(roots.tcad, device, gid)
    u, _i, _p, cal = tcad_cgg(roots.tcad, device, gid, "calibrated")
    us, _i, _p, start = tcad_cgg(roots.tcad, device, gid, "start")
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(STYLE["two_in"])
        top, bottom = fig.subplots(2, 1)
        _draw_sweep(top, spice_cv(roots.spice, device, gid), [pal["text"]], [pal["band"]], 1,
                    None, pal)  # fmt: skip
        top.plot(us, start, color=pal["hole"], lw=lw, ls="--", gid="tcad start")
        top.plot(u, cal, color=pal["highlight"], lw=lw, gid="tcad calibrated")
        top.set_ylabel("Cgg (fF)")
        top.set_title("Cgg against SPICE")
        res = rec["residuals"]
        tols = {}
        for side, colour in (("acc", pal["hole"]), ("inv", pal["electron"])):
            pu = np.asarray(res[f"plateau_{side}_u"], dtype=float)
            tol = pct * rec["verdicts"][f"plateau_{side}"]["tolerance"]
            tols[side] = tol
            span = [pu.min(), pu.max()]
            bottom.plot(pu, pct * np.asarray(res[f"plateau_{side}_rel"]), color=colour, lw=lw,
                        marker="o", markersize=STYLE["marker_pt"] / 2,
                        gid=f"plateau {side}")  # fmt: skip
            for edge, sign in (("upper", 1), ("lower", -1)):
                bottom.plot(span, [sign * tol, sign * tol], color=pal["muted"], lw=lw, ls="--",
                            gid=f"tolerance {side} {edge}")  # fmt: skip
        bottom.set_ylabel("(TCAD − SPICE) / SPICE (%)")
        bottom.set_title("plateau errors, from the result file")
        for ax in (top, bottom):
            ax.set_xlabel(U_LABEL)
            ax.grid(True)
        if tols["acc"] == tols["inv"]:
            tol_keys = [f"tolerance ±{tols['acc']:g} %"]
        else:
            tol_keys = [f"tolerance ({side}) ±{t:g} %" for side, t in tols.items()]
        keys = [
            Line2D([], [], color=pal["text"], lw=lw, label="SPICE, typical corner"),
            Patch(color=pal["band"], label=f"SPICE, all {len(CORNERS)} corners"),
            Line2D([], [], color=pal["highlight"], lw=lw, label="TCAD, calibrated"),
            Line2D([], [], color=pal["hole"], lw=lw, ls="--", label="TCAD, start values"),
            Line2D([], [], color=pal["hole"], lw=lw, marker="o", label="accumulation error"),
            Line2D([], [], color=pal["electron"], lw=lw, marker="o", label="inversion error"),
            *(Line2D([], [], color=pal["muted"], lw=lw, ls="--", label=t) for t in tol_keys),
        ]
        _legend(fig, keys)
        return fig


def split_figure(device: str, gid: str, palette: str, roots: Roots = DEFAULT_ROOTS):
    """The calibrated 1D TCAD Cgg of one geometry (gid ``total``) and its two parts:
    ``intrinsic``, the C per area times the BSIM4 capacitance area, and ``parasitic``, the
    overlap, fringe and gate-bulk terms; with the ngspice typical line (``typical``)."""
    pal = ef.PALETTES[palette]
    lw = STYLE["line_width"]
    u, intrinsic, parasitic, total = tcad_cgg(roots.tcad, device, gid, "calibrated")
    s = spice_cv(roots.spice, device, gid)
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(STYLE["one_in"])
        ax = fig.subplots()
        ((_v, x, tt),) = s.corners[TYPICAL]
        ax.plot(x, tt, color=pal["text"], lw=lw, gid="typical")
        ax.plot(u, total, color=pal["highlight"], lw=lw, gid="total")
        ax.plot(u, intrinsic, color=pal["electron"], lw=lw, ls="--", gid="intrinsic")
        ax.plot(u, parasitic, color=pal["highlight_oxide"], lw=lw, ls=":", gid="parasitic")
        ax.set_xlabel(U_LABEL)
        ax.set_ylabel("Cgg (fF)")
        ax.set_ylim(bottom=0)
        ax.grid(True)
        ax.set_title(geometry_label(geometry(device, gid)))
        _legend(fig, [
            Line2D([], [], color=pal["text"], lw=lw, label="SPICE, typical corner"),
            Line2D([], [], color=pal["highlight"], lw=lw, label="TCAD total"),
            Line2D([], [], color=pal["electron"], lw=lw, ls="--", label="intrinsic part"),
            Line2D([], [], color=pal["highlight_oxide"], lw=lw, ls=":", label="parasitic part"),
        ])  # fmt: skip
        return fig


def two_d_cells(tcad_root: pathlib.Path, device: str, gid: str) -> list[str]:
    """The parameter sets (of :data:`TWO_D_PARAMS`) with a committed 2D cell of ``gid``."""
    root = pathlib.Path(tcad_root) / "moscap2d" / device
    return [p for p in TWO_D_PARAMS if (root / p / gid / "cv.meta.json").is_file()]


def two_d_curves(tcad_root: pathlib.Path, device: str, gid: str, params: str):
    """``(u2, c2, u1, c1)``: the C per area (fF/µm²) of the committed 2D cell at ``params``
    against u, and that of the committed 1D stack at the same values."""
    pol = DEVICES[device].polarity
    cols, _meta = io.read_csv(pathlib.Path(tcad_root) / "moscap2d" / device / params / gid
                              / "cv.csv")  # fmt: skip
    u2, c2 = data.u_sorted(cols["vg"], pol, cols["c_per_area"])
    m, _proc = data.read_moscap(tcad_root, device, params)
    u1, c1 = data.u_sorted(m.vg, pol, m.c_per_area_ff_um2)
    return u2, c2, u1, c1


def two_d_figure(device: str, gid: str, palette: str, roots: Roots = DEFAULT_ROOTS):
    """One panel per committed 2D cell of ``gid`` (axis gid: its parameter set): its C per area
    (gid ``cell``), the per-width Cgg divided by the drawn L with no bookkeeping, against the
    1D stack at the same values (dashed, gid ``stack``). ValueError if there is no 2D cell."""
    pal = ef.PALETTES[palette]
    lw = STYLE["line_width"]
    cells = two_d_cells(roots.tcad, device, gid)
    if not cells:
        raise ValueError(f"{device} {gid}: no committed 2D cell")
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(STYLE["one_in"] if len(cells) == 1 else STYLE["two_in"])
        axes = fig.subplots(len(cells), 1, squeeze=False)[:, 0]
        for ax, params in zip(axes, cells, strict=True):
            ax.set_gid(params)
            u2, c2, u1, c1 = two_d_curves(roots.tcad, device, gid, params)
            ax.plot(u1, c1, color=pal["electron"], lw=lw, ls="--", gid="stack")
            ax.plot(u2, c2, color=pal["highlight"], lw=lw, gid="cell")
            ax.set_title(f"{geometry_label(geometry(device, gid))}, {params} values")
            ax.set_xlabel(U_LABEL)
            ax.set_ylabel("C per area (fF/µm²)")
            ax.grid(True)
        _legend(fig, [
            Line2D([], [], color=pal["highlight"], lw=lw, label="cell with source and drain"),
            Line2D([], [], color=pal["electron"], lw=lw, ls="--", label="stack, same values"),
        ])  # fmt: skip
        return fig


def meshconv_report(tcad_root: pathlib.Path, device: str, structure: str) -> dict:
    """The committed mesh-convergence report of ``device``'s ``structure`` (``moscap1d`` or
    ``moscap2d``)."""
    return _read_json(pathlib.Path(tcad_root) / "meshconv" / structure / device / "report.json")


def meshconv_figure(device: str, structure: str, palette: str, roots: Roots = DEFAULT_ROOTS):
    """Top: the C per area at each mesh level (gid ``level <i>``; the selected level solid, the
    others dashed). Bottom: each level's relative change ``|C / C_finer − 1|`` against the next finer level
    (gid ``change <i>``, floored at ``change_floor``), and the criterion (gid ``criterion``)."""
    pal = ef.PALETTES[palette]
    lw = STYLE["line_width"]
    report = meshconv_report(roots.tcad, device, structure)
    pol = DEVICES[device].polarity
    sel = report["selected"]["level"]
    family = [pal[c] for c in ef.STYLE["family"]]
    if len(report["levels"]) > len(family):
        raise ValueError(f"{device} {structure}: more levels than colours")
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(STYLE["two_in"])
        vals, changes = fig.subplots(2, 1)
        keys = []
        for i, lv in enumerate(report["levels"]):
            ls = "-" if i == sel else "--"
            u, c = data.u_sorted(report["vg"], pol, lv["c_per_area_ff_um2"])
            vals.plot(u, c, color=family[i], lw=lw, ls=ls, gid=f"level {i}")
            if lv["rel_change"] is not None:
                u, r = data.u_sorted(report["vg"], pol, lv["rel_change"])
                changes.plot(u, np.maximum(np.abs(r), STYLE["change_floor"]), color=family[i],
                             lw=lw, ls=ls, gid=f"change {i}")  # fmt: skip
            mark = ", selected" if i == sel else ""
            keys.append(Line2D([], [], color=family[i], lw=lw, ls=ls,
                               label=f"level {i}: {lv['node_count']} nodes{mark}"))  # fmt: skip
        crit = report["criterion"]
        changes.axhline(crit, color=pal["muted"], lw=lw, gid="criterion")
        keys.append(Line2D([], [], color=pal["muted"], lw=lw, label=f"criterion {crit:g}"))
        changes.set_yscale("log")
        vals.set_ylabel("C per area (fF/µm²)")
        changes.set_ylabel("relative change")
        vals.set_title(f"{device}, by mesh level")
        changes.set_title("change against the next finer level")
        for ax in (vals, changes):
            ax.set_xlabel(U_LABEL)
            ax.grid(True)
        _legend(fig, keys)
        return fig


#: The layers the calibration fits, highlighted on the stack figure: the oxide (its thickness)
#: and the body (its doping).
FITTED_PARTS = ("oxide", "body")


def stack_model(device: str):
    """The explainer model of ``device``'s calibrated 1D stack, at the explainer's scale factors
    (:func:`gf180tcad.explain.model.device`, which reads the committed 1D metadata)."""
    from gf180tcad.explain import model

    return model.device(device, "calibrated", scales=ef.STYLE["scales"])


def stack_figure(device: str, palette: str, roots: Roots = DEFAULT_ROOTS):
    """The calibrated 1D stack of ``device``, gate on top, each layer labelled with its material,
    thickness and doping, the fitted layers highlighted
    (:func:`gf180tcad.explain.figures.stack_1d_figure`). Like the explainer's stack drawings it
    reads the committed tree through the explainer model, so ``roots`` is not used."""
    return ef.stack_1d_figure(stack_model(device), FITTED_PARTS, palette)
