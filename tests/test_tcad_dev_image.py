# SPDX-License-Identifier: Apache-2.0
"""The dev-HEAD TCAD image (docker/TCAD_DEV_IMAGE): the TCAD stack at upstream development HEAD.

It mirrors tests/test_tcad_image.py (the stable image, PyPI releases). The sandbox-marked tests
run inside the pinned dev image through ``sandbox.run(image=...)`` (run with
``pytest -m sandbox``); the others only read committed files.
"""

import io
import json
import re
import subprocess
import tarfile
import tomllib
from pathlib import Path

import pytest
from test_tcad_image import (
    _DEVSIM_SOLVE,
    _GMSH_MESH,
    _MESH_READBACK,
    MESH_READBACK_EXPECTED,
    TCAD_KEYS,
    _base_path,
)

from gf180tcad import sandbox

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKER = REPO_ROOT / "docker"
DEV = DOCKER / "tcad-dev"
PIN = DOCKER / "TCAD_DEV_IMAGE"
VERSIONS = DEV / "versions.json"
VENV = "/opt/gf180tcad-tcad"
SITE = f"{VENV}/lib/python3.13/site-packages/"
DEV_KEYS = TCAD_KEYS | {"upstream", "devsim_build"}


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
    assert all(
        isinstance(v, str) and v for k, v in data.items() if k not in ("upstream", "devsim_build")
    )
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
    # (the five dev-HEAD packages are excluded: their version strings come from upstream HEAD
    # and may or may not coincide with the release; devsim and gf180mcu do, at 2.11.1 and 1.0.0)
    for key in TCAD_KEYS - {"devsim", "meshwell", "gmsh", "gdsfactory", "gf180mcu"}:
        assert data[key] == stable[key], key


def test_tcad_dev_versions_json_devsim_build():
    """DEVSIM's build record: the manifest's commit, built by the build stage's GCC 14.2."""
    build = _json(VERSIONS)["devsim_build"]
    assert set(build) == {"commit", "compilers", "devsim_py3.so sha256"}
    assert build["commit"] == _json(DEV / "upstream.json")["devsim"]["commit"]
    assert re.fullmatch(r"[0-9a-f]{64}", build["devsim_py3.so sha256"])
    gcc = _json(DEV / "upstream.json")["gcc-14-x86-64-linux-gnu"]["version"]
    assert f"GCC: (Ubuntu {gcc}) 14.2.0" in build["compilers"], build["compilers"]


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
        "import json, devsim, meshwell, meshwell.orchestrator, gmsh, gdsfactory as gf; "
        "print(json.dumps([m.__file__ for m in (devsim, meshwell, gmsh, gf)]"
        " + [gf.__version__, gmsh.__version__]))"
    )
    res = _run(["python3", "-c", code], tmp_path)
    # DEVSIM prints a banner on import; the JSON is the last line.
    *files, gf_version, gmsh_version = json.loads(res.stdout.splitlines()[-1])
    for f in files:
        assert f.startswith(SITE), f
    versions = _json(VERSIONS)
    assert gf_version == versions["gdsfactory"]
    assert versions["gmsh"].startswith(gmsh_version + ".dev")


# The three dev-HEAD drifts found when the image was first pinned are fixed in the mithro forks
# (docs/reproduce/image.md, "Forks, and why"); their tests were strict expected failures until
# then, and are now ordinary tests: gf180mcu imports with gdsfactory 10, meshwell's mesh reads back
# through meshio under gmsh 5, and the fork's PN-slab test passes on the gmsh-5 mesh.


@pytest.mark.sandbox
def test_tcad_dev_gf180mcu_pdk(tmp_path):
    code = (
        "import json, gdsfactory as gf, gf180mcu; "
        "print(json.dumps([gf.get_active_pdk().name, gf180mcu.__file__]))"
    )
    res = _run(["python3", "-c", code], tmp_path)
    name, f = json.loads(res.stdout.splitlines()[-1])
    assert name == "gf180mcu"
    assert f.startswith(SITE)


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
def test_tcad_dev_meshwell_thread_defaults(tmp_path):
    """meshwell's import-time n_threads=cpu_count() defaults are 1 (PYTHON_CPU_COUNT=1)."""
    code = (
        "import inspect, json, meshwell.cad_gmsh, meshwell.cad_occ, meshwell.mesh\n"
        "out = {}\n"
        "for mod in (meshwell.cad_gmsh, meshwell.cad_occ, meshwell.mesh):\n"
        "    for name, obj in vars(mod).items():\n"
        "        if callable(obj) and getattr(obj, '__module__', None) == mod.__name__:\n"
        "            for f in (obj, getattr(obj, '__init__', None)):\n"
        "                try:\n"
        "                    p = inspect.signature(f).parameters.get('n_threads')\n"
        "                except (TypeError, ValueError):\n"
        "                    continue\n"
        "                if p is not None:\n"
        "                    out[f'{mod.__name__}.{name}'] = p.default\n"
        "print(json.dumps(out, sort_keys=True))\n"
    )
    got = json.loads(_run(["python3", "-c", code], tmp_path).stdout.splitlines()[-1])
    assert got, "no n_threads defaults found in meshwell"
    assert set(got.values()) == {1}, got


