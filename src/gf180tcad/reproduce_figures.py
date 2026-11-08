# SPDX-License-Identifier: Apache-2.0
"""The figures of the reproduce pages (``docs/reproduce/``), each in a light and a dark twin.

Each figure is drawn from committed files only: the :repo:`Makefile`, the SPICE reference
(``results/spice``), the generator registry (``src/gf180tcad/generators.json``), the workflow
``.github/workflows/crosscheck.yml``, the output-cache configuration (``data/output-cache.json``)
and the committed 2D job records, the render-manifest fixture
(``tests/fixtures/renders/r-test.render.json``), the display values of the renders
(``data/render/display.toml``), the dev-HEAD image's input list
(``docker/tcad-dev/upstream.json``), meshwell's mesh of the unit square in each TCAD image
(``data/images/meshwell-square.json``) and :data:`gf180tcad.tcad.RESULTS_IMAGE`.

The box diagrams use the colours and boxes of :mod:`gf180tcad.imagefig`, whose contrast is
tested; the plots use those of the explainer figures (:mod:`gf180tcad.explain.figures`).
:func:`write_all` writes each figure as ``<name>-light.svg`` and ``<name>-dark.svg`` into
``docs/_generated/reproduce/`` at docs build time (:func:`gf180tcad.docgen.generate`). A page
embeds both twins, and the theme shows one.

No number is typed below except in :data:`STYLE` (sizes, offsets) and :data:`UNITS` (unit
conversions), so a figure's data come only from the committed files (tested). No generator
imports this module, so it is outside every hashed closure.
"""

from __future__ import annotations

import json
import re
import textwrap
import tomllib
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch

from gf180tcad import imagefig, outcache
from gf180tcad.devices import DEVICES, geometry_id
from gf180tcad.explain import figures as ef
from gf180tcad.sandbox import REPO_ROOT

STYLE = {
    "width_in": 6.4,
    # The box diagrams: the height of one row of boxes, and the room above and below them (in).
    "row_in": 0.72,
    # The workflow figures: one row per step, most of one line.
    "step_row_in": 0.56,
    # A row's centre lies this share of the row below its top.
    "mid": 0.5,
    # The push and pull arrows sit one of this many parts of a box's height inside its edges.
    "arrow_parts": 3,
    # The forks figure: a row tall enough for a fork's commit and three lines of its fix.
    "fork_row_in": 1.15,
    # The forks figure's columns: a wide one for each fork and its fix, a narrow one for where
    # it enters.
    "fork_left": (0.33, 0.62),
    "fork_right": (0.82, 0.29),
    "pad_in": 0.25,
    # A box fills this share of its row's height; the rest is the gap the arrow crosses.
    "box_share": 0.78,
    # Box text wraps at this many characters for a full-width box (12 pt on 6.4 in).
    "wrap_chars": 52,
    # Centre and width of a full-width box, and of the left and right columns, as fractions.
    "full": (0.5, 0.92),
    "left": (0.25, 0.46),
    "right": (0.76, 0.44),
    # The arrow label sits this far right of its arrow, as a fraction of the width.
    "label_dx": 0.02,
    # A commit is named by this many hex digits, a sha256 in the cache tree by this many.
    "short_sha": 7,
    "tree_sha": 12,
    # The cache tree: the height of one line of text (in).
    "tree_line_in": 0.3,
    # The jobs grid: the figure's size, and the marker size (pt).
    "grid_in": (6.4, 6.4),
    "marker_pt": 13.0,
    "tick_deg": 90,
    # The stack of the exaggeration figure: the bar width, and the label offset (fraction).
    "stack_in": (6.4, 4.8),
    "bar_width": 0.6,
    "label_lift": 0.02,
    # The band-offset figure: its size, the x extent of the oxide and the silicon, and where
    # the gap arrows sit inside each.
    "bands_in": (6.4, 5.6),
    "oxide_x": (0.0, 1.0),
    "silicon_x": (1.0, 2.0),
    "arrow_at": 0.5,
    "line_width": 2.4,
    # The meshwell-square figure: its size, the width of a triangle's edges (pt), and the
    # margin round the unit square, as a fraction of its side.
    "square_in": (6.4, 3.7),
    "edge_width": 1.2,
    "square_margin": 0.08,
}

#: Unit conversions: the nanometres in one of each length unit of a render manifest.
UNITS = {"nm_per": {"nm": 1.0, "um": 1e3}}

