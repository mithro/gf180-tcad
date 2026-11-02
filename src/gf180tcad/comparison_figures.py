# SPDX-License-Identifier: Apache-2.0
"""Every figure of the comparison pages (``docs/comparison/``), in a light and a dark twin.

Each figure is drawn from committed files only: the SPICE reference (``results/spice``), the
rerun with the older PDK (``results/spice-pdk-d658698``), the 1D and 2D TCAD results and the
mesh-convergence reports (``results/tcad``), the process files (``data/process``) and the
netlist template (:func:`gf180tcad.spice.netlist.instance_params`). It uses the colours, text
size and deterministic SVG settings of the explainer figures (:mod:`gf180tcad.explain.figures`),
and :func:`write_all` writes each as ``<name>-light.svg`` and ``<name>-dark.svg`` into
``docs/_generated/comparison/`` at docs build time (:func:`gf180tcad.docgen.generate`). A page
embeds both, and the theme shows one.

No number is typed below except in :data:`STYLE` (sizes, offsets, axis spans) and :data:`UNITS`
(unit conversions), so a figure's data come only from the committed files (tested).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from gf180tcad.calibrate import cv as calcv
from gf180tcad.devices import DEVICES, Geometry, geometry_id
from gf180tcad.explain import data, model
from gf180tcad.explain import figures as ef
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.spice import netlist
from gf180tcad.tcad import process

STYLE = {
    # Two or three rows of panels: a taller figure at the explainer figures' width.
    "tall_in": (6.4, 7.2),
    "plan_in": (6.4, 6.4),
    "marker_pt": 9.0,
    # The gate of the plan view runs this far past the active area at each end (µm), a
    # drawing choice: the instance parameters do not depend on it.
    "gate_overhang_um": 0.2,
    # Room round the plan view, as a fraction of its width, for the dimension labels.
    "plan_margin": 0.35,
    "dim_offset": 0.12,
    # The pfet edge plot: the span of u (V) that holds every depletion-side crossing.
    "edge_u_v": (-2.0, 0.0),
    "edge_headroom": 1.05,
    # The C-V plots of the metric: shading of the plateaus, label lift (fraction of C_acc).
    "plateau_alpha": 0.2,
    "label_lift": 0.04,
    "metric_headroom": 1.35,
    # The Id-Vg plot of the two PDKs: the older PDK's line dashed, on top.
    "older_zorder": 3,
    "older_dash": (0, (4, 3)),
    # The criterion label of the mesh plot sits this fraction of the axis width from the left.
    "criterion_x": 0.02,
    # Legends of three or more entries: this many per row.
    "legend_cols": 3,
    # The tick labels of gate lengths stand upright, so that 0.5, 0.6 and 0.7 do not overlap.
    "tick_deg": 90,
}

# Unit conversions: m to µm and nm, A to µA.
UNITS = {"um_per_m": 1e6, "nm_per_m": 1e9, "ua_per_a": 1e6}

# The committed SPICE reference.
SPICE_ROOT = REPO_ROOT / "results" / "spice"
# The committed rerun of the SPICE reference with the open_pdks d658698 models.
OLDER_PDK_ROOT = REPO_ROOT / "results" / "spice-pdk-d658698"
# The committed TCAD results: 1D and 2D C-V, calibration, validation, mesh convergence.
TCAD_ROOT = REPO_ROOT / "results" / "tcad"
# The corner of the SPICE reference that the TCAD is compared with.
TYPICAL = "typical"

_DEVICES = ("nfet_05v0", "pfet_05v0")
_SHORT = {"nfet_05v0": "nfet", "pfet_05v0": "pfet"}
_CARRIER = {"nfet_05v0": "electron", "pfet_05v0": "hole"}
# The colours of up to five curves of one plot, distinct in both palettes.
_SERIES = ("electron", "hole", "highlight", "highlight_oxide", "intrinsic")


def _label(g: Geometry) -> str:
    return f"W{g.w_um:g}/L{g.l_um:g}"


def _geometries(device: str, role: str) -> list[Geometry]:
    """The geometries of ``device`` with ``role``, by falling W and then falling L."""
    gs = [g for g in DEVICES[device].geometries if g.role == role]
    return sorted(gs, key=lambda g: (-g.w_um, -g.l_um))


def _figure(size: tuple[float, float]) -> Figure:
    fig = Figure(figsize=size, layout="constrained")
    FigureCanvasAgg(fig)
    return fig


# --- the definition of agreement ----------------------------------------------------------------


def process_cell(palette: str) -> bytes:
    """The 2D cell of the calibrated nfet at ``w10p0_l0p70`` cut along its length, drawn by
    :func:`gf180tcad.explain.figures.cross_section`: the parts whose doping, oxide and contacts
    one process description sets."""
    c = model.cell("nfet_05v0", "calibrated", "w10p0_l0p70", scales=ef.STYLE["scales"],
                   drawn=ef.STYLE["drawn_um"])  # fmt: skip
    return ef.cross_section(c, (), palette)


# The device of the plan view.
PLAN_DEVICE = "nfet_05v0"
# The geometry of the plan view: the narrow test-device geometry, the one closest to square.
PLAN_GEOMETRY = "w1p6_l0p70"


def instance_extents(device: str = PLAN_DEVICE, gid: str = PLAN_GEOMETRY) -> dict[str, float]:
    """W, L and the source/drain length (µm) of the instance the SPICE reference writes, read
    back from :func:`gf180tcad.spice.netlist.instance_params`: the length is AS / W, and the
    perimeter PS = 2·(W + length) is checked against it (ValueError if it differs)."""
    dev = DEVICES[device]
    (g,) = [g for g in dev.geometries if geometry_id(g) == gid]
    p = netlist.instance_params(dev, g)
    w_m = g.w_um / UNITS["um_per_m"]
    sd_um = float(p["as"]) / w_m * UNITS["um_per_m"]
    ps_um = float(p["ps"]) * UNITS["um_per_m"]
    if not np.isclose(ps_um, 2 * (g.w_um + sd_um)):
        raise ValueError(f"{device} {gid}: PS {ps_um} µm is not 2·(W + AS/W)")
    if p["as"] != p["ad"] or p["ps"] != p["pd"]:
        raise ValueError(f"{device} {gid}: the source and drain differ")
    return {"w_um": g.w_um, "l_um": g.l_um, "sd_um": sd_um}


def instance_plan(palette: str) -> bytes:
    """The transistor of the SPICE reference seen from above, to scale: the gate strip of length
    L across the active area of width W, and the source and drain each of the length that AS and
    PS (AD and PD) assume, outlined by the perimeter those parameters count."""
    pal = ef.PALETTES[palette]
    e = instance_extents()
    w, half, sd = e["w_um"], e["l_um"] / 2, e["sd_um"]
    over = STYLE["gate_overhang_um"]
    off = (2 * (half + sd)) * STYLE["dim_offset"]
    fill = pal[_CARRIER[PLAN_DEVICE]]
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(STYLE["plan_in"])
        ax = fig.subplots()
        ax.set_axis_off()
        ax.set_aspect("equal")
        for x0, x1, name, short in ((-half - sd, -half, "source", "AS, PS"),
                                    (half, half + sd, "drain", "AD, PD")):  # fmt: skip
            ax.fill_between([x0, x1], 0, w, color=fill, alpha=ef.STYLE["cell_alpha"], lw=0)
            ax.plot([x0, x1, x1, x0, x0], [0, 0, w, w, 0], color=pal["text"],
                    lw=ef.STYLE["line_width"], ls=ef.STYLE["window_dash"])  # fmt: skip
            ax.text((x0 + x1) / 2, w / 2, f"{name}\n{short}", ha="center", va="center",
                    rotation=ef.STYLE["upright_deg"])  # fmt: skip
        ax.fill_between([-half, half], -over, w + over, color=pal["muted"],
                        alpha=ef.STYLE["cell_alpha"], lw=0)  # fmt: skip
        ax.plot([-half, half, half, -half, -half], [-over, -over, w + over, w + over, -over],
                color=pal["text"], lw=ef.STYLE["edge_width"])  # fmt: skip
        ax.text(0, w / 2, "gate", ha="center", va="center", rotation=ef.STYLE["upright_deg"])
        arrow = {"arrowstyle": "<->", "color": pal["text"], "lw": ef.STYLE["edge_width"]}
        right = half + sd + off
        ax.annotate("", xy=(right, 0), xytext=(right, w), arrowprops=arrow)
        ax.text(right + off / 2, w / 2, f"W = {w:g} µm", ha="left", va="center")
        top = w + over + off
        ax.annotate("", xy=(-half, top), xytext=(half, top), arrowprops=arrow)
        ax.text(0, top + off / 2, f"L = {e['l_um']:g} µm", ha="center", va="bottom")
        bottom = -over - off
        ax.annotate("", xy=(half, bottom), xytext=(half + sd, bottom), arrowprops=arrow)
        ax.text(half + sd / 2, bottom - off / 2, f"{sd:g} µm", ha="center", va="top")
        span = 2 * (half + sd)
        pad = span * STYLE["plan_margin"]
        ax.set_xlim(-half - sd - pad, half + sd + pad * 2)
        ax.set_ylim(bottom - pad, top + pad)
        return ef._svg(fig)


def geometries(palette: str) -> bytes:
    """W against L of every compared geometry, one panel per device: filled markers for the
    calibration geometries, open markers for the held-out ones (:attr:`Geometry.role`)."""
    pal = ef.PALETTES[palette]
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        axes = fig.subplots(len(_DEVICES), 1)
        for ax, device in zip(axes, _DEVICES, strict=True):
            colour = pal[_CARRIER[device]]
            for role, face, name in (("calibration", colour, "calibration"),
                                     ("validation", "none", "held out")):  # fmt: skip
                gs = _geometries(device, role)
                ax.plot([g.l_um for g in gs], [g.w_um for g in gs], ls="none", marker="o",
                        ms=STYLE["marker_pt"], mfc=face, mec=colour,
                        mew=ef.STYLE["edge_width"] * 2, label=name)  # fmt: skip
            every = DEVICES[device].geometries
            ax.set_xscale("log")
            ax.set_xticks(sorted({g.l_um for g in every}), minor=False)
            ax.set_xticks([], minor=True)
            ax.set_xticklabels([f"{x:g}" for x in sorted({g.l_um for g in every})],
                               rotation=STYLE["tick_deg"])  # fmt: skip
            ax.set_yticks(sorted({g.w_um for g in every}))
            ax.set_yticklabels([f"{w:g}" for w in sorted({g.w_um for g in every})])
            ax.set_ylim(0, max(g.w_um for g in every) * STYLE["edge_headroom"] ** 2)
            ax.set_title(_SHORT[device], fontsize=ef.STYLE["text_pt"])
            ax.set_ylabel("W (µm)")
            ax.grid(True)
            ax.legend(loc="center right", frameon=False)
            ax.set_xlabel("L (µm)")
        return ef._svg(fig)


def meshconv_report(dim: int, device: str) -> dict:
    """The committed mesh-convergence report of the ``dim``-D MOS capacitor of ``device``."""
    path = TCAD_ROOT / "meshconv" / f"moscap{dim}d" / device / "report.json"
    return json.loads(path.read_text("utf-8"))


def meshconv_points(report: dict) -> tuple[list[int], list[float]]:
    """``(node counts, largest |C / C_finer - 1| over the sweep)`` of each level that has a
    finer level to compare with."""
    nodes, change = [], []
    for lv in report["levels"]:
        if lv["rel_change"] is None:
            continue
        nodes.append(lv["node_count"])
        change.append(max(abs(x) for x in lv["rel_change"]))
    return nodes, change


def meshconv(palette: str) -> bytes:
    """The mesh convergence of the 1D and 2D MOS capacitors: the largest change of the C per
    area against the next finer mesh, by node count, with the reports' criterion."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    crit = set()
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        ax = fig.subplots()
        for dim, style in ((1, "-"), (2, "--")):
            for device in _DEVICES:
                report = meshconv_report(dim, device)
                crit.add(report["criterion"])
                nodes, change = meshconv_points(report)
                ax.plot(nodes, change, color=pal[_CARRIER[device]], ls=style, lw=lw, marker="o",
                        label=f"{dim}D {_SHORT[device]}")  # fmt: skip
        (c,) = crit
        ax.axhline(c, color=pal["text"], lw=ef.STYLE["edge_width"], ls=":")
        ax.text(STYLE["criterion_x"], c, f"criterion {c:.0%}", va="bottom", ha="left",
                transform=ax.get_yaxis_transform())  # fmt: skip
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("mesh nodes")
        ax.set_ylabel("largest |C / C_finer − 1|")
        ax.grid(True)
        fig.legend(loc="outside lower center", ncols=2, frameon=False)
        return ef._svg(fig)


