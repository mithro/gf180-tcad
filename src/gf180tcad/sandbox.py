# SPDX-License-Identifier: Apache-2.0
"""Python wrapper over ``tools/sandbox-run``: every simulator run goes through here."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_RUN = REPO_ROOT / "tools" / "sandbox-run"
OOM_EXIT = 137


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
    """Run ``cmd`` in the sandbox; ``out_dir`` is mounted rw at /work/out."""
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
    if res.returncode == OOM_EXIT:
        raise SandboxOOM(res)
    if res.returncode != 0:
        raise SandboxError(res)
    return res
