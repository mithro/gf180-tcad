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

from gf180tcad import sandbox

SANDBOX_RUN = sandbox.SANDBOX_RUN
SANDBOX_SETUP = sandbox.REPO_ROOT / "tools" / "sandbox-setup"
GOOD_SLICE = "MemoryMax=137438953472\nMemorySwapMax=0\nTasksMax=32768\n"
UNSET_SLICE = "MemoryMax=infinity\nMemorySwapMax=infinity\nTasksMax=infinity\n"


@pytest.fixture
def fakes(tmp_path):
    """A PATH with fake docker/systemctl; returns a runner of tools/sandbox-run."""
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
    for f in bindir.iterdir():
        f.chmod(0o755)

    def run(workdir, *, slice_out=GOOD_SLICE, rc=0, home=None):
        env = {
            **os.environ,
            "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_SYSTEMCTL_LOG": str(tmp_path / "systemctl.args"),
            "FAKE_SYSTEMCTL_OUT": slice_out,
            "FAKE_SYSTEMCTL_RC": str(rc),
        }
        if home is not None:
            env["HOME"] = str(home)
        if docker_log.exists():
            docker_log.unlink()
        res = subprocess.run(
            [str(SANDBOX_RUN), "--workdir", str(workdir), "--", "true"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
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
