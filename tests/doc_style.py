"""Checks of the documentation writing rules of spec §10.3 (used by tests/test_doc_style.py).

- Tables hold data: one value per cell, no sentences, no cells with two or more numbers.
- Present state only: no narrative history phrases outside the change log, plans, the
  reproduction record and the plugin-history page.

Run ``uv run --locked python tests/doc_style.py [paths...]`` for an inventory of every table
(file:line, columns, offending cells) in the given Markdown files (default: the docs sources).

Opt-outs, each with a reason that a reviewer reads:
- a table: an HTML comment ``<!-- table-ok: <reason> -->`` on one of the three lines above it;
- a line with a history phrase: ``<!-- history-ok: <reason> -->`` on the same line.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# A cell holds at most this many words (after markup is reduced to its visible text): the
# table-cell cap of the writing-sourced-docs skill (spec §10.3).
MAX_WORDS = 25
# Columns (writing-sourced-docs: no sideways scroll at 400 px): at most 5 when every cell is a
# number, code or at most 3 words; at most 3 when any cell holds more.
MAX_COLUMNS = 5
MAX_COLUMNS_PROSE = 3
SHORT_WORDS = 3

# Pages that may narrate what used to be true (spec §10.3).
HISTORY_ALLOWED = (
    "docs/superpowers/",
    "docs/reproduce/",
    "docs/limitations/plugin-history.md",
    "docs/api/",
)

HISTORY_PHRASES = re.compile(
    r"\b(previously|no longer|used to be|before PR|until PR|was changed|initially|predates?|backfilled|"
    r"were changed|formerly|in the past|at the time of writing|originally)\b",
    re.IGNORECASE,
)

_TABLE_OK = re.compile(r"<!--\s*table-ok:\s*\S.*-->")
_HISTORY_OK = re.compile(r"<!--\s*history-ok:\s*\S.*-->")
_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")

# A number: digits with optional thousands separators and decimals, optional exponent. A cell's
# visible text is split into tokens at spaces and separators (including "/", so "10/0.6" is two
# numbers); a token counts when it is a whole number after a leading sign and a trailing "%".
_NUMBER = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][−+-]?\d+)?")
_TOKEN_SPLIT = re.compile(r"[\s;()\[\]/=<>≤≥:|]+")


def visible_text(cell: str) -> str:
    """The text a reader sees in a Markdown/MyST table cell, with code spans as one token."""
    s = cell.replace("\\|", "|")
    # {role}`text <target>` -> text ; {role}`target` -> target
    s = re.sub(r"\{[\w:.-]+\}`([^`<]*?)\s*<[^`>]*>`", r"\1", s)
    s = re.sub(r"\{[\w:.-]+\}`([^`]*)`", r"\1", s)
    # [text](url) -> text
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    # {{ substitution }} -> one word
    s = re.sub(r"\{\{\s*(\w+)\s*\}\}", r"\1", s)
    # `code` -> CODE (one token, its digits do not count as numbers)
    s = re.sub(r"`[^`]*`", "CODE", s)
    s = re.sub(r"[*_]{1,2}", "", s)
    return s.strip()


def words(cell: str) -> int:
    return len([w for w in re.split(r"\s+", visible_text(cell)) if re.search(r"\w", w)])


def numbers(cell: str) -> list[str]:
    """The numbers in a cell's visible text (code spans, role targets and URLs excluded)."""
    out = []
    # A date or a date and time (2026-10-27 11:31) is one value.
    text = re.sub(
        r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?\b", "DATE", visible_text(cell)
    )
    text = re.sub(r"\b\d{1,2}:\d{2}\b", "TIME", text)
    for tok in _TOKEN_SPLIT.split(text):
        tok = tok.strip(",.").lstrip("−+-±~≈×").rstrip("%")
        if tok and _NUMBER.fullmatch(tok):
            out.append(tok)
    return out


def split_row(line: str) -> list[str]:
    s = line.strip()
    s = s.removeprefix("|")
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur, i = [], "", 0
    in_code = False
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            cur += "\\|"
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    cells.append(cur.strip())
    return cells


@dataclass
class Problem:
    row: int  # 1-based line number of the row in the file
    column: str
    cell: str
    reason: str


@dataclass
class Table:
    path: str
    line: int  # 1-based line of the header row
    columns: list[str]
    rows: list[tuple[int, list[str]]]
    opt_out: str | None
    problems: list[Problem] = field(default_factory=list)


def check_cell(cell: str) -> str | None:
    if visible_text(cell) in ("", "-"):
        return "blank or '-' cell (write none, not applicable or not recorded)"
    n_words = words(cell)
    nums = numbers(cell)
    if n_words > MAX_WORDS:
        return f"{n_words} words (> {MAX_WORDS})"
    if len(nums) >= 2:
        return f"{len(nums)} numbers ({', '.join(nums[:4])})"
    return None


