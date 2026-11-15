# SPDX-License-Identifier: Apache-2.0
"""The figures of the reproduce pages (gf180tcad.reproduce_figures): deterministic light and dark
twins, drawn from the committed files, each embedded as a pair and cited on its page. The
expected values are read here from the committed files, never from the pages' prose."""

import ast
import json
import os
import re
import subprocess
import sys
import textwrap
import tomllib

import pytest
from optional import importorskip

importorskip("matplotlib", reason="needs the docs dependency group")

import itertools

import numpy as np
import test_explained
from matplotlib.collections import PathCollection
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.text import Annotation
from test_explained import numeric_literals

from gf180tcad import imagefig
from gf180tcad import reproduce_figures as rf
from gf180tcad.devices import DEVICES, geometry_id
from gf180tcad.explain import figures as ef
from gf180tcad.sandbox import REPO_ROOT

PAGES = sorted((REPO_ROOT / "docs" / "reproduce").glob("*.md"))
SRC = REPO_ROOT / "src" / "gf180tcad" / "reproduce_figures.py"

# Every figure (test_figures_listed_here_are_all_the_figures holds the list complete).
FIGURES = [
    "image-forks",
    "meshwell-square",
    "results-images",
    "reproduce-targets",
    "reference-jobs",
    "tcad-registry",
    "tcad-inputs",
    "crosscheck-steps",
    "crosscheck-tcad-steps",
    "output-cache-flow",
    "output-cache-tree",
    "render-exaggeration",
    "render-band-offsets",
]

_RENDER = textwrap.dedent(
    """
    import sys
    from gf180tcad import reproduce_figures
    sys.stdout.buffer.write(reproduce_figures.FIGURES[sys.argv[1]](sys.argv[2]))
    """
)


def test_figures_listed_here_are_all_the_figures():
    assert sorted(FIGURES) == sorted(rf.FIGURES) == sorted(rf.DRAW)


@pytest.mark.parametrize("figure", FIGURES)
@pytest.mark.parametrize("palette", ["light", "dark"])
def test_svg_deterministic(figure, palette):
    """Two fresh processes with different hash seeds give the same bytes, with text kept as text,
    no date and no host path."""
    runs = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run(
            [sys.executable, "-c", _RENDER, figure, palette],
            env=env, capture_output=True, check=True, timeout=300,
        )  # fmt: skip
        runs.append(r.stdout)
    a, b = runs
    assert a.startswith(b"<?xml") and b"<text" in a and a == b
    assert b"<dc:date>" not in a and str(REPO_ROOT).encode() not in a


def test_figures_have_dark_twins_and_every_page_embeds_pairs(tmp_path):
    rf.write_all(tmp_path)
    for name in FIGURES:
        light = (tmp_path / f"{name}-light.svg").read_bytes()
        assert light != (tmp_path / f"{name}-dark.svg").read_bytes(), name
    used = set()
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        for name in set(re.findall(r"/_generated/reproduce/([\w-]+)-light\.svg", text)):
            if name not in rf.FIGURES:
                continue  # a figure of gf180tcad.imagefig
            light = f"```{{figure}} /_generated/reproduce/{name}-light.svg\n:name: {name}\n:figclass: only-light\n"
            dark = f"```{{figure}} /_generated/reproduce/{name}-dark.svg\n:figclass: only-dark\n"
            assert light in text and dark in text, (page.name, name)
            assert text.index(light) < text.index(dark), (page.name, name)
            assert f"{{numref}}`{name}`" in text, (page.name, name)
            used.add(name)
    assert used == set(rf.FIGURES), f"drawn but on no page: {sorted(set(rf.FIGURES) - used)}"


# --- the expected values, read from the committed files -----------------------------------------
#
# Each check asserts the full text of every text the figure draws (box texts, labels, ticks,
# legend entries, axis labels) and both ends of every arrow, against values read here from the
# committed files. test_every_text_and_arrow_is_checked changes each in turn and requires the
# check to fail.

GITHUB = "https://github.com/"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _plain_texts(fig) -> list:
    return [t for ax in fig.axes for t in ax.texts if not isinstance(t, Annotation)]


def _annotations(fig) -> list:
    return [t for ax in fig.axes for t in ax.texts if isinstance(t, Annotation)]