# --- the C-V calibration ---------------------------------------------------------------------


def _cv_grid(role: str, palette: str) -> bytes:
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    rows = {d: _geometries(d, role) for d in _DEVICES}
    (n,) = {len(gs) for gs in rows.values()}
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(STYLE["tall_in"])
        axes = fig.subplots(n, len(_DEVICES), sharex=True)
        for col, device in enumerate(_DEVICES):
            for row, g in enumerate(rows[device]):
                ax = axes[row][col]
                c = ef.cv_curves(device, "calibrated", geometry_id(g))
                ax.fill_between(c["u_spice"], c["spice_lo"], c["spice_hi"], color=pal["band"],
                                linewidth=0, label="SPICE, all corners")  # fmt: skip
                ax.plot(c["u_spice"], c["spice_tt"], color=pal["text"], lw=lw,
                        label="SPICE, typical")  # fmt: skip
                ax.plot(c["u"], c["tcad"], color=pal["highlight"], lw=lw, ls="--",
                        zorder=ef.STYLE["cv_zorder"], label="simulated, fitted")  # fmt: skip
                ax.set_ylim(bottom=0)
                ax.grid(True)
                ax.set_title(f"{_SHORT[device]} {_label(g)}", fontsize=ef.STYLE["text_pt"])
                if col == 0:
                    ax.set_ylabel("Cgg (fF)")
                if row == n - 1:
                    ax.set_xlabel("u (V)")
        handles, labels = axes[0][0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside lower center", ncols=len(labels),
                   frameon=False)  # fmt: skip
        return ef._svg(fig)


