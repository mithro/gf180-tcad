# SPDX-License-Identifier: Apache-2.0
"""The pinned image (docker/IMAGE) provides the project environment (run with `pytest -m sandbox`)."""

import json

import pytest

from gf180tcad import sandbox

pytestmark = pytest.mark.sandbox


def test_venv_python_first_on_path(tmp_path):
    res = sandbox.run(
        ["python3", "-c", "import sys; print(sys.prefix); print(sys.version.split()[0])"],
        out_dir=tmp_path,
    )
    assert res.stdout.split() == ["/opt/gf180tcad", "3.12.3"]


def test_project_and_deps_import(tmp_path):
    code = (
        "import json, gf180tcad, numpy, devsim, gdsfactory; "
        "print(json.dumps([gf180tcad.__file__, numpy.__file__, devsim.__file__]))"
    )
    res = sandbox.run(["python3", "-c", code], out_dir=tmp_path)
    # DEVSIM prints a banner on import; the JSON is the last line.
    pkg, np_file, devsim_file = json.loads(res.stdout.splitlines()[-1])
    assert pkg == "/work/src/src/gf180tcad/__init__.py"
    assert np_file.startswith("/opt/gf180tcad/lib/python3.12/site-packages/")
    assert devsim_file.startswith("/opt/gf180tcad/lib/python3.12/site-packages/")


def test_devsim_solves(tmp_path):
    # DEVSIM needs BLAS/LAPACK at import and solve time (DEVSIM_MATH_LIBS in the image).
    code = (
        "import devsim as d; "
        "d.create_1d_mesh(mesh='m'); "
        "d.add_1d_mesh_line(mesh='m', pos=0, ps=0.1, tag='a'); "
        "d.add_1d_mesh_line(mesh='m', pos=1, ps=0.1, tag='b'); "
        "d.add_1d_contact(mesh='m', name='a', tag='a', material='metal'); "
        "d.add_1d_contact(mesh='m', name='b', tag='b', material='metal'); "
        "d.add_1d_region(mesh='m', material='Si', region='r', tag1='a', tag2='b'); "
        "d.finalize_mesh(mesh='m'); d.create_device(mesh='m', device='dev'); "
        "d.node_solution(device='dev', region='r', name='V'); "
        "d.edge_from_node_model(device='dev', region='r', node_model='V'); "
        "d.edge_model(device='dev', region='r', name='E', equation='(V@n0-V@n1)*EdgeInverseLength'); "
        "d.edge_model(device='dev', region='r', name='E:V@n0', equation='EdgeInverseLength'); "
        "d.edge_model(device='dev', region='r', name='E:V@n1', equation='-EdgeInverseLength'); "
        "d.equation(device='dev', region='r', name='Pe', variable_name='V', "
        "edge_model='E', variable_update='default'); "
        "[d.contact_node_model(device='dev', contact=c, name=c+'bc', equation=f'V-{v}') "
        "for c, v in (('a', 0), ('b', 1))]; "
        "[d.contact_node_model(device='dev', contact=c, name=c+'bc:V', equation='1') "
        "for c in ('a', 'b')]; "
        "[d.contact_equation(device='dev', contact=c, name='Pe', node_model=c+'bc') "
        "for c in ('a', 'b')]; "
        "d.solve(type='dc', absolute_error=1e-10, relative_error=1e-12, maximum_iterations=5); "
        "v = d.get_node_model_values(device='dev', region='r', name='V'); "
        "print(repr(v[len(v) // 2]))"
    )
    res = sandbox.run(["python3", "-c", code], out_dir=tmp_path)
    assert abs(float(res.stdout.strip().splitlines()[-1]) - 0.5) < 1e-12


def test_simulators_on_path(tmp_path):
    res = sandbox.run(
        ["sh", "-c", "for t in ngspice Xyce klayout; do command -v $t; done"], out_dir=tmp_path
    )
    assert res.stdout.split() == [
        "/foss/tools/ngspice/bin/ngspice",
        "/foss/tools/xyce/bin/Xyce",
        "/foss/tools/klayout/klayout",
    ]


def test_environment(tmp_path):
    res = sandbox.run(
        ["sh", "-c", 'echo "$PDK $PDK_ROOT $OMP_NUM_THREADS $USER $HOME"'], out_dir=tmp_path
    )
    assert res.stdout.split() == ["gf180mcuD", "/foss/pdks", "1", "gf180tcad", "/tmp/home"]


def test_venv_has_no_bytecode(tmp_path):
    # .pyc files embed source mtimes and would break build reproducibility.
    res = sandbox.run(["find", "/opt/gf180tcad", "-name", "*.pyc"], out_dir=tmp_path)
    assert res.stdout == ""
