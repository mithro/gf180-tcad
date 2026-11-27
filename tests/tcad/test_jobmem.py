# SPDX-License-Identifier: Apache-2.0
"""The memory budget of a 2D sweep job (gf180tcad.tcad.jobmem, issue #233) and its restart.

Host tests: the readings come from fake /proc and cgroup files, and the restart of
:func:`gf180tcad.tcad.__main__.run_job_2d` is checked with a fake sweep and a fake ``execve``.
"""

import os
import platform
import sys

import pytest

from gf180tcad.tcad import __main__ as cli
from gf180tcad.tcad import jobmem, moscap2d
from gf180tcad.tcad.mesh import MeshSpec

GIB = 1 << 30


def test_rss_bytes(tmp_path):
    status = tmp_path / "status"
    status.write_text("Name:\tpython3\nVmPeak:\t  9 kB\nVmRSS:\t  2048 kB\n", encoding="utf-8")
    assert jobmem.rss_bytes(status) == 2048 * 1024
    status.write_text("Name:\tpython3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no VmRSS"):
        jobmem.rss_bytes(status)


def test_rss_bytes_of_this_process():
    assert jobmem.rss_bytes() > 0


@pytest.mark.parametrize(
    ("text", "want"),
    [("17179869184\n", 16 * GIB), ("max\n", None), ("9223372036854771712\n", None)],
)
def test_limit_bytes(tmp_path, text, want):
    v2, v1 = tmp_path / "memory.max", tmp_path / "memory.limit_in_bytes"
    v2.write_text(text, encoding="utf-8")
    assert jobmem.limit_bytes((v2, v1)) == want
    v2.unlink()
    v1.write_text(text, encoding="utf-8")  # cgroup v1: no limit is a huge number
    assert jobmem.limit_bytes((v2, v1)) == want


def test_limit_bytes_without_cgroup_files(tmp_path):
    assert jobmem.limit_bytes((tmp_path / "a", tmp_path / "b")) is None


@pytest.mark.skipif(platform.libc_ver()[0] != "glibc", reason="malloc_trim is glibc's")
def test_trim_on_glibc():
    """On glibc the trim is there, and it hands back the pages of freed heap blocks."""
    assert jobmem._malloc_trim() is not None
    before = jobmem.rss_bytes()
    # 4096 blocks of under 64 KiB (below the mmap threshold, so on the heap), all touched,
    # then all freed but the last, which pins the heap top: free() keeps the pages resident
    # and only malloc_trim hands them back
    blocks = [bytearray(64 * 1024 - 64) for _ in range(4096)]
    assert jobmem.rss_bytes() - before > 128 * 1024 * 1024
    del blocks[:-1]
    freed = jobmem.trim()
    assert freed is not None and freed > 64 * 1024 * 1024, freed


def test_trim_without_malloc_trim(monkeypatch):
    monkeypatch.setattr(jobmem, "_malloc_trim", lambda: None)
    assert jobmem.trim() is None


def test_rss_bytes_without_status_file(tmp_path):
    assert jobmem.rss_bytes(tmp_path / "missing") is None


def test_over_budget():
    limit = 16 * GIB
    # the issue #233 job: 4 GiB after its first point, growing 0.2 GiB per point
    assert not jobmem.over_budget(11 * GIB, 4 * GIB, limit)
    assert jobmem.over_budget(13 * GIB, 4 * GIB, limit)
    # high from the start: a restart would not help, so none
    assert not jobmem.over_budget(13 * GIB, 12 * GIB, limit)
    assert not jobmem.over_budget(15 * GIB, 4 * GIB, None)


@pytest.fixture
def readings(monkeypatch):
    """after_point with fake readings: set ``rss`` (a list, one value per call) and ``limit``."""
    state = {"rss": [], "limit": 16 * GIB, "trim": 3 << 20}
    monkeypatch.setattr(jobmem, "_first_rss", None)
    monkeypatch.setattr(jobmem, "trim", lambda: state["trim"])
    monkeypatch.setattr(jobmem, "rss_bytes", lambda: state["rss"].pop(0))
    monkeypatch.setattr(jobmem, "limit_bytes", lambda: state["limit"])
    return state


