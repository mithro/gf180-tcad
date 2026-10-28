# SPDX-License-Identifier: Apache-2.0
"""The host-side parts of :mod:`gf180tcad.meshcut` (renders plan Task R0): the strict MSH 2.2
reader, the gate window and the deterministic npz writer; the artefact files and their meta
schema, the in-image job (run here in-process with a stand-in cross-section) and the host
command (with its pull and sandbox calls faked).

The fixture ``tests/fixtures/meshcut/grid30.msh`` is a 6 x 5 node grid (30 nodes, 40
triangles, 10 interface lines) with the layout of the gplugins meshes: coordinates in cm,
triangles (element type 2) carrying a region's physical tag, lines (type 1) an interface's.
"""

import ast
import hashlib
import json
import struct
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from gf180tcad import meshcut
from gf180tcad.meshcut import artefact, job, msh, npz, window

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
        ("11 2 2 1 11 1 2 8\n", "11 2 2 1 11 1 2 2\n", "repeats a node"),
        ("1 1 2 1 1 13 14\n", "1 1 2 1 1 13 13\n", "repeats a node"),
    ],
)
def test_reader_refuses_other_versions_and_elements(tmp_path, old, new, match):
    with pytest.raises(msh.MshError, match=match):
        msh.read(_rewrite(tmp_path, old, new))


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ('2 1 "body"\n', '2 one "body"\n', r"\$PhysicalNames: bad line '2 one"),
        ("30 5e-05 2e-05 0\n", "30 abc 2e-05 0\n", r"\$Nodes: bad line '30 abc"),
        ("30 5e-05 2e-05 0\n", "30 5e-05 2e-05 zero\n", r"\$Nodes: bad line '30 5e-05 2e-05 zero"),
        ("30 5e-05 2e-05 0\n", "30.5 5e-05 2e-05 0\n", r"\$Nodes: bad line '30.5"),
        ("1 1 2 1 1 13 14\n", "1 1 2 1 1 13 x14\n", r"\$Elements: bad line '1 1 2 1 1 13 x14"),
        ("$Nodes\n30\n", "$Nodes\nthirty\n", r"\$Nodes: bad count line"),
    ],
)
def test_reader_names_the_section_and_line_of_a_non_numeric_field(tmp_path, old, new, match):
    with pytest.raises(msh.MshError, match=match):
        msh.read(_rewrite(tmp_path, old, new))


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "NaN", "Infinity"])
@pytest.mark.parametrize("column", [1, 2])
def test_reader_refuses_non_finite_coordinates(tmp_path, value, column):
    fields = ["30", "5e-05", "2e-05", "0"]
    fields[column] = value
    path = _rewrite(tmp_path, "30 5e-05 2e-05 0\n", " ".join(fields) + "\n")
    with pytest.raises(msh.MshError, match="not finite"):
        msh.read(path)


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
    files = sorted(pkg.rglob("*.py"))
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


# --- Step 2 part 2: the artefact files, the job and the host command -------------------------

RESULTS = REPO / "results"
MESHES = RESULTS / "tcad" / "meshes"
MOSCAP2D = RESULTS / "tcad" / "moscap2d"
# The #35 calibrated nfet job: its mesh is in the output cache (renders plan, Step 2 part 1).
L0P60 = MOSCAP2D / "nfet_05v0" / "calibrated" / "w10p0_l0p60"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class _Lin:
    """A stand-in doping profile ``a + b x + c depth`` that records the bounds it was bound to."""

    def __init__(self, a, b=0.0, c=0.0, bound=None):
        self.a, self.b, self.c, self.bound = a, b, c, bound

    def open_edges(self, x_range, y_range):
        return _Lin(self.a, self.b, self.c, (tuple(x_range), tuple(y_range)))

    def __call__(self, x_um, y_um):
        x = np.asarray(x_um, dtype=float)
        y = np.asarray(y_um, dtype=float)
        if self.bound is not None:
            _BOUNDS.append(self.bound)
        return self.a + self.b * x + self.c * y


