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
- ``http``: an ``http://`` URL (``https`` only);
- ``broken-link``: a Markdown link into this repository (relative, or ``blob``/``tree`` on
  GitHub) to an untracked path, or into the published docs (README/CONTRIBUTING link to
  ``gf180-tcad.readthedocs.io``) to a page or anchor that the sources do not define.

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
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
GLOSSARY = DOCS / "glossary.md"
CONF = DOCS / "conf.py"
OUTSIDE_SPHINX = ("README.md", "CONTRIBUTING.md")
GLOSSARY_URL = "gf180-tcad.readthedocs.io/en/latest/glossary.html"
RTD = re.compile(
    r"https://gf180-tcad\.readthedocs\.io/en/latest/(?P<page>[^#]*?)(?:\.html)?(?:#(?P<anchor>.*))?$"
)


# Tool and project names whose first mention on a page must be linked: the display texts of
# docs/conf.py:_TOOLS, mapped to their substitution key ({{ key }}).
@cache
def tools() -> dict[str, str]:
    return {text: key for key, (text, _url) in conf_tools().items()}


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


def _word_regex(names, plural: bool, behind: str = r"\w./-") -> re.Pattern:
    alts = []
    for n in sorted(names, key=len, reverse=True):
        suffix = "(?:s|es)?" if plural and re.fullmatch(r"[A-Za-z][A-Za-z -]*", n) else ""
        alts.append(re.escape(n) + suffix)
    # A term may be followed by a hyphen ("DEVSIM-versus-BSIM") but not preceded by one, so the
    # tail of a compound or a name ("bias-sweep", "gf180-tcad", "spice-job") is not a use. The
    # longest alternative wins, so "roll-off" is matched before any shorter term inside it.
    return re.compile(rf"(?<![{behind}])(?:" + "|".join(alts) + r")(?!\w)")


@cache
def _term_regex() -> re.Pattern:
    return _word_regex([t for e in glossary() for t in e], plural=True)


@cache
def _tool_regex() -> re.Pattern:
    return _word_regex(tools(), plural=False)


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
                for tl in _tool_regex().finditer(body):  # e.g. {term}`BSIM4` is a link too
                    events.append((pos, "tool", tl.group(0), True))
            elif rname in ("repo", "test"):
                repo_targets.add(_role_target(body).lstrip("~").split("#")[0].split("::")[0])
        elif m.group("subst"):
            key = m.group("skey")
            for tool, k in tools().items():
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
            local = None
            if gh:
                local = gh.group(1).split("#")[0].rstrip("/")
            elif url and not re.match(r"([a-z]+:|#)", url):
                local = url.split("#")[0].rstrip("/")
            if local is not None:
                repo_targets.add(local)
                if local not in files and local not in dirs:
                    bad(pos, "broken-link", f"{url}: {local} is not tracked by git")
            if (rtd := RTD.match(url)) and not _rtd_target_exists(rtd["page"], rtd["anchor"]):
                bad(pos, "broken-link", f"{url}: no such page or anchor in docs/")
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
            how = f"{{{{ {tools()[key]} }}}}" if sphinx else "a Markdown link"
            bad(pos, "unlinked-tool", f"first mention of {key!r} is not {how}")
    return problems


def _slug(text: str) -> str:
    return re.sub(r"[^\w.]+", "-", text.replace('"', "")).strip("-").lower()


@cache
def _rtd_target_exists(page: str, anchor: str | None) -> bool:
    """Does docs/ define the published page (and its anchor)? Mirrors Sphinx's ids."""
    page = page.strip("/") or "index"
    src = DOCS / f"{page}.md"
    if not src.is_file():
        return False
    if not anchor:
        return True
    if anchor.startswith("term-"):
        return page == "glossary" and _slug(anchor[5:]) in {_slug(t) for t in _all_terms()}
    text = src.read_text(encoding="utf-8")
    ids = set(re.findall(r"^\(([\w-]+)\)=$", text, re.MULTILINE))
    ids |= {_slug(re.sub(r"`", "", h)) for h in re.findall(r"^#+ (.*)$", text, re.MULTILINE)}
    return anchor.lower() in ids


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


