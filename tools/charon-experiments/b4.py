"""B4: the harmonic-balance small-signal column convention, checked against the quasi-static C.

On the nfet calibrated strip at two DC biases where the 1 MHz capacitance equals the quasi-static
one (accumulation, vg = -2 V; depletion, vg = 0 V; no inversion layer), the small-signal gate
current of a 1e-4 V gate excitation at 1 MHz is read from currents-loca.dat. C from each column
(cos/sin, conduction/displacement, gate/body) as I/(2 pi f A) is compared with the QS central
difference of the oxide-flux gate charge at the same bias (+-1 mV steady-state solves).
"""
import json
import math
import re

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
F, AMP, DV, W_CM = 1e6, 1e-4, 1e-3, 1e-4
HB = """      apply harmonic balance for large signal analysis
      start harmonic balance parameters
          truncation order = 1
          truncation scheme is box
          fundamental harmonics = {f!r}
          remapped fundamental harmonics = 1.0
      end harmonic balance parameters"""


def base(name, mesh, gate_bc, problem, init, extra=(), sweep=None):
    d = decks.moscap_deck(job, mesh=mesh, out=f"{name}.exo", gate_bc=gate_bc, problem=problem,
                          init=init, rel=opts.REL, abs_=opts.ABS, extra=list(opts.EXTRA) + list(extra),
                          sweep=sweep)
    return d.replace("BC is ohmic for body on body", "BC is ohmic for body_contact on body")


def qs_charge(name, mesh, v, init):
    open(f"{name}.inp", "w").write(base(name, mesh, f"fixed at {v!r}", "steady state", init))
    ok, log, dt = cx.run(f"{name}.inp")
    if not ok:
        raise SystemExit(f"{name} failed")
    st = cx.read_states(f"{name}.exo")
    return cx.oxide_flux_charge(st, 0, xs1d, bn[1], bn[2], c.eps_ox, c.eps0_f_per_cm)[0]


out = {"f_hz": F, "amplitude_v": AMP}
prev = "strip.exo"
init = "equilibrium"
for label, vg in (("accumulation", -2.0), ("depletion", 0.0)):
    v = vg - job.dv_fb
    qa = qs_charge(f"qs_{label}_a", prev, v - DV, init)
    qb = qs_charge(f"qs_{label}_b", f"qs_{label}_a.exo", v + DV, "exodus")
    c_qs = (qb - qa) / (2 * DV)  # F/cm^2
    qs_charge(f"dc_{label}", f"qs_{label}_b.exo", v, "exodus")
    prev, init = f"dc_{label}.exo", "exodus"
    # HB deck: DC state imported, one LOCA step from v to v + 0.05 V with the small signal on
    d = base(f"hb_{label}", f"dc_{label}.exo", "fixed at 0.0", "parameter sweep", "exodus",
             sweep=["initial step size = 0.05", "minimum step size = 0.05",
                    "maximum step size = 0.05", "step size aggressiveness = 0.0",
                    "predictor method is secant"])
    d = d.replace(f"BC is ohmic for gate on gate_poly fixed at 0.0\n", "")
    d = d.replace("BC is ohmic for body_contact on body fixed at 0.0\n", "")
    d = re.sub(r"(  standard discretization type is [^\n]*\n)", r"\1" + HB.format(f=F) + "\n", d)
    d = re.sub(r"initial conditions for (\w+) in (\w+) is exodus file",
               r"Harmonic Balance initial conditions for \1 in \2 is DC remapped", d)
    d += f"""start Harmonic Balance BC for body_contact on body
  type is ohmic
  frequencies  "0"
  amplitudes   "0"
  phase shifts "0"
end Harmonic Balance BC for body_contact on body
start Harmonic Balance BC for gate on gate_poly
  type is ohmic
  small signal sweep from {v!r} to {v + 0.05!r} with amplitude {AMP!r}
end Harmonic Balance BC for gate on gate_poly
"""
    open(f"hb_{label}.inp", "w").write(d)
    ok, log, dt = cx.run(f"hb_{label}.inp")
    rec = {"vg": vg, "v_device": v, "c_qs_f_cm2": c_qs, "hb_ok": ok, "hb_time_s": dt}
    if ok:
        head, rows = cx.read_currents("currents-loca.dat")
        rec["columns"] = head
        rec["rows"] = rows.tolist()
        # 2D currents are per cm of depth; the strip is W_CM wide -> per cm^2 divide by W_CM
        k = 2 * math.pi * F * AMP * W_CM
        rec["c_from_columns_over_c_qs"] = {
            h: float(rows[0, i] / k / c_qs) for i, h in enumerate(head) if "H1" in h}
    else:
        rec["tail"] = log[-3000:]
    out[label] = rec
    print(label, {k: v for k, v in rec.items() if k not in ("rows", "tail", "columns")},
          flush=True)
json.dump(out, open("b4.json", "w"), indent=1, default=float)