_BOUNDS: list = []


def _fixture_xs(**over):
    """A cross-section stand-in with the fixture's layout: the gate over x 0 to 0.5 um, the
    oxide from y 0 to 0.1 um, the poly from 0.1 to 0.2 um; the body doping varies with x and
    depth so the frames are visible."""
    fields = {
        "gate_u": (0.0, 0.5),
        "t_ox_nm": 100.0,
        "l_um": 0.5,
        "levels": {
            "body": ((1001, 0), -0.2, 0.2, "si"),
            "oxide": ((1002, 0), 0.0, 0.1, "sio2"),
            "gate_poly": ((1003, 0), 0.1, 0.1, "si"),
        },
        "doping": {
            "body": ((_Lin(1e15, 1e16, 1e17),), (_Lin(2e15),)),
            "gate_poly": ((_Lin(1e20, 0.0, 1e19),), ()),
        },
    }
    fields.update(over)
    return SimpleNamespace(**fields)


def _fixture_job(tmp_path, *, mesh_sha=None, device="nfet_05v0", params="start", gid="w1p0_l0p50"):
    """A 2D job directory ``<tmp>/results/tcad/moscap2d/<device>/<params>/<gid>`` whose
    cv.meta.json names the fixture mesh, with that mesh pulled beside it."""
    results = tmp_path / "results"
    d = results / "tcad" / "moscap2d" / device / params / gid
    d.mkdir(parents=True)
    mesh_spec = json.loads((L0P60 / "cv.meta.json").read_bytes())["mesh"]
    meta = {"device": device, "params": params, "dim": 2, "mesh": mesh_spec,
            "mesh_sha256": mesh_sha or _sha(FIXTURE)}  # fmt: skip
    (d / "cv.meta.json").write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
    return results, d


def _cut_fixture(tmp_path, out=None, **kw):
    results, d = _fixture_job(tmp_path)
    out = out or tmp_path / "out"
    out.mkdir(exist_ok=True)
    mesh = out / "mesh.msh"
    mesh.write_bytes(FIXTURE.read_bytes())
    meta = job.cut(
        mesh,
        job_dir=d,
        results_root=results,
        xs=kw.pop("xs", _fixture_xs()),
        kx=kw.pop("kx", 0.0),
        depth_um=kw.pop("depth_um", 0.15),
        source=kw.pop("source", "cache"),
        out=out,
    )
    return meta, out, d


def test_window_with_net_doping_has_seven_members():
    mesh = msh.read(FIXTURE)
    w = window.cut(mesh, x_um=(0.15, 0.35), y_um=(-0.15, 0.15))
    assert w.net_doping_cm3 is None
    w2 = w.with_net_doping(np.zeros(len(w.node_id)))
    assert sorted(w2.arrays()) == sorted([*w.arrays(), "net_doping_cm3"])
    assert w2.arrays()["net_doping_cm3"].dtype == np.float64
    with pytest.raises(ValueError, match="one value per node"):
        w.with_net_doping(np.zeros(len(w.node_id) + 1))


