# SPDX-License-Identifier: Apache-2.0
"""The figures of docs/reproduce/image.md's Charon section, each in a light and a dark twin.

:func:`charon_stages` draws the three stages of ``docker/charon-libs/Dockerfile`` (``deps``,
``build`` and the final image) with the inputs and the base image they start from, as boxes
joined by arrows. :func:`charon_mpi` draws ``charon_mp.exe`` as one MPI process with its two
threads inside the container of ``tools/sandbox-run``. :func:`charon_ci` draws the gate, the
build, the three checks and the published tags of the charon-libs entry of
``.github/workflows/image.yml``. :func:`write_all` writes every figure of :data:`FIGURES` as
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
    "edge_width": 1.5,
    # The MPI figure: (x0, y0, x1, y1) of each box, as fractions of the drawing.
    "mpi_size_in": (6.4, 6.0),
    "mpi": {
        "container": (0.03, 0.03, 0.97, 0.97),
        "process": (0.08, 0.50, 0.92, 0.82),
        "main": (0.12, 0.54, 0.49, 0.70),
        "progress": (0.53, 0.54, 0.88, 0.70),
        "tmp": (0.08, 0.24, 0.47, 0.42),
        "absent": (0.53, 0.24, 0.92, 0.42),
    },
    # The CI figure: box centres (x, y), widths and one height, as fractions of the drawing.
    "ci_size_in": (6.4, 7.2),
    "ci_box_h": 0.105,
    "ci": {
        "trigger": (0.5, 0.925, 0.88),
        "gate": (0.5, 0.765, 0.88),
        "build": (0.33, 0.585, 0.54),
        "skip": (0.81, 0.585, 0.26),
        "check_id": (0.155, 0.38, 0.255),
        "check_pin": (0.5, 0.38, 0.255),
        "check_probe": (0.845, 0.38, 0.255),
        "publish": (0.5, 0.11, 0.88),
    },
    "ci_label_dx": 0.03,
}

# Okabe-Ito blue, reddish purple, vermilion, bluish green and yellow are the hues of the box
# roles, mixed towards white for the light twin and towards black for the dark twin; the
# container role is a neutral grey with an edge in the arrow colour.
PALETTES = {
    "light": {
        "background": "#ffffff",
        "text": "#222222",
        "arrow": "#555555",
        "fill": {
            "inputs": "#cce3f0",
            "base": "#f2d7e6",
            "stage": "#f7d5bf",
            "image": "#c8eadf",
            "check": "#f7f2c0",
            "container": "#eeeeee",
        },
    },
    "dark": {
        "background": "#131416",
        "text": "#e4e4e4",
        "arrow": "#bdbdbd",
        "fill": {
            "inputs": "#0b3a57",
            "base": "#5a2f48",
            "stage": "#6a3008",
            "image": "#0a4a37",
            "check": "#4a4410",
            "container": "#2a2c2f",
        },
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


#: The OpenMPI setting of the image's ENV that the MPI figure names (``docker/charon-libs/Dockerfile``).
MPI_ENV = "OMPI_MCA_ess_singleton_isolated=1"

#: The text of each box of the MPI figure (lines).
MPI_BOXES = {
    "container": ("Container of tools/sandbox-run:", "no network, read-only root, /tmp writable"),
    "process": ("charon_mp.exe: one MPI process, no mpirun",),
    "main": ("Thread 1: main", "runs the solve"),
    "progress": ("Thread 2: OpenMPI", "progress thread"),
    "tmp": ("/tmp (tmpfs)", "ompi.* session", "directory"),
    "absent": ("Not started:", "orted daemon,", "/tmp/pmix-gds-shmem.*"),
    "env": ("The image's ENV sets", MPI_ENV),
}

#: The paths whose change runs the charon-libs entry on a pull request or a push (the gate).
CI_GATE_PATHS = ("docker/charon-libs", "docker/IMAGE", "docker/CHARON_LIBS_IMAGE")

#: The three check steps of ``.github/workflows/image.yml`` by their step names, with the
#: box text the CI figure gives each.
CI_CHECKS = {
    "check_id": ("Config digest matches IMAGE_ID", ("Config digest", "= IMAGE_ID")),
    "check_pin": ("Manifest matches the pin file", ("Manifest", "= the pin file")),
    "check_probe": (
        "versions.json matches the probe run in the pinned image",
        ("Probe output", "= versions.json"),
    ),
}

#: The text of the other boxes of the CI figure (lines).
CI_BOXES = {
    "trigger": ("Pull request, push to main, or manual run",),
    "gate": (
        "Does the change touch docker/charon-libs/,",
        "docker/IMAGE or docker/CHARON_LIBS_IMAGE?",
        "A manual run always builds.",
    ),
    "build": ("Build; push only", "the tag unverified"),
    "skip": ("Skip every", "later step;", "the job passes"),
    "publish": ("All three pass: push the published tags,", "pr-<number>, or latest and sha-<commit>"),
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


def _rect(ax, box: tuple[float, float, float, float], fill: str, edge: str | None = None,
          dashed: bool = False) -> None:  # fmt: skip
    x0, y0, x1, y1 = box
    ax.add_patch(
        FancyBboxPatch(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            boxstyle=f"round,pad={STYLE['pad']}",
            facecolor=fill,
            edgecolor=edge or "none",
            linewidth=STYLE["edge_width"] if edge else 0,
            linestyle="--" if dashed else "-",
        )
    )


def charon_mpi(palette: str = "light", fmt: str = "svg") -> bytes:
    """``charon_mp.exe`` in the sandbox: one process, two threads, its files under ``/tmp``."""
    pal = PALETTES[palette]
    fill, arrow, b = pal["fill"], pal["arrow"], STYLE["mpi"]
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["mpi_size_in"])
        ax = _axes(fig)
        _rect(ax, b["container"], fill["container"], edge=arrow)
        x0, _, _, y1 = b["container"]
        ax.text(x0 + 0.03, y1 - 0.03, "\n".join(MPI_BOXES["container"]), ha="left", va="top")
        _rect(ax, b["process"], fill["stage"])
        x0, _, x1, y1 = b["process"]
        ax.text((x0 + x1) / 2, y1 - 0.02, "\n".join(MPI_BOXES["process"]), ha="center", va="top")
        for key, role in (("main", "image"), ("progress", "inputs"), ("tmp", "base")):
            _rect(ax, b[key], fill[role])
        _rect(ax, b["absent"], fill["container"], edge=arrow, dashed=True)
        for key in ("main", "progress", "tmp", "absent"):
            x0, y0, x1, y1 = b[key]
            ax.text((x0 + x1) / 2, (y0 + y1) / 2, "\n".join(MPI_BOXES[key]), ha="center",
                    va="center")  # fmt: skip
        # the process writes its session directory under /tmp
        tx0, _, tx1, ty1 = b["tmp"]
        pad = STYLE["pad"]
        _arrow(ax, ((tx0 + tx1) / 2, b["process"][1] - pad), ((tx0 + tx1) / 2, ty1 + pad), arrow)
        cx0, cy0, cx1, _ = b["container"]
        ax.text((cx0 + cx1) / 2, (cy0 + b["tmp"][1]) / 2, "\n".join(MPI_BOXES["env"]),
                ha="center", va="center")  # fmt: skip
        return _save(fig, fmt)


def _ci_box(ax, key: str, lines: tuple[str, ...], role: str, pal: dict, dashed: bool = False):
    x, y, w = STYLE["ci"][key]
    h = STYLE["ci_box_h"]
    edge = pal["arrow"] if dashed else None
    _rect(ax, (x - w / 2, y - h / 2, x + w / 2, y + h / 2), pal["fill"][role], edge, dashed)
    ax.text(x, y, "\n".join(lines), ha="center", va="center")


def _ci_edge(key: str, side: str) -> tuple[float, float]:
    x, y, _ = STYLE["ci"][key]
    half = STYLE["ci_box_h"] / 2 + STYLE["pad"]
    return (x, y - half) if side == "bottom" else (x, y + half)


def _ci_side(key: str, side: str) -> tuple[float, float]:
    x, y, w = STYLE["ci"][key]
    half = w / 2 + STYLE["pad"]
    return (x + half, y) if side == "right" else (x - half, y)


def charon_ci(palette: str = "light", fmt: str = "svg") -> bytes:
    """The charon-libs entry of build-push: the gate, the build, three checks in turn, the tags."""
    pal = PALETTES[palette]
    arrow = pal["arrow"]
    with matplotlib.rc_context(_rc(palette)):
        fig = Figure(figsize=STYLE["ci_size_in"])
        ax = _axes(fig)
        _ci_box(ax, "trigger", CI_BOXES["trigger"], "inputs", pal)
        _ci_box(ax, "gate", CI_BOXES["gate"], "base", pal)
        _ci_box(ax, "build", CI_BOXES["build"], "stage", pal)
        _ci_box(ax, "skip", CI_BOXES["skip"], "container", pal, dashed=True)
        for key, (_, lines) in CI_CHECKS.items():
            _ci_box(ax, key, lines, "check", pal)
        _ci_box(ax, "publish", CI_BOXES["publish"], "image", pal)
        _arrow(ax, _ci_edge("trigger", "bottom"), _ci_edge("gate", "top"), arrow)
        gate_bottom_y = _ci_edge("gate", "bottom")[1]
        dx = STYLE["ci_label_dx"]
        for key, word in (("build", "yes"), ("skip", "no")):
            top = _ci_edge(key, "top")
            _arrow(ax, (top[0], gate_bottom_y), top, arrow)
            ax.text(top[0] + dx, (gate_bottom_y + top[1]) / 2, word, ha="left", va="center")
        # the checks run in turn; a failed one ends the job before the tags
        checks = list(CI_CHECKS)
        _arrow(ax, _ci_edge("build", "bottom"), _ci_edge(checks[0], "top"), arrow)
        for a, b in pairwise(checks):
            _arrow(ax, _ci_side(a, "right"), _ci_side(b, "left"), arrow)
        _arrow(ax, _ci_edge(checks[-1], "bottom"), _ci_edge("publish", "top"), arrow)
        return _save(fig, fmt)


#: Every figure of the image page, by file name stem; each is drawn once per palette.
FIGURES: dict[str, Callable[[str], bytes]] = {
    "charon-stages": charon_stages,
    "charon-mpi": charon_mpi,
    "charon-ci": charon_ci,
}


def write_all(out_dir: Path) -> None:
    """Write every figure of :data:`FIGURES` as ``<name>-light.svg`` and ``<name>-dark.svg``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, draw in FIGURES.items():
        for palette in PALETTES:
            (out / f"{name}-{palette}.svg").write_bytes(draw(palette))