def assert_texts(fig, want: dict[str, str]):
    """The figure's texts, by gid, are exactly ``want`` (whitespace and line breaks aside)."""
    got = {}
    for t in _plain_texts(fig):
        assert t.get_gid(), f"a text without a gid: {t.get_text()!r}"
        got[t.get_gid()] = _flat(t.get_text())
    assert got == {k: _flat(v) for k, v in want.items()}


def _box(fig, key: str) -> tuple[float, float, float, float]:
    (p,) = [p for ax in fig.axes for p in ax.patches if p.get_gid() == f"box {key}"]
    return p.get_x(), p.get_y(), p.get_x() + p.get_width(), p.get_y() + p.get_height()


def _on_edge(pt, box, tol=1e-9) -> bool:
    x, y = pt
    x0, y0, x1, y1 = box
    on_side = min(abs(x - x0), abs(x - x1)) < tol and y0 - tol <= y <= y1 + tol
    on_cap = min(abs(y - y0), abs(y - y1)) < tol and x0 - tol <= x <= x1 + tol
    return on_side or on_cap


def assert_box_texts_inside(fig, keys):
    """Each box's text sits inside that box: its anchor, and its drawn extent (no line runs past
    the box's edges)."""
    renderer = fig.canvas.get_renderer()
    for key in keys:
        (t,) = [t for t in _plain_texts(fig) if t.get_gid() == f"text {key}"]
        x0, y0, x1, y1 = _box(fig, key)
        x, y = t.get_position()
        assert x0 <= x <= x1 and y0 <= y <= y1, key
        (p,) = [p for ax in fig.axes for p in ax.patches if p.get_gid() == f"box {key}"]
        text, box = t.get_window_extent(renderer), p.get_window_extent(renderer)
        assert box.x0 <= text.x0 and text.x1 <= box.x1, (key, "runs past the box", text, box)
        assert box.y0 <= text.y0 and text.y1 <= box.y1, (key, "runs past the box", text, box)


def assert_box_arrows(fig, edges: dict[str, tuple[str, str]]):
    """The arrows are exactly ``edges`` (key -> (from box, to box)); each starts on the edge of
    its first box and ends on the edge of its second."""
    arrows = {a.get_gid(): a for a in _annotations(fig)}
    assert set(arrows) == {f"arrow {k}" for k in edges}
    for key, (src, dst) in edges.items():
        a = arrows[f"arrow {key}"]
        assert a.get_text() == ""
        assert _on_edge(a.xyann, _box(fig, src)), (key, "start", a.xyann)
        assert _on_edge(a.xy, _box(fig, dst)), (key, "end", a.xy)


def _ticks(axis) -> list[str]:
    return [t.get_text() for t in axis.get_ticklabels()]


def _legend(fig) -> list[str]:
    legends = [*fig.legends, *[ax.get_legend() for ax in fig.axes if ax.get_legend()]]
    return [t.get_text() for lg in legends for t in lg.get_texts()]


def _chain_edges(keys: list[str]) -> dict[str, tuple[str, str]]:
    return {f"{a}->{b}": (a, b) for a, b in itertools.pairwise(keys)}


def check_reproduce_targets(fig):
    make = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = re.search(r"^reproduce:\n((?:\t.*\n)+)", make, re.MULTILINE).group(1).splitlines()
    want, keys = {}, []
    for i, line in enumerate(recipe):
        line = line.strip()
        if line.startswith("$(MAKE) "):
            make_args = line.split()[1:]
            target = make_args[-1]
            body = re.search(rf"^{target}:.*\n((?:\t.*\n)+)", make, re.MULTILINE).group(1)
            outs = list(dict.fromkeys(re.findall(r"--out (\S+)", body.replace("\\\n", " "))))
            assert outs, target
            want[f"text {target}"] = f"make {' '.join(make_args)} writes " + ", ".join(outs)
            keys.append(target)
        else:
            want[f"text command {i}"] = line.replace("$(PYTHON) ", "python ")
            keys.append(f"command {i}")
    assert_texts(fig, want)
    assert_box_texts_inside(fig, keys)
    assert_box_arrows(fig, _chain_edges(keys))


