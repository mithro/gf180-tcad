# SPDX-License-Identifier: Apache-2.0
"""Python wrapper over ``tools/sandbox-run``: every simulator run goes through here.

Nesting: ``tools/sandbox-run`` sets ``GF180TCAD_IN_SANDBOX=1`` in the container. Code that
already runs inside the sandbox (e.g. ``python -m gf180tcad spice-job``, which calls the SPICE
runners) has no Docker, so :func:`run` then executes the command directly, with ``out_dir`` as
working directory, under the enclosing container's memory, CPU, PID and network limits; the
``mem``/``cpus``/``pids``/``network`` arguments do not apply and ``image`` must be None.

The marker alone never enables this direct mode: :func:`check_confined` must also prove that
the process is confined (``/.dockerenv`` exists, the cgroup v2 ``memory.max`` and ``pids.max``
are finite, ``/work/src`` is mounted read-only and ``/sys/class/net`` lists no interface but
``lo``). If the marker is set and any of these fails, :class:`SandboxNotConfined` is raised;
there is no fallback.
"""

import os
import signal
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_RUN = REPO_ROOT / "tools" / "sandbox-run"
OOM_EXIT = 137
IN_SANDBOX_ENV = "GF180TCAD_IN_SANDBOX"


CONFINEMENT_ROOT = Path("/")  # filesystem root inspected by check_confined (tests use a fake)


def in_sandbox() -> bool:
    """True inside a confined ``tools/sandbox-run`` container.

    False if ``GF180TCAD_IN_SANDBOX`` is unset. If it is ``1``, :func:`check_confined` must
    pass, else :class:`SandboxNotConfined` is raised; any other value raises ValueError.
    """
    value = os.environ.get(IN_SANDBOX_ENV)
    if value is None:
        return False
    if value != "1":
        raise ValueError(f"{IN_SANDBOX_ENV} must be unset or '1', got {value!r}")
    check_confined()
    return True


def _finite_limit(path: Path, problems: list[str]) -> None:
    name = path.name
    try:
        text = path.read_text(encoding="ascii").strip()
    except OSError as e:
        problems.append(f"cgroup {name} is unreadable ({path}): {e}")
        return
    if text == "max":
        problems.append(f"cgroup {name} is 'max' (unlimited)")
    elif not (text.isascii() and text.isdigit()):
        problems.append(f"cgroup {name} is not a number: {text!r}")


SOURCE_MOUNT = "/work/src"  # where tools/sandbox-run mounts the repo, read-only


