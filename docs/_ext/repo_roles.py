# SPDX-License-Identifier: Apache-2.0
"""Sphinx roles that link repository files and test functions to GitHub, checked offline.

``{repo}`path``` links ``https://github.com/mithro/gf180-tcad/blob/<ref>/path`` (``tree/`` for a
directory) and shows the path as code. ``{repo}`~path``` shows only the last path component, and
``{repo}`text <path>``` shows ``text`` as plain prose. A ``#fragment`` after the path is kept in
the URL. ``{test}`tests/x.py::test_name``` links the line of that test function (found with
:mod:`ast` at build time, so the anchor cannot drift) and shows ``test_name`` as code.

Every target is checked against the checkout when the page is read: a path that is not tracked
by git (missing, misspelt or git-ignored such as ``docs/_generated/``; without git, the
top-level .gitignore decides), a git submodule (gitlink) or a path inside one (GitHub has no
page for it here; the warning says to link the submodule's repository at the pinned commit), a
``#L<n>`` line past the end of the file, a ``#heading`` that a
Markdown file does not have, or a test function that does not exist exactly once is a Sphinx
warning, which ``sphinx-build -W`` (CI, Read the Docs, and
``tests/test_docgen.py::test_docs_build_offline``) turns into a build failure. No network is
used.

``<ref>`` is ``READTHEDOCS_GIT_COMMIT_HASH`` when set, else ``git rev-parse HEAD``, else ``main``.
Pinning to the commit keeps links stable and makes a file added in the same pull request resolve
before merge. It also means the HTML depends on the commit being built: two builds of the same
commit are identical.
"""

from __future__ import annotations

import ast
import configparser
import fnmatch
import functools
import os
import re
import subprocess
from pathlib import Path

from docutils import nodes
from sphinx.util import logging
from sphinx.util.docutils import SphinxRole

GITHUB = "https://github.com/mithro/gf180-tcad"
ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


@functools.cache
def git_ref() -> str:
    """The commit the links point at (see the module docstring)."""
    env = os.environ.get("READTHEDOCS_GIT_COMMIT_HASH", "").strip()
    if env:
        return env
    head = _git("rev-parse", "HEAD")
    return head.strip() if head and head.strip() else "main"


@functools.cache
def tracked() -> tuple[frozenset[str], frozenset[str]]:
    """``(files, directories)`` tracked by git; empty sets when git is unavailable."""
    out = _git("ls-files", "-z")
    if out is None:
        return frozenset(), frozenset()
    files = frozenset(p for p in out.split("\0") if p)
    dirs = frozenset(str(d) for f in files for d in Path(f).parents if str(d) != ".")
    return files, dirs


@functools.cache
def _gitignore() -> tuple[str, ...]:
    path = ROOT / ".gitignore"
    if not path.is_file():
        return ()
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(ln.strip() for ln in lines if ln.strip() and not ln.startswith("#"))


def ignored(path: str) -> bool:
    """Whether ``path`` (or a parent) matches a pattern of the top-level .gitignore.

    Used only without git. It understands what this repository's .gitignore uses (globs, a
    trailing ``/`` for directories, a leading ``/`` for the root); negations are not supported.
    """
    parts = Path(path).parts
    for pat in _gitignore():
        if pat.startswith("!"):
            raise ValueError(f".gitignore negation {pat!r} is not supported without git")
        anchored = pat.startswith("/") or "/" in pat.rstrip("/")
        pat = pat.strip("/")
        for i in range(1, len(parts) + 1):
            prefix = "/".join(parts[:i])
            if fnmatch.fnmatch(prefix if anchored else parts[i - 1], pat):
                return True
    return False


@functools.cache
def submodules() -> tuple[tuple[str, str | None, str | None], ...]:
    """``(path, url, commit)`` of every git submodule (gitlink).

    With git: the mode-160000 entries of ``git ls-files -s`` (the pinned commit), with the URL
    from ``.gitmodules``. Without git: the ``path``/``url`` entries of ``.gitmodules``; the
    commit is then unknown (None).
    """
    urls: dict[str, str | None] = {}
    gm = ROOT / ".gitmodules"
    if gm.is_file():
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read_string(gm.read_text(encoding="utf-8"))
        for section in cfg.sections():
            if "path" in cfg[section]:
                urls[cfg[section]["path"].strip().rstrip("/")] = cfg[section].get("url")
    out = _git("ls-files", "-s", "-z")
    if out is None:
        return tuple((path, url, None) for path, url in sorted(urls.items()))
    links = []
    for entry in out.split("\0"):
        meta, _, path = entry.partition("\t")
        fields = meta.split()
        if len(fields) == 3 and fields[0] == "160000":
            links.append((path, urls.get(path), fields[1]))
    return tuple(sorted(links))


def submodule(path: str) -> tuple[str, str | None, str | None] | None:
    """The submodule ``path`` is, or lies inside, as in :func:`submodules`; else None."""
    path = path.rstrip("/")
    for sub in submodules():
        if path == sub[0] or path.startswith(sub[0] + "/"):
            return sub
    return None


def submodule_hint(sub: tuple[str, str | None, str | None]) -> str:
    """What to link instead of a submodule path: the fork at the pinned commit."""
    path, url, commit = sub
    base = (url or "<submodule url>").removesuffix(".git")
    return (
        f"link the submodule's own repository at the pinned commit instead, e.g. "
        f"[...]({base}/tree/{commit or '<pinned commit>'}/<path inside it>) "
        f"(the commit is `git ls-tree HEAD {path}`)"
    )


