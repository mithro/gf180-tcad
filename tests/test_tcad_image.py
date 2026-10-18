# SPDX-License-Identifier: Apache-2.0
"""The TCAD image (docker/TCAD_IMAGE): Python 3.13 + DEVSIM/meshwell/gmsh/gdsfactory/gf180mcu.

The sandbox-marked tests run inside the pinned TCAD image through ``sandbox.run(image=...)``
(run with ``pytest -m sandbox``); the others only read committed files.
"""

import json
import re
from pathlib import Path

import pytest

from gf180tcad import sandbox

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKER = REPO_ROOT / "docker"
TCAD_IMAGE_FILE = DOCKER / "TCAD_IMAGE"
VERSIONS = DOCKER / "tcad" / "versions.json"
VENV = "/opt/gf180tcad-tcad"

BASE_KEYS = set(json.loads((DOCKER / "base" / "versions.json").read_text(encoding="utf-8")))
TCAD_KEYS = BASE_KEYS | {
    "tcad_python",
    "meshwell",
    "gmsh",
    "gf180mcu",
    "scipy",
    "numpy",
    "base_image_ref",
}


def _tcad_image() -> str:
    return TCAD_IMAGE_FILE.read_text(encoding="utf-8").strip()


def _run(cmd: list[str], tmp_path: Path, **kw):
    return sandbox.run(cmd, out_dir=tmp_path, image=_tcad_image(), **kw)


# --- committed files (no Docker) -------------------------------------------------------------


def test_tcad_image_pinned_by_digest():
    text = TCAD_IMAGE_FILE.read_text(encoding="utf-8")
    assert re.fullmatch(r"ghcr\.io/mithro/gf180-tcad-tcad@sha256:[0-9a-f]{64}\n", text)


def test_tcad_image_id_is_a_digest():
    text = (DOCKER / "tcad" / "IMAGE_ID").read_text(encoding="utf-8")
    assert re.fullmatch(r"sha256:[0-9a-f]{64}\n", text)


def test_tcad_versions_json_shape():
    text = VERSIONS.read_text(encoding="utf-8")
    data = json.loads(text)
    assert set(data) == TCAD_KEYS
    assert all(isinstance(v, str) and v for v in data.values())
    assert text == json.dumps(data, indent=2, sort_keys=True) + "\n"
    assert data["python"].startswith("3.13.")
    assert data["devsim"] == "2.11.1"
    assert data["meshwell"] == "2.5.2"
    assert data["gmsh"] == "4.15.2"
    assert data["gdsfactory"] == "9.51.0"
    assert data["gf180mcu"] == "1.0.0"
    # The TCAD image is built FROM the pinned base image (docker/IMAGE) ...
    assert data["base_image_ref"] == (DOCKER / "IMAGE").read_text(encoding="utf-8").strip()
    # ... and shares its tools and open_pdks facts.
    base = json.loads((DOCKER / "base" / "versions.json").read_text(encoding="utf-8"))
    for key in BASE_KEYS - {"python", "devsim", "gdsfactory", "klayout_python"}:
        assert data[key] == base[key], key


# --- inside the TCAD image -------------------------------------------------------------------


@pytest.mark.sandbox
def test_tcad_versions_json_matches_image(tmp_path):
    res = _run(["python3", "/work/src/docker/tcad/probe_versions.py"], tmp_path)
    assert res.stdout == VERSIONS.read_text(encoding="utf-8")


def _base_path() -> str:
    """The base image's PATH, from its one definition (ENV PATH= in docker/base/Dockerfile)."""
    text = (DOCKER / "base" / "Dockerfile").read_text(encoding="utf-8")
    m = re.search(r"^ENV PATH=(\S+)", text, re.MULTILINE)
    assert m, "no ENV PATH= in docker/base/Dockerfile"
    return m.group(1)