#: The Makefile whose ``reproduce`` recipe :func:`reproduce_figure` draws.
MAKEFILE = REPO_ROOT / "Makefile"
#: The committed SPICE reference, whose job folders :func:`jobs_figure` draws.
SPICE_ROOT = REPO_ROOT / "results" / "spice"
#: The committed TCAD results: the 2D job records and the plugin commit.
TCAD_ROOT = REPO_ROOT / "results" / "tcad"
#: The generator registry that :func:`registry_figure` draws.
REGISTRY = REPO_ROOT / "src" / "gf180tcad" / "generators.json"
#: The cross-check workflow whose job steps :func:`crosscheck_figure` draws.
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "crosscheck.yml"
#: The synthetic render manifest that :func:`exaggeration_figure` draws.
RENDER_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "renders" / "r-test.render.json"
#: The display values of the renders that :func:`band_offset_figure` draws.
DISPLAY = REPO_ROOT / "data" / "render" / "display.toml"
#: The input list of the dev-HEAD image, which names the forks it builds.
DEV_INPUTS = REPO_ROOT / "docker" / "tcad-dev" / "upstream.json"
#: The submodule list, which names the plugin fork.
GITMODULES = REPO_ROOT / ".gitmodules"
#: meshwell's mesh of the unit square in each TCAD image, recorded by ``tools/meshwell-square``.
MESHWELL_SQUARE = REPO_ROOT / "data" / "images" / "meshwell-square.json"
#: The panels of :func:`meshwell_square_figure`: the record's key and the image's name.
SQUARE_PANELS = (("stable", "stable image"), ("dev", "dev-HEAD image"))

#: The example of a partial run on the reproduce page: one engine, one corner, one device.
EXAMPLE_RUN = {"engine": "ngspice", "corner": "typical", "device": "nfet_05v0"}


# --- the box diagrams ---------------------------------------------------------------------------


def _wrap(text: str, share: float = 1.0) -> list[str]:
    return textwrap.wrap(text, int(STYLE["wrap_chars"] * share), break_on_hyphens=False)


def _diagram(rows: float, palette: str, row_in: float | None = None):
    pal = imagefig.PALETTES[palette]
    row_in = row_in or STYLE["row_in"]
    height = row_in * rows + 2 * STYLE["pad_in"]
    with matplotlib.rc_context(imagefig.palette_rc(palette)):
        fig = Figure(figsize=(STYLE["width_in"], height))
        FigureCanvasAgg(fig)
        fig.set_facecolor(pal["background"])
        ax = fig.add_axes((0, 0, 1, 1))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, height)
        ax.axis("off")
        ax.set_facecolor(pal["background"])
    fig.row_in = row_in
    return fig, ax


def _row_y(fig: Figure, row: float) -> float:
    """The centre height (in) of row ``row`` from the top, rows counted from 0."""
    return fig.get_figheight() - STYLE["pad_in"] - fig.row_in * (row + STYLE["mid"])


def _box(ax, key: str, lines: list[str], at: tuple[float, float, float], role: str,
         palette: str, dashed: bool = False) -> tuple[float, float, float, float]:  # fmt: skip
    """Draw one box centred at (x, y) of width w; return its (x0, y0, x1, y1)."""
    pal = imagefig.PALETTES[palette]
    x, y, w = at
    h = ax.figure.row_in * STYLE["box_share"]
    patch = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h, boxstyle=f"round,pad={imagefig.STYLE['pad']}",
        facecolor=pal["fill"][role], edgecolor=pal["arrow"] if dashed else "none",
        linewidth=imagefig.STYLE["edge_width"] if dashed else 0,
        linestyle="--" if dashed else "-", gid=f"box {key}",
    )  # fmt: skip
    ax.add_patch(patch)
    ax.text(x, y, "\n".join(lines), ha="center", va="center", gid=f"text {key}",
            color=pal["text"], fontsize=imagefig.STYLE["text_pt"])  # fmt: skip
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def _top(box: tuple[float, float, float, float]) -> float:
    return box[-1]


def _bottom(box: tuple[float, float, float, float]) -> float:
    _, y0, _, _ = box
    return y0


def _centre_x(box: tuple[float, float, float, float]) -> float:
    x0, _, x1, _ = box
    return (x0 + x1) / 2