def cv_fit(palette: str) -> bytes:
    """Cgg against u of each calibration geometry, nfet left and pfet right: the SPICE typical
    corner inside the band of its five corners, and the fitted 1D stack, dashed."""
    return _cv_grid("calibration", palette)


def cv_validation(palette: str) -> bytes:
    """The same as :func:`cv_fit` at the held-out geometries."""
    return _cv_grid("validation", palette)


# The device of the curve the metric figure marks.
METRIC_DEVICE = "nfet_05v0"
# The geometry of the curve the metric figure marks: the longest calibration gate.
METRIC_GEOMETRY = "w10p0_l10p00"


def metric_regions() -> tuple[np.ndarray, np.ndarray, calcv.Regions]:
    """``(u, C, regions)`` of the SPICE typical curve of :data:`METRIC_GEOMETRY`, the regions
    by :func:`gf180tcad.calibrate.cv.regions`, the function the calibration uses."""
    pol = DEVICES[METRIC_DEVICE].polarity
    cols = data.spice_columns(SPICE_ROOT, "ngspice", TYPICAL, METRIC_DEVICE, METRIC_GEOMETRY, "cv")
    u, c = data.spice_cv(cols, pol)
    return u, c, calcv.regions(tuple(u.tolist()), tuple(c.tolist()))