def test_after_point_logs_and_raises_on_growth(readings):
    lines = []
    readings["rss"] = [4 * GIB, 8 * GIB, 13 * GIB]
    jobmem.after_point(0, last=False, log=lines.append)
    jobmem.after_point(1, last=False, log=lines.append)
    with pytest.raises(jobmem.BudgetReached, match="after point 3") as e:
        jobmem.after_point(2, last=False, log=lines.append)
    assert e.value.index == 2
    assert lines[0] == "memory after point 1: rss 4096 MiB, trim freed 3 MiB, limit 16384 MiB"
    assert len(lines) == 3


def test_after_point_never_raises_after_the_last_point(readings):
    readings["rss"] = [4 * GIB, 15 * GIB]
    jobmem.after_point(0, last=False)
    jobmem.after_point(1, last=True)


def test_after_point_without_limit(readings):
    lines = []
    readings["rss"], readings["limit"] = [4 * GIB, 60 * GIB], None
    jobmem.after_point(0, last=False, log=lines.append)
    jobmem.after_point(1, last=False, log=lines.append)
    assert lines[1].endswith("no limit")


def test_after_point_without_readings(readings):
    """Without malloc_trim or /proc/self/status the line says so and the budget is skipped."""
    lines = []
    readings["rss"], readings["trim"] = [None, None], None
    jobmem.after_point(0, last=False, log=lines.append)
    jobmem.after_point(1, last=False, log=lines.append)
    assert lines[0] == "memory after point 1: rss unavailable, trim unavailable, limit 16384 MiB"


class _Exec(Exception):
    pass


@pytest.fixture
def restart(tmp_path, monkeypatch):
    """run_job_2d with a sweep that reaches the budget and an execve that records its call."""
    monkeypatch.setattr(cli.meshconv, "selected_spec", lambda d, dim: MeshSpec.DEFAULT_2D)

    def simulate(*args, **kwargs):
        raise jobmem.BudgetReached(41, 13 * GIB, 16 * GIB)

    calls = []

    def execve(path, argv, env):
        calls.append((path, argv, env))
        raise _Exec

    monkeypatch.setattr(moscap2d, "simulate", simulate)
    monkeypatch.setattr(os, "execve", execve)
    monkeypatch.delenv(cli.RESTARTS_ENV, raising=False)
    out = tmp_path / "job"
    out.mkdir()
    return out, calls


def test_budget_restarts_the_sweep_in_a_fresh_process(restart):
    """The sweep is replaced by ``moscap-job --method qs`` on the same scratch dir, with the
    restart counted in the environment and logged in the progress log."""
    out, calls = restart
    with pytest.raises(_Exec):
        cli.run_job_2d("nfet_05v0", "start", "w10p0_l0p60", out, method="qs")
    ((path, argv, env),) = calls
    assert path == sys.executable
    assert argv == [
        sys.executable, "-m", "gf180tcad.tcad", "moscap-job", "--device", "nfet_05v0",
        "--dim", "2", "--params", "start", "--geometry", "w10p0_l0p60", "--out", str(out),
        "--method", "qs",
    ]  # fmt: skip
    assert env[cli.RESTARTS_ENV] == "1"
    log = (out / "progress_qs.log").read_text(encoding="utf-8")
    assert "restart 1 in a fresh process" in log and "after point 42" in log
    # the job command line parses to the same job
    a = cli._parser().parse_args(argv[3:])
    assert (a.command, a.device, a.dim, a.params, a.geometry, a.method) == (
        "moscap-job", "nfet_05v0", 2, "start", "w10p0_l0p60", "qs",
    )  # fmt: skip


def test_restarts_are_capped(restart, monkeypatch):
    out, calls = restart
    monkeypatch.setenv(cli.RESTARTS_ENV, str(cli.MAX_RESTARTS))
    with pytest.raises(RuntimeError, match="memory budget"):
        cli.run_job_2d("nfet_05v0", "start", "w10p0_l0p60", out, method="ac")
    assert calls == []


def test_restart_argv_hook(restart, monkeypatch):
    """The test hook replaces the restart's command (the sandbox restart test's driver)."""
    out, calls = restart
    monkeypatch.setattr(cli, "RESTART_ARGV", lambda argv, m: ["/bin/driver", m, argv[-3]])
    with pytest.raises(_Exec):
        cli.run_job_2d("nfet_05v0", "start", "w10p0_l0p60", out, method="qs")
    ((path, argv, _),) = calls
    assert (path, argv) == ("/bin/driver", ["/bin/driver", "qs", str(out)])
