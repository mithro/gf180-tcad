"""B1 analysis: the C per area of the 2D TRI3 mesh at vg = 0 V, from the two solves of b1.py.

The uniform stack's potential depends on depth only, so the gate charge per area is
eps_ox * (psi at the poly/oxide interface - psi at the oxide/body interface) / t_ox, with each
interface potential averaged over its nodes (and the spread across them reported). Writes
b1an.json; compares with the DEVSIM 1D C at vg = 0 V.
"""

import json
from pathlib import Path

import cx
import numpy as np

job = cx.job1d("nfet_05v0", "start")  # the 2D mesh of b1.py is the start stack
c = job.stack.constants

DV = 1e-3
q, spread = {}, {}
for side in ("A", "B"):
    st = cx.read_states(f"m2d_{side}.exo")
    psi = st.nodal["ELECTRIC_POTENTIAL"][0]
    ox = np.unique(st.blocks["oxide"].ravel())
    poly = np.unique(st.blocks["gate_poly"].ravel())
    body = np.unique(st.blocks["body"].ravel())
    top = np.intersect1d(ox, poly)
    bot = np.intersect1d(ox, body)
    t_cm = abs(st.y[top].mean() - st.y[bot].mean()) * 1e-4  # um -> cm
    q[side] = c.eps_ox * c.eps0_f_per_cm * (psi[top].mean() - psi[bot].mean()) / t_cm
    spread[side] = [float(np.ptp(psi[top])), float(np.ptp(psi[bot]))]
cc = (q["B"] - q["A"]) / (2 * DV) * 1e7
i = job.vg.index(0.0)
out = {
    "c_2d_ff_um2": cc,
    "t_ox_mesh_nm": t_cm * 1e7,
    "c_devsim_1d": job.c_devsim[i],
    "rel_vs_devsim_1d": (cc - job.c_devsim[i]) / job.c_devsim[i],
    "interface_potential_spread_v": spread,
}
print(out)
Path("b1an.json").write_text(json.dumps(out, indent=1))