def cv_metric(palette: str) -> bytes:
    """The SPICE curve of :data:`METRIC_GEOMETRY` with the parts the agreement metric reads:
    the two plateaus (shaded), u_fb and u_t, the level C_mid and its two crossings."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    u, c, r = metric_regions()
    off = calcv.PLATEAU_OFFSET_V
    lift = r.c_acc * STYLE["label_lift"]
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        ax = fig.subplots()
        ax.axvspan(u[0], r.u_fb - off, color=pal["hole"], alpha=STYLE["plateau_alpha"], lw=0)
        ax.axvspan(r.u_t + off, u[-1], color=pal["electron"], alpha=STYLE["plateau_alpha"], lw=0)
        ax.plot(u, c, color=pal["text"], lw=lw)
        for x, name in ((r.u_fb, "u_fb"), (r.u_t, "u_t")):
            ax.axvline(x, color=pal["intrinsic"], lw=ef.STYLE["edge_width"], ls=":")
            ax.text(x, lift, f" {name}", ha="left", va="bottom", color=pal["intrinsic"])
        ax.axhline(r.c_mid, color=pal["highlight"], lw=ef.STYLE["edge_width"], ls="--")
        ax.text(u[-1], r.c_mid + lift, "C_mid ", ha="right", va="bottom", color=pal["highlight"])
        ax.plot([r.u_dep, r.u_inv], [r.c_mid, r.c_mid], ls="none", marker="o",
                ms=STYLE["marker_pt"], color=pal["highlight"])  # fmt: skip
        ax.text(r.u_dep, r.c_mid - lift, "u_dep ", ha="right", va="top", color=pal["highlight"])
        ax.text(r.u_inv, r.c_mid - lift, " u_inv", ha="left", va="top", color=pal["highlight"])
        ax.text((u[0] + r.u_fb - off) / 2, r.c_acc + lift, "accumulation\nplateau",
                ha="center", va="bottom")  # fmt: skip
        ax.text((r.u_t + off + u[-1]) / 2, r.c_inv + lift, "inversion\nplateau",
                ha="center", va="bottom")  # fmt: skip
        ax.set_ylim(0, max(r.c_acc, r.c_inv) * STYLE["metric_headroom"])
        ax.set_xlabel("u = Vg (V)")
        ax.set_ylabel("SPICE Cgg, typical corner (fF)")
        ax.grid(True)
        return ef._svg(fig)


def edge_curves(device: str = "pfet_05v0") -> list[dict]:
    """For each W = 10 µm geometry of ``device`` by falling L: the SPICE typical curve and the
    fitted 1D curve, each divided by its own C at u = -5 V, and the SPICE depletion-side
    crossing ``u_dep`` with its level, by :func:`gf180tcad.calibrate.cv.crossings`."""
    pol = DEVICES[device].polarity
    moscap, proc = data.read_moscap(TCAD_ROOT, device, "calibrated")
    out = []
    wide = max(g.w_um for g in DEVICES[device].geometries)
    for g in sorted(DEVICES[device].geometries, key=lambda g: -g.l_um):
        if g.w_um != wide:
            continue
        cols = data.spice_columns(SPICE_ROOT, "ngspice", TYPICAL, device, geometry_id(g), "cv")
        u_s, c_s = data.spice_cv(cols, pol)
        u_t, _i, _p, c_t = data.tcad_cgg(moscap, g, proc, pol)
        u_dep, _u_inv = calcv.crossings(tuple(u_s.tolist()), tuple(c_s.tolist()))
        level = (min(c_s) + c_s[0]) / 2 / c_s[0]
        out.append({"geometry": g, "u_spice": u_s, "spice": c_s / c_s[0], "u": u_t,
                    "tcad": c_t / c_t[0], "u_dep": u_dep, "level": level})  # fmt: skip
    return out


def pfet_edge(palette: str) -> bytes:
    """The pfet's depletion edge against gate length: the SPICE typical curve (solid) and the
    fitted 1D curve (dashed) of each W = 10 µm geometry, each over its own accumulation value,
    with the SPICE crossing u_dep marked."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    curves = edge_curves()
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        ax = fig.subplots()
        for k, cur in zip(_SERIES, curves, strict=False):
            colour = pal[k]
            ax.plot(cur["u_spice"], cur["spice"], color=colour, lw=lw,
                    label=f"L = {cur['geometry'].l_um:g} µm")  # fmt: skip
            ax.plot(cur["u"], cur["tcad"], color=colour, lw=lw, ls="--")
            ax.plot([cur["u_dep"]], [cur["level"]], ls="none", marker="o",
                    ms=STYLE["marker_pt"], color=colour)  # fmt: skip
        ax.set_xlim(*STYLE["edge_u_v"])
        ax.set_ylim(0, STYLE["edge_headroom"])
        ax.set_xlabel("u = −Vg (V)")
        ax.set_ylabel("Cgg / Cgg(u = −5 V)")
        ax.grid(True)
        fig.legend(loc="outside lower center", ncols=STYLE["legend_cols"], frameon=False)
        return ef._svg(fig)