def tables(text: str, path: str) -> list[Table]:
    """Every pipe table in ``text`` (outside fenced code blocks), with its problems."""
    lines = text.splitlines()
    out: list[Table] = []
    fence = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^\s*(`{3,}|~{3,})", line)
        if m:
            tok = m.group(1)
            if fence is None:
                if not line.strip().startswith(("```{", "~~~{")) or "table" not in line:
                    fence = tok[0] * len(tok)
            elif line.strip().startswith(fence):
                fence = None
            i += 1
            continue
        if (
            fence is None
            and line.lstrip().startswith("|")
            and i + 1 < len(lines)
            and _SEP.match(lines[i + 1])
        ):
            header = split_row(line)
            before = "\n".join(lines[max(0, i - 3) : i])
            ok = _TABLE_OK.search(before)
            t = Table(path, i + 1, header, [], ok.group(0) if ok else None)
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                t.rows.append((j + 1, split_row(lines[j])))
                j += 1
            for k, h in enumerate(header):
                r = check_cell(h)
                if r and words(h) > MAX_WORDS:
                    t.problems.append(Problem(i + 1, h, h, "header " + r))
            for n, cells in t.rows:
                for k, c in enumerate(cells):
                    r = check_cell(c)
                    if r:
                        col = header[k] if k < len(header) else f"col {k + 1}"
                        t.problems.append(Problem(n, col, c, r))
            prose = any(words(c) > SHORT_WORDS for _n, cells in t.rows for c in cells)
            cap = MAX_COLUMNS_PROSE if prose else MAX_COLUMNS
            if len(header) > cap:
                kind = "with a cell over 3 words" if prose else "of short cells"
                t.problems.append(
                    Problem(i + 1, "(table)", " | ".join(header)[:80],
                            f"{len(header)} columns (> {cap} for a table {kind})")
                )  # fmt: skip
            out.append(t)
            i = j
            continue
        i += 1
    return out


def history_lines(text: str) -> list[tuple[int, str]]:
    """Lines with a narrative history phrase and no history-ok marker (fenced code skipped)."""
    out, fence = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if re.match(r"^\s*(`{3,}|~{3,})", line):
            fence = not fence
            continue
        if fence or _HISTORY_OK.search(line):
            continue
        if HISTORY_PHRASES.search(line):
            out.append((n, line.strip()))
    return out


# Hedge and unknown words banned on reader pages (spec §10.3, owner decision of 14:40). "about"
# counts only before a number. Whole words; a word in `code` or in "double quotes" is a mention.
HEDGES = re.compile(
    r"\b(not yet|yet|unverified|not public|not stated|not published|presumably|probably|"
    r"probable|plausible|plausibly|likely|roughly|approximately)\b|\babout(?= [~≈]?[−+-]?\d)",
    re.IGNORECASE,
)
# A MyST target label line, "(name)=": an identifier, not prose.
_LABEL = re.compile(r"^\s*\([\w.:-]+\)=\s*$")
# Pages that are not reader pages for the hedge rule.
HEDGE_EXEMPT = ("docs/superpowers/", "docs/api/")


def hedge_lines(text: str) -> list[tuple[int, str]]:
    """(line, word) of each hedge word outside code, fences, quotations, HTML comments, roles
    and target label lines."""
    out, fence = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if re.match(r"^\s*(`{3,}|~{3,})", line):
            fence = not fence
            continue
        if fence or _LABEL.match(line):
            continue
        s = re.sub(r"`[^`]*`", " ", line)
        s = re.sub(r"<!--.*?-->", " ", s)
        s = re.sub(r"\]\([^)]*\)", "]", s)
        s = re.sub(r"\{[\w:.-]+\}`[^`]*`", " ", s)
        s = re.sub(r'"[^"]*"|“[^”]*”', " ", s)
        out += [(n, m.group(0)) for m in HEDGES.finditer(s)]
    return out


def source_pages() -> list[Path]:
    """The Markdown sources the docs build reads (no plans, spec or API stubs) and README."""
    pages = [ROOT / "README.md"]
    for p in sorted(DOCS.rglob("*.md")):
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(("docs/superpowers/", "docs/_build/", "docs/_generated", "docs/api/")):
            continue
        pages.append(p)
    return pages


def history_allowed(rel: str) -> bool:
    return rel.startswith(HISTORY_ALLOWED)


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or source_pages()
    bad = 0
    for p in paths:
        if p.is_dir():
            files = sorted(p.rglob("*.md"))
        else:
            files = [p]
        for f in files:
            try:
                rel = f.resolve().relative_to(ROOT).as_posix()
            except ValueError:
                rel = str(f)
            for t in tables(f.read_text(encoding="utf-8"), rel):
                flag = "OPT-OUT" if t.opt_out else ("BAD" if t.problems else "ok")
                print(f"{rel}:{t.line} [{flag}] columns: {' | '.join(t.columns)}")
                for pr in t.problems:
                    print(f"    {rel}:{pr.row} col {pr.column!r}: {pr.reason}: {pr.cell[:90]}")
                bad += bool(t.problems) and not t.opt_out
    print(f"{bad} tables with problems")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
