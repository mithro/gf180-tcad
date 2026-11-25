"""B4, the analytic case: harmonic balance on a parallel-plate oxide capacitor.

An oxide-only strip (the nfet calibrated oxide thickness and node spacing, 1 um wide) between two
gate contacts on the insulator. The exact capacitance per area is eps_ox * eps0 / t_ox. A DC
solve at 0 V gives the state; the HB run puts a small signal of amplitude A at frequency f on
one plate. Every HB current column is printed as I / (2 pi f A w) / C_exact, with w the strip
width in cm, so the column that carries C reads +-1. Writes b4pp.json.
"""
import json
import math
import os

import numpy as np

import cx

job = cx.job1d("nfet_05v0", "calibrated")
c = job.stack.constants
xs, bn = job.stack.node_positions_um()
x_ox = np.array(xs[bn[1]: bn[2] + 1]) - xs[bn[1]]
t_ox_cm = (x_ox[-1] - x_ox[0]) * 1e-4
c_exact = c.eps_ox * c.eps0_f_per_cm / t_ox_cm
xy, blocks, ss = cx.strip_mesh(list(x_ox), ["oxide"] * (len(x_ox) - 1), ["oxide"])
ss = [("top", *ss[0][1:]), ("bottom", *ss[1][1:])]
cx.write_exodus("pp.exo", xy, blocks, ss)
W_CM = cx.STRIP_WIDTH_UM * 1e-4
out = {"c_exact_f_cm2": c_exact, "t_ox_cm": t_ox_cm, "runs": {}}

HEAD = """tpetra is on
lattice temperature = 298.15
start output parameters
  Output State File {out}
  Unscale Variables is on
end output parameters
start Physics Block oxide
  geometry block is oxide
  standard discretization type is laplace cvfem
{hb}  material model is oxideParameter
end Physics Block oxide
start Material Block oxideParameter
  material name is SiO2
  relative permittivity = {eps!r}
end Material Block oxideParameter
"""
SOLVER = """start solver block
  start tpetra block
    problem type is {problem}
    linear solver tolerance = 1e-12
    verbosity level is high
    start nonlinear solver wrms block
      relative tolerance = 1e-10
      absolute tolerance = 1e-12
    end nonlinear solver wrms block
  end tpetra block
end solver block
"""
dc = ("Import State File pp.exo\n" + HEAD.format(out="pp_dc.exo", hb="", eps=c.eps_ox)
      + "initial conditions for ELECTRIC_POTENTIAL in oxide is uninitialized\n"
      + "BC is contact on insulator for top on oxide with work function 4.05 fixed at 0.0\n"
      + "BC is contact on insulator for bottom on oxide with work function 4.05 fixed at 0.0\n"
      + SOLVER.format(problem="steady state"))
open("pp_dc.inp", "w").write(dc)
ok, log, dt = cx.run("pp_dc.inp")
out["dc_ok"] = ok
print("dc", ok, flush=True)
for f, amp in ((1e6, 1e-4), (1e3, 1e-4), (1e0, 1e-4), (1e6, 1e-3), (1e6, 1e-5)):
    hb = ("  apply harmonic balance for large signal analysis\n"
          "  start harmonic balance parameters\n    truncation order = 1\n"
          "    truncation scheme is box\n"
          f"    fundamental harmonics = {f!r}\n    remapped fundamental harmonics = 1.0\n"
          "  end harmonic balance parameters\n")
    name = f"pp_hb_{f:g}_{amp:g}"
    deck = ("Import State File pp_dc.exo\n" + HEAD.format(out=f"{name}.exo", hb=hb, eps=c.eps_ox)
            + "Harmonic Balance initial conditions for ELECTRIC_POTENTIAL in oxide is DC remapped\n"
            + "start Harmonic Balance BC for bottom on oxide\n"
            + "  type is contact on insulator with work function 4.05\n"
            + '  frequencies  "0"\n  amplitudes   "0"\n  phase shifts "0"\n'
            + "end Harmonic Balance BC for bottom on oxide\n"
            + "start Harmonic Balance BC for top on oxide\n"
            + "  type is contact on insulator with work function 4.05\n"
            + f"  small signal sweep from 0.0 to 0.05 with amplitude {amp!r}\n"
            + "end Harmonic Balance BC for top on oxide\n"
            + "start sweep options\n  initial step size = 0.05\n  minimum step size = 0.05\n"
            + "  maximum step size = 0.05\n  step size aggressiveness = 0.0\nend sweep options\n"
            + SOLVER.format(problem="parameter sweep"))
    open(f"{name}.inp", "w").write(deck)
    ok, log, dt = cx.run(f"{name}.inp")
    rec = {"ok": ok}
    if ok:
        head, rows = cx.read_currents("currents-loca.dat")
        k = 2 * math.pi * f * amp * W_CM * c_exact
        rec["columns"] = head
        rec["rows"] = rows.tolist()
        rec["ratio"] = {h: float(rows[0, i] / k) for i, h in enumerate(head) if "H1" in h}
    else:
        rec["tail"] = log[-2000:]
    out["runs"][name] = rec
    print(name, ok, rec.get("ratio"), flush=True)
json.dump(out, open("b4pp.json", "w"), indent=1)