def test_meta_schema_sorted_and_complete(tmp_path):
    meta, out, d = _cut_fixture(tmp_path)
    path = out / meshcut.META
    text = path.read_text(encoding="utf-8")
    # written as io.write_json writes: sorted keys, two-space indent, trailing newline
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"
    on_disk = json.loads(text)
    assert on_disk == meta
    assert tuple(sorted(on_disk)) == artefact.META_KEYS
    assert tuple(sorted(on_disk["job"])) == artefact.JOB_KEYS
    assert tuple(sorted(on_disk["window"])) == artefact.WINDOW_KEYS
    assert tuple(sorted(on_disk["window"]["rule"])) == artefact.RULE_KEYS
    assert on_disk["format"] == meshcut.FORMAT
    assert on_disk["units"] == {
        "net_doping_cm3": "cm^-3", "nodes_cm": "cm", "um_per_mesh_unit": 1e4, "window": "um",
    }  # fmt: skip
    assert on_disk["job"] == {
        "cv_meta_sha256": _sha(d / "cv.meta.json"),
        "device": "nfet_05v0",
        "geometry_id": "w1p0_l0p50",
        "params": "start",
        "tree": "tcad/moscap2d",
    }
    assert on_disk["full_mesh_sha256"] == _sha(FIXTURE)
    assert (on_disk["full_mesh_node_count"], on_disk["full_mesh_triangle_count"]) == (30, 40)
    assert on_disk["npz_sha256"] == _sha(out / meshcut.ARTEFACT)
    assert on_disk["regions"] == ["body", "oxide", "gate_poly"]
    assert on_disk["boundaries"] == ["body___oxide", "gate_poly___oxide"]
    assert on_disk["source"] == "cache"
    assert on_disk["window"]["rule"] == {
        "depth_um": 0.15, "gate_x_um": [0.0, 0.5], "kx": 0.0, "poly_top_um": 0.2,
        "surface_um": 0.0,
    }  # fmt: skip
    assert on_disk["window"]["x_um"] == [0.0, 0.5] and on_disk["window"]["y_um"] == [-0.15, 0.2]
    a = npz.read_npz(out / meshcut.ARTEFACT)
    assert on_disk["node_count"] == len(a["node_id"])
    assert on_disk["triangle_count"] == len(a["triangles"])
    assert on_disk["boundary_line_count"] == len(a["boundary_lines"])
    artefact.check_meta(on_disk)


@pytest.mark.parametrize(
    "spoil",
    [
        lambda m: m.pop("npz_sha256"),
        lambda m: m.update(extra=1),
        lambda m: m["job"].pop("tree"),
        lambda m: m["window"]["rule"].update(kx="wide"),
        lambda m: m.update(format=2),
        lambda m: m.update(source="somewhere"),
        lambda m: m.update(node_count=-1),
        lambda m: m["units"].update(nodes_cm="um"),
        lambda m: m.update(full_mesh_sha256="abc"),
        lambda m: m.update(regions="body"),
    ],
)
def test_meta_schema_refuses_a_bad_meta(tmp_path, spoil):
    meta, _, _ = _cut_fixture(tmp_path)
    spoil(meta)
    with pytest.raises(ValueError):
        artefact.check_meta(meta)


def test_read_round_trip(tmp_path):
    meta, out, _ = _cut_fixture(tmp_path)
    w = meshcut.read(out)
    a = npz.read_npz(out / meshcut.ARTEFACT)
    assert sorted(w.arrays()) == sorted(a)
    for k in a:
        assert np.array_equal(w.arrays()[k], a[k]) and w.arrays()[k].dtype == a[k].dtype
    assert w.regions == tuple(meta["regions"]) and w.boundaries == tuple(meta["boundaries"])
    assert w.x_um == (0.0, 0.5) and w.y_um == (-0.15, 0.2)
    assert artefact.read_meta(out) == meta


def test_read_refuses_an_npz_that_is_not_the_meta_s(tmp_path):
    _, out, _ = _cut_fixture(tmp_path)
    data = bytearray((out / meshcut.ARTEFACT).read_bytes())
    data[-1] ^= 1
    (out / meshcut.ARTEFACT).write_bytes(bytes(data))
    with pytest.raises(ValueError, match="npz_sha256"):
        meshcut.read(out)


def test_read_refuses_members_that_disagree_with_the_meta(tmp_path):
    meta, out, _ = _cut_fixture(tmp_path)
    a = npz.read_npz(out / meshcut.ARTEFACT)
    a["region"] = a["region"].astype(np.int64)  # wrong dtype
    npz.write_npz(out / meshcut.ARTEFACT, a)
    meta["npz_sha256"] = _sha(out / meshcut.ARTEFACT)
    (out / meshcut.META).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", "utf-8")
    with pytest.raises(ValueError, match="region"):
        meshcut.read(out)


