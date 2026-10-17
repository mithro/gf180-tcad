# SPDX-License-Identifier: Apache-2.0
"""Sandbox limit tests. Need Docker and the pinned image (run with `pytest -m sandbox`)."""

import os
import subprocess

import pytest

from gf180tcad import sandbox

pytestmark = pytest.mark.sandbox


def _leftover_containers() -> list[str]:
    out = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=gf180tcad-", "--format", "{{.Names}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.split()


def test_oom_is_reported(tmp_path):
    with pytest.raises(sandbox.SandboxOOM):
        sandbox.run(
            ["python3", "-c", "b=bytearray(3*2**30); b[::4096]=b'x'*len(b[::4096])"],
            out_dir=tmp_path,
            mem="1g",
        )
    assert _leftover_containers() == []


def test_network_disabled(tmp_path):
    with pytest.raises(sandbox.SandboxError):
        sandbox.run(
            ["python3", "-c", "import socket; socket.create_connection(('1.1.1.1',53),2)"],
            out_dir=tmp_path,
        )


def test_pids_limited(tmp_path):
    # 200 background sleeps cannot all start under pids=64; the script exits 3 if they did.
    script = (
        "for i in $(seq 200); do sleep 30 & done; "
        'n=$(jobs -p | wc -l); kill $(jobs -p); [ "$n" -lt 200 ] && exit 3; exit 0'
    )
    with pytest.raises(sandbox.SandboxError):
        sandbox.run(["bash", "-c", script], out_dir=tmp_path, pids=64)
    assert _leftover_containers() == []


def test_in_slice(tmp_path):
    res = sandbox.run(["cat", "/proc/self/cgroup"], out_dir=tmp_path)
    assert "gf180-tcad.slice" in res.stdout


def test_outputs_owned_by_user(tmp_path):
    sandbox.run(["sh", "-c", "echo hi > /work/out/f.txt"], out_dir=tmp_path)
    assert (tmp_path / "f.txt").stat().st_uid == os.getuid()


def test_stdout_is_clean(tmp_path):
    res = sandbox.run(["echo", "hello"], out_dir=tmp_path)
    assert res.stdout == "hello\n"


def test_network_opt_in_flag_accepted(tmp_path):
    res = sandbox.run(["cat", "/proc/net/dev"], out_dir=tmp_path, network=True)
    assert "eth0" in res.stdout