def check_reference_jobs(fig):
    root = REPO_ROOT / "results" / "spice"
    jobs = sorted(tuple(p.parent.relative_to(root).parts) for p in root.rglob("metrics.json"))
    assert jobs
    rows = sorted({j[:2] for j in jobs})
    cols = [(d, g) for d in sorted(DEVICES) for g in DEVICES[d].geometries]
    cols = [(d, g) for d, g in cols if any(j[2:] == (d, geometry_id(g)) for j in jobs)]
    col_ids = [(d, geometry_id(g)) for d, g in cols]
    example = rf.EXAMPLE_RUN
    (ax,) = fig.axes
    for gid, keep in (("jobs", False), ("selected", True)):
        want = [
            (col_ids.index(j[2:]), rows.index(j[:2]))
            for j in jobs
            if (j[:3] == (example["engine"], example["corner"], example["device"])) == keep
        ]
        (coll,) = [c for c in ax.collections if c.get_gid() == gid]
        assert np.array_equal(coll.get_offsets(), np.array(want, float)), gid
    assert _ticks(ax.yaxis) == [f"{e} {c}" for e, c in rows]
    assert _ticks(ax.xaxis) == [f"{d.split('_')[0]} W{g.w_um:g}/L{g.l_um:g}" for d, g in cols]
    assert _legend(fig) == [
        "a job: one folder",
        f"--engine {example['engine']} --corner {example['corner']} --device {example['device']}",
    ]
    assert (ax.get_xlabel(), ax.get_ylabel()) == ("device and geometry", "engine and corner")
    assert_texts(fig, {})
    assert not _annotations(fig)


def _registry() -> dict:
    return json.loads((REPO_ROOT / "src" / "gf180tcad" / "generators.json").read_text("utf-8"))


def check_tcad_registry(fig):
    reg = _registry()
    want = {f"text {ep}": f"{ep} {len(m)} modules hashed" for ep, m in reg["entry_points"].items()}
    want |= {f"text {tree}": f"results/{tree}" for tree in reg["trees"]}
    assert_texts(fig, want)
    assert_box_texts_inside(fig, [*reg["entry_points"], *reg["trees"]])
    assert_box_arrows(fig, {f"{w}->{t}": (w, t) for t, w in reg["trees"].items()})


def check_tcad_inputs(fig):
    reg = _registry()["input_trees"]
    sources = {p for prefixes in reg.values() for p in prefixes}

    def drawn(path: str) -> str:
        # a path longer than STYLE["folder_chars"] is drawn on two lines, split before its last
        # two parts (the moscap2d cells)
        if len(path) <= rf.STYLE["folder_chars"]:
            return path
        head, a, b = path.rsplit("/", 2)
        return f"{head}/ {a}/{b}"

    want = {f"text input {p}": drawn(f"results/{p}") for p in sources}
    assert sum(" " in v for v in want.values()) == 2  # the two moscap2d cells
    want |= {f"text {t}": f"results/{t}" for t in reg}
    assert_texts(fig, want)
    assert_box_texts_inside(fig, [*(f"input {p}" for p in sources), *reg])
    assert_box_arrows(
        fig, {f"input {p}->{t}": (f"input {p}", t) for t, ps in reg.items() for p in ps}
    )


def _steps(job: str) -> list[tuple[str, bool]]:
    """Each step of ``job``: its name (an action's name and its artefact for an unnamed step,
    or its command) and whether it runs only on failure."""
    text = (REPO_ROOT / ".github" / "workflows" / "crosscheck.yml").read_text("utf-8")
    block = text.split(f"\n  {job}:\n", 1)[1].split("\n\n  ", 1)[0]
    steps = []
    for item in block.split("\n      - ")[1:]:
        first, *rest = item.split("\n")
        kind, value = first.split(": ", 1)
        if kind == "uses":
            value = value.split("@")[0]
            named = [ln.split(": ", 1)[1] for ln in rest if ln.startswith("          name: ")]
            value = f"{value}: {named[0]}" if named else value
        steps.append((value.strip(), "        if: failure()" in rest))
    return steps


def _check_steps(job: str):
    def check(fig):
        steps = _steps(job)
        assert steps
        assert_texts(fig, {f"text step {i}": title for i, (title, _) in enumerate(steps)})
        keys = [f"step {i}" for i in range(len(steps))]
        assert_box_texts_inside(fig, keys)
        assert_box_arrows(fig, _chain_edges(keys))
        for i, (_, failure) in enumerate(steps):
            (p,) = [p for p in fig.axes[0].patches if p.get_gid() == f"box step {i}"]
            assert (p.get_linestyle() == "--") == failure, i

    return check


def _calibrated_meshes() -> list[str]:
    metas = (REPO_ROOT / "results" / "tcad" / "moscap2d").glob("*/calibrated/*/cv.meta.json")
    return sorted({json.loads(p.read_text("utf-8"))["mesh_sha256"] for p in metas})