def _arrow(ax, key: str, start: tuple[float, float], end: tuple[float, float], palette: str,
           label: str | None = None) -> None:  # fmt: skip
    colour = imagefig.PALETTES[palette]["arrow"]
    a = ax.annotate("", xy=end, xytext=start, arrowprops={
        "arrowstyle": "-|>", "color": colour, "lw": imagefig.STYLE["arrow_width"],
        "shrinkA": 0, "shrinkB": 0})  # fmt: skip
    a.set_gid(f"arrow {key}")
    if label:
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        ax.text(mx + STYLE["label_dx"], my, label, ha="left", va="center",
                color=imagefig.PALETTES[palette]["text"], fontsize=imagefig.STYLE["text_pt"], gid=f"label {key}")  # fmt: skip


def _chain(rows: list[tuple[str, list[str], str, bool]], palette: str,
           row_in: float | None = None):  # fmt: skip
    """Full-width boxes top to bottom, each joined to the next by an arrow."""
    fig, ax = _diagram(len(rows), palette, row_in)
    x, w = STYLE["full"]
    boxes = {}
    for i, (key, lines, role, dashed) in enumerate(rows):
        boxes[key] = _box(ax, key, lines, (x, _row_y(fig, i), w), role, palette, dashed)
    for a, b in pairwise(key for key, *_ in rows):
        _arrow(ax, f"{a}->{b}", (x, _bottom(boxes[a])), (x, _top(boxes[b])), palette)
    return fig


def _two_columns(left: list[tuple[str, list[str], str]], right: list[tuple[str, list[str], str]],
                 edges: list[tuple[str, str]], palette: str,
                 row_in: float | None = None,
                 columns: tuple[str, str] = ("left", "right")):  # fmt: skip
    """Two columns of boxes, each column spread over the taller one's rows, with an arrow from
    the right edge of each left box to the left edge of the right box it names."""
    rows = max(len(left), len(right))
    fig, ax = _diagram(rows, palette, row_in)
    boxes = {}
    for column, side in ((left, columns[0]), (right, columns[1])):
        x, w = STYLE[side]
        step = rows / len(column)
        for i, (key, lines, role) in enumerate(column):
            y = _row_y(fig, step * (i + STYLE["mid"]) - STYLE["mid"])
            boxes[key] = _box(ax, key, lines, (x, y, w), role, palette)
    for a, b in edges:
        (_, ay0, ax1, ay1), (bx0, by0, _, by1) = boxes[a], boxes[b]
        _arrow(ax, f"{a}->{b}", (ax1, (ay0 + ay1) / 2), (bx0, (by0 + by1) / 2), palette)
    return fig


def _svg(fig: Figure, palette: str) -> bytes:
    """The SVG bytes of ``fig`` with the deterministic settings of :mod:`gf180tcad.plots` (text
    kept as text, fixed hash salt, no date) on the background of ``palette``."""
    with matplotlib.rc_context(ef.palette_rc(palette)):
        return ef.svg_bytes(fig)


# --- make reproduce: the Makefile's chain of targets ----------------------------------------------


def _recipe(target: str, text: str) -> list[str]:
    """The recipe lines of ``target`` in ``text`` (a Makefile), continuation lines joined."""
    m = re.search(rf"^{re.escape(target)}:[^\n]*\n((?:\t[^\n]*\n)+)", text, re.MULTILINE)
    if not m:
        raise ValueError(f"no target {target} in the Makefile")
    body = m.group(1).replace("\\\n", " ")
    return [" ".join(line.split()) for line in body.splitlines() if line.strip()]


def reproduce_steps(makefile: Path = MAKEFILE) -> list[tuple[str, list[str]]]:
    """The steps of ``make reproduce`` in order: each sub-make target with the results folders
    its recipe writes (``--out``), then each other recipe line as a command with no target."""
    text = makefile.read_text(encoding="utf-8")
    steps = []
    for line in _recipe("reproduce", text):
        if m := re.fullmatch(r"\$\(MAKE\) ((?:-\S+ )*)(\S+)", line):
            flags, target = m.groups()
            outs = []
            for sub in _recipe(target, text):
                for out in re.findall(r"--out (\S+)", sub):
                    if out not in outs:
                        outs.append(out)
            steps.append((flags + target, outs))
        else:
            steps.append((re.sub(r"^\$\(PYTHON\) ", "python ", line), []))
    return steps


