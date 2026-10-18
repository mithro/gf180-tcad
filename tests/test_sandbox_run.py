# SPDX-License-Identifier: Apache-2.0
"""tools/sandbox-run guards, run against fake ``docker`` and ``systemctl`` on PATH.

No container starts here: the fake ``docker`` records its arguments, and the fake ``systemctl``
prints the slice properties a test gives it. The real container is covered by
tests/sandbox/test_limits.py.
"""

import itertools
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from git_worktree import GIT_VARS, make_worktree

from gf180tcad import sandbox

SANDBOX_RUN = sandbox.SANDBOX_RUN
SANDBOX_SETUP = sandbox.REPO_ROOT / "tools" / "sandbox-setup"
GOOD_SLICE = "MemoryMax=137438953472\nMemorySwapMax=0\nTasksMax=32768\n"
UNSET_SLICE = "MemoryMax=infinity\nMemorySwapMax=infinity\nTasksMax=infinity\n"


REAL_GETENT = shutil.which("getent")


@pytest.fixture
def fakes(tmp_path):
    """A PATH with fake docker/systemctl/getent; returns a runner of tools/sandbox-run.

    The fake getent passes through to the real one unless ``FAKE_GETENT_OUT`` is set.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    docker_log = tmp_path / "docker.args"
    (bindir / "docker").write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$FAKE_DOCKER_LOG"\nexit 0\n', encoding="utf-8"
    )
    (bindir / "systemctl").write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$*" > "$FAKE_SYSTEMCTL_LOG"\n'
        'printf \'%s\' "$FAKE_SYSTEMCTL_OUT"\nexit "${FAKE_SYSTEMCTL_RC:-0}"\n',
        encoding="utf-8",
    )
    (bindir / "getent").write_text(
        '#!/bin/sh\nif [ -n "${FAKE_GETENT_RC:-}" ]; then exit "$FAKE_GETENT_RC"; fi\n'
        'if [ -n "${FAKE_GETENT_OUT:-}" ]; then printf \'%s\\n\' "$FAKE_GETENT_OUT"; exit 0; fi\n'
        f'exec {REAL_GETENT} "$@"\n',
        encoding="utf-8",
    )
    for f in bindir.iterdir():
        f.chmod(0o755)

    def run(workdir, *, slice_out=GOOD_SLICE, rc=0, home=None, script=SANDBOX_RUN, env=None):
        full = {
            **os.environ,
            "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_SYSTEMCTL_LOG": str(tmp_path / "systemctl.args"),
            "FAKE_SYSTEMCTL_OUT": slice_out,
            "FAKE_SYSTEMCTL_RC": str(rc),
        }
        if home is not None:
            full["HOME"] = str(home)
        for k, v in (env or {}).items():
            if v is None:
                full.pop(k, None)
            else:
                full[k] = v
        if docker_log.exists():
            docker_log.unlink()
        res = subprocess.run(
            [str(script), "--workdir", str(workdir), "--", "true"],
            capture_output=True,
            text=True,
            check=False,
            env=full,
        )
        args = docker_log.read_text(encoding="utf-8").splitlines() if docker_log.exists() else None
        return res, args

    return run


# --- workdir -------------------------------------------------------------------------------


def _refused(res, args):
    assert res.returncode == 2, res.stderr
    assert args is None, "docker must not run"


def test_root_is_refused(fakes):
    res, args = fakes("/")
    _refused(res, args)
    assert "filesystem root" in res.stderr


def test_home_is_refused(fakes, tmp_path):
    home = tmp_path / "home"  # not an ancestor of the repo: the $HOME rule on its own
    home.mkdir()
    res, args = fakes(home, home=home)
    _refused(res, args)
    assert "HOME" in res.stderr


@pytest.mark.parametrize("up", [1, 2])
def test_ancestor_of_the_repo_is_refused(fakes, up):
    res, args = fakes(sandbox.REPO_ROOT.parents[up - 1])
    _refused(res, args)
    assert "ancestor" in res.stderr


def test_ancestor_given_through_a_symlink_is_refused(fakes, tmp_path):
    link = tmp_path / "up"
    link.symlink_to(sandbox.REPO_ROOT.parent)
    res, args = fakes(link)
    _refused(res, args)
    assert "ancestor" in res.stderr


def test_repo_and_inside_still_refused(fakes):
    for d in (sandbox.REPO_ROOT, sandbox.REPO_ROOT / "tests"):
        res, args = fakes(d)
        _refused(res, args)
        assert "inside" in res.stderr


def test_scratch_dir_is_allowed(fakes, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    res, args = fakes(work)
    assert res.returncode == 0, res.stderr
    assert f"{work.resolve()}:/work/out:rw" in args


def test_sibling_of_the_repo_is_allowed(fakes):
    # A sibling whose name starts with the repo's own name (like gf180-tcad-worktrees next to
    # gf180-tcad): a plain string-prefix test would wrongly call it "inside the repo".
    sib = Path(tempfile.mkdtemp(prefix=sandbox.REPO_ROOT.name + "-", dir=sandbox.REPO_ROOT.parent))
    try:
        res, args = fakes(sib)
        assert res.returncode == 0, res.stderr
        assert f"{sib.resolve()}:/work/out:rw" in args
    finally:
        shutil.rmtree(sib)


# --- $HOME fallback -------------------------------------------------------------------------


@pytest.mark.parametrize("home", [None, "/nonexistent/gf180tcad-home"], ids=["unset", "missing"])
def test_home_falls_back_to_the_passwd_entry(fakes, tmp_path, home):
    passwd_home = tmp_path / "pwhome"
    passwd_home.mkdir()
    env = {"HOME": home, "FAKE_GETENT_OUT": f"u:x:1000:1000::{passwd_home}:/bin/sh"}
    res, args = fakes(passwd_home, env=env)
    _refused(res, args)
    assert "HOME" in res.stderr
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    res, args = fakes(scratch, env=env)
    assert res.returncode == 0, res.stderr


@pytest.mark.parametrize(
    "env",
    [
        {"HOME": None, "FAKE_GETENT_RC": "2"},
        {"HOME": None, "FAKE_GETENT_OUT": "u:x:1000:1000::/nonexistent/x:/bin/sh"},
        {"HOME": None, "FAKE_GETENT_OUT": "garbage"},
    ],
    ids=["getent-fails", "passwd-home-missing", "garbage"],
)
def test_home_unknown_fails_closed(fakes, tmp_path, env):
    res, args = fakes(tmp_path, env=env)
    _refused(res, args)
    assert "home directory" in res.stderr


def test_home_unset_with_the_real_passwd_entry_runs(fakes, tmp_path):
    res, args = fakes(tmp_path, env={"HOME": None})
    assert res.returncode == 0, res.stderr
    assert args is not None


# --- git worktree: the common dir is outside the repo ------------------------------------


GIT_CLEAN_ENV = dict.fromkeys(GIT_VARS)


@pytest.fixture
def worktree(tmp_path):
    """A main checkout with a linked worktree ``wt`` that holds a copy of tools/sandbox-run."""
    main, wt = make_worktree(tmp_path)
    (wt / "tools").mkdir()
    shutil.copy2(SANDBOX_RUN, wt / "tools" / "sandbox-run")
    (wt / "docker").mkdir()
    shutil.copy2(sandbox.REPO_ROOT / "docker" / "IMAGE", wt / "docker" / "IMAGE")
    return main, wt


@pytest.mark.parametrize(
    "rel", ["main", "main/.git", "main/.git/hooks", "main/.git/worktrees/wt", "main/sub"]
)
def test_git_common_dir_and_main_checkout_refused(fakes, worktree, rel):
    main, wt = worktree
    target = main.parent / rel
    target.mkdir(parents=True, exist_ok=True)
    res, args = fakes(target, script=wt / "tools" / "sandbox-run", env=GIT_CLEAN_ENV)
    _refused(res, args)
    assert "git" in res.stderr or "checkout" in res.stderr


def test_sibling_scratch_dir_of_a_worktree_allowed(fakes, worktree):
    main, wt = worktree
    scratch = main.parent / "scratch"
    scratch.mkdir()
    res, args = fakes(scratch, script=wt / "tools" / "sandbox-run", env=GIT_CLEAN_ENV)
    assert res.returncode == 0, res.stderr
    assert f"{scratch}:/work/out:rw" in args


def test_misleading_git_environment_is_ignored(fakes, worktree, tmp_path):
    main, wt = worktree
    decoy = tmp_path / "decoy.git"
    decoy.mkdir()
    env = {"GIT_DIR": str(decoy), "GIT_COMMON_DIR": str(decoy)}
    res, args = fakes(main / ".git" / "hooks", script=wt / "tools" / "sandbox-run", env=env)
    _refused(res, args)


def test_broken_git_checkout_fails_closed(fakes, worktree, tmp_path):
    _, wt = worktree
    (wt / ".git").write_text("gitdir: /nonexistent/gf180tcad\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    res, args = fakes(scratch, script=wt / "tools" / "sandbox-run", env=GIT_CLEAN_ENV)
    _refused(res, args)
    assert "git" in res.stderr


def test_git_missing_fails_closed(fakes, worktree, tmp_path):
    _, wt = worktree
    nogit = tmp_path / "nogit"
    nogit.mkdir()
    for tool in ("bash", "cat", "head", "id", "dirname", "sort", "getent", "cut", "basename"):
        found = shutil.which(tool)
        if found:
            (nogit / tool).symlink_to(found)
    bindir = tmp_path / "bin"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    env = {**GIT_CLEAN_ENV, "PATH": f"{bindir}{os.pathsep}{nogit}"}
    res, args = fakes(scratch, script=wt / "tools" / "sandbox-run", env=env)
    _refused(res, args)
    assert "git" in res.stderr


# --- container flags -----------------------------------------------------------------------


def test_container_drops_capabilities_and_privilege_escalation(fakes, tmp_path):
    res, args = fakes(tmp_path)
    assert res.returncode == 0, res.stderr
    pairs = list(itertools.pairwise(args))
    assert ("--cap-drop", "ALL") in pairs
    assert ("--security-opt", "no-new-privileges") in pairs
    assert ("--network", "none") in pairs
    assert "--cgroup-parent=gf180-tcad.slice" in args


# --- the slice ------------------------------------------------------------------------------


def test_slice_with_the_setup_limits_runs(fakes, tmp_path):
    res, args = fakes(tmp_path)
    assert res.returncode == 0, res.stderr
    assert args is not None
    asked = (tmp_path / "systemctl.args").read_text(encoding="utf-8")
    assert "show gf180-tcad.slice" in asked


def test_slice_property_order_does_not_matter(fakes, tmp_path):
    out = "TasksMax=32768\nMemorySwapMax=0\nMemoryMax=137438953472\n"
    res, args = fakes(tmp_path, slice_out=out)
    assert res.returncode == 0, res.stderr
    assert args is not None


@pytest.mark.parametrize(
    "out",
    [
        UNSET_SLICE,  # sandbox-setup never ran: docker would create an unlimited slice
        GOOD_SLICE.replace("137438953472", "68719476736"),
        GOOD_SLICE.replace("MemorySwapMax=0", "MemorySwapMax=infinity"),
        GOOD_SLICE.replace("32768", "4096"),
        "MemoryMax=137438953472\nTasksMax=32768\n",  # a property missing
        GOOD_SLICE + "MemoryMax=infinity\n",  # a property twice
        "",
        "garbage\n",
    ],
    ids=["unset", "memory", "swap", "tasks", "missing", "duplicate", "empty", "garbage"],
)
def test_slice_without_the_setup_limits_is_refused(fakes, tmp_path, out):
    res, args = fakes(tmp_path, slice_out=out)
    _refused(res, args)
    assert "gf180-tcad.slice" in res.stderr and "tools/sandbox-setup" in res.stderr


def test_systemctl_failure_is_refused(fakes, tmp_path):
    res, args = fakes(tmp_path, rc=1)
    _refused(res, args)
    assert "gf180-tcad.slice" in res.stderr


def _setup_limits() -> dict[str, str]:
    text = SANDBOX_SETUP.read_text(encoding="utf-8")
    body = text.split("[Slice]\n", 1)[1].split("'", 1)[0]
    return dict(line.split("=", 1) for line in body.splitlines() if line)


def _run_limits() -> dict[str, str]:
    text = SANDBOX_RUN.read_text(encoding="utf-8")
    m = re.search(r'^SLICE_LIMITS="([^"]*)"', text, re.MULTILINE)
    assert m, "tools/sandbox-run has no SLICE_LIMITS line"
    return dict(item.split("=", 1) for item in m.group(1).split())


def test_checked_limits_are_the_ones_sandbox_setup_writes():
    units = {"G": 1 << 30}
    want = {}
    for k, v in _setup_limits().items():
        want[k] = str(int(v[:-1]) * units[v[-1]]) if v[-1] in units else v
    assert want == _run_limits() == dict(line.split("=") for line in GOOD_SLICE.split())
