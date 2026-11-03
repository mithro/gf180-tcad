# SPDX-License-Identifier: Apache-2.0
"""Every figure of the explainer pages, drawn from the one device model in a light and a dark twin.

Each figure is drawn with the deterministic SVG settings of :mod:`gf180tcad.plots` (fixed hash
salt, text kept as text, no date), sized for a phone, and written by :func:`write_all` as
``<name>-light.svg`` and ``<name>-dark.svg`` into ``docs/_generated/explained/`` at docs build
time (:func:`gf180tcad.docgen.generate`). A page embeds both, and the theme shows one.

No number is typed below except in :data:`STYLE` (sizes, colours, line widths, label offsets and
the drawing's scale factors), so a figure's data come only from the model, which reads the
committed files (tested).
"""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import NamedTuple

import matplotlib
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from gf180tcad import meshcut, plots
from gf180tcad.explain import data, idealised, model, numbers

STYLE = {
    # 6.4 in wide with 12 pt text: 10.4 px text when the SVG is scaled to a 400 px column.
    "size_in": (6.4, 4.8),
    "text_pt": 12,
    "line_width": 2.4,
    "edge_width": 0.8,
    "band_alpha": {"highlight": 0.32, "muted": 0.12},
    # One factor per drawn part, the same for every device: the oxide is too thin to see at 1.
    "scales": {"oxide": 5.0},
    # The density axis spans the drawn values with this factor of headroom at either end.
    "headroom": 30.0,
    # Region labels sit this fraction of the axis height below its top (log axis: in decades).
    "label_drop": 0.14,
    # A region narrower than this fraction of the axis width gets its label turned upright.
    "narrow": 0.12,
    "upright_deg": 90,
    # The stack diagram: the layers fill this fraction of the width, their labels start here.
    "stack_width": 0.3,
    "label_x": 0.34,
    # Room round the layer boxes, as a fraction of the width and height, so no border is clipped.
    "stack_margin": 0.01,
    # A layer thinner than this (µm) gives its thickness in nm.
    "nm_below_um": 0.1,
    # Most significant digits a label shows (fewer when they print the same value).
    "label_digits": {"thickness": 4, "doping": 3},
    # The band diagram: room above the conduction band edge and below the valence band edge,
    # as a fraction of the band gap; band names sit this far into that room.
    "band_room": 0.45,
    "band_name_at": 0.6,
    # Line labels sit this fraction of the band gap above their line, at this x (0 to 1).
    "level_label_lift": 0.02,
    "level_label_x": 0.04,
    "fill_alpha": 0.22,
    # The 2D cross-section: extents with no committed source, drawn at a chosen size (µm).
    "drawn_um": {"source and drain width": 0.6},
    # Contacts are bars this fraction of the drawing's height thick, the source and drain ones
    # this fraction of their region's width wide.
    "contact_frac": 0.025,
    "contact_width": 0.5,
    "cell_alpha": 0.55,
    "junction_width": 4.0,
    # Labels of the cross-section sit this fraction of the drawing's height off their part.
    "cell_label_gap": 0.03,
    # The reduced mesh artefact's window, outlined on the cross-section: dashed, this wide.
    "window_width": 2.4,
    "window_dash": (0, (4, 2)),
    # The junction panels: positions from (1 + pad) widths into the body to pad widths into the
    # source, on this many points; the charge axis spans the dopings with headroom.
    "junction_pad": 0.25,
    "junction_points": 20001,
    # The donor spike of the junction panels sits on the junction line: drawn this wide, and
    # stacked above it (matplotlib zorder; its lines and curves default to 2).
    "spike_width": 3.5,
    "spike_zorder": 3,
    "junction_line_zorder": 1,
    # The C-V plot: the simulated line is drawn dashed on top of the SPICE curves.
    "cv_zorder": 3,
    # The regions plot: shading opacity, and room above the highest curve for the region names.
    "region_alpha": 0.2,
    "region_headroom": 1.25,
    # The band panels: a taller figure for the two rows; depths to (1 + pad) times the deepest
    # depleted layer on this many points; the carriers of a sheet at the surface drawn as a column
    # of circles at this fraction of the depth, this far apart in energy (eV) beyond the band edge
    # they sit on, this size (pt), so the sheet does not merge with the edge's line.
    "regimes_size_in": (6.4, 6.4),
    "regime_pad": 0.5,
    "regime_points": 601,
    "sheet_frac": 0.04,
    "sheet_steps_ev": (0.12, 0.27, 0.42),
    "sheet_marker_pt": 7.0,
    # The C-V parts plot: part labels sit this fraction of the axis height off the point they
    # name; the voltage-shift arrow is this fraction of the axis
    # width long, a drawing choice (the fitted shift is too small to see at its true length).
    "part_offset": 0.14,
    "shift_arrow": 0.1,
    # The calibration limits: a taller figure for the three panels; each limit drawn as a bar this
    # wide (pt) with end ticks this tall (pt); the start and fitted markers this size (pt); room of
    # this fraction of a row above and below the two rows, and of the axis width at either end, so
    # no marker on a limit is clipped.
    "limits_size_in": (6.4, 6.4),
    "limit_width": 10.0,
    "limit_tick_pt": 16.0,
    "marker_pt": 9.0,
    # The SPICE crossings of the compare plot: hollow rings this size (pt) round the simulated ones.
    "ring_pt": 16.0,
    "row_pad": 0.6,
    "limit_margin": 0.08,
    # The gate-area figure of the corner fits, in drawing units: the drawn gate's length and
    # width, then the size drawn for |X_L| and |X_W| and for D_L and D_W.
    "area_drawn": {"gate length and width": (4.0, 2.6), "length and width offsets": (0.45, 0.3)},
    "dim_gap": 0.45,
    "dim_width_spacing": 1.6,
    "dim_label_pad": 0.06,
}

#: Unit conversions of the junction panels: cm to µm, V/cm to kV/cm.
UNITS = {"um_per_cm": 1e4, "kv_per_v": 1e-3}

# Okabe-Ito colours for the carriers and the highlight; greys for the muted parts.
PALETTES = {
    "light": {
        "background": "#ffffff",
        "text": "#222222",
        "grid": "#c8c8c8",
        # The SPICE corner band of the C-V plot: opaque, lighter than the grid lines in dark.
        "band": "#e4e4e4",
        "highlight": "#009E73",
        "highlight_oxide": "#CC79A7",
        "muted": "#8c8c8c",
        "electron": "#0072B2",
        "hole": "#D55E00",
        "intrinsic": "#555555",
    },
    "dark": {
        "background": "#131416",
        "text": "#e4e4e4",
        "grid": "#4a4a4a",
        "band": "#5e5e5e",
        "highlight": "#2fbf8f",
        "highlight_oxide": "#e09bc4",
        "muted": "#9a9a9a",
        "electron": "#56B4E9",
        "hole": "#E69F00",
        "intrinsic": "#bdbdbd",
    },
}

# The carrier a dopant gives (the majority carrier of a layer doped with it), and the other one.
_MAJORITY = {"donor": "electron", "acceptor": "hole"}
_MINORITY = {"donor": "hole", "acceptor": "electron"}
_PART_LABEL = {"gate": "gate", "oxide": "oxide", "body": "body"}


def _rc(palette: str) -> dict:
    pal = PALETTES[palette]
    return {
        **plots.RC,
        "figure.facecolor": pal["background"],
        "savefig.facecolor": pal["background"],
        "axes.facecolor": pal["background"],
        "text.color": pal["text"],
        "axes.labelcolor": pal["text"],
        "axes.edgecolor": pal["text"],
        "xtick.color": pal["text"],
        "ytick.color": pal["text"],
        "grid.color": pal["grid"],
        "legend.facecolor": pal["background"],
        "legend.edgecolor": pal["grid"],
        "font.size": STYLE["text_pt"],
    }


def _svg(fig: Figure) -> bytes:
    buf = BytesIO()
    fig.savefig(buf, format="svg", metadata=plots.METADATA)
    return buf.getvalue()


def stack_extents(dev: model.Device) -> list[tuple[model.Layer, float, float]]:
    """Each layer with its drawn extent, the silicon surface (the oxide's lower face) at 0."""
    out = []
    top = 0.0
    for layer in reversed(dev.layers[:-1]):  # oxide, then gate, upwards from the surface
        drawn = layer.thickness_um * dev.scales.get(layer.part, 1)
        out.append((layer, top - drawn, top))
        top -= drawn
    body = dev.layers[-1]
    out.reverse()
    out.append((body, 0.0, body.thickness_um * dev.scales.get(body.part, 1)))
    return out


