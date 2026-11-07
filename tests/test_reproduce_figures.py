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
    "results-images",
    "reproduce-targets",
    "reference-jobs",
    "tcad-registry",
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


def _texts(fig) -> dict[str, str]:
    return {t.get_gid(): t.get_text() for ax in fig.axes for t in ax.texts if t.get_gid()}


def _arrows(fig) -> set[str]:
    return {
        a.get_gid().removeprefix("arrow ")
        for ax in fig.axes
        for a in ax.texts
        if (a.get_gid() or "").startswith("arrow ")
    }


def _flat(text: str) -> str:
    return " ".join(text.split())


def check_reproduce_targets(fig):
    make = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = re.search(r"^reproduce:\n((?:\t.*\n)+)", make, re.MULTILINE).group(1).splitlines()
    texts = _texts(fig)
    keys = []
    for i, line in enumerate(recipe):
        line = line.strip()
        if line.startswith("$(MAKE) "):
            make_args = line.split()[1:]
            target = make_args[-1]
            body = re.search(rf"^{target}:.*\n((?:\t.*\n)+)", make, re.MULTILINE).group(1)
            outs = list(dict.fromkeys(re.findall(r"--out (\S+)", body.replace("\\\n", " "))))
            assert outs, target
            want = f"make {' '.join(make_args)} writes " + ", ".join(outs)
            assert _flat(texts[f"text {target}"]) == want
            keys.append(target)
        else:
            want = line.replace("$(PYTHON) ", "python ")
            assert _flat(texts[f"text command {i}"]) == want
            keys.append(f"command {i}")
    assert len([k for k in texts if k.startswith("text ")]) == len(keys)
    assert _arrows(fig) == {f"{a}->{b}" for a, b in itertools.pairwise(keys)}


def check_reference_jobs(fig):
    root = REPO_ROOT / "results" / "spice"
    jobs = sorted(tuple(p.parent.relative_to(root).parts) for p in root.rglob("metrics.json"))
    assert jobs
    rows = sorted({j[:2] for j in jobs})
    cols = [(d, geometry_id(g)) for d in sorted(DEVICES) for g in DEVICES[d].geometries]
    cols = [c for c in cols if any(j[2:] == c for j in jobs)]
    (ax,) = fig.axes
    for gid, keep in (("jobs", False), ("selected", True)):
        want = [
            (cols.index(j[2:]), rows.index(j[:2]))
            for j in jobs
            if (
                j[0] == rf.EXAMPLE_RUN["engine"]
                and j[1] == rf.EXAMPLE_RUN["corner"]
                and j[2] == rf.EXAMPLE_RUN["device"]
            )
            == keep
        ]
        (coll,) = [c for c in ax.collections if c.get_gid() == gid]
        assert np.array_equal(coll.get_offsets(), np.array(want, float)), gid
    assert [t.get_text() for t in ax.get_yticklabels()] == [f"{e} {c}" for e, c in rows]


def check_tcad_registry(fig):
    reg = json.loads((REPO_ROOT / "src" / "gf180tcad" / "generators.json").read_text("utf-8"))
    texts = _texts(fig)
    for ep, mods in reg["entry_points"].items():
        assert _flat(texts[f"text {ep}"]) == f"{ep} {len(mods)} modules hashed"
    for tree in reg["trees"]:
        assert texts[f"text {tree}"] == f"results/{tree}"
    assert _arrows(fig) == {f"{w}->{t}" for t, w in reg["trees"].items()}


def _steps(job: str) -> list[str]:
    text = (REPO_ROOT / ".github" / "workflows" / "crosscheck.yml").read_text("utf-8")
    block = text.split(f"\n  {job}:\n", 1)[1].split("\n\n  ", 1)[0]
    return re.findall(r"^      - (\w+): (.+)$", block, re.MULTILINE)


def _check_steps(job: str):
    def check(fig):
        steps = _steps(job)
        texts = _texts(fig)
        assert len([k for k in texts if k.startswith("text ")]) == len(steps)
        for i, (kind, value) in enumerate(steps):
            got = _flat(texts[f"text step {i}"])
            if kind == "name":
                assert got == value.strip()
            elif kind == "uses":
                assert got.startswith(value.split("@")[0]), (got, value)
            else:
                assert got == value.strip()
        assert _arrows(fig) == {f"step {i}->step {i + 1}" for i in range(len(steps) - 1)}

    return check


