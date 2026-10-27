# SPDX-License-Identifier: Apache-2.0
"""The host-side parts of :mod:`gf180tcad.meshcut` (renders plan Task R0): the strict MSH 2.2
reader, the gate window and the deterministic npz writer.

The fixture ``tests/fixtures/meshcut/grid30.msh`` is a 6 x 5 node grid (30 nodes, 40
triangles, 10 interface lines) with the layout of the gplugins meshes: coordinates in cm,
triangles (element type 2) carrying a region's physical tag, lines (type 1) an interface's.
"""

import ast
import struct
import zipfile
from pathlib import Path

import numpy as np
import pytest

from gf180tcad import meshcut
from gf180tcad.meshcut import msh, npz, window

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "meshcut" / "grid30.msh"


def _text_nodes(path):
    """The node block parsed independently with Python's float(): {id: (x, y)}."""
    lines = path.read_text(encoding="ascii").splitlines()
    start = lines.index("$Nodes")
    count = int(lines[start + 1])
    out = {}
    for line in lines[start + 2 : start + 2 + count]:
        i, x, y, _ = line.split()
        out[int(i)] = (float(x), float(y))
    return out


def _bits(a):
    return np.ascontiguousarray(a, dtype=np.float64).view(np.uint64)


def test_msh22_reader_round_trip():
    mesh = msh.read(FIXTURE)
    assert mesh.nodes.shape == (30, 2) and mesh.nodes.dtype == np.float64
    assert mesh.node_id.tolist() == list(range(1, 31))
    assert mesh.triangles.shape == (40, 3)
    assert mesh.lines.shape == (10, 2)
    assert mesh.names == {
        (1, 1): "body___oxide",
        (1, 2): "gate_poly___oxide",
        (2, 1): "body",
        (2, 2): "oxide",
        (2, 3): "gate_poly",
    }
    assert mesh.region_names() == ("body", "oxide", "gate_poly")
    assert mesh.boundary_names() == ("body___oxide", "gate_poly___oxide")
    # every coordinate is the exact double of its decimal text, bit for bit
    text = _text_nodes(FIXTURE)
    for k, i in enumerate(mesh.node_id.tolist()):
        assert _bits(mesh.nodes[k]).tolist() == _bits(np.array(text[i])).tolist()
    assert mesh.nodes[4, 0] == 4.400000000000001e-05
    # the first triangle: element 11, region body, nodes 1 2 8 (ids) -> indices 0 1 7
    assert mesh.triangles[0].tolist() == [0, 1, 7]
    assert mesh.triangle_tag.tolist() == [1] * 20 + [2] * 10 + [3] * 10
    assert mesh.line_tag.tolist() == [1] * 5 + [2] * 5


def _rewrite(tmp_path, old, new):
    text = FIXTURE.read_text(encoding="ascii")
    assert old in text
    path = tmp_path / "bad.msh"
    path.write_text(text.replace(old, new, 1), encoding="ascii")
    return path


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ("2.2 0 8", "4.1 0 8", "version"),
        ("2.2 0 8", "2.2 1 8", "ASCII"),
        ("2.2 0 8", "2.2 0 4", "data size"),
        ("1 1 2 1 1 13 14\n", "1 15 2 1 1 13\n", "element type 15"),
        ("1 1 2 1 1 13 14\n", "1 3 2 1 1 13 14 20 19\n", "element type 3"),
        ("30 5e-05 2e-05 0\n", "30 5e-05 2e-05 1e-05\n", "z"),
        ("1 1 2 1 1 13 14\n", "1 1 2 1 1 13 99\n", "unknown node"),
        ("1 1 2 1 1 13 14\n", "1 1 2 7 1 13 14\n", "physical"),
        ("$Nodes\n30\n", "$Nodes\n31\n", "count"),
        ("2 1e-05 -2e-05 0\n", "1 1e-05 -2e-05 0\n", "duplicate"),
        ("1 1 2 1 1 13 14\n", "1 1 0 13 14\n", "physical"),
        ("1 1 2 1 1 13 14\n", "1 1 2 1 1 13\n", "nodes"),
    ],
)
def test_reader_refuses_other_versions_and_elements(tmp_path, old, new, match):
    with pytest.raises(msh.MshError, match=match):
        msh.read(_rewrite(tmp_path, old, new))


@pytest.mark.parametrize("section", ["$MeshFormat", "$PhysicalNames", "$Nodes", "$Elements"])
def test_reader_refuses_a_missing_section(tmp_path, section):
    lines = FIXTURE.read_text(encoding="ascii").splitlines()
    start = lines.index(section)
    end = lines.index("$End" + section[1:])
    path = tmp_path / "missing.msh"
    path.write_text("\n".join(lines[:start] + lines[end + 1 :]) + "\n", encoding="ascii")
    with pytest.raises(msh.MshError, match=section[1:]):
        msh.read(path)