def _cache_config() -> dict:
    return json.loads((REPO_ROOT / "data" / "output-cache.json").read_text("utf-8"))


def _object_name(sha: str, art: dict) -> str:
    gz = {"gzip": ".gz"}[art["compression"]]
    return f"{sha[:12]}….{art['ext']}{gz}"


def check_cache_flow(fig):
    (art,) = _cache_config()["artefacts"]
    sha = _calibrated_meshes()[0]
    assert_texts(fig, {
        "text file": f"results/{art['pattern']} (git-ignored)",
        "text meta": f"{art['meta']} names its {art['hash_key']} (committed)",
        "text object": f"objects/sha256/{sha[:2]}/ {_object_name(sha, art)}",
        "text index": "index.json each sha256 and its object",
        "label push": "push",
        "label pull": "pull",
        "label meta->file": "pull checks the sha256",
        "label index->object": "lists",
    })  # fmt: skip
    assert_box_texts_inside(fig, ["file", "meta", "object", "index"])
    assert_box_arrows(fig, {
        "push": ("file", "object"),
        "pull": ("object", "file"),
        "meta->file": ("meta", "file"),
        "index->object": ("index", "object"),
    })  # fmt: skip


def check_cache_tree(fig):
    config = _cache_config()
    (art,) = config["artefacts"]
    shas = _calibrated_meshes()
    assert shas
    objects = [
        f"    {'└──' if i == len(shas) - 1 else '├──'} {s[:2]}/{_object_name(s, art)}"
        for i, s in enumerate(shas)
    ]
    lines = [
        config["repo_https"].rsplit("/", 1)[1] + "/",
        "├── README.md",
        "├── .gitattributes",
        "├── index.json",
        "└── objects/sha256/",
        *objects,
    ]
    assert_texts(fig, {f"line {i}": line for i, line in enumerate(lines)})
    got = [t.get_text() for t in sorted(_plain_texts(fig), key=lambda t: -t.get_position()[1])]
    assert got == lines  # top to bottom, indentation kept
    assert not _annotations(fig)


def check_exaggeration(fig):
    m = json.loads(
        (REPO_ROOT / "tests" / "fixtures" / "renders" / "r-test.render.json").read_text("utf-8")
    )
    nm = {"nm": 1.0, "um": 1000.0}
    geo = {k: e for k, e in m["quantities"].items() if e.get("role") == "geometry"}
    assert set(geo) == {"t_ox", "poly"}
    (ax,) = fig.axes
    bars = {p.get_gid(): p for p in ax.patches if isinstance(p, Rectangle) and p.get_gid()}
    assert len(bars) == 2 * len(geo)
    for col, key in enumerate(("true_nm", "drawn_nm")):
        bottom = 0.0
        for name in ("t_ox", "poly"):  # the oxide at the bottom
            e = geo[name]
            h = e["value"] * nm[e["unit"]] * (e["scale"] if key == "drawn_nm" else 1.0)
            bar = bars[f"{key} {name}"]
            assert bar.get_height() == pytest.approx(h, rel=1e-12), (key, name)
            assert bar.get_y() == pytest.approx(bottom, abs=1e-12), (key, name)
            assert bar.get_x() + bar.get_width() / 2 == pytest.approx(col)
            bottom += h
    scaled = [s for s in m["exaggeration"] if s.startswith(geo["t_ox"]["label"])]
    assert _ticks(ax.xaxis) == ["true scale", "\n".join(["as the render draws it:", *scaled])]
    assert _legend(fig) == [geo["t_ox"]["label"], geo["poly"]["label"]]
    assert ax.get_ylabel() == "height above the silicon surface (nm)"
    assert_texts(fig, {})
    assert not _annotations(fig)


