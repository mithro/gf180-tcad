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

# A cell holds at most this many words (after markup is reduced to its visible text).
MAX_WORDS = 8

# Pages that may narrate what used to be true (spec §10.3).
HISTORY_ALLOWED = (
    "docs/superpowers/",
    "docs/reproduce/",
    "docs/limitations/plugin-history.md",
    "docs/api/",
)

HISTORY_PHRASES = re.compile(
    r"\b(previously|no longer|used to be|used to\b|before PR|until PR|was changed|initially|predates?|backfilled|"
    r"were changed|formerly|in the past|at the time of writing|originally)\b",
    re.IGNORECASE,
)

_TABLE_OK = re.compile(r"<!--\s*table-ok:\s*\S.*-->")
_HISTORY_OK = re.compile(r"<!--\s*history-ok:\s*\S.*-->")
_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")

# A number: optional sign, digits with optional thousands separators and decimals, optional
# exponent (1e-10, 1.6e-16, 10⁻³ style is not used in tables).
_NUMBER = re.compile(
    r"(?<![\w.])[−+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][−+-]?\d+)?(?![\w])"
)


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
    text = visible_text(cell)
    # identifiers such as nfet_05v0, w10p0_l0p60, Table MS3, R1, #35, sha prefixes
    text = re.sub(r"\b\w*[A-Za-z_]\w*\d\w*\b|\b\d+\w*[A-Za-z_]\w*\b", "ID", text)
    text = re.sub(r"#\d+", "ID", text)
    return _NUMBER.findall(text)


def split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
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
        if fence is None and line.lstrip().startswith("|") and i + 1 < len(lines) and _SEP.match(
            lines[i + 1]
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
