# SPDX-License-Identifier: Apache-2.0
"""Host tests: merging a two-region DEVSIM-style mesh, and the deck text."""

import numpy as np

import charon_deck
import charon_mesh


def _grid_region(xs, ys):
    """Nodes and DEVSIM-style triangles (two per cell) of a tensor grid, plus the grid."""
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    xy = np.stack([gx.ravel(), gy.ravel()], axis=1)
    idx = np.arange(len(xy)).reshape(len(xs), len(ys))
    tri = []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            a, b, c, d = idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1]
            tri += [[a, c, b], [a, d, c]]  # clockwise on purpose: merge must turn them
    return xy, np.array(tri), idx


def _two_regions():
    xs = np.array([0.0, 1e-4, 2e-4])
    xy_si, tri_si, idx_si = _grid_region(xs, np.array([0.0, 1e-4, 3e-4]))
    xy_ox, tri_ox, _ = _grid_region(xs, np.array([-2e-4, 0.0]))
    top = idx_si[:, 0]  # silicon surface nodes, y = 0
    meta = {"regions": [["si", "Si"], ["ox", "Oxide"]], "contacts": {"well": "si"}, "extra": {}}
    arrays = {"xy_si": xy_si, "tri_si": tri_si, "xy_ox": xy_ox, "tri_ox": tri_ox,
              "contact_well": np.array([[top[0], top[1]]])}  # fmt: skip
    return meta, arrays


def test_merge_shares_interface_nodes_and_orients():
    meta, arrays = _two_regions()
    m = charon_mesh.merge(meta, arrays)
    assert len(m["xy_cm"]) == 9 + 6 - 3  # the three surface nodes are shared
    assert np.array_equal(m["xy_cm"][m["node_map"]["si"]], arrays["xy_si"])
    assert np.array_equal(m["xy_cm"][m["node_map"]["ox"]], arrays["xy_ox"])
    for _, _, tri in m["blocks"]:
        a, b, c = (m["xy_cm"][tri[:, k]] for k in range(3))
        ab, ac = b - a, c - a
        area2 = ab[:, 0] * ac[:, 1] - ab[:, 1] * ac[:, 0]
        assert np.all(area2 > 0)
    block, elems, locs = m["sides"]["well"]
    assert block == 0 and len(elems) == 1
    tri = m["blocks"][0][2][elems[0]]
    edge = {int(tri[locs[0]]), int(tri[(locs[0] + 1) % 3])}
    assert edge == {int(g) for g in m["node_map"]["si"][arrays["contact_well"][0]]}


def test_merge_quads():
    meta, arrays = _two_regions()
    m = charon_mesh.merge(meta, arrays, quads=True)
    assert [b[2].shape for b in m["blocks"]] == [(4, 4), (2, 4)]
    quad = m["blocks"][0][2]
    p = m["xy_cm"][quad]
    area = 0.5 * np.abs((p[:, 2, 0] - p[:, 0, 0]) * (p[:, 3, 1] - p[:, 1, 1])
                        - (p[:, 3, 0] - p[:, 1, 0]) * (p[:, 2, 1] - p[:, 0, 1]))  # fmt: skip
    assert np.isclose(area.sum(), 2e-4 * 3e-4)
    assert len(m["sides"]["well"][1]) == 1


def test_deck_doping_matches_structure_expression():
    p = {"sub": 3e15, "wells": [{"x0": -5, "x1": 4, "peak": 9e16, "rp": 0.5, "sy": 0.4, "sx": 0.3}],
         "pfield": [{"x0": 6, "x1": 20, "peak": 1e17, "rp": 0.5, "sy": 0.4, "sx": 0.3}],
         "plates": [{"x0": 3, "x1": 8, "y0": -0.2, "y1": 0.0, "tie": "well"}]}  # fmt: skip
    dev = charon_deck.describe_params(p, [["ox", "Oxide"], ["si", "Si"]])
    net = charon_deck.net_doping(dev, np.array([4.0, 0.0, 12.0]), np.array([0.5, 0.5, 5.0]))
    assert np.isclose(net[0], -3e15 + 9e16 * 0.5, rtol=1e-6)  # on the drawn edge: half the peak
    assert np.isclose(net[1], -3e15 + 9e16, rtol=1e-6)
    assert np.isclose(net[2], -3e15, rtol=1e-3)  # deep under the P field
    text = charon_deck.deck(dev, "sweep", "dd0.exo", "sweep.exo", v1=50.0, step=2.0)
    assert "BC is ohmic for well on si swept from 0 to 50" in text
    assert "BC is contact on insulator for plate0 on ins_ox" in text
    assert "geometry block is ins_ox" in text and "swept from 0 to 50" in text
    assert text.count("start mgauss doping") == 2
    assert "avalanche is on" in text and "electron E0 = 1.231e+06" in text
