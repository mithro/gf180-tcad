# SPDX-License-Identifier: Apache-2.0
"""docker/tcad-dev: the dev-HEAD TCAD image's locks and its upstream manifest are consistent.

- upstream.json records, for every input that is not a PyPI file, the URL, sha256, licence, the
  file name the build saves it as, its mirror URL and (for git projects) the commit and its
  commit date; for the mithro forks also the upstream repository and the upstream commit the fork
  is based on;
- wheelhouse.json records every PyPI file the build installs, exactly one per pin of the locks,
  with a hash the lock allows, its PyPI URL and its mirror URL;
- requirements.lock is the exact `uv export` of docker/tcad-dev/uv.lock, uv.lock is current for
  docker/tcad-dev/pyproject.toml, and the URL sources of both (meshwell, gdsfactory, gf180mcu,
  gmsh) are exactly the URLs and hashes of upstream.json;
- build-requirements.lock reproduces from the command in its header;
- the CPython patch and numpy equal the stable TCAD image's.
"""

import importlib.util
import json
import re
import shlex
import subprocess
import tomllib
import urllib.parse
from pathlib import Path

import pytest
from packaging.utils import canonicalize_name
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
SINGLE_LOCKS = ("build-requirements",)
# The development projects (git, default-branch HEAD) the image installs.
PROJECTS = {
    "devsim": "https://github.com/devsim/devsim",
    "meshwell": "https://github.com/mithro/meshwell",
    "gdsfactory": "https://github.com/gdsfactory/gdsfactory",
    "gf180mcu": "https://github.com/mithro/gf180mcu",
    "gmsh": "https://gitlab.onelab.info/gmsh/gmsh",
}
# The mithro forks among them (fork main = upstream HEAD + gf180-tcad's fixes): their upstream.
FORKS = {
    "meshwell": "https://github.com/simbilod/meshwell",
    "gf180mcu": "https://github.com/gdsfactory/gf180mcu",
}
URL_INSTALLED = ("meshwell", "gdsfactory", "gf180mcu", "gmsh")
# gf180-tcad's input mirror: release assets of mithro/gf180-tcad.
MIRROR = "https://github.com/mithro/gf180-tcad/releases/download/gf180-tcad/inputs/tcad-dev-20261019/"
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


def _wheelhouse() -> dict:
    return json.loads((DEV / "wheelhouse.json").read_text(encoding="utf-8"))


def _wheelhouse_module():
    spec = importlib.util.spec_from_file_location("gf180tcad_wheelhouse", DEV / "wheelhouse.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- upstream.json ---------------------------------------------------------------------------


def test_upstream_json_shape():
    text = (DEV / "upstream.json").read_text(encoding="utf-8")
    up = json.loads(text)
    assert text == json.dumps(up, indent=2, sort_keys=True) + "\n"
    assert set(up) == set(PROJECTS) | set(SUBMODULES) | set(DEBS) | {"cpython"}
    for name, e in up.items():
        assert re.fullmatch(r"[0-9a-f]{64}", e["sha256"]), name
        assert e["url"].startswith("https://"), name
        assert e["license"] and e["role"], name
        assert e["kind"] in ("source", "wheel", "deb", "python"), name
    for name in (*PROJECTS, *SUBMODULES):
        e = up[name]
        assert re.fullmatch(r"[0-9a-f]{40}", e["commit"]), name
        # an ISO 8601 date with its UTC offset, as git prints it (%cI)
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(Z|[+-]\d\d:\d\d)", e["commit_date"])
    for name, repo in PROJECTS.items():
        assert up[name]["repository"] == repo
        assert up[name]["branch"] in ("main", "master"), name
    for name, e in up.items():
        assert ("upstream_repository" in e) == (name in FORKS), name


def test_forks_record_their_upstream_base():
    up = _upstream()
    for name, upstream_repo in FORKS.items():
        e = up[name]
        assert e["repository"] == upstream_repo.replace(
            upstream_repo.split("/")[3], "mithro", 1
        ), name
        assert e["upstream_repository"] == upstream_repo
        assert re.fullmatch(r"[0-9a-f]{40}", e["upstream_commit"]), name
        assert e["upstream_commit"] != e["commit"], name
        assert re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(Z|[+-]\d\d:\d\d)", e["upstream_commit_date"]
        )
    # SPDX: meshwell's CITATION.cff declares GPL-3.0-or-later (its LICENSE is the GPLv3 text)
    assert up["meshwell"]["license"] == "GPL-3.0-or-later"


def _mirror_url(file: str) -> str:
    """GitHub turns ``~`` into ``.`` in a release asset's name."""
    return MIRROR + urllib.parse.quote(file.replace("~", "."))