def test_cut_is_byte_identical_twice(tmp_path):
    _cut_fixture(tmp_path / "one")
    _cut_fixture(tmp_path / "two")
    for name in (meshcut.ARTEFACT, meshcut.META):
        assert (tmp_path / "one/out" / name).read_bytes() == (
            tmp_path / "two/out" / name
        ).read_bytes()


def test_job_refuses_wrong_sha(tmp_path, monkeypatch):
    """A mesh whose sha256 is not the job's committed mesh_sha256 is refused before it is read."""
    results, d = _fixture_job(tmp_path, mesh_sha="0" * 64)
    out = tmp_path / "out"
    out.mkdir()
    (out / "mesh.msh").write_bytes(FIXTURE.read_bytes())

    def never(*a, **k):
        raise AssertionError("the mesh was read")

    monkeypatch.setattr(msh, "read", never)
    with pytest.raises(job.MeshShaMismatch, match="0" * 64):
        job.cut(out / "mesh.msh", job_dir=d, results_root=results, xs=_fixture_xs(), kx=0.0,
                depth_um=0.1, source="cache", out=out)  # fmt: skip
    assert not (out / meshcut.ARTEFACT).exists()


def test_job_window_follows_the_rule_from_the_cross_section(tmp_path):
    xs = _fixture_xs()
    x_um, y_um, rule = job.gate_window(xs, kx=0.5, depth_um=0.15)
    assert rule == {
        "depth_um": 0.15, "gate_x_um": (0.0, 0.5), "kx": 0.5, "poly_top_um": 0.2,
        "surface_um": 0.0,
    }  # fmt: skip
    assert (x_um, y_um) == window.rule_bounds(
        gate_x_um=(0.0, 0.5), poly_top_um=0.2, surface_um=0.0, kx=0.5, depth_um=0.15
    )


def test_job_refuses_a_mesh_whose_gate_is_not_the_cross_section_s(tmp_path):
    with pytest.raises(job.JobMismatch, match="gate_poly"):
        _cut_fixture(tmp_path, xs=_fixture_xs(gate_u=(0.1, 0.5)))
    with pytest.raises(job.JobMismatch, match="gate_poly"):
        _cut_fixture(tmp_path / "b", xs=_fixture_xs(t_ox_nm=90.0))


def test_net_doping_uses_the_job_s_frames_and_region_bounds(tmp_path):
    """Donors minus acceptors of the job's profiles, each region's in its own frame (body:
    depth below the silicon surface; poly: height above the poly bottom), bound to the whole
    region's bounds in the full mesh, as gplugins.devsim.doping.assign_doping does."""
    _BOUNDS.clear()
    _, out, _ = _cut_fixture(tmp_path, depth_um=0.2)
    w = meshcut.read(out)
    x = w.nodes_cm[:, 0] * meshcut.UM_PER_MSH_UNIT
    y = w.nodes_cm[:, 1] * meshcut.UM_PER_MSH_UNIT
    body = y <= 0.0
    poly = y >= 0.1
    assert np.all(body | poly)  # the fixture has no node in the oxide only
    want = np.where(body, 1e15 + 1e16 * x + 1e17 * (-(y - 0.0)) - 2e15, 1e20 + 1e19 * (y - 0.1))
    assert np.allclose(w.net_doping_cm3, want, rtol=1e-12, atol=0)
    # body: x 0..0.5 um, depth 0..0.2 um; poly: x 0..0.5 um, height 0..0.1 um (full regions)
    got = {tuple(round(v, 9) for v in xr + yr) for xr, yr in _BOUNDS}
    assert got == {(0.0, 0.5, 0.0, 0.2), (0.0, 0.5, 0.0, 0.1)}


