# SPDX-License-Identifier: Apache-2.0
"""docker/tcad-dev: the dev-HEAD TCAD image's locks and its upstream manifest are consistent.

- upstream.json records, for every source that is not a PyPI release, the URL, sha256, licence
  and (for git projects) the commit and its upstream commit date;
- requirements.lock is the exact `uv export` of docker/tcad-dev/uv.lock, uv.lock is current for
  docker/tcad-dev/pyproject.toml, and the URL sources of both (meshwell, gdsfactory, gmsh) and of
  gf180mcu.lock are exactly the URLs and hashes of upstream.json;
- gf180mcu.lock and build-requirements.lock reproduce from the command in their header;
- the CPython patch and numpy equal the stable TCAD image's.
"""

import json
import re
import shlex
import subprocess
import tomllib
from pathlib import Path

import pytest
from test_tcad_lock import _lock_drift, _strip_cmd_echo, _uv

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV = REPO_ROOT / "docker" / "tcad-dev"
STABLE = REPO_ROOT / "docker" / "tcad"
BASE = REPO_ROOT / "docker" / "base"

EXPORT = [
    "uv",
    "export",
    "--project",
    "docker/tcad-dev",
    "--frozen",
    "--offline",
    "--no-emit-project",
    "--format",
    "requirements-txt",
    "--hashes",
]
SINGLE_LOCKS = ("gf180mcu", "build-requirements")
# The upstream development projects (git, default-branch HEAD) and how each is installed.
PROJECTS = {
    "devsim": "https://github.com/devsim/devsim",
    "meshwell": "https://github.com/simbilod/meshwell",
    "gdsfactory": "https://github.com/gdsfactory/gdsfactory",
    "gf180mcu": "https://github.com/gdsfactory/gf180mcu",
    "gmsh": "https://gitlab.onelab.info/gmsh/gmsh",
}
SUBMODULES = ("symdiff", "umfpack_lgpl", "boost_config", "boost_math", "boost_multiprecision")
# GCC 14, only in the build stage (upstream builds its x86_64 wheels with GCC 14).
DEBS = (
    "cpp-14-x86-64-linux-gnu",
    "gcc-14-x86-64-linux-gnu",
    "g++-14-x86-64-linux-gnu",
    "gfortran-14-x86-64-linux-gnu",
    "libgcc-14-dev",
    "libstdc++-14-dev",
    "libgfortran-14-dev",
)


def _upstream() -> dict:
    return json.loads((DEV / "upstream.json").read_text(encoding="utf-8"))


# --- upstream.json ---------------------------------------------------------------------------


def test_upstream_json_shape():
    text = (DEV / "upstream.json").read_text(encoding="utf-8")
    up = json.loads(text)
    assert text == json.dumps(up, indent=2, sort_keys=True) + "\n"
    assert set(up) == set(PROJECTS) | set(SUBMODULES) | set(DEBS)
    for name, e in up.items():
        assert re.fullmatch(r"[0-9a-f]{64}", e["sha256"]), name
        assert e["url"].startswith("https://"), name
        assert e["license"] and e["role"], name
        assert e["kind"] in ("source", "wheel", "deb"), name
    for name in (*PROJECTS, *SUBMODULES):
        e = up[name]
        assert re.fullmatch(r"[0-9a-f]{40}", e["commit"]), name
        # an ISO 8601 date with its UTC offset, as git prints it (%cI)
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(Z|[+-]\d\d:\d\d)", e["commit_date"])
    for name, repo in PROJECTS.items():
        assert up[name]["repository"] == repo
        assert up[name]["branch"] in ("main", "master"), name


def test_github_sources_are_commit_tarballs():
    """Every GitHub source is the tarball of exactly its commit (codeload or its redirect)."""
    up = _upstream()
    for name, e in up.items():
        if e["kind"] != "source":
            continue
        owner_repo = e["repository"].removeprefix("https://github.com/")
        assert e["url"] in (
            f"https://codeload.github.com/{owner_repo}/tar.gz/{e['commit']}",
            f"https://github.com/{owner_repo}/archive/{e['commit']}.tar.gz",
        ), name