def test_every_input_has_a_mirror_url_and_a_sha256():
    """Every file the build fetches has a mithro-owned mirror URL, its original URL and a sha256."""
    up, wh = _upstream(), _wheelhouse()
    entries = [(n, e, e["file"]) for n, e in up.items()] + [(f, e, f) for f, e in wh.items()]
    assert len(entries) == len(up) + len(wh)
    assert len({file for _, _, file in entries}) == len(entries), "two inputs share a file name"
    for name, e, file in entries:
        assert re.fullmatch(r"[0-9a-f]{64}", e["sha256"]), name
        assert e["mirror_url"] == _mirror_url(file), name
        assert e["url"].startswith("https://") and not e["url"].startswith(MIRROR), name
        assert "/" not in file and file not in (".", ".."), name


def test_upstream_files():
    up = _upstream()
    for name, e in up.items():
        if e["kind"] == "source":
            assert e["file"] == f"{name}-{e['commit']}.tar.gz", name
        else:
            path = urllib.parse.unquote(urllib.parse.urlparse(e["url"]).path)
            assert e["file"] == path.rsplit("/", 1)[1], name


def test_cpython_is_the_tcad_python():
    e = _upstream()["cpython"]
    py = _arg(DEV / "Dockerfile", "TCAD_PYTHON")
    assert e["version"] == py
    assert e["url"] == (
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        f"{e['release']}/cpython-{py}%2B{e['release']}-x86_64-unknown-linux-gnu-"
        "install_only_stripped.tar.gz"
    )


def test_wheelhouse_is_exactly_the_locked_pypi_files():
    """One file per pin of requirements.lock (markers evaluated for the image) and
    build-requirements.lock, with a hash the lock allows; nothing else."""
    wh_mod = _wheelhouse_module()
    wh = _wheelhouse()
    text = (DEV / "wheelhouse.json").read_text(encoding="utf-8")
    assert text == json.dumps(wh, indent=2, sort_keys=True) + "\n"
    want: dict[tuple[str, str], set[str]] = {}
    for lock in wh_mod.LOCKS:
        for name, (version, hashes) in wh_mod.pins((DEV / lock).read_text("utf-8")).items():
            assert want.setdefault((name, version), hashes) == hashes, (lock, name)
    got: dict[tuple[str, str], list[str]] = {}
    for file, e in wh.items():
        assert canonicalize_name(e["package"]) == e["package"], file
        got.setdefault((e["package"], e["version"]), []).append(file)
        assert e["sha256"] in want.get((e["package"], e["version"]), set()), file
        assert e["url"].startswith("https://files.pythonhosted.org/packages/"), file
        assert e["url"].endswith("/" + file), file
    assert set(got) == set(want)
    # no file for a package installed from a URL (upstream.json), or for DEVSIM
    assert not {n for n, _ in got} & {*URL_INSTALLED, "devsim", "gplugins"}


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
    assert set(reqs) == set(URL_INSTALLED)
    for name, (url, sha) in reqs.items():
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
    """DEVSIM is built from source and gplugins comes from the submodule, never from PyPI;
    gf180mcu comes from its fork's commit (a URL requirement), not from PyPI."""
    text = (DEV / "requirements.lock").read_text(encoding="utf-8")
    assert not re.search(r"^(devsim|gplugins)\b", text, re.MULTILINE)
    assert not re.search(r"^gf180mcu==", text, re.MULTILINE)


# --- the single locks ------------------------------------------------------------------------


def _recorded_command(name: str) -> list[str]:
    head = (DEV / f"{name}.lock").read_text(encoding="utf-8").splitlines()[1]
    assert head.startswith("#    uv pip compile "), head
    return shlex.split(head.removeprefix("#    "))


@pytest.mark.parametrize("name", SINGLE_LOCKS)
def test_tcad_dev_single_lock_command_is_pinned(name):
    assert re.fullmatch(
        rf"uv pip compile docker/tcad-dev/{name}\.in --generate-hashes "
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
    # a COPY from the build context keeps the checkout's mode (umask-dependent): none at all,
    # every file reaches the image through a bind mount in the build stage
    assert re.findall(r"^COPY (?!--from=).*$", docker, re.MULTILINE) == []
    assert used >= {
        "upstream.json",
        "wheelhouse.json",
        "fetch_sources.py",
        "local_inputs.py",
        "build-devsim.sh",
        "requirements.lock",
        "build-requirements.lock",
    }
    assert {f"docker/tcad-dev/{f}" for f in used} <= inputs
    assert {"docker/tcad-dev/Dockerfile", "docker/IMAGE"} <= inputs