def _source_read_only(root: Path, problems: list[str]) -> None:
    """``/work/src`` exists and its visible (last) mount in mountinfo has the ``ro`` option."""
    if not (root / SOURCE_MOUNT.lstrip("/")).is_dir():
        problems.append(f"{SOURCE_MOUNT} is missing")
        return
    try:
        lines = (root / "proc" / "self" / "mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError as e:
        problems.append(f"/proc/self/mountinfo is unreadable: {e}")
        return
    # fields: id parent major:minor root mount-point mount-options ... - fstype source super-opts
    mounts = [f for f in (ln.split() for ln in lines) if len(f) > 5 and f[4] == SOURCE_MOUNT]
    if not mounts:
        problems.append(f"{SOURCE_MOUNT} is not a mount point in /proc/self/mountinfo")
    elif "ro" not in mounts[-1][5].split(","):
        problems.append(f"{SOURCE_MOUNT} is not mounted read-only (options {mounts[-1][5]})")


def check_confined(root: Path | None = None) -> None:
    """Raise :class:`SandboxNotConfined` unless the process is confined like a sandbox container.

    Checks, all relative to ``root`` (default :data:`CONFINEMENT_ROOT`, i.e. ``/``):

    - ``/.dockerenv`` exists;
    - ``/proc/self/cgroup`` has a cgroup v2 line (``0::<path>``), and ``memory.max`` and
      ``pids.max`` of that cgroup under ``/sys/fs/cgroup`` are finite numbers (not ``max``);
    - ``/work/src`` (the repo) exists and its visible mount in ``/proc/self/mountinfo`` has the
      ``ro`` option;
    - ``/sys/class/net`` exists and has no network interface (directory entry) but ``lo``.

    Every failed check is listed in the error.
    """
    root = Path(root) if root is not None else CONFINEMENT_ROOT
    problems: list[str] = []
    if not (root / ".dockerenv").is_file():
        problems.append("/.dockerenv is missing")
    try:
        lines = (root / "proc" / "self" / "cgroup").read_text(encoding="utf-8").splitlines()
    except OSError as e:
        lines = None
        problems.append(f"/proc/self/cgroup is unreadable: {e}")
    if lines is not None:
        v2 = [ln[3:] for ln in lines if ln.startswith("0::")]
        if len(v2) != 1:
            problems.append(f"/proc/self/cgroup has no single cgroup v2 line: {lines}")
        else:
            cg = root / "sys" / "fs" / "cgroup" / v2[0].strip().lstrip("/")
            for name in ("memory.max", "pids.max"):
                _finite_limit(cg / name, problems)
    _source_read_only(root, problems)
    net = root / "sys" / "class" / "net"
    if not net.is_dir():
        problems.append("/sys/class/net is missing")
    else:
        others = sorted(p.name for p in net.iterdir() if p.is_dir() and p.name != "lo")
        if others:
            problems.append(f"network interfaces other than lo: {others}")
    if problems:
        raise SandboxNotConfined(
            f"{IN_SANDBOX_ENV}=1 is set but this process is not confined, so commands will not "
            "run directly: " + "; ".join(problems)
        )


class SandboxError(RuntimeError):
    """The sandboxed command exited non-zero."""

    def __init__(self, result: subprocess.CompletedProcess):
        self.result = result
        super().__init__(
            f"sandboxed command failed (exit {result.returncode}): {result.args}\n{result.stderr}"
        )


class SandboxNotConfined(SandboxError):
    """The in-sandbox marker is set but the process cannot prove it is confined."""

    def __init__(self, message: str):
        self.result = None
        RuntimeError.__init__(self, message)


class SandboxOOM(SandboxError):
    """The sandboxed command was killed for exceeding its memory limit (exit 137)."""


def run(
    cmd: list[str],
    *,
    out_dir: Path,
    mem: str = "16g",
    cpus: int = 8,
    pids: int = 4096,
    image: str | None = None,
    network: bool = False,
) -> subprocess.CompletedProcess:
    """Run ``cmd`` in the sandbox; ``out_dir`` is mounted rw at /work/out.

    Inside the sandbox already (:func:`in_sandbox`), ``cmd`` runs directly in ``out_dir``.
    """
    if in_sandbox():
        return _run_nested(cmd, Path(out_dir), image)
    args = [
        str(SANDBOX_RUN),
        "--mem",
        mem,
        "--cpus",
        str(cpus),
        "--pids",
        str(pids),
        "--workdir",
        str(out_dir),
        "--network",
        "bridge" if network else "none",
    ]
    if image:
        args += ["--image", image]
    res = subprocess.run([*args, "--", *cmd], capture_output=True, text=True, check=False)
    return _check(res)


def _check(res: subprocess.CompletedProcess) -> subprocess.CompletedProcess:
    if res.returncode == OOM_EXIT:
        raise SandboxOOM(res)
    if res.returncode != 0:
        raise SandboxError(res)
    return res


def _run_nested(cmd: list[str], out_dir: Path, image: str | None) -> subprocess.CompletedProcess:
    if image is not None:
        raise ValueError("inside the sandbox the image is fixed; image must be None")
    where = out_dir.resolve()
    if where == REPO_ROOT or REPO_ROOT in where.parents:
        raise ValueError(f"workdir must not be the repo root or inside it: {where}")
    res = subprocess.run(cmd, cwd=where, capture_output=True, text=True, check=False)
    if res.returncode == -signal.SIGKILL:  # the kernel OOM killer, as docker reports it
        res.returncode = OOM_EXIT
    return _check(res)