def test_rule_bounds():
    # gate from 1.0 to 1.6 um (L = 0.6), k_x = 0.5, depth 0.25 um below a surface at y = 0
    x_um, y_um = window.rule_bounds(
        gate_x_um=(1.0, 1.6), poly_top_um=0.2, surface_um=0.0, kx=0.5, depth_um=0.25
    )
    assert x_um == pytest.approx((0.7, 1.9))
    assert y_um == (-0.25, 0.2)
    with pytest.raises(ValueError):
        window.rule_bounds(
            gate_x_um=(1.6, 1.0), poly_top_um=0.2, surface_um=0.0, kx=0.5, depth_um=0.25
        )
    with pytest.raises(ValueError):
        window.rule_bounds(
            gate_x_um=(1.0, 1.6), poly_top_um=0.2, surface_um=0.0, kx=-1.0, depth_um=0.25
        )


def _brute_force_kept(mesh, x_um, y_um):
    c = mesh.nodes[mesh.triangles].mean(axis=1) * meshcut.UM_PER_MSH_UNIT
    inside = (
        (c[:, 0] >= x_um[0]) & (c[:, 0] <= x_um[1]) & (c[:, 1] >= y_um[0]) & (c[:, 1] <= y_um[1])
    )
    return np.flatnonzero(inside)


# windows in um: one cutting through cells of every region, one inside the body only
WINDOWS = [((0.15, 0.35), (-0.15, 0.15)), ((0.0, 0.5), (-0.2, -0.1)), ((0.25, 0.45), (-0.05, 0.25))]


@pytest.mark.parametrize(("x_um", "y_um"), WINDOWS)
def test_window_rule_keeps_whole_elements_only(x_um, y_um):
    mesh = msh.read(FIXTURE)
    w = window.cut(mesh, x_um=x_um, y_um=y_um)
    kept = _brute_force_kept(mesh, x_um, y_um)
    assert len(kept) > 0
    assert w.triangles.shape == (len(kept), 3) and w.triangles.dtype == np.int32
    # the kept elements are exactly the centroid-inside ones, whole: every vertex present
    full = {tuple(sorted(mesh.node_id[mesh.triangles[k]].tolist())) for k in kept}
    got = {tuple(sorted(w.node_id[t].tolist())) for t in w.triangles}
    assert got == full
    # the nodes are exactly the ones those elements use, in ascending original-id order
    used = np.unique(mesh.node_id[mesh.triangles[kept]])
    assert w.node_id.tolist() == used.tolist()
    assert w.node_id.dtype == np.int64
    # regions by name, in the full mesh's tag order
    assert w.regions == mesh.region_names()
    assert w.region.dtype == np.uint8
    names = [w.regions[r] for r in w.region]
    assert names == [mesh.names[(2, int(mesh.triangle_tag[k]))] for k in kept]
    assert w.x_um == x_um and w.y_um == y_um


def test_window_boundary_lines_are_edges_of_kept_elements():
    mesh = msh.read(FIXTURE)
    w = window.cut(mesh, x_um=(0.15, 0.35), y_um=(-0.15, 0.15))
    assert w.boundary_lines.dtype == np.int32 and w.boundary.dtype == np.uint8
    assert w.boundaries == mesh.boundary_names()
    edges = set()
    for t in w.triangles.tolist():
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            edges.add((min(a, b), max(a, b)))
    got = [tuple(sorted(e)) for e in w.boundary_lines.tolist()]
    assert got and all(e in edges for e in got)
    # every mesh line that is an edge of a kept element is kept (no interface dropped)
    expect = 0
    ids = {int(i): k for k, i in enumerate(w.node_id)}
    for (a, b), tag in zip(mesh.node_id[mesh.lines].tolist(), mesh.line_tag.tolist(), strict=True):
        if a in ids and b in ids and (min(ids[a], ids[b]), max(ids[a], ids[b])) in edges:
            expect += 1
    assert len(got) == expect
    assert {w.boundaries[b] for b in w.boundary} == {"body___oxide", "gate_poly___oxide"}


@pytest.mark.parametrize(("x_um", "y_um"), WINDOWS)
def test_window_nodes_are_bit_equal_subset(x_um, y_um):
    mesh = msh.read(FIXTURE)
    w = window.cut(mesh, x_um=x_um, y_um=y_um)
    assert w.nodes_cm.dtype == np.float64
    text = _text_nodes(FIXTURE)
    for row, i in zip(w.nodes_cm, w.node_id.tolist(), strict=True):
        assert _bits(row).tolist() == _bits(np.array(text[i])).tolist()


