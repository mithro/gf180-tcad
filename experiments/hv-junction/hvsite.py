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
POLY = (-0.20, 0.0)
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
    "sub": 3.5e15,
    "nw": [{"peak": 2.5e17, "rp": 0.32, "sy": 0.13, "sx": 0.08},
           {"peak": 3e16, "rp": 0.9, "sy": 0.5, "sx": 0.35}],
    "dnw": [{"peak": 4e16, "rp": 1.5, "sy": 0.7, "sx": 0.5}],
    "pw": [{"peak": 4e17, "rp": 0.32, "sy": 0.13, "sx": 0.08},
           {"peak": 4e16, "rp": 0.8, "sy": 0.4, "sx": 0.3}],
    "pplus": [{"peak": 5e19, "rp": 0.0, "sy": 0.08, "sx": 0.08}],
    "nplus": [{"peak": 1e20, "rp": 0.0, "sy": 0.08, "sx": 0.08}],
    "qf": 0.0,
    # "everywhere": the foundry generates P-well wherever there is no N-well, deep N-well
    # (kept 1.5 um away, rule LPW.11) or NAT. "drawn": only where the layout draws it.
    "pwell": "everywhere",
}  # fmt: skip


def _boxes(x0, x1, implants):
    return [{"x0": x0, "x1": x1, **g} for g in implants]


def section(struct, process=None, corner=None, vmax=140.0, gate_v=0.0):
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
    d = 0.0
    for gap, rw in s["rings"]:
        d += gap
        wells += _boxes(edge + d, edge + d + rw, pr["nw"])
        probes.append([edge + d + rw / 2, pr["nw"][0]["rp"]])
        d += rw
    # P side: the P+ ring, and the P-well according to the assumption
    ring0 = edge + term
    pfield = _boxes(ring0, ring0 + s["ncomp_w"], pr["pplus"])
    far = width + 10.0
    if s["pwell_gap"] is not None:
        pfield += _boxes(edge + s["pwell_gap"], far, pr["pw"])
    elif pr["pwell"] == "everywhere":
        if s["nat_gap"] is not None:
            start = ring0 - 0.5  # P-well only beyond the NAT region
            if s["nat_gap"] > 0.01:  # and in the strip between the well and the NAT layer
                pfield += _boxes(edge, edge + s["nat_gap"], pr["pw"])
        else:
            start = edge + (1.5 if s["kind"] == "dnw" else 0.0)
        pfield += _boxes(start, far, pr["pw"])
    plates = []
    top = 1.5
    for layer, length in s["plates"].items():
        y0, y1 = LAYER_Y[layer]
        if s["gate"]:
            x0 = edge - 1.0
        else:
            x0 = edge - inset + 0.4 if layer == "poly" else edge - inset - w
        plates.append({"x0": x0, "x1": edge + length, "y0": y0, "y1": y1,
                       "tie": "gate" if s["gate"] else "well"})  # fmt: skip
        top = max(top, -y0 + 1.5)
    c0, c1 = edge - inset - w, edge - inset
    wells += _boxes(c0, c1, pr["nplus"])  # the N+ contact ring
    sti = [[c1, ring0], [ring0 + s["ncomp_w"], width]]
    if c0 > 0.3:
        sti.insert(0, [0.0, c0])
    return {
        "width": width, "depth": 18.0, "ox_top": top, "sub": pr["sub"],
        "cyl": corner is not None,
        "wells": wells, "pfield": pfield, "sti": sti, "sti_depth": STI,
        "contacts": {"well": [c0, c1], "sub": [ring0, ring0 + s["ncomp_w"]]},
        "plates": plates, "qf": pr["qf"], "gate_v": gate_v,
        "mesh": {"fine": 0.05, "surf": 0.02, "coarse": 0.5},
        "vmax": vmax, "vstep": 4.0, "probes": probes, "extended": False,
    }  # fmt: skip
