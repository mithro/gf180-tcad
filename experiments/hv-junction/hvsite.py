# SPDX-License-Identifier: Apache-2.0
"""Translate one test-die structure into the parameters of its 2D cross-section.

The structure dictionary is the one the layout generator of mithro/evampire
(silicon/hvtest/junction.py) draws, so the simulated section and the drawn structure come
from the same numbers: well kind, inset of the N+ ring, termination length, rings, plates,
drawn P-well and NAT gaps. What the layout does not fix is the process: the `process`
dictionary holds the doping family member and the assumption about the generated P-well.

Section: x along a radius of the structure, x = 0 a symmetry plane 8 um inside the well
edge. With `corner` the section is taken in cylindrical coordinates about the centre of
a corner of that radius.
"""

from __future__ import annotations

STI = 0.32
# The poly plate is lifted 10 nm off the trench oxide's top, so that it lies wholly inside
# the dielectric region and its contact fixes the potential on every side. With its bottom
# face on the boundary between the two oxide regions the trench oxide under it was left
# floating, and every poly-plate result was wrong.
POLY = (-0.21, -0.01)
M1 = (-1.41, -0.86)
M2 = (-2.56, -2.01)
LAYER_Y = {"poly": POLY, "m1": M1, "m2": M2}

DEFAULT_STRUCT = {
    "kind": "nw", "inset": 2.0, "ncomp_w": 2.0, "term": 20.0, "rings": [], "plates": {},
    "pwell_gap": None, "nat_gap": None, "gate": False,
}  # fmt: skip

# One member of the doping family. Each well is a sum of Gaussian implants: peak cm^-3,
# depth of the peak, vertical and lateral standard deviations in um. The N-well and the
# P-well are a shallow heavy part, which sets the 10 to 14 V junctions the PDK publishes
# (N+/P-well 11 V, P+/N-well 10.5 V, N-well/P-well 14 V), and a deeper light part, which
# with the substrate sets the published N-well capacitance and sheet resistance.
DEFAULT_PROCESS = {
    "sub": 3.56e15,
    "nw": [{"peak": 2.5e17, "rp": 0.32, "sy": 0.13, "sx": 0.08},
           {"peak": 4.63e16, "rp": 1.42, "sy": 0.41, "sx": 0.29}],
    "dnw": [{"peak": 2e17, "rp": 2.55, "sy": 0.3, "sx": 0.3}],
    "pw": [{"peak": 4e17, "rp": 0.32, "sy": 0.13, "sx": 0.08},
           {"peak": 4e16, "rp": 0.8, "sy": 0.4, "sx": 0.3}],
    "pplus": [{"peak": 5e19, "rp": 0.0, "sy": 0.08, "sx": 0.08}],
    "nplus": [{"peak": 1e20, "rp": 0.0, "sy": 0.08, "sx": 0.08}],
    "qf": 0.0,
    # A P layer about 4.4 um down, which the deep N-well's capacitance model and its 30 V
    # breakdown need (fit.py). The N-well's capacitance model, which reaches only 10 V,
    # cannot tell whether that layer lies under deep N-well only ("dnw") or under the
    # whole wafer ("blanket"); "none" leaves it out.
    "deep_p": [{"peak": 4.99e17, "rp": 4.36, "sy": 0.3, "sx": 0.3}],
    "deep_p_where": "dnw",
    # whether the generated P-well fills the strip between an N-well and a NAT region
    "nat_strip": True,
    # "everywhere": the foundry generates P-well wherever there is no N-well, deep N-well
    # (kept 1.5 um away, rule LPW.11) or NAT. "drawn": only where the layout draws it.
    "pwell": "everywhere",
}  # fmt: skip


def _boxes(x0, x1, implants):
    return [{"x0": x0, "x1": x1, **g} for g in implants]