def test_tool_urls_are_https():
    keys = conf_tools()
    assert {"ngspice", "Xyce", "DEVSIM", "Charon", "numpy"} <= set(keys)
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
    https://example.org/page for more, and [a missing file](tools/no-such-tool).

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
             "bare-url", "http", "broken-link"],
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
    broken = (
        "See [the tool](tools/no-such-tool), [docs](https://gf180-tcad.readthedocs.io/en/latest/"
        "nope.html), [a term](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-Nope)"
        " and [a section](https://gf180-tcad.readthedocs.io/en/latest/reproduce/index.html#nope)."
    )
    problems = [p for p in check("README.md", broken, sphinx=False) if p.kind == "broken-link"]
    assert len(problems) == 4, problems
    fine = (
        "[x](https://gf180-tcad.readthedocs.io/en/latest/reproduce/index.html#cross-host-determinism)"
        " [y](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-Same-process-window)"
        " [z](https://github.com/mithro/gf180-tcad/blob/main/docker/IMAGE)"
    )
    assert [p for p in check("README.md", fine, sphinx=False) if p.kind == "broken-link"] == []


# --- positive control for the {repo}/{test} roles: a wrong path fails the -W build -----------


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("{repo}`tools/no-such-file`", "not a file or directory tracked by git"),
        ("{repo}`docs/_generated/results/index.md`", "not a file or directory tracked by git"),
        ("{test}`tests/test_doc_links.py::test_no_such_test`", "no function"),
        ("{repo}`tools/sandbox-run#L999999`", "is outside the"),
        ("{repo}`README.md#no-such-heading`", "is not a heading of"),
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


# --- the built HTML: autodoc content, generated pages and everything the sources expand to ----
#
# The source scan above cannot see docstrings, which autodoc pulls in at build time. This scan
# reads the HTML of an offline -W build (the same build as test_docs_build_offline) and applies
# the rules to what a reader sees: every check is "outside an <a>", in the main content, not in
# code blocks, signatures, navigation or headings' permalinks.

_HTML_BLOCK = {
    "p", "div", "li", "td", "th", "tr", "table", "dd", "dt", "section", "h1", "h2", "h3", "h4",
    "h5", "h6", "pre", "ul", "ol", "dl", "blockquote", "figcaption", "caption", "article",
}  # fmt: skip
_HTML_VOID = {"br", "img", "hr", "meta", "link", "input", "wbr", "source"}
_HTML_SKIP_TAGS = {"pre", "script", "style", "nav", "aside"}
# Verdict names are ordinary English words in lower case ("the engines agree"), so they are
# matched with their capital letter only. Every other term and tool is matched ignoring case.
_CASE_SENSITIVE_TERMS = {"Agree", "Disagree", "Same process"}
_HTML_IDENT = re.compile(r"gf180tcad(?:\.\w+)*")
_HTML_TEST = re.compile(r"(?<![\w/])test_\w+")


