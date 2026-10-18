# SPDX-License-Identifier: Apache-2.0
"""Turn references in docstrings into links when autodoc renders them, without editing sources.

The generator modules (``gf180tcad.reference.GENERATOR_MODULES``) cannot be edited for a
documentation-only change: their bytes are hashed into ``generator_sha256``, so any edit forces
a regeneration of the SPICE reference. This ``autodoc-process-docstring`` hook therefore adapts
every docstring as it is read (the source files stay byte-identical):

- an inline literal naming a file or directory tracked by git becomes ``:repo:``;
- an inline literal naming a test function (``test_*``) becomes ``:test:`` (the function must
  exist exactly once under ``tests/``, else the build fails);
- an inline literal naming a ``gf180tcad`` module or object becomes ``:py:obj:``;
- the first use on each API page of every glossary term (``docs/glossary.md``) and every tool
  (``docs/conf.py:_TOOLS``, the same tables the Markdown pages use) becomes a ``:term:`` or an
  upstream link, matched ignoring case except for the three verdict words;
- short references to names a module imports from another gf180tcad module are qualified to
  the defining module, where they are documented (plus ``GRID_TOL``, a plain float);
- standard-library and numpy types in signatures (which intersphinx would resolve, but it needs
  the network) are linked to their upstream documentation from a fixed table;
- ``|Vgs|``-style magnitudes are escaped (reST would read them as substitutions), and module
  constants without a doc comment lose the docstring of their type (``dict``, ``tuple``).
"""

from __future__ import annotations

import ast
import functools
import re
import sys
from pathlib import Path

import repo_roles
from docutils import nodes
from sphinx.errors import ExtensionError

DOCS = Path(__file__).resolve().parents[1]
ROOT = DOCS.parent
CASE_SENSITIVE_TERMS = {"Agree", "Disagree", "Same process"}  # verdicts; lower case is a verb


def case_sensitive(name: str) -> bool:
    """Match ``name`` with its exact capitalisation?

    The verdicts, and every short name with a capital letter (TT, FF, SS corner names, PDK, Vt,
    Cgg, Lmin, BSIM...): in lower or mixed case those are other words or units ("fF", "tt").
    """
    return name in CASE_SENSITIVE_TERMS or (len(name) <= 5 and name != name.lower())


QUALIFY = {
    ":data:`GRID_TOL`": ":data:`~gf180tcad.devices.GRID_TOL`",
    ":attr:`SpiceResult.warnings`": ":attr:`~gf180tcad.spice.common.SpiceResult.warnings`",
}
_MAGNITUDE = re.compile(r"\|(\w+)\|")
_FIELD = re.compile(r"^\s*:\w[^:`]*:(?!`)")
# Inline markup that is left alone: roles, literals, hyperlinks, explicit targets, URLs.
_PROTECTED = re.compile(
    r"(?P<strong>\*\*[^*]+\*\*|\*[^*\s][^*]*\*)"  # reST cannot nest a role in emphasis
    r"|(?P<role>:[\w:+-]+:`[^`]*`)"
    r"|(?P<literal>``(?P<lbody>[^`]+)``)"
    r"|(?P<link>`[^`]*`__?)"
    r"|(?P<url>https?://\S+)"
)


def glossary_entries() -> list[list[str]]:
    """The term names of each entry of docs/glossary.md (same parsing as the tests)."""
    text = (DOCS / "glossary.md").read_text(encoding="utf-8")
    body = re.search(r"^```\{glossary\}\n(.*?)^```", text, re.DOTALL | re.MULTILINE).group(1)
    entries: list[list[str]] = []
    in_terms = False
    for line in body.splitlines():
        if not line.strip() or line.startswith(":") or line[0].isspace():
            in_terms = False
            continue
        if not in_terms:
            entries.append([])
            in_terms = True
        entries[-1].append(line.strip())
    return entries


def word_regex(names, *, plural: bool, ignore_case: bool) -> re.Pattern:
    alts = []
    for n in sorted(names, key=len, reverse=True):
        suffix = "(?:s|es)?" if plural and re.fullmatch(r"[A-Za-z][A-Za-z -]*", n) else ""
        alts.append(re.escape(n) + suffix)
    flags = re.IGNORECASE if ignore_case else 0
    # Not followed by a word character, nor by "." and one ("provenance.json" is a file name).
    return re.compile(r"(?<![\w./-])(?:" + "|".join(alts) + r")(?!\w|\.\w)", flags)


