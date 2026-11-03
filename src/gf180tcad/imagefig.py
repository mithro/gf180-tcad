# SPDX-License-Identifier: Apache-2.0
"""The figures of docs/reproduce/image.md's Charon section, each in a light and a dark twin.

:func:`charon_stages` draws the three stages of ``docker/charon-libs/Dockerfile`` (``deps``,
``build`` and the final image) with the inputs and the base image they start from, as boxes
joined by arrows. :func:`write_all` writes every figure of :data:`FIGURES` as
``<name>-light.svg`` and ``<name>-dark.svg`` into ``docs/_generated/reproduce/`` at docs build
time (:func:`gf180tcad.docgen.generate`). A page embeds both twins, and the theme shows one
(``docs/_ext/theme_figures.py`` merges them into one numbered figure).

Each twin has an opaque background. Its box fills are pale tints in the light twin, with
near-black text, and deep shades in the dark twin, with near-white text. Every text colour
reaches a contrast of at least :data:`MIN_TEXT_CONTRAST` on every fill and background it sits
on, and every arrow at least :data:`MIN_GRAPHIC_CONTRAST` on the background (:func:`contrast`,
the WCAG 2.1 contrast ratio; tested). The SVG settings are those of :mod:`gf180tcad.plots`
(fixed hash salt, text kept as text, no date), so each file is byte-for-byte the same on every
build.
"""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from itertools import pairwise
from pathlib import Path

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch

from gf180tcad import plots

#: The stages as the Dockerfile names them (``FROM ... AS <name>``), in build order.
STAGES = ("deps", "build")

#: WCAG 2.1 contrast floors: normal-size text (success criterion 1.4.3) and graphics (1.4.11).
MIN_TEXT_CONTRAST = 4.5
MIN_GRAPHIC_CONTRAST = 3.0

STYLE = {
    # 6.4 in wide with 12 pt text: legible when the SVG is scaled to a 400 px column.
    "size_in": (6.4, 6.4),
    "text_pt": 12,
    "arrow_width": 2.0,
    # Box centres and sizes, as fractions of the drawing (x right, y up).
    "main_x": 0.64,
    "main_w": 0.66,
    "side_x": 0.135,
    "side_w": 0.23,
    "box_h": 0.15,
    "rows": {"inputs": 0.89, "deps": 0.64, "build": 0.39, "image": 0.12},
    "side_y": 0.39,
    "pad": 0.012,
}

# Okabe-Ito blue, reddish purple, vermilion and bluish green are the hues of the box roles,
# mixed towards white for the light twin and towards black for the dark twin.
PALETTES = {
    "light": {
        "background": "#ffffff",
        "text": "#222222",
        "arrow": "#555555",
        "fill": {"inputs": "#cce3f0", "base": "#f2d7e6", "stage": "#f7d5bf", "image": "#c8eadf"},
    },
    "dark": {
        "background": "#131416",
        "text": "#e4e4e4",
        "arrow": "#bdbdbd",
        "fill": {"inputs": "#0b3a57", "base": "#5a2f48", "stage": "#6a3008", "image": "#0a4a37"},
    },
}

#: The text of each box (lines), drawn from the Dockerfile's stages.
BOXES = {
    "inputs": ("Inputs of upstream.json", "mirror first, then the original URL,", "sha256 checked"),
    "base": ("Base image", "docker/IMAGE"),
    "deps": ("Stage deps", "build packages installed,", "sources unpacked and patched"),
    "build": ("Stage build", "configure, make, make install,", "4 probe tests, into /opt/charon"),
    "image": ("charon-libs image", "base image + /opt/charon,", "every library found (ldd)"),
}


def _luminance(colour: str) -> float:
    """WCAG 2.1 relative luminance of a ``#rrggbb`` colour."""
    lin = []
    for i in (1, 3, 5):
        c = int(colour[i : i + 2], 16) / 255
        lin.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    """WCAG 2.1 contrast ratio of two ``#rrggbb`` colours, from 1 to 21."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def text_pairs(palette: str) -> list[tuple[str, str]]:
    """Every (text colour, colour under it) pair the figures of ``palette`` draw."""
    pal = PALETTES[palette]
    return [(pal["text"], f) for f in (*pal["fill"].values(), pal["background"])]


def _rc(palette: str) -> dict:
    pal = PALETTES[palette]
    return {
        **plots.RC,
        "font.size": STYLE["text_pt"],
        "figure.facecolor": pal["background"],
        "savefig.facecolor": pal["background"],
        "text.color": pal["text"],
    }


def _axes(fig: Figure):
    FigureCanvasAgg(fig)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return ax


def _save(fig: Figure, fmt: str) -> bytes:
    buf = BytesIO()
    fig.savefig(buf, format=fmt, metadata=plots.METADATA if fmt == "svg" else None)
    return buf.getvalue()


def _box(ax, key: str, x: float, y: float, w: float, fill: str) -> None:
    h = STYLE["box_h"]
    ax.add_patch(
        FancyBboxPatch(
            (x - w / 2, y - h / 2),
            w,
            h,
            boxstyle=f"round,pad={STYLE['pad']}",
            facecolor=fill,
            edgecolor="none",
        )
    )
    ax.text(x, y, "\n".join(BOXES[key]), ha="center", va="center")


def _arrow(ax, start: tuple[float, float], end: tuple[float, float], colour: str) -> None:
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops={"arrowstyle": "-|>", "color": colour, "lw": STYLE["arrow_width"]},
    )


def charon_stages(palette: str = "light", fmt: str = "svg") -> bytes:
    """The stage diagram in ``palette`` as SVG bytes (``fmt="png"`` for a raster preview)."""
    pal = PALETTES[palette]
    fill, arrow = pal["fill"], pal["arrow"]
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["size_in"])
        ax = _axes(fig)
        mx, mw, sx, sw = STYLE["main_x"], STYLE["main_w"], STYLE["side_x"], STYLE["side_w"]
        rows, half = STYLE["rows"], STYLE["box_h"] / 2 + STYLE["pad"]
        _box(ax, "inputs", mx, rows["inputs"], mw, fill["inputs"])
        for stage in STAGES:
            _box(ax, stage, mx, rows[stage], mw, fill["stage"])
        _box(ax, "image", mx, rows["image"], mw, fill["image"])
        _box(ax, "base", sx, STYLE["side_y"], sw, fill["base"])
        order = ("inputs", *STAGES, "image")
        for a, b in pairwise(order):
            _arrow(ax, (mx, rows[a] - half), (mx, rows[b] + half), arrow)
        side_top = (sx, STYLE["side_y"] + half)
        side_bottom = (sx, STYLE["side_y"] - half)
        _arrow(ax, side_top, (mx - mw / 2 - STYLE["pad"], rows["deps"]), arrow)
        _arrow(ax, side_bottom, (mx - mw / 2 - STYLE["pad"], rows["image"]), arrow)
        return _save(fig, fmt)


#: Every figure of the image page, by file name stem; each is drawn once per palette.
FIGURES: dict[str, Callable[[str], bytes]] = {"charon-stages": charon_stages}


def write_all(out_dir: Path) -> None:
    """Write every figure of :data:`FIGURES` as ``<name>-light.svg`` and ``<name>-dark.svg``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, draw in FIGURES.items():
        for palette in PALETTES:
            (out / f"{name}-{palette}.svg").write_bytes(draw(palette))
