"""1D check: DEVSIM reverse-biased abrupt N+/P diode, breakdown from the ionisation integral.

Compares the simulated field's breakdown voltage with the triangular-field value from
test_ionize._abrupt_bv. Writes diode1d.json. Run through run.py.
"""

import json
import sys

import devsim as ds
import numpy as np

import dd
import ionize


def run(na, vmax, length_um):
    dev, reg = f"d{na:.0e}", "si"
    ds.create_1d_mesh(mesh=dev)
    L = length_um * 1e-4
    xj = 0.5e-4
    ds.add_1d_mesh_line(mesh=dev, pos=0.0, ps=5e-7, tag="top")
    ds.add_1d_mesh_line(mesh=dev, pos=xj, ps=1e-7, tag="mid")
    ds.add_1d_mesh_line(mesh=dev, pos=L, ps=L / 400, tag="bot")
    ds.add_1d_contact(mesh=dev, name="n", tag="top", material="metal")
    ds.add_1d_contact(mesh=dev, name="p", tag="bot", material="metal")
    ds.add_1d_region(mesh=dev, material="Si", region=reg, tag1="top", tag2="bot")
    ds.finalize_mesh(mesh=dev)
    ds.create_device(mesh=dev, device=dev)
    dd.silicon_parameters(dev, reg)
    dd.set_doping(dev, reg, f"ifelse(x < {xj}, 1e19, -{na})")
    contacts = {"n": reg, "p": reg}
    dd.potential_only(dev, [reg], [], contacts, {}, [])
    dd.solve(abs_=1.0, rel=1e-10)
    dd.drift_diffusion(dev, [reg], contacts)
    dd.solve()
    x = np.array(ds.get_node_model_values(device=dev, region=reg, name="x"))
    volts, ints = [], []

    def point(v):
        psi = np.array(ds.get_node_model_values(device=dev, region=reg, name="Potential"))
        xm = 0.5 * (x[1:] + x[:-1])
        e = np.abs(np.diff(psi) / np.diff(x))
        # P side (low potential) first: x decreasing from the bottom contact
        i_n, _ = ionize.ionisation_integrals((xm[-1] - xm)[::-1], e[::-1])
        volts.append(v)
        ints.append(i_n)

    dd.ramp(dev, ["n"], vmax, vmax / 60, point)
    return ionize.breakdown_voltage(volts, ints), volts[-1]


if __name__ == "__main__":
    dd.use_extended_precision()
    out = {}
    for na, vmax, length in ((1e15, 400.0, 40.0), (1e16, 90.0, 8.0), (1e17, 25.0, 2.0)):
        bv, reached = run(na, vmax, length)
        out[f"{na:.0e}"] = {"bv_v": bv, "reached_v": reached}
        print("RESULT", na, bv, reached, flush=True)
    json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else "diode1d.json", "w"), indent=1)
