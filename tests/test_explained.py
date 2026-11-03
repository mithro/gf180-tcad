# SPDX-License-Identifier: Apache-2.0
"""The explainer section ``docs/explained/`` and its machinery, :mod:`gf180tcad.explain`.

Every number on an explainer page enters by a ``{{ x_<name> }}`` substitution from
:mod:`gf180tcad.explain.numbers` (a committed file, a textbook entry or an idealised example),
and every figure is drawn by :mod:`gf180tcad.explain.figures` from committed files, in a light
and a dark twin. These tests hold the pages and the code to that (plan
``docs/superpowers/plans/2026-10-27-explainer-docs.md``, Global Constraints).
"""

from __future__ import annotations

import ast
import json
import math
import re
import subprocess
import sys
import textwrap
import tomllib
from collections import Counter
from itertools import pairwise
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPLAINED = ROOT / "docs" / "explained"
LITERATURE = ROOT / "docs" / "limitations" / "literature.md"
TEXTBOOK = ROOT / "data" / "explain" / "textbook.toml"
DISPLAY = ROOT / "data" / "render" / "display.toml"
EXPLAIN_SRC = ROOT / "src" / "gf180tcad" / "explain"
SRC = ROOT / "src"

_SUBST = re.compile(r"\{\{\s*(x_\w+)\s*\}\}")


def pages() -> list[Path]:
    return sorted(EXPLAINED.glob("*.md"))


def explanation_pages() -> list[Path]:
    return [p for p in pages() if p.name != "index.md"]


def _numbers():
    from gf180tcad.explain import numbers

    return numbers


# --- the number registry ---------------------------------------------------------------------


def test_there_are_pages():
    assert (EXPLAINED / "index.md").is_file()
    assert explanation_pages(), "docs/explained/ holds no explanation page"


def test_substitutions_defined():
    from gf180tcad import explain

    subs = explain.substitutions()
    for page in pages():
        for name in _SUBST.findall(page.read_text(encoding="utf-8")):
            assert name in subs, f"{page.relative_to(ROOT)}: {{{{ {name} }}}} is not registered"


def _used_names() -> set[str]:
    used: set[str] = set()
    for page in pages():
        for key in _SUBST.findall(page.read_text(encoding="utf-8")):
            used.add(key.removeprefix("x_").removesuffix("_label"))
    return used


def test_every_registered_number_is_used():
    """A registry entry is on a page, or is an input of one that is (directly or not)."""
    numbers = _numbers()
    needed = set(_used_names()) & set(numbers.REGISTRY)
    todo = list(needed)
    while todo:
        for i in numbers.REGISTRY[todo.pop()].inputs:
            if i not in needed:
                needed.add(i)
                todo.append(i)
    unused = sorted(set(numbers.REGISTRY) - needed)
    assert not unused, f"registered but on no page and input of none: {unused}"


def test_inputs_are_registered_and_kinds_closed():
    numbers = _numbers()
    for n in numbers.REGISTRY.values():
        assert n.kind in numbers.KINDS, n
        for i in n.inputs:
            assert i in numbers.REGISTRY, f"{n.name}: input {i!r} is not registered"
        if n.kind == "idealised":
            assert n.formula and n.inputs, f"{n.name}: an idealised number is a formula"
        else:
            assert n.source and n.key, f"{n.name}: a {n.kind} number is read from a file"


def test_sources_exist():
    for n in _numbers().REGISTRY.values():
        if n.source is not None:
            assert (ROOT / n.source).is_file(), f"{n.name}: {n.source} does not exist"
            _numbers().value(n.name)  # the key resolves


def test_textbook_entries_cite_literature():
    anchors = set(re.findall(r"^\((lit-[\w-]+)\)=$", LITERATURE.read_text("utf-8"), re.MULTILINE))
    numbers = _numbers()
    textbook = [n for n in numbers.REGISTRY.values() if n.kind == "textbook"]
    for n in textbook:
        assert n.source in (
            str(TEXTBOOK.relative_to(ROOT)),
            str(DISPLAY.relative_to(ROOT)),
        ), n
        cite = numbers.citation(n.name)
        found = re.findall(r"\((lit-[\w-]+)\)", cite)
        assert found and set(found) <= anchors, f"{n.name}: {cite!r} names no literature anchor"


def _toml_keys(path: Path) -> set[tuple[str, str]]:
    if not path.is_file():
        return set()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {(s, k) for s, t in data.items() if isinstance(t, dict) for k in t if k != "sources"}


def test_no_textbook_value_twice():
    both = _toml_keys(TEXTBOOK) & _toml_keys(DISPLAY)
    assert not both, f"defined in both {TEXTBOOK.name} and {DISPLAY.name}: {sorted(both)}"


def test_value_text_and_labels():
    numbers = _numbers()
    subs = numbers.substitutions()
    for name, n in numbers.REGISTRY.items():
        assert subs[f"x_{name}"] == numbers.text(name)
        assert subs[f"x_{name}_label"] == numbers.LABELS[n.kind]
        assert math.isfinite(numbers.value(name))


@pytest.mark.parametrize(
    ("value", "digits", "unit", "text"),
    [
        (8.813323306821749e16, 3, "cm⁻³", "8.81\u00a0×\u00a010¹⁶\u00a0cm⁻³"),
        (1e20, 2, "cm⁻³", "1.0\u00a0×\u00a010²⁰\u00a0cm⁻³"),
        (8265841554.853887, 3, "cm⁻³", "8.27\u00a0×\u00a010⁹\u00a0cm⁻³"),
        (298.15, 5, "K", "298.15\u00a0K"),
        (775.2, 3, "cm⁻³", "775\u00a0cm⁻³"),
        (0.0371, 2, "V", "0.037\u00a0V"),
        (-0.25, 2, "V", "−0.25\u00a0V"),
        (2.15, 3, "fF/µm²", "2.15\u00a0fF/\u2060µm²"),
        (0.67, 2, "%", "0.67\u00a0%"),
    ],
)
def test_format(value, digits, unit, text):
    assert _numbers().format_value(value, digits, unit) == text


def test_committed_values_are_the_files():
    """Three entries traced to their files by hand (not through the registry's own reader)."""
    numbers = _numbers()
    meta = json.loads(
        (ROOT / "results/tcad/moscap1d/nfet_05v0/calibrated/per_area.meta.json").read_text("utf-8")
    )
    proc = tomllib.loads((ROOT / "data/process/nfet_05v0.toml").read_text("utf-8"))
    assert numbers.value("n_ch_nfet_cal") == meta["stack"]["n_ch_cm3"]
    assert numbers.value("n_i_tcad") == meta["constants"]["n_i_cm3"]
    assert numbers.value("ngate_nfet") == proc["param"]["ngate_cm3"]["value"]


def test_conf_merges_the_substitutions():
    sys.path.insert(0, str(ROOT / "docs"))
    try:
        import importlib

        conf = importlib.import_module("conf")
    finally:
        sys.path.remove(str(ROOT / "docs"))
    from gf180tcad import explain

    subs = explain.substitutions()
    for key, val in subs.items():
        assert conf.myst_substitutions[key] == val
    assert not set(subs) & set(conf._TOOLS)


def _sentences(text: str) -> list[str]:
    """The prose sentences of a page, wrapped lines joined (display math and directives kept
    whole, so a sentence never spans them)."""
    paras = re.split(r"\n\s*\n", re.sub(r"\$\$.*?\$\$", "\n\n", text, flags=re.DOTALL))
    out = []
    for para in paras:
        flat = " ".join(para.split())
        out += re.split(r"(?<=[.?!])\s+(?=[A-Z{])", flat)
    return out


def unlabelled(text: str) -> list[str]:
    """Sentences carrying a textbook value without a literature link, or an idealised value
    without the word "idealised"."""
    reg = _numbers().REGISTRY
    bad = []
    for sent in _sentences(text):
        for key in _SUBST.findall(sent):
            n = reg.get(key.removeprefix("x_"))
            if n is None:
                continue
            if n.kind == "textbook" and not re.search(r"<lit-[\w-]+>`", sent):
                bad.append(sent)
            if n.kind == "idealised" and "idealised" not in sent:
                bad.append(sent)
    return bad


def test_non_committed_values_are_labelled():
    bad = [f"{p.name}: {s}" for p in pages() for s in unlabelled(p.read_text("utf-8"))]
    assert not bad, "\n".join(bad)


# A textbook entry for the controls (no page prints a textbook value while #88 is open).
_NC = {"name": "nc_si", "kind": "textbook", "unit": "cm⁻³", "digits": 2,
       "source": "data/render/display.toml", "key": {"toml": ["silicon", "nc_cm3"]}}  # fmt: skip


@pytest.fixture
def textbook_entry(monkeypatch):
    numbers = _numbers()
    monkeypatch.setitem(numbers.REGISTRY, "nc_si", numbers.Number(**_NC))
    numbers.value.cache_clear()
    yield numbers
    numbers.value.cache_clear()


def test_citation_reads_the_sources_table(textbook_entry):
    cite = textbook_entry.citation("nc_si")
    assert "(lit-sze)" in cite and "Appendix G" in cite
    with pytest.raises(ValueError, match="not a textbook value"):
        textbook_entry.citation("n_i_tcad")


def test_positive_control_unlabelled(textbook_entry):
    text = "Electrons number {{ x_n_minority_nfet }} here. The gap uses {{ x_nc_si }} as well.\n"
    assert len(unlabelled(text)) == 2
    ok = (
        "In an idealised example electrons number {{ x_n_minority_nfet }}. It uses"
        " {{ x_nc_si }} ({ref}`Sze and Ng <lit-sze>`).\n"
    )
    assert unlabelled(ok) == []


# --- the idealised formulas ------------------------------------------------------------------


def test_idealised_table_is_closed_and_documented():
    from gf180tcad.explain import idealised

    assert set(idealised.FORMULAS) == {
        "abrupt_junction", "boltzmann_fermi", "built_in_potential", "degenerate_offset",
        "depletion_width", "mass_action", "bulk_potential", "flat_band", "threshold",
        "depletion_depth", "surface_bending",
    }  # fmt: skip
    for f in idealised.FORMULAS.values():
        doc = " ".join((f.fn.__doc__ or "").split())
        assert f.equation in doc and f"Reference: {f.reference}." in doc, f.name


def test_derive_against_hand_values():
    """Each idealised formula against a value worked by hand.

    - mass_action: n_i = 1e10 cm⁻³ and N_A = 1e17 cm⁻³ give n = n_i²/N_A = 1e20/1e17 = 1e3.
    - boltzmann_fermi: n = 1e17, n_i = 1e10, V_t = 0.025 V give E_F − E_i =
      0.025·ln(1e7) = 0.025 × 16.11810 = 0.4029524 eV.
    - degenerate_offset: F_½(0) = 0.7651470 (the tabulated Fermi–Dirac integral at η = 0,
      Blakemore 1982, Solid-State Electron. 25, 1067, Table 1). At n/N_c = 0.7651470 Fermi–Dirac
      puts the Fermi level at the band edge (η = 0), Boltzmann at η = ln(0.7651470) = −0.267683,
      so with V_t = 0.025 V the offset is 0.025 × 0.267683 = 6.692 mV.
    - degenerate_offset at n/N_c = 1e20/2.8e19 = 3.5714: the Joyce–Dixon series
      η = ln r + r/√8 + (3/16 − √3/9)·r² ≈ 1.27297 + 1.26270 − 0.06316 = 2.4725 gives
      (2.4725 − 1.27297) × 0.025 = 30.0 mV, within 1 mV of the exact inverse (the series'
      next terms are below 0.04 in η at this r).
    """
    from gf180tcad.explain import idealised

    assert idealised.mass_action(1e10, 1e17) == pytest.approx(1e3, rel=1e-12)
    assert idealised.boltzmann_fermi(1e17, 1e10, 0.025) == pytest.approx(0.4029524, rel=1e-6)
    assert idealised.degenerate_offset(0.7651470 * 2.8e19, 2.8e19, 0.025) == pytest.approx(
        6.692e-3, abs=2e-6
    )
    assert idealised.degenerate_offset(1e20, 2.8e19, 0.025) == pytest.approx(30.0e-3, abs=1e-3)


def test_no_formula_twice():
    from gf180tcad import derive
    from gf180tcad.explain import idealised

    assert not set(idealised.FORMULAS) & set(derive.FORMULAS)
    eq_d = {f.equation for f in derive.FORMULAS.values()}
    for f in idealised.FORMULAS.values():
        assert f.equation not in eq_d, f.name


# --- no bare numbers on a page ---------------------------------------------------------------

# Proper names that carry digits, allowed in prose (plan, Global Constraints).
PROPER_NAMES = (
    "GF180MCU",
    "gf180mcu",
    "5 V transistor",
    "nfet_05v0",
    "pfet_05v0",
    "1D",
    "2D",
    "3D",
    "BSIM4",
    "Poly2",  # the PDK's gate layer, named in the plan view's alt text
    "Tier 1",
    "Tier 2",
    "Tier 3",
)
_GEOMETRY_ID = re.compile(r"\bw\d+p\d+_l\d+p\d+\b")
_STRIP = (
    re.compile(r"\$\$.*?\$\$", re.DOTALL),  # display math
    re.compile(r"\$[^$\n]+\$"),  # inline math
    re.compile(r"<!--.*?-->", re.DOTALL),  # comments
    re.compile(r"\{[\w:.-]+\}`[^`]*`"),  # roles and their targets
    re.compile(r"`[^`]*`"),  # code spans
    _SUBST,  # substitutions
    re.compile(r"\]\([^)]*\)"),  # link targets
    re.compile(r"\bch\. \d+"),  # citation: chapter
    re.compile(r"§\d+(\.\d+)*"),  # citation: section
    re.compile(r"(?<![\w#])#\d+"),  # issue and PR numbers
    _GEOMETRY_ID,
)


def bare_numbers(text: str) -> list[tuple[int, str]]:
    """(line, text) of each line of ``text`` holding a digit outside the allowed places."""
    out = []
    for i, line in enumerate(_strip_blocks(text).splitlines(), 1):
        if re.search(r"<!--\s*number-ok:\s*\S", line):
            continue
        s = line
        for rx in _STRIP:
            s = rx.sub(" ", s)
        for name in PROPER_NAMES:
            s = s.replace(name, " ")
        if re.search(r"[0-9]", s):
            out.append((i, line))
    return out


def _strip_blocks(text: str) -> str:
    """Blank the display-math blocks (keeping line numbers) and the directive option lines,
    except the text of an ``:alt:`` line, which the reader sees and the scan reads."""
    text = re.sub(r"\$\$.*?\$\$", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.DOTALL)
    text = re.sub(r"^:alt:", "", text, flags=re.MULTILINE)
    return re.sub(r"^:[\w-]+:.*$", "", text, flags=re.MULTILINE)


