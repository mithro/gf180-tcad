# SPDX-License-Identifier: Apache-2.0
"""The dev-HEAD TCAD image (docker/TCAD_DEV_IMAGE): the TCAD stack at upstream development HEAD.

It mirrors tests/test_tcad_image.py (the stable image, PyPI releases). The sandbox-marked tests
run inside the pinned dev image through ``sandbox.run(image=...)`` (run with
``pytest -m sandbox``); the others only read committed files.
"""

import json
import re
import tomllib
from pathlib import Path

import pytest
from test_tcad_image import _DEVSIM_SOLVE, _GMSH_MESH, TCAD_KEYS, _base_path

from gf180tcad import sandbox

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKER = REPO_ROOT / "docker"
DEV = DOCKER / "tcad-dev"
PIN = DOCKER / "TCAD_DEV_IMAGE"
VERSIONS = DEV / "versions.json"
VENV = "/opt/gf180tcad-tcad"
SITE = f"{VENV}/lib/python3.13/site-packages/"
DEV_KEYS = TCAD_KEYS | {"upstream"}


def _image() -> str:
    return PIN.read_text(encoding="utf-8").strip()


def _run(cmd: list[str], tmp_path: Path, **kw):
    return sandbox.run(cmd, out_dir=tmp_path, image=_image(), **kw)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _locked(name: str) -> str:
    lock = tomllib.loads((DEV / "uv.lock").read_text(encoding="utf-8"))
    (pkg,) = [p for p in lock["package"] if p["name"] == name]
    return pkg["version"]


# --- committed files (no Docker) -------------------------------------------------------------


def test_tcad_dev_image_pinned_by_digest():
    text = PIN.read_text(encoding="utf-8")
    assert re.fullmatch(r"ghcr\.io/mithro/gf180-tcad-tcad-dev@sha256:[0-9a-f]{64}\n", text)


def test_tcad_dev_image_id_is_a_digest():
    text = (DEV / "IMAGE_ID").read_text(encoding="utf-8")
    assert re.fullmatch(r"sha256:[0-9a-f]{64}\n", text)
    assert text != (DOCKER / "tcad" / "IMAGE_ID").read_text(encoding="utf-8")


def test_tcad_dev_versions_json_shape():
    text = VERSIONS.read_text(encoding="utf-8")
    data = json.loads(text)
    assert set(data) == DEV_KEYS
    assert text == json.dumps(data, indent=2, sort_keys=True) + "\n"
    assert all(isinstance(v, str) and v for k, v in data.items() if k != "upstream")
    # the manifest baked into the image is the committed one
    assert data["upstream"] == _json(DEV / "upstream.json")
    # the dev stack: the locked dev versions, not the stable releases
    stable = _json(DOCKER / "tcad" / "versions.json")
    for name in ("meshwell", "gdsfactory", "gmsh"):
        assert data[name] == _locked(name), name
        assert data[name] != stable[name], name
    assert data["gmsh"].startswith("5.0.0.dev")
    # same base image, same CPython, same tools and open_pdks facts as the stable image
    assert data["base_image_ref"] == (DOCKER / "IMAGE").read_text(encoding="utf-8").strip()
    for key in TCAD_KEYS - {"devsim", "meshwell", "gmsh", "gdsfactory", "gf180mcu", "scipy"}:
        assert data[key] == stable[key], key


# --- inside the dev image --------------------------------------------------------------------


@pytest.mark.sandbox
def test_tcad_dev_versions_json_matches_image(tmp_path):
    res = _run(["python3", "/work/src/docker/tcad-dev/probe_versions.py"], tmp_path)
    assert res.stdout == VERSIONS.read_text(encoding="utf-8")


@pytest.mark.sandbox
def test_tcad_dev_environment(tmp_path):
    keys = ["PDK", "PDK_ROOT", "PATH", "PYTHON_CPU_COUNT", "OPENBLAS_CORETYPE", "DEVSIM_MATH_LIBS"]
    code = (
        "import json, os, sys; print(json.dumps([sys.prefix, sys.version.split()[0], "
        f"{{k: os.environ[k] for k in {keys!r}}}]))"
    )
    prefix, ver, env = json.loads(_run(["python3", "-c", code], tmp_path).stdout)
    assert prefix == VENV
    assert ver == _json(VERSIONS)["python"]
    assert env == {
        "PDK": "gf180mcu",
        "PDK_ROOT": "/foss/pdks",
        "PATH": f"{VENV}/bin:{_base_path()}",
        "PYTHON_CPU_COUNT": "1",
        "OPENBLAS_CORETYPE": "Haswell",
        "DEVSIM_MATH_LIBS": "libopenblas.so.0",
    }