def reproduce_figure(palette: str):
    """The targets of ``make reproduce`` in the order it runs them, each with what it writes,
    then the manifest check."""
    rows = []
    for i, (step, outs) in enumerate(reproduce_steps()):
        if outs:
            lines = [f"make {step}", *_wrap("writes " + ", ".join(outs))]
            rows.append((step.split()[-1], lines, "stage", False))
        else:
            rows.append((f"command {i}", _wrap(step), "check", False))
    return _chain(rows, palette)


# --- the jobs of the SPICE reference ---------------------------------------------------------------


def reference_jobs(root: Path = SPICE_ROOT) -> list[tuple[str, str, str, str]]:
    """Every committed job of the SPICE reference, as (engine, corner, device, geometry id): a
    folder with a ``metrics.json``."""
    return sorted(
        tuple(p.parent.relative_to(root).parts) for p in root.glob("*/*/*/*/metrics.json")
    )


def job_grid(jobs: list[tuple[str, str, str, str]]):
    """The rows (engine, corner), the columns (device, geometry id) and each job's (column,
    row) position."""
    rows = sorted({(e, c) for e, c, _, _ in jobs})
    order = {d: [geometry_id(g) for g in DEVICES[d].geometries] for d in DEVICES}
    cols = sorted(
        {(d, g) for _, _, d, g in jobs}, key=lambda dg: (dg[0], order[dg[0]].index(dg[1]))
    )
    pos = {(e, c, d, g): (cols.index((d, g)), rows.index((e, c))) for e, c, d, g in jobs}
    return rows, cols, pos


def _selected(job: tuple[str, str, str, str]) -> bool:
    e, c, d, _ = job
    return (e, c, d) == (EXAMPLE_RUN["engine"], EXAMPLE_RUN["corner"], EXAMPLE_RUN["device"])


def _geometry_label(device: str, gid: str) -> str:
    (g,) = [g for g in DEVICES[device].geometries if geometry_id(g) == gid]
    return f"{device.split('_')[0]} W{g.w_um:g}/L{g.l_um:g}"