@pytest.mark.sandbox
def test_tcad_environment(tmp_path):
    keys = ["PDK", "PDK_ROOT", "PATH", "OPENBLAS_CORETYPE", "PYTHONDONTWRITEBYTECODE"]
    code = (
        "import json, os, sys; print(json.dumps([sys.prefix, sys.version.split()[0], "
        f"{{k: os.environ[k] for k in {keys!r}}}]))"
    )
    res = _run(["python3", "-c", code], tmp_path)
    prefix, ver, env = json.loads(res.stdout)
    assert prefix == VENV
    assert ver.startswith("3.13.")
    assert env == {
        "PDK": "gf180mcu",
        "PDK_ROOT": "/foss/pdks",
        # the TCAD venv first, then exactly the base image's PATH
        "PATH": f"{VENV}/bin:{_base_path()}",
        "OPENBLAS_CORETYPE": "Haswell",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


@pytest.mark.sandbox
def test_tcad_imports(tmp_path):
    code = (
        "import json, devsim, meshwell.orchestrator, gmsh, gdsfactory as gf, gf180mcu; "
        "pdk = gf.get_active_pdk(); "
        "print(json.dumps([pdk.name, devsim.__file__, gf180mcu.__file__]))"
    )
    res = _run(["python3", "-c", code], tmp_path)
    # DEVSIM prints a banner on import; the JSON is the last line.
    name, devsim_file, gf180_file = json.loads(res.stdout.splitlines()[-1])
    assert name == "gf180mcu"
    assert devsim_file.startswith(f"{VENV}/lib/python3.13/site-packages/")
    assert gf180_file.startswith(f"{VENV}/lib/python3.13/site-packages/")


@pytest.mark.sandbox
def test_gplugins_pth_points_at_the_submodule(tmp_path):
    # The submodule arrives in Task 2; a missing directory must be harmless.
    code = (
        "import json, sys, sysconfig, pathlib; "
        "pth = pathlib.Path(sysconfig.get_paths()['purelib']) / 'gf180tcad-gplugins.pth'; "
        "print(json.dumps([pth.read_text(), '/work/src/third_party/gplugins' in sys.path]))"
    )
    res = _run(["python3", "-W", "error", "-c", code], tmp_path)
    text, on_path = json.loads(res.stdout)
    assert text == "/work/src/third_party/gplugins\n"
    # site only adds .pth entries that exist, so it is on sys.path iff the submodule is checked out
    assert on_path == (REPO_ROOT / "third_party" / "gplugins").is_dir()
    assert res.stderr == ""


@pytest.mark.sandbox
def test_tcad_numpy_baseline(tmp_path):
    code = (
        "import json, numpy._core._multiarray_umath as m; "
        "print(json.dumps({'dispatch': m.__cpu_dispatch__, "
        "'enabled': [f for f in m.__cpu_dispatch__ if m.__cpu_features__.get(f)]}))"
    )
    res = _run(["python3", "-W", "error", "-c", code], tmp_path)
    assert res.stderr == "", res.stderr
    got = json.loads(res.stdout)
    assert {"X86_V3", "X86_V4"} <= set(got["dispatch"])
    assert got["enabled"] == []


_DEVSIM_SOLVE = """
import json
import devsim as d
d.create_1d_mesh(mesh='m')
d.add_1d_mesh_line(mesh='m', pos=0, ps=0.001, tag='a')
d.add_1d_mesh_line(mesh='m', pos=1, ps=0.001, tag='b')
d.add_1d_contact(mesh='m', name='a', tag='a', material='metal')
d.add_1d_contact(mesh='m', name='b', tag='b', material='metal')
d.add_1d_region(mesh='m', material='Si', region='r', tag1='a', tag2='b')
d.finalize_mesh(mesh='m')
d.create_device(mesh='m', device='dev')
d.node_solution(device='dev', region='r', name='V')
d.edge_from_node_model(device='dev', region='r', node_model='V')
d.edge_model(device='dev', region='r', name='E', equation='(V@n0-V@n1)*EdgeInverseLength')
d.edge_model(device='dev', region='r', name='E:V@n0', equation='EdgeInverseLength')
d.edge_model(device='dev', region='r', name='E:V@n1', equation='-EdgeInverseLength')
d.equation(device='dev', region='r', name='Pe', variable_name='V', edge_model='E',
           variable_update='default')
for c, v in (('a', 0), ('b', 1)):
    d.contact_node_model(device='dev', contact=c, name=c + 'bc', equation=f'V-{v}')
    d.contact_node_model(device='dev', contact=c, name=c + 'bc:V', equation='1')
    d.contact_equation(device='dev', contact=c, name='Pe', node_model=c + 'bc')
d.solve(type='dc', absolute_error=1e-10, relative_error=1e-12, maximum_iterations=5)
threads = int(open('/proc/self/status').read().split('Threads:')[1].split()[0])
params = d.get_parameter_list()
avail = d.get_parameter(name='threads_available') if 'threads_available' in params else None
v = d.get_node_model_values(device='dev', region='r', name='V')
print(json.dumps({'threads': threads, 'threads_available': avail, 'v_mid': v[len(v) // 2]}))
"""


@pytest.mark.sandbox
def test_devsim_single_thread(tmp_path):
    res = _run(["python3", "-c", _DEVSIM_SOLVE], tmp_path)
    got = json.loads(res.stdout.splitlines()[-1])
    assert abs(got["v_mid"] - 0.5) < 1e-12
    assert got["threads_available"] in (None, 1)
    # After the solve, so any solver or BLAS thread pool would still be alive.
    assert got["threads"] == 1
    log = res.stdout + res.stderr
    assert 'Loading "libopenblas.so.0"' in log
    assert "mkl" not in log.lower()


@pytest.mark.sandbox
def test_python_cpu_count_one(tmp_path):
    res = _run(["python3", "-c", "import os; print(os.cpu_count())"], tmp_path)
    assert res.stdout == "1\n"


# meshwell's default generate_mesh (no n_threads): its ModelManager takes the import-time
# os.cpu_count() default, so only PYTHON_CPU_COUNT=1 makes gmsh single-threaded here.
_GMSH_MESH = """
import json, gmsh
from shapely.geometry import box
from meshwell.orchestrator import generate_mesh
from meshwell.polysurface import PolySurface
generate_mesh([PolySurface(polygons=box(0, 0, 1, 1), physical_name='sq', mesh_order=1)],
              dim=2, default_characteristic_length=0.5, verbosity=0)
print(json.dumps({'NumThreads': gmsh.option.getNumber('General.NumThreads'),
                  'OCCParallel': gmsh.option.getNumber('Geometry.OCCParallel')}))
"""


@pytest.mark.sandbox
def test_gmsh_single_thread(tmp_path):
    got = json.loads(_run(["python3", "-c", _GMSH_MESH], tmp_path).stdout.splitlines()[-1])
    assert got == {"NumThreads": 1, "OCCParallel": 0}


@pytest.mark.sandbox
def test_gmsh_control_without_python_cpu_count(tmp_path):
    # Control: without the variable, meshwell's default asks gmsh for every host CPU.
    res = _run(["env", "-u", "PYTHON_CPU_COUNT", "python3", "-c", _GMSH_MESH], tmp_path)
    got = json.loads(res.stdout.splitlines()[-1])
    cpus = int(_run(["python3", "-c", "import os; print(os.cpu_count())"], tmp_path).stdout)
    assert cpus == 1  # with the variable
    if got["NumThreads"] == 1:
        pytest.skip("this host has one CPU, so the control cannot show a difference")
    assert got["NumThreads"] > 1 and got["OCCParallel"] == 1


@pytest.mark.sandbox
def test_pytest_in_image(tmp_path):
    res = _run(["python3", "-m", "pytest", "--version"], tmp_path)
    assert re.match(r"pytest \d+\.\d+", res.stdout + res.stderr)


@pytest.mark.sandbox
def test_tcad_venv_has_no_bytecode(tmp_path):
    # .pyc files embed source mtimes and would break build reproducibility; the CPython archive's
    # own .pyc files in /opt/uv-python are stale after extraction, so they are deleted too.
    res = _run(["find", VENV, "/opt/uv-python", "-name", "*.pyc"], tmp_path)
    assert res.stdout == ""
