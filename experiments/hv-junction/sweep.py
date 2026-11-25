# SPDX-License-Identifier: Apache-2.0
"""Reverse-bias sweep of one well-edge cross-section; breakdown from the ionisation integral.

    python sweep.py PARAMS.json RESULT.json

Runs inside the DEVSIM image. PARAMS is the dictionary structure.py documents, plus
"vmax", "vstep" and optional "probes" (list of [x, y] in um whose potential is recorded,
for floating rings). RESULT holds the bias points, the largest electron ionisation
integral at each, the peak silicon field, the well current and the breakdown voltage.
"""

from __future__ import annotations

import json
import sys
import time

import devsim as ds
import numpy as np

import dd
import fieldline
import ionize
import structure

UM = 1e-4


def main(params_path, result_path):
    p = json.load(open(params_path))
    t0 = time.time()
    dd.use_extended_precision(p.get("extended", True))
    names = structure.build(p)
    dev = names["device"]
    structure.setup_physics(p, names)
    x = np.array(ds.get_node_model_values(device=dev, region="si", name="x"))
    y = np.array(ds.get_node_model_values(device=dev, region="si", name="y"))
    step = 0.5 * p["mesh"]["surf"] * UM
    probes = p.get("probes", [])
    probe_idx = [int(np.argmin((x - a * UM) ** 2 + (y - b * UM) ** 2)) for a, b in probes]
    tied = ["well"] + [f"plate{k}" for k, pl in enumerate(p.get("plates", [])) if pl["tie"] == "well"]
    rec = {"v": [], "i_n": [], "emax": [], "where_um": [], "i_well": [], "probes": [], "eox_max": []}

    def point(v):
        psi = np.array(ds.get_node_model_values(device=dev, region="si", name="Potential"))
        i_n, where, emax = fieldline.max_integral(x, y, psi, step)
        cur = sum(ds.get_contact_current(device=dev, contact="well", equation=e)
                  for e in ("ElectronContinuityEquation", "HoleContinuityEquation"))  # fmt: skip
        eox = 0.0
        for r in names["ox"]:
            ef = np.abs(ds.get_edge_model_values(device=dev, region=r, name="ElectricField"))
            eox = max(eox, float(ef.max()))
        rec["v"].append(v)
        rec["i_n"].append(i_n)
        rec["emax"].append(emax)
        rec["where_um"].append([float(where[0] / UM), float(where[1] / UM)] if where is not None else None)
        rec["i_well"].append(float(cur))
        rec["probes"].append([float(psi[k]) for k in probe_idx])
        rec["eox_max"].append(eox)
        print(f"POINT v={v:.2f} I_n={i_n:.4f} Emax={emax:.3e} Eox={eox:.3e} I={cur:.3e} "
              f"t={time.time() - t0:.0f}s", flush=True)  # fmt: skip
        return i_n > p.get("stop_at", 1.3)

    point(0.0)
    reached = dd.ramp(dev, tied, p["vmax"], p["vstep"], point)
    out = {
        "params": p,
        "nodes": {r: len(ds.get_node_model_values(device=dev, region=r, name="x"))
                  for r in names["si"] + names["ox"]},  # fmt: skip
        "reached_v": reached,
        "bv_v": ionize.breakdown_voltage(rec["v"], rec["i_n"]),
        "seconds": time.time() - t0,
        **rec,
    }
    json.dump(out, open(result_path, "w"), indent=1)
    print("RESULT bv", out["bv_v"], "reached", reached, "nodes", out["nodes"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
