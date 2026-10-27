#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Vendored unchanged (below this header) from the user's mithro/dot-claude repository,
# marketplace/writing-sourced-docs/skills/writing-sourced-documentation/scripts/measure_docs.py.
# Unpublished at the time of vendoring: local commit 30b9fbac55f7fe2b8ba82fcead649c26b6a95e94 of
# that repository (Apache-2.0); obtainable from it once pushed.
# (sha256 26ea5586ed154e2cad84c12ffd55a541979248c157c707ab2d32172f13471012 of the original file).
# Copyright Tim Ansell; licensed under the Apache License 2.0, as the rest of this repository.
# Update by copying the new upstream file below this header and changing the commit and sha256.
"""Measure Markdown documentation against the sourced-documentation caps, check
footnote integrity, and diff a page before and after a presentation edit.

    uv run python measure_docs.py PATH...                 # caps + footnote report
    uv run python measure_docs.py --preserve BEFORE AFTER # what a rewrite lost or gained
    uv run python measure_docs.py --selftest              # offline unit checks

Caps (words; a quotation or a code span counts as one word; footnote markers and
MyST role wrappers are ignored):

    paragraph 100 · list item 60 · sentence 45 · table cell 25 · first sentence 25

The footnote report lists markers with no definition, definitions never referenced,
inline http(s) links whose URL is not in one of the page's own footnote definitions,
and sentences that carry a unit-bearing number but no marker and no "typical" label
(candidates only: a reader must judge them).

``--preserve`` compares the multisets of footnote markers, numeric tokens, quoted
strings, hedge words, URLs and cross-reference roles between two files, and prints
every content word lost or gained. A LOST line is a fact, number, quotation, hedge or
citation that the rewrite dropped; an ADDED line is one it invented. The check is
necessary, not sufficient: it cannot see a marker that merely moved to a neighbouring
sentence. Read the diff as well.

Standard library only. Exit status is 1 when a cap is exceeded, a footnote is
unbalanced, or a preservation category lost or gained an item.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

CAPS = {"paragraph": 100, "item": 60, "sentence": 45, "cell": 25, "first_sentence": 25}

HEDGES = [
    "we infer", "inference", "our reading", "this reference's reading", "on this page's reading",
    "our arithmetic", "our extraction", "our estimate", "not public", "not stated", "not published",
    "industry-typical", "era-typical", "typical", "typically", "about", "approximately", "roughly",
    "likely", "single source", "(single source)",
]

MARKER_RE = re.compile(r"\[\^([A-Za-z0-9_.-]+)\]")
DEF_RE = re.compile(r"^\[\^([A-Za-z0-9_.-]+)\]:", re.M)
ROLE_RE = re.compile(r"\{(ref|term|doc|math|numref)\}`([^`]*)`")
CODE_RE = re.compile(r"`[^`\n]+`")
QUOTE_RE = re.compile(r"\"([^\"\n]{1,800}?)\"|“([^”\n]{1,800}?)”")
URL_RE = re.compile(r"https?://[^\s<>\]\"]+")  # a DOI may contain parentheses: 10.1016/0168-583X(91)95283-J
# angle-bracket form first, so a URL containing parentheses (a DOI) is read to its closing ">"
INLINE_LINK_RE = re.compile(r"\[[^\]]*\]\((?:<(https?://[^>\s]+)>|(https?://[^)\s]+))\)")
NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_])[+\-−~≈]?\d[\d,.]*(?:\s?[×x]\s?10[⁰¹²³⁴⁵⁶⁷⁸⁹⁻\-\d]+|e[+\-]?\d+)?(?![A-Za-z0-9_])"
)
UNIT_RE = re.compile(
    r"\d\s?(?:nm|µm|um|Å|mm|cm|m|keV|eV|MeV|V|A|mA|W|kW|°C|K|s|ms|min|h|Torr|mTorr|Pa|sccm|cm⁻²|cm⁻³|%|wph|MHz|kHz|Ω|mΩ)\b"
)
IDENT_RE = re.compile(r"\b[A-Z][A-Z0-9]*\d[A-Z0-9]*\b")  # SKY130, S8, MM4, 1X-style codes


def clean(text: str) -> str:
    """Strip markers, collapse roles and code/quotes to one token each."""
    text = MARKER_RE.sub("", text)
    text = ROLE_RE.sub(lambda m: m.group(2).split("<")[0].strip() or "ROLE", text)
    text = CODE_RE.sub("CODESPAN", text)
    text = QUOTE_RE.sub("QUOTATION", text)
    text = re.sub(r"\s[—–-]\s", " ", text)
    return text


def words(text: str) -> int:
    return len([w for w in clean(text).split() if re.search(r"[A-Za-z0-9]", w)])


def sentences(text: str) -> list[str]:
    text = clean(text)
    parts = re.split(r"(?<=[.!?])[\"'”’)\]]*\s+(?=[A-Z0-9“\"(])", text)
    return [p.strip() for p in parts if p.strip()]


def blocks(text: str):
    """Yield (kind, line_no, text) for prose paragraphs, list items and table cells,
    skipping footnote definitions, fences, directives, headings and generated blocks."""
    lines = text.split("\n")
    i, n = 0, len(lines)
    in_fence = None
    in_generated = False
    in_defs = False
    buf: list[str] = []
    buf_kind = None
    buf_start = 0

    def flush():
        nonlocal buf, buf_kind
        if buf and buf_kind:
            yield_value = (buf_kind, buf_start, " ".join(s.strip() for s in buf))
            buf, buf_kind = [], None
            return yield_value
        buf, buf_kind = [], None
        return None

    while i < n:
        line = lines[i]
        stripped = line.strip()
        if re.match(r"^(:::+|```+|~~~+)", stripped):
            fence = re.match(r"^(:::+|```+|~~~+)", stripped).group(1)
            if in_fence is None:
                in_fence = fence[0]
                out = flush()
                if out:
                    yield out
            elif stripped.startswith(in_fence):
                in_fence = None
            i += 1
            continue
        if in_fence:
            i += 1
            continue
        if "<!--" in stripped and ":begin" in stripped:
            in_generated = True
        if in_generated:
            if ":end" in stripped:
                in_generated = False
            i += 1
            continue
        if DEF_RE.match(line) or stripped == "<!-- footnotes -->":
            in_defs = True
        if in_defs:
            i += 1
            continue
        if not stripped or stripped.startswith("#") or re.match(r"^\(.*\)=$", stripped) or stripped.startswith(":"):
            out = flush()
            if out:
                yield out
            i += 1
            continue
        if stripped.startswith("|"):
            out = flush()
            if out:
                yield out
            if not re.match(r"^\|?\s*:?-{2,}", stripped):
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                for c in cells:
                    if c:
                        yield ("cell", i + 1, c)
            i += 1
            continue
        if re.match(r"^\s*([*+-]|\d+\.)\s", line):
            out = flush()
            if out:
                yield out
            buf_kind, buf_start = "item", i + 1
            buf = [re.sub(r"^\s*([*+-]|\d+\.)\s", "", line)]
            i += 1
            # continuation lines of the item: indented, non-blank, not a new item
            while i < n and lines[i].strip() and lines[i].startswith(" ") and not re.match(r"^\s*([*+-]|\d+\.)\s", lines[i]) and not lines[i].strip().startswith("|") and not re.match(r"^\s*(:::|```)", lines[i]):
                buf.append(lines[i])
                i += 1
            out = flush()
            if out:
                yield out
            continue
        if buf_kind is None:
            buf_kind, buf_start = "paragraph", i + 1
        buf.append(line)
        i += 1
    out = flush()
    if out:
        yield out


def caps_report(path: Path, text: str) -> list[str]:
    problems = []
    first_done = False
    for kind, line, body in blocks(text):
        w = words(body)
        cap_kind = kind
        if w > CAPS[cap_kind]:
            problems.append(f"{path}:{line}: {kind} {w} words (cap {CAPS[cap_kind]})")
        if kind in ("paragraph", "item"):
            for s in sentences(body):
                sw = len([x for x in s.split() if re.search(r"[A-Za-z0-9]", x)])
                if sw > CAPS["sentence"]:
                    problems.append(f"{path}:{line}: sentence {sw} words (cap {CAPS['sentence']}): {s[:70]}…")
        if kind == "paragraph" and not first_done:
            first_done = True
            ss = sentences(body)
            if ss:
                sw = len(ss[0].split())
                if sw > CAPS["first_sentence"]:
                    problems.append(f"{path}:{line}: first sentence {sw} words (cap {CAPS['first_sentence']})")
    return problems


def footnote_report(path: Path, text: str) -> list[str]:
    problems = []
    defs = Counter(DEF_RE.findall(text))
    body = DEF_RE.split(text)[0] if DEF_RE.search(text) else text
    # markers anywhere except on definition lines
    marker_lines = [l for l in text.split("\n") if not DEF_RE.match(l)]
    refs = Counter(MARKER_RE.findall("\n".join(marker_lines)))
    for label in sorted(refs.keys() - defs.keys()):
        problems.append(f"{path}: marker [^{label}] has no definition")
    for label in sorted(defs.keys() - refs.keys()):
        problems.append(f"{path}: definition [^{label}] is never referenced")
    for label, c in defs.items():
        if c > 1:
            problems.append(f"{path}: definition [^{label}] defined {c} times")
    if re.search(r"^\[[^\^\]]+\]:\s*\S", text, re.M):
        problems.append(f"{path}: reference-style link definition present ([text]: url)")
    def_text = text[len(body):] if DEF_RE.search(text) else ""
    def_urls = set(URL_RE.findall(def_text))
    for a, b in INLINE_LINK_RE.findall(body):
        url = a or b
        if url not in def_urls:
            problems.append(f"{path}: inline URL not in any footnote definition: {url}")
    # uncited numbers (candidates)
    for kind, line, blk in blocks(text):
        if kind == "cell":
            continue
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", blk):
            if UNIT_RE.search(s) and not MARKER_RE.search(s) and not re.search(r"typical|our arithmetic|our reading|derived above|\(inference", s, re.I):
                problems.append(f"{path}:{line}: number with no marker or 'typical' label (check): {clean(s)[:80]}…")
    return problems


def extract(text: str) -> dict[str, Counter]:
    body_lines = [l for l in text.split("\n") if not DEF_RE.match(l)]
    body = "\n".join(body_lines)
    flat = re.sub(r"\s+", " ", body)
    urls = Counter(u.rstrip(").,") for u in URL_RE.findall(text))
    # URLs are their own category; digits inside them (a DOI, an ISBN) are not page numbers
    flat = URL_RE.sub(" ", flat)
    masked = IDENT_RE.sub(" ", MARKER_RE.sub(" ", flat))
    masked = re.sub(r"(?m)^\s*\d+\.\s", " ", masked)
    # a trailing comma or full stop belongs to the sentence, not the number ("500, 275" → "500")
    nums = Counter(n.rstrip(",.") for n in NUMBER_RE.findall(masked))
    quotes = Counter(q[0] or q[1] for q in QUOTE_RE.findall(flat))
    hedges = Counter()
    low = flat.lower()
    for h in HEDGES:
        c = len(re.findall(r"(?<![a-z])" + re.escape(h) + r"(?![a-z])", low))
        if c:
            hedges[h] = c
    roles = Counter(f"{{{r}}}{t}" for r, t in ROLE_RE.findall(flat))
    markers = Counter(MARKER_RE.findall(body))
    defs = Counter(DEF_RE.findall(text))
    prose = QUOTE_RE.sub(" ", CODE_RE.sub(" ", MARKER_RE.sub(" ", ROLE_RE.sub(lambda m: m.group(2), flat))))
    wordset = Counter(w.lower().strip("*_()[],.;:\"'“”") for w in prose.split() if re.search(r"[A-Za-z]", w))
    return {"markers": markers, "definitions": defs, "numbers": nums, "quotes": quotes,
            "hedges": hedges, "roles": roles, "urls": urls, "words": wordset}


STOPWORDS = set("the a an of to in on and or is are was were be been it its this that these those as at by for from with which who whom whose but so than then there their they them we our you your he she his her not no nor if when where while into onto over under up down out off also both each either any all some such only own same more most very can may might must shall should will would do does did done has have had having here".split())


def preserve_report(before: Path, after: Path) -> list[str]:
    a = extract(before.read_text(encoding="utf-8"))
    b = extract(after.read_text(encoding="utf-8"))
    problems, info = [], []
    for cat in ("markers", "definitions", "numbers", "quotes", "hedges", "roles", "urls"):
        lost = a[cat] - b[cat]
        added = b[cat] - a[cat]
        for k, c in sorted(lost.items()):
            problems.append(f"LOST {cat} ({c}x): {k}")
        for k, c in sorted(added.items()):
            problems.append(f"ADDED {cat} ({c}x): {k}")
    lostw = {w: c for w, c in (a["words"] - b["words"]).items() if w not in STOPWORDS}
    addw = {w: c for w, c in (b["words"] - a["words"]).items() if w not in STOPWORDS}
    if lostw:
        info.append("WORDS LOST: " + ", ".join(f"{w}×{c}" if c > 1 else w for w, c in sorted(lostw.items())))
    if addw:
        info.append("WORDS ADDED: " + ", ".join(f"{w}×{c}" if c > 1 else w for w, c in sorted(addw.items())))
    return problems + info


def selftest() -> int:
    base = (
        "# T\n\nThe oxide is about 10 nm thick.[^a] \"Quoted words\" stay.[^b] We infer the rest.\n\n"
        "* **Item.** Value 2.0 × 10¹³ cm⁻² here.[^a]\n\n| A | B |\n|---|---|\n| 1 | two |\n\n"
        "<!-- footnotes -->\n\n[^a]: Source A. <https://example.org/a>\n[^b]: Source B. <https://example.org/b>\n"
    )
    assert words("\"a b c d\" and `x y` z") == 4, words("\"a b c d\" and `x y` z")
    ex = extract(base)
    assert ex["markers"]["a"] == 2 and ex["numbers"]["10"] == 1 and ex["quotes"]["Quoted words"] == 1
    assert extract("Energies of 500, 275 and 130 keV.")["numbers"] == Counter({"500": 1, "275": 1, "130": 1})
    assert ex["hedges"]["we infer"] == 1 and ex["hedges"]["about"] == 1
    changed = base.replace("[^b] We", " We").replace("about 10 nm", "10 nm").replace("We infer the rest.", "The rest follows.")
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p1, p2 = Path(d, "b.md"), Path(d, "a.md")
        p1.write_text(base); p2.write_text(changed)
        rep = preserve_report(p1, p2)
    assert any("LOST hedges" in r and "about" in r for r in rep), rep
    assert any("LOST hedges" in r and "we infer" in r for r in rep), rep
    assert any("LOST markers" in r and r.endswith("b") for r in rep), rep
    long = "x " * 101
    caps = caps_report(Path("t.md"), f"# T\n\n{long}\n")
    assert any("paragraph 101 words" in c for c in caps), caps
    fn = footnote_report(Path("t.md"), "# T\n\nA claim.[^z] See [x](<https://e.org/q>).\n\n[^y]: Y. <https://e.org/y>\n")
    assert any("no definition" in f for f in fn) and any("never referenced" in f for f in fn) and any("inline URL" in f for f in fn), fn
    doi = "# T\n\nSee [Tsukamoto 1991](<https://doi.org/10.1016/0168-583X(91)95283-J>).[^t]\n\n[^t]: T. <https://doi.org/10.1016/0168-583X(91)95283-J>\n"
    assert not [f for f in footnote_report(Path("t.md"), doi) if "inline URL" in f], footnote_report(Path("t.md"), doi)
    kinds = [k for k, _, _ in blocks(base)]
    assert kinds == ["paragraph", "item", "cell", "cell", "cell", "cell"], kinds
    print("selftest OK")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="Markdown files or directories")
    ap.add_argument("--preserve", nargs=2, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--no-numbers", action="store_true", help="skip the uncited-number candidates")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.preserve:
        rep = preserve_report(Path(args.preserve[0]), Path(args.preserve[1]))
        if not rep:
            print("identical in every category")
            return 0
        print("\n".join(rep))
        return 1 if any(r.startswith(("LOST", "ADDED")) for r in rep) else 0
    files: list[Path] = []
    for p in args.paths:
        pp = Path(p)
        files += sorted(pp.rglob("*.md")) if pp.is_dir() else [pp]
    if not files:
        ap.error("give at least one path, --preserve or --selftest")
    status = 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        probs = caps_report(f, text) + [p for p in footnote_report(f, text) if not (args.no_numbers and "(check)" in p)]
        for p in probs:
            print(p)
            if "(check)" not in p:
                status = 1
    print(f"{len(files)} file(s) measured")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