def check_band_offsets(fig):
    with (REPO_ROOT / "data" / "render" / "display.toml").open("rb") as f:
        d = tomllib.load(f)
    eg, ox = d["silicon"]["band_gap_ev"], d["sio2"]
    edge = {
        "silicon conduction": eg,
        "silicon valence": 0.0,
        "oxide conduction": eg + ox["conduction_offset_ev"],
        "oxide valence": -ox["valence_offset_ev"],
    }
    (ax,) = fig.axes
    lines = {ln.get_gid(): ln for ln in ax.get_lines()}
    for gid, y in edge.items():
        assert np.allclose(lines[gid].get_ydata(), [y, y], rtol=0, atol=1e-12), gid
    assert np.array_equal(lines["interface"].get_xdata(), [1, 1])
    assert set(lines) == {*edge, "interface"}
    values = {
        "band gap": eg,
        "conduction offset": ox["conduction_offset_ev"],
        "valence offset": ox["valence_offset_ev"],
    }
    want = {f"value {k}": f"{k} {v:g} eV" for k, v in values.items()}
    for part in ("oxide", "silicon"):
        for band in ("conduction", "valence"):
            want[f"label {part} {band}"] = f"{part}: {band} band edge"
    assert_texts(fig, want)
    for part in ("oxide", "silicon"):  # each edge label sits on its edge
        for band in ("conduction", "valence"):
            (t,) = [t for t in _plain_texts(fig) if t.get_gid() == f"label {part} {band}"]
            assert t.get_position()[1] == pytest.approx(edge[f"{part} {band}"], abs=1e-12)
    x_si = np.mean(lines["silicon conduction"].get_xdata())
    x_ox = np.mean(lines["oxide conduction"].get_xdata())
    spans = {  # each arrow spans the edges its value separates
        "band gap": ((x_si, 0.0), (x_si, eg)),
        "conduction offset": ((x_ox, eg), (x_ox, edge["oxide conduction"])),
        "valence offset": ((x_ox, edge["oxide valence"]), (x_ox, 0.0)),
    }
    arrows = {a.get_gid(): a for a in _annotations(fig)}
    assert set(arrows) == {f"arrow {k}" for k in spans}
    assert all(a.get_text() == "" for a in arrows.values())
    for key, (start, end) in spans.items():
        a = arrows[f"arrow {key}"]
        assert np.allclose(a.xyann, start, rtol=0, atol=1e-12), (key, a.xyann)
        assert np.allclose(a.xy, end, rtol=0, atol=1e-12), (key, a.xy)
        (t,) = [t for t in _plain_texts(fig) if t.get_gid() == f"value {key}"]
        assert t.get_position()[1] == pytest.approx((start[1] + end[1]) / 2, abs=1e-12)
    assert ax.get_ylabel() == "energy (eV), silicon's valence band edge at 0"


def check_forks(fig):
    inputs = json.loads((REPO_ROOT / "docker" / "tcad-dev" / "upstream.json").read_text("utf-8"))
    forks = [e for e in inputs.values() if e.get("repository", "").startswith(GITHUB + "mithro/")]
    assert len(forks) >= 2
    sub = re.search(
        r"path = (\S+)\n\s*url = https://github.com/(\S+?)(?:\.git)?\n",
        (REPO_ROOT / ".gitmodules").read_text("utf-8"),
    )
    path, plugin = sub.groups()
    prov = json.loads((REPO_ROOT / "results/tcad/moscap1d/provenance.json").read_text("utf-8"))
    want, edges = {}, {}
    for e in forks:
        repo = e["repository"].removeprefix(GITHUB)
        fix = e["role"].split("the mithro fork: ", 1)[1]
        want[f"text {repo}"] = f"{repo} at {e['commit'][:7]} {fix}"
        edges[f"{repo}->dev"] = (repo, "dev")
    want[f"text {plugin}"] = f"{plugin} at {prov['gplugins_commit'][:7]}"
    edges[f"{plugin}->{path}"] = (plugin, path)
    want["text dev"] = "dev-HEAD TCAD image"
    want[f"text {path}"] = "plugin submodule " + path.replace("/", "/ ")
    assert_texts(fig, want)
    assert_box_texts_inside(fig, [k.removeprefix("text ") for k in want])
    assert_box_arrows(fig, edges)


