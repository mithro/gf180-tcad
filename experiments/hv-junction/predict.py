# SPDX-License-Identifier: Apache-2.0
"""The prediction cases: every structure of the test die under each process assumption.

    uv run python experiments/hv-junction/predict.py OUT.json [SET] [RECORD.json ...]

structures.json is the structure list exported by mithro/evampire
(silicon/hvtest/export.py). Each structure is simulated as a straight edge and as a round
corner of its corner radius, under the process assumptions of PROCESSES. Case names are
<structure>|<process>|<edge or corner>, with @g0 or @gw for a gated plate held at 0 V or
tied to the well.

SET "main" is every structure under the main assumptions. SET "family" is a few key
structures under the lighter and heavier substrate and a higher oxide charge. SET "rest
RECORD.json ..." is every case of "main" that the records named do not hold with its present
parameters. SET "p5" is each ring-sense structure with its first ring held at 0 V.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import hvsite

HERE = pathlib.Path(__file__).resolve().parent

# Where the P-well is. A: the foundry generates it wherever no N-well, deep N-well or NAT
# is drawn. An: as A, but not in the strip between an N-well and NAT. B: only where drawn.
# Where the deep P layer is. L: only under deep N-well. D: under the whole wafer.
# q: with a fixed oxide charge of 1e11 cm^-2 at the silicon surface.
L_, D_ = {"deep_p_where": "dnw"}, {"deep_p_where": "blanket"}
PROCESSES = {
    "AL": {"pwell": "everywhere", **L_},
    "AD": {"pwell": "everywhere", **D_},
    "BL": {"pwell": "drawn", **L_},
    "BD": {"pwell": "drawn", **D_},
    "BLq": {"pwell": "drawn", "qf": 1e11, **L_},
}
NAT_ONLY = {
    "AnL": {"pwell": "everywhere", "nat_strip": False, **L_},
    "AnD": {"pwell": "everywhere", "nat_strip": False, **D_},
}
FAMILY = {
    "BLlo": {"pwell": "drawn", "sub": 2e15, **L_},
    "BLhi": {"pwell": "drawn", "sub": 5e15, **L_},
    "BDlo": {"pwell": "drawn", "sub": 2e15, **D_},
    "BDhi": {"pwell": "drawn", "sub": 5e15, **D_},
    "BLq3": {"pwell": "drawn", "qf": 3e11, **L_},
    "ALhi": {"pwell": "everywhere", "sub": 5e15, **L_},
}
KEY = ["NT20", "NC0", "NA0p6", "NAM1_6", "NW3", "NR3_2", "NM1_6", "NP2", "DT20", "DM1_6", "DAo1"]
# A drawn sharp corner is simulated as a round one of this radius: about the lateral spread
# of the well's deep part plus the corner rounding of the mask.
MIN_CORNER = 1.0
# The process assumptions of the set "p5".
P5_PROCESSES = ("AL", "BL", "BD")


def structures():
    data = json.loads((HERE / "structures.json").read_text())
    return {k: v for k, v in data.items() if v["kind"] != "open" and v["half"] < 40}


def cases(names, processes):
    out = {}
    for name in names:
        st = STRUCTS[name]
        variants = [("", st)]
        if st["gate"]:
            variants = [("@g0", st), ("@gw", st)]
        for tag, s in variants:
            for pname, proc in processes.items():
                strip = (
                    s["nat_gap"] is not None and s["nat_gap"] > 0 and proc.get("nat_strip", True)
                )
                # an abutting P-well: breakdown below 30 V whatever else is drawn
                a_like = (
                    proc["pwell"] == "everywhere"
                    and s["kind"] == "nw"
                    and (s["nat_gap"] is None or strip)
                )
                if a_like and proc["deep_p_where"] == "blanket":
                    continue  # a layer 4 um down does not reach a junction that breaks at 18 V
                shapes = [("edge", None)]
                if not a_like:  # next to an abutting P-well the corner radius hardly matters
                    shapes.append(("corner", max(s["corner"], MIN_CORNER)))
                for shape, corner in shapes:
                    p = hvsite.section(s, proc, corner=corner)
                    p["vstep"] = 1.5 if a_like else 3.0
                    p["vmax"] = 60.0 if a_like else 150.0
                    p["depth"] = 14.0
                    # mesh spacings: the 0.1 um mesh gives a bare edge within 0.5 % of the 0.05 um one
                    # (73.84 V against 73.51 V), far inside the spread of the doping family
                    # a heavy P region within 1.5 um of the edge (a drawn P-well, or the P+
                    # ring of NT1) needs the fine mesh just as an abutting generated P-well
                    # does: NW0 under B came out 12 % high on the 0.1 um mesh
                    near = (
                        s["pwell_gap"] is not None
                        and s["pwell_gap"] <= 1.5
                        and not a_like
                        and proc["pwell"] != "everywhere"
                    ) or s["term"] <= 2.0
                    p["mesh"] = (
                        {"fine": 0.03, "surf": 0.02, "coarse": 0.6}
                        if a_like or near
                        else {"fine": 0.1, "surf": 0.04, "coarse": 0.6}
                    )
                    if tag == "@gw":  # the gate pad connected to the well pad
                        for pl in p["plates"]:
                            pl["tie"] = "well"
                    out[f"{name}{tag}|{pname}|{shape}"] = p
    return out


STRUCTS = structures()


def digest(params):
    """The sha256 of a case's parameters, as record.py stores it."""
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()


def main_cases():
    """Set "main": every structure under PROCESSES, the NAT structures under NAT_ONLY too."""
    got = cases(sorted(STRUCTS), PROCESSES)
    nat = [n for n, st in STRUCTS.items() if st["nat_gap"] is not None and st["nat_gap"] > 0]
    got.update(cases(sorted(nat), NAT_ONLY))
    return got


def family_cases():
    """Set "family": the KEY structures under FAMILY."""
    return cases([k for k in KEY if k in STRUCTS], FAMILY)


def rest_cases(have):
    """Set "rest": the cases of "main" that the record rows `have` ({case: row}) do not hold
    with their present parameters."""
    return {n: p for n, p in main_cases().items()
            if n not in have or have[n]["params_sha256"] != digest(p)}  # fmt: skip


def p5_cases():
    """Set "p5": ring 1 of each ring-sense structure held at 0 V. The current into the well
    is then the punch-through current that procedure P5 of the test method measures."""
    got = {}
    for name in sorted(n for n, st in STRUCTS.items() if st["sense"]):
        for pname in P5_PROCESSES:
            p = hvsite.section(STRUCTS[name], PROCESSES[pname], ring_grounded=True)
            p["vstep"], p["vmax"], p["depth"] = 1.0, 100.0, 14.0
            p["mesh"] = {"fine": 0.05, "surf": 0.03, "coarse": 0.6}
            got[f"{name}|{pname}|edge"] = p
    return got


if __name__ == "__main__":
    which = sys.argv[2] if len(sys.argv) > 2 else "main"
    if which == "main":
        got = main_cases()
    elif which == "rest":
        have = {}
        for path in sys.argv[3:]:
            have.update(json.loads(pathlib.Path(path).read_text())["cases"])
        got = rest_cases(have)
    elif which == "p5":
        got = p5_cases()
    else:
        got = family_cases()
    with open(sys.argv[1], "w") as out_file:
        json.dump(got, out_file, indent=1)
    print(f"{len(got)} cases")