def test_submodules_of_devsim():
    up = _upstream()
    for name in SUBMODULES:
        assert up[name]["submodule_of"].startswith("devsim:external/"), name


def test_gmsh_is_a_development_snapshot():
    g = _upstream()["gmsh"]
    assert g["kind"] == "wheel"
    m = re.fullmatch(
        r"https://gmsh\.info/python-packages-dev/gmsh/gmsh-(\d+\.\d+\.\d+\.dev\d{8})-py2\.py3-none-"
        r"manylinux_2_24_x86_64\.whl",
        g["url"],
    )
    assert m, g["url"]
    # the commit the wheel reports (General.BuildInfo "Version: 5.0.0-git-<hash>")
    assert g["commit"][:9] in g["role"]


# --- requirements.lock / uv.lock -------------------------------------------------------------


def test_tcad_dev_lock_in_sync():
    _uv()
    res = subprocess.run(EXPORT, check=False, cwd=REPO_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    have = (DEV / "requirements.lock").read_text(encoding="utf-8")
    assert _strip_cmd_echo(have) == _strip_cmd_echo(res.stdout), (
        f"docker/tcad-dev/requirements.lock is stale; regenerate with: "
        f"{shlex.join(EXPORT)} > docker/tcad-dev/requirements.lock"
    )


def _load_dev_project() -> tuple[dict, dict]:
    pyproject = tomllib.loads((DEV / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((DEV / "uv.lock").read_text(encoding="utf-8"))
    return pyproject, lock


def test_tcad_dev_uv_lock_matches_pyproject():
    assert _lock_drift(*_load_dev_project()) == [], (
        "relock with the command in docker/tcad-dev/pyproject.toml"
    )


def _url_requirements(text: str) -> dict[str, tuple[str, str]]:
    """name -> (url, sha256) of every `name @ url --hash=sha256:...` requirement."""
    found = re.findall(r"^(\S+) @ (\S+) \\\n\s+--hash=sha256:([0-9a-f]{64})$", text, re.MULTILINE)
    return {name: (url, sha) for name, url, sha in found}


def test_lock_url_sources_are_upstream_json():
    up = _upstream()
    reqs = _url_requirements((DEV / "requirements.lock").read_text(encoding="utf-8"))
    assert set(reqs) == {"meshwell", "gdsfactory", "gmsh"}
    gf = _url_requirements((DEV / "gf180mcu.lock").read_text(encoding="utf-8"))
    assert set(gf) == {"gf180mcu"}
    for name, (url, sha) in {**reqs, **gf}.items():
        assert (url, sha) == (up[name]["url"], up[name]["sha256"]), name
    sources = _load_dev_project()[0]["tool"]["uv"]["sources"]
    assert {n: s["url"] for n, s in sources.items()} == {n: up[n]["url"] for n in reqs}


def test_meshwell_version_matches_dockerfile():
    """The hatch-vcs version given to the meshwell sdist build is the locked one."""
    lock = _load_dev_project()[1]
    (mw,) = [p for p in lock["package"] if p["name"] == "meshwell"]
    docker = (DEV / "Dockerfile").read_text(encoding="utf-8")
    assert f"ARG MESHWELL_VERSION={mw['version']}\n" in docker
    assert f"SETUPTOOLS_SCM_PRETEND_VERSION={mw['version']} uv lock" in (
        DEV / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert mw["version"].endswith("+g" + _upstream()["meshwell"]["commit"][:9])


def test_no_pypi_devsim_or_gplugins():
    """DEVSIM is built from source and gplugins comes from the submodule, never from PyPI."""
    text = (DEV / "requirements.lock").read_text(encoding="utf-8")
    assert not re.search(r"^(devsim|gplugins|gf180mcu)\b", text, re.MULTILINE)


# --- the single locks ------------------------------------------------------------------------


def _recorded_command(name: str) -> list[str]:
    head = (DEV / f"{name}.lock").read_text(encoding="utf-8").splitlines()[1]
    assert head.startswith("#    uv pip compile "), head
    return shlex.split(head.removeprefix("#    "))


@pytest.mark.parametrize("name", SINGLE_LOCKS)
def test_tcad_dev_single_lock_command_is_pinned(name):
    no_deps = "--no-deps " if name == "gf180mcu" else ""
    assert re.fullmatch(
        rf"uv pip compile docker/tcad-dev/{name}\.in {no_deps}--generate-hashes "
        r"--python-version 3\.13\.\d+ --python-platform x86_64-manylinux_2_28 "
        r"--exclude-newer \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ",
        shlex.join(_recorded_command(name)),
    )


@pytest.mark.parametrize("name", SINGLE_LOCKS)
def test_tcad_dev_single_locks_fresh(name):
    """Re-running the recorded command reproduces the lock (needs network)."""
    cmd = [_uv(), *_recorded_command(name)[1:]]
    res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    have = (DEV / f"{name}.lock").read_text(encoding="utf-8")
    assert _strip_cmd_echo(have) == _strip_cmd_echo(res.stdout), (
        f"docker/tcad-dev/{name}.lock is stale; regenerate with its recorded command"
    )


def test_build_backends_are_constrained():
    """The sdists built in the image get their backends from the hashed build constraints."""
    text = (DEV / "build-requirements.lock").read_text(encoding="utf-8")
    for pkg in ("uv", "setuptools", "hatchling", "hatch-vcs", "flit-core"):
        assert re.search(rf"^{pkg}==\S+ \\\n\s+--hash=sha256:", text, re.MULTILINE), pkg


# --- shared with the stable image ------------------------------------------------------------


def _arg(path: Path, name: str) -> str:
    m = re.search(rf"^ARG {name}=(\S+)$", path.read_text(encoding="utf-8"), re.MULTILINE)
    assert m, f"no ARG {name}= in {path}"
    return m.group(1)


def test_same_python_as_stable():
    py = _arg(DEV / "Dockerfile", "TCAD_PYTHON")
    assert py == _arg(STABLE / "Dockerfile", "TCAD_PYTHON")
    for name in SINGLE_LOCKS:
        assert f"--python-version {py} " in shlex.join(_recorded_command(name))


def _pin(lock: Path, package: str) -> str:
    m = re.search(rf"^{package}==(\S+) ", lock.read_text(encoding="utf-8"), re.MULTILINE)
    assert m, f"no {package} pin in {lock}"
    return m.group(1)


def test_tcad_dev_numpy_matches_base():
    assert _pin(DEV / "requirements.lock", "numpy") == _pin(BASE / "requirements.lock", "numpy")


def test_build_inputs_date_the_build():
    """Every file the Dockerfile reads is a SOURCE_DATE_EPOCH input of docker/tcad-dev/build."""
    build = (DEV / "build").read_text(encoding="utf-8")
    m = re.search(r"^INPUTS=\((.*?)\)$", build, re.MULTILINE | re.DOTALL)
    assert m
    inputs = set(m.group(1).split())
    docker = (DEV / "Dockerfile").read_text(encoding="utf-8")
    used = set(re.findall(r"source=([\w.-]+),", docker)) | set(
        re.findall(r"^COPY (?:--chmod=\d+ )?([\w.-]+) ", docker, re.MULTILINE)
    )
    # a COPY from the build context keeps the checkout's mode (umask-dependent) unless pinned
    for line in re.findall(r"^COPY (?!--from=).*$", docker, re.MULTILINE):
        assert line.startswith("COPY --chmod="), line
    assert used >= {"upstream.json", "fetch_sources.py", "build-devsim.sh", "requirements.lock"}
    assert {f"docker/tcad-dev/{f}" for f in used} <= inputs
    assert {"docker/tcad-dev/Dockerfile", "docker/IMAGE"} <= inputs