def doping_profile(dev: model.Device, highlight: str, palette: str) -> bytes:
    """The dopant and carrier densities through the 1D stack on a log axis, with the intrinsic
    density, in thermal equilibrium: in each silicon layer the majority carrier density equals
    the doping and the minority density follows the mass-action law
    (:func:`gf180tcad.explain.idealised.mass_action`). ``highlight`` names the part shaded."""
    pal = PALETTES[palette]
    lw = STYLE["line_width"]
    edges = stack_extents(dev)
    lines = []  # (x0, x1, density, carrier, dashed)
    for layer, a, b in edges:
        if layer.dopant is None:
            continue
        minority = idealised.mass_action(dev.n_i_cm3, layer.doping_cm3)
        lines.append((a, b, layer.doping_cm3, _MAJORITY[layer.dopant], False))
        lines.append((a, b, minority, _MINORITY[layer.dopant], True))
    lo = min(d for *_, d, _c, _s in lines) / STYLE["headroom"]
    hi = max(d for *_, d, _c, _s in lines) * STYLE["headroom"]
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        ax.set_yscale("log")
        ax.set_ylim(lo, hi)
        x0, x1 = edges[0][1], edges[-1][2]
        ax.set_xlim(x0, x1)
        # Left of the surface the drawing is stretched (the oxide scale) and is not a distance
        # below the surface, so only the body carries tick labels.
        ax.set_xticks([t for t in ax.get_xticks() if 0 <= t <= x1])
        label_y = hi / (hi / lo) ** STYLE["label_drop"]
        for layer, a, b in edges:
            role = "highlight" if layer.part == highlight else "muted"
            ax.axvspan(a, b, color=pal[role], alpha=STYLE["band_alpha"][role], linewidth=0)
            ax.axvline(b, color=pal["text"], lw=STYLE["edge_width"])
            upright = (b - a) / (x1 - x0) < STYLE["narrow"]
            ax.text(
                (a + b) / 2,
                label_y,
                _PART_LABEL[layer.part],
                ha="center",
                va="top",
                rotation=STYLE["upright_deg"] if upright else 0,
                fontweight="bold" if layer.part == highlight else "normal",
            )
            if layer.dopant is not None:
                ax.plot([a, b], [dev.n_i_cm3] * 2, color=pal["intrinsic"], lw=lw, ls=":")
        for a, b, d, carrier, dashed in lines:
            ax.plot([a, b], [d] * 2, color=pal[carrier], lw=lw, ls="--" if dashed else "-")
        ax.set_xlabel("distance below the silicon surface (µm)")
        ax.set_ylabel("density (cm⁻³)")
        ax.set_title(model.exaggeration(dev.scales), fontsize=STYLE["text_pt"])
        handles = [
            Line2D([], [], color=pal["electron"], lw=lw, label="electrons"),
            Line2D([], [], color=pal["hole"], lw=lw, label="holes"),
            Line2D([], [], color=pal["intrinsic"], lw=lw, ls=":", label="intrinsic density"),
            Line2D([], [], color=pal["text"], lw=lw, label="majority (solid)"),
            Line2D([], [], color=pal["text"], lw=lw, ls="--", label="minority (dashed)"),
        ]
        fig.legend(handles=handles, loc="outside lower center", ncols=2, frameon=False)
        return _svg(fig)


def _short(v: float, unit: str, most: int) -> str:
    """``v`` with the fewest significant digits (up to ``most``) that print the same value as
    ``most`` digits do: 0.2 µm, not 0.2000 µm (:func:`gf180tcad.explain.numbers.shortest`)."""
    return numbers.shortest(v, unit, most)


def _thickness(layer: model.Layer) -> str:
    most = STYLE["label_digits"]["thickness"]
    if layer.thickness_um < STYLE["nm_below_um"]:
        return _short(layer.thickness_um * model.UNITS["nm_per_um"], "nm", most)
    return _short(layer.thickness_um, "µm", most)


_STACK_NAME = {"gate": "gate", "oxide": "gate oxide", "body": "body"}


def stack_1d_figure(dev: model.Device, highlight: tuple[str, ...], palette: str):
    """The 1D stack as layers, gate on top, each labelled with its material, its thickness and
    its doping from the model. The parts in ``highlight`` are shaded (a silicon layer in its
    majority carrier's colour), the rest muted. Drawn at
    the model's scale factors, stated in the title; there is no distance axis, because the
    drawing is stretched, so each layer carries its own thickness."""
    pal = PALETTES[palette]
    edges = stack_extents(dev)
    width = STYLE["stack_width"]
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        ax.set_axis_off()
        ax.set_xlim(-STYLE["stack_margin"], 1)
        top, bottom = edges[0][1], edges[-1][2]
        pad = (bottom - top) * STYLE["stack_margin"]
        ax.set_ylim(bottom + pad, top - pad)  # depth grows downwards
        for layer, a, b in edges:
            role = "highlight" if layer.part in highlight else "muted"
            # A highlighted silicon layer takes its majority carrier's colour (n-type: electrons,
            # p-type: holes), as in the band diagram; the oxide its own.
            colour = pal.get(f"{role}_{layer.part}", pal[role])
            if role == "highlight" and layer.dopant is not None:
                colour = pal[_MAJORITY[layer.dopant]]
            ax.fill_between(
                [0, width],
                a,
                b,
                color=colour,
                alpha=STYLE["band_alpha"][role],
                linewidth=0,
            )
            ax.plot([0, width, width, 0, 0], [a, a, b, b, a], color=pal["text"],
                    lw=STYLE["edge_width"])  # fmt: skip
            lines = [f"{_STACK_NAME[layer.part]}: {layer.material}, {_thickness(layer)}"]
            if layer.dopant is not None:
                dose = _short(layer.doping_cm3, "cm⁻³", STYLE["label_digits"]["doping"])
                lines.append(f"{dose} {layer.dopant}s")
            ax.text(
                STYLE["label_x"],
                (a + b) / 2,
                "\n".join(lines),
                ha="left",
                va="center",
                fontweight="bold" if layer.part in highlight else "normal",
            )
        ax.set_title(model.exaggeration(dev.scales), fontsize=STYLE["text_pt"])
        return fig


def stack_1d(dev: model.Device, highlight: tuple[str, ...], palette: str) -> bytes:
    """:func:`stack_1d_figure` as SVG bytes."""
    with matplotlib.rc_context(_rc(palette)):
        return _svg(stack_1d_figure(dev, highlight, palette))


def band_levels(dev: model.Device, part: str) -> dict[str, float]:
    """The flat-band energy levels of the silicon layer ``part`` (eV, from the middle of the gap,
    taken as the intrinsic level): the band edges half the :term:`band gap` above and below it
    (``band_gap_si``, a textbook value), and the :term:`Fermi level` of Boltzmann statistics
    (:func:`gf180tcad.explain.idealised.boltzmann_fermi`) from the layer's electron density,
    the doping for donors or the mass-action minority density for acceptors."""
    layer = dev.layer(part)
    if layer.dopant is None:
        raise ValueError(f"{part} is not a silicon layer")
    half = numbers.value("band_gap_si") / 2
    n = layer.doping_cm3
    if layer.dopant == "acceptor":
        n = idealised.mass_action(dev.n_i_cm3, layer.doping_cm3)
    fermi = idealised.boltzmann_fermi(n, dev.n_i_cm3, dev.vt_v)
    return {"conduction": half, "valence": -half, "intrinsic": 0, "fermi": fermi}


_DOPED = {"donor": "n-type", "acceptor": "p-type"}