def fitted_stack(palette: str) -> bytes:
    """The 1D stack of the calibrated nfet, oxide and body shaded: the layers the three tunables
    set, labelled with the fitted thickness and doping."""
    dev = model.device("nfet_05v0", "calibrated", scales=ef.STYLE["scales"])
    return ef.stack_1d(dev, ("oxide", "body"), palette)


# --- the process data ------------------------------------------------------------------------


def start_stack(palette: str) -> bytes:
    """The 1D stack of the nfet at the start values of the calibration, oxide and body shaded."""
    dev = model.device("nfet_05v0", "start", scales=ef.STYLE["scales"])
    return ef.stack_1d(dev, ("oxide", "body"), palette)


# The device of the split plot.
SPLIT_DEVICE = "nfet_05v0"
# The geometry of the split plot: the nfet's shortest gate, where the extrinsic part of Cgg is
# the largest share.
SPLIT_GEOMETRY = "w10p0_l0p60"


def cgg_split(palette: str) -> bytes:
    """The fitted 1D Cgg of :data:`SPLIT_GEOMETRY` and its two parts by the BSIM4 bookkeeping
    (:meth:`gf180tcad.tcad.moscap1d.MoscapCV.area_scaled`): the intrinsic part over the
    capacitance area, and the overlap, fringe and gate-bulk part."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    dev = DEVICES[SPLIT_DEVICE]
    (g,) = [g for g in dev.geometries if geometry_id(g) == SPLIT_GEOMETRY]
    moscap, proc = data.read_moscap(TCAD_ROOT, SPLIT_DEVICE, "calibrated")
    u, intrinsic, parasitic, total = data.tcad_cgg(moscap, g, proc, dev.polarity)
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        ax = fig.subplots()
        ax.plot(u, total, color=pal["text"], lw=lw, label="total")
        ax.plot(u, intrinsic, color=pal["highlight"], lw=lw, ls="--", label="intrinsic")
        ax.plot(u, parasitic, color=pal["hole"], lw=lw, ls=":",
                label="overlap, fringe, gate-bulk")  # fmt: skip
        ax.set_ylim(bottom=0)
        ax.set_xlabel("u = Vg (V)")
        ax.set_ylabel(f"Cgg, nfet {_label(g)} (fF)")
        ax.grid(True)
        fig.legend(loc="outside lower center", ncols=STYLE["legend_cols"], frameon=False)
        return ef._svg(fig)


def centroid_curves(device: str) -> dict:
    """The charge-centroid depth of ``device`` against u on the SPICE cv grid
    (:data:`gf180tcad.tcad.process.CV_VG`): the accumulation formula for u ≤ 0
    (:func:`gf180tcad.tcad.process.ctm_x_dc_acc_m`), the inversion supremum
    (:func:`gf180tcad.tcad.process.ctm_x_dc_inv_sup_m`), and the result of
    :func:`gf180tcad.tcad.process.centroid` (nm and V)."""
    cv = process.load(device).card_values()
    pol = int(cv["type"])
    u = np.array(sorted(pol * v for v in process.CV_VG if pol * v <= 0))
    x_acc = np.array([process.ctm_x_dc_acc_m(pol * x, cv) for x in u]) * UNITS["nm_per_m"]
    return {"u": u, "x_acc_nm": x_acc, "polarity": pol,
            "x_inv_nm": process.ctm_x_dc_inv_sup_m(cv) * UNITS["nm_per_m"],
            "centroid": process.centroid(cv)}  # fmt: skip


def centroid(palette: str) -> bytes:
    """X_DC against u for both devices: the accumulation formula (solid), the plateau windows
    beyond ±:data:`gf180tcad.tcad.process.PLATEAU_V` (shaded), the largest value inside the
    accumulation window (marked) and the inversion supremum (dotted, on the inversion window)."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    edge = process.PLATEAU_V
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        ax = fig.subplots()
        for device in _DEVICES:
            k = centroid_curves(device)
            colour = pal[_CARRIER[device]]
            ax.plot(k["u"], k["x_acc_nm"], color=colour, lw=lw, label=_SHORT[device])
            cen = k["centroid"]
            ax.plot([cen.vg_at_max_v * k["polarity"]],
                    [cen.x_dc_acc_max_m * UNITS["nm_per_m"]], ls="none", marker="o",
                    ms=STYLE["marker_pt"], color=colour)  # fmt: skip
            ax.plot([edge, -process.CV_VG[0]], [k["x_inv_nm"]] * 2, color=colour, lw=lw, ls=":")
        lo, hi = process.CV_VG[0], -process.CV_VG[0]
        ax.axvspan(lo, -edge, color=pal["muted"], alpha=STYLE["plateau_alpha"], lw=0)
        ax.axvspan(edge, hi, color=pal["muted"], alpha=STYLE["plateau_alpha"], lw=0)
        ax.set_xlim(lo, hi)
        ax.set_ylim(bottom=0)
        ax.set_xlabel("u = polarity × Vg (V)")
        ax.set_ylabel("X_DC (nm)")
        ax.grid(True)
        fig.legend(loc="outside lower center", ncols=2, frameon=False)
        return ef._svg(fig)


