# SPDX-License-Identifier: Apache-2.0
"""The local gate in front of CI: tools/install-hooks and the pre-push hook it installs.

Each test runs git in a fresh repository under ``tmp_path``, never in this checkout: installing
the hook writes the clone's shared git config.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "tools" / "install-hooks"
HOOK = ROOT / "tools" / "git-hooks" / "pre-push"
ZERO = "0" * 40

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo, env=_env(), capture_output=True, text=True, check=True,
    )  # fmt: skip


def _repo(tmp_path: Path, pre_push_recipe: str = "true") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "Makefile").write_text(
        f"pre-push:\n\t@{pre_push_recipe}\npre-push-docs:\n\t@touch ../docs-ran\n", encoding="utf-8"
    )
    _git(repo, "add", "Makefile")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _install(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INSTALL), *args],
        cwd=repo, env=_env(), capture_output=True, text=True, check=False,
    )  # fmt: skip


def _hook(repo: Path, stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(HOOK), "origin", "git@example.com:x.git"],
        cwd=repo, env=_env(), input=stdin, capture_output=True, text=True, check=False,
    )  # fmt: skip


def _push_line(repo: Path, remote: str = ZERO) -> str:
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return f"refs/heads/b {head} refs/heads/b {remote}\n"


def _commit(repo: Path, path: str) -> str:
    """Commit a new file at ``path``; returns the commit before it (the remote's old tip)."""
    before = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text("x\n", encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", path)
    return before


def test_install_sets_hooks_path_idempotently(tmp_path):
    repo = _repo(tmp_path)
    assert _install(repo, "--check").returncode == 1
    for _ in range(2):
        r = _install(repo)
        assert r.returncode == 0, r.stderr
    assert _git(repo, "config", "--get", "core.hooksPath").stdout.strip() == "tools/git-hooks"
    assert _install(repo, "--check").returncode == 0


def test_install_refuses_to_replace_another_hooks_path(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "config", "core.hooksPath", "elsewhere")
    r = _install(repo)
    assert r.returncode == 2 and "elsewhere" in r.stderr
    assert _git(repo, "config", "--get", "core.hooksPath").stdout.strip() == "elsewhere"


def test_hook_covers_worktrees(tmp_path):
    """A relative core.hooksPath resolves in each worktree to that worktree's tools/git-hooks."""
    repo = _repo(tmp_path)
    hooks = repo / "tools" / "git-hooks"
    hooks.mkdir(parents=True)
    shutil.copy2(HOOK, hooks / "pre-push")
    _git(repo, "add", "tools")
    _git(repo, "commit", "-q", "-m", "hooks")
    assert _install(repo).returncode == 0
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", "other", str(wt))
    r = _git(wt, "rev-parse", "--git-path", "hooks")
    assert (wt / r.stdout.strip()).resolve() == (wt / "tools" / "git-hooks").resolve()


def test_hook_passes_when_make_pre_push_passes(tmp_path):
    repo = _repo(tmp_path, "true")
    r = _hook(repo, _push_line(repo))
    assert r.returncode == 0, r.stderr


def test_hook_refuses_when_make_pre_push_fails(tmp_path):
    repo = _repo(tmp_path, "false")
    r = _hook(repo, _push_line(repo))
    assert r.returncode == 1
    assert "refused" in r.stderr


def test_hook_skips_a_deletion_only_push(tmp_path):
    repo = _repo(tmp_path, "false")
    r = _hook(repo, f"(delete) {ZERO} refs/heads/b {'1' * 40}\n")
    assert r.returncode == 0, r.stderr


def test_hook_notes_a_working_tree_that_differs(tmp_path):
    repo = _repo(tmp_path, "true")
    with (repo / "Makefile").open("a", encoding="utf-8") as f:
        f.write("# edited\n")
    r = _hook(repo, _push_line(repo))
    assert r.returncode == 0 and "differs from the pushed commit" in r.stderr


@pytest.mark.parametrize(
    ("path", "docs"),
    [("docs/x.md", True), ("README.md", True), ("src/m.py", True), ("results/r.csv", True),
     ("tests/t.py", False), ("tools/t", False)],
)  # fmt: skip
def test_hook_runs_the_docs_check_only_for_docs_inputs(tmp_path, path, docs):
    repo = _repo(tmp_path)
    before = _commit(repo, path)
    r = _hook(repo, _push_line(repo, before))
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "docs-ran").exists() == docs


def test_hook_runs_the_docs_check_when_the_base_is_unknown(tmp_path):
    """A new branch with no origin/main to compare against: everything is checked."""
    repo = _repo(tmp_path)
    r = _hook(repo, _push_line(repo))
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "docs-ran").exists()


def test_make_pre_push_runs_make_lint_first():
    if shutil.which("make") is None:
        pytest.skip("make is not installed")
    r = subprocess.run(
        ["make", "--no-print-directory", "-n", "pre-push"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )  # fmt: skip
    lines = r.stdout.splitlines()
    assert lines[:2] == ["uv run --locked ruff check", "uv run --locked ruff format --check"]
    assert any("pytest" in ln for ln in lines[2:]), lines