def band_flat(dev: model.Device, parts: tuple[str, ...], palette: str) -> bytes:
    """One flat band diagram per silicon layer in ``parts``, side by side on one energy axis:
    the :term:`conduction band` (shaded above its edge), the :term:`valence band` (shaded below
    its edge), the middle of the gap (dotted) and the Fermi level (:func:`band_levels`)."""
    pal = PALETTES[palette]
    lw = STYLE["line_width"]
    gap = numbers.value("band_gap_si")
    room = gap * STYLE["band_room"]
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        axes = fig.subplots(1, len(parts), sharey=True)
        for ax, part in zip(axes, parts, strict=True):
            lv = band_levels(dev, part)
            top, bottom = lv["conduction"] + room, lv["valence"] - room
            ax.set_xlim(0, 1)
            ax.set_ylim(bottom, top)
            ax.set_xticks([])
            ax.axhspan(
                lv["conduction"], top, color=pal["electron"], alpha=STYLE["fill_alpha"], lw=0
            )
            ax.axhspan(bottom, lv["valence"], color=pal["hole"], alpha=STYLE["fill_alpha"], lw=0)
            ax.axhline(lv["conduction"], color=pal["electron"], lw=lw)
            ax.axhline(lv["valence"], color=pal["hole"], lw=lw)
            ax.axhline(lv["intrinsic"], color=pal["intrinsic"], lw=lw, ls=":")
            ax.axhline(lv["fermi"], color=pal["highlight"], lw=lw, ls="--")
            mid = (ax.get_xlim()[0] + ax.get_xlim()[1]) / 2
            at = STYLE["band_name_at"] * room
            ax.text(mid, lv["conduction"] + at, "conduction band", ha="center", va="center")
            ax.text(mid, lv["valence"] - at, "valence band", ha="center", va="center")
            lift = gap * STYLE["level_label_lift"]
            x = STYLE["level_label_x"]
            ax.text(x, lv["fermi"] + lift, "Fermi level", ha="left", va="bottom",
                    color=pal["highlight"], fontweight="bold")  # fmt: skip
            ax.text(x, lv["intrinsic"] - lift, "middle of the gap", ha="left", va="top",
                    color=pal["intrinsic"])  # fmt: skip
            layer = dev.layer(part)
            ax.set_title(f"{_DOPED[layer.dopant]} {_PART_LABEL[part]}", fontsize=STYLE["text_pt"])
        axes[0].set_ylabel("energy from the middle of the gap (eV)")
        return _svg(fig)


def _silicon_doping(palette: str) -> bytes:
    dev = model.device("nfet_05v0", "calibrated", scales=STYLE["scales"])
    return doping_profile(dev, "body", palette)


def _oxide_stack(palette: str) -> bytes:
    dev = model.device("nfet_05v0", "calibrated", scales=STYLE["scales"])
    return stack_1d(dev, ("gate", "oxide"), palette)


def _calibration_stack(palette: str) -> bytes:
    # The calibration page: the two layers the fit changes, the oxide and the body, highlighted.
    dev = model.device("nfet_05v0", "calibrated", scales=STYLE["scales"])
    return stack_1d(dev, ("oxide", "body"), palette)


def _bands_stack(palette: str) -> bytes:
    dev = model.device("nfet_05v0", "calibrated", scales=STYLE["scales"])
    return stack_1d(dev, ("gate", "body"), palette)


def _bands_flat(palette: str) -> bytes:
    dev = model.device("nfet_05v0", "calibrated", scales=STYLE["scales"])
    return band_flat(dev, ("gate", "body"), palette)


class Box(NamedTuple):
    """A drawn rectangle (µm): x from ``x0`` to ``x1``, depth from ``y0`` to ``y1``."""

    x0: float
    x1: float
    y0: float
    y1: float


def cell_extents(c: model.Cell) -> dict[str, Box]:
    """The drawn extent ``(x0, x1, y0, y1)`` of each part of the 2D cell (µm), the silicon surface
    at y = 0 and depth growing downwards, the gate centred on x = 0. The oxide is drawn at its
    scale factor; the source and drain width is the drawn extent ``c.drawn``."""
    half = c.l_um / 2
    sd = c.drawn["source and drain width"]
    t_ox = c.t_ox_um * c.scales.get("oxide", 1)
    return {
        "gate": Box(-half, half, -(t_ox + c.poly_um), -t_ox),
        "oxide": Box(-half, half, -t_ox, 0.0),
        "source": Box(-half - sd, -half, 0.0, c.xj_um),
        "drain": Box(half, half + sd, 0.0, c.xj_um),
        "body": Box(-half - sd, half + sd, 0.0, c.body_um),
    }


_CELL_LABEL = {"gate": "gate", "oxide": "gate oxide", "source": "source", "drain": "drain"}
_BODY_LABEL = {"n": "body", "p": "n-well (body)"}


def window_box(c: model.Cell) -> Box:
    """The window that :mod:`gf180tcad.meshcut` cuts with its default rule, in the drawn
    coordinates of :func:`cell_extents`: :data:`gf180tcad.meshcut.WINDOW_KX` gate lengths
    either side of the gate, from the drawn poly top down to
    :data:`gf180tcad.meshcut.WINDOW_DEPTH_UM` below the silicon surface."""
    gate = cell_extents(c)["gate"]
    margin = meshcut.WINDOW_KX * c.l_um
    return Box(gate.x0 - margin, gate.x1 + margin, gate.y0, meshcut.WINDOW_DEPTH_UM)


def cross_section_figure(
    c: model.Cell, highlight: tuple[str, ...], palette: str, window: Box | None = None
):
    """The 2D cell cut along its length: gate, gate oxide, source, drain and body, each filled
    with its carrier's colour (n-type: electrons, p-type: holes; the oxide its own) and labelled
    on the part, and the contacts of ``c.contacts`` as dark bars. With ``highlight``, the parts
    named there keep their colour and the rest are muted; ``"junction"`` draws the boundary of
    the source and the drain with the body in the highlight colour. With ``window``, that box
    is outlined, dashed, in the highlight colour and labelled "mesh window"."""
    pal = PALETTES[palette]
    ext = cell_extents(c)
    carrier = {"donor": "electron", "acceptor": "hole"}
    fill = {
        "gate": pal[carrier[c.sd_dopant]],
        "oxide": pal["highlight_oxide"],
        "source": pal[carrier[c.sd_dopant]],
        "drain": pal[carrier[c.sd_dopant]],
        "body": pal[carrier[c.body_dopant]],
    }
    x0, x1 = ext["body"].x0, ext["body"].x1
    top, bottom = ext["gate"].y0, ext["body"].y1
    height = bottom - top
    bar = height * STYLE["contact_frac"]
    gap = height * STYLE["cell_label_gap"]
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        ax.set_axis_off()
        pad = (x1 - x0) * STYLE["stack_margin"]
        ax.set_xlim(x0 - pad, x1 + pad)
        ax.set_ylim(bottom + bar + gap * 2, top - bar - gap * 2)  # depth grows downwards
        for part in ("body", "source", "drain", "oxide", "gate"):
            a, b, y0, y1 = ext[part]
            muted = bool(highlight) and part not in highlight
            colour = pal["muted"] if muted else fill[part]
            alpha = STYLE["band_alpha"]["muted"] if muted else STYLE["cell_alpha"]
            # An opaque ground first, so a part drawn over another keeps its own tint.
            ax.fill_between([a, b], y0, y1, color=pal["background"], linewidth=0)
            ax.fill_between([a, b], y0, y1, color=colour, alpha=alpha, linewidth=0)
            ax.plot(
                [a, b, b, a, a], [y0, y0, y1, y1, y0], color=pal["text"], lw=STYLE["edge_width"]
            )
        if "junction" in highlight:
            for side in ("source", "drain"):
                a, b, _y0, y1 = ext[side]
                edge_x = b if side == "source" else a
                far_x = a if side == "source" else b
                ax.plot([far_x, edge_x, edge_x], [y1, y1, 0.0], color=pal["highlight"],
                        lw=STYLE["junction_width"])  # fmt: skip
        labels = {
            "gate": ((ext["gate"].x0 + ext["gate"].x1) / 2, (ext["gate"].y0 + ext["gate"].y1) / 2),
            "source": ((ext["source"].x0 + ext["source"].x1) / 2, ext["source"].y1 / 2),
            "drain": ((ext["drain"].x0 + ext["drain"].x1) / 2, ext["drain"].y1 / 2),
        }
        for part, (x, y) in labels.items():
            bold = "bold" if part in highlight else "normal"
            ax.text(x, y, _CELL_LABEL[part], ha="center", va="center", fontweight=bold)
        body_y = (ext["source"].y1 + ext["body"].y1) / 2
        ax.text(0.0, body_y, _BODY_LABEL[c.polarity], ha="center", va="center",
                fontweight="bold" if "body" in highlight else "normal")  # fmt: skip
        ox = ext["oxide"]
        ax.annotate("gate oxide", xy=(ox.x1, (ox.y0 + ox.y1) / 2),
                    xytext=(ext["drain"].x1 - pad, top + gap), ha="right", va="center",
                    arrowprops={"arrowstyle": "-", "color": pal["text"], "lw": STYLE["edge_width"]},
                    fontweight="bold" if "oxide" in highlight else "normal")  # fmt: skip
        if "junction" in highlight:
            a, b, _y0, y1 = ext["drain"]
            ax.text((a + b) / 2, y1 + gap, "junction", ha="center", va="top",
                    color=pal["highlight"], fontweight="bold")  # fmt: skip
        width = ext["source"].x1 - ext["source"].x0
        cw = width * STYLE["contact_width"]
        bars = {
            "gate": (ext["gate"].x0, ext["gate"].x1, top - bar, top),
            "body": (x0, x1, bottom, bottom + bar),
        }
        for side in ("source", "drain"):
            mid = (ext[side][0] + ext[side][1]) / 2
            bars[side] = (mid - cw / 2, mid + cw / 2, -bar, 0.0)
        for name in c.contacts:
            a, b, y0, y1 = bars[name]
            ax.fill_between([a, b], y0, y1, color=pal["text"], linewidth=0)
            if name in ("source", "drain"):
                ax.text((a + b) / 2, y0 - gap / 2, "contact", ha="center", va="bottom")
        if window is not None:
            a, b, y0, y1 = window
            ax.plot([a, b, b, a, a], [y0, y0, y1, y1, y0], color=pal["highlight"],
                    lw=STYLE["window_width"], ls=STYLE["window_dash"])  # fmt: skip
            # Left of the box, level with the "gate oxide" label on the right: clear of the
            # parts' boundaries.
            ax.text(a - pad / 2, top + gap, "mesh window", ha="right", va="center",
                    color=pal["highlight"], fontweight="bold")  # fmt: skip
        statement = model.exaggeration(c.scales, c.drawn).replace(". ", ".\n")
        ax.set_title(statement, fontsize=STYLE["text_pt"])
        return fig