@pytest.mark.sandbox
def test_tcad_dev_imports(tmp_path):
    code = (
        "import json, devsim, meshwell, meshwell.orchestrator, gmsh, gdsfactory as gf, gf180mcu; "
        "pdk = gf.get_active_pdk(); "
        "print(json.dumps([pdk.name] + [m.__file__ for m in (devsim, meshwell, gmsh, gf, gf180mcu)]"
        " + [gf.__version__, gmsh.__version__]))"
    )
    res = _run(["python3", "-c", code], tmp_path)
    # DEVSIM prints a banner on import; the JSON is the last line.
    name, *files, gf_version, gmsh_version = json.loads(res.stdout.splitlines()[-1])
    assert name == "gf180mcu"
    for f in files:
        assert f.startswith(SITE), f
    versions = _json(VERSIONS)
    assert gf_version == versions["gdsfactory"]
    assert versions["gmsh"].startswith(gmsh_version + ".dev")


@pytest.mark.sandbox
def test_tcad_dev_gplugins_from_the_submodule(tmp_path):
    if not (REPO_ROOT / "third_party" / "gplugins" / "gplugins").is_dir():
        pytest.skip("third_party/gplugins is not checked out")
    code = "import gplugins, gplugins.devsim; print(gplugins.__file__)"
    res = _run(["python3", "-c", code], tmp_path)
    assert res.stdout.splitlines()[-1] == "/work/src/third_party/gplugins/gplugins/__init__.py"


@pytest.mark.sandbox
def test_tcad_dev_devsim_is_the_source_build(tmp_path):
    """DEVSIM is our build of the pinned commit, not the auditwheel-repaired PyPI wheel."""
    code = (
        "import json; from importlib.metadata import distribution; d = distribution('devsim'); "
        "print(json.dumps([str(f) for f in d.files], sort_keys=True))"
    )
    files = json.loads(_run(["python3", "-c", code], tmp_path).stdout)
    assert "devsim/devsim_py3.so" in files
    assert "devsim/umfpack/libumfpack_lgpl.so" in files
    # auditwheel (the PyPI wheels) bundles libquadmath/libgfortran into devsim.libs/
    assert not [f for f in files if f.startswith("devsim.libs/")]


@pytest.mark.sandbox
def test_tcad_dev_devsim_single_thread(tmp_path):
    res = _run(["python3", "-c", _DEVSIM_SOLVE], tmp_path)
    got = json.loads(res.stdout.splitlines()[-1])
    assert abs(got["v_mid"] - 0.5) < 1e-12
    assert got["threads_available"] in (None, 1)
    assert got["threads"] == 1
    log = res.stdout + res.stderr
    assert 'Loading "libopenblas.so.0"' in log
    assert "mkl" not in log.lower()


@pytest.mark.sandbox
def test_tcad_dev_python_cpu_count_one(tmp_path):
    assert _run(["python3", "-c", "import os; print(os.cpu_count())"], tmp_path).stdout == "1\n"


@pytest.mark.sandbox
def test_tcad_dev_gmsh_single_thread(tmp_path):
    got = json.loads(_run(["python3", "-c", _GMSH_MESH], tmp_path).stdout.splitlines()[-1])
    assert got == {"NumThreads": 1, "OCCParallel": 0}


@pytest.mark.sandbox
def test_tcad_dev_no_bytecode_and_no_compiler(tmp_path):
    res = _run(["find", VENV, "/opt/uv-python", "-name", "*.pyc"], tmp_path)
    assert res.stdout == ""
    # gfortran and the DEVSIM build tree exist only in the build stage
    res = _run(
        ["sh", "-c", "ls /usr/bin/x86_64-linux-gnu-gfortran-13 /opt/build || echo absent"],
        tmp_path,
    )
    assert res.stdout.splitlines()[-1] == "absent"