def classify(path: str) -> str | None:
    """``"blob"`` for a tracked file, ``"tree"`` for a tracked directory, else None.

    A git submodule (gitlink) and anything inside it is None: GitHub serves no blob/tree page of
    this repository for it.
    """
    path = path.rstrip("/")
    if submodule(path) is not None:
        return None
    files, dirs = tracked()
    if not files:  # no git (e.g. an sdist): the file system, minus what .gitignore excludes
        p = ROOT / path
        if ignored(path):
            return None
        return "tree" if p.is_dir() else "blob" if p.is_file() else None
    if path in files:
        return "blob"
    if path in dirs:
        return "tree"
    return None


def _github_slug(heading: str) -> str:
    """GitHub's anchor for a Markdown heading (lower case, punctuation dropped, spaces to -)."""
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def fragment_error(path: str, fragment: str) -> str | None:
    """Why ``#fragment`` does not exist in the tracked file ``path`` (None if it does)."""
    if not fragment:
        return None
    m = re.fullmatch(r"L(\d+)(?:-L(\d+))?", fragment)
    if m:
        n = len((ROOT / path).read_text(encoding="utf-8").splitlines())
        lines = [int(x) for x in m.groups() if x]
        if not all(1 <= x <= n for x in lines) or lines != sorted(lines):
            return f"#{fragment} is outside the {n} lines of {path}"
        return None
    if path.endswith(".md"):
        text = (ROOT / path).read_text(encoding="utf-8")
        slugs = {_github_slug(h) for h in re.findall(r"^#+ (.+)$", text, re.MULTILINE)}
        if fragment not in slugs:
            return f"#{fragment} is not a heading of {path}"
    return None


def repo_url(path: str, fragment: str = "") -> str | None:
    kind = classify(path)
    if kind is None:
        return None
    url = f"{GITHUB}/{kind}/{git_ref()}/{path.rstrip('/')}"
    return url + (f"#{fragment}" if fragment else "")


def test_lines(path: str, name: str) -> list[int]:
    """Lines of every ``def name`` (module level, in a class or nested) in the file ``path``."""
    if classify(path) != "blob":
        return []
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def test_line(path: str, name: str) -> int | None:
    """Line of the one ``def name`` in ``path``; None if there is none or more than one."""
    lines = test_lines(path, name)
    return lines[0] if len(lines) == 1 else None


def _split(text: str) -> tuple[str | None, str]:
    """``"title <target>"`` -> ``(title, target)``; a bare target gives ``(None, target)``."""
    text = text.strip()
    if text.endswith(">") and " <" in text:
        title, _, target = text[:-1].rpartition(" <")
        return title.strip(), target.strip()
    return None, text


class RepoRole(SphinxRole):
    def run(self):
        title, target = _split(self.text)
        short = target.startswith("~")
        target = target.lstrip("~")
        path, _, fragment = target.partition("#")
        url = repo_url(path, fragment)
        problem = fragment_error(path, fragment) if url is not None else None
        if problem is not None:
            logger.warning(
                "{repo} target %r: %s", target, problem, location=self.get_location(),
                type="repo", subtype="fragment",
            )  # fmt: skip
        sub = submodule(path) if url is None else None
        if sub is not None:
            logger.warning(
                "{repo} target %r is the git submodule %s (a gitlink: GitHub has no page for it "
                "in this repository); %s",
                path, sub[0], submodule_hint(sub), location=self.get_location(),
                type="repo", subtype="submodule",
            )  # fmt: skip
            url = f"{GITHUB}/tree/{git_ref()}/{path}"
        elif url is None:
            logger.warning(
                "{repo} target %r is not a file or directory tracked by git (missing, misspelt "
                "or git-ignored)",
                path,
                location=self.get_location(),
                type="repo",
                subtype="missing",
            )
            url = f"{GITHUB}/blob/{git_ref()}/{path}"
        if title is not None:
            inner = nodes.Text(title)
        else:
            shown = path.rstrip("/").rsplit("/", 1)[-1] if short else path
            inner = nodes.literal(shown, shown)
        ref = nodes.reference("", "", inner, refuri=url, classes=["repo-link"])
        return [ref], []


class TestRole(SphinxRole):
    def run(self):
        title, target = _split(self.text)
        path, sep, name = target.partition("::")
        lines = test_lines(path, name) if sep else []
        line = lines[0] if len(lines) == 1 else None
        if line is None:
            logger.warning(
                "{test} target %r: %s function %r in a tracked file %r (use path::test_name)",
                target,
                f"{len(lines)} definitions (lines {lines}) of the" if lines else "no",
                name,
                path,
                location=self.get_location(),
                type="repo",
                subtype="missing",
            )
            url = f"{GITHUB}/blob/{git_ref()}/{path}"
        else:
            url = f"{GITHUB}/blob/{git_ref()}/{path}#L{line}"
        inner = nodes.Text(title) if title is not None else nodes.literal(name, name)
        ref = nodes.reference("", "", inner, refuri=url, classes=["repo-link"])
        return [ref], []


def setup(app):
    app.add_role("repo", RepoRole())
    app.add_role("test", TestRole())
    return {"parallel_read_safe": True, "parallel_write_safe": True, "version": "1"}