def cross_section(
    c: model.Cell, highlight: tuple[str, ...], palette: str, window: Box | None = None
) -> bytes:
    """:func:`cross_section_figure` as SVG bytes."""
    with matplotlib.rc_context(_rc(palette)):
        return _svg(cross_section_figure(c, highlight, palette, window))


_JUNCTION_PANELS = ("charge", "field", "potential")


def junction_panels(palette: str) -> bytes:
    """The charge, field and potential of the idealised abrupt junction between the nfet's
    source and its body (:func:`gf180tcad.explain.idealised.abrupt_junction`), from the
    registry's dopings, built-in potential and constants, against the distance from the
    junction: negative in the source, positive in the body."""
    pal = PALETTES[palette]
    lw = STYLE["line_width"]
    n_a, n_d = numbers.value("n_ch_nfet_cal"), numbers.value("sd_peak_nfet")
    vbi = numbers.value("vbi_nfet")
    consts = (numbers.value("eps_si_tcad"), numbers.value("eps0_tcad"), numbers.value("q_tcad"))
    w = idealised.depletion_width(n_a, n_d, vbi, *consts)
    pad = STYLE["junction_pad"]
    # x > 0 is the body (the p side): the formula puts the n side at x < 0.
    x = np.linspace(-pad * w, (1 + pad) * w, STYLE["junction_points"])
    prof = idealised.abrupt_junction(x, n_a, n_d, vbi, *consts)
    x_um = x * UNITS["um_per_cm"]
    x_p = w * n_d / (n_a + n_d) * UNITS["um_per_cm"]
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        ax_q, ax_e, ax_v = fig.subplots(len(_JUNCTION_PANELS), 1, sharex=True)
        charge = prof["charge_cm3"]
        pos = np.where(charge > 0, charge, np.nan)
        neg = np.where(charge < 0, -charge, np.nan)
        ax_q.set_yscale("log")
        ax_q.plot(x_um, pos, color=pal["electron"], lw=lw, label="donors (+)")
        ax_q.plot(x_um, neg, color=pal["hole"], lw=lw, label="acceptors (−)")
        ax_q.vlines(
            0.0,
            n_a,
            n_d,
            color=pal["electron"],
            lw=STYLE["spike_width"],
            zorder=STYLE["spike_zorder"],
        )
        ax_q.set_ylim(n_a / STYLE["headroom"], n_d * STYLE["headroom"])
        ax_q.set_ylabel("ions (cm⁻³)")
        ax_q.legend(loc="upper right", frameon=False, ncols=2)
        ax_e.plot(x_um, prof["field_v_per_cm"] * UNITS["kv_per_v"], color=pal["highlight"], lw=lw)
        ax_e.set_ylabel("field (kV/cm)")
        ax_v.plot(x_um, prof["potential_v"], color=pal["highlight"], lw=lw)
        ax_v.set_ylabel("potential (V)")
        ax_v.set_xlabel("distance from the junction (µm): source < 0 < body")
        for ax in (ax_q, ax_e, ax_v):
            ax.axvline(
                0.0, color=pal["text"], lw=STYLE["edge_width"], zorder=STYLE["junction_line_zorder"]
            )
            ax.axvline(x_p, color=pal["intrinsic"], lw=STYLE["edge_width"], ls=":")
        ax_v.text(x_p, vbi, "depletion edge ", ha="right", va="top", color=pal["intrinsic"])
        return _svg(fig)


def _parts_cell(palette: str) -> bytes:
    c = model.cell(
        "nfet_05v0", "calibrated", "w10p0_l0p70", scales=STYLE["scales"], drawn=STYLE["drawn_um"]
    )
    return cross_section(c, (), palette)


def _mesh_window(palette: str) -> bytes:
    c = model.cell(
        "nfet_05v0", "calibrated", "w10p0_l0p60", scales=STYLE["scales"], drawn=STYLE["drawn_um"]
    )
    return cross_section(c, (), palette, window=window_box(c))


def _junction_cell(palette: str) -> bytes:
    c = model.cell(
        "nfet_05v0", "calibrated", "w10p0_l0p70", scales=STYLE["scales"], drawn=STYLE["drawn_um"]
    )
    return cross_section(c, ("junction",), palette)


# The committed SPICE reference tree, and its typical corner (the line; all the corners give
# the band).
SPICE_ROOT = numbers.ROOT / "results" / "spice"
TYPICAL = "typical"


def cv_curves(
    device: str,
    params: str,
    gid: str,
    spice_root: Path = SPICE_ROOT,
    tcad_root: Path = numbers.ROOT / "results" / "tcad",
) -> dict[str, np.ndarray]:
    """The curves of :func:`cv_against_spice`, read by the readers the results pages use
    (:mod:`gf180tcad.explain.data`): the simulated gate capacitance of ``gid`` from the committed
    1D C per area at ``params`` with the BSIM4 bookkeeping, and the :term:`SPICE` :term:`cv` sweep at
    the :term:`typical corner` with the lowest and highest of the five :term:`corners <corner>` at
    each voltage. Keys ``u``,
    ``tcad``, ``u_spice``, ``spice_tt``, ``spice_lo``, ``spice_hi`` (V and fF). The trees are
    the committed ones unless ``spice_root`` and ``tcad_root`` name others."""
    from gf180tcad.devices import CORNERS, DEVICES, geometry_id

    dev = DEVICES[device]
    (geom,) = [g for g in dev.geometries if geometry_id(g) == gid]
    moscap, proc = data.read_moscap(tcad_root, device, params)
    u, _intrinsic, _parasitic, total = data.tcad_cgg(moscap, geom, proc, dev.polarity)
    spice = {}
    for corner in CORNERS:
        cols = data.spice_columns(spice_root, "ngspice", corner, device, gid, "cv")
        spice[corner] = data.spice_cv(cols, dev.polarity)
    u_s, tt = spice[TYPICAL]
    for corner, (uc, _c) in spice.items():
        if not np.array_equal(uc, u_s):
            raise ValueError(f"{device} {gid} cv: the {corner} grid differs from {TYPICAL}")
    stack = np.array([c for _u, c in spice.values()])
    return {"u": u, "tcad": total, "u_spice": u_s, "spice_tt": tt,
            "spice_lo": stack.min(axis=0), "spice_hi": stack.max(axis=0)}  # fmt: skip


