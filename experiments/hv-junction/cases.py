# SPDX-License-Identifier: Apache-2.0
"""Parameter dictionaries of the well-edge cases (see structure.py for the keys).

    uv run python experiments/hv-junction/cases.py SET OUT.json

A case is a base cross-section plus overrides. Lengths in um. The high-voltage N-well
occupies x < EDGE; its contact is at the left; the substrate tap is at the right end.
"""

from __future__ import annotations

import json
import sys

import hvsite as site

EDGE = 6.0  # drawn N-well edge
INSET = 2.0  # the N+ contact ring (end of the trench) sits this far inside the well edge
STI = 0.32  # extraction thickness of the trench oxide (interconnect spec, table 2.2)

# Vertical positions of conductors above the active surface (y is negative upwards).
# Poly sits on the trench oxide, whose top is level with the active surface.
POLY = (-0.20, 0.0)  # 0.2 um poly directly on the STI
M1 = (-1.41, -0.86)  # 0.86 um ILD, 0.55 um metal
M2 = (-2.56, -2.01)
M3 = (-3.71, -3.16)

NWELL = {"peak": 9e16, "rp": 0.5, "sy": 0.4, "sx": 0.3}
PWELL = {"peak": 1e17, "rp": 0.5, "sy": 0.4, "sx": 0.3}


def base(reach=25.0, sub=3.5e15, nwell=NWELL, vmax=140.0, edge=EDGE, cyl=False):
    """A bare N-well edge in uniform substrate, trench oxide from the well contact to the tap.

    The trench starts INSET inside the well edge, as on the layout. With cyl the section
    is a round corner of radius `edge`."""
    width = edge + reach
    inset = min(INSET, edge / 2)
    return {
        "width": width, "depth": 18.0, "ox_top": 1.5, "sub": sub, "cyl": cyl,
        "wells": [{"x0": -10.0, "x1": edge, **nwell}],
        "pfield": [],
        "sti": [[edge - inset, width - 2.0]], "sti_depth": STI,
        "contacts": {"well": [0.0, (edge - inset) * 0.75], "sub": [width - 1.5, width]},
        "plates": [], "qf": 0.0,
        "mesh": {"fine": 0.05, "surf": 0.02, "coarse": 0.5},
        # double precision and 4 V steps reproduce the 128-bit, 2 V result of the first
        # case to 0.2 V (77.44 V both precisions; 77.57 V with 5 V steps)
        "vmax": vmax, "vstep": 4.0, "probes": [], "extended": False,
    }  # fmt: skip


def stop_early(p, vstep=2.0):
    """Finer steps for cases that break down below about 40 V."""
    p["vstep"] = vstep
    return p


def with_pwell(p, gap, pwell=PWELL):
    """Add the generated P-well starting `gap` beyond the N-well edge, to the right end."""
    p["pfield"] = [{"x0": EDGE + gap, "x1": p["width"] + 10.0, **pwell}]
    return p


def with_plate(p, layer, length, tie="well", start=EDGE - 1.0):
    """A field plate on `layer` from `start` to `length` beyond the well edge."""
    y0, y1 = layer
    p["ox_top"] = max(p["ox_top"], -y0 + 1.5)
    p["plates"] = p["plates"] + [{"x0": start, "x1": EDGE + length, "y0": y0, "y1": y1, "tie": tie}]
    return p


def with_rings(p, gaps, width=2.0, nwell=NWELL):
    """Floating N-well rings: gaps[k] is the space before ring k, each `width` wide."""
    x = EDGE
    for g in gaps:
        x += g
        p["wells"] = p["wells"] + [{"x0": x, "x1": x + width, **nwell}]
        p["probes"] = p["probes"] + [[x + width / 2, nwell["rp"]]]
        x += width
    return p