def check_meshwell_square(fig):
    """Each panel draws its image's mesh from data/images/meshwell-square.json: every triangle's
    edges, every point at its place with its number, and the image's gmsh version. The two
    images mesh the same square: the same points and triangles, numbered differently."""
    record = json.loads((REPO_ROOT / "data" / "images" / "meshwell-square.json").read_text("utf-8"))
    names = {"stable": "stable image", "dev": "dev-HEAD image"}
    assert set(record) == set(names)
    assert len(fig.axes) == len(names)
    want = {}
    for ax, (key, name) in zip(fig.axes, names.items(), strict=True):
        mesh = record[key]
        pts = mesh["points"]
        assert (
            record[key]["image"]
            == (REPO_ROOT / "docker" / ("TCAD_IMAGE" if key == "stable" else "TCAD_DEV_IMAGE"))
            .read_text("utf-8")
            .strip()
        )
        assert ax.get_title() == f"{name}, gmsh {mesh['gmsh']}"
        lines = {ln.get_gid(): ln for ln in ax.get_lines()}
        assert set(lines) == {f"{key} triangle {i}" for i in range(len(mesh["triangles"]))}
        for i, tri in enumerate(mesh["triangles"]):
            loop = [*tri, tri[0]]
            ln = lines[f"{key} triangle {i}"]
            assert np.array_equal(ln.get_xdata(), [pts[j][0] for j in loop]), (key, i)
            assert np.array_equal(ln.get_ydata(), [pts[j][1] for j in loop]), (key, i)
        for t in ax.texts:
            i = int(t.get_gid().removeprefix(f"{key} point "))
            assert tuple(t.get_position()) == tuple(pts[i]), (key, i)
        want |= {f"{key} point {i}": f"{i}" for i in range(len(pts))}
    assert_texts(fig, want)

    def triangles(mesh):
        p = mesh["points"]
        return sorted(sorted(tuple(p[j]) for j in tri) for tri in mesh["triangles"])

    assert triangles(record["stable"]) == triangles(record["dev"])
    assert record["stable"]["triangles"] != record["dev"]["triangles"]


def check_results_images(fig):
    from gf180tcad.tcad import RESULTS_IMAGE

    images = _registry()["images"]
    want = {f"text {img}": f"{img} image {e['pin']}" for img, e in images.items()}
    for kind in RESULTS_IMAGE:
        assert (REPO_ROOT / "results" / "tcad" / kind).is_dir()
        assert (REPO_ROOT / "results" / "tcad" / "meshconv" / kind).is_dir()
        want[f"text {kind}"] = f"results/tcad/{kind} results/tcad/meshconv/{kind}"
    for e in images.values():
        assert (REPO_ROOT / e["pin"]).is_file()
    assert_texts(fig, want)
    assert_box_texts_inside(fig, [*RESULTS_IMAGE, *images])
    assert_box_arrows(fig, {f"{k}->{v}": (k, v) for k, v in RESULTS_IMAGE.items()})


CHECKS = {
    "image-forks": check_forks,
    "meshwell-square": check_meshwell_square,
    "results-images": check_results_images,
    "reproduce-targets": check_reproduce_targets,
    "reference-jobs": check_reference_jobs,
    "tcad-registry": check_tcad_registry,
    "tcad-inputs": check_tcad_inputs,
    "crosscheck-steps": _check_steps("crosscheck"),
    "crosscheck-tcad-steps": _check_steps("crosscheck-tcad"),
    "output-cache-flow": check_cache_flow,
    "output-cache-tree": check_cache_tree,
    "render-exaggeration": check_exaggeration,
    "render-band-offsets": check_band_offsets,
}


def test_every_figure_has_a_drawn_data_check():
    assert sorted(CHECKS) == sorted(FIGURES)


@pytest.mark.parametrize("palette", ["light", "dark"])
@pytest.mark.parametrize("figure", FIGURES)
def test_drawn_data_are_the_committed_files(figure, palette):
    CHECKS[figure](rf.DRAW[figure](palette))


# --- every drawn line, scatter and bar, doubled, fails its check --------------------------------


def _data_artists(fig) -> list:
    """The lines, scatters and bars of ``fig`` (the boxes of a diagram are layout, not data)."""
    out = []
    for ax in fig.axes:
        out += [ln for ln in ax.get_lines() if ln.get_gid()]
        out += [c for c in ax.collections if c.get_gid()]
        out += [p for p in ax.patches if type(p) is Rectangle and p.get_gid()]
    return out


def _vertical(line) -> bool:
    return line.get_transform() == line.axes.get_xaxis_transform()