def cv_against_spice(device: str, params: str, gid: str, palette: str) -> bytes:
    """The gate capacitance against the gate voltage of one geometry: the :term:`SPICE` model at
    the :term:`typical corner` (solid) inside the band of its five :term:`corners <corner>`, and the simulated curve of the
    committed 1D stack at ``params`` (dashed, on top), from :func:`cv_curves`."""
    pal = PALETTES[palette]
    lw = STYLE["line_width"]
    c = cv_curves(device, params, gid)
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        ax.fill_between(c["u_spice"], c["spice_lo"], c["spice_hi"], color=pal["band"],
                        linewidth=0, label="SPICE, all corners")  # fmt: skip
        ax.plot(c["u_spice"], c["spice_tt"], color=pal["text"], lw=lw, label="SPICE, typical")
        ax.plot(c["u"], c["tcad"], color=pal["highlight"], lw=lw, ls="--",
                zorder=STYLE["cv_zorder"], label="simulated, fitted")  # fmt: skip
        ax.set_ylim(bottom=0)
        ax.grid(True)
        ax.set_xlabel("gate voltage (V)")
        ax.set_ylabel("gate capacitance (fF)")
        fig.legend(loc="outside lower center", ncols=2, frameon=False)
        return _svg(fig)


def _moscap_cell(palette: str) -> bytes:
    c = model.cell(
        "nfet_05v0", "calibrated", "w10p0_l0p70", scales=STYLE["scales"], drawn=STYLE["drawn_um"]
    )
    return cross_section(c, ("gate", "oxide", "body"), palette)


def _moscap_cv(palette: str) -> bytes:
    return cv_against_spice("nfet_05v0", "calibrated", "w10p0_l10p00", palette)


# The regions page (accumulation-depletion-inversion.md): the calibrated nfet at the longest
# calibration gate, the geometry of the MOS capacitor page's C-V figure.
REGIONS_DEVICE, REGIONS_GEOMETRY = "nfet_05v0", "w10p0_l10p00"
#: The three regions of the C-V curve, by rising gate voltage of the nfet, and the colour of
#: each: the carrier that gathers at the surface, none (muted) in depletion.
REGIONS = ("accumulation", "depletion", "inversion")
_REGION_COLOUR = {"accumulation": "hole", "depletion": "muted", "inversion": "electron"}


def region_edges() -> tuple[float, float]:
    """The two gate voltages (V) where the calibration marks the end of accumulation and the start
    of inversion on the :term:`SPICE` curve at the :term:`typical corner`: ``u_fb`` and ``u_t``
    of the nfet result file's ``spice_regions`` (registry entries ``u_fb_l10``, ``u_t_l10``;
    the nfet's u is its gate voltage)."""
    return numbers.value("u_fb_l10"), numbers.value("u_t_l10")


def cv_regions_figure(palette: str):
    """The matplotlib figure of :func:`cv_regions`, for the tests to read its spans."""
    from gf180tcad.devices import DEVICES

    if DEVICES[REGIONS_DEVICE].polarity != 1:
        raise ValueError(f"{REGIONS_DEVICE}: u is not the gate voltage")
    pal = PALETTES[palette]
    lw = STYLE["line_width"]
    c = cv_curves(REGIONS_DEVICE, "calibrated", REGIONS_GEOMETRY)
    lo, hi = region_edges()
    u = c["u_spice"]
    spans = dict(zip(REGIONS, ((u[0], lo), (lo, hi), (hi, u[-1])), strict=True))
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        ax.set_xlim(u[0], u[-1])
        top = max(c["spice_tt"].max(), c["tcad"].max()) * STYLE["region_headroom"]
        ax.set_ylim(0, top)
        for name, (a, b) in spans.items():
            ax.axvspan(a, b, color=pal[_REGION_COLOUR[name]], alpha=STYLE["region_alpha"], lw=0)
            narrow = (b - a) < STYLE["narrow"] * (u[-1] - u[0])
            ax.text((a + b) / 2, top * (1 - STYLE["label_drop"] / 2), name, ha="center",
                    va="top" if narrow else "center", rotation=STYLE["upright_deg"] if narrow else 0,
                    color=pal["text"], fontweight="bold")  # fmt: skip
        ax.plot(u, c["spice_tt"], color=pal["text"], lw=lw, label="SPICE, typical")
        ax.plot(c["u"], c["tcad"], color=pal["highlight"], lw=lw, ls="--",
                zorder=STYLE["cv_zorder"], label="simulated, fitted")  # fmt: skip
        ax.set_xlabel("gate voltage (V)")
        ax.set_ylabel("gate capacitance (fF)")
        fig.legend(loc="outside lower center", ncols=2, frameon=False)
        return fig


def cv_regions(palette: str) -> bytes:
    """The gate capacitance of the nfet at ``w10p0_l10p00`` against the gate voltage, the
    :term:`SPICE` curve at the :term:`typical corner` (solid) and the fitted simulation (dashed),
    with the three regions shaded between the calibration's marks (:func:`region_edges`)."""
    # Saved inside the palette's rc context: the SVG settings (text as text, hash salt) apply.
    with matplotlib.rc_context(_rc(palette)):
        return _svg(cv_regions_figure(palette))


#: The four states of the band panels, by rising gate voltage, and the surface bending of each
#: in units of ψ_B, the body's Fermi-level distance below the middle of the gap: none at flat
#: band, and none at accumulation, where the drawing puts the extra holes in a sheet of no
#: thickness and keeps the bands flat (a drawing choice: the depletion approximation covers
#: depletion and inversion only, and the real bands bend up by a few thermal voltages); ψ_B for
#: depletion (the surface at the middle of the gap); 2·ψ_B at the onset of strong inversion.
REGIMES = {"accumulation": 0, "flat band": 0, "depletion": 1, "inversion": 2}
_SHEET = {"accumulation": "hole", "inversion": "electron"}
_SHEET_LABEL = {"hole": "holes at the surface", "electron": "electrons at the surface"}


