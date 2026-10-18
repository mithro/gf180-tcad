# SPDX-License-Identifier: Apache-2.0
"""docker/tcad/*.lock are reproducible from their sources.

- requirements.lock is the exact `uv export` of the docker/tcad uv project (`--offline`, as
  tests/test_requirements_lock.py does for the base image);
- gf180mcu.lock and build-requirements.lock are single-purpose `uv pip compile --no-deps` locks.
  Their header records the full command, including `--exclude-newer`, so re-running it later
  gives the same lock even after newer PyPI releases (needs network);
- the TCAD image's numpy equals the base image's.
"""

import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TCAD = REPO_ROOT / "docker" / "tcad"
BASE = REPO_ROOT / "docker" / "base"

EXPORT = [
    "uv",
    "export",
    "--project",
    "docker/tcad",
    "--locked",
    "--offline",
    "--no-emit-project",
    "--format",
    "requirements-txt",
    "--hashes",
]
SINGLE_LOCKS = ("gf180mcu", "build-requirements")


def _strip_cmd_echo(text: str) -> list[str]:
    # uv echoes its command line in the header; ignore only that line.
    return [ln for ln in text.splitlines() if not re.match(r"#    uv (export|pip compile) ", ln)]


def _uv() -> str:
    uv = shutil.which("uv")
    assert uv, "uv is required to check the docker/tcad lock files"
    return uv


def _ensure_python_313(uv: str) -> None:
    """uv export needs a Python 3.13 interpreter (requires-python ==3.13.*) to exist.

    The GitHub runners have none, so fetch one first; this is the only online step, kept apart
    from the export itself, which runs --offline.
    """
    found = subprocess.run(
        [uv, "python", "find", "3.13"], check=False, capture_output=True, text=True
    )
    if found.returncode != 0:
        subprocess.run([uv, "python", "install", "3.13"], check=True, capture_output=True)


def test_tcad_lock_in_sync():
    _ensure_python_313(_uv())
    res = subprocess.run(EXPORT, check=False, cwd=REPO_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    have = (TCAD / "requirements.lock").read_text(encoding="utf-8")
    assert _strip_cmd_echo(have) == _strip_cmd_echo(res.stdout), (
        f"docker/tcad/requirements.lock is stale; regenerate with: "
        f"{shlex.join(EXPORT)} > docker/tcad/requirements.lock"
    )


def _recorded_command(name: str) -> list[str]:
    head = (TCAD / f"{name}.lock").read_text(encoding="utf-8").splitlines()[1]
    assert head.startswith("#    uv pip compile "), head
    return shlex.split(head.removeprefix("#    "))


@pytest.mark.parametrize("name", SINGLE_LOCKS)
def test_tcad_single_lock_command_is_pinned(name):
    """The recorded command is the documented one, pinned by --exclude-newer."""
    cmd = _recorded_command(name)
    assert re.fullmatch(
        rf"uv pip compile docker/tcad/{name}\.in --no-deps --generate-hashes "
        r"--python-version 3\.13\.\d+ --python-platform x86_64-manylinux_2_28 "
        r"--exclude-newer \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ",
        shlex.join(cmd),
    )


@pytest.mark.parametrize("name", SINGLE_LOCKS)
def test_tcad_single_locks_fresh(name):
    """Re-running the recorded command reproduces the lock (needs network)."""
    cmd = [_uv(), *_recorded_command(name)[1:]]
    res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    have = (TCAD / f"{name}.lock").read_text(encoding="utf-8")
    assert _strip_cmd_echo(have) == _strip_cmd_echo(res.stdout), (
        f"docker/tcad/{name}.lock is stale; regenerate with its recorded command"
    )


def test_tcad_python_patch_is_the_lock_python():
    """The single locks are compiled for the CPython patch the Dockerfile installs."""
    m = re.search(
        r"^ARG TCAD_PYTHON=(3\.13\.\d+)$", (TCAD / "Dockerfile").read_text(), re.MULTILINE
    )
    assert m, "docker/tcad/Dockerfile must pin ARG TCAD_PYTHON=3.13.<patch>"
    for name in SINGLE_LOCKS:
        assert f"--python-version {m.group(1)} " in shlex.join(_recorded_command(name))


def _pin(lock: Path, package: str) -> str:
    m = re.search(rf"^{package}==(\S+) ", lock.read_text(encoding="utf-8"), re.MULTILINE)
    assert m, f"no {package} pin in {lock}"
    return m.group(1)


def test_tcad_numpy_matches_base():
    assert _pin(TCAD / "requirements.lock", "numpy") == _pin(BASE / "requirements.lock", "numpy")


def test_tcad_lock_has_no_gplugins():
    """gplugins comes from the submodule (.pth), never from PyPI."""
    assert not re.search(r"^gplugins==", (TCAD / "requirements.lock").read_text(), re.MULTILINE)