def test_no_bare_numbers():
    problems = [
        f"{p.relative_to(ROOT)}:{i}: {line}" for p in pages() for i, line in bare_numbers(p.read_text("utf-8"))
    ]  # fmt: skip
    assert not problems, "\n".join(problems)


def test_positive_control_bare_numbers():
    bad = (
        "The body holds 1.7e17 acceptors per cubic centimetre.\nAt 300 K it is intrinsic.\n"
        ":alt: A curve that peaks at 1e17.\n:figclass: only-light\n"
    )
    assert [i for i, _ in bare_numbers(bad)] == [1, 2, 3]
    good = textwrap.dedent(
        """\
        The body holds {{ x_n_ch_nfet_cal }} of acceptors ({ref}`Sze and Ng, ch. 1 <lit-sze>`).
        The GF180MCU 5 V transistor {term}`nfet_05v0` in 1D and 2D, $n p = n_i^2$, see #46.
        $$
        n = 10^{17}
        $$
        A typed 42 here is allowed. <!-- number-ok: a control -->
        """
    )
    assert bare_numbers(good) == []


# --- the figure module -----------------------------------------------------------------------


# The two tables a figure module may hold numbers in: STYLE (sizes, colours, line widths, label
# offsets, scale factors) and UNITS (unit conversions).
TABLES = ("STYLE", "UNITS")


def _table_nodes(tree: ast.Module) -> list[ast.AST]:
    out = []
    for node in tree.body:
        if isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id in TABLES for t in targets):
                out.append(node)
    return out


def numeric_literals(source: str) -> list[tuple[int, object]]:
    """(line, value) of each number literal outside the tables, other than 0, 1, 2."""
    tree = ast.parse(source)
    allowed = {n for t in _table_nodes(tree) for n in ast.walk(t)}
    doc_nodes = {
        n.body[0].value
        for n in ast.walk(tree)
        if isinstance(n, ast.Module | ast.FunctionDef | ast.ClassDef)
        and n.body
        and isinstance(n.body[0], ast.Expr)
        and isinstance(n.body[0].value, ast.Constant)
    }
    out = []
    for node in ast.walk(tree):
        if node in allowed or node in doc_nodes or not isinstance(node, ast.Constant):
            continue
        v = node.value
        if isinstance(v, int | float | complex) and not isinstance(v, bool) and v not in (0, 1, 2):
            out.append((node.lineno, v))
    return out


@pytest.mark.parametrize("module", ["figures.py", "model.py"])
def test_figure_code_has_no_numeric_literals(module):
    found = numeric_literals((EXPLAIN_SRC / module).read_text(encoding="utf-8"))
    assert not found, f"{module}: number literals outside {TABLES}: {found}"


def test_positive_control_numeric_literals():
    src = "STYLE = {'w': 6.4}\nUNITS = {'nm_per_um': 1e3}\ndef f(x):\n    return x * 40 + 1\n"
    assert numeric_literals(src) == [(4, 40)]


def test_figures_have_dark_twins(tmp_path):
    from gf180tcad.explain import figures

    figures.write_all(tmp_path)
    light = sorted(p.name.removesuffix("-light.svg") for p in tmp_path.glob("*-light.svg"))
    dark = sorted(p.name.removesuffix("-dark.svg") for p in tmp_path.glob("*-dark.svg"))
    assert light and light == dark == sorted(figures.FIGURES)
    for name in light:
        a = (tmp_path / f"{name}-light.svg").read_bytes()
        b = (tmp_path / f"{name}-dark.svg").read_bytes()
        assert a.startswith(b"<?xml") and b.startswith(b"<?xml") and a != b
    for page in explanation_pages():
        text = page.read_text(encoding="utf-8")
        for name in re.findall(r"/_generated/explained/([\w-]+)-light\.svg", text):
            assert f"/_generated/explained/{name}-dark.svg" in text, (page.name, name)
            assert name in figures.FIGURES, (page.name, name)
        assert text.count(":figclass: only-light") == text.count(":figclass: only-dark"), page


def test_figures_legible_at_400px():
    """An SVG is scaled to the content width, so text at 400 px is pt × 400 / (width_in × 72)."""
    from gf180tcad.explain import figures

    width_in, _height_in = figures.STYLE["size_in"]
    px = figures.STYLE["text_pt"] * 400 / (width_in * 72)
    assert px >= 9, f"{px:.1f} px at 400 px"


# --- copied images and their licence notes ---------------------------------------------------

IMAGES = EXPLAINED / "images"
_LICENCE_LINE = re.compile(r"^Licence:\s*\S", re.MULTILINE)
_SOURCE_LINE = re.compile(r"^Source:\s*https://\S", re.MULTILINE)


def licence_problems(images: Path) -> list[str]:
    """Each copied image needs ``<name>.licence.txt`` beside it naming its source and licence;
    each note needs its image."""
    out = []
    for f in sorted(images.iterdir()):
        if f.name.endswith(".licence.txt"):
            if not (images / f.name.removesuffix(".licence.txt")).is_file():
                out.append(f"{f.name}: a licence note with no image")
            continue
        note = images / f"{f.name}.licence.txt"
        if not note.is_file():
            out.append(f"{f.name}: no licence note")
            continue
        text = note.read_text(encoding="utf-8")
        if not _LICENCE_LINE.search(text):
            out.append(f"{note.name}: no 'Licence:' line")
        if not _SOURCE_LINE.search(text):
            out.append(f"{note.name}: no 'Source: https://' line")
    return out


def test_every_copied_image_has_a_licence_note():
    assert IMAGES.is_dir() and any(IMAGES.iterdir())
    problems = licence_problems(IMAGES)
    assert not problems, "\n".join(problems)


def test_positive_control_licence_notes(tmp_path):
    (tmp_path / "a.png").write_bytes(b"x")
    (tmp_path / "b.jpg").write_bytes(b"x")
    (tmp_path / "b.jpg.licence.txt").write_text(
        "Source: https://example.org/b\nLicence:\n", encoding="utf-8"
    )
    (tmp_path / "c.png.licence.txt").write_text(
        "Source: https://x\nLicence: CC BY\n", encoding="utf-8"
    )
    assert licence_problems(tmp_path) == [
        "a.png: no licence note",
        "b.jpg.licence.txt: no 'Licence:' line",
        "c.png.licence.txt: a licence note with no image",
    ]


def test_every_copied_image_is_on_a_page():
    used = "".join(p.read_text(encoding="utf-8") for p in pages())
    for f in IMAGES.iterdir():
        if not f.name.endswith(".licence.txt"):
            assert f"images/{f.name}" in used, f.name


def test_exaggeration_statement_follows_the_scales():
    from gf180tcad.explain import model

    assert model.exaggeration({}) == "Drawn to scale."
    assert model.exaggeration({"oxide": 1.0}) == "Drawn to scale."
    assert model.exaggeration({"oxide": 5.0}) == "Oxide thickness ×5, not to scale."


def test_model_reads_the_committed_stack():
    from gf180tcad.explain import model

    meta = json.loads(
        (ROOT / "results/tcad/moscap1d/nfet_05v0/calibrated/per_area.meta.json").read_text("utf-8")
    )
    d = model.device("nfet_05v0", "calibrated", scales={})
    by = {layer.part: layer for layer in d.layers}
    assert [layer.part for layer in d.layers] == ["gate", "oxide", "body"]
    assert by["gate"].thickness_um == meta["stack"]["poly_um"]
    assert by["oxide"].thickness_um == meta["stack"]["t_ox_nm"] / 1000
    assert by["body"].thickness_um == meta["stack"]["body_um"]
    assert by["body"].doping_cm3 == meta["stack"]["n_ch_cm3"]
    assert (by["gate"].dopant, by["body"].dopant) == ("donor", "acceptor")
    p = model.device("pfet_05v0", "calibrated", scales={})
    assert [layer.dopant for layer in p.layers] == ["acceptor", None, "donor"]


# --- the pages -------------------------------------------------------------------------------

NOT_COUNTED = ("inline URL not in any footnote definition", "number with no marker")