def band_regimes_figure(palette: str):
    """The matplotlib figure of :func:`band_regimes`, for the tests to read its lines."""
    pal = PALETTES[palette]
    lw = STYLE["line_width"]
    n_a, n_i, vt = (numbers.value(k) for k in ("n_ch_nfet_cal", "n_i_tcad", "vt_tcad"))
    consts = (numbers.value("eps_si_tcad"), numbers.value("eps0_tcad"), numbers.value("q_tcad"))
    half = numbers.value("band_gap_si") / 2
    psi_b = idealised.bulk_potential(n_a, n_i, vt)
    deepest = max(REGIMES.values()) * psi_b
    w_max = idealised.depletion_depth(deepest, n_a, *consts)
    x = np.linspace(0, (1 + STYLE["regime_pad"]) * w_max, STYLE["regime_points"])
    x_um = x * UNITS["um_per_cm"]
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["regimes_size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        axes = fig.subplots(2, 2, sharex=True, sharey=True).ravel()
        for ax, (name, k) in zip(axes, REGIMES.items(), strict=True):
            psi_s = k * psi_b
            mid = psi_b - idealised.surface_bending(x, psi_s, n_a, *consts)
            if psi_s > 0:
                w = idealised.depletion_depth(psi_s, n_a, *consts) * UNITS["um_per_cm"]
                ax.axvspan(0, w, color=pal["muted"], alpha=STYLE["fill_alpha"], lw=0,
                           label="no free carriers")  # fmt: skip
            ax.plot(x_um, mid + half, color=pal["electron"], lw=lw, label="conduction band edge")
            ax.plot(x_um, mid, color=pal["intrinsic"], lw=lw, ls=":", label="middle of the gap")
            ax.plot(x_um, mid - half, color=pal["hole"], lw=lw, label="valence band edge")
            ax.axhline(0, color=pal["highlight"], lw=lw, ls="--", label="Fermi level")
            if name in _SHEET:
                carrier = _SHEET[name]
                edge = mid + half if carrier == "electron" else mid - half
                # Holes below the valence band edge, electrons above the conduction band edge.
                sign = 1 if carrier == "electron" else -1
                steps = np.asarray(STYLE["sheet_steps_ev"])
                xs = np.full(len(steps), STYLE["sheet_frac"] * x_um[-1])
                ax.plot(xs, edge[0] + sign * steps, ls="none", marker="o",
                        ms=STYLE["sheet_marker_pt"], mfc=pal[carrier], mec=pal["text"],
                        label=_SHEET_LABEL[carrier])  # fmt: skip
            ax.set_title(name, fontsize=STYLE["text_pt"])
            ax.set_xlim(x_um[0], x_um[-1])
        for ax in axes[2:]:
            ax.set_xlabel("depth below the oxide (µm)")
        for ax in axes[::2]:
            ax.set_ylabel("energy (eV)")
        handles = {}
        for ax in axes:
            for h, lab in zip(*ax.get_legend_handles_labels(), strict=True):
                handles.setdefault(lab, h)
        fig.legend(handles.values(), handles.keys(), loc="outside lower center", ncols=2,
                   frameon=False)  # fmt: skip
        return fig


def band_regimes(palette: str) -> bytes:
    """The bands of the nfet's p-type body against the depth below the oxide, in the four states
    of :data:`REGIMES`, for the idealised stack in the :term:`depletion approximation`
    (:func:`gf180tcad.explain.idealised.surface_bending`): the band edges, the middle of the gap
    and the :term:`Fermi level` (the zero of energy), from the calibrated body doping, the
    simulations' constants and the textbook band gap."""
    with matplotlib.rc_context(_rc(palette)):
        return _svg(band_regimes_figure(palette))


# The C-V curve page (cv-curve.md): the same nfet geometry as the regions page.
#: The curves of the C-V parts plot: the SPICE typical curve and the simulated stack at the
#: calibration's start values and at its fitted values, by their legend labels.
CV_PARTS_LINES = {
    "spice": "SPICE, typical",
    "start": "simulated, start values",
    "calibrated": "simulated, fitted",
}
#: The parts of the C-V curve and the label of each, the parameter that sets it: the two flat
#: parts, the dip and the position on the voltage axis.
CV_PARTS = {
    "accumulation": "oxide thickness",
    "dip": "body doping",
    "inversion": "oxide thickness\nand gate doping",
    "position": "voltage shift",
}


def cv_parts_figure(palette: str):
    """The matplotlib figure of :func:`cv_parts`, for the tests to read its lines and labels."""
    from gf180tcad.devices import DEVICES

    if DEVICES[REGIONS_DEVICE].polarity != 1:
        raise ValueError(f"{REGIONS_DEVICE}: u is not the gate voltage")
    pal = PALETTES[palette]
    lw = STYLE["line_width"]
    fitted = cv_curves(REGIONS_DEVICE, "calibrated", REGIONS_GEOMETRY)
    start = cv_curves(REGIONS_DEVICE, "start", REGIONS_GEOMETRY)
    u, tt = fitted["u_spice"], fitted["spice_tt"]
    lo, hi = region_edges()
    u_min, c_min = numbers.value("u_min_l10"), numbers.value("c_min_l10")
    u_dep = numbers.value("u_dep_spice_l10")
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        ax.set_xlim(u[0], u[-1])
        top = max(tt.max(), fitted["tcad"].max(), start["tcad"].max()) * STYLE["region_headroom"]
        ax.set_ylim(0, top)
        ax.grid(True)
        ax.plot(u, tt, color=pal["text"], lw=lw, label=CV_PARTS_LINES["spice"])
        ax.plot(start["u"], start["tcad"], color=pal["muted"], lw=lw, ls=":",
                label=CV_PARTS_LINES["start"])  # fmt: skip
        ax.plot(fitted["u"], fitted["tcad"], color=pal["highlight"], lw=lw, ls="--",
                zorder=STYLE["cv_zorder"], label=CV_PARTS_LINES["calibrated"])  # fmt: skip
        gap = top * STYLE["part_offset"]
        arrow = {"arrowstyle": "-", "color": pal["text"], "lw": STYLE["edge_width"]}
        # The flat parts: midway between the axis end and the calibration's mark; the
        # accumulation label above the curve, clear of the shift label, the two-line inversion
        # label below it, inside the axes.
        flats = (("accumulation", (u[0] + lo) / 2, 1, "bottom"),
                 ("inversion", (hi + u[-1]) / 2, -1, "top"))  # fmt: skip
        for part, x, side, va in flats:
            y = float(np.interp(x, u, tt))
            ax.annotate(CV_PARTS[part], xy=(x, y), xytext=(x, y + side * gap), ha="center",
                        va=va, arrowprops=arrow, fontweight="bold")  # fmt: skip
        ax.annotate(CV_PARTS["dip"], xy=(u_min, c_min), xytext=(u_min, c_min - gap),
                    ha="center", va="top", arrowprops=arrow, fontweight="bold")  # fmt: skip
        # The shift: an arrow centred on the SPICE curve's falling-side crossing, its one head
        # towards more positive gate voltages (the way the shift moves the simulated curve),
        # labelled to its left.
        y = (c_min + tt[0]) / 2
        half = (u[-1] - u[0]) * STYLE["shift_arrow"] / 2
        ax.annotate("", xy=(u_dep + half, y), xytext=(u_dep - half, y),
                    arrowprops={**arrow, "arrowstyle": "->"})  # fmt: skip
        ax.annotate(CV_PARTS["position"], xy=(u_dep, y), xytext=(u_dep - half, y), ha="right",
                    va="center", fontweight="bold")  # fmt: skip
        ax.set_xlabel("gate voltage (V)")
        ax.set_ylabel("gate capacitance (fF)")
        fig.legend(loc="outside lower center", ncols=2, frameon=False)
        return fig


def cv_parts(palette: str) -> bytes:
    """The gate capacitance of the nfet at ``w10p0_l10p00`` against the gate voltage: the
    :term:`SPICE` curve at the :term:`typical corner` and the simulated stack at the
    calibration's start and fitted values, each part of the curve labelled with the parameter
    that sets it (:data:`CV_PARTS`)."""
    with matplotlib.rc_context(_rc(palette)):
        return _svg(cv_parts_figure(palette))


# The calibration page (calibration.md): the fitted numbers of both transistors within their limits.
#: The fitted numbers drawn on a log axis (a doping spans powers of ten).
LOG_TUNABLES = ("n_ch_cm3",)


def calibration_limits_figure(palette: str):
    """The matplotlib figure of :func:`calibration_limits`, for the tests to read its lines."""
    pal = PALETTES[palette]
    devices = list(numbers.FITS)
    fits = {d: numbers.fits(d) for d in devices}
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["limits_size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        axes = fig.subplots(len(numbers.TUNABLES), 1)
        for i, (ax, (name, (words, unit, _most))) in enumerate(
            zip(axes, numbers.TUNABLES.items(), strict=True)
        ):
            if name in LOG_TUNABLES:
                ax.set_xscale("log")
            for row, device in enumerate(devices):
                (f,) = [f for f in fits[device] if f.name == name]
                ax.plot([f.lower, f.upper], [row, row], color=pal["band"], lw=STYLE["limit_width"],
                        solid_capstyle="butt", label="limits" if row == 0 else None)  # fmt: skip
                ax.plot([f.lower, f.upper], [row, row], ls="none", marker="|", color=pal["text"],
                        ms=STYLE["limit_tick_pt"], mew=STYLE["edge_width"] * 2)  # fmt: skip
                ax.plot([f.start], [row], ls="none", marker="o", ms=STYLE["marker_pt"], mfc=pal["background"],
                        mec=pal["text"], mew=STYLE["edge_width"] * 2, label="start" if row == 0 else None)  # fmt: skip
                ax.plot([f.fitted], [row], ls="none", marker="D", ms=STYLE["marker_pt"], color=pal["highlight"],
                        mec=pal["text"], mew=STYLE["edge_width"], label="fitted" if row == 0 else None)  # fmt: skip
            ax.set_yticks(range(len(devices)), [d.split("_")[0] for d in devices])
            ax.set_ylim(-STYLE["row_pad"], len(devices) - 1 + STYLE["row_pad"])
            ax.margins(x=STYLE["limit_margin"])
            ax.set_xlabel(f"{words.lower()} ({unit})" if unit else words.lower())
            ax.grid(True, axis="x")
            if i == 0:
                handles, labels = ax.get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside lower center", ncols=len(labels), frameon=False)
        return fig


def calibration_limits(palette: str) -> bytes:
    """Each fitted number of the nfet and the pfet (:data:`gf180tcad.explain.numbers.TUNABLES`)
    on its own axis: a bar from its lower to its upper limit, its start (open circle) and its
    fitted value (filled diamond), read from the calibration result files
    (:func:`gf180tcad.explain.numbers.fits`)."""
    with matplotlib.rc_context(_rc(palette)):
        return _svg(calibration_limits_figure(palette))


#: The legend words of the crossing marks of :func:`calibration_compare`, by curve.
COMPARE_MARKS = {"spice": "SPICE crossings", "tcad": "simulated crossings"}


def calibration_compare_figure(palette: str):
    """The matplotlib figure of :func:`calibration_compare`, for the tests to read it."""
    from gf180tcad.devices import DEVICES

    if DEVICES[REGIONS_DEVICE].polarity != 1:
        raise ValueError(f"{REGIONS_DEVICE}: u is not the gate voltage")
    pal = PALETTES[palette]
    lw = STYLE["line_width"]
    c = cv_curves(REGIONS_DEVICE, "calibrated", REGIONS_GEOMETRY)
    rec = numbers.fit_record(REGIONS_DEVICE, REGIONS_GEOMETRY)
    res, sp, tc = rec["residuals"], rec["spice_regions"], rec["tcad_crossings"]
    u = c["u_spice"]
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        ax.set_xlim(u[0], u[-1])
        top = max(c["spice_tt"].max(), c["tcad"].max()) * STYLE["region_headroom"]
        ax.set_ylim(0, top)
        ax.grid(True)
        for key in ("plateau_acc_u", "plateau_inv_u"):
            a, b = min(res[key]), max(res[key])
            ax.axvspan(a, b, color=pal["highlight"], alpha=STYLE["region_alpha"], lw=0,
                       label="flat parts compared" if key == "plateau_acc_u" else None)  # fmt: skip
        ax.plot(u, c["spice_tt"], color=pal["text"], lw=lw, label="SPICE, typical")
        ax.plot(c["u"], c["tcad"], color=pal["highlight"], lw=lw, ls="--",
                zorder=STYLE["cv_zorder"], label="simulated, fitted")  # fmt: skip
        for key, xs, uu, cc, marker in (
            ("tcad", [tc["u_dep"], tc["u_inv"]], c["u"], c["tcad"], "D"),
            ("spice", [sp["u_dep"], sp["u_inv"]], u, c["spice_tt"], "o"),
        ):
            # The two crossings lie close together: the SPICE ones are hollow rings, larger and
            # on top, so the simulated diamond shows through each.
            ring = key == "spice"
            ax.plot(xs, np.interp(xs, uu, cc), ls="none", marker=marker,
                    ms=STYLE["ring_pt"] if ring else STYLE["marker_pt"],
                    mfc="none" if ring else pal["highlight"], mec=pal["text"],
                    mew=STYLE["edge_width"] * 2, zorder=STYLE["spike_zorder"] + (2 if ring else 1),
                    label=COMPARE_MARKS[key])  # fmt: skip
        ax.set_xlabel("gate voltage (V)")
        ax.set_ylabel("gate capacitance (fF)")
        fig.legend(loc="outside lower center", ncols=2, frameon=False)
        return fig


def calibration_compare(palette: str) -> bytes:
    """The nfet at ``w10p0_l10p00``: the :term:`SPICE` curve at the :term:`typical corner` and the
    fitted simulated curve, the flat parts the fit compares shaded (the voltages of the result
    file's residuals) and each curve's halfway-level crossings marked (``spice_regions`` and
    ``tcad_crossings``)."""
    with matplotlib.rc_context(_rc(palette)):
        return _svg(calibration_compare_figure(palette))


#: The transistor of :func:`calibration_pfet`.
PFET = "pfet_05v0"


def pfet_geometries() -> tuple[str, str]:
    """The shortest and the longest gate of the pfet's fit (``per_geometry`` of its result file)."""
    fit = numbers.fit_geometries(PFET)
    by_l = sorted(fit, key=lambda g: fit[g])
    return by_l[0], by_l[-1]


def calibration_pfet_figure(palette: str):
    """The matplotlib figure of :func:`calibration_pfet`, for the tests to read its lines."""
    from gf180tcad.devices import DEVICES

    pol = DEVICES[PFET].polarity
    pal = PALETTES[palette]
    lw = STYLE["line_width"]
    gids = pfet_geometries()
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["limits_size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        axes = fig.subplots(len(gids), 1)
        for ax, gid in zip(axes, gids, strict=True):
            c = cv_curves(PFET, "calibrated", gid)
            ax.fill_between(pol * c["u_spice"], c["spice_lo"], c["spice_hi"], color=pal["band"],
                            linewidth=0, label="SPICE, all corners")  # fmt: skip
            ax.plot(
                pol * c["u_spice"], c["spice_tt"], color=pal["text"], lw=lw, label="SPICE, typical"
            )
            ax.plot(pol * c["u"], c["tcad"], color=pal["highlight"], lw=lw, ls="--",
                    zorder=STYLE["cv_zorder"], label="simulated, fitted")  # fmt: skip
            ax.set_ylim(bottom=0)
            ax.grid(True)
            ax.set_title(
                f"gate length {numbers.fit_geometries(PFET)[gid]:g} µm", fontsize=STYLE["text_pt"]
            )
            ax.set_xlabel("gate voltage (V)")
            ax.set_ylabel("gate capacitance (fF)")
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside lower center", ncols=len(labels), frameon=False)
        return fig


def calibration_pfet(palette: str) -> bytes:
    """The pfet's gate capacitance at the shortest and the longest gate of its fit
    (:func:`pfet_geometries`), on the true gate voltage: the :term:`SPICE` band of all
    :term:`corners <corner>`, the typical curve and the fitted simulated curve."""
    with matplotlib.rc_context(_rc(palette)):
        return _svg(calibration_pfet_figure(palette))


# The corner-fit figure of docs/reproduce/index.md (Task 16a): the nfet at the longest
# calibration gate, the geometry of the MOS capacitor page's C-V figure.
CORNER_DEVICE, CORNER_GEOMETRY = "nfet_05v0", "w10p0_l10p00"
#: The corners drawn in colour: the slow and the fast nfet, the two ends of its corner range.
CORNER_HIGHLIGHT = {"ss": "hole", "ff": "electron"}
#: The line style of each mixed corner, drawn thin and muted.
CORNER_MIXED_STYLE = {"fs": ":", "sf": "-."}


def corner_cv_curves(device: str, gid: str) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """``{corner: (u, cgg_ff)}``: the committed :term:`SPICE` :term:`cv` sweep of ``gid`` at each of
    the five :term:`corners <corner>`, u = polarity × gate voltage (V), Cgg in fF."""
    from gf180tcad.devices import CORNERS, DEVICES

    pol = DEVICES[device].polarity
    return {
        c: data.spice_cv(data.spice_columns(SPICE_ROOT, "ngspice", c, device, gid, "cv"), pol)
        for c in CORNERS
    }


def corner_cv(palette: str) -> bytes:
    """The five SPICE corner curves of one geometry: the typical corner (solid, text colour),
    the slow and fast corners in colour, the two mixed corners muted, dotted (fs) and
    dash-dotted (sf). A corner fit takes one of
    the coloured curves as its target instead of the typical one."""
    pal = PALETTES[palette]
    lw = STYLE["line_width"]
    curves = corner_cv_curves(CORNER_DEVICE, CORNER_GEOMETRY)
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        for corner, (u, c) in curves.items():
            if corner == TYPICAL:
                ax.plot(u, c, color=pal["text"], lw=lw, label="typical",
                        zorder=STYLE["cv_zorder"])  # fmt: skip
            elif corner in CORNER_HIGHLIGHT:
                ax.plot(u, c, color=pal[CORNER_HIGHLIGHT[corner]], lw=lw, ls="--", label=corner)
            else:
                ax.plot(u, c, color=pal["muted"], lw=STYLE["line_width"] / 2,
                        ls=CORNER_MIXED_STYLE[corner], label=corner)  # fmt: skip
        ax.set_ylim(bottom=0)
        ax.grid(True)
        ax.set_xlabel("gate voltage (V)")
        ax.set_ylabel("gate capacitance (fF)")
        fig.legend(loc="outside lower center", ncols=len(curves), frameon=False)
        return _svg(fig)


# The gate-area figure of the corner-fit section of docs/reproduce/index.md (eq-corner-area and
# eq-corner-overlap): the gate seen from above at one corner, with the signs of that corner's
# XL and XW for the nfet of the corner-cv figure.
#: The corner whose XL and XW signs the gate-area figure draws: the slow corner.
AREA_CORNER = "ss"
_OVERLAP_LABEL = {
    "source overlap": "source overlap:\nCGSO, CGSL",
    "drain overlap": "drain overlap:\nCGDO, CGDL",
}


def corner_area_extents() -> dict[str, Box]:
    """The drawn extents of the gate-area figure, in drawing units, the gate centred on 0, x
    along the length and y along the width: ``drawn`` (L by W), ``corner`` (L + X_L by W + X_W,
    each offset with the sign of the ``CORNER_DEVICE``'s ``AREA_CORNER`` value in
    :repo:`data/pdk_corners.json`), ``area`` (the corner outline less D_L at each end and D_W at
    each side: the capacitance area L_c by W_c), and ``source overlap`` and ``drain overlap`` (the
    D_L strips at the two ends, W_c wide). The sizes are :data:`STYLE` ``area_drawn``."""
    from gf180tcad.calibrate import corners

    size = STYLE["area_drawn"]
    length, width = size["gate length and width"]
    x, d = size["length and width offsets"]
    lc = length + np.copysign(x, corners.card_shift(CORNER_DEVICE, AREA_CORNER, "xl"))
    wc = width + np.copysign(x, corners.card_shift(CORNER_DEVICE, AREA_CORNER, "xw"))
    return {
        "drawn": Box(-length / 2, length / 2, -width / 2, width / 2),
        "corner": Box(-lc / 2, lc / 2, -wc / 2, wc / 2),
        "area": Box(-lc / 2 + d, lc / 2 - d, -wc / 2 + d, wc / 2 - d),
        "source overlap": Box(-lc / 2, -lc / 2 + d, -wc / 2 + d, wc / 2 - d),
        "drain overlap": Box(lc / 2 - d, lc / 2, -wc / 2 + d, wc / 2 - d),
    }


def _dimension(ax, a: float, b: float, at: float, label: str, colour: str, along: str) -> None:
    """A two-headed dimension line from ``a`` to ``b`` at ``at``, labelled outside the drawing:
    along x (a length, label above) or along y (a width, label to the right)."""
    ends = ((a, at), (b, at)) if along == "x" else ((at, a), (at, b))
    ax.annotate("", xy=ends[0], xytext=ends[1],
                arrowprops={"arrowstyle": "<->", "color": colour, "lw": STYLE["edge_width"],
                            "shrinkA": 0, "shrinkB": 0})  # fmt: skip
    mid = (a + b) / 2
    pad = STYLE["dim_label_pad"]
    if along == "x":
        ax.text(mid, at + pad, label, ha="center", va="bottom")
    else:
        ax.text(at + pad, mid, label, ha="left", va="center", rotation=STYLE["upright_deg"])


def _guide(ax, xs: tuple[float, float], ys: tuple[float, float], colour: str) -> None:
    ax.plot(xs, ys, color=colour, lw=STYLE["edge_width"], ls=":")


def corner_area(palette: str) -> bytes:
    """The gate seen from above at one corner: the drawn outline (solid), the corner's outline
    L + X_L by W + X_W (dashed), the capacitance area L_c by W_c inside it (filled, the
    highlight), and the two D_L strips at the source and drain ends that carry the overlap
    capacitances (filled, the electron colour), each length and width dimensioned with the
    symbols of eq-corner-area. Not to scale; the statement says so."""
    pal = PALETTES[palette]
    ext = corner_area_extents()
    gap = STYLE["dim_gap"]
    fills = {"area": pal["highlight"], "source overlap": pal["electron"],
             "drain overlap": pal["electron"]}  # fmt: skip
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["size_in"], layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        ax.set_axis_off()
        ax.set_aspect("equal")
        for part, colour in fills.items():
            a, b, y0, y1 = ext[part]
            ax.fill_between([a, b], y0, y1, color=colour, alpha=STYLE["cell_alpha"], linewidth=0)
        for part, ls in (("drawn", "-"), ("corner", "--")):
            a, b, y0, y1 = ext[part]
            ax.plot([a, b, b, a, a], [y0, y0, y1, y1, y0], color=pal["text"],
                    lw=STYLE["line_width"] / 2, ls=ls)  # fmt: skip
        area = ext["area"]
        ax.text(0.0, (area.y0 + area.y1) / 2, "capacitance area\n$L_c \\times W_c$",
                ha="center", va="center")  # fmt: skip
        top = max(ext["drawn"].y1, ext["corner"].y1)
        right = max(ext["drawn"].x1, ext["corner"].x1)
        lengths = (("drawn", "$L$"), ("corner", "$L + X_{L,c}$"), ("area", "$L_c$"))
        for n, (part, label) in enumerate(lengths, start=1):
            a, b, _y0, y1 = ext[part]
            at = top + n * gap
            for x in (a, b):
                _guide(ax, (x, x), (y1, at), pal["grid"])
            _dimension(ax, a, b, at, label, pal["text"], "x")
        widths = (("drawn", "$W$"), ("corner", "$W + X_{W,c}$"), ("area", "$W_c$"))
        for n, (part, label) in enumerate(widths, start=1):
            _a, b, y0, y1 = ext[part]
            at = right + n * gap * STYLE["dim_width_spacing"]
            for y in (y0, y1):
                _guide(ax, (b, at), (y, y), pal["grid"])
            _dimension(ax, y0, y1, at, label, pal["text"], "y")
        corner = ext["corner"]
        bottom = corner.y0 - gap
        _dimension(ax, corner.x0, area.x0, bottom, "", pal["text"], "x")
        ax.text(corner.x0 - STYLE["dim_label_pad"], bottom, "$D_L$", ha="right", va="center")
        _guide(ax, (area.x0, area.x0), (corner.y0, bottom), pal["grid"])
        _guide(ax, (corner.x0, corner.x0), (corner.y0, bottom), pal["grid"])
        left = corner.x0 - gap
        _dimension(ax, area.y1, corner.y1, left, "", pal["text"], "y")
        ax.text(left - STYLE["dim_label_pad"], corner.y1, "$D_W$", ha="right", va="center")
        _guide(ax, (left, area.x0), (area.y1, area.y1), pal["grid"])
        _guide(ax, (left, corner.x0), (corner.y1, corner.y1), pal["grid"])
        for part, label in _OVERLAP_LABEL.items():
            a, b, y0, _y1 = ext[part]
            ha = "left" if part == "source overlap" else "right"
            ax.annotate(label, xy=((a + b) / 2, (y0 + area.y1) / 2),
                        xytext=(a if ha == "left" else b, bottom - gap), ha=ha, va="top",
                        arrowprops={"arrowstyle": "-", "color": pal["text"],
                                    "lw": STYLE["edge_width"]})  # fmt: skip
        ax.set_title(_statement("corner-area").replace(". ", ".\n"), fontsize=STYLE["text_pt"])
        return _svg(fig)


# name -> function of the palette name; each is written in both palettes by write_all.
FIGURES: dict[str, Callable[[str], bytes]] = {
    "silicon-doping": _silicon_doping,
    "oxide-stack": _oxide_stack,
    "bands-stack": _bands_stack,
    "bands-flat": _bands_flat,
    "parts-cell": _parts_cell,
    "junction-cell": _junction_cell,
    "junction-panels": junction_panels,
    "moscap-cell": _moscap_cell,
    "moscap-cv": _moscap_cv,
    "cv-regions": cv_regions,
    "band-regimes": band_regimes,
    "mesh-window": _mesh_window,
    "cv-parts": cv_parts,
    "calibration-limits": calibration_limits,
    "calibration-compare": calibration_compare,
    "calibration-pfet": calibration_pfet,
    "calibration-stack": _calibration_stack,
    "corner-cv": corner_cv,
    "corner-area": corner_area,
}


# The figures drawn from the 2D cell, whose statement also names the drawn extents; the plots of
# computed curves (not drawings of the device) carry no statement.
_CELL_FIGURES = ("parts-cell", "junction-cell", "moscap-cell", "mesh-window")
_PLOTS = (
    "bands-flat",
    "junction-panels",
    "moscap-cv",
    "cv-regions",
    "band-regimes",
    "cv-parts",
    "calibration-limits",
    "calibration-compare",
    "calibration-pfet",
    "corner-cv",
)


def _statement(name: str) -> str:
    """The exaggeration statement of the drawing ``name``: the gate-area figure scales no layer
    and chooses its sizes for the drawing; the others use the layer scale factors."""
    if name == "corner-area":
        return model.exaggeration({}, STYLE["area_drawn"])
    drawn = STYLE["drawn_um"] if name in _CELL_FIGURES else None
    return model.exaggeration(STYLE["scales"], drawn)


def substitutions() -> dict[str, str]:
    """``{"x_fig_<name>_scale": statement}``: the exaggeration statement of each drawing of the
    device, for its caption, from the same scale factors (and drawn extents) the drawing uses."""
    return {
        f"x_fig_{name.replace('-', '_')}_scale": _statement(name)
        for name in FIGURES
        if name not in _PLOTS
    }


def write_all(out_dir: Path) -> None:
    """Write every figure of :data:`FIGURES` as ``<name>-light.svg`` and ``<name>-dark.svg``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, draw in FIGURES.items():
        for palette in PALETTES:
            (out / f"{name}-{palette}.svg").write_bytes(draw(palette))
