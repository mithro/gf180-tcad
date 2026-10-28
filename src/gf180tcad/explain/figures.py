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

from gf180tcad import plots
from gf180tcad.explain import idealised, model, numbers

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
    # The junction panels: positions from (1 + pad) widths into the body to pad widths into the
    # source, on this many points; the charge axis spans the dopings with headroom.
    "junction_pad": 0.25,
    "junction_points": 20001,
}

#: Unit conversions of the junction panels: cm to µm, V/cm to kV/cm.
UNITS = {"um_per_cm": 1e4, "kv_per_v": 1e-3}

# Okabe-Ito colours for the carriers and the highlight; greys for the muted parts.
PALETTES = {
    "light": {
        "background": "#ffffff",
        "text": "#222222",
        "grid": "#c8c8c8",
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
    ``most`` digits do: 0.2 µm, not 0.2000 µm."""
    target = float(f"{v:.{most - 1}e}")
    for d in range(1, most + 1):
        if float(f"{v:.{d - 1}e}") == target:
            return numbers.format_value(v, d, unit)
    return numbers.format_value(v, most, unit)


def _thickness(layer: model.Layer) -> str:
    most = STYLE["label_digits"]["thickness"]
    if layer.thickness_um < STYLE["nm_below_um"]:
        return _short(layer.thickness_um * model.UNITS["nm_per_um"], "nm", most)
    return _short(layer.thickness_um, "µm", most)


_STACK_NAME = {"gate": "gate", "oxide": "gate oxide", "body": "body"}


def stack_1d(dev: model.Device, highlight: tuple[str, ...], palette: str) -> bytes:
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
        return _svg(fig)


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


def cross_section(c: model.Cell, highlight: tuple[str, ...], palette: str) -> bytes:
    """The 2D cell cut along its length: gate, gate oxide, source, drain and body, each filled
    with its carrier's colour (n-type: electrons, p-type: holes; the oxide its own) and labelled
    on the part, and the contacts of ``c.contacts`` as dark bars. With ``highlight``, the parts
    named there keep their colour and the rest are muted; ``"junction"`` draws the boundary of
    the source and the drain with the body in the highlight colour."""
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
        statement = model.exaggeration(c.scales, c.drawn).replace(". ", ".\n")
        ax.set_title(statement, fontsize=STYLE["text_pt"])
        return _svg(fig)


_JUNCTION_PANELS = ("charge", "field", "potential")


def junction_panels(palette: str) -> bytes:
    """The charge, field and potential of the idealised abrupt junction between the nfet's
    source and its body (:func:`gf180tcad.explain.idealised.abrupt_junction`), from the
    registry's dopings, built-in potential and constants, against the distance from the
    junction into the body."""
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
        ax_q.vlines(0.0, n_a, n_d, color=pal["electron"], lw=lw)
        ax_q.set_ylim(n_a / STYLE["headroom"], n_d * STYLE["headroom"])
        ax_q.set_ylabel("ions (cm⁻³)")
        ax_q.legend(loc="upper right", frameon=False, ncols=2)
        ax_e.plot(x_um, prof["field_v_per_cm"] * UNITS["kv_per_v"], color=pal["highlight"], lw=lw)
        ax_e.set_ylabel("field (kV/cm)")
        ax_v.plot(x_um, prof["potential_v"], color=pal["highlight"], lw=lw)
        ax_v.set_ylabel("potential (V)")
        ax_v.set_xlabel("distance from the junction into the body (µm)")
        for ax in (ax_q, ax_e, ax_v):
            ax.axvline(0.0, color=pal["text"], lw=STYLE["edge_width"])
            ax.axvline(x_p, color=pal["intrinsic"], lw=STYLE["edge_width"], ls=":")
        ax_v.text(x_p, vbi, "depletion edge ", ha="right", va="top", color=pal["intrinsic"])
        return _svg(fig)


def _parts_cell(palette: str) -> bytes:
    c = model.cell(
        "nfet_05v0", "calibrated", "w10p0_l0p70", scales=STYLE["scales"], drawn=STYLE["drawn_um"]
    )
    return cross_section(c, (), palette)


def _junction_cell(palette: str) -> bytes:
    c = model.cell(
        "nfet_05v0", "calibrated", "w10p0_l0p70", scales=STYLE["scales"], drawn=STYLE["drawn_um"]
    )
    return cross_section(c, ("junction",), palette)


# name -> function of the palette name; each is written in both palettes by write_all.
FIGURES: dict[str, Callable[[str], bytes]] = {
    "silicon-doping": _silicon_doping,
    "oxide-stack": _oxide_stack,
    "bands-stack": _bands_stack,
    "bands-flat": _bands_flat,
    "parts-cell": _parts_cell,
    "junction-cell": _junction_cell,
    "junction-panels": junction_panels,
}


# The figures drawn from the 2D cell, whose statement also names the drawn extents; the plots of
# computed curves (not drawings of the device) carry no statement.
_CELL_FIGURES = ("parts-cell", "junction-cell")
_PLOTS = ("bands-flat", "junction-panels")


def substitutions() -> dict[str, str]:
    """``{"x_fig_<name>_scale": statement}``: the exaggeration statement of each drawing of the
    device, for its caption, from the same scale factors (and drawn extents) the drawing uses."""
    out = {}
    for name in FIGURES:
        if name in _PLOTS:
            continue
        drawn = STYLE["drawn_um"] if name in _CELL_FIGURES else None
        out[f"x_fig_{name.replace('-', '_')}_scale"] = model.exaggeration(STYLE["scales"], drawn)
    return out


def write_all(out_dir: Path) -> None:
    """Write every figure of :data:`FIGURES` as ``<name>-light.svg`` and ``<name>-dark.svg``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, draw in FIGURES.items():
        for palette in PALETTES:
            (out / f"{name}-{palette}.svg").write_bytes(draw(palette))