# --- the PDK versions ------------------------------------------------------------------------

# The geometry of the Id-Vg plot of the two PDKs: the longest gate.
PDK_GEOMETRY = "w10p0_l10p00"


def pdk_sweep_curves(device: str, root: Path) -> list[tuple[np.ndarray, np.ndarray]]:
    """``(|Vg|, |Id|)`` of the committed typical ``idvg_lin`` sweep of :data:`PDK_GEOMETRY`
    under ``root`` (V and µA), one pair per body bias, in file order."""
    cols = data.spice_columns(root, "ngspice", TYPICAL, device, PDK_GEOMETRY, "idvg_lin")
    out = []
    for vb in dict.fromkeys(cols["vb"].tolist()):
        keep = cols["vb"] == vb
        out.append((np.abs(cols["vg"][keep]), np.abs(cols["id"][keep]) * UNITS["ua_per_a"]))
    return out


def pdk_sweeps(palette: str) -> bytes:
    """|Id| against |Vg| of the linear sweep at :data:`PDK_GEOMETRY`, one panel per device: the
    reference with the PDK of the image (solid) and the rerun with open_pdks d658698 (dashed,
    on top)."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    with matplotlib.rc_context(ef._rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        axes = fig.subplots(1, len(_DEVICES), sharey=True)
        for ax, device in zip(axes, _DEVICES, strict=True):
            new = pdk_sweep_curves(device, SPICE_ROOT)
            old = pdk_sweep_curves(device, OLDER_PDK_ROOT)
            for k, ((vg, i_new), (vg_old, i_old)) in enumerate(zip(new, old, strict=True)):
                ax.plot(vg, i_new, color=pal[_CARRIER[device]], lw=lw,
                        label=None if k else "PDK of the image")  # fmt: skip
                ax.plot(vg_old, i_old, color=pal["text"], lw=lw, ls=STYLE["older_dash"],
                        zorder=STYLE["older_zorder"],
                        label=None if k else "open_pdks d658698")  # fmt: skip
            ax.set_yscale("log")
            ax.set_title(f"{_SHORT[device]} W10/L10", fontsize=ef.STYLE["text_pt"])
            ax.set_xlabel("|Vg| (V)")
            ax.grid(True)
        axes[0].set_ylabel("|Id| (µA)")
        fig.legend(*axes[0].get_legend_handles_labels(), loc="outside lower center",
                   ncols=2, frameon=False)  # fmt: skip
        return ef._svg(fig)


# name -> function of the palette name; each is written in both palettes by write_all.
FIGURES: dict[str, Callable[[str], bytes]] = {
    "process-cell": process_cell,
    "instance-plan": instance_plan,
    "geometries": geometries,
    "meshconv": meshconv,
    "cv-fit": cv_fit,
    "cv-validation": cv_validation,
    "cv-metric": cv_metric,
    "pfet-edge": pfet_edge,
    "fitted-stack": fitted_stack,
    "start-stack": start_stack,
    "cgg-split": cgg_split,
    "centroid": centroid,
    "pdk-sweeps": pdk_sweeps,
}


def write_all(out_dir: Path) -> None:
    """Write every figure of :data:`FIGURES` as ``<name>-light.svg`` and ``<name>-dark.svg``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, draw in FIGURES.items():
        for palette in ef.PALETTES:
            (out / f"{name}-{palette}.svg").write_bytes(draw(palette))
