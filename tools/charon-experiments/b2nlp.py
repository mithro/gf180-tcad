"""B2, the separate question: does Charon's nonlinear Poisson (nlp) solve honour a biased
semiconductor (poly) gate?

The nfet calibrated strip with `nlp cvfem` in poly and body and the gate ohmic on the poly, at
committed grid biases vg (solved at vg - dv_fb -+ 1 mV): the C per area from the oxide-flux gate
charge is compared with the committed DEVSIM quasi-static C (equilibrium Poisson-Boltzmann with
each silicon region at its own contact's Fermi level). The poly charge neutrality in its bulk is
reported too (the potential drop across the poly). Writes b2nlp.json.
"""
import json

import numpy as np

import cx
import decks
import opts

job = cx.job1d("nfet_05v0", "calibrated")
_, xy, blocks, ss = cx.stack_strip(job.stack)
ss = [("gate", *ss[0][1:]), ("body_contact", *ss[1][1:])]
cx.write_exodus("strip.exo", xy, blocks, ss)
xs1d = np.array(job.stack.node_positions_um()[0])
bn = job.stack.node_positions_um()[1]
c = job.stack.constants
DV = 1e-3
out = {"points": []}
for vg in (-3.0, -1.0, 0.0, 0.5, 1.0, 3.0):
    i = min(range(len(job.vg)), key=lambda k: abs(job.vg[k] - vg))
    q = {}
    for side, sgn in (("A", -1), ("B", 1)):
        v = vg - job.dv_fb + sgn * DV
        name = f"nlp_{vg:+.1f}_{side}"
        d = decks.moscap_deck(job, mesh="strip.exo", out=f"{name}.exo", gate_bc=f"fixed at {v!r}",
                              disc="nlp cvfem", ox_disc="laplace cvfem", rel=opts.REL,
                              abs_=opts.ABS, extra=opts.KLU2)
        d = d.replace("BC is ohmic for body on body", "BC is ohmic for body_contact on body")
        open(f"{name}.inp", "w").write(d)
        ok, log, dt = cx.run(f"{name}.inp")
        if not ok:
            q = None
            out["points"].append({"vg": vg, "ok": False, "tail": log[-1500:]})
            break
        st = cx.read_states(f"{name}.exo")
        q[side] = cx.oxide_flux_charge(st, 0, xs1d, bn[1], bn[2], c.eps_ox, c.eps0_f_per_cm)[0]
        psi = st.nodal["ELECTRIC_POTENTIAL"][0, 0::2]
        poly_drop = float(psi[bn[1]] - psi[0])
    if q is None:
        print(vg, "failed", flush=True)
        continue
    cc = (q["B"] - q["A"]) / (2 * DV) * 1e7
    rec = {"vg": vg, "ok": True, "c_nlp": cc, "c_devsim": job.c_devsim[i],
           "rel": (cc - job.c_devsim[i]) / job.c_devsim[i], "poly_potential_drop_v": poly_drop}
    out["points"].append(rec)
    print(rec, flush=True)
json.dump(out, open("b2nlp.json", "w"), indent=1)
