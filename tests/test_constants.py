# SPDX-License-Identifier: Apache-2.0
"""Shared constants have one owner; every other module imports them instead of copying them.

The result-tree names and the engine list live in :mod:`gf180tcad.layout`, the engine
cross-check threshold next to :func:`~gf180tcad.spice.xyce.engine_diff`, and the bias-grid
tolerance next to the grids in :mod:`gf180tcad.devices`.
"""

import ast
from pathlib import Path

import pytest

from gf180tcad import devices, docgen, layout, manifest, metrics, reference, specwindow
from gf180tcad.spice import common, ngspice, xyce

SRC = Path(reference.__file__).resolve().parent
TOOLS = SRC.parents[1] / "tools"

# literal -> the one module (path relative to src/gf180tcad) allowed to define it
OWNERS = {
    "metrics.json": "layout.py",
    "envelope.json": "layout.py",
    "provenance.json": "layout.py",
    ("ngspice", "xyce"): "layout.py",
    0.005: "spice/xyce.py",
    1e-9: "devices.py",
}


def _module_level_literals(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            try:
                yield ast.literal_eval(node.value)
            except ValueError:
                continue


def _sources():
    yield from sorted(SRC.rglob("*.py"))
    yield TOOLS / "crosscheck-args"
    yield TOOLS / "crosscheck-tcad-run"


@pytest.mark.parametrize("path", list(_sources()), ids=lambda p: p.name)
def test_no_module_copies_a_shared_constant(path):
    rel = path.relative_to(SRC).as_posix() if path.is_relative_to(SRC) else path.name
    for value in _module_level_literals(path):
        try:
            owner = OWNERS.get(value)
        except TypeError:  # unhashable literal (list, dict)
            continue
        assert owner in (None, rel), f"{rel} defines {value!r}; import it from {owner}"


def test_the_owners_are_imported():
    assert reference.ENGINES is layout.ENGINES
    assert reference.METRICS_NAME is layout.METRICS_NAME
    assert reference.PROVENANCE_NAME is layout.PROVENANCE_NAME
    assert specwindow.METRICS_NAME is layout.METRICS_NAME
    assert specwindow.ENVELOPE_NAME is layout.ENVELOPE_NAME
    assert manifest.PROVENANCE_NAME is layout.PROVENANCE_NAME
    assert manifest.ENVELOPE_NAME is layout.ENVELOPE_NAME
    assert docgen.ENGINE_DIFF_THRESHOLD == xyce.ENGINE_DIFF_THRESHOLD == 0.005
    assert common.GRID_TOL is devices.GRID_TOL and ngspice.GRID_TOL is devices.GRID_TOL
    assert metrics.GRID_TOL is devices.GRID_TOL


def test_layout_imports_nothing_from_the_package():
    # manifest imports layout at module level and must not load the generator.
    tree = ast.parse((SRC / "layout.py").read_text(encoding="utf-8"))
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert all(isinstance(n, ast.ImportFrom) and n.module == "__future__" for n in imports)