def mutate(artist):
    """Double what ``artist`` draws (add 1 where that is 0); return the undo."""

    def changed(v):
        v = np.asarray(v, float)
        return np.where(v == 0, v + 1, v * 2)

    if isinstance(artist, Line2D):
        if _vertical(artist):
            old = artist.get_xdata()
            artist.set_xdata(changed(old))
            return lambda: artist.set_xdata(old)
        old = artist.get_ydata()
        artist.set_ydata(changed(old))
        return lambda: artist.set_ydata(old)
    if isinstance(artist, Rectangle):
        y, h = artist.get_y(), artist.get_height()
        artist.set_y(float(changed(y)))
        artist.set_height(float(changed(h)))
        return lambda: (artist.set_y(y), artist.set_height(h))
    if isinstance(artist, PathCollection):
        old = artist.get_offsets().copy()
        new = old.copy()
        new[:, 1] = changed(old[:, 1])
        artist.set_offsets(new)
        return lambda: artist.set_offsets(old)
    raise TypeError(f"no mutation for {type(artist).__name__} {artist.get_gid()}")


@pytest.mark.parametrize("figure", FIGURES)
def test_every_drawn_artist_is_checked(figure):
    """Doubling any one line, scatter or bar of the figure makes its check fail."""
    fig = rf.DRAW[figure]("light")
    check = CHECKS[figure]
    check(fig)
    missed = []
    for artist in _data_artists(fig):
        undo = mutate(artist)
        try:
            check(fig)
            missed.append(artist.get_gid())
        except (AssertionError, KeyError):
            pass
        undo()
    check(fig)
    assert not missed, missed


def _fails(check, fig) -> bool:
    try:
        check(fig)
    except (AssertionError, KeyError, ValueError):
        return True
    return False


def _text_mutations(fig):
    """(name, apply, undo) for each text the figure draws: every plain text and annotation text,
    every tick label, legend entry and axis label. Each change appends a word, and doubles the
    first number in the text when it holds one."""

    def changed(text: str) -> str:
        m = re.search(r"\d+(\.\d+)?", text)
        if m:
            new = 2 * float(m.group()) or 1.0
            return text[: m.start()] + f"{new:g}" + text[m.end() :]
        return text + " changed"

    texts = [*fig.texts, *(t for lg in fig.legends for t in lg.get_texts())]
    for ax in fig.axes:
        texts += [*ax.texts, ax.xaxis.label, ax.yaxis.label, ax.title]
        if ax.get_legend():
            texts += ax.get_legend().get_texts()
    out = []
    for t in texts:
        old = t.get_text()
        if not old and not isinstance(t, Annotation):
            continue  # an empty text the figure leaves unused (a title)
        out.append((f"text {t.get_gid() or old!r}", lambda t=t, old=old: t.set_text(changed(old)),
                    lambda t=t, old=old: t.set_text(old)))  # fmt: skip
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            labels = [lb.get_text() for lb in axis.get_ticklabels()]
            if (
                not labels
                or not any(labels)
                or axis.get_major_formatter().__class__.__name__ != "FixedFormatter"
            ):
                continue  # numeric ticks set by matplotlib from the data limits
            ticks = list(axis.get_ticklocs())
            for i in range(len(labels)):
                new = [*labels]
                new[i] = changed(new[i])
                out.append((f"tick {labels[i]!r}",
                            lambda axis=axis, ticks=ticks, new=new: axis.set_ticks(ticks, new),
                            lambda axis=axis, ticks=ticks, old=labels: axis.set_ticks(ticks, old)))  # fmt: skip
    return out


def _arrow_mutations(fig):
    """(name, apply, undo) doubling each end of each arrow (0 becomes 1)."""

    def doubled(p):
        return tuple(2 * v if v else 1.0 for v in p)

    out = []
    for a in _annotations(fig):
        for end in ("xy", "xyann"):
            old = getattr(a, end)
            out.append((f"{a.get_gid()} {end}",
                        lambda a=a, end=end, old=old: setattr(a, end, doubled(old)),
                        lambda a=a, end=end, old=old: setattr(a, end, old)))  # fmt: skip
    return out


@pytest.mark.parametrize("figure", FIGURES)
def test_every_text_and_arrow_is_checked(figure):
    """Changing any one text, tick label, legend entry or axis label, or moving either end of
    any arrow, makes the figure's check fail."""
    fig = rf.DRAW[figure]("light")
    check = CHECKS[figure]
    check(fig)
    mutations = _text_mutations(fig) + _arrow_mutations(fig)
    assert mutations
    missed = []
    for name, apply, undo in mutations:
        apply()
        if not _fails(check, fig):
            missed.append(name)
        undo()
        check(fig)
    assert not missed, missed


def test_positive_control_mutate_changes_zero_lines():
    fig = Figure()
    ax = fig.subplots()
    line = ax.axhline(0, gid="zero")
    undo = mutate(line)
    assert list(line.get_ydata()) == [1, 1]
    undo()
    assert list(line.get_ydata()) == [0, 0]