def section(struct, process=None, corner=None, vmax=140.0, gate_v=0.0, ring_grounded=False):
    """ring_grounded: ring 1 gets the contact its sense pad has, held at 0 V while the well
    is swept: the punch-through measurement between a well and a neighbouring well."""
    s = {**DEFAULT_STRUCT, **struct}
    pr = {**DEFAULT_PROCESS, **(process or {})}
    edge = 8.0 if corner is None else max(float(corner), 1.0)
    inset = min(s["inset"], edge / 2)
    w = min(s["ncomp_w"], edge - inset - 0.2)
    term = s["term"]
    width = edge + term + s["ncomp_w"] + 3.0
    well = pr["nw"] if s["kind"] == "nw" else pr["dnw"]
    wells = _boxes(-10.0, edge, well)
    probes = []
    ring_spans = []
    d = 0.0
    for gap, rw in s["rings"]:
        d += gap
        ring_spans.append((edge + d, edge + d + rw))
        wells += _boxes(edge + d, edge + d + rw, pr["nw"])
        probes.append([edge + d + rw / 2, pr["nw"][0]["rp"]])
        d += rw
    # P side: the P+ ring, and the P-well according to the assumption
    ring0 = edge + term
    pfield = _boxes(ring0, ring0 + s["ncomp_w"], pr["pplus"])
    far = width + 10.0
    if s["pwell_gap"] is not None and pr["pwell"] != "everywhere":
        # a drawn P-well; where the P-well is generated anyway it is the same implant, and
        # drawing it adds nothing
        pfield += _boxes(edge + s["pwell_gap"], far, pr["pw"])
    if pr["pwell"] == "everywhere":
        if s["nat_gap"] is not None:
            start = ring0 - 0.5  # P-well only beyond the NAT region
            if s["nat_gap"] > 0.01 and pr["nat_strip"]:
                # and in the strip that rule NAT.3 leaves between an N-well and the NAT layer
                pfield += _boxes(edge, edge + s["nat_gap"], pr["pw"])
                # and in the 0.6 um strips the NAT layer leaves on each side of a ring
                for ra, rb in ring_spans:
                    pfield += _boxes(ra - 0.6, ra, pr["pw"])
                    pfield += _boxes(rb, rb + 0.6, pr["pw"])
        else:
            start = edge + (1.5 if s["kind"] == "dnw" else 0.0)
        # the generated P-well is the complement of the N-well layer: none where a ring is
        x = start
        for a, b in ring_spans:
            if a > x:
                pfield += _boxes(x, a, pr["pw"])
            x = max(x, b)
        pfield += _boxes(x, far, pr["pw"])
    if pr["deep_p_where"] == "blanket":
        pfield += _boxes(-10.0, far, pr["deep_p"])
    elif pr["deep_p_where"] == "dnw" and s["kind"] == "dnw":
        pfield += _boxes(-10.0, edge, pr["deep_p"])
    plates = []
    top = 1.5
    for layer, length in s["plates"].items():
        y0, y1 = LAYER_Y[layer]
        if s["gate"]:
            x0 = edge - 0.5
        else:
            x0 = edge - inset + 0.4 if layer == "poly" else edge - inset - w
        plates.append({"x0": x0, "x1": edge + length, "y0": y0, "y1": y1,
                       "tie": "gate" if s["gate"] else "well"})  # fmt: skip
        top = max(top, -y0 + 1.5)
    c0, c1 = edge - inset - w, edge - inset
    wells += _boxes(c0, c1, pr["nplus"])  # the N+ contact ring
    if s["kind"] == "dnw":  # the N-well drawn under the contact ring of a deep N-well
        wells += _boxes(c0 - 0.3, c1 + 0.3, pr["nw"])
    sti = [[c1, ring0], [ring0 + s["ncomp_w"], width]]
    if c0 > 0.3:
        sti.insert(0, [0.0, c0])
    contacts = {"well": [c0, c1], "sub": [ring0, ring0 + s["ncomp_w"]]}
    if ring_grounded:
        a, b = ring_spans[0]
        mid = (a + b) / 2
        tap = [mid - 0.3, mid + 0.3]  # the 0.6 um N+ tap of the sense pad
        k = next(i for i, (x0, x1) in enumerate(sti) if x0 < tap[0] and tap[1] < x1)
        sti[k : k + 1] = [[sti[k][0], tap[0]], [tap[1], sti[k][1]]]
        wells += _boxes(tap[0], tap[1], pr["nplus"])
        contacts["ring"] = tap
    return {
        "width": width, "depth": 18.0, "ox_top": top, "sub": pr["sub"],
        "cyl": corner is not None,
        "wells": wells, "pfield": pfield, "sti": sti, "sti_depth": STI,
        "contacts": contacts,
        "plates": plates, "qf": pr["qf"], "gate_v": gate_v,
        "mesh": {"fine": 0.05, "surf": 0.02, "coarse": 0.5},
        "vmax": vmax, "vstep": 4.0, "probes": probes, "extended": False,
    }  # fmt: skip
