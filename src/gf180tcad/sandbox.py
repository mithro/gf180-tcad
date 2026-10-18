# SPDX-License-Identifier: Apache-2.0
"""Python wrapper over ``tools/sandbox-run``: every simulator run goes through here.

Nesting: ``tools/sandbox-run`` sets ``GF180TCAD_IN_SANDBOX=1`` in the container. Code that
already runs inside the sandbox (e.g. ``python -m gf180tcad spice-job``, which calls the SPICE
runners) has no Docker, so :func:`run` then executes the command directly, with ``out_dir`` as
working directory, under the enclosing container's memory, CPU, PID and network limits; the
``mem``/``cpus``/``pids``/``network`` arguments do not apply and ``image`` must be None.
"""

import os
import signal
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_RUN = REPO_ROOT / "tools" / "sandbox-run"
OOM_EXIT = 137
IN_SANDBOX_ENV = "GF180TCAD_IN_SANDBOX"


def in_sandbox() -> bool:
    """True inside a ``tools/sandbox-run`` container (``GF180TCAD_IN_SANDBOX=1``)."""
    value = os.environ.get(IN_SANDBOX_ENV)
    if value is None:
        return False
    if value != "1":
        raise ValueError(f"{IN_SANDBOX_ENV} must be unset or '1', got {value!r}")
    return True


class SandboxError(RuntimeError):
    """The sandboxed command exited non-zero."""

    def __init__(self, result: subprocess.CompletedProcess):
        self.result = result
        super().__init__(
            f"sandboxed command failed (exit {result.returncode}): {result.args}\n{result.stderr}"
        )


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
