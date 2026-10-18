# SPDX-License-Identifier: Apache-2.0
"""sandbox.run inside the sandbox: the command runs directly in the enclosing container.

A ``spice-job`` runs as one sandboxed container and calls ``simulate`` from inside it; there is
no Docker in the image, so ``sandbox.run`` must execute the command itself (with ``out_dir`` as
working directory) under the enclosing container's limits. These tests use harmless shell
commands, never a simulator.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from confined_root import make_confined_root

from gf180tcad import sandbox


def test_sandbox_run_sets_the_marker():
    text = sandbox.SANDBOX_RUN.read_text(encoding="utf-8")
    assert f"-e {sandbox.IN_SANDBOX_ENV}=1" in text


def test_runs_directly_in_out_dir(inside, tmp_path):
    res = sandbox.run(["sh", "-c", "pwd; echo made > f.txt"], out_dir=tmp_path)
    assert res.returncode == 0
    assert res.stdout.strip() == str(tmp_path.resolve())
    assert (tmp_path / "f.txt").read_text() == "made\n"


def test_nonzero_exit_raises(inside, tmp_path):
    with pytest.raises(sandbox.SandboxError) as exc:
        sandbox.run(["sh", "-c", "echo bad >&2; exit 3"], out_dir=tmp_path)
    assert exc.value.result.returncode == 3
    assert "bad" in exc.value.result.stderr
    assert not isinstance(exc.value, sandbox.SandboxOOM)


@pytest.mark.parametrize("cmd", ["exit 137", "kill -9 $$"])
def test_killed_is_oom(inside, tmp_path, cmd):
    with pytest.raises(sandbox.SandboxOOM) as exc:
        sandbox.run(["sh", "-c", cmd], out_dir=tmp_path)
    assert exc.value.result.returncode == sandbox.OOM_EXIT


def test_image_cannot_be_chosen_inside(inside, tmp_path):
    with pytest.raises(ValueError, match="image"):
        sandbox.run(["true"], out_dir=tmp_path, image="other@sha256:" + "0" * 64)


def test_out_dir_inside_repo_refused(inside):
    with pytest.raises(ValueError, match="repo"):
        sandbox.run(["true"], out_dir=sandbox.REPO_ROOT / "tests")


@pytest.mark.parametrize("which", ["root", "parent", "grandparent"])
def test_out_dir_that_is_an_ancestor_of_the_repo_refused(inside, which):
    where = {
        "root": Path("/"),
        "parent": sandbox.REPO_ROOT.parent,
        "grandparent": sandbox.REPO_ROOT.parents[1],
    }[which]
    with pytest.raises(ValueError, match="ancestor|root"):
        sandbox.run(["true"], out_dir=where)


def test_out_dir_that_is_home_refused(inside, monkeypatch, tmp_path):
    home = tmp_path / "home"  # not an ancestor of the repo: the $HOME rule on its own
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    with pytest.raises(ValueError, match="HOME"):
        sandbox.run(["sh", "-c", "echo ran > ran.txt"], out_dir=home)
    assert not (home / "ran.txt").exists()


def test_out_dir_next_to_the_repo_allowed(inside):
    sib = Path(tempfile.mkdtemp(prefix=sandbox.REPO_ROOT.name + "-", dir=sandbox.REPO_ROOT.parent))
    try:
        res = sandbox.run(["sh", "-c", "pwd"], out_dir=sib)
        assert res.stdout.strip() == str(sib.resolve())
    finally:
        shutil.rmtree(sib)


@pytest.mark.parametrize(
    "where, ok",
    [
        ("/", False),
        ("/home", False),
        ("/home/u", False),  # $HOME
        ("/home/u/src", False),  # ancestor of the repo
        ("/home/u/src/repo", False),
        ("/home/u/src/repo/tests", False),
        ("/home/u/src/repo-worktrees/x", True),
        ("/home/u/src/other", True),
        ("/home/u/tmp/scratch", True),
        ("/tmp/x", True),
    ],
)
def test_check_workdir_rules(where, ok):
    kw = {"repo_root": Path("/home/u/src/repo"), "home": Path("/home/u")}
    if ok:
        sandbox.check_workdir(Path(where), **kw)
    else:
        with pytest.raises(ValueError):
            sandbox.check_workdir(Path(where), **kw)


def test_marker_must_be_exactly_one(monkeypatch, tmp_path):
    monkeypatch.setenv(sandbox.IN_SANDBOX_ENV, "yes")
    with pytest.raises(ValueError, match=sandbox.IN_SANDBOX_ENV):
        sandbox.run(["true"], out_dir=tmp_path)


# --- confinement proof: the marker alone never enables direct mode ------------------------


def test_fake_confined_root_passes(tmp_path):
    sandbox.check_confined(make_confined_root(tmp_path))


def test_nested_cgroup_path_is_followed(tmp_path):
    sandbox.check_confined(make_confined_root(tmp_path, cgroup="/docker/abc"))


def _break(root: Path, case: str) -> str:
    cg = root / "sys" / "fs" / "cgroup"
    if case == "no_dockerenv":
        (root / ".dockerenv").unlink()
        return "/.dockerenv"
    if case == "memory_unlimited":
        (cg / "memory.max").write_text("max\n")
        return "memory.max"
    if case == "memory_missing":
        (cg / "memory.max").unlink()
        return "memory.max"
    if case == "pids_unlimited":
        (cg / "pids.max").write_text("max\n")
        return "pids.max"
    if case == "pids_garbage":
        (cg / "pids.max").write_text("lots\n")
        return "pids.max"
    if case == "no_cgroup_v2_line":
        (root / "proc" / "self" / "cgroup").write_text("1:memory:/\n")
        return "cgroup v2"
    if case == "no_proc_cgroup":
        (root / "proc" / "self" / "cgroup").unlink()
        return "cgroup"
    if case == "network_interface":
        (root / "sys" / "class" / "net" / "eth0").mkdir()
        return "eth0"
    if case == "no_sys_class_net":
        for p in (root / "sys" / "class" / "net").iterdir():
            p.rmdir() if p.is_dir() else p.unlink()
        (root / "sys" / "class" / "net").rmdir()
        return "/sys/class/net"
    mountinfo = root / "proc" / "self" / "mountinfo"
    if case == "no_work_src":
        (root / "work" / "src").rmdir()
        return "/work/src"
    if case == "no_mountinfo":
        mountinfo.unlink()
        return "mountinfo"
    if case == "work_src_not_a_mount":
        mountinfo.write_text("986 900 0:60 / / ro,relatime - overlay overlay rw\n")
        return "/work/src"
    if case == "work_src_rw":
        mountinfo.write_text(mountinfo.read_text().replace("/work/src ro,", "/work/src rw,"))
        return "read-only"
    if case == "work_src_remounted_rw":  # the last mount on a mount point is the visible one
        with mountinfo.open("a") as f:
            f.write("997 986 254:124 /home/u/repo /work/src rw,relatime - ext4 /dev/sda1 rw\n")
        return "read-only"
    raise AssertionError(case)


CASES = [
    "no_dockerenv", "memory_unlimited", "memory_missing", "pids_unlimited", "pids_garbage",
    "no_cgroup_v2_line", "no_proc_cgroup", "network_interface", "no_sys_class_net",
    "no_work_src", "no_mountinfo", "work_src_not_a_mount", "work_src_rw", "work_src_remounted_rw",
]  # fmt: skip


@pytest.mark.parametrize("case", CASES)
def test_each_confinement_failure_is_reported(tmp_path, case):
    root = make_confined_root(tmp_path)
    what = _break(root, case)
    with pytest.raises(sandbox.SandboxNotConfined, match="not confined") as exc:
        sandbox.check_confined(root)
    assert what in str(exc.value)
    assert isinstance(exc.value, sandbox.SandboxError)


@pytest.mark.parametrize("case", CASES)
def test_marker_with_unconfined_root_never_runs_the_command(monkeypatch, tmp_path, case):
    root = make_confined_root(tmp_path / "root")
    _break(root, case)
    monkeypatch.setenv(sandbox.IN_SANDBOX_ENV, "1")
    monkeypatch.setattr(sandbox, "CONFINEMENT_ROOT", root)
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(sandbox.SandboxNotConfined):
        sandbox.run(["sh", "-c", "echo ran > ran.txt"], out_dir=out)
    with pytest.raises(sandbox.SandboxNotConfined):
        sandbox.in_sandbox()
    assert not (out / "ran.txt").exists()


@pytest.mark.skipif(os.path.exists("/.dockerenv"), reason="the test host is itself a container")
def test_marker_on_the_real_host_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv(sandbox.IN_SANDBOX_ENV, "1")
    with pytest.raises(sandbox.SandboxNotConfined):
        sandbox.run(["sh", "-c", "echo ran > ran.txt"], out_dir=tmp_path)
    assert not (tmp_path / "ran.txt").exists()


def test_no_marker_means_not_inside(monkeypatch):
    monkeypatch.delenv(sandbox.IN_SANDBOX_ENV, raising=False)
    assert sandbox.in_sandbox() is False


# --- the real container ------------------------------------------------------------------


@pytest.mark.sandbox
def test_real_container_is_confined(tmp_path):
    code = "from gf180tcad import sandbox; sandbox.check_confined(); print(sandbox.in_sandbox())"
    res = sandbox.run(["python3", "-c", code], out_dir=tmp_path, mem="1g", cpus=1, pids=64)
    assert res.stdout.strip() == "True"


@pytest.mark.sandbox
def test_real_container_with_network_is_not_confined(tmp_path):
    code = "from gf180tcad import sandbox; sandbox.in_sandbox()"
    with pytest.raises(sandbox.SandboxError) as exc:
        sandbox.run(["python3", "-c", code], out_dir=tmp_path, network=True)
    assert "not confined" in exc.value.result.stderr