def scan1():
    """First scan: where the generated P-well is, its strength, and the substrate doping."""
    out = {}
    for sub in (2e15, 3.5e15, 5e15):
        out[f"bare-sub{sub:.1e}"] = base(sub=sub)
    for peak in (5e16, 1e17, 2e17):
        for gap in (0.0, 0.5, 1.5, 3.0, 6.0):
            case = with_pwell(base(vmax=100.0), gap, {**PWELL, "peak": peak})
            out[f"pw{peak:.0e}-gap{gap}"] = stop_early(case) if gap < 1.0 else case
    return out


def corners():
    """Round corners of several radii in cylindrical coordinates."""
    out = {}
    for sub in (2e15, 3.5e15, 5e15):
        for r in (1.0, 3.0, 6.0, 12.0, 25.0):
            out[f"cyl-r{r}-sub{sub:.1e}"] = base(sub=sub, edge=r, cyl=True)
    return out


def meshes():
    """Mesh refinement of the bare edge."""
    out = {}
    for fine, surf in ((0.1, 0.04), (0.05, 0.02), (0.025, 0.01)):
        p = base()
        p["mesh"] = {"fine": fine, "surf": surf, "coarse": 0.5}
        out[f"mesh-f{fine}"] = p
    return out


def calib():
    """An N-well with the P-well abutting: which lateral spread and P-well strength give
    the published 14 V (typical) / 10 V (minimum) of the N-well to substrate junction."""
    out = {}
    for sx in (0.05, 0.1, 0.2, 0.3):
        for pw in (1e17, 2e17, 4e17):
            for nw in (1.5e17,):
                proc = {"nw": {"peak": nw, "rp": 0.3, "sy": 0.35, "sx": sx},
                        "pw": {"peak": pw, "rp": 0.3, "sy": 0.35, "sx": sx}}  # fmt: skip
                p = site.section({"term": 6.0}, proc, vmax=45.0)
                p["vstep"] = 1.5
                out[f"sx{sx}-pw{pw:.0e}"] = p
    return out


def calib2():
    """The abutting case on a finer mesh, with a stronger N-well surface too."""
    out = {}
    for sx in (0.05, 0.1):
        for nw in (1.5e17, 2.5e17):
            for fine in (0.05, 0.015):
                proc = {"nw": {"peak": nw, "rp": 0.3, "sy": 0.35, "sx": sx},
                        "pw": {"peak": 4e17, "rp": 0.3, "sy": 0.35, "sx": sx}}  # fmt: skip
                p = site.section({"term": 4.0}, proc, vmax=30.0)
                p["vstep"] = 1.0
                p["mesh"] = {"fine": fine, "surf": min(0.02, fine), "coarse": 0.5}
                out[f"sx{sx}-nw{nw:.1e}-f{fine}"] = p
    return out


def calib3():
    """The two-part wells: the N-well against an abutting P-well, bare, and the deep
    N-well (P-well 1.5 um away) for several deep N-well strengths."""
    out = {}
    for fine in (0.05, 0.02):
        p = site.section({"term": 5.0}, vmax=30.0)
        p["vstep"] = 1.0
        p["mesh"] = {"fine": fine, "surf": min(0.02, fine), "coarse": 0.5}
        out[f"nw-abut-f{fine}"] = p
    p = site.section({}, {"pwell": "drawn"})
    out["nw-bare"] = p
    for peak in (2e16, 4e16, 8e16):
        for rp, sy in ((1.5, 0.7), (1.2, 0.5)):
            proc = {"dnw": [{"peak": peak, "rp": rp, "sy": sy, "sx": 0.7 * sy}]}
            p = site.section({"kind": "dnw"}, proc, vmax=80.0)
            p["vstep"] = 2.0
            out[f"dnw-{peak:.0e}-rp{rp}"] = p
    return out


SETS = {"calib3": calib3, "scan1": scan1, "corners": corners, "meshes": meshes, "calib": calib, "calib2": calib2}

if __name__ == "__main__":
    json.dump(SETS[sys.argv[1]](), open(sys.argv[2], "w"), indent=1)
