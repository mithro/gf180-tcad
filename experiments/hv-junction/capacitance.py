# SPDX-License-Identifier: Apache-2.0
"""The N-well's junction capacitance under the two assumptions about the deep P layer.

    uv run --locked python experiments/hv-junction/capacitance.py results/hv-junction/capacitance.json

For each reverse bias of BIAS_V the record holds the capacitance per area of the N-well of
hvsite.DEFAULT_PROCESS, in the depletion approximation of profile1d.py, with no deep P layer
under the well (assumption L) and with the layer under it (assumption D), and the published
junction model's value (MODEL). The ratios to the model are what a measured capacitance sweep
is compared with to tell L from D. The script runs on the host (numpy only) in under a second
and is deterministic; the record also holds the sha256 of the two modules it computes from.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import hvsite
import numpy as np
import profile1d

HERE = pathlib.Path(__file__).resolve().parent
BIAS_V = (0.0, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0)
#: The N-well junction model of the PDK's diode models: area capacitance at 0 V (F/cm^2),
#: grading coefficient and junction potential (V).
MODEL = {"cj0": 1.4914e-8, "mj": 0.30525, "pb": 0.43905}
UM = 1e-4


def compute() -> dict:
    pr = hvsite.DEFAULT_PROCESS
    y = np.linspace(0, 16 * UM, 32001)
    volts = np.array(BIAS_V)

    def boxes(implants):
        return [(g["peak"], g["rp"] * UM, g["sy"] * UM) for g in implants]

    bare, _ = profile1d.net(y, boxes(pr["nw"]), pr["sub"])
    layer, _ = profile1d.net(y, boxes(pr["nw"]), pr["sub"], boxes(pr["deep_p"]))
    model = profile1d.model_c(volts, MODEL["cj0"], MODEL["mj"], MODEL["pb"])
    out = {"bias_v": list(BIAS_V), "model_f_cm2": [float(c) for c in model]}
    for key, profile in (("L", bare), ("D", layer)):
        c = profile1d.cv(y, profile, volts)
        out[key] = {
            "c_f_cm2": [float(v) for v in c],
            "over_model": [float(v) for v in c / model],
        }
    return out


def pins() -> dict:
    return {
        f: hashlib.sha256((HERE / f).read_bytes()).hexdigest()
        for f in ("capacitance.py", "hvsite.py", "profile1d.py")
    }


if __name__ == "__main__":
    doc = {"schema": 1, "model": MODEL, "pins": pins(), **compute()}
    pathlib.Path(sys.argv[1]).write_text(json.dumps(doc, indent=1) + "\n")
    for key in ("L", "D"):
        print(key, " ".join(f"{r:.3f}" for r in doc[key]["over_model"]))
