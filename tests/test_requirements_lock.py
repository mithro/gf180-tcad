# SPDX-License-Identifier: Apache-2.0
"""docker/base/requirements.lock must be the exact `uv export` of the `image` group of uv.lock."""

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK = REPO_ROOT / "docker" / "base" / "requirements.lock"
EXPORT_CMD = [
    "uv",
    "export",
    "--locked",
    "--group",
    "image",
    "--no-dev",
    "--no-emit-project",
    "--format",
    "requirements-txt",
    "--hashes",
]


def test_requirements_lock_in_sync_with_uv_lock():
    assert shutil.which("uv"), "uv is required to check docker/base/requirements.lock"
    res = subprocess.run(EXPORT_CMD, cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    # uv echoes the command line in the header; ignore only that line (--locked is ours).
    want = [ln for ln in res.stdout.splitlines() if not ln.startswith("#    uv export")]
    have = [
        ln
        for ln in LOCK.read_text(encoding="utf-8").splitlines()
        if not ln.startswith("#    uv export")
    ]
    assert have == want, (
        "docker/base/requirements.lock is stale; regenerate with: "
        "uv export --group image --no-dev --no-emit-project --format requirements-txt "
        "--hashes > docker/base/requirements.lock"
    )
