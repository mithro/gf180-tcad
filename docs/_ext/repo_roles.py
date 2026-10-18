# SPDX-License-Identifier: Apache-2.0
"""Sphinx roles that link repository files and test functions to GitHub, checked offline.

``{repo}`path``` links ``https://github.com/mithro/gf180-tcad/blob/<ref>/path`` (``tree/`` for a
directory) and shows the path as code. ``{repo}`~path``` shows only the last path component, and
``{repo}`text <path>``` shows ``text`` as plain prose. A ``#fragment`` after the path is kept in
the URL. ``{test}`tests/x.py::test_name``` links the line of that test function (found with
:mod:`ast` at build time, so the anchor cannot drift) and shows ``test_name`` as code.

Every target is checked against the checkout when the page is read: a path that is not tracked
by git (missing, misspelt or git-ignored such as ``docs/_generated/``) or a test function that
does not exist is a Sphinx warning, which ``sphinx-build -W`` (CI, Read the Docs, and
``tests/test_docgen.py::test_docs_build_offline``) turns into a build failure. No network is
used.

``<ref>`` is ``READTHEDOCS_GIT_COMMIT_HASH`` when set, else ``git rev-parse HEAD``, else ``main``.
Pinning to the commit keeps links stable and makes a file added in the same pull request resolve
before merge. It also means the HTML depends on the commit being built: two builds of the same
commit are identical.
"""

from __future__ import annotations

import ast
import functools
import os
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


def classify(path: str) -> str | None:
    """``"blob"`` for a tracked file, ``"tree"`` for a tracked directory, else None."""
    path = path.rstrip("/")
    files, dirs = tracked()
    if not files:  # no git (e.g. an sdist): fall back to the file system
        p = ROOT / path
        if "_generated" in Path(path).parts:
            return None
        return "tree" if p.is_dir() else "blob" if p.is_file() else None
    if path in files:
        return "blob"
    if path in dirs:
        return "tree"
    return None


def repo_url(path: str, fragment: str = "") -> str | None:
    kind = classify(path)
    if kind is None:
        return None
    url = f"{GITHUB}/{kind}/{git_ref()}/{path.rstrip('/')}"
    return url + (f"#{fragment}" if fragment else "")


def test_line(path: str, name: str) -> int | None:
    """Line of ``def name`` (module level or in a class) in the repository file ``path``."""
    if classify(path) != "blob":
        return None
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node.lineno
    return None


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
        if url is None:
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
        line = test_line(path, name) if sep else None
        if line is None:
            logger.warning(
                "{test} target %r: no function %r in a tracked file %r (use path::test_name)",
                target,
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
