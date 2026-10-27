# SPDX-License-Identifier: Apache-2.0
"""Deterministic SVG plots for the generated results pages.

Everything here is presentation: it draws arrays it is given and computes nothing that is
published as a result. The SVG bytes depend only on the input arrays and the pinned
matplotlib version: fixed hash salt (element ids), no date, text kept as text (no font
outlines), fixed size and dpi, and path simplification off.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from io import BytesIO

import matplotlib
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

RC = {
    "svg.hashsalt": "gf180tcad",
    "svg.fonttype": "none",
    "path.simplify": False,
    "figure.dpi": 100,
    "savefig.dpi": 100,
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans"],
    "axes.unicode_minus": False,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
}
METADATA = {"Date": None, "Creator": "gf180tcad"}
FIG_W, FIG_H = 10.0, 4.0  # inches; the width is the page-wide 100 dpi layout

# Colourblind-safe (Okabe-Ito) colours: engines, then the Vgs / Vbs family.
NGSPICE_COLOR = "#0072B2"
XYCE_COLOR = "#D55E00"
FAMILY = ("#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#000000")


@dataclass(frozen=True)
class Curve:
    """One line (``y2`` None) or a shaded band between ``y`` and ``y2``."""

    x: np.ndarray
    y: np.ndarray
    color: str
    y2: np.ndarray | None = None
    dashed: bool = False
    label: str | None = None


@dataclass(frozen=True)
class Key:
    """One legend entry: a solid or dashed line, or a shaded band (``kind``)."""

    label: str
    color: str
    kind: str = "line"  # "line", "dashed" or "band"


@dataclass(frozen=True)
class Panel:
    title: str
    xlabel: str
    ylabel: str
    curves: list[Curve] = field(default_factory=list)
    yscale: str = "linear"
    ylim: tuple[float, float] | None = None
    keys: list[Key] = field(default_factory=list)  # own legend (replaces the engine legend)


def _handle(k: Key):
    if k.kind == "band":
        return Patch(color=k.color, alpha=0.25, label=k.label)
    if k.kind not in ("line", "dashed"):
        raise ValueError(f"unknown legend kind {k.kind!r}")
    return Line2D(
        [], [], color=k.color, linestyle="--" if k.kind == "dashed" else "-", label=k.label
    )


def figure_svg(
    panels: list[Panel],
    legend: dict[str, str] | None = None,
    *,
    size: tuple[float, float] = (FIG_W, FIG_H),
    rc: Mapping[str, object] | None = None,
    text_pt: float | None = None,
) -> bytes:
    """Render panels side by side to SVG bytes. ``legend`` maps line label to colour.

    Without :attr:`Panel.keys` the last panel carries the engine legend (ngspice TT, its corner
    envelope, Xyce TT). If any panel has ``keys``, each such panel carries its own legend instead.

    ``size`` is the figure size in inches, ``rc`` overrides entries of :data:`RC` (a dark
    palette), and ``text_pt`` sets every text size (titles, labels, ticks, legends) to one value.
    The defaults draw the results pages' figures, byte for byte as before these parameters.
    """
    title_pt, legend_pt = (10, 8) if text_pt is None else (text_pt, text_pt)
    params = {**RC, **(rc or {})}
    if text_pt is not None:
        params["font.size"] = text_pt
    with matplotlib.rc_context(params):
        fig = Figure(figsize=size, layout="constrained")
        FigureCanvasAgg(fig)
        axes = fig.subplots(1, len(panels), squeeze=False)[0]
        for ax, panel in zip(axes, panels, strict=True):
            for c in panel.curves:
                if c.y2 is not None:
                    ax.fill_between(c.x, c.y, c.y2, color=c.color, alpha=0.25, linewidth=0)
                else:
                    ax.plot(
                        c.x, c.y, color=c.color, linewidth=1.4, linestyle="--" if c.dashed else "-"
                    )
            ax.set_yscale(panel.yscale)
            if panel.ylim is not None:
                ax.set_ylim(*panel.ylim)
            ax.set_title(panel.title, fontsize=title_pt)
            ax.set_xlabel(panel.xlabel)
            ax.set_ylabel(panel.ylabel)
        if any(p.keys for p in panels):
            for ax, panel in zip(axes, panels, strict=True):
                if panel.keys:
                    handles = [_handle(k) for k in panel.keys]
                    ax.legend(handles=handles, fontsize=legend_pt, loc="best", framealpha=0.85)
            buf = BytesIO()
            fig.savefig(buf, format="svg", metadata=METADATA)
            return buf.getvalue()
        # With a colour family (Id-Vd) the colour is the Vgs, so the engine key is neutral grey.
        key = "#555555" if legend else NGSPICE_COLOR
        handles = [
            Line2D([], [], color=key, label="ngspice TT"),
            Patch(color=key, alpha=0.25, label="ngspice corner envelope"),
        ]
        if any(c.dashed for p in panels for c in p.curves):
            xkey = key if legend else XYCE_COLOR
            handles.insert(1, Line2D([], [], color=xkey, linestyle="--", label="Xyce TT"))
        for label, color in (legend or {}).items():
            handles.append(Line2D([], [], color=color, linewidth=3, label=label))
        axes[-1].legend(handles=handles, fontsize=legend_pt, loc="best", framealpha=0.85)
        buf = BytesIO()
        fig.savefig(buf, format="svg", metadata=METADATA)
        return buf.getvalue()
