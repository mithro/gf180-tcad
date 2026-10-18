# SPDX-License-Identifier: Apache-2.0
"""Sandbox limit tests. Need Docker and the pinned image (run with `pytest -m sandbox`)."""

import os
import subprocess
import time
from pathlib import Path

import pytest

from gf180tcad import sandbox

pytestmark = pytest.mark.sandbox


def _leftover_containers() -> list[str]:
    out = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=^gf180tcad-", "--format", "{{.Names}}"],
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
    with pytest.raises(sandbox.SandboxError) as exc:
        sandbox.run(
            ["python3", "-c", "import socket; socket.create_connection(('1.1.1.1',53),2)"],
            out_dir=tmp_path,
        )
    assert "Network is unreachable" in exc.value.result.stderr


def test_pids_limited(tmp_path):
    # 200 background sleeps cannot all start under pids=64: bash hits fork errors (or the
    # script exits 3 because fewer than 200 started).
    script = (
        "for i in $(seq 200); do sleep 30 & done; "
        'n=$(jobs -p | wc -l); kill $(jobs -p); [ "$n" -lt 200 ] && exit 3; exit 0'
    )
    with pytest.raises(sandbox.SandboxError) as exc:
        sandbox.run(["bash", "-c", script], out_dir=tmp_path, pids=64)
    res = exc.value.result
    assert res.returncode == 3 or "Resource temporarily unavailable" in res.stderr
    assert _leftover_containers() == []


def test_in_slice(tmp_path):
    proc = subprocess.Popen(
        [str(sandbox.SANDBOX_RUN), "--workdir", str(tmp_path), "--", "sleep", "30"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        names: list[str] = []
        for _ in range(100):
            names = _leftover_containers()
            if names:
                break
            time.sleep(0.2)
        assert names, "container did not start"
        pid = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Pid}}", names[0]],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        cgroup = Path(f"/proc/{pid}/cgroup").read_text()
        assert "gf180-tcad.slice" in cgroup
    finally:
        subprocess.run(["docker", "rm", "-f", *_leftover_containers()], check=False)
        proc.wait(timeout=30)
        proc.stderr.close()
    assert _leftover_containers() == []


def test_memory_limit_applied(tmp_path):
    res = sandbox.run(["cat", "/sys/fs/cgroup/memory.max"], out_dir=tmp_path, mem="1g")
    assert res.stdout.strip() == str(2**30)


def test_workdir_inside_repo_refused():
    res = subprocess.run(
        [str(sandbox.SANDBOX_RUN), "--workdir", str(sandbox.REPO_ROOT / "tests"), "--", "true"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 2
    assert "inside" in res.stderr


def test_workdir_required():
    res = subprocess.run(
        [str(sandbox.SANDBOX_RUN), "--", "true"], capture_output=True, text=True, check=False
    )
    assert res.returncode == 2
    assert "--workdir is required" in res.stderr


def test_outputs_owned_by_user(tmp_path):
    sandbox.run(["sh", "-c", "echo hi > /work/out/f.txt"], out_dir=tmp_path)
    assert (tmp_path / "f.txt").stat().st_uid == os.getuid()


def test_stdout_is_clean(tmp_path):
    res = sandbox.run(["echo", "hello"], out_dir=tmp_path)
    assert res.stdout == "hello\n"


def test_network_opt_in_flag_accepted(tmp_path):
    res = sandbox.run(["cat", "/proc/net/dev"], out_dir=tmp_path, network=True)
    assert "eth0" in res.stdout


def test_no_capabilities_and_no_new_privileges(tmp_path):
    res = sandbox.run(["cat", "/proc/self/status"], out_dir=tmp_path)
    status = dict(line.split(":\t", 1) for line in res.stdout.splitlines() if ":\t" in line)
    for cap in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
        assert status[cap].strip() == "0" * 16, (cap, status[cap])
    assert status["NoNewPrivs"].strip() == "1"
