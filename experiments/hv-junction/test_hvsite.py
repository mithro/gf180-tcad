"""Host tests of the structure-to-section translation and of the doping family's anchors."""

import numpy as np

import hvsite
import profile1d

UM = 1e-4


def _gauss(implants):
    return [(g["peak"], g["rp"] * UM, g["sy"] * UM) for g in implants]


def test_nwell_profile_meets_the_public_anchors():
    """Sheet resistance 800 to 1200 ohm/sq (electrical spec 5.1) and the zero-bias
    capacitance of diode_nw2ps_06v0, 1.4914e-4 F/m^2, within 15 %."""
    pr = hvsite.DEFAULT_PROCESS
    y = np.linspace(0, 12e-4, 24001)
    n, total = profile1d.net(y, _gauss(pr["nw"]), pr["sub"])
    rs = profile1d.sheet_resistance(y, n, total)
    c0 = profile1d.cv(y, n, np.array([0.0]))[0]
    assert 800 < rs < 1200, rs
    assert abs(c0 - 1.4914e-8) / 1.4914e-8 < 0.15, c0


def _acceptor_starts(p):
    return sorted(b["x0"] for b in p["pfield"] if b["peak"] < 1e19)


def test_generated_pwell_abuts_an_nwell_but_not_a_deep_nwell():
    edge = 8.0
    a = hvsite.section({}, {"pwell": "everywhere"})
    assert _acceptor_starts(a)[0] == edge
    d = hvsite.section({"kind": "dnw"}, {"pwell": "everywhere"})
    assert _acceptor_starts(d)[0] == edge + 1.5
    b = hvsite.section({}, {"pwell": "drawn"})
    assert _acceptor_starts(b) == []


def test_nat_keeps_the_pwell_out_to_the_ring():
    p = hvsite.section({"nat_gap": 0.6, "term": 20.0}, {"pwell": "everywhere"})
    starts = _acceptor_starts(p)
    assert starts[0] == 8.0  # the strip between the well and the NAT layer
    assert max(starts) == 8.0 + 20.0 - 0.5


def test_plates_and_rings_follow_the_layout():
    p = hvsite.section({"plates": {"poly": 2.0, "m1": 5.0}, "rings": [[2.0, 2.0], [2.5, 2.0]]})
    poly, m1 = p["plates"]
    assert (poly["x1"], m1["x1"]) == (10.0, 13.0)
    assert poly["y1"] == 0.0 and m1["y1"] == -0.86
    ring_boxes = [w for w in p["wells"] if w["x0"] > 8.0]
    assert sorted({w["x0"] for w in ring_boxes}) == [10.0, 14.5]
    assert len(p["probes"]) == 2


def test_a_drawn_pwell_adds_nothing_when_pwell_is_generated_everywhere():
    plain = hvsite.section({}, {"pwell": "everywhere"})
    drawn = hvsite.section({"pwell_gap": 6.0}, {"pwell": "everywhere"})
    assert _acceptor_starts(drawn)[0] == _acceptor_starts(plain)[0] == 8.0
    assert _acceptor_starts(hvsite.section({"pwell_gap": 6.0}, {"pwell": "drawn"})) == [14.0, 14.0]


def test_nat_overlapping_a_deep_nwell_leaves_no_pwell_beside_it():
    p = hvsite.section({"kind": "dnw", "nat_gap": -1.0}, {"pwell": "everywhere"})
    assert min(_acceptor_starts(p)) == 8.0 + 20.0 - 0.5
