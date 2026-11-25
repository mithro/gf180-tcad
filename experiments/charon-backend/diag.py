"""Diagnostics: profiles of one steady-state solve of the nfet calibrated strip."""
import sys
import numpy as np
import cx, decks
vgate = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
job = cx.job1d("nfet_05v0", "calibrated")
xs, xy, blocks, ss = cx.stack_strip(job.stack)
ss = [("gate", *ss[0][1:]), ("body_contact", *ss[1][1:])]
cx.write_exodus("strip.exo", xy, blocks, ss)
names = "Doping,Acceptor Concentration,Donor Concentration,Intrinsic Concentration,Space Charge,Electron Quasi Fermi Level,Hole Quasi Fermi Level"
d = decks.moscap_deck(job, mesh="strip.exo", out="diag.exo", gate_bc=f"fixed at {vgate!r}",
                      nodal_out=[("gate_poly", names), ("body", names)])
d = d.replace("BC is ohmic for body on body", "BC is ohmic for body_contact on body")
open("diag.inp", "w").write(d)
ok, out, dt = cx.run("diag.inp")
print("ok", ok)
if not ok:
    print(out[-3000:]); raise SystemExit(1)
st = cx.read_states("diag.exo")
print("vars", list(st.nodal))
bn = job.stack.node_positions_um()[1]
idx = sorted(set(list(range(0, 4)) + list(range(bn[1] - 4, bn[1] + 2)) + list(range(bn[2] - 1, bn[2] + 4)) + [len(xs) - 1]))
keys = list(st.nodal)
print("i x_um " + " | ".join(keys))
for i in idx:
    print(i, f"{xs[i]:.6f}", " ".join(f"{st.nodal[k][0, 2 * i]:.6e}" for k in keys))
