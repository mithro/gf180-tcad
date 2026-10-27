# SPDX-License-Identifier: Apache-2.0
"""The readers of :mod:`gf180tcad.quantity`: the closed selector set, each reader and the
canonical hash of an array."""

import gzip
import json
import math

import numpy as np
import pytest

from gf180tcad import quantity


def test_selector_kinds_closed():
    assert quantity.SELECTOR_KINDS == ("csv", "json", "npz", "toml")
    good = [
        {"json": ["stack", "t_ox_nm"]},
        {"json": ["levels", 0, "node_count"]},
        {"csv": {"columns": ["vg"], "rows": "all"}},
        {"csv": {"columns": ["vg", "c"], "where": {"vg": -5.0}}},
        {"csv": {"columns": ["c"], "index": 3}},
        {"npz": "nodes_um"},
        {"toml": ["silicon", "band_gap_ev"]},
    ]
    for d in good:
        assert quantity.Selector.from_dict(d).to_dict() == d
    bad = [
        {"xpath": "/a"},
        {"json": ["a"], "toml": ["a"]},
        {},
        {"json": []},
        {"json": ["a", 1.5]},
        {"json": ["a", True]},
        {"toml": ["a", 0]},
        {"npz": ""},
        {"csv": {"columns": ["vg"]}},
        {"csv": {"columns": ["vg"], "rows": "some"}},
        {"csv": {"columns": ["vg"], "rows": "all", "index": 0}},
        {"csv": {"columns": [], "rows": "all"}},
        {"csv": {"columns": ["vg"], "where": {"vg": 1.0, "c": 2.0}}},
        {"csv": {"columns": ["vg"], "index": -1}},
        {"csv": {"columns": ["vg"], "rows": "all", "extra": 1}},
    ]
    for d in bad:
        with pytest.raises(ValueError):
            quantity.Selector.from_dict(d)


def test_json_and_toml_readers(tmp_path):
    j = tmp_path / "a.json"
    j.write_text(json.dumps({"levels": [{"n": 3}, {"n": 5}], "s": "x"}), encoding="utf-8")
    assert quantity.read(quantity.Selector.from_dict({"json": ["levels", 1, "n"]}), j) == 5
    assert quantity.read(quantity.Selector.from_dict({"json": ["s"]}), j) == "x"
    with pytest.raises(KeyError, match="no key"):
        quantity.read(quantity.Selector.from_dict({"json": ["levels", 2, "n"]}), j)
    t = tmp_path / "a.toml"
    t.write_text("[silicon]\nband_gap_ev = 1.12\n", encoding="utf-8")
    assert (
        quantity.read(quantity.Selector.from_dict({"toml": ["silicon", "band_gap_ev"]}), t) == 1.12
    )


def test_csv_reader(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("# device: x\nvg,c\n-1.0,2.0\n0.0,3.0\n1.0,2.5\n", encoding="utf-8")

    def sel(spec):
        return quantity.Selector.from_dict({"csv": spec})

    vg = quantity.read(sel({"columns": ["vg"], "rows": "all"}), p)
    assert isinstance(vg, np.ndarray) and vg.tolist() == [-1.0, 0.0, 1.0]
    both = quantity.read(sel({"columns": ["vg", "c"], "rows": "all"}), p)
    assert [a.tolist() for a in both] == [[-1.0, 0.0, 1.0], [2.0, 3.0, 2.5]]
    assert quantity.read(sel({"columns": ["c"], "where": {"vg": 0.0}}), p) == 3.0
    assert quantity.read(sel({"columns": ["vg", "c"], "index": 2}), p) == (1.0, 2.5)
    with pytest.raises(ValueError, match="no row"):
        quantity.read(sel({"columns": ["c"], "where": {"vg": 0.5}}), p)
    with pytest.raises(KeyError, match="no column"):
        quantity.read(sel({"columns": ["id"], "rows": "all"}), p)
    with pytest.raises(IndexError):
        quantity.read(sel({"columns": ["c"], "index": 3}), p)
    dup = tmp_path / "dup.csv"
    dup.write_text("vg,c\n0.0,1.0\n0.0,2.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="2 rows"):
        quantity.read(sel({"columns": ["c"], "where": {"vg": 0.0}}), dup)


def test_csv_reader_reads_gzip(tmp_path):
    p = tmp_path / "a.csv.gz"
    p.write_bytes(gzip.compress(b"vg,c\n0.0,1.0\n", mtime=0))
    got = quantity.read(quantity.Selector.from_dict({"csv": {"columns": ["c"], "rows": "all"}}), p)
    assert got.tolist() == [1.0]


def test_npz_reader(tmp_path):
    p = tmp_path / "a.npz"
    np.savez(p, nodes_um=np.array([[0.0, 1.0], [2.0, 3.0]]))
    got = quantity.read(quantity.Selector.from_dict({"npz": "nodes_um"}), p)
    assert got.tolist() == [[0.0, 1.0], [2.0, 3.0]]
    with pytest.raises(KeyError, match="no member"):
        quantity.read(quantity.Selector.from_dict({"npz": "triangles"}), p)


def test_canonical_sha256():
    a = quantity.canonical_sha256(np.array([1.0, 0.1 + 0.2]))
    assert a == quantity.canonical_sha256([1.0, 0.30000000000000004])
    assert a == quantity.canonical_sha256((1.0, 0.30000000000000004))
    assert a != quantity.canonical_sha256([1.0, 0.3])
    assert quantity.canonical_sha256([0.0]) != quantity.canonical_sha256([-0.0])
    assert quantity.canonical_sha256(np.array([[1, 2]])) == quantity.canonical_sha256([[1, 2]])
    with pytest.raises(ValueError):
        quantity.canonical_sha256([math.nan])
    # The canonical text: compact JSON, repr floats.
    assert quantity.canonical_json([1.0, [2.5e-17]]) == "[1.0,[2.5e-17]]"


def test_is_array():
    assert quantity.is_array(np.zeros(2)) and quantity.is_array((np.zeros(2), np.zeros(2)))
    assert not quantity.is_array(1.0) and not quantity.is_array("n") and not quantity.is_array(3)


def test_repo_path():
    assert quantity.repo_path("results/tcad/a.json") == "results/tcad/a.json"
    for bad in ["/abs", "..", "a/../b", "a\\b", "", "./a", "a//b"]:
        with pytest.raises(ValueError, match="repo-relative"):
            quantity.repo_path(bad)
