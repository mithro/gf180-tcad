# SPDX-License-Identifier: Apache-2.0
"""Every reference in the documentation is a link (the docs-links rule).

Sphinx already fails the ``-W`` build on a wrong ``{repo}`` path, an undefined ``{term}``, an
unresolved ``{py:...}`` target or an unknown label. What it cannot see is a reference that was
never written as a link at all. This test scans the Markdown sources (``docs/**``, the pages
``gf180tcad.docgen`` generates, ``README.md`` and ``CONTRIBUTING.md``) offline and fails on:

- ``bare-path``: an inline-code path of a file or directory tracked by git that is not a link
  (``{repo}`` in the docs, a Markdown link in README/CONTRIBUTING);
- ``bare-identifier``: inline code naming a ``gf180tcad`` module or object instead of a
  ``{py:...}`` role;
- ``bare-test``: inline code naming a test function instead of the ``{test}`` role;
- ``unlinked-term``: the first use on a page of a glossary term (``docs/glossary.md``) that is
  not a ``{term}`` role (or, outside Sphinx, a link to the published glossary);
- ``unlinked-tool``: the first mention on a page of a tool or project that is not linked (its
  ``{{ substitution }}`` from ``docs/conf.py``, or a Markdown link);
- ``bare-url``: a URL written as plain text instead of a link;
- ``http``: an ``http://`` URL (``https`` only).

Each detector has a positive control below that proves it fires.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
GLOSSARY = DOCS / "glossary.md"
CONF = DOCS / "conf.py"
OUTSIDE_SPHINX = ("README.md", "CONTRIBUTING.md")
GLOSSARY_URL = "gf180-tcad.readthedocs.io/en/latest/glossary.html"

# Tool and project names whose first mention on a page must be linked. Each is a key of
# docs/conf.py:_TOOLS (checked below), so the docs can write {{ key }}.
TOOLS = {
    "ngspice": "ngspice",
    "Xyce": "Xyce",
    "DEVSIM": "DEVSIM",
    "Charon": "Charon",
    "gdsfactory": "gdsfactory",
    "KLayout": "KLayout",
    "IIC-OSIC-TOOLS": "IIC_OSIC_TOOLS",
    "open_pdks": "open_pdks",
    "Docker": "Docker",
    "BuildKit": "BuildKit",
    "systemd": "systemd",
    "uv": "uv",
    "numpy": "numpy",
    "matplotlib": "matplotlib",
    "pytest": "pytest",
    "ruff": "ruff",
    "Sphinx": "Sphinx",
    "MyST": "MyST",
    "Read the Docs": "Read_the_Docs",
    "GitHub Actions": "GitHub_Actions",
    "wafer.space": "wafer_space",
    "Tiny Tapeout": "Tiny_Tapeout",
    "SemiMod": "SemiMod",
    "DMT-core": "DMT_core",
}

# Fenced blocks whose content is code, not prose (other directives, e.g. admonitions, are prose).
_CODE_FENCE_INFO = re.compile(r"^(|\w[\w+-]*|\{(toctree|eval-rst|code-block|code)\}.*)$")
_FENCE = re.compile(
    r"^(?P<fence>```+|:::+)(?P<info>[^\n]*)\n(?P<body>.*?)^(?P=fence)[ \t]*$",
    re.DOTALL | re.MULTILINE,
)
_SKIP_LINE = re.compile(r"^(#{1,6} .*|\([\w-]+\)=|:[\w-]+:.*|\s*!\[.*)$", re.MULTILINE)
_TOKEN = re.compile(
    r"(?P<role>\{(?P<rname>[\w:.-]+)\}`(?P<rbody>[^`]*)`)"
    r"|(?P<subst>\{\{\s*(?P<skey>\w+)\s*\}\})"
    r"|(?P<link>\[(?P<ltext>(?:[^\[\]]|\[[^\]]*\])*)\]\((?P<lurl>[^)\s]*)\))"
    r"|(?P<autolink><https?://[^>\s]+>)"
    r"|(?P<code>`(?P<cbody>[^`]+)`)"
    r"|(?P<url>https?://[^\s)>\]]+)",
)
_IDENT = re.compile(r"gf180tcad(\.\w+)*")
_TEST = re.compile(r"(\S+::)?test_\w+")


@dataclass(frozen=True)
class Problem:
    page: str
    line: int
    kind: str
    text: str

    def __str__(self) -> str:
        return f"{self.page}:{self.line}: {self.kind}: {self.text}"


@cache
def tracked() -> tuple[frozenset[str], frozenset[str]]:
    r = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, text=True, check=False
    )
    if r.returncode != 0:
        pytest.skip(f"not a git checkout: {r.stderr.strip()}")
    files = frozenset(p for p in r.stdout.split("\0") if p)
    dirs = frozenset(str(d) for f in files for d in Path(f).parents if str(d) != ".")
    return files, dirs


@cache
def glossary() -> tuple[tuple[str, ...], ...]:
    """The entries of docs/glossary.md, each a tuple of its term names."""
    text = GLOSSARY.read_text(encoding="utf-8")
    m = re.search(r"^```\{glossary\}\n(.*?)^```", text, re.DOTALL | re.MULTILINE)
    assert m, "docs/glossary.md has no {glossary} block"
    entries: list[list[str]] = []
    in_terms = False
    for line in m.group(1).splitlines():
        if not line.strip() or line.startswith(":"):
            in_terms = False
            continue
        if line[0].isspace():
            in_terms = False
            continue
        if not in_terms:
            entries.append([])
            in_terms = True
        entries[-1].append(line.strip())
    return tuple(tuple(e) for e in entries)


@cache
def conf_tools() -> dict[str, tuple[str, str]]:
    tree = ast.parse(CONF.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign | ast.Assign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "_TOOLS" for t in targets):
                return ast.literal_eval(node.value)
    raise AssertionError("docs/conf.py defines no _TOOLS")


def _term_index() -> dict[str, int]:
    return {t.lower(): i for i, entry in enumerate(glossary()) for t in entry}


def _word_regex(names, plural: bool) -> re.Pattern:
    alts = []
    for n in sorted(names, key=len, reverse=True):
        suffix = "(?:s|es)?" if plural and re.fullmatch(r"[A-Za-z][A-Za-z -]*", n) else ""
        alts.append(re.escape(n) + suffix)
    return re.compile(r"(?<![\w.\-/])(?:" + "|".join(alts) + r")(?![\w\-])")


@cache
def _term_regex() -> re.Pattern:
    return _word_regex([t for e in glossary() for t in e], plural=True)


@cache
def _tool_regex() -> re.Pattern:
    return _word_regex(TOOLS, plural=False)


def _role_target(body: str) -> str:
    m = re.fullmatch(r"(?s)(.*?)\s*<([^<>]+)>", body.strip())
    return (m.group(2) if m else body).strip()


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + re.sub(r"[^\n]", " ", text[start:end]) + text[end:]


def check(name: str, text: str, *, sphinx: bool = True, terms: bool = True) -> list[Problem]:
    """All problems on one page. ``sphinx`` is False for README/CONTRIBUTING (no roles there)."""
    files, dirs = tracked()
    term_index = _term_index()
    problems: list[Problem] = []

    def line_of(pos: int) -> int:
        return text.count("\n", 0, pos) + 1

    def bad(pos: int, kind: str, msg: str) -> None:
        problems.append(Problem(name, line_of(pos), kind, msg))

    for m in re.finditer(r"http://(?!localhost|127\.0\.0\.1)\S+", text):
        bad(m.start(), "http", f"{m.group(0)} -> use https")

    prose = text
    for m in _FENCE.finditer(text):
        if _CODE_FENCE_INFO.match(m.group("info").strip()):
            prose = _blank(prose, m.start(), m.end())
        else:  # a directive with prose inside (admonition, glossary): drop only the fences
            prose = _blank(prose, m.start(), m.start("body"))
            prose = _blank(prose, m.end("body"), m.end())
            if m.group("info").strip() == "{glossary}":  # term lines define, they do not use
                for t in re.finditer(r"^\S.*$", m.group("body"), re.MULTILINE):
                    prose = _blank(prose, m.start("body") + t.start(), m.start("body") + t.end())
    prose = _SKIP_LINE.sub(lambda m: " " * len(m.group(0)), prose)

    # (offset, kind, key, linked) events; kind is "term" (key = entry index) or "tool".
    events: list[tuple[int, str, object, bool]] = []
    repo_targets: set[str] = set()
    masked = prose
    for m in _TOKEN.finditer(prose):
        pos = m.start()
        if m.group("role"):
            rname, body = m.group("rname"), m.group("rbody")
            if rname == "term":
                idx = term_index.get(_role_target(body).lower())
                if idx is not None:
                    events.append((pos, "term", idx, True))
            elif rname in ("repo", "test"):
                repo_targets.add(_role_target(body).lstrip("~").split("#")[0].split("::")[0])
        elif m.group("subst"):
            key = m.group("skey")
            for tool, k in TOOLS.items():
                if k == key:
                    events.append((pos, "tool", tool, True))
        elif m.group("link"):
            ltext, url = m.group("ltext"), m.group("lurl")
            for t in _tool_regex().finditer(ltext):
                events.append((pos, "tool", t.group(0), True))
            if GLOSSARY_URL in url:
                for t in _term_regex().finditer(ltext):
                    idx = term_index.get(_singular(t.group(0), term_index))
                    if idx is not None:
                        events.append((pos, "term", idx, True))
            gh = re.match(r"https://github\.com/mithro/gf180-tcad/(?:blob|tree)/[^/]+/(.+)", url)
            if gh:
                repo_targets.add(gh.group(1).split("#")[0].rstrip("/"))
            elif url and not re.match(r"[a-z]+:", url):
                repo_targets.add(url.split("#")[0].rstrip("/"))
        elif m.group("url") and not m.group("autolink"):
            bad(pos, "bare-url", f"{m.group('url')} -> [text]({m.group('url')})")
        elif m.group("autolink"):
            bad(pos, "bare-url", f"{m.group('autolink')} -> [text](url)")
        elif m.group("code"):
            body = m.group("cbody").strip()
            tok = body.rstrip("/")
            role = "{repo}`" if sphinx else "[`...`](...)"
            if tok in files or tok in dirs:
                bad(pos, "bare-path", f"`{body}` -> {role}{body}`" if sphinx else f"`{body}`")
            elif _IDENT.fullmatch(tok):
                bad(pos, "bare-identifier", f"`{body}` -> {{py:...}}`{body}`")
            elif _TEST.fullmatch(tok):
                bad(pos, "bare-test", f"`{body}` -> {{test}}`path::{body}`")
            else:
                idx = term_index.get(body.lower()) if body in _all_terms() else None
                if idx is not None:
                    events.append((pos, "term", idx, False))
                for word in body.split()[1:] if " " in body else ():
                    w = word.rstrip("/")
                    if "/" in w and w in files:
                        events.append((pos, "path", w, False))
        masked = _blank(masked, m.start(), m.end())

    for m in _term_regex().finditer(masked):
        idx = term_index.get(_singular(m.group(0), term_index))
        if idx is not None:
            events.append((m.start(), "term", idx, False))
    for m in _tool_regex().finditer(masked):
        events.append((m.start(), "tool", m.group(0), False))

    seen: set[tuple[str, object]] = set()
    for pos, kind, key, linked in sorted(events, key=lambda e: e[0]):
        if kind == "path":
            if key not in repo_targets:
                bad(pos, "bare-path", f"{key} (inside a command) is never linked on this page")
            continue
        if (kind, key) in seen:
            continue
        seen.add((kind, key))
        if linked:
            continue
        if kind == "term" and terms:
            entry = glossary()[key]
            how = "{term}`...`" if sphinx else f"a link to https://{GLOSSARY_URL}"
            bad(pos, "unlinked-term", f"first use of {entry[0]!r} is not {how}")
        elif kind == "tool":
            how = f"{{{{ {TOOLS[key]} }}}}" if sphinx else "a Markdown link"
            bad(pos, "unlinked-tool", f"first mention of {key!r} is not {how}")
    return problems


@cache
def _all_terms() -> frozenset[str]:
    return frozenset(t for e in glossary() for t in e)


def _singular(word: str, index: dict[str, int]) -> str:
    w = word.lower()
    for cut in ("", "s", "es"):
        if cut and w.endswith(cut) and w[: -len(cut)] in index:
            return w[: -len(cut)]
        if not cut and w in index:
            return w
    return w


# --- the pages --------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def generated(tmp_path_factory) -> Path:
    pytest.importorskip("matplotlib", reason="needs the docs dependency group")
    from gf180tcad import docgen

    out = tmp_path_factory.mktemp("generated")
    docgen.generate(out)
    return out


def _pages(generated: Path) -> list[tuple[str, str, bool, bool]]:
    """(name, text, sphinx, check_terms) for every page."""
    pages = []
    for p in sorted(DOCS.rglob("*.md")):
        rel = p.relative_to(ROOT)
        if {"superpowers", "_generated", "_build"} & set(rel.parts):
            continue
        # The glossary defines the terms; its own term lines are not "uses".
        pages.append((str(rel), p.read_text(encoding="utf-8"), True, p != GLOSSARY))
    for p in sorted((generated / "results").rglob("*.md")):
        name = "docgen:" + str(p.relative_to(generated))
        pages.append((name, p.read_text(encoding="utf-8"), True, True))
    for name in OUTSIDE_SPHINX:
        pages.append((name, (ROOT / name).read_text(encoding="utf-8"), False, True))
    return pages


def test_every_reference_is_a_link(generated):
    problems = [
        p for name, text, sphinx, terms in _pages(generated)
        for p in check(name, text, sphinx=sphinx, terms=terms)
    ]  # fmt: skip
    assert not problems, f"{len(problems)} unlinked references:\n" + "\n".join(map(str, problems))


def test_tool_keys_exist_in_conf():
    keys = conf_tools()
    assert set(TOOLS.values()) <= set(keys), set(TOOLS.values()) - set(keys)
    for key, (text, url) in keys.items():
        assert url.startswith("https://"), (key, url)


def test_glossary_parses():
    entries = glossary()
    names = [t.lower() for e in entries for t in e]
    assert len(entries) >= 60 and len(names) == len(set(names)), "duplicate glossary term"
    assert "tcad" in names and "ss corner" in names and "subthreshold slope" in names


# --- positive controls: each detector fires -------------------------------------------------

_BAD = textwrap.dedent(
    """\
    # A heading with `tools/sandbox-run` is ignored

    Every run goes through `tools/sandbox-run`, see `gf180tcad.sandbox.run` and
    `test_engines_agree`. The TCAD is compared with ngspice. See http://example.org and
    https://example.org/page for more.

    ```sh
    tools/sandbox-run -- true
    ```

    Run `python -m gf180tcad.manifest verify-subset x --subset tests/crosscheck_subset.txt`.
    """
)

_GOOD = textwrap.dedent(
    """\
    Every run goes through {repo}`tools/sandbox-run`, see {py:func}`gf180tcad.sandbox.run` and
    {test}`tests/spice/test_xyce.py::test_engines_agree`. The {term}`TCAD` is compared with
    {{ ngspice }}; later the TCAD and ngspice again. See [the example](https://example.org).

    Run `python -m gf180tcad.manifest verify-subset x --subset tests/crosscheck_subset.txt`
    ({repo}`tests/crosscheck_subset.txt`).
    """
)


@pytest.mark.parametrize(
    "kind", ["bare-path", "bare-identifier", "bare-test", "unlinked-term", "unlinked-tool",
             "bare-url", "http"],
)  # fmt: skip
def test_positive_control_detector_fires(kind):
    found = {p.kind for p in check("control.md", _BAD)}
    assert kind in found, (kind, [str(p) for p in check("control.md", _BAD)])


def test_positive_control_paths_inside_commands():
    problems = [str(p) for p in check("control.md", _BAD) if p.kind == "bare-path"]
    assert any("tests/crosscheck_subset.txt" in p for p in problems), problems
    assert not any(":1:" in p for p in problems), "headings must be ignored"
    assert not any(":8:" in p for p in problems), "code blocks must be ignored"


def test_positive_control_linked_text_is_clean():
    assert check("control.md", _GOOD) == []


def test_positive_control_outside_sphinx():
    found = {p.kind for p in check("README.md", _BAD, sphinx=False)}
    assert {"bare-path", "unlinked-term", "unlinked-tool"} <= found
    good = (
        "The [TCAD](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-TCAD) runs "
        "through [`tools/sandbox-run`](tools/sandbox-run) and [ngspice](https://ngspice.org/)."
    )
    assert check("README.md", good, sphinx=False) == []


# --- positive control for the {repo}/{test} roles: a wrong path fails the -W build -----------


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("{repo}`tools/no-such-file`", "not a file or directory tracked by git"),
        ("{repo}`docs/_generated/results/index.md`", "not a file or directory tracked by git"),
        ("{test}`tests/test_doc_links.py::test_no_such_test`", "no function"),
    ],
)
def test_repo_role_rejects_bad_targets(tmp_path, source, message):
    pytest.importorskip("sphinx")
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text(
        f"import sys\nsys.path.insert(0, {str(DOCS / '_ext')!r})\n"
        "extensions = ['myst_parser', 'repo_roles']\n",
        encoding="utf-8",
    )
    (src / "index.md").write_text(f"# t\n\n{source} and {{repo}}`tools/sandbox-run`\n", "utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "sphinx", "-W", "-q", "-b", "html", str(src), str(tmp_path / "o")],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip
    assert r.returncode != 0 and message in r.stderr, r.stdout + r.stderr


def test_repo_role_links_the_commit(tmp_path):
    pytest.importorskip("sphinx")
    sys.path.insert(0, str(DOCS / "_ext"))
    try:
        import repo_roles
    finally:
        sys.path.remove(str(DOCS / "_ext"))
    ref = repo_roles.git_ref()
    assert repo_roles.repo_url("tools/sandbox-run") == (
        f"https://github.com/mithro/gf180-tcad/blob/{ref}/tools/sandbox-run"
    )
    assert repo_roles.repo_url("docker/base/") == (
        f"https://github.com/mithro/gf180-tcad/tree/{ref}/docker/base"
    )
    assert repo_roles.repo_url("docs/_generated") is None
    line = repo_roles.test_line("tests/test_docgen.py", "test_docs_build_offline")
    assert (
        line is not None
        and "def test_docs_build_offline"
        in ((ROOT / "tests/test_docgen.py").read_text(encoding="utf-8").splitlines()[line - 1])
    )