def _cap_findings(files: list[str]) -> list[str]:
    """The findings of both docs linters on ``files`` that the house rules count."""
    m = subprocess.run(
        [sys.executable, "-I", str(ROOT / "tools" / "measure_docs.py"), *files],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    found = [
        ln for ln in m.stdout.splitlines()
        if not ln.endswith("file(s) measured") and not any(k in ln for k in NOT_COUNTED)
    ]  # fmt: skip
    lint = subprocess.run(
        [sys.executable, "-I", str(ROOT / "tools" / "docs_lint.py"), "--no-front-matter", *files],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    found += [
        ln for ln in (lint.stdout + lint.stderr).splitlines() if re.search(r": (FAIL|warn) ", ln)
    ]
    return found


def test_explained_pages_meet_every_cap():
    found = _cap_findings([str(p) for p in pages()])
    assert not found, "\n".join(found)


def test_explained_pages_meet_every_cap_with_substitutions_filled_in(tmp_path):
    """The linters see only ``{{ x_name }}`` in the source, so a long generated clause would
    pass them: lint each page again with every substitution filled in."""
    from gf180tcad import explain

    subs = explain.substitutions()
    files = []
    for page in pages():
        out = tmp_path / page.name
        out.write_text(_render(page.read_text(encoding="utf-8"), subs), "utf-8")
        files.append(str(out))
    found = _cap_findings(files)
    assert not found, "\n".join(found)


def test_positive_control_filled_in_caps(tmp_path):
    long = "The clause " + " ".join(["word"] * 30) + " ends here."
    page = tmp_path / "long.md"
    page.write_text("# Title\n\n{{ x_long }}\n", "utf-8")
    assert not _cap_findings([str(page)])
    page.write_text(_render(page.read_text("utf-8"), {"x_long": long}), "utf-8")
    assert _cap_findings([str(page)])


@pytest.mark.parametrize("page", explanation_pages(), ids=lambda p: p.name)
def test_explained_pages_are_explanations(page):
    text = page.read_text(encoding="utf-8")
    heads = re.findall(r"^## (.+)$", text, re.MULTILINE)
    assert 1 <= len(heads) <= 7, heads
    assert "Where this repo's results differ" in heads
    assert not re.search(r"^\s*\d+\. ", text, re.MULTILINE), "numbered steps on an explanation page"
    first_head = text.index("\n## ")
    assert "```{figure} /_generated/explained/" in text[:first_head], "no opening figure"
    assert len(re.findall(r"^# ", text, re.MULTILINE)) == 1


def test_landing_lists_every_page():
    text = (EXPLAINED / "index.md").read_text(encoding="utf-8")
    toc = re.search(r"```\{toctree\}\n(.*?)```", text, re.DOTALL)
    assert toc, "docs/explained/index.md has no toctree"
    entries = [ln.strip() for ln in toc.group(1).splitlines() if ln.strip() and ":" not in ln]
    names = [p.stem for p in explanation_pages()]
    assert sorted(entries) == sorted(names)
    for name in names:
        assert re.search(rf"^- \{{doc\}}`[^`<]+<{re.escape(name)}>`: ", text, re.MULTILINE), name
    prose = [
        ln for ln in text[: toc.start()].splitlines()
        if ln.strip() and not ln.startswith(("# ", "## ", "### ", "- ", "(")) and not ln.startswith("  ")
    ]  # fmt: skip
    assert len(prose) <= 2, f"a landing page is one line per destination: {prose}"
    # One heading per tier keeps each list within the 7-item cap.
    for head in re.findall(r"^## (.+)$", text[: toc.start()], re.MULTILINE):
        assert head in ("The basics", "The MOS capacitor", "The MOSFET"), head


def test_explained_is_first_in_the_top_toctree():
    text = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    toc = re.search(r"```\{toctree\}\n(.*?)```", text, re.DOTALL).group(1)
    entries = [ln.strip() for ln in toc.splitlines() if ln.strip() and not ln.startswith(":")]
    assert entries[0] == "explained/index"
    assert "five sections" in text


# --- isolation from the generators -----------------------------------------------------------


def _module_file(name: str) -> Path | None:
    parts = name.split(".")
    base = SRC.joinpath(*parts)
    for cand in (base.with_suffix(".py"), base / "__init__.py"):
        if cand.is_file():
            return cand
    return None


def _imports(path: Path, modname: str) -> set[str]:
    out: set[str] = set()
    pkg = modname if path.name == "__init__.py" else modname.rpartition(".")[0]
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg.split(".")
                base = base[: len(base) - node.level + 1]
                mod = ".".join([*base, node.module] if node.module else base)
            else:
                mod = node.module or ""
            out.add(mod)
            out.update(f"{mod}.{a.name}" for a in node.names)
    return out


def hashed_closures() -> dict[str, list[str]]:
    """Every hashed module list: the TCAD entry points, the SPICE reference, the renders."""
    from gf180tcad import reference

    reg = json.loads((SRC / "gf180tcad" / "generators.json").read_text(encoding="utf-8"))
    out = {f"tcad:{k}": list(v) for k, v in reg["entry_points"].items()}
    out["spice:reference"] = list(reference.GENERATOR_MODULES)
    renders = reg.get("renders")
    if isinstance(renders, dict):
        out["renders"] = list(renders.get("shared_modules", [])) + list(
            renders.get("module_list", [])
        )
    return out


def test_explain_in_no_generator_closure():
    for closure, mods in hashed_closures().items():
        assert mods, closure
        for mod in mods:
            assert not mod.startswith("gf180tcad.explain"), (closure, mod)
            if closure != "renders":
                assert mod != "gf180tcad.quantity", (closure, mod)
            path = _module_file(mod)
            if path is None:
                continue
            bad = {i for i in _imports(path, mod) if i.startswith("gf180tcad.explain")}
            assert not bad, f"{closure}: {mod} imports {sorted(bad)}"


def test_positive_control_import_scan(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("from gf180tcad.explain import numbers\nfrom . import explain\n", "utf-8")
    found = _imports(f, "gf180tcad.m")
    assert "gf180tcad.explain.numbers" in found and "gf180tcad.explain" in found


def _explain_modules() -> list[tuple[Path, str]]:
    pkg = SRC / "gf180tcad" / "explain"
    out = []
    for path in sorted(pkg.rglob("*.py")):
        rel = path.relative_to(SRC).with_suffix("")
        parts = rel.parts[:-1] if path.name == "__init__.py" else rel.parts
        out.append((path, ".".join(parts)))
    return out


# The one explain module that may read through gf180tcad.tcad, and what it may import: the 1D
# reader and the process-file reader the results pages use, both standard-library only (plan,
# task E2 as built). Every other explain module imports nothing from gf180tcad.tcad, and
# gf180tcad.tcad.stack (gdsfactory, shapely) is forbidden everywhere.
TCAD_ALLOWED = {"gf180tcad.explain.data": ("gf180tcad.tcad.moscap1d", "gf180tcad.tcad.process")}


def tcad_import_violations(path: Path, mod: str) -> set[str]:
    """The ``gf180tcad.tcad`` imports of module ``mod`` (file ``path``) outside
    :data:`TCAD_ALLOWED`; the bare package name counts only where nothing else is imported."""
    tcad = {i for i in _imports(path, mod) if i.split(".")[:2] == ["gf180tcad", "tcad"]}
    allowed = TCAD_ALLOWED.get(mod, ())
    bad = {
        i for i in tcad
        if i != "gf180tcad.tcad" and not any(i == a or i.startswith(f"{a}.") for a in allowed)
    }  # fmt: skip
    if tcad == {"gf180tcad.tcad"}:
        bad.add("gf180tcad.tcad")
    return bad


def test_explain_imports_nothing_from_tcad():
    """The explainer redraws the cell from committed data; only ``explain.data`` reads through
    the two standard-library-only TCAD readers (:data:`TCAD_ALLOWED`)."""
    mods = _explain_modules()
    assert {m for _, m in mods} >= {"gf180tcad.explain", "gf180tcad.explain.model", *TCAD_ALLOWED}
    for path, mod in mods:
        bad = tcad_import_violations(path, mod)
        assert not bad, f"{mod} imports {sorted(bad)}"


def test_positive_control_tcad_import_scan(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("import gf180tcad.tcad.stack\nfrom ..tcad import moscap1d\n", "utf-8")
    found = _imports(f, "gf180tcad.explain.m")
    assert "gf180tcad.tcad.stack" in found and "gf180tcad.tcad.moscap1d" in found
    # Any tcad import outside explain.data fails, even an allowed reader.
    assert tcad_import_violations(f, "gf180tcad.explain.model") == {
        "gf180tcad.tcad.stack", "gf180tcad.tcad.moscap1d",
    }  # fmt: skip
    # In explain.data the two readers pass and the stack still fails.
    assert tcad_import_violations(f, "gf180tcad.explain.data") == {"gf180tcad.tcad.stack"}
    g = tmp_path / "d.py"
    g.write_text("from gf180tcad.tcad import moscap1d, process\n", "utf-8")
    assert tcad_import_violations(g, "gf180tcad.explain.data") == set()
    assert tcad_import_violations(g, "gf180tcad.explain.figures") == {
        "gf180tcad.tcad.moscap1d", "gf180tcad.tcad.process",
    }  # fmt: skip


_DOCS_GROUP_ONLY = textwrap.dedent(
    """
    import sys
    for name in ("gdsfactory", "gplugins", "shapely", "gf180mcu", "devsim"):
        sys.modules[name] = None
    from pathlib import Path
    import gf180tcad.explain
    from gf180tcad.explain import figures, numbers
    figures.write_all(Path(sys.argv[1]))
    numbers.substitutions()
    print(sorted(p.name for p in Path(sys.argv[1]).iterdir()))
    """
)


def test_explain_runs_with_the_docs_group_only(tmp_path):
    r = subprocess.run(
        [sys.executable, "-c", _DOCS_GROUP_ONLY, str(tmp_path)],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip
    assert r.returncode == 0, r.stderr[-3000:]
    assert "-dark.svg" in r.stdout and "-light.svg" in r.stdout


def test_glossary_terms_of_the_section():
    text = (ROOT / "docs" / "glossary.md").read_text(encoding="utf-8")
    terms = Counter(re.findall(r"^(\S[^\n]*)\n  ", text, re.MULTILINE))
    for t in (
        "electron",
        "hole",
        "dopant",
        "donor",
        "acceptor",
        "intrinsic carrier density",
        "majority carrier",
        "minority carrier",
    ):
        assert terms[t] == 1, t


# --- the oxide and poly-silicon page (task E1) -----------------------------------------------

OXIDE_PAGE = EXPLAINED / "oxide-and-poly.md"
_RESULT = "results/tcad/calibration/nfet_05v0.result.json"


def test_unitless_value_has_no_trailing_space():
    assert _numbers().format_value(3.9, 2, "") == "3.9"


def test_oxide_capacitance_is_the_shared_formula():
    """C_ox comes from gf180tcad.derive.oxide_capacitance, never from a second copy, and agrees
    with the calibration result's own check.

    Hand value: ε_ox = 3.9, ε_0 = 8.8541878128e-14 F/cm and TOXE = 15.2 nm = 1.52e-6 cm give
    C_ox = 3.9 × 8.8541878128e-14 / 1.52e-6 = 2.271798e-7 F/cm² = 2.271798 fF/µm².
    """
    from gf180tcad import derive
    from gf180tcad.explain import idealised

    numbers = _numbers()
    assert "oxide_capacitance" not in idealised.FORMULAS
    assert "oxide_capacitance" in derive.FORMULAS
    for name in ("cox_nfet_cal", "cox_toxe_nfet"):
        n = numbers.REGISTRY[name]
        assert (n.kind, n.formula) == ("idealised", "oxide_capacitance"), name
    assert numbers.value("cox_toxe_nfet") == pytest.approx(2.271798, rel=1e-6)
    result = json.loads((ROOT / _RESULT).read_text("utf-8"))
    assert numbers.value("cox_nfet_cal") == pytest.approx(
        result["cox_check"]["c_ox_ff_per_um2"], rel=1e-12
    )
    assert numbers.value("cox_check_nfet") == result["cox_check"]["c_ox_ff_per_um2"]


def test_oxide_values_are_the_files():
    """The thicknesses and bounds the oxide page prints, traced to their files by hand."""
    numbers = _numbers()
    proc = tomllib.loads((ROOT / "data/process/nfet_05v0.toml").read_text("utf-8"))
    meta = json.loads(
        (ROOT / "results/tcad/moscap1d/nfet_05v0/calibrated/per_area.meta.json").read_text("utf-8")
    )
    result = json.loads((ROOT / _RESULT).read_text("utf-8"))
    assert numbers.value("toxe_nfet") == proc["param"]["toxe_nm"]["value"]
    assert numbers.value("toxp_nfet") == proc["param"]["toxp_nm"]["value"]
    assert numbers.value("epsrox_nfet") == proc["param"]["epsrox"]["value"]
    assert numbers.value("delta_nfet") == proc["centroid_allowance"]["delta_nm"]
    assert numbers.value("t_ox_nfet_cal") == meta["stack"]["t_ox_nm"]
    assert numbers.value("t_ox_upper_nfet") == result["bounds"]["t_ox_eff_nm"][1]
    assert numbers.value("poly_nfet") == meta["stack"]["poly_um"]
    assert numbers.value("cox_spec_min") == result["cox_check"]["spec"]["min"]
    assert numbers.value("cox_spec_max") == result["cox_check"]["spec"]["max"]


def test_stack_figure_draws_the_model():
    """Every drawn layer of the stack figure is the model's thickness times its stated scale,
    the layers touch, and the figure is written in both palettes."""
    from gf180tcad.explain import figures, model

    dev = model.device("nfet_05v0", "calibrated", scales=figures.STYLE["scales"])
    drawn = figures.stack_extents(dev)
    assert [layer.part for layer, _a, _b in drawn] == ["gate", "oxide", "body"]
    for layer, a, b in drawn:
        assert b - a == pytest.approx(layer.thickness_um * dev.scales.get(layer.part, 1)), layer
    for (_l, _a, b), (_m, c, _d) in pairwise(drawn):
        assert b == pytest.approx(c)
    assert "oxide-stack" in figures.FIGURES
    light = figures.FIGURES["oxide-stack"]("light")
    assert light.startswith(b"<?xml") and light != figures.FIGURES["oxide-stack"]("dark")


def test_oxide_page_prints_its_numbers():
    text = OXIDE_PAGE.read_text(encoding="utf-8")
    for key in ("toxe_nfet", "toxp_nfet", "t_ox_nfet_cal", "cox_nfet_cal", "cox_check_nfet"):
        assert "{{ x_" + key + " }}" in text, key
    assert "/_generated/explained/oxide-stack-light.svg" in text


def test_gate_voltage_shift_is_printed_from_the_calibration_file():
    """PR #95 re-review: the silicon page states the calibrated gate-voltage shift as a value."""
    numbers = _numbers()
    cal = json.loads((ROOT / "results/tcad/calibration/nfet_05v0.json").read_text("utf-8"))
    assert numbers.value("dv_fb_nfet_cal") == cal["values"]["dv_fb_v"]
    text = (EXPLAINED / "silicon-and-carriers.md").read_text(encoding="utf-8")
    assert "{{ x_dv_fb_nfet_cal }}" in text
    assert "small shift" not in text


# --- the energy bands and Fermi level page (task E1b) ----------------------------------------

BANDS_PAGE = EXPLAINED / "bands-and-fermi-level.md"


def test_band_gap_is_the_display_value_with_a_checked_source():
    """The band gap has one home, data/render/display.toml (plan, Decisions), and the source it
    cites there includes the Ioffe archive page that was read (lit-ioffe); #88 doubts the
    Sze and Ng values that were not read."""
    numbers = _numbers()
    display = tomllib.loads(DISPLAY.read_text("utf-8"))
    n = numbers.REGISTRY["band_gap_si"]
    assert (n.kind, n.source) == ("textbook", "data/render/display.toml")
    assert numbers.value("band_gap_si") == display["silicon"]["band_gap_ev"]
    assert "(lit-ioffe)" in numbers.citation("band_gap_si")
    assert "(lit-ioffe)=" in LITERATURE.read_text("utf-8")


def test_fermi_levels_against_hand_values():
    """The two Fermi levels the bands page prints, idealised from the committed dopings.

    Hand values (nfet calibrated per_area.meta.json: n_i = 8.265841554853887e9 cm⁻³,
    V_t = 0.02569257912108585 V, n_ch = 8.813323306821749e16 cm⁻³; NGATE = 1e20 cm⁻³):
    - gate: E_F − E_i = V_t·ln(1e20 / 8.2658e9) = 0.025692579 × 23.21653 = 0.596487 eV;
    - body: n = n_i²/n_ch = 775.24 cm⁻³, E_F − E_i = V_t·ln(775.24 / 8.2658e9) = −0.415763 eV,
      printed as 0.416 eV below the middle of the gap (factor −1).
    """
    numbers = _numbers()
    assert numbers.REGISTRY["fermi_gate_nfet"].formula == "boltzmann_fermi"
    assert numbers.value("fermi_gate_nfet") == pytest.approx(0.596487, abs=1e-6)
    assert numbers.value("fermi_body_nfet") == pytest.approx(-0.415763, abs=1e-6)
    assert numbers.text("fermi_body_nfet") == "0.416\u00a0eV"
    meta = json.loads(
        (ROOT / "results/tcad/moscap1d/nfet_05v0/calibrated/per_area.meta.json").read_text("utf-8")
    )
    assert numbers.value("vt_tcad") == meta["constants"]["vt_v"]


def test_band_figure_draws_the_numbers():
    """The flat band diagram puts each level where the page's numbers put it: the band edges
    half the gap above and below the middle, the Fermi level at the idealised value."""
    from gf180tcad.explain import figures, model

    numbers = _numbers()
    dev = model.device("nfet_05v0", "calibrated", scales=figures.STYLE["scales"])
    half = numbers.value("band_gap_si") / 2
    for part, fermi in (("gate", "fermi_gate_nfet"), ("body", "fermi_body_nfet")):
        lv = figures.band_levels(dev, part)
        assert lv["conduction"] == pytest.approx(half)
        assert lv["valence"] == pytest.approx(-half)
        assert lv["intrinsic"] == 0
        assert lv["fermi"] == pytest.approx(numbers.value(fermi), rel=1e-12), part
    assert dev.vt_v == numbers.value("vt_tcad")
    for name in ("bands-flat", "bands-stack"):
        light = figures.FIGURES[name]("light")
        assert light.startswith(b"<?xml") and light != figures.FIGURES[name]("dark"), name


def test_bands_page_prints_its_numbers():
    text = BANDS_PAGE.read_text(encoding="utf-8")
    for key in ("band_gap_si", "fermi_gate_nfet", "fermi_body_nfet", "vt_tcad"):
        assert "{{ x_" + key + " }}" in text, key
    for name in ("bands-stack", "bands-flat"):
        assert f"/_generated/explained/{name}-light.svg" in text, name


def test_glossary_terms_of_the_bands_page():
    text = (ROOT / "docs" / "glossary.md").read_text(encoding="utf-8")
    terms = Counter(re.findall(r"^(\S[^\n]*)\n  ", text, re.MULTILINE))
    for t in ("conduction band", "valence band", "band gap", "Fermi level"):
        assert terms[t] == 1, t


# --- the 2D cell, the pn junction and the transistor's parts (task E1b-2) --------------------

JUNCTION_PAGE = EXPLAINED / "pn-junction.md"
PARTS_PAGE = EXPLAINED / "transistor-parts.md"
_CELL = "results/tcad/moscap2d/nfet_05v0/calibrated/w10p0_l0p70/cv.meta.json"


def test_junction_formulas_against_hand_values():
    """The built-in potential and the depletion width of an idealised abrupt junction.

    - built_in_potential: N_A = N_D = 1e17 cm⁻³, n_i = 1e10 cm⁻³, V_t = 0.025 V give
      V_bi = 0.025·ln(1e34 / 1e20) = 0.025 × 32.23619 = 0.8059048 V.
    - depletion_width: N_A = N_D = 1e16 cm⁻³, V_bi = 0.7 V, ε_r = 11.7,
      ε_0 = 8.8541878128e-14 F/cm, q = 1.602176634e-19 C give
      W = √(2 × 11.7 × 8.8541878128e-14 × 0.7 × (2e-16) / 1.602176634e-19)
        = √(1.810429e-9) = 4.254917e-5 cm = 0.4255 µm.
    - The committed nfet values (calibrated n_ch = 8.813323306821749e16 cm⁻³, NSD peak 1e20 cm⁻³,
      n_i = 8.265841554853887e9 cm⁻³, V_t = 0.02569257912108585 V): V_bi = V_t·ln(8.8133e36 /
      6.8324e19) = 0.02569258 × 39.39857 = 1.012250 V, and W = 0.121925 µm.
    """
    from gf180tcad.explain import idealised

    assert idealised.built_in_potential(1e17, 1e17, 1e10, 0.025) == pytest.approx(
        0.8059048, rel=1e-6
    )
    w = idealised.depletion_width(1e16, 1e16, 0.7, 11.7, 8.8541878128e-14, 1.602176634e-19)
    assert w == pytest.approx(4.254917e-5, rel=1e-6)
    numbers = _numbers()
    assert numbers.value("vbi_nfet") == pytest.approx(1.012250, abs=1e-6)
    assert numbers.value("w_dep_nfet") * numbers.REGISTRY["w_dep_nfet"].factor == pytest.approx(
        0.121925, abs=1e-6
    )
    assert numbers.text("w_dep_nfet") == "0.122\u00a0µm"


def test_abrupt_junction_profile_is_consistent():
    """The drawn charge, field and potential of the depletion approximation: neutral overall, the
    field peaks at the junction and vanishes at both depletion edges, and the potential rises by
    the built-in potential across the region."""
    import numpy as np

    from gf180tcad.explain import idealised

    n_a, n_d, vbi, eps, e0, q = 1e17, 1e18, 0.9, 11.7, 8.8541878128e-14, 1.602176634e-19
    w = idealised.depletion_width(n_a, n_d, vbi, eps, e0, q)
    x = np.linspace(-w, w, 200001)
    p = idealised.abrupt_junction(x, n_a, n_d, vbi, eps, e0, q)
    # neutral to the grid step (1e-5 W) at each of the four edges
    assert np.trapezoid(p["charge_cm3"], x) == pytest.approx(0, abs=1e-4 * n_d * w)
    assert np.argmax(np.abs(p["field_v_per_cm"])) == np.argmin(np.abs(x))
    assert p["field_v_per_cm"][0] == pytest.approx(0, abs=1) and p["field_v_per_cm"][
        -1
    ] == pytest.approx(0, abs=1)
    assert p["potential_v"][0] - p["potential_v"][-1] == pytest.approx(vbi, rel=1e-9)


def test_cell_reads_the_committed_files():
    """The 2D cell of the model from cv.meta.json, the process file and the 1D stack only."""
    from gf180tcad.explain import model

    meta = json.loads((ROOT / _CELL).read_text("utf-8"))
    proc = tomllib.loads((ROOT / "data/process/nfet_05v0.toml").read_text("utf-8"))
    stack = json.loads(
        (ROOT / "results/tcad/moscap1d/nfet_05v0/calibrated/per_area.meta.json").read_text("utf-8")
    )["stack"]
    c = model.cell("nfet_05v0", "calibrated", "w10p0_l0p70", scales={}, drawn={})
    assert c.l_um == meta["geometry"]["l_um"] and c.w_um == meta["geometry"]["w_um"]
    assert c.t_ox_um == meta["meshed_t_ox_nm"] / 1000
    assert c.xj_um == proc["param"]["xj_um"]["value"]
    assert (c.poly_um, c.body_um) == (stack["poly_um"], stack["body_um"])
    assert c.n_sd_cm3 == meta["sd_peak_cm3"]
    assert c.n_body_cm3 == meta["tunables"]["n_ch_cm3"]["value"]
    assert c.contacts == tuple(meta["contacts"])
    assert (c.sd_dopant, c.body_dopant) == ("donor", "acceptor")


def test_cross_section_matches_cell():
    """Every drawn part of the cross-section is the cell's dimension times its stated scale, and a
    drawn-not-to-scale extent is named in the exaggeration statement."""
    from gf180tcad.explain import figures, model

    c = model.cell(
        "nfet_05v0", "calibrated", "w10p0_l0p70",
        scales=figures.STYLE["scales"], drawn=figures.STYLE["drawn_um"],
    )  # fmt: skip
    ext = figures.cell_extents(c)
    s_ox = c.scales.get("oxide", 1)
    gx0, gx1, gy0, gy1 = ext["gate"]
    assert gx1 - gx0 == pytest.approx(c.l_um)
    assert gy1 - gy0 == pytest.approx(c.poly_um)
    ox = ext["oxide"]
    assert ox[1] - ox[0] == pytest.approx(c.l_um) and ox[3] - ox[2] == pytest.approx(
        c.t_ox_um * s_ox
    )
    assert ox[2] == pytest.approx(gy1) and ox[3] == pytest.approx(0)
    for side in ("source", "drain"):
        x0, x1, y0, y1 = ext[side]
        assert (y0, y1) == (0, pytest.approx(c.xj_um))
        assert x1 - x0 == pytest.approx(c.drawn["source and drain width"])
    assert ext["source"][1] == pytest.approx(gx0) and ext["drain"][0] == pytest.approx(gx1)
    bx0, bx1, by0, by1 = ext["body"]
    assert (bx0, bx1) == (pytest.approx(ext["source"][0]), pytest.approx(ext["drain"][1]))
    assert by1 - by0 == pytest.approx(c.body_um)
    statement = model.exaggeration(c.scales, c.drawn)
    assert "Oxide thickness ×5" in statement and "source and drain width" in statement.lower()
    assert "Source and drain width chosen for the drawing, not to scale." in statement
    subs = figures.substitutions()
    assert subs["x_fig_parts_cell_scale"] == subs["x_fig_junction_cell_scale"] == statement
    assert "x_fig_junction_panels_scale" not in subs  # a plot of curves, not a drawing
    for name in ("parts-cell", "junction-cell", "junction-panels"):
        light = figures.FIGURES[name]("light")
        assert light.startswith(b"<?xml") and light != figures.FIGURES[name]("dark"), name


def test_parts_and_junction_pages_print_their_numbers():
    parts = PARTS_PAGE.read_text(encoding="utf-8")
    for key in ("l_cell", "w_cell", "t_ox_cell", "xj_nfet", "node_count_cell", "cgdl_nfet"):
        assert "{{ x_" + key + " }}" in parts, key
    assert "/_generated/explained/parts-cell-light.svg" in parts
    junction = JUNCTION_PAGE.read_text(encoding="utf-8")
    for key in ("vbi_nfet", "w_dep_nfet", "xj_nfet", "sd_peak_nfet", "n_ch_nfet_cal"):
        assert "{{ x_" + key + " }}" in junction, key
    for name in ("junction-cell", "junction-panels"):
        assert f"/_generated/explained/{name}-light.svg" in junction, name


def test_cell_values_are_the_files():
    numbers = _numbers()
    meta = json.loads((ROOT / _CELL).read_text("utf-8"))
    proc = tomllib.loads((ROOT / "data/process/nfet_05v0.toml").read_text("utf-8"))
    assert numbers.value("l_cell") == meta["geometry"]["l_um"]
    assert numbers.value("w_cell") == meta["geometry"]["w_um"]
    assert numbers.value("t_ox_cell") == meta["meshed_t_ox_nm"]
    assert numbers.value("node_count_cell") == meta["node_count"]
    assert numbers.value("xj_nfet") == proc["param"]["xj_um"]["value"]
    assert numbers.value("cgdl_nfet") == proc["param"]["cgdl_f_per_m"]["value"]


def test_glossary_terms_of_the_junction_page():
    text = (ROOT / "docs" / "glossary.md").read_text(encoding="utf-8")
    terms = Counter(re.findall(r"^(\S[^\n]*)\n  ", text, re.MULTILINE))
    assert terms["pn junction"] == 1


# --- the MOS capacitor page (task E2a) -------------------------------------------------------

MOSCAP_PAGE = EXPLAINED / "mos-capacitor.md"
_L10 = "w10p0_l10p00"
_SPICE_L10 = f"results/spice/ngspice/typical/nfet_05v0/{_L10}/metrics.json"


def test_docgen_reads_curves_through_explain_data():
    """The 1D and SPICE curve readers live once, in ``gf180tcad.explain.data``; docgen imports
    them (plan, task E2) and keeps no copy."""
    from gf180tcad import docgen
    from gf180tcad.explain import data

    for name in ("spice_columns", "spice_cv", "tcad_cgg", "u_sorted"):
        assert getattr(docgen, name) is getattr(data, name), name
    src = (SRC / "gf180tcad" / "docgen.py").read_text(encoding="utf-8")
    for gone in ("def _cols(", "def _u_sorted(", "1e15"):
        assert gone not in src, gone


def test_cv_figure_reads_the_committed_curves():
    """The moscap-cv curves are the committed 1D C per area through the BSIM4 bookkeeping and the
    committed SPICE cv sweeps, traced here by hand."""
    from gf180tcad.devices import CORNERS, DEVICES, geometry_id
    from gf180tcad.explain import figures
    from gf180tcad.tcad import moscap1d, process

    curves = figures.cv_curves("nfet_05v0", "calibrated", _L10)
    (geom,) = [g for g in DEVICES["nfet_05v0"].geometries if geometry_id(g) == _L10]
    m = moscap1d.read(ROOT / "results/tcad/moscap1d/nfet_05v0/calibrated")
    vg, _i, _p, total = m.area_scaled(geom, process.load("nfet_05v0"))
    assert list(curves["u"]) == sorted(vg)
    assert curves["tcad"][0] == pytest.approx(total[vg.index(min(vg))], rel=1e-12)
    tt = (ROOT / f"results/spice/ngspice/typical/nfet_05v0/{_L10}/cv.csv").read_text("utf-8")
    rows = [ln.split(",") for ln in tt.splitlines() if ln and not ln.startswith("#")]
    head, body = rows[0], rows[1:]
    cgg = [float(r[head.index("cgg")]) * 1e15 for r in body]
    vgs = [float(r[head.index("vg")]) for r in body]
    assert list(curves["u_spice"]) == sorted(vgs)
    assert curves["spice_tt"][0] == pytest.approx(cgg[vgs.index(min(vgs))], rel=1e-12)
    assert len(CORNERS) == 5
    assert all(curves["spice_lo"] <= curves["spice_tt"]) and all(
        curves["spice_tt"] <= curves["spice_hi"]
    )


def test_moscap_figures_are_registered():
    from gf180tcad.explain import figures

    for name in ("moscap-cell", "moscap-cv"):
        assert name in figures.FIGURES, name
        light = figures.FIGURES[name]("light")
        assert light.startswith(b"<?xml") and light != figures.FIGURES[name]("dark")
    subs = figures.substitutions()
    assert "x_fig_moscap_cell_scale" in subs and "x_fig_moscap_cv_scale" not in subs


def test_moscap_values_are_the_files():
    numbers = _numbers()
    spice = json.loads((ROOT / _SPICE_L10).read_text("utf-8"))["metrics"]
    rec = json.loads((ROOT / _RESULT).read_text("utf-8"))["per_geometry"][_L10]
    assert numbers.value("cgg_acc_l10") == spice["cgg_acc_ff"]
    assert numbers.value("cgg_inv_l10") == spice["cgg_inv_ff"]
    assert numbers.value("plateau_acc_l10") == rec["metrics"]["plateau_acc_max_rel"]
    assert numbers.value("plateau_inv_l10") == rec["metrics"]["plateau_inv_max_rel"]
    assert numbers.value("plateau_tol_l10") == rec["verdicts"]["plateau_acc"]["tolerance"]
    assert (
        rec["verdicts"]["plateau_inv"]["tolerance"] == rec["verdicts"]["plateau_acc"]["tolerance"]
    )
    assert numbers.text("plateau_tol_l10") == "5\u00a0%"


_VERDICT_FILES = {
    "verdict_nfet_1d": ("results/tcad/calibration/nfet_05v0.result.json", ["verdict"]),
    "verdict_pfet_1d": ("results/tcad/calibration/pfet_05v0.result.json", ["verdict"]),
}  # fmt: skip
# The crossing checks' verdicts at w10p0_l10p00, printed by the regions page.
_CROSSING_VERDICTS = {
    f"verdict_{c}_l10": ("results/tcad/calibration/nfet_05v0.result.json",
                         ["per_geometry", "w10p0_l10p00", "verdicts", c, "verdict"])
    for c in ("dv_dep", "dv_inv")
}  # fmt: skip


def test_verdict_words_are_read_from_the_result_files():
    numbers = _numbers()
    assert set(numbers.WORDS) == set(_VERDICT_FILES) | set(_CROSSING_VERDICTS)
    subs = numbers.substitutions()
    for name, (path, keys) in {**_VERDICT_FILES, **_CROSSING_VERDICTS}.items():
        v = json.loads((ROOT / path).read_text("utf-8"))
        for k in keys:
            v = v[k]
        assert numbers.word(name) == v == subs[f"x_{name}"], name
        assert v in ("Agree", "Same process", "Disagree"), (name, v)
        assert subs[f"x_{name}_term"] == f"{{term}}`{v}`", name


def _render(text: str, subs: dict[str, str]) -> str:
    return _SUBST.sub(lambda m: subs[m.group(1)], text)


def test_verdict_sentence_follows_an_edited_result_file(tmp_path):
    """Plan E2 exit criterion: a copy of the pfet result file with a new verdict changes the
    page's sentence, so no verdict is a typed word."""
    numbers = _numbers()
    src = "results/tcad/calibration/pfet_05v0.result.json"
    data = json.loads((ROOT / src).read_text("utf-8"))
    data["verdict"] = "Same process"
    for path, _keys in _VERDICT_FILES.values():
        dst = tmp_path / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text((ROOT / path).read_text("utf-8"), "utf-8")
    (tmp_path / src).write_text(json.dumps(data), "utf-8")
    text = MOSCAP_PAGE.read_text(encoding="utf-8")
    (line,) = [s for s in _sentences(text) if "{{ x_verdict_pfet_1d }}" in s]
    before = {f"x_{n}": numbers.word(n) for n in numbers.WORDS}
    after = {f"x_{n}": numbers.word(n, root=tmp_path) for n in numbers.WORDS}
    assert after["x_verdict_pfet_1d"] == "Same process"
    assert _render(line, {**numbers.substitutions(), **before}) != _render(
        line, {**numbers.substitutions(), **after}
    )
    assert "Same process" in _render(line, {**numbers.substitutions(), **after})


def test_moscap_page_prints_its_numbers():
    text = MOSCAP_PAGE.read_text(encoding="utf-8")
    for key in (*_VERDICT_FILES, "cgg_acc_l10", "cgg_inv_l10", "plateau_acc_l10", "plateau_inv_l10",
                "plateau_tol_l10", "two_d_table", "two_d_disagree", "corner_count",
                "fit_length_count", "dv_fb_nfet_cal"):  # fmt: skip
        assert "{{ x_" + key + " }}" in text, key
    for name in ("moscap-cell", "moscap-cv"):
        assert f"/_generated/explained/{name}-light.svg" in text, name
    for anchor in ("cv-agreement-mismatch", "cv-agreement-validation", "cv-agreement-windows",
                   "cv-agreement-metric"):  # fmt: skip
        assert f"<{anchor}>`" in text or f"{{ref}}`{anchor}`" in text, anchor


# --- the 2D verdicts: every committed one on the page ----------------------------------------

_VALIDATION = ROOT / "results" / "tcad" / "validation"


def _committed_two_d(root: Path = ROOT) -> list[tuple[str, float, float, str]]:
    """(device, W, L, verdict) of every ``two_d`` entry with a verdict, read here by hand."""
    out = []
    for path in sorted((root / "results" / "tcad" / "validation").glob("*.json")):
        doc = json.loads(path.read_text("utf-8"))
        for e in doc.get("two_d", {}).values():
            if e.get("verdict") is not None:
                out.append(
                    (doc["device"], e["geometry"]["w_um"], e["geometry"]["l_um"], e["verdict"])
                )
    return out


def _row(device: str, w: float, length: float, verdict: str) -> str:
    return f"| {{term}}`{device}` | {w:g} µm | {length:g} µm | {{term}}`{verdict}` |"


def test_every_two_d_verdict_is_on_the_page():
    """Each committed 2D verdict is a row of the page's table, and the table has no other row,
    so a new validated cell adds its row with no edit of the page."""
    from gf180tcad import explain

    cells = _committed_two_d()
    assert cells and {d for d, *_ in cells} == {"nfet_05v0", "pfet_05v0"}
    page = _render(MOSCAP_PAGE.read_text(encoding="utf-8"), explain.substitutions())
    rows = [ln for ln in page.splitlines() if ln.startswith("| {term}`")]
    assert sorted(rows) == sorted(_row(*c) for c in cells)
    assert rows == [_row(*c) for c in sorted(cells)]  # grouped by device, then W, then L


def _validation_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "results" / "tcad" / "validation"
    dst.mkdir(parents=True)
    for f in _VALIDATION.glob("*.json"):
        (dst / f.name).write_text(f.read_text("utf-8"), "utf-8")
    return dst


def test_two_d_table_grows_with_a_new_cell(tmp_path):
    numbers = _numbers()
    dst = _validation_copy(tmp_path)
    doc = json.loads((dst / "pfet_05v0.json").read_text("utf-8"))
    assert "w5p0_l0p70" not in doc["two_d"]  # a cell no validation file has
    new = json.loads(json.dumps(doc["two_d"]["w10p0_l0p70"]))
    new["geometry"] = {**new["geometry"], "geometry_id": "w5p0_l0p70", "w_um": 5.0}
    doc["two_d"]["w5p0_l0p70"] = new
    (dst / "pfet_05v0.json").write_text(json.dumps(doc), "utf-8")
    before = numbers.two_d_table().splitlines()
    after = numbers.two_d_table(root=tmp_path).splitlines()
    assert len(after) == len(before) + 1
    assert _row("pfet_05v0", 5.0, 0.7, new["verdict"]) in after


def test_disagree_clause_follows_the_checks(tmp_path):
    numbers = _numbers()
    assert numbers.two_d_disagree(root=tmp_path / "missing") == "No 2D cell is Disagree"
    dst = _validation_copy(tmp_path)
    one = numbers.two_d_disagree(root=tmp_path)
    assert one.startswith("Every Disagree cell fails only one check: ")
    doc = json.loads((dst / "nfet_05v0.json").read_text("utf-8"))
    cell = doc["two_d"]["w10p0_l0p60"]
    assert cell["verdict"] == "Disagree"
    cell["verdicts"]["plateau_acc"]["verdict"] = "Disagree"
    (dst / "nfet_05v0.json").write_text(json.dumps(doc), "utf-8")
    two = numbers.two_d_disagree(root=tmp_path)
    assert numbers.CHECKS["plateau_acc"] in two and two.startswith("The Disagree cells fail on ")


def _u_sign(verdict: dict) -> int:
    """The sign of u where a committed check is measured: a crossing's ``u_tcad``, or the u of
    a plateau's tightest point."""
    u = verdict["u_tcad"] if "u_tcad" in verdict else verdict["window"]["tightest"]["u"]
    return 1 if u > 0 else -1


def check_side_problems(checks: dict[str, str]) -> list[str]:
    """Each check's words must name, for each device, the gate-voltage sign where the check is
    measured: the sign of u in that device's committed result file times its polarity
    (u = polarity × Vg). Returns the mismatches."""
    from gf180tcad.devices import DEVICES

    problems = []
    for device in ("nfet_05v0", "pfet_05v0"):
        path = ROOT / f"results/tcad/calibration/{device}.result.json"
        verdicts = json.loads(path.read_text("utf-8"))["per_geometry"][_L10]["verdicts"]
        short = device.split("_")[0]
        for key, words in checks.items():
            sign = DEVICES[device].polarity * _u_sign(verdicts[key])
            want = ["positive" if sign > 0 else "negative"]
            got = re.findall(rf"{short}'s (negative|positive) side", words)
            if got != want:
                problems.append(f"{key} {device}: words say {got}, the result file gives {want}")
    return problems


def test_check_words_name_both_signs():
    """The checks run in u = polarity × Vg: each device's side is named with its own sign."""
    numbers = _numbers()
    assert set(numbers.CHECKS) == {"plateau_acc", "plateau_inv", "dv_dep", "dv_inv"}
    assert not check_side_problems(numbers.CHECKS)


def test_positive_control_check_sides():
    """A swapped pair (nfet and pfet signs exchanged) and a one-device wording both fail."""
    checks = dict(_numbers().CHECKS)
    swap = {"negative": "positive", "positive": "negative"}
    swapped = {
        k: re.sub(r"negative|positive", lambda m: swap[m.group(0)], v) for k, v in checks.items()
    }
    assert len(check_side_problems(swapped)) == 2 * len(checks)
    one = {**checks, "dv_dep": "the halfway-level crossing on the nfet's negative side"}
    assert check_side_problems(one) == [
        "dv_dep pfet_05v0: words say [], the result file gives ['positive']"
    ]


def test_crossing_words_name_one_level():
    """Both crossing checks use one level definition, (C_min + C_acc)/2 of each curve on its own
    (``calibrate.cv.crossings``): their words name the same level and differ only in the sides,
    so neither suggests a level between the minimum and the inversion flat part. The regions
    page defines that level per curve, and describes the start of inversion, (C_min + C_inv)/2
    of the SPICE curve, without the word "halfway", so a reader does not take the two as one."""
    numbers = _numbers()
    dep, inv = numbers.CHECKS["dv_dep"], numbers.CHECKS["dv_inv"]
    swap = {"negative": "positive", "positive": "negative"}
    assert re.sub(r"negative|positive", lambda m: swap[m.group(0)], dep) == inv
    assert "halfway-level crossing" in dep and " up " not in inv and " down " not in dep
    page = REGIONS_PAGE.read_text(encoding="utf-8")
    dip = page[page.index("(explained-regions-dip)=") : page.index("(explained-regions-bands)=")]
    flat = " ".join(dip.split())
    assert "halfway level of each curve lies midway between its own minimum and its" in flat
    assert "crosses its own halfway level" in flat
    start = flat[flat.index("Inversion starts") :]
    assert "halfway" not in start[: start.index(".")]


def test_disagree_cells_are_the_issue_on_the_page():
    """The page links issue #108 (the depletion crossing) beside the Disagree clause: while a 2D
    cell is Disagree, that check is among the failing ones."""
    numbers = _numbers()
    bad = [c for c in numbers.two_d_cells() if c.verdict == "Disagree"]
    if bad:
        assert all("dv_dep" in c.failing for c in bad)
    assert "issues/108" in MOSCAP_PAGE.read_text(encoding="utf-8")


_COUNT_WORDS = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|ten)\s+(\{term\}`)?"
    r"(corners?|gate lengths?|cells?|geometries)",
    re.IGNORECASE,
)


def test_moscap_page_types_no_count():
    """Counts that can drift (corners, fit lengths, cells) come from substitutions; the fixed
    ones (the three layers of the stack, the two plates of a capacitor) are words."""
    assert not _COUNT_WORDS.findall(MOSCAP_PAGE.read_text(encoding="utf-8"))
    for bad in ("spans its five corners", "at three gate lengths", "Disagree at three cells"):
        assert _COUNT_WORDS.search(bad), bad


def test_counts_are_derived(tmp_path):
    from gf180tcad.devices import CORNERS

    numbers = _numbers()
    src = "results/tcad/calibration/nfet_05v0.result.json"
    fit = json.loads((ROOT / src).read_text("utf-8"))
    lengths = {g["geometry"]["l_um"] for g in fit["per_geometry"].values()}
    pfet_fit = json.loads(
        (ROOT / "results/tcad/calibration/pfet_05v0.result.json").read_text("utf-8")
    )
    assert numbers.counts() == {
        "corner_count": len(CORNERS),
        "fit_length_count": len(lengths),
        "budget": fit["budget"],
        "budget_used": fit["budget_used"],
        "nfev_nfet": fit["optimiser"]["nfev"],
        "nfev_pfet": pfet_fit["optimiser"]["nfev"],
    }
    subs = numbers.substitutions()
    assert subs["x_corner_count"] == str(len(CORNERS))
    assert subs["x_fit_length_count"] == str(len(lengths))
    # A copy of the result file with one more fit length: the count follows it.
    extra = json.loads(json.dumps(next(iter(fit["per_geometry"].values()))))
    extra["geometry"] = {**extra["geometry"], "geometry_id": "w10p0_l5p00", "l_um": 5.0}
    fit["per_geometry"]["w10p0_l5p00"] = extra
    (tmp_path / src).parent.mkdir(parents=True)
    (tmp_path / src).write_text(json.dumps(fit), "utf-8")
    pfet = "results/tcad/calibration/pfet_05v0.result.json"  # counts() also reads the budgets
    (tmp_path / pfet).write_text((ROOT / pfet).read_text("utf-8"), "utf-8")
    assert numbers.counts(root=tmp_path)["fit_length_count"] == len(lengths) + 1


# --- the regions page (task E2b) -------------------------------------------------------------

REGIONS_PAGE = EXPLAINED / "accumulation-depletion-inversion.md"
_REGIONS_KEYS = {
    "u_fb_l10": ["spice_regions", "u_fb"],
    "u_t_l10": ["spice_regions", "u_t"],
    "u_min_l10": ["spice_regions", "u_min"],
    "c_min_l10": ["spice_regions", "c_min"],
    "u_dep_spice_l10": ["spice_regions", "u_dep"],
    "u_inv_spice_l10": ["spice_regions", "u_inv"],
    "u_dep_tcad_l10": ["tcad_crossings", "u_dep"],
    "u_inv_tcad_l10": ["tcad_crossings", "u_inv"],
    "dv_tol_l10": ["verdicts", "dv_dep", "tolerance_v"],
}


def _l10_record() -> dict:
    return json.loads((ROOT / _RESULT).read_text("utf-8"))["per_geometry"][_L10]


def test_region_values_are_the_files():
    from gf180tcad.devices import DEVICES

    numbers = _numbers()
    assert DEVICES["nfet_05v0"].polarity == 1  # the nfet's u is its gate voltage
    rec = _l10_record()
    for name, keys in _REGIONS_KEYS.items():
        v = rec
        for k in keys:
            v = v[k]
        assert numbers.value(name) == v, name
    assert rec["verdicts"]["dv_inv"]["tolerance_v"] == rec["verdicts"]["dv_dep"]["tolerance_v"]
    assert numbers.text("dv_tol_l10") == "50\u00a0mV"
    for check in ("dv_dep", "dv_inv"):
        assert numbers.word(f"verdict_{check}_l10") == rec["verdicts"][check]["verdict"], check


def test_regions_follow_the_committed_crossings():
    """Plan E2 test: the shaded region edges of the C-V figure are the result file's marks."""
    from gf180tcad.explain import figures

    rec = _l10_record()["spice_regions"]
    assert figures.region_edges() == (rec["u_fb"], rec["u_t"])
    for palette in figures.PALETTES:
        fig = figures.cv_regions_figure(palette)
        (ax,) = fig.axes
        spans = sorted(
            (p.get_x(), p.get_x() + p.get_width()) for p in ax.patches if p.get_width() > 0
        )
        assert len(spans) == len(figures.REGIONS)
        edges = [b for _a, b in spans[:-1]]
        assert edges == [rec["u_fb"], rec["u_t"]]
        assert [a for a, _b in spans[1:]] == edges
        labels = [t.get_text() for t in ax.texts]
        assert labels == list(figures.REGIONS)


def test_regions_follow_an_edited_result_file(monkeypatch):
    """A new mark in the result file moves the shading: the edges are read, never typed."""
    from gf180tcad.explain import figures

    numbers = _numbers()
    real = numbers.value
    moved = {"u_fb_l10": real("u_fb_l10") - 0.25, "u_t_l10": real("u_t_l10") + 0.25}
    monkeypatch.setattr(numbers, "value", lambda name: moved.get(name, real(name)))
    assert figures.region_edges() == (moved["u_fb_l10"], moved["u_t_l10"])
    (ax,) = figures.cv_regions_figure("light").axes
    starts = sorted(p.get_x() for p in ax.patches if p.get_width() > 0)
    assert starts[1:] == [moved["u_fb_l10"], moved["u_t_l10"]]


def test_flat_band_and_threshold_against_hand_values():
    """V_FB = −V_t·ln(N_gate·N_A/n_i²); V_T = V_FB + 2ψ_B + √(4 ε q N_A ψ_B)/C_ox, worked here
    with plain arithmetic (C_ox in F/cm²: 1 fF/µm² = 1e-7 F/cm²)."""
    from gf180tcad.explain import idealised

    vt, ni, na, ng = 0.025, 1.0e10, 1.0e17, 1.0e20
    vfb = -vt * math.log(ng * na / ni**2)
    assert idealised.flat_band(na, ng, ni, vt) == pytest.approx(vfb, rel=1e-12)
    assert vfb == pytest.approx(-0.978, abs=1e-3)
    psi_b = vt * math.log(na / ni)
    assert idealised.bulk_potential(na, ni, vt) == pytest.approx(psi_b, rel=1e-12)
    eps, e0, q, cox = 11.7, 8.854e-14, 1.602e-19, 2.0
    vth = vfb + 2 * psi_b + math.sqrt(4 * eps * e0 * q * na * psi_b) / (cox * 1e-7)
    assert idealised.threshold(na, ni, vt, vfb, eps, e0, q, cox) == pytest.approx(vth, rel=1e-12)
    # By hand: ψ_B = 0.025 × ln(1e7) = 0.40295; √(4 × 11.7 × 8.854e-14 × 1.602e-19 × 1e17 × ψ_B)
    # = 1.6355e-7 C/cm², over 2e-7 F/cm² = 0.8177 V; V_FB = −0.025 × ln(1e17) = −0.9786 V.
    assert vth == pytest.approx(-0.9786 + 0.8059 + 0.8177, abs=1e-3)


def test_surface_bending_against_hand_values():
    from gf180tcad.explain import idealised

    eps, e0, q, na, psi_s = 11.7, 8.854e-14, 1.602e-19, 1.0e17, 0.8
    w = math.sqrt(2 * eps * e0 * psi_s / (q * na))
    assert idealised.depletion_depth(psi_s, na, eps, e0, q) == pytest.approx(w, rel=1e-12)
    assert w == pytest.approx(1.0175e-5, rel=1e-3)  # 0.102 µm by hand
    x = [0.0, w / 2, w, 2 * w]
    got = idealised.surface_bending(x, psi_s, na, eps, e0, q)
    assert list(got) == pytest.approx([psi_s, psi_s / 4, 0.0, 0.0])
    assert list(idealised.surface_bending(x, 0.0, na, eps, e0, q)) == [0.0] * 4


def test_bulk_potential_is_the_bands_page_value():
    """ψ_B of the regions page is the body's Fermi-level distance the bands page prints."""
    numbers = _numbers()
    from gf180tcad.explain import idealised

    psi_b = idealised.bulk_potential(
        *(numbers.value(k) for k in ("n_ch_nfet_cal", "n_i_tcad", "vt_tcad"))
    )
    assert psi_b == pytest.approx(-numbers.value("fermi_body_nfet"), rel=1e-12)


def test_band_regimes_draw_the_idealised_bending():
    """Each panel's middle of the gap is ψ_B minus the bending of its state, from the formula."""
    from gf180tcad.explain import figures, idealised

    numbers = _numbers()
    na = numbers.value("n_ch_nfet_cal")
    consts = (numbers.value("eps_si_tcad"), numbers.value("eps0_tcad"), numbers.value("q_tcad"))
    psi_b = idealised.bulk_potential(na, numbers.value("n_i_tcad"), numbers.value("vt_tcad"))
    half = numbers.value("band_gap_si") / 2
    fig = figures.band_regimes_figure("light")
    axes = fig.axes
    assert [ax.get_title() for ax in axes] == list(figures.REGIMES)
    for ax, k in zip(axes, figures.REGIMES.values(), strict=True):
        lines = {ln.get_label(): ln for ln in ax.get_lines()}
        x_um, mid = lines["middle of the gap"].get_data()
        assert mid[0] == pytest.approx(psi_b - k * psi_b, abs=1e-12)
        assert mid[-1] == pytest.approx(psi_b, abs=1e-12)
        x_cm = x_um / figures.UNITS["um_per_cm"]
        want = psi_b - idealised.surface_bending(x_cm, k * psi_b, na, *consts)
        assert list(mid) == pytest.approx(list(want))
        _x, top = lines["conduction band edge"].get_data()
        assert list(top - mid) == pytest.approx([half] * len(mid))
    # Inversion: the surface is as n-type as the body is p-type.
    assert axes[-1].get_lines()[1].get_data()[1][0] == pytest.approx(-psi_b)


def test_band_regimes_sheets_stand_apart_from_the_band_edges():
    """The carrier sheets (holes in accumulation, electrons in inversion) are circles edged in the
    text colour beyond their band edge, so at 400 px the accumulation panel differs from the
    flat-band panel, whose bands are the same."""
    from gf180tcad.explain import figures

    for palette in figures.PALETTES:
        pal = figures.PALETTES[palette]
        axes = figures.band_regimes_figure(palette).axes
        for ax in axes:
            lines = {ln.get_label(): ln for ln in ax.get_lines()}
            sheets = [lab for lab in lines if lab.endswith("at the surface")]
            want = {"accumulation": ["holes at the surface"],
                    "inversion": ["electrons at the surface"]}.get(ax.get_title(), [])  # fmt: skip
            assert sheets == want, ax.get_title()
            for lab in sheets:
                sheet = lines[lab]
                edge_name = "valence" if lab.startswith("holes") else "conduction"
                edge = lines[f"{edge_name} band edge"]
                assert sheet.get_marker() == "o" and sheet.get_linestyle() == "None"
                assert sheet.get_markeredgecolor() == pal["text"] != edge.get_color()
                e0 = edge.get_ydata()[0]
                gap = sheet.get_ydata() - e0
                assert all(gap < 0) if lab.startswith("holes") else all(gap > 0)


def test_regions_figures_are_registered():
    from gf180tcad.explain import figures

    for name in ("cv-regions", "band-regimes"):
        assert name in figures.FIGURES, name
        light = figures.FIGURES[name]("light")
        assert light.startswith(b"<?xml") and light != figures.FIGURES[name]("dark")
    subs = figures.substitutions()
    assert "x_fig_cv_regions_scale" not in subs and "x_fig_band_regimes_scale" not in subs


def test_regions_page_prints_its_numbers():
    text = REGIONS_PAGE.read_text(encoding="utf-8")
    for key in (*_REGIONS_KEYS, "v_fb_nfet", "v_t_nfet", "verdict_dv_dep_l10",
                "verdict_dv_inv_l10", "verdict_pfet_1d", "two_d_disagree"):  # fmt: skip
        assert "{{ x_" + key + " }}" in text, key
    for name in ("cv-regions", "band-regimes"):
        assert f"/_generated/explained/{name}-light.svg" in text, name
    for anchor in ("cv-agreement-mismatch", "cv-agreement-validation", "cv-agreement-metric"):
        assert f"<{anchor}>`" in text or f"{{ref}}`{anchor}`" in text, anchor
    assert not _COUNT_WORDS.findall(text)


def test_glossary_terms_of_the_regions_page():
    text = (ROOT / "docs" / "glossary.md").read_text(encoding="utf-8")
    terms = Counter(re.findall(r"^(\S[^\n]*)\n  ", text, re.MULTILINE))
    for t in ("accumulation", "depletion", "inversion", "flat band"):
        assert terms[t] == 1, t
        entry = text[text.index(f"\n{t}\n") :].split("\n\n", 1)[0]
        assert "{ref}`explained-regions" in entry, t


# --- the mesh window figure (renders plan Task R0, docs/reproduce/index.md) -------------------

REPRODUCE_PAGE = ROOT / "docs" / "reproduce" / "index.md"


def test_mesh_window_figure_draws_the_window_rule():
    """The reproduce page's figure outlines the window that meshcut cuts with its default rule:
    a quarter gate length either side of the gate, from the drawn poly top down to
    WINDOW_DEPTH_UM below the silicon surface (depth grows downwards in the drawing)."""
    from gf180tcad import meshcut
    from gf180tcad.explain import figures, model

    c = model.cell("nfet_05v0", "calibrated", "w10p0_l0p60", scales=figures.STYLE["scales"],
                   drawn=figures.STYLE["drawn_um"])  # fmt: skip
    gate = figures.cell_extents(c)["gate"]
    box = figures.window_box(c)
    assert box.x0 == pytest.approx(gate.x0 - meshcut.WINDOW_KX * c.l_um)
    assert box.x1 == pytest.approx(gate.x1 + meshcut.WINDOW_KX * c.l_um)
    assert box.y0 == pytest.approx(gate.y0)  # the poly top
    assert box.y1 == pytest.approx(meshcut.WINDOW_DEPTH_UM)
    assert "mesh-window" in figures.FIGURES
    light = figures.FIGURES["mesh-window"]("light")
    assert light.startswith(b"<?xml") and light != figures.FIGURES["mesh-window"]("dark")
    assert b"window" in light
    text = REPRODUCE_PAGE.read_text(encoding="utf-8")
    for palette in figures.PALETTES:
        assert f"/_generated/explained/mesh-window-{palette}.svg" in text, palette
    assert "{numref}`mesh-window-figure`" in text


# --- the C-V curve page (task E2c) -----------------------------------------------------------

CV_PAGE = EXPLAINED / "cv-curve.md"
# The calibration's start and fitted values of the three tunables, as the result file records
# them, and the registry entries that print them.
_START_KEYS = {
    "t_ox_nfet_start": "t_ox_eff_nm",
    "n_ch_nfet_start": "n_ch_cm3",
    "dv_fb_nfet_start": "dv_fb_v",
}
_FITTED_KEYS = {
    "t_ox_nfet_cal": "t_ox_eff_nm",
    "n_ch_nfet_cal": "n_ch_cm3",
    "dv_fb_nfet_cal": "dv_fb_v",
}
# The fit's errors at w10p0_l10p00, from the result file's metrics.
_CV_METRICS = {
    "dv_dep_l10": "dv_dep_v",
    "dv_inv_l10": "dv_inv_v",
    "depletion_l10": "depletion_max_rel",
}


def test_cv_parts_values_are_the_files():
    """The start and fitted values the page prints are the result file's ``start`` and
    ``values``; the fitted ones are also the calibration file's and the 1D stack's."""
    numbers = _numbers()
    result = json.loads((ROOT / _RESULT).read_text("utf-8"))
    cal = json.loads((ROOT / "results/tcad/calibration/nfet_05v0.json").read_text("utf-8"))
    for name, key in _START_KEYS.items():
        assert numbers.value(name) == result["start"][key], name
    for name, key in _FITTED_KEYS.items():
        assert numbers.value(name) == result["values"][key] == cal["values"][key], name
    # The start values are the process file's values (the card's TOXE and NDEP, and 0 V).
    proc = tomllib.loads((ROOT / "data/process/nfet_05v0.toml").read_text("utf-8"))["param"]
    for name, key in _START_KEYS.items():
        assert numbers.value(name) == proc[key]["value"], name
    assert numbers.value("t_ox_nfet_start") == numbers.value("toxe_nfet")
    assert numbers.value("n_ch_nfet_start") == numbers.value("ndep_nfet")
    rec = _l10_record()["metrics"]
    for name, key in _CV_METRICS.items():
        assert numbers.value(name) == rec[key], name
    assert numbers.text("dv_fb_nfet_start") == "0\u00a0V"


def test_cv_parts_draws_the_start_and_fitted_curves():
    """The cv-parts figure draws the committed start and calibrated 1D curves through the BSIM4
    bookkeeping, and the SPICE typical curve, read by the readers the results pages use."""
    from gf180tcad.explain import figures

    for palette in figures.PALETTES:
        (ax,) = figures.cv_parts_figure(palette).axes
        lines = {ln.get_label(): ln for ln in ax.get_lines()}
        assert set(figures.CV_PARTS_LINES.values()) <= set(lines)
        for params, label in figures.CV_PARTS_LINES.items():
            want = figures.cv_curves(
                "nfet_05v0", "calibrated" if params == "spice" else params, _L10
            )
            x, y = lines[label].get_data()
            if params == "spice":
                assert list(x) == list(want["u_spice"]) and list(y) == list(want["spice_tt"])
            else:
                assert list(x) == list(want["u"]) and list(y) == list(want["tcad"])
    start = figures.cv_curves("nfet_05v0", "start", _L10)["tcad"]
    fitted = figures.cv_curves("nfet_05v0", "calibrated", _L10)["tcad"]
    assert list(start) != list(fitted)


def test_cv_parts_labels_name_the_parameters_at_the_committed_marks():
    """Each part of the curve carries the parameter that sets it; the dip label points at the
    SPICE minimum and the shift arrow sits on the SPICE falling-side crossing, from the result
    file."""
    from matplotlib.patches import ArrowStyle

    from gf180tcad.explain import figures

    numbers = _numbers()
    (ax,) = figures.cv_parts_figure("light").axes
    texts = {t.get_text(): t for t in ax.texts}
    assert set(figures.CV_PARTS.values()) <= set(texts)
    dip = texts[figures.CV_PARTS["dip"]]
    assert tuple(dip.xy) == (numbers.value("u_min_l10"), numbers.value("c_min_l10"))
    shift = texts[figures.CV_PARTS["position"]]
    assert shift.xy[0] == pytest.approx(numbers.value("u_dep_spice_l10"))
    # The shift arrow: one head, at its more positive end, centred on the crossing.
    (arrow,) = [t for t in ax.texts if not t.get_text() and t.arrow_patch is not None]
    style = arrow.arrow_patch.get_arrowstyle()
    assert isinstance(style, ArrowStyle.CurveB), style
    head, tail = arrow.xy, arrow.xyann
    assert head[0] > tail[0] and head[1] == tail[1]
    assert (head[0] + tail[0]) / 2 == pytest.approx(numbers.value("u_dep_spice_l10"))
    lo, hi = figures.region_edges()
    acc = texts[figures.CV_PARTS["accumulation"]]
    inv = texts[figures.CV_PARTS["inversion"]]
    assert acc.xy[0] < lo and inv.xy[0] > hi


def test_cv_page_dip_order_is_the_curves():
    """The page says the start curve's dip is shallower than the SPICE minimum it prints and the
    fitted curve's dip is deeper: the committed curves' minima, in that order."""
    from gf180tcad.explain import figures

    c_min = _numbers().value("c_min_l10")
    fitted = figures.cv_curves("nfet_05v0", "calibrated", _L10)
    start = figures.cv_curves("nfet_05v0", "start", _L10)
    assert min(fitted["spice_tt"]) == pytest.approx(c_min)
    assert min(fitted["tcad"]) < c_min < min(start["tcad"])


def test_cv_parts_figure_is_registered():
    from gf180tcad.explain import figures

    assert "cv-parts" in figures.FIGURES
    light = figures.FIGURES["cv-parts"]("light")
    assert light.startswith(b"<?xml") and light != figures.FIGURES["cv-parts"]("dark")
    assert "x_fig_cv_parts_scale" not in figures.substitutions()


def test_cv_page_prints_its_numbers():
    text = CV_PAGE.read_text(encoding="utf-8")
    for key in (*_START_KEYS, *_FITTED_KEYS, *_CV_METRICS, "plateau_acc_l10", "plateau_inv_l10",
                "plateau_tol_l10", "dv_tol_l10", "cox_toxe_nfet", "cox_nfet_cal",
                "verdict_nfet_1d", "verdict_pfet_1d", "two_d_disagree",
                "fit_length_count", "c_min_l10"):  # fmt: skip
        assert "{{ x_" + key + " }}" in text, key
    assert "/_generated/explained/cv-parts-light.svg" in text
    for anchor in ("cv-agreement-mismatch", "cv-agreement-validation", "cv-agreement-deviation",
                   "explained-regions-dip"):  # fmt: skip
        assert f"<{anchor}>`" in text or f"{{ref}}`{anchor}`" in text, anchor
    assert not _COUNT_WORDS.findall(text)


def test_cv_page_table_rows_are_the_registry():
    """The page's table of tunables has one row per tunable, start then fitted, by substitution."""
    text = CV_PAGE.read_text(encoding="utf-8")
    for start, fitted in zip(_START_KEYS, _FITTED_KEYS, strict=True):
        row = rf"^\|[^|\n]+\| \{{\{{ x_{start} \}}\}} \| \{{\{{ x_{fitted} \}}\}} \|$"
        assert re.search(row, text, re.MULTILINE), (start, fitted)


# --- the calibration page (task E2d) ---------------------------------------------------------

CALIBRATION_PAGE = EXPLAINED / "calibration.md"
_FITS = {d: f"results/tcad/calibration/{d}.result.json" for d in ("nfet_05v0", "pfet_05v0")}


def _fit(device: str, root: Path = ROOT) -> dict:
    return json.loads((root / _FITS[device]).read_text("utf-8"))


def _fit_copy(tmp_path: Path) -> Path:
    for path in _FITS.values():
        dst = tmp_path / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text((ROOT / path).read_text("utf-8"), "utf-8")
    return tmp_path


def test_calibration_table_from_result_file():
    """Plan E2 test: each row of a fit table is the result file's bounds, start and values."""
    numbers = _numbers()
    for device in _FITS:
        doc = _fit(device)
        assert doc["params"] == list(numbers.TUNABLES)
        rows = numbers.fit_table(device).splitlines()
        assert rows[0] == "| Number | Lower limit | Start | Fitted | Upper limit |"
        assert len(rows) == 2 + len(numbers.TUNABLES)
        for row, name in zip(rows[2:], numbers.TUNABLES, strict=True):
            words, unit, most = numbers.TUNABLES[name]
            lo, hi = doc["bounds"][name]
            # The unit sits in the row label, so the cells are narrow enough for a phone.
            want = [f"{words} ({unit})"] + [
                numbers.shortest(v, "", most)
                for v in (lo, doc["start"][name], doc["values"][name], hi)
            ]
            assert [c.strip() for c in row.strip("|").split("|")] == want, (device, name)


def test_fit_table_follows_an_edited_result_file(tmp_path):
    numbers = _numbers()
    root = _fit_copy(tmp_path)
    doc = _fit("pfet_05v0")
    doc["values"]["t_ox_eff_nm"] = 16.25
    doc["bounds"]["dv_fb_v"] = [-0.3, 0.3]
    (root / _FITS["pfet_05v0"]).write_text(json.dumps(doc), "utf-8")
    table = numbers.fit_table("pfet_05v0", root=root)
    assert table != numbers.fit_table("pfet_05v0")
    assert "| Oxide thickness (nm) |" in table and "| 16.25 |" in table
    assert "| −0.3 |" in table and "| 0.3 |" in table


def test_shortest_keeps_the_value():
    numbers = _numbers()
    assert numbers.shortest(0.2, "V", 3) == "0.2\u00a0V"
    assert numbers.shortest(-0.2, "V", 3) == "−0.2\u00a0V"
    assert numbers.shortest(0.0, "V", 3) == "0\u00a0V"
    assert numbers.shortest(16.050483616382458, "nm", 4) == "16.05\u00a0nm"
    assert numbers.shortest(1.7e17, "cm⁻³", 3) == "1.7\u00a0×\u00a010¹⁷\u00a0cm⁻³"
    assert numbers.shortest(6.2967947909822296e16, "cm⁻³", 3) == "6.3\u00a0×\u00a010¹⁶\u00a0cm⁻³"


def test_limit_kinds_are_the_process_files(tmp_path):
    numbers = _numbers()
    want = {}
    for device in _FITS:
        params = tomllib.loads((ROOT / f"data/process/{device}.toml").read_text("utf-8"))["param"]
        want[device] = {
            n: (params[n]["start_kind"], *params[n]["bounds_kind"]) for n in numbers.TUNABLES
        }
    assert want["nfet_05v0"] == want["pfet_05v0"] == numbers.limit_kinds()
    rows = numbers.limit_kinds_table().splitlines()[2:]
    for row, (name, kinds) in zip(rows, want["nfet_05v0"].items(), strict=True):
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells == [numbers.TUNABLES[name][0], *(numbers.KIND_WORDS[k] for k in kinds)]
    # A copy whose pfet start comes from elsewhere: the two transistors differ, which the table
    # cannot show in one row, so it refuses.
    for device in _FITS:
        dst = tmp_path / f"data/process/{device}.toml"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text((ROOT / f"data/process/{device}.toml").read_text("utf-8"), "utf-8")
    p = tmp_path / "data/process/pfet_05v0.toml"
    text = p.read_text("utf-8")
    assert text.count('start_kind = "project-choice"') == 1
    p.write_text(text.replace('start_kind = "project-choice"', 'start_kind = "card"'), "utf-8")
    with pytest.raises(ValueError, match="differ"):
        numbers.limit_kinds(root=tmp_path)


def test_bound_hits_sentence_follows_the_result_files(tmp_path):
    numbers = _numbers()
    assert all(_fit(d)["bound_hits"] == {} for d in _FITS)
    assert numbers.bound_hits() == "No fitted value of either transistor sits on a limit"
    root = _fit_copy(tmp_path)
    doc = _fit("nfet_05v0")
    doc["bound_hits"] = {"t_ox_eff_nm": "upper"}
    (root / _FITS["nfet_05v0"]).write_text(json.dumps(doc), "utf-8")
    assert numbers.bound_hits(root=root) == (
        "The fit stopped on a limit for the oxide thickness of the nfet_05v0"
    )


def test_every_fit_verdict_is_a_row(tmp_path):
    numbers = _numbers()
    want = sorted(
        (d, e["geometry"]["w_um"], e["geometry"]["l_um"], e["verdict"])
        for d in _FITS
        for e in _fit(d)["per_geometry"].values()
    )
    rows = numbers.fit_verdict_table().splitlines()[2:]
    assert rows == [_row(*c) for c in want]
    root = _fit_copy(tmp_path)
    doc = _fit("pfet_05v0")
    doc["per_geometry"]["w10p0_l2p00"]["verdict"] = "Agree"
    (root / _FITS["pfet_05v0"]).write_text(json.dumps(doc), "utf-8")
    assert _row("pfet_05v0", 10, 2, "Agree") in numbers.fit_verdict_table(root=root)


def test_corner_spread_is_the_committed_corners():
    """The lowest and highest of each quantity are the min and max over every corner's file;
    the crossings' are the corner window of the result file, which is the same min and max."""
    from gf180tcad.devices import CORNERS

    numbers = _numbers()
    gid = numbers.SPREAD_GEOMETRY
    metrics = {
        c: json.loads(
            (ROOT / f"results/spice/ngspice/{c}/nfet_05v0/{gid}/metrics.json").read_text("utf-8")
        )["metrics"]
        for c in CORNERS
    }
    env = json.loads((ROOT / "results/spice/envelope.json").read_text("utf-8"))
    rec = _fit("nfet_05v0")["per_geometry"][gid]
    got = {s.words: s for s in numbers.corner_spread()}
    for key, words in (
        ("cgg_acc_ff", "Accumulation flat part"),
        ("cgg_inv_ff", "Inversion flat part"),
    ):
        vals = [m[key] for m in metrics.values()]
        s = got[words]
        assert (s.typical, s.lowest, s.highest) == (metrics["typical"][key], min(vals), max(vals))
        assert [s.lowest, s.highest] == env["ngspice"]["nfet_05v0"][gid][key]
        assert s.lowest < s.typical < s.highest
    for check, key, words in (
        ("dv_dep", "u_dep", "Depletion crossing"),
        ("dv_inv", "u_inv", "Inversion crossing"),
    ):
        w = rec["verdicts"][check]["window"]
        s = got[words]
        assert (s.typical, s.lowest, s.highest) == (rec["spice_regions"][key], w["lo"], w["hi"])
        assert s.lowest < s.typical < s.highest
    rows = numbers.corner_table().splitlines()
    assert rows[0] == "| Quantity | Typical | Lowest | Highest | Spread |"
    for row, s in zip(rows[2:], numbers.corner_spread(), strict=True):
        cells = [c.strip() for c in row.strip("|").split("|")]
        spread = numbers.format_value(s.highest - s.lowest, numbers.SPREAD_DIGITS, s.unit)
        assert cells[0] == s.words and cells[-1] == spread


_CORNERS = {d: f"results/tcad/corners/{d}/summary.json" for d in _FITS}


def _corners(device: str, root: Path = ROOT) -> dict:
    return json.loads((root / _CORNERS[device]).read_text("utf-8"))


def _corners_copy(tmp_path: Path) -> Path:
    for path in _CORNERS.values():
        dst = tmp_path / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text((ROOT / path).read_text("utf-8"), "utf-8")
    return tmp_path


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip("|").split("|")]


def test_corner_bounds_table_is_the_summary():
    """Issue #121: each row of a bounds table is the corner summary's typical, lowest, highest
    and spread of that number; the typical is the committed calibration's fitted value."""
    numbers = _numbers()
    for device in _FITS:
        doc = _corners(device)
        rows = numbers.corner_bounds_table(device).splitlines()
        assert rows[0] == "| Number | Typical | Lowest | Highest | Spread |"
        assert len(rows) == 2 + len(numbers.TUNABLES)
        for row, name in zip(rows[2:], numbers.TUNABLES, strict=True):
            words, unit, most = numbers.TUNABLES[name]
            t = doc["tunables"][name]
            assert t["typical"] == _fit(device)["values"][name], (device, name)
            assert t["min"] <= t["typical"] <= t["max"], (device, name)
            assert t["spread"] == t["max"] - t["min"]
            want = [f"{words} ({unit})"] + [
                numbers.shortest(t[k], "", most) for k in ("typical", "min", "max", "spread")
            ]
            assert _cells(row) == want, (device, name)


def test_corner_bounds_follow_an_edited_summary(tmp_path):
    numbers = _numbers()
    root = _corners_copy(tmp_path)
    doc = _corners("nfet_05v0")
    t = doc["tunables"]["t_ox_eff_nm"]
    t["min"], t["min_corner"], t["min_at_bound"] = 15.0, "sf", "lower"
    t["spread"] = t["max"] - t["min"]
    (root / _CORNERS["nfet_05v0"]).write_text(json.dumps(doc), "utf-8")
    table = numbers.corner_bounds_table("nfet_05v0", root=root)
    assert table != numbers.corner_bounds_table("nfet_05v0")
    assert _cells(table.splitlines()[2])[2] == "15"  # the lowest oxide, on its limit
    rows = numbers.corner_extremes_table(root=root).splitlines()
    assert _cells(rows[2])[2] == "sf"
    assert "The lowest oxide thickness of the nfet_05v0, at sf, sits on its lower limit" in (
        numbers.corner_bound_hits(root=root)
    )
    with pytest.raises(KeyError):
        doc["device"] = "pfet_05v0"
        (root / _CORNERS["nfet_05v0"]).write_text(json.dumps(doc), "utf-8")
        numbers.corner_bounds("nfet_05v0", root=root)


def test_corner_extremes_and_hits_are_the_summaries():
    numbers = _numbers()
    rows = numbers.corner_extremes_table().splitlines()
    assert rows[0] == "| Transistor | Number | Lowest at | Highest at |"
    want = [
        [f"{{term}}`{d}`", numbers.TUNABLES[n][0], t["min_corner"], t["max_corner"]]
        for d in _FITS
        for n in numbers.TUNABLES
        for t in [_corners(d)["tunables"][n]]
    ]
    assert [_cells(r) for r in rows[2:]] == want
    hits = [
        (d, n, side)
        for d in _FITS
        for n, t in _corners(d)["tunables"].items()
        for side in ("min", "max")
        if t[f"{side}_at_bound"] is not None
    ]
    sentence = numbers.corner_bound_hits()
    assert (sentence == "No lowest or highest value sits on a limit of its fit") == (not hits)
    for d, n, side in hits:
        words = numbers.TUNABLES[n][0].lower()
        assert f"The {'lowest' if side == 'min' else 'highest'} {words} of the {d}" in sentence


def test_corner_bounds_figure_draws_the_summaries():
    from gf180tcad.explain import figures

    numbers = _numbers()
    for palette in figures.PALETTES:
        fig = figures.corner_bounds_figure(palette)
        assert len(fig.axes) == len(numbers.TUNABLES)
        for ax, name in zip(fig.axes, numbers.TUNABLES, strict=True):
            assert (ax.get_xscale() == "log") == (name in figures.LOG_TUNABLES)
            xs = [list(line.get_xdata()) for line in ax.get_lines()]
            for device in _FITS:
                t = _corners(device)["tunables"][name]
                assert [t["min"], t["max"]] in xs, (device, name)
                assert [t["typical"]] in xs, (device, name)
                for c in figures.STYLE["corner_markers"]:
                    assert [t["values"][c]] in xs, (device, name, c)
                left, right = ax.get_xlim()
                assert left < t["min"] and t["max"] < right, (palette, name)
    assert "corner-bounds" in figures.FIGURES
    light = figures.FIGURES["corner-bounds"]("light")
    assert light.startswith(b"<?xml") and light != figures.FIGURES["corner-bounds"]("dark")
    assert "x_fig_corner_bounds_scale" not in figures.substitutions()
    assert "/_generated/explained/corner-bounds-light.svg" in CALIBRATION_PAGE.read_text("utf-8")


LIMITS_CORNERS_PAGE = ROOT / "docs" / "limitations" / "corners.md"


def test_crosscheck_numbers_are_the_summaries():
    """The largest cross-check difference of each transistor and number is the summary's
    ``shift_difference`` of largest size, printed with its corner."""
    numbers = _numbers()
    subs = numbers.crosscheck_substitutions()
    for device in _FITS:
        short = device.split("_")[0]
        for name, (key, unit, digits, factor) in numbers.CROSSCHECK.items():
            diffs = _corners(device)["tunables"][name]["shift_difference"]
            corner = max(diffs, key=lambda c: abs(diffs[c]))
            t = _corners(device)["tunables"][name]
            assert diffs[corner] == t["tcad_shift"][corner] - t["card_shift"][corner]
            assert subs[f"x_crosscheck_{key}_corner_{short}"] == corner
            assert subs[f"x_crosscheck_{key}_gap_{short}"] == numbers.shortest(
                diffs[corner] * factor, unit, digits
            )


def test_corner_fit_limits_are_the_files():
    from gf180tcad.devices import CORNERS

    numbers = _numbers()
    for device, typical in _FITS.items():
        fits = {(f.corner, f.name): f for f in numbers.corner_fit_limits(device)}
        assert set(fits) == {(c, n) for c in CORNERS for n in numbers.TUNABLES}
        for c in CORNERS:
            path = typical if c == "typical" else f"results/tcad/corners/{device}/{c}.json"
            doc = json.loads((ROOT / path).read_text("utf-8"))
            for n in numbers.TUNABLES:
                f = fits[(c, n)]
                assert [f.lower, f.upper] == doc["bounds"][n] and f.fitted == doc["values"][n]
                assert f.at_bound == doc["bound_hits"].get(n)
    hits = numbers.corner_fit_hits()
    for device in _FITS:
        for f in numbers.corner_fit_limits(device):
            named = f"The {numbers.TUNABLES[f.name][0].lower()} of the {device} at {f.corner}"
            assert (named in hits) == (f.at_bound is not None), named


def test_corner_verdict_sentence_is_the_summaries():
    numbers = _numbers()
    sentence = numbers.corner_verdicts()
    for device in _FITS:
        verdicts = {
            c: e["verdict"] for c, e in _corners(device)["corners"].items() if c != "typical"
        }
        if len(set(verdicts.values())) == 1:
            (v,) = set(verdicts.values())
            assert f"the {{term}}`{device}` is {{term}}`{v}` at every corner" in sentence


def test_corner_crossing_gaps_back_the_limitations_page():
    """The page says the pfet's depletion crossing shift is positive at its shortest gate and
    negative at its longest at every corner, and the nfet's lines lie near zero: the nfet's
    largest gap is smaller than the pfet's swing at every corner."""
    numbers = _numbers()
    nfet = numbers.corner_crossing_gaps("nfet_05v0")
    pfet = numbers.corner_crossing_gaps("pfet_05v0")
    for corner, gaps in pfet.items():
        lengths = sorted(gaps)
        assert gaps[lengths[0]] > 0 > gaps[lengths[-1]], corner
        swing = gaps[lengths[0]] - gaps[lengths[-1]]
        assert max(abs(v) for v in nfet[corner].values()) < swing / 5, corner
    text = " ".join(LIMITS_CORNERS_PAGE.read_text("utf-8").split())
    assert (
        "At every corner the pfet's shift is positive at its shortest gate and negative at its "
        "longest." in text
    )


def test_corner_figures_are_registered_and_drawn():
    from gf180tcad.explain import figures

    numbers = _numbers()
    text = LIMITS_CORNERS_PAGE.read_text("utf-8")
    for name in ("corner-crosscheck", "corner-crossing", "corner-limits"):
        light = figures.FIGURES[name]("light")
        assert light.startswith(b"<?xml") and light != figures.FIGURES[name]("dark")
        assert f"x_fig_{name.replace('-', '_')}_scale" not in figures.substitutions()
        assert f"/_generated/explained/{name}-light.svg" in text
        assert f"/_generated/explained/{name}-dark.svg" in text
    fig = figures.corner_crosscheck_figure("light")
    xs = {(line.get_xdata()[0], line.get_ydata()[0]) for ax in fig.axes for line in ax.get_lines()
          if len(line.get_xdata()) == 1}  # fmt: skip
    for device in _FITS:
        for name, (_w, _u, factor) in figures.CROSSCHECK.items():
            t = _corners(device)["tunables"][name]
            for c in figures.STYLE["corner_markers"]:
                assert (t["card_shift"][c] * factor, t["tcad_shift"][c] * factor) in xs
    fig = figures.corner_limits_figure("light")
    for ax, name in zip(fig.axes, numbers.TUNABLES, strict=True):
        drawn = [list(line.get_xdata()) for line in ax.get_lines()]
        for device in _FITS:
            for f in numbers.corner_fit_limits(device):
                if f.name == name:
                    assert [f.lower, f.upper] in drawn and [f.fitted] in drawn


def test_calibration_counts_are_derived():
    numbers = _numbers()
    docs = {d: _fit(d) for d in _FITS}
    c = numbers.counts()
    assert {doc["budget"] for doc in docs.values()} == {c["budget"]}
    assert {doc["budget_used"] for doc in docs.values()} == {c["budget_used"]}
    assert c["budget_used"] == len(numbers.TUNABLES)
    assert c["nfev_nfet"] == docs["nfet_05v0"]["optimiser"]["nfev"]
    assert c["nfev_pfet"] == docs["pfet_05v0"]["optimiser"]["nfev"]


def test_calibration_figure_draws_the_result_files():
    from gf180tcad.explain import figures

    numbers = _numbers()
    for palette in figures.PALETTES:
        fig = figures.calibration_limits_figure(palette)
        assert len(fig.axes) == len(numbers.TUNABLES)
        for ax, name in zip(fig.axes, numbers.TUNABLES, strict=True):
            assert (ax.get_xscale() == "log") == (name in figures.LOG_TUNABLES)
            xs = [list(line.get_xdata()) for line in ax.get_lines()]
            for device in _FITS:
                doc = _fit(device)
                lo, hi = doc["bounds"][name]
                assert [lo, hi] in xs, (device, name)
                assert [doc["start"][name]] in xs and [doc["values"][name]] in xs, (device, name)
                left, right = ax.get_xlim()
                assert left < lo and hi < right, (palette, name)  # the limit marks are not clipped


def test_calibration_figure_is_registered():
    from gf180tcad.explain import figures

    assert "calibration-limits" in figures.FIGURES
    light = figures.FIGURES["calibration-limits"]("light")
    assert light.startswith(b"<?xml") and light != figures.FIGURES["calibration-limits"]("dark")
    assert "x_fig_calibration_limits_scale" not in figures.substitutions()


def test_calibration_page_prints_its_numbers():
    text = CALIBRATION_PAGE.read_text(encoding="utf-8")
    for key in ("fit_table_nfet", "fit_table_pfet", "limit_kinds_table", "bound_hits",
                "fit_verdict_table", "corner_table", "corner_count", "fit_length_count",
                "budget", "budget_used", "nfev_nfet", "nfev_pfet", "verdict_pfet_1d_term",
                "two_d_disagree", "corner_bounds_table_nfet", "corner_bounds_table_pfet",
                "corner_extremes_table", "corner_bound_hits"):  # fmt: skip
        assert "{{ x_" + key + " }}" in text, key
    assert "/_generated/explained/calibration-limits-light.svg" in text
    for anchor in ("cv-agreement-mismatch", "cv-agreement-validation", "cv-agreement-windows",
                   "process-data-tunables"):  # fmt: skip
        assert f"<{anchor}>`" in text or f"{{ref}}`{anchor}`" in text, anchor
    # the corner fits that give each fitted number its bounds, and their limitations page
    assert "{ref}`reproduce-corners`" in text and "{doc}`/limitations/corners`" in text
    assert "/_generated/explained/corner-bounds-light.svg" in text
    assert not _COUNT_WORDS.findall(text)


def test_two_d_cells_reuse_the_fit():
    """The page says the 2D cells reuse the 1D fit unchanged: the validation files' values are the
    calibration files' values."""
    for device in _FITS:
        cal = json.loads((ROOT / f"results/tcad/calibration/{device}.json").read_text("utf-8"))
        val = json.loads((_VALIDATION / f"{device}.json").read_text("utf-8"))
        assert val["values"] == cal["values"], device


def test_crossing_gap_is_weighed_by_the_allowed_gap():
    """The page says the fit weighs each crossing gap by the allowed gap: the scaled residuals
    are the gaps over the tolerance."""
    for device in _FITS:
        for gid, e in _fit(device)["per_geometry"].items():
            for check in ("dv_dep", "dv_inv"):
                v = e["verdicts"][check]
                scaled = e["residuals"][f"{check}_scaled"]
                assert math.isclose(scaled, v["dv_v"] / v["tolerance_v"]), (device, gid, check)


def test_cost_is_half_the_sum_of_the_squared_residuals():
    """The page's cost equation: the optimiser's cost is half the sum of the squares of every
    geometry's residuals (flat-part relative errors and crossing gaps over the tolerance)."""
    for device in _FITS:
        doc = _fit(device)
        res = []
        for e in doc["per_geometry"].values():
            r = e["residuals"]
            res += [
                *r["plateau_acc_rel"],
                *r["plateau_inv_rel"],
                r["dv_dep_scaled"],
                r["dv_inv_scaled"],
            ]
        assert len(res) == doc["optimiser"]["residuals"], device
        assert math.isclose(
            0.5 * math.fsum(x * x for x in res), doc["optimiser"]["cost"], rel_tol=1e-9
        )


def test_compare_figure_marks_what_the_fit_compares():
    """The flat parts the fit compares are shaded from the result file's residual voltages, and
    each curve's crossings are marked at the result file's voltages."""
    from gf180tcad.explain import figures

    rec = _fit("nfet_05v0")["per_geometry"][figures.REGIONS_GEOMETRY]
    acc, inv = rec["residuals"]["plateau_acc_u"], rec["residuals"]["plateau_inv_u"]
    for palette in figures.PALETTES:
        (ax,) = figures.calibration_compare_figure(palette).axes
        spans = sorted(
            (p.get_x(), p.get_x() + p.get_width()) for p in ax.patches if p.get_width() > 0
        )
        assert spans == [(min(acc), max(acc)), (min(inv), max(inv))]
        marks = {line.get_label(): list(line.get_xdata()) for line in ax.get_lines()}
        sp, tc = rec["spice_regions"], rec["tcad_crossings"]
        assert marks[figures.COMPARE_MARKS["spice"]] == [sp["u_dep"], sp["u_inv"]]
        assert marks[figures.COMPARE_MARKS["tcad"]] == [tc["u_dep"], tc["u_inv"]]


def test_pfet_figure_draws_the_shortest_and_longest_fit_gates():
    """One panel per end of the pfet's fit lengths, on the true gate voltage (−u for the pfet),
    the SPICE typical and the fitted curves read by the shared readers."""
    from gf180tcad.devices import DEVICES
    from gf180tcad.explain import figures

    pol = DEVICES["pfet_05v0"].polarity
    fit = _fit("pfet_05v0")["per_geometry"]
    by_l = sorted(fit, key=lambda g: fit[g]["geometry"]["l_um"])
    assert figures.pfet_geometries() == (by_l[0], by_l[-1])
    for palette in figures.PALETTES:
        axes = figures.calibration_pfet_figure(palette).axes
        assert len(axes) == len(figures.pfet_geometries())
        for ax, gid in zip(axes, figures.pfet_geometries(), strict=True):
            c = figures.cv_curves("pfet_05v0", "calibrated", gid)
            xs = [list(line.get_xdata()) for line in ax.get_lines()]
            assert list(pol * c["u_spice"]) in xs and list(pol * c["u"]) in xs, gid
            assert ax.get_xlabel() == "gate voltage (V)"


def test_calibration_figures_are_registered():
    from gf180tcad.explain import figures

    for name in ("calibration-compare", "calibration-pfet"):
        assert name in figures.FIGURES, name
        light = figures.FIGURES[name]("light")
        assert light.startswith(b"<?xml") and light != figures.FIGURES[name]("dark")
        assert f"x_fig_{name.replace('-', '_')}_scale" not in figures.substitutions()
        assert f"/_generated/explained/{name}-light.svg" in CALIBRATION_PAGE.read_text("utf-8")


def test_calibration_page_numbers_its_figures():
    """Owner rule (2026-11-03): each figure has a name and the text refers to it by number."""
    text = CALIBRATION_PAGE.read_text("utf-8")
    names = re.findall(r"^:name: (fig-[\w-]+)$", text, re.MULTILINE)
    assert len(names) == text.count(":figclass: only-light") and len(set(names)) == len(names)
    for name in names:
        assert f"{{numref}}`{name}`" in text or f"<{name}>`" in text, name


def test_calibration_stack_highlights_the_fitted_layers(monkeypatch):
    """The opening drawing highlights the oxide and the body, the two layers the fit changes."""
    from gf180tcad.explain import figures

    seen = []
    real = figures.stack_1d
    monkeypatch.setattr(
        figures, "stack_1d", lambda dev, hl, pal: seen.append((dev, hl)) or real(dev, hl, pal)
    )
    assert figures.FIGURES["calibration-stack"]("light").startswith(b"<?xml")
    ((dev, hl),) = seen
    assert set(hl) == {"oxide", "body"} and dev.name == "nfet_05v0"
    assert "x_fig_calibration_stack_scale" in figures.substitutions()


# --- the SPICE model's quasi-static switches (cv-curve.md) -----------------------------------

MODEL_CARD = ROOT / "data" / "explain" / "model_card.toml"


def test_model_card_file_names_the_process_files_card():
    """data/explain/model_card.toml reads the card that data/process/nfet_05v0.toml names (same
    file and sha256), with the process file's model among its bins, and every bin holds the
    values the registry prints. tests/tcad/test_process.py ties the bins to the card's length
    bins and, in the sandbox, checks each line in the card."""
    numbers = _numbers()
    card = tomllib.loads(MODEL_CARD.read_text(encoding="utf-8"))
    proc = tomllib.loads((ROOT / "data/process/nfet_05v0.toml").read_text(encoding="utf-8"))
    assert card["card"] == {k: proc["card"][k] for k in ("file", "sha256")}
    bins = card["nfet_05v0"]
    assert bins[proc["card"]["model"]]["model_line"] == proc["card"]["model_line"]
    assert len(bins) == 2
    for key in ("acnqsmod", "trnqsmod"):
        n = numbers.REGISTRY[f"{key}_nfet"]
        assert (n.kind, n.source) == ("committed", numbers.MODEL_CARD)
        for model, b in bins.items():
            assert numbers.value(n.name) == b[key]["value"], (model, key)
            assert b[key]["card_line"] > b["model_line"], (model, key)


def test_cv_page_says_quasi_static_only_when_both_switches_are_off():
    """The page calls the SPICE capacitance quasi-static because both selectors are 0, which
    turns BSIM4's non-quasi-static model off (manual section 8.1, appendix A)."""
    numbers = _numbers()
    text = CV_PAGE.read_text(encoding="utf-8")
    assert "{{ x_acnqsmod_nfet }}" in text and "{{ x_trnqsmod_nfet }}" in text
    assert (
        "<lit-bsim4>" in text and "{repo}`model_card.toml <data/explain/model_card.toml>`" in text
    )
    assert "SPICE capacitance is\nquasi-static" in text
    assert numbers.value("acnqsmod_nfet") == 0 and numbers.value("trnqsmod_nfet") == 0