def test_net_doping_is_zero_off_silicon(tmp_path):
    mesh = msh.read(FIXTURE)
    w = window.cut(mesh, x_um=(0.0, 0.5), y_um=(0.01, 0.09))  # the oxide row only
    xs = _fixture_xs(doping={"body": ((_Lin(1.0),), ()), "gate_poly": ((_Lin(2.0),), ())})
    nd = job.net_doping(mesh, w, xs)
    y = w.nodes_cm[:, 1] * meshcut.UM_PER_MSH_UNIT
    # oxide nodes on the body interface get the body's value, on the poly interface the poly's
    assert np.array_equal(nd, np.where(y <= 0.0, 1.0, 2.0))


def test_doping_frames_are_the_jobs():
    """job.doping_frames repeats moscap2d.build_device's ``surfaces``, which a 2D job uses for
    assign_doping; this ties the two texts together."""
    src = (REPO / "src/gf180tcad/tcad/moscap2d.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src)) if getattr(n, "name", "") == "build_device")
    assigns = [
        ast.unparse(n.value)
        for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["surfaces"]
    ]
    assert assigns == ["{stack_mod.BODY: (0.0, -1), stack_mod.POLY: (xs.t_ox_nm * 0.001, 1)}"]
    frames = job.doping_frames(SimpleNamespace(t_ox_nm=16.05))
    assert frames == {"body": (0.0, -1), "gate_poly": (16.05 * 1e-3, 1)}


def test_job_key_reads_the_tree_device_params_and_geometry(tmp_path):
    results, d = _fixture_job(tmp_path)
    assert job.job_key(d, results) == {
        "device": "nfet_05v0", "geometry_id": "w1p0_l0p50", "params": "start",
        "tree": "tcad/moscap2d",
    }  # fmt: skip
    other = results / "tcad" / "meshconv" / "nfet_05v0" / "start" / "w1p0_l0p50"
    other.mkdir(parents=True)
    with pytest.raises(ValueError, match="tcad/moscap2d"):
        job.job_key(other, results)
    with pytest.raises(ValueError, match="results"):
        job.job_key(tmp_path / "elsewhere" / "a" / "b" / "c", results)


@pytest.mark.parametrize(
    "rel",
    sorted(p.parent.relative_to(MOSCAP2D).as_posix() for p in MOSCAP2D.glob("*/*/*/cv.meta.json")),
)
def test_committed_2d_jobs_tie_to_today_s_parameters(rel):
    """job.load_params reproduces each committed 2D job's param_sha256 and geometry on the host,
    so a cut job can prove it rebuilt the job's own cross-section."""
    d = MOSCAP2D / rel
    cv_meta = json.loads((d / "cv.meta.json").read_bytes())
    proc, geometry = job.load_params(d, cv_meta)
    assert proc.device == cv_meta["device"]
    assert geometry.l_um == cv_meta["l_um"] and geometry.w_um == cv_meta["w_um"]


def test_load_params_refuses_a_job_from_other_parameters(tmp_path):
    d = tmp_path / "nfet_05v0" / "calibrated" / "w10p0_l0p60"
    d.mkdir(parents=True)
    cv_meta = json.loads((L0P60 / "cv.meta.json").read_bytes())
    cv_meta["param_sha256"] = "f" * 64
    with pytest.raises(job.JobMismatch, match="param_sha256"):
        job.load_params(d, cv_meta)


def test_check_cross_section_refuses_another_structure():
    cv_meta = {"l_um": 0.6, "t_ox_nm": 16.0, "sd_peak_cm3": 1e20, "with_sd": True}
    ok = SimpleNamespace(l_um=0.6, t_ox_nm=16.0, sd_peak_cm3=1e20, with_sd=True)
    job.check_cross_section(ok, cv_meta)
    for field, value in (
        ("l_um", 0.7),
        ("t_ox_nm", 15.0),
        ("sd_peak_cm3", 1e19),
        ("with_sd", False),
    ):
        bad = SimpleNamespace(**{**vars(ok), field: value})
        with pytest.raises(job.JobMismatch, match=field):
            job.check_cross_section(bad, cv_meta)