def test_the_data_figures_have_data_artists():
    """The plots carry the artists the mutation test doubles (so it never passes on nothing)."""
    for name in [n for n in _PLOTS if n in rf.DRAW]:
        assert _data_artists(rf.DRAW[name]("light")), name


# --- colours ------------------------------------------------------------------------------------

_PLOTS = ("reference-jobs", "render-exaggeration", "render-band-offsets", "meshwell-square")
_DIAGRAMS = [n for n in FIGURES if n not in _PLOTS]


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_every_diagram_colour_is_in_the_contrast_tested_palette(palette):
    pal = imagefig.PALETTES[palette]
    allowed = {pal["background"], pal["text"], pal["arrow"], *pal["fill"].values()}
    allowed = {c.lower() for c in allowed}
    for name in _DIAGRAMS:
        svg = rf.FIGURES[name](palette).decode()
        drawn = set(re.findall(r"(?:fill|stroke|color):\s*(#[0-9a-f]{6})", svg))
        assert drawn and drawn <= allowed, (name, drawn - allowed)


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_plots_use_the_explainer_palette(palette):
    pal = {c.lower() for c in ef.PALETTES[palette].values()}
    for name in [n for n in _PLOTS if n in rf.FIGURES]:
        svg = rf.FIGURES[name](palette).decode()
        drawn = set(re.findall(r"(?:fill|stroke):\s*(#[0-9a-f]{6})", svg))
        assert drawn and drawn <= pal, (name, drawn - pal)


# --- no number typed into the code ---------------------------------------------------------------

TABLES = ("STYLE", "UNITS")


def string_digits(source: str, allowed: set[str]) -> list[tuple[int, str]]:
    """(line, text) of each string literal holding a digit once the ``allowed`` names are taken
    out. Skipped: docstrings, raise messages, format specs and the :data:`TABLES`."""
    tree = ast.parse(source)
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            skip |= set(ast.walk(node))
        if isinstance(node, ast.FormattedValue) and node.format_spec is not None:
            skip |= set(ast.walk(node.format_spec))
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                skip.add(first.value)
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        if isinstance(node, ast.Assign | ast.AnnAssign) and any(
            isinstance(t, ast.Name) and t.id in TABLES for t in targets
        ):
            skip |= set(ast.walk(node))
    out = []
    for node in ast.walk(tree):
        if node in skip or not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value.isidentifier():
            continue
        text = node.value
        for name in sorted(allowed, key=len, reverse=True):
            text = text.replace(name, "")
        if re.search(r"\d", text):
            out.append((node.lineno, node.value))
    return out


# Names that hold digits but are not numbers: the hash, the generator registry's file name,
# the device names, the render fixture and the regex classes of the module.
_ALLOWED = {"sha256", "nfet_05v0", "pfet_05v0", "r-test", "2D", "1D", "utf-8", "moscap2d"}


def test_figure_code_has_no_numeric_literals(monkeypatch):
    monkeypatch.setattr(test_explained, "TABLES", TABLES)
    found = numeric_literals(SRC.read_text(encoding="utf-8"))
    assert not found, f"number literals outside STYLE and UNITS: {found}"


def test_figure_strings_type_no_numbers():
    found = string_digits(SRC.read_text(encoding="utf-8"), _ALLOWED)
    assert not found, f"numbers typed into strings (derive them from the data): {found}"


def test_positive_control_string_digits():
    src = (
        '"""At 25 C."""\n'
        'STYLE = {"a": "4.6"}\n'
        "def f(ax, g):\n"
        "    ax.text(0, 0, 'band gap 1.12 eV')\n"
        "    ax.text(0, 0, f'{g:.0e} sha256')\n"
        "    raise ValueError('2 things')\n"
    )
    assert [line for line, _ in string_digits(src, {"sha256"})] == [4]


def test_module_is_outside_every_hashed_closure():
    """No generator's hashed module list names the figure module (its edits move no hash)."""
    reg = json.loads((REPO_ROOT / "src" / "gf180tcad" / "generators.json").read_text("utf-8"))
    for ep, mods in reg["entry_points"].items():
        assert "gf180tcad.reproduce_figures" not in mods, ep
    from gf180tcad.reference import GENERATOR_MODULES

    assert not any("reproduce_figures" in str(m) for m in GENERATOR_MODULES)
