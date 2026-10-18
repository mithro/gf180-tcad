# SPDX-License-Identifier: Apache-2.0
"""The gplugins fork is the git submodule third_party/gplugins.

- The gitlink in HEAD is a commit on the fork's ``main`` (``gh api .../compare``; needs ``gh``,
  authenticated, or ``GH_TOKEN`` on CI), and ``.gitmodules`` points at the fork.
- Inside the TCAD image, ``import gplugins`` comes from the submodule under ``/work/src`` (the
  image's ``gf180tcad-gplugins.pth``); the submodule must be checked out (``git submodule update
  --init``). Sandbox-marked: run with ``pytest -m sandbox``.
- ruff never lints the fork (``[tool.ruff] extend-exclude``).
"""

import configparser
import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from gf180tcad import sandbox

REPO_ROOT = Path(__file__).resolve().parents[1]
SUBMODULE = "third_party/gplugins"
FORK = "mithro/gplugins"
FORK_URL = f"https://github.com/{FORK}.git"
MOUNTED = f"{sandbox.SOURCE_MOUNT}/{SUBMODULE}/"


def _gitlink() -> str:
    """The submodule commit recorded in HEAD (``git ls-tree HEAD third_party/gplugins``)."""
    res = subprocess.run(
        ["git", "ls-tree", "HEAD", SUBMODULE],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True,
    )  # fmt: skip
    m = re.fullmatch(rf"160000 commit ([0-9a-f]{{40}})\t{re.escape(SUBMODULE)}\n", res.stdout)
    assert m, f"{SUBMODULE} is not a submodule gitlink in HEAD: {res.stdout!r}"
    return m.group(1)


def test_gitmodules_points_at_the_fork():
    cfg = configparser.ConfigParser()
    cfg.read_string((REPO_ROOT / ".gitmodules").read_text(encoding="utf-8"))
    section = f'submodule "{SUBMODULE}"'
    assert cfg.sections() == [section]
    assert cfg[section]["path"] == SUBMODULE
    assert cfg[section]["url"] == FORK_URL


def test_submodule_pinned_on_fork_main():
    sha = _gitlink()
    gh = shutil.which("gh")
    assert gh, "gh is required to check the submodule commit against the fork's main"
    res = subprocess.run(
        [gh, "api", f"repos/{FORK}/compare/main...{sha}"],
        cwd=REPO_ROOT, check=False, capture_output=True, text=True,
    )  # fmt: skip
    assert res.returncode == 0, f"gh api failed:\n{res.stdout}\n{res.stderr}"
    status = json.loads(res.stdout)["status"]
    # behind/identical: sha is reachable from the fork's main. "ahead"/"diverged" means the
    # pinned commit is not (yet) merged into main.
    assert status in ("behind", "identical"), f"{SUBMODULE} @ {sha} vs {FORK} main: {status}"


@pytest.mark.sandbox
def test_plugin_imports_from_submodule(tmp_path):
    image = (REPO_ROOT / "docker" / "TCAD_IMAGE").read_text(encoding="utf-8").strip()
    code = "import gplugins; print(gplugins.__file__)"
    res = sandbox.run(["python3", "-c", code], out_dir=tmp_path, image=image)
    path = res.stdout.strip()
    assert path == f"{MOUNTED}gplugins/__init__.py", path


def test_ruff_excludes_third_party():
    cfg = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "third_party" in cfg["tool"]["ruff"].get("extend-exclude", [])
