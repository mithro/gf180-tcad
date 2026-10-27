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

import matplotlib
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
    # A layer thinner than this (µm) gives its thickness in nm.
    "nm_below_um": 0.1,
    # Most significant digits a label shows (fewer when they print the same value).
    "label_digits": {"thickness": 4, "doping": 3},
}

# Okabe-Ito colours for the carriers and the highlight; greys for the muted parts.
PALETTES = {
    "light": {
        "background": "#ffffff",
        "text": "#222222",
        "grid": "#c8c8c8",
        "highlight": "#009E73",
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
    its doping from the model. The parts in ``highlight`` are shaded, the rest muted. Drawn at
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
        ax.set_xlim(0, 1)
        ax.set_ylim(edges[-1][2], edges[0][1])  # depth grows downwards
        for layer, a, b in edges:
            role = "highlight" if layer.part in highlight else "muted"
            ax.fill_between(
                [0, width], a, b, color=pal[role], alpha=STYLE["band_alpha"][role], linewidth=0
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


def _silicon_doping(palette: str) -> bytes:
    dev = model.device("nfet_05v0", "calibrated", scales=STYLE["scales"])
    return doping_profile(dev, "body", palette)


def _oxide_stack(palette: str) -> bytes:
    dev = model.device("nfet_05v0", "calibrated", scales=STYLE["scales"])
    return stack_1d(dev, ("gate", "oxide"), palette)


# name -> function of the palette name; each is written in both palettes by write_all.
FIGURES: dict[str, Callable[[str], bytes]] = {
    "silicon-doping": _silicon_doping,
    "oxide-stack": _oxide_stack,
}


def substitutions() -> dict[str, str]:
    """``{"x_fig_<name>_scale": statement}``: the exaggeration statement of each figure, for its
    caption, from the same scale factors the drawing uses."""
    return {
        f"x_fig_{name.replace('-', '_')}_scale": model.exaggeration(STYLE["scales"])
        for name in FIGURES
    }


def write_all(out_dir: Path) -> None:
    """Write every figure of :data:`FIGURES` as ``<name>-light.svg`` and ``<name>-dark.svg``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, draw in FIGURES.items():
        for palette in PALETTES:
            (out / f"{name}-{palette}.svg").write_bytes(draw(palette))