class _HtmlText(HTMLParser):
    """Flatten a page to text, with per-character flags and the code spans."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict]] = []
        self.chars: list[str] = []
        self.flags: list[tuple[bool, bool, bool, bool, int]] = []
        self.code: list[tuple[int, int, bool, bool, str]] = []  # start, end, in_a, skip, class
        self.linked: list[str] = []  # text of every <a>, for "linked elsewhere on the page"
        self.dd = -1  # index of the current glossary <dd>
        self.dd_terms: list[list[str]] = []  # term names (<dt>) of each <dd>
        self._pending_dt: list[str] = []
        self._code_start: tuple[int, str] | None = None
        self._a_start: int | None = None
        self._dt_start: int | None = None

    def _state(self) -> tuple[bool, bool, bool, bool, int]:
        tags = [t for t, _ in self.stack]
        in_a = "a" in tags
        skip = (
            bool(_HTML_SKIP_TAGS & set(tags))
            or not any(a.get("id") == "furo-main-content" for _, a in self.stack)
            or any(
                {"headerlink", "sig", "toctree-wrapper", "viewcode-link"}
                & set(a.get("class", "").split())
                or (t == "dt" and a.get("id", "").startswith("term-"))
                for t, a in self.stack
            )
        )
        heading = bool({"h1", "h2", "h3", "h4", "h5", "h6"} & set(tags))
        in_dd = "dd" in tags
        return in_a, "code" in tags, skip, heading, self.dd if in_dd else -1

    def _add(self, s: str) -> None:
        f = self._state()
        self.chars.extend(s)
        self.flags.extend([f] * len(s))

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag in _HTML_BLOCK:
            self._add("\n")
        if tag in _HTML_VOID:
            return
        if tag == "dt" and a.get("id", "").startswith("term-"):
            self._dt_start = len(self.chars)
        if tag == "dd":
            self.dd += 1
            self.dd_terms.append(self._pending_dt)
            self._pending_dt = []
        self.stack.append((tag, a))
        if tag == "code" and self._code_start is None:
            self._code_start = (len(self.chars), a.get("class", ""))
        if tag == "a" and self._a_start is None:
            self._a_start = len(self.chars)

    def handle_endtag(self, tag):
        if tag in _HTML_VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] != tag:
                continue
            outer = [t for t, _ in self.stack[:i]]
            if tag == "code" and self._code_start is not None and "code" not in outer:
                start, cls = self._code_start
                del self.stack[i:]
                in_a, _, skip, _, _ = self._state()
                self.code.append((start, len(self.chars), in_a, skip, cls))
                self._code_start = None
            elif tag == "a" and self._a_start is not None and "a" not in outer:
                self.linked.append("".join(self.chars[self._a_start :]))
                self.linked.append(self.stack[i][1].get("href", ""))
                self._a_start = None
                del self.stack[i:]
            elif tag == "dt" and self._dt_start is not None:
                name = "".join(self.chars[self._dt_start :]).strip().rstrip("¶").strip()
                self._pending_dt.append(name)
                self._dt_start = None
                del self.stack[i:]
            else:
                del self.stack[i:]
            break
        if tag in _HTML_BLOCK:
            self._add("\n")

    def handle_data(self, data):
        self._add(data)


@cache
def _ci_term_regex() -> re.Pattern:
    names = [t for e in glossary() for t in e]
    sensitive = [n for n in names if n in _CASE_SENSITIVE_TERMS]
    other = [n for n in names if n not in _CASE_SENSITIVE_TERMS]
    # In the HTML a path has been rendered as code, so "/" may precede a term ("10/Lmin").
    # "*" too: "j*2*pi*f*Cgg" is a formula, where reST cannot place a link.
    a = _word_regex(other, plural=True, behind=r"\w.*-").pattern
    b = _word_regex(sensitive, plural=True, behind=r"\w.*-").pattern
    return re.compile(f"(?i:{a})|{b}")


@cache
def _ci_tool_regex() -> re.Pattern:
    return re.compile(_word_regex(tools(), plural=False).pattern, re.IGNORECASE)


def _ci_lookup(word: str) -> int | None:
    index = _term_index()
    w = word.lower()
    for cand in (w, w[:-1] if w.endswith("s") else None, w[:-2] if w.endswith("es") else None):
        if cand and cand in index:
            return index[cand]
    return None


def check_html(name: str, html_text: str) -> list[Problem]:
    """All problems on one built page (``name`` is its path relative to the HTML root)."""
    files, dirs = tracked()
    p = _HtmlText()
    p.feed(html_text)
    s = "".join(p.chars)
    linked = "\n".join(p.linked)
    problems: list[Problem] = []

    def bad(pos: int, kind: str, msg: str) -> None:
        ctx = re.sub(r"\s+", " ", s[max(0, pos - 40) : pos + 60]).strip()
        problems.append(Problem(name, 0, kind, f"{msg} [...{ctx}...]"))

    def outside(pos: int) -> bool:
        in_a, _in_code, skip, _heading, _dd = p.flags[pos]
        return not in_a and not skip

    for start, end, in_a, skip, cls in p.code:
        if in_a or skip:
            continue
        body = re.sub(r"\s+", " ", s[start:end]).strip()
        tok = body.rstrip("/")
        if "xref" in cls.split():
            bad(start, "html-unresolved-xref", f"`{body}` is a role that did not resolve")
        if (tok in files or tok in dirs) and ("/" in body or "." in tok):  # not a bare `data`
            bad(start, "html-path", f"`{body}` is a tracked path but not a link")
        elif _HTML_IDENT.fullmatch(tok):
            bad(start, "html-identifier", f"`{body}` is not a {{py:...}} link")
        elif re.fullmatch(r"(\S+::)?test_\w+", tok):
            bad(start, "html-test", f"`{body}` is not a {{test}} link")
        elif " " in body:  # a command: its paths and identifiers must be linked on the page
            for word in body.split():
                w = word.strip("'\"(),;:").rstrip("/")
                if (("/" in w and (w in files or w in dirs)) or _HTML_IDENT.fullmatch(w)) and (
                    w not in linked
                ):
                    bad(start, "html-path", f"{w} (inside `{body}`) is never linked on the page")
    for rx, kind in ((_HTML_IDENT, "html-identifier"), (_HTML_TEST, "html-test")):
        for m in rx.finditer(s):
            in_a, in_code, skip, heading, _ = p.flags[m.start()]
            if in_a or in_code or skip:
                continue
            if kind == "html-identifier" and "." not in m.group(0) and m.group(0) in linked:
                continue
            bad(m.start(), kind, f"{m.group(0)} is not a link")

    # Prose is matched ignoring case. Code is case-sensitive and must be the whole span (the
    # literal `cv` is the sweep; `rsd`, `ff` or `provenance.json` are other identifiers).
    exact = {t: i for i, e in enumerate(glossary()) for t in e}
    term_hits = []
    for m in _ci_term_regex().finditer(s):
        if not p.flags[m.start()][1]:
            term_hits.append((m.start(), m.group(0), _ci_lookup(m.group(0))))
    for start, end, _in_a, _skip, _cls in p.code:
        body = s[start:end].strip()
        if body in exact:
            term_hits.append((start, body, exact[body]))
    is_glossary = name == "glossary.html"
    seen_terms: set[tuple[int, int]] = set()
    for pos, word, idx in sorted(term_hits):
        in_a, _in_code, skip, heading, dd = p.flags[pos]
        if skip or heading:
            continue
        if idx is None:
            continue
        if is_glossary:
            if dd < 0 or {t.lower() for t in glossary()[idx]} & {t.lower() for t in p.dd_terms[dd]}:
                continue  # outside a definition, or the entry's own name
            region = dd
        else:
            region = -1
        if (region, idx) in seen_terms:
            continue
        seen_terms.add((region, idx))
        if not in_a:
            where = f" in the definition of {p.dd_terms[dd][0]!r}" if is_glossary else ""
            bad(pos, "html-term", f"first use of {word!r}{where} is not a link")
    if not is_glossary:
        seen_tools: set[str] = set()
        for m in _ci_tool_regex().finditer(s):
            in_a, in_code, skip, heading, _ = p.flags[m.start()]
            key = m.group(0).lower()
            if in_code:
                continue  # `bsim4*.out` is a file name, not the tool
            if skip or heading or key in seen_tools:
                continue
            seen_tools.add(key)
            if not in_a:
                bad(m.start(), "html-tool", f"first mention of {m.group(0)!r} is not a link")
    return problems


def _offline_build(out: Path) -> Path:
    """sphinx-build -W of docs/ with every socket call blocked; returns the HTML directory."""
    pytest.importorskip("sphinx")
    pytest.importorskip("matplotlib", reason="needs the docs dependency group")
    (out / "sitecustomize.py").write_text(
        "import socket\n"
        "def _blocked(*a, **k):\n"
        "    raise OSError('network disabled by test_doc_links')\n"
        "socket.socket.connect = socket.create_connection = socket.getaddrinfo = _blocked\n",
        encoding="utf-8",
    )
    env = {**__import__("os").environ, "PYTHONPATH": str(out)}
    html = out / "html"
    r = subprocess.run(
        [sys.executable, "-m", "sphinx", "-W", "-q", "-b", "html", "-d", str(out / "dt"),
         str(DOCS), str(html)],
        capture_output=True, text=True, env=env, check=False, timeout=900,
    )  # fmt: skip
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    return html


@pytest.fixture(scope="module")
def built_html(tmp_path_factory) -> Path:
    return _offline_build(tmp_path_factory.mktemp("htmlbuild"))


def _html_pages(root: Path) -> list[Path]:
    skip_dirs = {"_modules", "_static", "_sources", "_images"}
    skip_names = {"genindex.html", "search.html", "py-modindex.html"}
    return [
        p for p in sorted(root.rglob("*.html"))
        if not skip_dirs & set(p.relative_to(root).parts) and p.name not in skip_names
    ]  # fmt: skip


def test_every_reference_in_the_html_is_a_link(built_html):
    problems = [
        q for page in _html_pages(built_html)
        for q in check_html(str(page.relative_to(built_html)), page.read_text(encoding="utf-8"))
    ]  # fmt: skip
    assert not problems, f"{len(problems)} unlinked references in the HTML:\n" + "\n".join(
        map(str, problems)
    )


_HTML_BAD = """<html><body><div id="furo-main-content"><h1>Title about the TCAD and Xyce</h1>
<p>Uses <code class="docutils literal"><span class="pre">tools/sandbox-run</span></code>,
<code class="xref py py-func docutils literal"><span class="pre">nope()</span></code>, the module
gf180tcad.metrics, the test test_engines_agree and a ngspice run on the tcad.</p>
<pre>tools/sandbox-run gf180tcad.metrics ngspice</pre>
<p>Run <code class="docutils literal">sudo tools/sandbox-setup</code>.</p>
</div></body></html>"""

_HTML_GOOD = """<html><body><div id="furo-main-content">
<p>Uses <a href="x"><code class="docutils literal">tools/sandbox-run</code></a>, the module
<a href="m"><code class="xref py py-mod">gf180tcad.metrics</code></a>, the test
<a href="t"><code>test_engines_agree</code></a> and <a href="n">ngspice</a> on the
<a href="g"><span class="xref std std-term">TCAD</span></a>; later ngspice and TCAD again.</p>
<p>Run <code class="docutils literal">sudo tools/sandbox-setup</code>
(<a href="s"><code>tools/sandbox-setup</code></a>). The engines agree.</p>
</div></body></html>"""

_HTML_GLOSSARY = """<html><body><div id="furo-main-content"><dl class="glossary">
<dt id="term-hull">hull<a class="headerlink" href="#term-hull">¶</a></dt>
<dd><p>Of two intervals, as in the corner envelope.</p></dd>
<dt id="term-corner-envelope">corner envelope<a class="headerlink" href="#x">¶</a></dt>
<dd><p>The corner envelope uses the <a href="#term-hull">hull</a>.</p></dd>
</dl></div></body></html>"""


@pytest.mark.parametrize(
    "kind", ["html-path", "html-unresolved-xref", "html-identifier", "html-test", "html-term",
             "html-tool"],
)  # fmt: skip
def test_positive_control_html_detector_fires(kind):
    found = {q.kind for q in check_html("control.html", _HTML_BAD)}
    assert kind in found, (kind, [str(q) for q in check_html("control.html", _HTML_BAD)])


def test_positive_control_html_details():
    problems = [str(q) for q in check_html("control.html", _HTML_BAD)]
    assert any("tcad" in q and "html-term" in q for q in problems), "terms ignore case"
    assert any("tools/sandbox-setup (inside" in q for q in problems), "paths in commands"
    assert not any("'TCAD'" in q or "'Xyce'" in q for q in problems), "headings are skipped"
    heading = "<h1>The gf180tcad.metrics module</h1>"
    assert any(
        "gf180tcad.metrics" in str(q)
        for q in check_html(
            "h.html",
            _HTML_GOOD.replace(
                '<div id="furo-main-content">', '<div id="furo-main-content">' + heading
            ),
        )
    )
    assert check_html("control.html", _HTML_GOOD) == []


def test_positive_control_html_glossary_cross_references():
    problems = [str(q) for q in check_html("glossary.html", _HTML_GLOSSARY)]
    assert len(problems) == 1 and "corner envelope" in problems[0] and "'hull'" in problems[0], (
        problems
    )


# --- the API reference is complete ------------------------------------------------------------


def _modules() -> list[str]:
    import pkgutil

    sys.path.insert(0, str(ROOT / "src"))
    try:
        import gf180tcad
    finally:
        sys.path.remove(str(ROOT / "src"))
    return ["gf180tcad"] + sorted(
        m.name for m in pkgutil.walk_packages(gf180tcad.__path__, "gf180tcad.")
    )


def _public_names(module: str) -> list[str]:
    """Public names defined in ``module``'s own source (top-level def, class or assignment)."""
    rel = module.replace(".", "/")
    src = ROOT / "src" / (f"{rel}/__init__.py" if (ROOT / "src" / rel).is_dir() else f"{rel}.py")
    names = []
    for node in ast.parse(src.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names += [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return [n for n in dict.fromkeys(names) if not n.startswith("_")]


def test_every_module_has_an_api_page_in_the_toctree():
    index = (DOCS / "api" / "index.md").read_text(encoding="utf-8")
    toc = re.search(r"```\{toctree\}\n(.*?)```", index, re.DOTALL).group(1).split()
    for module in _modules():
        page = DOCS / "api" / f"{module}.md"
        assert page.is_file(), f"no API page docs/api/{module}.md"
        assert f".. automodule:: {module}\n" in page.read_text(encoding="utf-8"), page
        assert module in toc, f"{module} is not in the docs/api/index.md toctree"


def test_every_public_name_is_documented(built_html):
    missing = []
    for module in _modules():
        page = (built_html / "api" / f"{module}.html").read_text(encoding="utf-8")
        missing += [
            f"{module}.{n}" for n in _public_names(module) if f'id="{module}.{n}"' not in page
        ]
    assert not missing, "not on the API pages:\n" + "\n".join(missing)


def test_repo_role_offline_rules(tmp_path, monkeypatch):
    sys.path.insert(0, str(DOCS / "_ext"))
    try:
        import repo_roles
    finally:
        sys.path.remove(str(DOCS / "_ext"))
    # Without git, .gitignore decides what is not linkable.
    assert repo_roles.ignored("docs/_generated/results/index.md")
    assert repo_roles.ignored("src/gf180tcad/__pycache__/x.pyc")
    assert not repo_roles.ignored("docs/conf.py")
    # Fragments: lines and Markdown headings.
    assert repo_roles.fragment_error("tools/sandbox-run", "L1") is None
    assert repo_roles.fragment_error("tools/sandbox-run", "L999999")
    assert repo_roles.fragment_error("README.md", "development") is None
    assert repo_roles.fragment_error("README.md", "nope")
    # A test name defined twice is ambiguous: no line, and the role warns.
    (tmp_path / "t.py").write_text("def test_a():\n    def test_a():\n        pass\n", "utf-8")
    monkeypatch.setattr(repo_roles, "ROOT", tmp_path)
    monkeypatch.setattr(repo_roles, "classify", lambda path: "blob")
    assert repo_roles.test_lines("t.py", "test_a") == [1, 2]
    assert repo_roles.test_line("t.py", "test_a") is None


# --- the docstring linker (docs/_ext/api_links.py) --------------------------------------------


class _FakeApp:
    def __init__(self):
        sys.path.insert(0, str(DOCS))
        sys.path.insert(0, str(DOCS / "_ext"))
        try:
            import importlib

            conf = importlib.import_module("conf")
            self.subs = dict(conf.myst_substitutions)
        finally:
            sys.path.remove(str(DOCS))

    class config:
        pass


def _linker():
    app = _FakeApp()
    import api_links

    app.config.myst_substitutions = app.subs
    return api_links._Linker(app, set())


def test_linker_short_names_are_case_sensitive():
    lk = _linker()
    line = lk.line("Capacitance in fF; the ss and tt corners are named in lower case.")
    assert ":term:" not in line.split("corners")[0], line  # fF, ss, tt are not FF, SS, TT
    lk = _linker()
    assert ":term:`FF <FF>`" in lk.line("The FF corner is fast.")


def test_linker_leaves_field_names_alone():
    lk = _linker()
    line = lk.line(":param corner: the process corner to run")
    assert line.startswith(":param corner: "), line
    assert ":term:`corner <corner>`" in line, line
    assert _linker().line(":class:`gf180tcad.devices.Device` sweeps").startswith(":class:`")


def test_linker_does_not_link_into_a_filename():
    lk = _linker()
    assert ":term:" not in lk.line("It writes provenance.json next to the CSVs.")
    assert ":term:`provenance <provenance>`" in _linker().line("The provenance of a run.")


def test_html_scan_short_names_are_case_sensitive():
    page = (
        '<html><body><div id="furo-main-content"><p>Capacitance in fF, and the ss and tt '
        "values; it writes provenance.json.</p></div></body></html>"
    )
    assert check_html("u.html", page) == [], [str(q) for q in check_html("u.html", page)]
