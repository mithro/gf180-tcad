# SPDX-License-Identifier: Apache-2.0
"""DEVSIM reference for the diode strip that charon_run.py simulates in Charon.

    python charon_diode_ref.py NA LENGTH_UM VMAX VSTEP RESULT.json      (DEVSIM image)

Builds the strip of charon_mesh.dump_diode (the same nodes Charon gets), solves it with
dd.py as diode1d.py does, and records at each bias what sweep.py records for a
cross-section: the largest ionisation integral by fieldline.max_integral and the peak
field. Also writes the mesh dump (ref_mesh.npz).
"""

from __future__ import annotations

import json
import sys
import time

import devsim as ds
import numpy as np

import charon_mesh
import dd
import fieldline
import ionize


def main(na, length_um, vmax, vstep, result):
    t0 = time.time()
    dd.use_extended_precision()
    meta = charon_mesh.dump_diode(na, length_um, "ref_mesh.npz")
    xj = meta["extra"]["diode"]["xj_um"] * 1e-4
    dev, reg = "strip", "si"
    dd.silicon_parameters(dev, reg)
    dd.set_doping(dev, reg, f"ifelse(y < {xj}, 1e19, -{na})")
    contacts = {"well": reg, "sub": reg}
    dd.potential_only(dev, [reg], [], contacts, {}, [])
    dd.solve(abs_=1.0, rel=1e-10, iters=60)
    dd.drift_diffusion(dev, [reg], contacts)
    dd.solve(iters=60)
    x = np.array(ds.get_node_model_values(device=dev, region=reg, name="x"))
    y = np.array(ds.get_node_model_values(device=dev, region=reg, name="y"))
    rec = {"v": [], "i_n": [], "emax": [], "i_well": []}

    def point(v):
        psi = np.array(ds.get_node_model_values(device=dev, region=reg, name="Potential"))
        i_n, _, emax = fieldline.max_integral(x, y, psi, 1e-7)
        cur = sum(ds.get_contact_current(device=dev, contact="well", equation=e)
                  for e in ("ElectronContinuityEquation", "HoleContinuityEquation"))  # fmt: skip
        for key, value in (("v", v), ("i_n", i_n), ("emax", emax), ("i_well", cur)):
            rec[key].append(float(value))
        print(f"POINT v={v:.2f} I_n={i_n:.4f} Emax={emax:.4e} I={cur:.3e}", flush=True)

    point(0.0)
    reached = dd.ramp(dev, ["well"], vmax, vstep, point)
    out = {"na": na, "length_um": length_um, "nodes": len(x), "reached_v": reached,
           "bv_v": ionize.breakdown_voltage(rec["v"], rec["i_n"]),
           "seconds": time.time() - t0, **rec}  # fmt: skip
    json.dump(out, open(result, "w"), indent=1)
    print("RESULT bv", out["bv_v"], "reached", reached, flush=True)


if __name__ == "__main__":
    main(*(float(a) for a in sys.argv[1:5]), sys.argv[5])
