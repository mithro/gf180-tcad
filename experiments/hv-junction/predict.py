# SPDX-License-Identifier: Apache-2.0
"""The prediction cases: every structure of the test die under each process assumption.

    uv run python experiments/hv-junction/predict.py OUT.json [SET]

structures.json is the structure list exported by mithro/evampire
(silicon/hvtest/export.py). Each structure is simulated as a straight edge and as a round
corner of its corner radius, under the process assumptions of PROCESSES. Case names are
<structure>|<process>|<edge or corner>, with @g0 or @gw for a gated plate held at 0 V or
tied to the well.

SET "main" is every structure under the four main assumptions; "family" is a few key
structures under the lighter and heavier substrate.
"""

from __future__ import annotations

import json
import pathlib
import sys

import hvsite

HERE = pathlib.Path(__file__).resolve().parent

# A: the foundry generates P-well everywhere it can. B: only drawn P-well exists.
# q: with a fixed oxide charge of 1e11 cm^-2 at the silicon surface.
PROCESSES = {
    "A": {"pwell": "everywhere"},
    "B": {"pwell": "drawn"},
    "Aq": {"pwell": "everywhere", "qf": 1e11},
    "Bq": {"pwell": "drawn", "qf": 1e11},
}
FAMILY = {
    "Blo": {"pwell": "drawn", "sub": 2e15},
    "Bhi": {"pwell": "drawn", "sub": 5e15},
    "Alo": {"pwell": "everywhere", "sub": 2e15},
    "Ahi": {"pwell": "everywhere", "sub": 5e15},
    # substrate doping rising to 4e16 cm^-3 about 5 um down
    "Bdp": {"pwell": "drawn", "deep_p": [{"peak": 4e16, "rp": 5.0, "sy": 0.8, "sx": 0.8}]},
    "Bq3": {"pwell": "drawn", "qf": 3e11},
}
KEY = ["NT20", "NC0", "NA0p6", "NAM1_6", "NW3", "NR3_2", "NM1_6", "DT20", "DM1_6", "DW6"]
MIN_CORNER = 2.0  # a drawn sharp corner still has about this radius after diffusion


def structures():
    data = json.loads((HERE / "structures.json").read_text())
    return {k: v for k, v in data.items() if v["kind"] != "open" and v.get("block", True)}


def cases(names, processes):
    out = {}
    for name in names:
        st = STRUCTS[name]
        variants = [("", st)]
        if st["gate"]:
            variants = [("@g0", st), ("@gw", st)]
        for tag, s in variants:
            for pname, proc in processes.items():
                a_like = proc["pwell"] == "everywhere" and s["nat_gap"] is None
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
                    p["mesh"] = ({"fine": 0.07, "surf": 0.03, "coarse": 0.6} if a_like
                                 else {"fine": 0.1, "surf": 0.04, "coarse": 0.6})
                    if tag == "@gw":  # the gate pad connected to the well pad
                        for pl in p["plates"]:
                            pl["tie"] = "well"
                    out[f"{name}{tag}|{pname}|{shape}"] = p
    return out


STRUCTS = structures()

if __name__ == "__main__":
    which = sys.argv[2] if len(sys.argv) > 2 else "main"
    got = cases(sorted(STRUCTS), PROCESSES) if which == "main" else cases(KEY, FAMILY)
    json.dump(got, open(sys.argv[1], "w"), indent=1)
    print(f"{len(got)} cases")