def jobs_figure(palette: str, root: Path = SPICE_ROOT):
    """One square per job of the reference: a column per device and geometry, a row per engine
    and corner; the jobs of the page's example partial run highlighted."""
    pal = ef.PALETTES[palette]
    jobs = reference_jobs(root)
    rows, cols, pos = job_grid(jobs)
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = Figure(figsize=STYLE["grid_in"], layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.add_subplot()
        for gid, colour, keep in (
            ("jobs", pal["muted"], False),
            ("selected", pal["highlight"], True),
        ):
            pts = [pos[j] for j in jobs if _selected(j) == keep]
            label = (
                "a job: one folder"
                if not keep
                else "--engine {engine} --corner {corner} --device {device}".format(**EXAMPLE_RUN)
            )
            ax.scatter([p[0] for p in pts], [p[1] for p in pts], marker="s",
                       s=STYLE["marker_pt"] ** 2, color=colour, gid=gid, label=label)  # fmt: skip
        ax.set_xticks(range(len(cols)), [_geometry_label(d, g) for d, g in cols],
                      rotation=STYLE["tick_deg"])  # fmt: skip
        ax.set_yticks(range(len(rows)), [f"{e} {c}" for e, c in rows])
        ax.invert_yaxis()
        ax.set_xlabel("device and geometry")
        ax.set_ylabel("engine and corner")
        fig.legend(loc="outside upper center")
    return fig


# --- the generator registry -----------------------------------------------------------------------


def registry(path: Path = REGISTRY) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def registry_figure(palette: str):
    """The entry points of the registry (left), each with the number of modules its hash covers,
    and the results folders of ``trees`` (right), each joined to the entry point that writes it."""
    reg = registry()
    left = [(ep, [ep, f"{len(mods)} modules hashed"], "stage")
            for ep, mods in sorted(reg["entry_points"].items())]  # fmt: skip
    # The folders grouped by writer, so that the arrows of one writer do not cross another's.
    right = [(tree, [f"results/{tree}"], "image")
             for tree in sorted(reg["trees"], key=lambda t: (reg["trees"][t], t))]  # fmt: skip
    edges = [(writer, tree) for tree, writer in sorted(reg["trees"].items())]
    return _two_columns(left, right, edges, palette)


# --- the cross-check workflow -----------------------------------------------------------------------


def workflow_steps(job: str, path: Path = WORKFLOW) -> list[tuple[str, bool]]:
    """The steps of ``job`` in the workflow, in order: each step's name (an action's name and
    its artefact name for an unnamed step) and whether it runs only on failure."""
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"^  {re.escape(job)}:\n(.*?)(?=^  \S|\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        raise ValueError(f"no job {job} in {path.name}")
    steps = []
    for block in re.split(r"^      - ", m.group(1), flags=re.MULTILINE)[1:]:
        name = re.match(r"name: (.+)", block)
        action = re.match(r"uses: ([^@\s]+)", block)
        artefact = re.search(r"^          name: (\S+)", block, re.MULTILINE)
        if name:
            title = name.group(1).strip()
        elif action and artefact:
            title = f"{action.group(1)}: {artefact.group(1)}"
        elif action:
            title = action.group(1)
        else:
            title = re.match(r"run: (.+)", block).group(1).strip()
        failure = re.search(r"^        if: failure\(\)", block, re.MULTILINE) is not None
        steps.append((title, failure))
    return steps


def _workflow_figure(job: str, palette: str):
    rows = [(f"step {i}", _wrap(title), "container" if failure else "check", failure)
            for i, (title, failure) in enumerate(workflow_steps(job))]  # fmt: skip
    return _chain(rows, palette, STYLE["step_row_in"])


def crosscheck_figure(palette: str):
    """The steps of the ``crosscheck`` job; a dashed box runs only when a step before it failed."""
    return _workflow_figure("crosscheck", palette)


def crosscheck_tcad_figure(palette: str):
    """The steps of the ``crosscheck-tcad`` job, drawn as :func:`crosscheck_figure`."""
    return _workflow_figure("crosscheck-tcad", palette)


# --- the output cache -------------------------------------------------------------------------------


def cached_meshes(root: Path = TCAD_ROOT) -> list[str]:
    """The distinct ``mesh_sha256`` of the committed calibrated 2D jobs, sorted."""
    metas = root.glob("moscap2d/*/calibrated/*/cv.meta.json")
    return sorted({json.loads(p.read_text(encoding="utf-8"))["mesh_sha256"] for p in metas})


def cache_flow_figure(palette: str):
    """Push and pull: a job's file and the hash its committed record names (left), the object
    and the index of the cache repository (right)."""
    config = outcache.load_config()
    (art,) = config["artefacts"]
    sha = cached_meshes()[0]
    obj = outcache.object_relpath(sha, art["ext"], art["compression"])
    obj = obj.replace(sha, sha[: STYLE["tree_sha"]] + "…")
    left = [
        ("file", [f"results/{art['pattern']}", "(git-ignored)"], "stage"),
        ("meta", [f"{art['meta']} names its", f"{art['hash_key']} (committed)"], "inputs"),
    ]
    right = [
        ("object", [obj.rsplit("/", 1)[0] + "/", obj.rsplit("/", 1)[1]], "image"),
        ("index", [outcache.INDEX_NAME, "each sha256 and its object"], "base"),
    ]
    fig, ax = _diagram(len(left) * 2, palette)
    boxes = {}
    for column, side in ((left, "left"), (right, "right")):
        x, w = STYLE[side]
        for i, (key, lines, role) in enumerate(column):
            boxes[key] = _box(
                ax, key, lines, (x, _row_y(fig, 2 * i + STYLE["mid"]), w), role, palette
            )
    _, fy0, fx1, fy1 = boxes["file"]
    ox0 = boxes["object"][0]
    third = (fy1 - fy0) / STYLE["arrow_parts"]
    _arrow(ax, "push", (fx1, fy1 - third), (ox0, fy1 - third), palette)
    _arrow(ax, "pull", (ox0, fy0 + third), (fx1, fy0 + third), palette)
    for key, y in (("push", fy1), ("pull", fy0)):
        ax.text((fx1 + ox0) / 2, y, key, ha="center", va="bottom" if key == "push" else "top",
                color=imagefig.PALETTES[palette]["text"], fontsize=imagefig.STYLE["text_pt"], gid=f"label {key}")  # fmt: skip
    mx = _centre_x(boxes["meta"])
    _arrow(
        ax, "meta->file", (mx, _top(boxes["meta"])), (mx, fy0), palette, "pull checks the sha256"
    )
    ix = _centre_x(boxes["index"])
    _arrow(ax, "index->object", (ix, _top(boxes["index"])), (ix, _bottom(boxes["object"])), palette,
           "lists")  # fmt: skip
    return fig


def cache_tree(root: Path = TCAD_ROOT) -> list[str]:
    """The lines of the cache repository's tree with the objects of :func:`cached_meshes`."""
    config = outcache.load_config()
    (art,) = config["artefacts"]
    paths = [
        outcache.object_relpath(s, art["ext"], art["compression"]) for s in cached_meshes(root)
    ]
    top = outcache.OBJECTS_DIR
    lines = [f"{config['repo_https'].rsplit('/', 1)[1]}/"]
    for name in (outcache.README_NAME, outcache.ATTRIBUTES_NAME, outcache.INDEX_NAME):
        lines.append(f"├── {name}")
    lines.append(f"└── {top}/")
    for i, p in enumerate(paths):
        sub, name = p.removeprefix(top + "/").split("/")
        sha, ext = name.split(".", 1)
        branch = "└──" if i == len(paths) - 1 else "├──"
        lines.append(f"    {branch} {sub}/{sha[: STYLE['tree_sha']]}….{ext}")
    return lines


def cache_tree_figure(palette: str):
    """The cache repository's files: the README, the attributes, the index and one object per
    distinct mesh of the committed calibrated 2D jobs."""
    lines = cache_tree()
    pal = imagefig.PALETTES[palette]
    height = STYLE["tree_line_in"] * len(lines) + 2 * STYLE["pad_in"]
    with matplotlib.rc_context(imagefig.palette_rc(palette)):
        fig = Figure(figsize=(STYLE["width_in"], height))
        FigureCanvasAgg(fig)
        ax = fig.add_axes((0, 0, 1, 1))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, height)
        ax.axis("off")
        for i, line in enumerate(lines):
            y = height - STYLE["pad_in"] - STYLE["tree_line_in"] * (i + STYLE["mid"])
            ax.text(STYLE["full"][0] - STYLE["full"][1] / 2, y, line, ha="left", va="center",
                    family="monospace", color=pal["text"], gid=f"line {i}",
                    fontsize=imagefig.STYLE["text_pt"])  # fmt: skip
    return fig