def test_window_refuses_an_empty_cut():
    mesh = msh.read(FIXTURE)
    with pytest.raises(ValueError, match="no element"):
        window.cut(mesh, x_um=(10.0, 11.0), y_um=(10.0, 11.0))


def _arrays():
    mesh = msh.read(FIXTURE)
    return window.cut(mesh, x_um=(0.15, 0.35), y_um=(-0.15, 0.15)).arrays()


def test_window_arrays_are_the_npz_members():
    a = _arrays()
    assert sorted(a) == [
        "boundary",
        "boundary_lines",
        "node_id",
        "nodes_cm",
        "region",
        "triangles",
    ]


def test_npz_is_deterministic(tmp_path):
    a = _arrays()
    one, two = tmp_path / "one.npz", tmp_path / "two.npz"
    npz.write_npz(one, a)
    npz.write_npz(two, dict(reversed(list(a.items()))))
    assert one.read_bytes() == two.read_bytes()
    with zipfile.ZipFile(one) as z:
        infos = z.infolist()
        assert [i.filename for i in infos] == sorted(k + ".npy" for k in a)
        for i in infos:
            assert i.date_time == (1980, 1, 1, 0, 0, 0)
            assert i.compress_type == zipfile.ZIP_DEFLATED
            assert i.extra == b""
            assert i.comment == b""
            assert z.read(i.filename)[:8] == b"\x93NUMPY\x01\x00"  # .npy format 1.0
    # no extra field in the local headers either (zipfile.ZipInfo.extra is the central one)
    data = one.read_bytes()
    offset = 0
    for _ in a:
        sig, *_rest, name_len, extra_len = struct.unpack("<IHHHHHIIIHH", data[offset : offset + 30])
        assert sig == 0x04034B50 and extra_len == 0
        comp = struct.unpack("<I", data[offset + 18 : offset + 22])[0]
        offset += 30 + name_len + comp


def test_npz_readable_by_numpy_load(tmp_path):
    a = _arrays()
    path = tmp_path / "w.npz"
    npz.write_npz(path, a)
    with np.load(path, allow_pickle=False) as z:
        assert sorted(z.files) == sorted(a)
        for k, v in a.items():
            assert z[k].dtype == v.dtype and z[k].shape == v.shape
            assert np.array_equal(z[k], v)
    back = npz.read_npz(path)
    assert sorted(back) == sorted(a)
    assert all(np.array_equal(back[k], a[k]) for k in a)


@pytest.mark.parametrize(
    "bad",
    [
        {"x": np.array([object()], dtype=object)},
        {"": np.zeros(1)},
        {"a/b": np.zeros(1)},
        {"x": [1, 2]},
    ],
)
def test_npz_refuses_bad_members(tmp_path, bad):
    with pytest.raises((TypeError, ValueError)):
        npz.write_npz(tmp_path / "bad.npz", bad)


def test_constants():
    assert meshcut.ARTEFACT == "mesh-window.npz"
    assert meshcut.META == "mesh-window.meta.json"
    assert meshcut.MAX_BYTES == 2_000_000
    assert meshcut.FORMAT == 1
    assert meshcut.UM_PER_MSH_UNIT == 1e4


def _imports(path):
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            out.add(base)
            out.update(f"{base}.{a.name}" for a in node.names)
    return out


def test_meshcut_never_imports_outcache():
    """Only the host command will read the output cache, as a tools/output-cache subprocess;
    no meshcut module imports gf180tcad.outcache (spec §9.1)."""
    pkg = REPO / "src" / "gf180tcad" / "meshcut"
    files = sorted(pkg.glob("*.py"))
    assert files
    for f in files:
        names = _imports(f)
        assert not any("outcache" in n for n in names), f


def test_reader_window_and_npz_import_only_numpy_and_stdlib():
    import sys

    pkg = REPO / "src" / "gf180tcad" / "meshcut"
    allowed_local = {"gf180tcad.meshcut", "gf180tcad"}
    for name in ("__init__.py", "msh.py", "window.py", "npz.py"):
        for n in _imports(pkg / name):
            top = n.split(".")[0]
            if top == "gf180tcad":
                assert n in allowed_local or n.startswith("gf180tcad.meshcut."), (name, n)
            else:
                assert top in {"numpy", "__future__"} or top in sys.stdlib_module_names, (name, n)
