# SPDX-License-Identifier: Apache-2.0
"""docker/base/*requirements.lock must be the exact `uv export` of their groups in uv.lock."""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE = REPO_ROOT / "docker" / "base"


def _strip_cmd_echo(text: str) -> list[str]:
    # uv echoes its command line in the header; ignore only that line (--locked is ours).
    return [ln for ln in text.splitlines() if not ln.startswith("#    uv export")]


@pytest.mark.parametrize(
    ("group", "lock"),
    [("image", "requirements.lock"), ("image-build", "build-requirements.lock")],
)
def test_requirements_lock_in_sync_with_uv_lock(group, lock):
    assert shutil.which("uv"), "uv is required to check the docker/base lock files"
    cmd = [
        "uv",
        "export",
        "--locked",
        "--group",
        group,
        "--no-dev",
        "--no-emit-project",
        "--format",
        "requirements-txt",
        "--hashes",
    ]
    res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    have = (BASE / lock).read_text(encoding="utf-8")
    assert _strip_cmd_echo(have) == _strip_cmd_echo(res.stdout), (
        f"docker/base/{lock} is stale; regenerate with: "
        f"{' '.join(c for c in cmd if c != '--locked')} > docker/base/{lock}"
    )