def _calibrated_meshes() -> list[str]:
    metas = (REPO_ROOT / "results" / "tcad" / "moscap2d").glob("*/calibrated/*/cv.meta.json")
    return sorted({json.loads(p.read_text("utf-8"))["mesh_sha256"] for p in metas})


def check_cache_flow(fig):
    config = json.loads((REPO_ROOT / "data" / "output-cache.json").read_text("utf-8"))
    (art,) = config["artefacts"]
    texts = _texts(fig)
    assert texts["text file"].startswith(f"results/{art['pattern']}")
    assert _flat(texts["text meta"]) == f"{art['meta']} names its {art['hash_key']} (committed)"
    sha = _calibrated_meshes()[0]
    assert texts["text object"].replace("\n", "").startswith(f"objects/sha256/{sha[:2]}/{sha[:12]}")
    assert _arrows(fig) == {"push", "pull", "meta->file", "index->object"}


def check_cache_tree(fig):
    lines = [t for _, t in sorted(
        (int(g.split()[1]), t) for g, t in _texts(fig).items() if g.startswith("line "))]  # fmt: skip
    shas = _calibrated_meshes()
    assert len(shas) == len(set(shas)) and shas
    objects = [ln.split()[-1] for ln in lines[5:]]
    assert objects == [f"{s[:2]}/{s[:12]}….msh.gz" for s in shas]
    assert lines[1:5] == ["├── README.md", "├── .gitattributes", "├── index.json",
                          "└── objects/sha256/"]  # fmt: skip


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
    assert m["exaggeration"][0] in ax.get_xticklabels()[1].get_text()


def check_band_offsets(fig):
    with (REPO_ROOT / "data" / "render" / "display.toml").open("rb") as f:
        d = tomllib.load(f)
    eg = d["silicon"]["band_gap_ev"]
    want = {
        "silicon conduction": eg,
        "silicon valence": 0.0,
        "oxide conduction": eg + d["sio2"]["conduction_offset_ev"],
        "oxide valence": -d["sio2"]["valence_offset_ev"],
    }
    (ax,) = fig.axes
    lines = {ln.get_gid(): ln for ln in ax.get_lines()}
    for gid, y in want.items():
        assert np.allclose(lines[gid].get_ydata(), [y, y], rtol=0, atol=1e-12), gid
    assert np.array_equal(lines["interface"].get_xdata(), [1, 1])
    assert set(lines) == {*want, "interface"}


def check_forks(fig):
    inputs = json.loads((REPO_ROOT / "docker" / "tcad-dev" / "upstream.json").read_text("utf-8"))
    forks = [e for e in inputs.values() if "github.com/mithro/" in e.get("repository", "")]
    assert len(forks) >= 2
    texts = _texts(fig)
    for e in forks:
        repo = e["repository"].removeprefix("https://github.com/")
        assert texts[f"text {repo}"].startswith(f"{repo} at {e['commit'][:7]}")
    prov = json.loads((REPO_ROOT / "results/tcad/moscap1d/provenance.json").read_text("utf-8"))
    assert texts["text mithro/gplugins"] == f"mithro/gplugins at {prov['gplugins_commit'][:7]}"
    want = {f"{e['repository'].removeprefix('https://github.com/')}->dev" for e in forks}
    assert _arrows(fig) == want | {"mithro/gplugins->third_party/gplugins"}


def check_results_images(fig):
    from gf180tcad.tcad import RESULTS_IMAGE

    reg = json.loads((REPO_ROOT / "src" / "gf180tcad" / "generators.json").read_text("utf-8"))
    texts = _texts(fig)
    for img, entry in reg["images"].items():
        assert texts[f"text {img}"] == f"{img} image\n{entry['pin']}"
        assert (REPO_ROOT / entry["pin"]).is_file()
    for kind in RESULTS_IMAGE:
        assert (REPO_ROOT / "results" / "tcad" / kind).is_dir()
        assert (REPO_ROOT / "results" / "tcad" / "meshconv" / kind).is_dir()
    assert _arrows(fig) == {f"{k}->{v}" for k, v in RESULTS_IMAGE.items()}


CHECKS = {
    "image-forks": check_forks,
    "results-images": check_results_images,
    "reproduce-targets": check_reproduce_targets,
    "reference-jobs": check_reference_jobs,
    "tcad-registry": check_tcad_registry,
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

_PLOTS = ("reference-jobs", "render-exaggeration", "render-band-offsets")
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
