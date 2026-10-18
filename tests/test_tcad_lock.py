# SPDX-License-Identifier: Apache-2.0
"""docker/tcad/*.lock are reproducible from their sources.

- requirements.lock is the exact `uv export` of docker/tcad/uv.lock, and uv.lock is current
  for docker/tcad/pyproject.toml. Both checks are fully offline and need no Python 3.13: uv's
  own `--locked` / `uv lock --check` must find a 3.13 interpreter (requires-python ==3.13.*)
  even offline, and the GitHub runners have none. So the export runs `--frozen` (reads only
  uv.lock), and the pyproject-vs-lock check compares what uv records in uv.lock (requires-python,
  exclude-newer and the root's requires-dist) with pyproject.toml directly;
- gf180mcu.lock and build-requirements.lock are single-purpose `uv pip compile --no-deps` locks.
  Their header records the full command, including `--exclude-newer`, so re-running it later
  gives the same lock even after newer PyPI releases (needs network);
- the TCAD image's numpy equals the base image's.
"""

import re
import shlex
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

REPO_ROOT = Path(__file__).resolve().parents[1]
TCAD = REPO_ROOT / "docker" / "tcad"
BASE = REPO_ROOT / "docker" / "base"

EXPORT = [
    "uv",
    "export",
    "--project",
    "docker/tcad",
    "--frozen",
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


def test_tcad_lock_in_sync():
    _uv()
    res = subprocess.run(EXPORT, check=False, cwd=REPO_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    have = (TCAD / "requirements.lock").read_text(encoding="utf-8")
    assert _strip_cmd_echo(have) == _strip_cmd_echo(res.stdout), (
        f"docker/tcad/requirements.lock is stale; regenerate with: "
        f"{shlex.join(EXPORT)} > docker/tcad/requirements.lock"
    )


def _requirements(reqs) -> dict[str, SpecifierSet]:
    return {canonicalize_name(r.name): r.specifier for r in reqs}


def _lock_drift(pyproject: dict, lock: dict) -> list[str]:
    """Differences between pyproject.toml and what uv.lock was resolved from (empty = current)."""
    drift = []
    if lock["requires-python"] != pyproject["project"]["requires-python"]:
        drift.append("requires-python")
    if lock["options"]["exclude-newer"] != pyproject["tool"]["uv"]["exclude-newer"]:
        drift.append("exclude-newer")
    (root,) = [p for p in lock["package"] if p.get("source") == {"virtual": "."}]
    if canonicalize_name(root["name"]) != canonicalize_name(pyproject["project"]["name"]):
        drift.append("name")
    want = _requirements(Requirement(d) for d in pyproject["project"]["dependencies"])
    have = {
        canonicalize_name(d["name"]): SpecifierSet(d.get("specifier", ""))
        for d in root["metadata"]["requires-dist"]
    }
    drift += [
        f"dependency {n}" for n in sorted(set(want) | set(have)) if want.get(n) != have.get(n)
    ]
    return drift


def _load_tcad_project() -> tuple[dict, dict]:
    pyproject = tomllib.loads((TCAD / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((TCAD / "uv.lock").read_text(encoding="utf-8"))
    return pyproject, lock


def test_tcad_uv_lock_matches_pyproject():
    assert _lock_drift(*_load_tcad_project()) == [], "relock with: uv lock --project docker/tcad"


def test_tcad_lock_drift_control():
    """Positive control: every kind of pyproject change is detected."""
    pyproject, lock = _load_tcad_project()
    deps = pyproject["project"]["dependencies"]
    changed = [
        {**pyproject, "project": {**pyproject["project"], "dependencies": [*deps, "six"]}},
        {
            **pyproject,
            "project": {
                **pyproject["project"],
                "dependencies": [d.replace("==2.11.1", "==2.11.0") for d in deps],
            },
        },
        {**pyproject, "project": {**pyproject["project"], "requires-python": ">=3.13"}},
        {**pyproject, "tool": {"uv": {**pyproject["tool"]["uv"], "exclude-newer": "2027-01-01"}}},
    ]
    for p in changed:
        assert _lock_drift(p, lock), p


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
