# SPDX-License-Identifier: Apache-2.0
"""The documentation writing rules of spec §10.3: tables hold data, present state only, short
glossary definitions, every term defined. The checks themselves are in tests/doc_style.py."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from doc_style import (
    HEDGE_EXEMPT,
    MAX_WORDS,
    ROOT,
    check_cell,
    hedge_lines,
    history_allowed,
    history_lines,
    numbers,
    source_pages,
    tables,
    words,
)
from optional import importorskip

GLOSSARY = ROOT / "docs" / "glossary.md"
DOCGEN = ROOT / "src" / "gf180tcad" / "docgen.py"

# A glossary entry is at most this many words (the writing-sourced-docs cap, spec §10.3).
GLOSSARY_WORDS = 80

_TERM = re.compile(r"\{term\}`([^`]*)`")


# Pages are brought under these rules by the later commits of PR #62, which remove this marker.
_PENDING = pytest.mark.xfail(reason="pages fixed later in PR #62", strict=False)


def _table_problems(text: str, rel: str) -> list[str]:
    out = []
    for t in tables(text, rel):
        if t.opt_out:
            continue
        for p in t.problems:
            out.append(f"{rel}:{p.row} column {p.column!r}: {p.reason}: {p.cell[:80]}")
    return out


@pytest.fixture(scope="module")
def generated(tmp_path_factory) -> Path:
    importorskip("matplotlib", reason="needs the docs dependency group")
    from gf180tcad import docgen

    out = tmp_path_factory.mktemp("generated")
    docgen.generate(out)
    return out


@_PENDING
def test_table_cells():
    """Every table in the Markdown sources: one value per cell, no sentences (spec §10.3)."""
    problems = []
    for p in source_pages():
        rel = p.relative_to(ROOT).as_posix()
        problems += _table_problems(p.read_text(encoding="utf-8"), rel)
    assert not problems, "tables that hold prose or several numbers in a cell:\n" + "\n".join(
        problems
    )


@_PENDING
def test_generated_table_cells(generated):
    """The same rule for the pages docgen writes at build time."""
    problems = []
    for p in sorted(generated.rglob("*.md")):
        rel = "docs/_generated/" + p.relative_to(generated).as_posix()
        problems += _table_problems(p.read_text(encoding="utf-8"), rel)
    assert not problems, "\n".join(problems)


def test_table_opt_outs_give_a_reason():
    for p in source_pages():
        for t in tables(p.read_text(encoding="utf-8"), str(p)):
            if t.opt_out:
                reason = t.opt_out.split(":", 1)[1].removesuffix("-->").strip()
                assert len(reason.split()) >= 3, f"{p}:{t.line}: opt-out without a reason"


def test_no_history_phrases():
    """Pages outside the change log, plans, reproduction record and plugin history state the
    present, not what used to be true (spec §10.3)."""
    found = []
    for p in source_pages():
        rel = p.relative_to(ROOT).as_posix()
        if history_allowed(rel):
            continue
        found += [f"{rel}:{n}: {line[:100]}" for n, line in history_lines(p.read_text("utf-8"))]
    assert not found, "history narration (or add <!-- history-ok: reason -->):\n" + "\n".join(found)


def _glossary_entries() -> list[tuple[tuple[str, ...], str]]:
    """(term names, definition text) of each entry of docs/glossary.md."""
    text = GLOSSARY.read_text(encoding="utf-8")
    m = re.search(r"^```\{glossary\}\n(.*?)^```", text, re.DOTALL | re.MULTILINE)
    assert m, "docs/glossary.md has no {glossary} block"
    entries: list[tuple[list[str], list[str]]] = []
    for line in m.group(1).splitlines():
        if line.startswith(":"):
            continue
        if line and not line[0].isspace():
            if not entries or entries[-1][1]:
                entries.append(([], []))
            entries[-1][0].append(line.strip())
        elif entries:
            entries[-1][1].append(line.strip())
    return [(tuple(n), " ".join(d).strip()) for n, d in entries]


def test_glossary_definitions_short():
    long = []
    for names, definition in _glossary_entries():
        n = words(definition)
        if n > GLOSSARY_WORDS:
            long.append(f"{names[0]}: {n} words")
    assert not long, f"glossary definitions over {GLOSSARY_WORDS} plain words: {long}"


def _term_target(role_text: str) -> str:
    m = re.match(r"^(.*?)\s*<([^<>]+)>$", role_text, re.DOTALL)
    return (m.group(2) if m else role_text).strip()


def _defined_terms() -> set[str]:
    return {n.lower() for names, _ in _glossary_entries() for n in names}


def test_every_term_is_defined():
    """Every {term} role in the docs sources and in docgen names a glossary entry; the same
    check as Sphinx's, without a build."""
    defined = _defined_terms()
    sources = [p for p in source_pages() if p.name != "README.md"] + [DOCGEN]
    missing = []
    for p in sources:
        text = p.read_text(encoding="utf-8")
        for m in _TERM.finditer(text):
            target = _term_target(m.group(1)).replace("{{", "{").replace("}}", "}")
            if "{" in target:  # an f-string placeholder in docgen, e.g. {name}
                continue
            if target.lower() not in defined:
                missing.append(f"{p.relative_to(ROOT)}: {target!r}")
    assert not missing, "terms with no glossary entry:\n" + "\n".join(sorted(set(missing)))


