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
        (8.813323306821749e16, 3, "cm⁻³", "8.81 × 10¹⁶ cm⁻³"),
        (1e20, 2, "cm⁻³", "1.0 × 10²⁰ cm⁻³"),
        (8265841554.853887, 3, "cm⁻³", "8.27 × 10⁹ cm⁻³"),
        (298.15, 5, "K", "298.15 K"),
        (775.2, 3, "cm⁻³", "775 cm⁻³"),
        (0.0371, 2, "V", "0.037 V"),
        (-0.25, 2, "V", "−0.25 V"),
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

    assert set(idealised.FORMULAS) == {"boltzmann_fermi", "degenerate_offset", "mass_action"}
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


def test_explained_pages_meet_every_cap():
    files = [str(p) for p in pages()]
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
    assert not found, "\n".join(found)


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
        if ln.strip() and not ln.startswith(("# ", "- ", "(")) and not ln.startswith("  ")
    ]  # fmt: skip
    assert len(prose) <= 2, f"a landing page is one line per destination: {prose}"


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
    for (_l, _a, b), (_m, c, _d) in zip(drawn, drawn[1:], strict=False):
        assert b == pytest.approx(c)
    assert "oxide-stack" in figures.FIGURES
    light = figures.FIGURES["oxide-stack"]("light")
    assert light.startswith(b"<?xml") and light != figures.FIGURES["oxide-stack"]("dark")


def test_oxide_page_prints_its_numbers():
    text = OXIDE_PAGE.read_text(encoding="utf-8")
    for key in ("toxe_nfet", "toxp_nfet", "t_ox_nfet_cal", "cox_nfet_cal", "cox_check_nfet"):
        assert "{{ x_" + key + " }}" in text, key
    assert "/_generated/explained/oxide-stack-light.svg" in text
