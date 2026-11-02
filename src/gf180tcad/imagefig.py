# SPDX-License-Identifier: Apache-2.0
"""The figure of docs/reproduce/image.md's Charon section: how the charon-libs image is built.

:func:`charon_stages` draws the three stages of ``docker/charon-libs/Dockerfile`` (``deps``,
``build`` and the final image) with the inputs and the base image they start from, as boxes
joined by arrows. :func:`write_all` writes it as ``charon-stages.svg`` into
``docs/_generated/reproduce/`` at docs build time (:func:`gf180tcad.docgen.generate`).

One SVG serves both themes: the background is transparent, every word sits in white on a filled
box, and the arrows are a mid grey that reads on white and on near-black. The SVG settings are
those of :mod:`gf180tcad.plots` (fixed hash salt, text kept as text, no date), so the file is
byte-for-byte the same on every build.
"""

from __future__ import annotations

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

STYLE = {
    # 6.4 in wide with 12 pt text: legible when the SVG is scaled to a 400 px column.
    "size_in": (6.4, 6.4),
    "text_pt": 12,
    "arrow_width": 2.0,
    # Okabe-Ito blue, vermilion, bluish green and reddish purple, with white text on each.
    "fill": {"inputs": "#0072B2", "base": "#CC79A7", "stage": "#D55E00", "image": "#009E73"},
    "text": "#ffffff",
    "arrow": "#8c8c8c",
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

#: The text of each box (lines), drawn from the Dockerfile's stages.
BOXES = {
    "inputs": ("Inputs of upstream.json", "mirror first, then the original URL,", "sha256 checked"),
    "base": ("Base image", "docker/IMAGE"),
    "deps": ("Stage deps", "build packages installed,", "sources unpacked and patched"),
    "build": ("Stage build", "configure, make, make install,", "4 probe tests, into /opt/charon"),
    "image": ("charon-libs image", "base image + /opt/charon,", "every library found (ldd)"),
}


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
    ax.text(x, y, "\n".join(BOXES[key]), ha="center", va="center", color=STYLE["text"])


def _arrow(ax, start: tuple[float, float], end: tuple[float, float]) -> None:
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops={"arrowstyle": "-|>", "color": STYLE["arrow"], "lw": STYLE["arrow_width"]},
    )


def charon_stages(fmt: str = "svg") -> bytes:
    """The stage diagram as SVG bytes (``fmt="png"`` for a raster preview)."""
    rc = {
        **plots.RC,
        "font.size": STYLE["text_pt"],
        "figure.facecolor": "none",
        "savefig.facecolor": "none",
        "savefig.transparent": True,
    }
    with matplotlib.rc_context(rc):
        fig = Figure(figsize=STYLE["size_in"])
        FigureCanvasAgg(fig)
        ax = fig.add_axes((0, 0, 1, 1))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        mx, mw, sx, sw = STYLE["main_x"], STYLE["main_w"], STYLE["side_x"], STYLE["side_w"]
        rows, half = STYLE["rows"], STYLE["box_h"] / 2 + STYLE["pad"]
        _box(ax, "inputs", mx, rows["inputs"], mw, STYLE["fill"]["inputs"])
        for stage in STAGES:
            _box(ax, stage, mx, rows[stage], mw, STYLE["fill"]["stage"])
        _box(ax, "image", mx, rows["image"], mw, STYLE["fill"]["image"])
        _box(ax, "base", sx, STYLE["side_y"], sw, STYLE["fill"]["base"])
        order = ("inputs", *STAGES, "image")
        for a, b in pairwise(order):
            _arrow(ax, (mx, rows[a] - half), (mx, rows[b] + half))
        side_top = (sx, STYLE["side_y"] + half)
        side_bottom = (sx, STYLE["side_y"] - half)
        _arrow(ax, side_top, (mx - mw / 2 - STYLE["pad"], rows["deps"]))
        _arrow(ax, side_bottom, (mx - mw / 2 - STYLE["pad"], rows["image"]))
        buf = BytesIO()
        meta = plots.METADATA if fmt == "svg" else None
        fig.savefig(buf, format=fmt, metadata=meta, transparent=True)
    return buf.getvalue()


def write_all(out_dir: Path) -> None:
    """Write ``charon-stages.svg`` into ``out_dir``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "charon-stages.svg").write_bytes(charon_stages())