@functools.cache
def tables(substitutions: tuple[tuple[str, str], ...]):
    entries = glossary_entries()
    index = {t.lower(): i for i, e in enumerate(entries) for t in e}
    names = [t for e in entries for t in e]
    ci = word_regex([n for n in names if not case_sensitive(n)], plural=True,
                    ignore_case=True)  # fmt: skip
    cs = word_regex([n for n in names if case_sensitive(n)], plural=True,
                    ignore_case=False)  # fmt: skip
    tools = {}
    for _key, value in substitutions:
        m = re.fullmatch(r"\[([^\]]+)\]\((https://[^)]+)\)", value)
        if m:
            tools[m.group(1)] = m.group(2)
    tool_re = word_regex(tools, plural=False, ignore_case=True)
    return entries, index, (ci, cs), tools, tool_re


def _entry(word: str, index: dict[str, int]) -> int | None:
    w = word.lower()
    for cand in (w, w[:-1] if w.endswith("s") else None, w[:-2] if w.endswith("es") else None):
        if cand and cand in index:
            return index[cand]
    return None


@functools.cache
def test_functions() -> dict[str, list[str]]:
    """test name -> tracked test files that define it."""
    files, _dirs = repo_roles.tracked()
    out: dict[str, list[str]] = {}
    for f in sorted(files):
        if f.startswith("tests/") and f.endswith(".py"):
            tree = ast.parse((ROOT / f).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    out.setdefault(node.name, []).append(f)
    return out


class _Linker:
    def __init__(self, app, seen: set):
        subs = tuple(sorted(app.config.myst_substitutions.items()))
        self.entries, self.index, self.term_res, self.tools, self.tool_re = tables(subs)
        self.seen = seen

    def literal(self, body: str, original: str) -> str:
        kind = repo_roles.classify(body.rstrip("/")) if "/" in body or "." in body else None
        if kind is not None:
            return f":repo:`{body}`"
        if re.fullmatch(r"test_\w+", body):
            where = test_functions().get(body, [])
            if len(where) != 1:
                raise ExtensionError(f"docstring names test {body!r}, defined in {where}")
            return f":test:`{where[0]}::{body}`"
        if re.fullmatch(r"gf180tcad(\.\w+)+", body):
            return f":py:obj:`{body}`"
        if body in {t for e in self.entries for t in e}:  # exact (code is case-sensitive)
            idx = self.index[body.lower()]
            if ("term", idx) not in self.seen:
                self.seen.add(("term", idx))
                return f":term:`{body}`"
        return original

    def prose(self, text: str, prev: str = " ", nxt: str = " ") -> str:
        """Link first uses in ``text``; ``prev``/``nxt`` are the characters around it."""
        events = []
        for rx in self.term_res:
            for m in rx.finditer(text):
                idx = _entry(m.group(0), self.index)
                if idx is not None:
                    events.append((m.start(), m.end(), "term", idx, m.group(0)))
        for m in self.tool_re.finditer(text):
            name = next(t for t in self.tools if t.lower() == m.group(0).lower())
            events.append((m.start(), m.end(), "tool", name, m.group(0)))
        out, pos = [], 0
        for start, end, kind, key, word in sorted(events):
            if start < pos or (kind, key) in self.seen:
                continue
            before = text[start - 1] if start else prev
            after = text[end] if end < len(text) else nxt
            if not (before.isspace() or before in "'\"(<[{/:-") or not (
                after.isspace() or after in "-.,:;!?\\/'\")]}>"
            ):
                continue  # reST would not recognise a role here (e.g. "f*Cgg")
            self.seen.add((kind, key))
            out.append(text[pos:start])
            if kind == "term":
                canonical = self.entries[key][0]
                out.append(f":term:`{word} <{canonical}>`")
            else:
                out.append(f"`{word} <{self.tools[key]}>`__")
            pos = end
        out.append(text[pos:])
        return "".join(out)

    def line(self, line: str) -> str:
        if line.lstrip().startswith(".."):
            return line
        field = _FIELD.match(line)  # ":param corner: ..." -- the field name is not prose
        if field:
            return field.group(0) + self.line(line[field.end() :])
        for a, b in QUALIFY.items():
            line = line.replace(a, b)
        out, pos = [], 0
        for m in _PROTECTED.finditer(line):
            prev = line[pos - 1] if pos else " "
            out.append(self.prose(line[pos : m.start()], prev, line[m.start()]))
            if m.group("literal"):
                out.append(self.literal(m.group("lbody"), m.group(0)))
            elif m.group("strong"):  # *job*: a role cannot nest in emphasis, so it replaces it
                inner = m.group(0).strip("*")
                linked = self.prose(inner)
                out.append(
                    linked
                    if linked != inner
                    and linked.startswith(":")
                    and linked.endswith("`")
                    and linked.count("`") == 2
                    else m.group(0)
                )
            else:
                out.append(m.group(0))
            pos = m.end()
        out.append(self.prose(line[pos:], line[pos - 1] if pos else " "))
        return _MAGNITUDE.sub(r"\\|\1\\|", "".join(out))


_PY_ROLE = re.compile(r":(?:py:)?(class|func|data|attr|exc|meth|obj):`(~?)([A-Za-z_][\w.]*)`")


def _module_of(name: str):
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        mod = sys.modules.get(".".join(parts[:i]))
        if mod is not None:
            return mod
    return None


def qualify_imported(line: str, module) -> str:
    """``:class:`SpiceError``` in a module that imports it from elsewhere -> its real home.

    Re-exported names are documented once, where they are defined (``ignore-module-all``), so a
    short reference must name that module to resolve.
    """
    if module is None:
        return line

    def fix(m: re.Match) -> str:
        role, _tilde, target = m.groups()
        obj = getattr(module, target.split(".")[0], None)
        home = getattr(obj, "__module__", None)
        if home and home.startswith("gf180tcad") and home != module.__name__:
            return f":{role}:`~{home}.{target}`"
        return m.group(0)

    return _PY_ROLE.sub(fix, line)


def process_docstring(app, what, name, obj, options, lines):
    if (
        what == "data"
        and lines
        and type(obj).__doc__
        and "\n".join(lines).strip() == type(obj).__doc__.strip()
    ):
        lines.clear()
    docname = app.env.docname
    page_module = docname.removeprefix("api/")
    home = getattr(obj, "__module__", None) if what in ("function", "class", "exception") else None
    if isinstance(home, str) and home != page_module:
        # autodoc reads the docstring of an imported member before it decides to leave it out;
        # it must not use up the page's first uses.
        lines[:] = [_MAGNITUDE.sub(r"\\|\1\\|", line) for line in lines]
        return
    seen = app.env.__dict__.setdefault("_api_links_seen", {}).setdefault(docname, set())
    linker = _Linker(app, seen)
    module = _module_of(name)
    lines[:] = [qualify_imported(line, module) for line in lines]
    out, block_indent = [], None
    for line in lines:
        indent = len(line) - len(line.lstrip())
        if block_indent is not None and line.strip() and indent <= block_indent:
            block_indent = None  # the literal block ended
        if block_indent is not None or line.lstrip().startswith(">>>"):
            out.append(line)
            continue
        out.append(linker.line(line))
        if line.rstrip().endswith("::"):
            block_indent = indent
    lines[:] = out


def _reset(app, env, docnames):
    seen = env.__dict__.setdefault("_api_links_seen", {})
    for d in docnames:
        seen.pop(d, None)


_PY = "https://docs.python.org/3/library/"
# The anchor each builtin has in the Python documentation (checked: the ids exist on the pages).
_BUILTINS = {
    **{n: "stdtypes.html#" + n for n in ("str", "bytes", "dict", "list", "tuple", "set",
                                         "frozenset")},
    **{n: "functions.html#" + n for n in ("int", "float", "bool", "object", "type")},
}  # fmt: skip
_EXTERNAL = {
    "None": _PY + "constants.html#None",
    "pathlib.Path": _PY + "pathlib.html#pathlib.Path",
    "subprocess.CompletedProcess": _PY + "subprocess.html#subprocess.CompletedProcess",
    "argparse.Namespace": _PY + "argparse.html#argparse.Namespace",
    "numpy.ndarray": "https://numpy.org/doc/stable/reference/generated/numpy.ndarray.html",
    # Sphinx splits the string annotation "tuple[float, ...]" of a NamedTuple field at the comma.
    "'tuple[float": _PY + "stdtypes.html#tuple",
}


def external_url(target: str) -> str | None:
    if target in _BUILTINS:
        return _PY + _BUILTINS[target]
    if re.fullmatch(r"collections\.abc\.\w+", target):
        return _PY + f"collections.abc.html#{target}"
    return _EXTERNAL.get(target)


def resolve_external(app, env, node, contnode):
    if node.get("refdomain") != "py":
        return None
    url = external_url(node.get("reftarget", ""))
    if url is None:
        return None
    ref = nodes.reference("", "", internal=False, refuri=url, reftitle=node["reftarget"])
    ref += contnode
    return ref


def setup(app):
    app.connect("autodoc-process-docstring", process_docstring)
    app.connect("missing-reference", resolve_external)
    app.connect("env-before-read-docs", _reset)
    # The first-use state is per document and a document is read in one process, so parallel
    # reads (Read the Docs uses -j auto) give the same result; nothing needs merging.
    return {"parallel_read_safe": True, "parallel_write_safe": True, "version": "1"}