@pytest.mark.sandbox
def test_tcad_dev_meshwell_mesh_reads_back(tmp_path):
    """meshwell's 2D mesh, read back through meshio (gmsh 5 + the meshwell fork's MSH 4.1),
    is the stable image's (gmsh 4.15.2): the same points, cells and physical groups."""
    res = _run(["python3", "-c", _MESH_READBACK], tmp_path)
    assert json.loads(res.stdout.splitlines()[-1]) == MESH_READBACK_EXPECTED
    # and with gmsh single-threaded, after a real read-back
    got = json.loads(_run(["python3", "-c", _GMSH_MESH], tmp_path).stdout.splitlines()[-1])
    assert got == {"NumThreads": 1, "OCCParallel": 0}


# The same meshwell mesh as _GMSH_MESH, with only the meshio read-back of the finished mesh
# stubbed out (it was the meshio drift before the meshwell fork's fix), so the gmsh thread
# options are checked after a real meshwell CAD + mesh run independently of the read-back.
_GMSH_MESH_NO_READBACK = """
import json, gmsh, meshio
reads = []
meshio.read = lambda path, *a, **k: reads.append(path)
from shapely.geometry import box
from meshwell.orchestrator import generate_mesh
from meshwell.polysurface import PolySurface
generate_mesh([PolySurface(polygons=box(0, 0, 1, 1), physical_name='sq', mesh_order=1)],
              dim=2, default_characteristic_length=0.5, verbosity=0)
print(json.dumps({'NumThreads': gmsh.option.getNumber('General.NumThreads'),
                  'OCCParallel': gmsh.option.getNumber('Geometry.OCCParallel'),
                  'reads': len(reads)}))
"""


@pytest.mark.sandbox
def test_tcad_dev_gmsh_single_thread(tmp_path):
    res = _run(["python3", "-c", _GMSH_MESH_NO_READBACK], tmp_path)
    got = json.loads(res.stdout.splitlines()[-1])
    assert got == {"NumThreads": 1, "OCCParallel": 0, "reads": 1}


@pytest.mark.sandbox
def test_tcad_dev_gmsh_control_without_python_cpu_count(tmp_path):
    # Control: without the variable, meshwell's default asks gmsh for every host CPU.
    cmd = ["env", "-u", "PYTHON_CPU_COUNT", "python3", "-c", _GMSH_MESH_NO_READBACK]
    got = json.loads(_run(cmd, tmp_path).stdout.splitlines()[-1])
    cpus = int(_run(["python3", "-c", "import os; print(os.cpu_count())"], tmp_path).stdout)
    assert cpus == 1  # with the variable
    if got["NumThreads"] == 1:
        pytest.skip("this host has one CPU, so the control cannot show a difference")
    assert got["NumThreads"] > 1 and got["OCCParallel"] == 1


def _pinned_archive() -> bytes:
    """``git archive`` of the submodule's pinned commit (``git ls-tree HEAD third_party/gplugins``).

    The archive, not the checkout, so the test sees exactly the pinned files and can write into
    its own copy."""
    sub = REPO_ROOT / "third_party" / "gplugins"
    if not (sub / "gplugins").is_dir():
        pytest.skip("third_party/gplugins is not checked out")
    return subprocess.run(
        ["git", "-C", str(sub), "archive", _gplugins_pin()], capture_output=True, check=True
    ).stdout


@pytest.mark.sandbox
def test_tcad_dev_fork_pn_slab_currents_explained(tmp_path):
    """The fork's PN-slab test, from a git archive of the submodule pin, in the dev image."""
    archive = _pinned_archive()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(tmp_path, filter="data")
    test = "gplugins/devsim/tests/test_mesh.py::test_pn_slab_currents_explained"
    cmd = ["python3", "-m", "pytest", "-p", "no:cacheprovider", "-q", test]
    res = _run(cmd, tmp_path)
    assert "1 passed" in res.stdout


_RECORDS_CHECK = """
import csv, json, sysconfig
from pathlib import Path
site = Path(sysconfig.get_paths()["purelib"])
caches = sorted(str(p) for p in site.glob("*.dist-info/uv_cache.json"))
missing, n = [], 0
for record in sorted(site.glob("*.dist-info/RECORD")):
    for row in csv.reader(record.read_text(encoding="utf-8").splitlines()):
        n += 1
        if not (site / row[0]).resolve().exists():
            missing.append(row[0])
print(json.dumps({"uv_cache": caches, "missing": missing, "entries": n}))
"""


@pytest.mark.sandbox
def test_tcad_dev_records_complete_and_no_uv_cache(tmp_path):
    """The build stripped uv's timestamped uv_cache.json everywhere and left every RECORD whole
    (docker/tcad-dev/local_inputs.py strip-uv-cache)."""
    got = json.loads(_run(["python3", "-c", _RECORDS_CHECK], tmp_path).stdout.splitlines()[-1])
    assert got["uv_cache"] == []
    assert got["missing"] == []
    assert got["entries"] > 1000


def _gplugins_pin() -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-tree", "HEAD", "third_party/gplugins"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert out[1] == "commit", out
    return out[2]


@pytest.mark.sandbox
def test_tcad_dev_no_bytecode_and_no_compiler(tmp_path):
    res = _run(["find", VENV, "/opt/uv-python", "-name", "*.pyc"], tmp_path)
    assert res.stdout == ""
    # GCC 14 and the DEVSIM build tree exist only in the build stage
    paths = " ".join(
        f"/usr/bin/x86_64-linux-gnu-{tool}-14" for tool in ("cpp", "gcc", "g++", "gfortran")
    )
    script = (
        f'for p in {paths} /opt/build; do [ -e "$p" ] && echo "present: $p"; done; echo checked'
    )
    assert _run(["sh", "-c", script], tmp_path).stdout == "checked\n"