def test_generated_terms_are_defined(generated):
    defined = _defined_terms()
    missing = set()
    for p in generated.rglob("*.md"):
        for m in _TERM.finditer(p.read_text(encoding="utf-8")):
            if _term_target(m.group(1)).lower() not in defined:
                missing.add(_term_target(m.group(1)))
    assert not missing, sorted(missing)


# --- positive controls: each detector fires ---------------------------------------------------


@pytest.mark.parametrize(
    "cell",
    [
        "≤ 10 mV (stretch 7 mV)",
        "10/0.6",
        "[0.58, 0.82]",
        " ".join(["word"] * 26),
        "15.2 nm ([37309](https://example.org/x#L37309))",
    ],
)
def test_positive_control_bad_cells(cell):
    assert check_cell(cell) is not None


@pytest.mark.parametrize(
    "cell",
    [
        "0.85",
        "2.63e-05",
        "1.7e+17",
        "{term}`nfet_05v0`",
        "{doc}`w10p0_l0p60 <nfet_05v0/w10p0_l0p60>`",
        "`t_ox_eff_nm`",
        "corner envelope",
        "+308.6",
        "Same process",
        "2026-10-27 11:31",
    ],
)
def test_positive_control_good_cells(cell):
    assert check_cell(cell) is None


def test_positive_control_counts():
    assert numbers("[6.297e+16, 3.4e+17]") == ["6.297e+16", "3.4e+17"]
    assert numbers("cm^-3") == []
    assert words(" ".join(["w"] * MAX_WORDS)) == MAX_WORDS


def test_positive_control_table_and_opt_out():
    bad = "| A | B |\n|---|---|\n| 1 | 2 / 3 |\n"
    assert tables(bad, "x")[0].problems
    ok = "<!-- table-ok: a matrix of two numbers per cell, by design -->\n" + bad
    t = tables(ok, "x")[0]
    assert t.opt_out and t.problems
    fenced = "```text\n" + bad + "```\n"
    assert tables(fenced, "x") == []


def test_positive_control_history():
    assert history_lines("The 2D files were previously restamped.\n")
    assert not history_lines("The run is resumed. <!-- history-ok: needed here -->\n")
    assert not history_lines("```\npreviously\n```\n")


@_PENDING
def test_no_hedge_words():
    """Reader pages carry no hedge or unknown words (spec §10.3, owner decision of 14:40)."""
    found = []
    for p in source_pages():
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(HEDGE_EXEMPT):
            continue
        found += [f"{rel}:{n}: {w!r}" for n, w in hedge_lines(p.read_text(encoding="utf-8"))]
    assert not found, "hedge words on reader pages:\n" + "\n".join(found)


@_PENDING
def test_generated_pages_have_no_hedge_words(generated):
    found = []
    for p in sorted(generated.rglob("*.md")):
        found += [f"{p.name}:{n}: {w!r}" for n, w in hedge_lines(p.read_text(encoding="utf-8"))]
    assert not found, "\n".join(found)


@pytest.mark.parametrize(
    "line",
    ["The cause is probably the oxide.", "It takes about 10 min.", "This is not yet run.",
     "The value is not public.", "a plausible process description"],
)  # fmt: skip
def test_positive_control_hedges(line):
    assert hedge_lines(line)


@pytest.mark.parametrize(
    "line",
    ["What to note about them.", "The `unverified` tag.", 'The words "not yet" are banned.',
     "The cause: the oxide, shown by the 1D fit.", "(metrics-not-yet-extracted)=",
     "See {ref}`the list <metrics-not-yet-extracted>`."],
)  # fmt: skip
def test_positive_control_not_hedges(line):
    assert not hedge_lines(line)
