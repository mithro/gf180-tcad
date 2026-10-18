# SPDX-License-Identifier: Apache-2.0
"""A real git main checkout with a linked worktree (test helper)."""

import os
import subprocess
from pathlib import Path

GIT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")


def git(*args: str, cwd: Path) -> str:
    env = {k: v for k, v in os.environ.items() if k not in GIT_VARS}
    res = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd, env=env, check=True, capture_output=True, text=True,
    )  # fmt: skip
    return res.stdout


def make_worktree(root: Path) -> tuple[Path, Path]:
    """``root/proj/main`` (a repo with one commit) and its linked worktree ``root/proj/wt``."""
    main = root / "proj" / "main"
    main.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=main)
    (main / "README").write_text("x\n", encoding="utf-8")
    git("add", "README", cwd=main)
    git("commit", "-q", "-m", "init", cwd=main)
    wt = root / "proj" / "wt"
    git("worktree", "add", "-q", str(wt), cwd=main)
    return main.resolve(), wt.resolve()
