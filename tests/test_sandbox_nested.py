# SPDX-License-Identifier: Apache-2.0
"""sandbox.run inside the sandbox: the command runs directly in the enclosing container.

A ``spice-job`` runs as one sandboxed container and calls ``simulate`` from inside it; there is
no Docker in the image, so ``sandbox.run`` must execute the command itself (with ``out_dir`` as
working directory) under the enclosing container's limits. These tests use harmless shell
commands, never a simulator.
"""

import pytest

from gf180tcad import sandbox


@pytest.fixture
def inside(monkeypatch):
    monkeypatch.setenv(sandbox.IN_SANDBOX_ENV, "1")


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


def test_marker_must_be_exactly_one(monkeypatch, tmp_path):
    monkeypatch.setenv(sandbox.IN_SANDBOX_ENV, "yes")
    with pytest.raises(ValueError, match=sandbox.IN_SANDBOX_ENV):
        sandbox.run(["true"], out_dir=tmp_path)