# --- the render manifest ----------------------------------------------------------------------------


def exaggerated_geometry(path: Path = RENDER_FIXTURE) -> list[dict]:
    """The geometry entries of a render manifest, with their thickness in nm at true scale and
    as the render draws it, and the statement that names a scale other than 1."""
    m = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for name, e in sorted(m["quantities"].items()):
        if e.get("role") != "geometry":
            continue
        nm = e["value"] * UNITS["nm_per"][e["unit"]]
        statement = next((s for s in m["exaggeration"] if s.startswith(e["label"])), None)
        out.append({"name": name, "label": e["label"], "true_nm": nm,
                    "drawn_nm": nm * e["scale"], "statement": statement})  # fmt: skip
    return out


def exaggeration_figure(palette: str):
    """The fixture's stack at true scale (left) and as the render draws it (right): the oxide at
    its scale, the gate at 1."""
    pal = ef.PALETTES[palette]
    layers = exaggerated_geometry()
    colours = {"poly": pal["muted"], "t_ox": pal["highlight_oxide"]}
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = Figure(figsize=STYLE["stack_in"], layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.add_subplot()
        order = sorted(layers, key=lambda la: la["name"] != "t_ox")  # the oxide at the bottom
        for x, key in enumerate(("true_nm", "drawn_nm")):
            bottom = 0.0
            for la in order:
                ax.bar(x, la[key], STYLE["bar_width"], bottom=bottom,
                       color=colours.get(la["name"], pal["intrinsic"]),
                       label=la["label"] if x == 0 else None, gid=f"{key} {la['name']}")  # fmt: skip
                bottom += la[key]
        statements = [la["statement"] for la in order if la["statement"]]
        ax.set_xticks([0, 1], ["true scale", "\n".join(["as the render draws it:", *statements])])
        ax.set_ylabel("height above the silicon surface (nm)")
        ax.legend(loc="upper left")
    return fig


def display_values(path: Path = DISPLAY) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def band_edges(path: Path = DISPLAY) -> dict[str, tuple[float, float]]:
    """The conduction and valence band edges (eV) of silicon and of the oxide, silicon's valence
    edge at 0: the oxide's edges sit the two band offsets above and below silicon's."""
    d = display_values(path)
    si, ox = d["silicon"], d["sio2"]
    ec = si["band_gap_ev"]
    return {
        "silicon": (ec, 0.0),
        "oxide": (ec + ox["conduction_offset_ev"], -ox["valence_offset_ev"]),
    }


def band_offset_figure(palette: str):
    """The band edges of the oxide (left) and silicon (right) at their interface, with the
    silicon band gap and the two offsets of the display file marked."""
    pal = ef.PALETTES[palette]
    edges = band_edges()
    d = display_values()
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = Figure(figsize=STYLE["bands_in"], layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.add_subplot()
        for part, span in (("oxide", STYLE["oxide_x"]), ("silicon", STYLE["silicon_x"])):
            ec, ev = edges[part]
            ax.plot(span, [ec, ec], color=pal["electron"], lw=STYLE["line_width"],
                    gid=f"{part} conduction")  # fmt: skip
            ax.plot(span, [ev, ev], color=pal["hole"], lw=STYLE["line_width"],
                    gid=f"{part} valence")  # fmt: skip
            ax.text(sum(span) / 2, ec, f"{part}: conduction band edge", ha="center",
                    va="bottom", gid=f"label {part} conduction")  # fmt: skip
            ax.text(sum(span) / 2, ev, f"{part}: valence band edge", ha="center", va="top",
                    gid=f"label {part} valence")  # fmt: skip
        si_ec, si_ev = edges["silicon"]
        ox_ec, ox_ev = edges["oxide"]
        x_si = STYLE["silicon_x"][0] + STYLE["arrow_at"] * (
            STYLE["silicon_x"][1] - STYLE["silicon_x"][0]
        )
        x_ox = STYLE["oxide_x"][0] + STYLE["arrow_at"] * (STYLE["oxide_x"][1] - STYLE["oxide_x"][0])
        marks = (
            ("band gap", x_si, si_ev, si_ec, d["silicon"]["band_gap_ev"]),
            ("conduction offset", x_ox, si_ec, ox_ec, d["sio2"]["conduction_offset_ev"]),
            ("valence offset", x_ox, ox_ev, si_ev, d["sio2"]["valence_offset_ev"]),
        )
        for key, x, y0, y1, value in marks:
            a = ax.annotate("", xy=(x, y1), xytext=(x, y0),
                            arrowprops={"arrowstyle": "<|-|>", "color": pal["text"]})  # fmt: skip
            a.set_gid(f"arrow {key}")
            ax.text(x + STYLE["label_lift"], (y0 + y1) / 2, f"{key} {value:g} eV", ha="left",
                    va="center", gid=f"value {key}")  # fmt: skip
        ax.axvline(STYLE["silicon_x"][0], color=pal["muted"], gid="interface")
        ax.set_xticks([])
        ax.set_ylabel(f"energy (eV), silicon's valence band edge at {si_ev:g}")
    return fig


# --- the dev-HEAD image: forks and which image makes which results ---------------------------------


#: The words for where a fork of ``upstream.json`` enters: the image those inputs build.
FORK_DESTINATIONS = {"dev": ["dev-HEAD", "TCAD image"]}


def forks() -> list[dict]:
    """The mithro forks the dev-HEAD image builds (``upstream.json``), and the plugin fork of
    the submodule, each with its commit and where it enters."""
    inputs = json.loads(DEV_INPUTS.read_text(encoding="utf-8"))
    out = []
    for e in inputs.values():
        repo = e.get("repository", "")
        if "/mithro/" in repo:
            fix = e["role"].split("the mithro fork: ", 1)[1]
            out.append({"repo": repo.removeprefix("https://github.com/"), "commit": e["commit"],
                        "fix": fix, "into": "dev"})  # fmt: skip
    sub = re.search(r"path = (\S+)\n\s*url = https://github.com/(\S+?)(?:\.git)?\n",
                    GITMODULES.read_text(encoding="utf-8"))  # fmt: skip
    prov = json.loads((TCAD_ROOT / "moscap1d" / "provenance.json").read_text(encoding="utf-8"))
    out.append({"repo": sub.group(2), "commit": prov["gplugins_commit"], "fix": None,
                "into": sub.group(1)})  # fmt: skip
    return out


def forks_figure(palette: str):
    """Each fork at its commit (left) and where it enters the flow (right)."""
    fs = forks()
    left = []
    for f in fs:
        head = f"{f['repo']} at {f['commit'][: STYLE['short_sha']]}"
        fix = _wrap(f["fix"], STYLE["fork_left"][1]) if f["fix"] else []
        left.append((f["repo"], [head, *fix], "inputs"))
    dests = []
    for f in fs:
        if f["into"] not in dests:
            dests.append(f["into"])
    right = [(d, FORK_DESTINATIONS[d] if d in FORK_DESTINATIONS else
              ["plugin submodule", *(part + "/" for part in d.split("/")[:-1]), d.split("/")[-1]],
              "image") for d in dests]  # fmt: skip
    edges = [(f["repo"], f["into"]) for f in fs]
    return _two_columns(left, right, edges, palette, STYLE["fork_row_in"],
                        ("fork_left", "fork_right"))  # fmt: skip


def results_images_figure(palette: str):
    """Each result kind of :data:`gf180tcad.tcad.RESULTS_IMAGE` (left) and the image it is
    made in (right), by the image's pin file."""
    from gf180tcad.tcad import RESULTS_IMAGE

    images = registry()["images"]
    left = [(kind, [f"results/tcad/{kind}", f"results/tcad/meshconv/{kind}"], "stage")
            for kind in sorted(RESULTS_IMAGE)]  # fmt: skip
    right = [(img, [f"{img} image", images[img]["pin"]], "image") for img in sorted(images)]
    return _two_columns(left, right, sorted(RESULTS_IMAGE.items()), palette)


# --- every figure -------------------------------------------------------------------------------------


def meshwell_square(path: Path = MESHWELL_SQUARE) -> dict:
    """The record of ``tools/meshwell-square``: per image, its pin, the gmsh version, the points
    (x, y) and the triangles and boundary lines as point numbers."""
    return json.loads(path.read_text(encoding="utf-8"))


def meshwell_square_figure(palette: str):
    """meshwell's mesh of the unit square in the stable image (left) and the dev-HEAD image
    (right): each triangle's edges, and each point at its place with its number in that
    image's mesh."""
    pal = ef.PALETTES[palette]
    record = meshwell_square()
    margin = STYLE["square_margin"]
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = Figure(figsize=STYLE["square_in"], layout="constrained")
        FigureCanvasAgg(fig)
        axes = fig.subplots(1, len(SQUARE_PANELS))
        for ax, (key, name) in zip(axes, SQUARE_PANELS, strict=True):
            mesh = record[key]
            xs = [p[0] for p in mesh["points"]]
            ys = [p[1] for p in mesh["points"]]
            for i, tri in enumerate(mesh["triangles"]):
                loop = [*tri, tri[0]]
                ax.plot([xs[j] for j in loop], [ys[j] for j in loop], color=pal["muted"],
                        lw=STYLE["edge_width"], gid=f"{key} triangle {i}")  # fmt: skip
            for i, (x, y) in enumerate(mesh["points"]):
                ax.text(x, y, f"{i}", ha="center", va="center", gid=f"{key} point {i}",
                        bbox={"boxstyle": "round", "fc": pal["background"],
                              "ec": pal["text"]})  # fmt: skip
            ax.set_title(f"{name}, gmsh {mesh['gmsh']}")
            ax.set_xlim(min(xs) - margin, max(xs) + margin)
            ax.set_ylim(min(ys) - margin, max(ys) + margin)
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
    return fig


def _svg_of(draw: Callable) -> Callable[[str], bytes]:
    def svg(palette: str = "light") -> bytes:
        return _svg(draw(palette), palette)

    svg.__doc__ = draw.__doc__
    return svg


#: The figure functions, by file name stem. Each returns the matplotlib figure of one palette.
DRAW: dict[str, Callable] = {
    "image-forks": forks_figure,
    "meshwell-square": meshwell_square_figure,
    "results-images": results_images_figure,
    "reproduce-targets": reproduce_figure,
    "reference-jobs": jobs_figure,
    "tcad-registry": registry_figure,
    "crosscheck-steps": crosscheck_figure,
    "crosscheck-tcad-steps": crosscheck_tcad_figure,
    "output-cache-flow": cache_flow_figure,
    "output-cache-tree": cache_tree_figure,
    "render-exaggeration": exaggeration_figure,
    "render-band-offsets": band_offset_figure,
}

#: Every figure of the reproduce pages as SVG bytes, by file name stem.
FIGURES: dict[str, Callable[[str], bytes]] = {name: _svg_of(draw) for name, draw in DRAW.items()}


def write_all(out_dir: Path) -> None:
    """Write every figure of :data:`FIGURES` as ``<name>-light.svg`` and ``<name>-dark.svg``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, draw in FIGURES.items():
        for palette in ("light", "dark"):
            (out / f"{name}-{palette}.svg").write_bytes(draw(palette))
