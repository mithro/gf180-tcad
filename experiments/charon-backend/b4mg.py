"""B4, the metal-gate case: harmonic balance against the QS C on an oxide/body strip whose gate
is a contact on the insulator (no poly), as Charon's own loca_moscap_cv test is built.

The nfet calibrated oxide and body, the gate a work-function contact on the oxide's free face,
the body ohmic. At a gate bias in accumulation and one in depletion: the QS C from two
steady-state solves at -+1 mV (oxide-flux gate charge) and the HB C from a 1e-4 V gate signal at
1 MHz. Prints each HB column as I / (2 pi f A w) / C_qs. Writes b4mg.json.
"""
import json
import math

import numpy as np

import cx
import opts

job = cx.job1d("nfet_05v0", "calibrated")
c = job.stack.constants
st = job.meta["stack"]
xs, bn = job.stack.node_positions_um()
x = np.array(xs[bn[1]:]) - xs[bn[1]]
lay = ["oxide"] * (bn[2] - bn[1]) + ["body"] * (len(xs) - 1 - bn[2])
xy, blocks, ss = cx.strip_mesh(list(x), lay, ["oxide", "body"])
ss = [("gate", *ss[0][1:]), ("body_contact", *ss[1][1:])]
cx.write_exodus("mg.exo", xy, blocks, ss)
W_CM = cx.STRIP_WIDTH_UM * 1e-4
F, AMP, DV, WF = 1e6, 1e-4, 1e-3, 4.05
i_ox = bn[2] - bn[1]  # last oxide node in this strip

MAT = f"""start Material Block bodyParameter
  material name is Silicon
  relative permittivity = {c.eps_si!r}
  electron affinity = 4.05
  constant intrinsic concentration = {c.n_i_cm3!r}
  fixed mobility for electrons is {c.mu_n_cm2_per_vs!r} holes is {c.mu_p_cm2_per_vs!r}
  start Carrier Lifetime Block
    electron lifetime is constant = {c.tau_n_s!r}
    hole lifetime is constant = {c.tau_p_s!r}
  end Carrier Lifetime Block
  start uniform doping named Function1
    concentration = {st['n_ch_cm3']!r}
    type is acceptor
  end uniform doping named Function1
end Material Block bodyParameter
start Material Block oxideParameter
  material name is SiO2
  relative permittivity = {c.eps_ox!r}
end Material Block oxideParameter
"""


def physics(hb):
    out = ""
    for blk, disc, mat in (("body", "drift diffusion cvfem", "bodyParameter"),
                           ("oxide", "laplace cvfem", "oxideParameter")):
        out += (f"start Physics Block {blk}\n  geometry block is {blk}\n"
                f"  standard discretization type is {disc}\n")
        if hb:
            out += ("  apply harmonic balance for large signal analysis\n"
                    "  start harmonic balance parameters\n    truncation order = 1\n"
                    "    truncation scheme is box\n"
                    f"    fundamental harmonics = {F!r}\n    remapped fundamental harmonics = 1.0\n"
                    "  end harmonic balance parameters\n")
        out += f"  material model is {mat}\n"
        if blk == "body":
            out += "  SRH Recombination is on\n"
        out += f"end Physics Block {blk}\n"
    return out


def solver(problem, rel):
    return "\n".join(opts.KLU2) + "\n" + _solver(problem, rel)


def _solver(problem, rel):
    return (f"start solver block\n  start tpetra block\n    problem type is {problem}\n"
            "    linear solver tolerance = 1e-12\n    verbosity level is high\n"
            f"    start nonlinear solver wrms block\n      relative tolerance = {rel!r}\n"
            f"      absolute tolerance = {rel * 1e-2!r}\n    end nonlinear solver wrms block\n"
            "  end tpetra block\nend solver block\n")


def head(imp, out):
    return (f"Import State File {imp}\ntpetra is on\nlattice temperature = {c.t_k!r}\n"
            f"start output parameters\n  Output State File {out}\n  Unscale Variables is on\n"
            "end output parameters\n")


def dc(name, imp, v, init):
    ic = ("initial conditions for ELECTRIC_POTENTIAL in body is equilibrium potential\n"
          "initial conditions for ELECTRON_DENSITY in body is equilibrium density\n"
          "initial conditions for HOLE_DENSITY in body is equilibrium density\n"
          "initial conditions for ELECTRIC_POTENTIAL in oxide is uninitialized\n"
          if init == "eq" else
          "".join(f"initial conditions for {d} in body is exodus file\n"
                  for d in ("ELECTRIC_POTENTIAL", "ELECTRON_DENSITY", "HOLE_DENSITY"))
          + "initial conditions for ELECTRIC_POTENTIAL in oxide is exodus file\n")
    deck = (head(imp, f"{name}.exo") + physics(False) + MAT + ic
            + "BC is ohmic for body_contact on body fixed at 0.0\n"
            + f"BC is contact on insulator for gate on oxide with work function {WF!r} fixed at {v!r}\n"
            + solver("steady state", 1e-10))
    open(f"{name}.inp", "w").write(deck)
    ok, log, dt = cx.run(f"{name}.inp")
    if not ok:
        raise SystemExit(f"{name} failed:\n{log[-2000:]}")
    s = cx.read_states(f"{name}.exo")
    psi = s.nodal["ELECTRIC_POTENTIAL"][0, 0::2]
    xc = x * 1e-4
    return c.eps_ox * c.eps0_f_per_cm * (psi[0] - psi[1]) / (xc[1] - xc[0])


out = {}
prev, init = "mg.exo", "eq"
for label, v in (("accumulation", -2.0), ("depletion", -0.5)):
    qa = dc(f"qs_{label}_a", prev, v - DV, init)
    qb = dc(f"qs_{label}_b", f"qs_{label}_a.exo", v + DV, "exo")
    c_qs = (qb - qa) / (2 * DV)
    dc(f"dc_{label}", f"qs_{label}_b.exo", v, "exo")
    prev, init = f"dc_{label}.exo", "exo"
    deck = (head(f"dc_{label}.exo", f"hb_{label}.exo") + physics(True) + MAT
            + "".join(f"Harmonic Balance initial conditions for {d} in body is DC remapped\n"
                      for d in ("ELECTRIC_POTENTIAL", "ELECTRON_DENSITY", "HOLE_DENSITY"))
            + "Harmonic Balance initial conditions for ELECTRIC_POTENTIAL in oxide is DC remapped\n"
            + "start Harmonic Balance BC for body_contact on body\n  type is ohmic\n"
            + '  frequencies  "0"\n  amplitudes   "0"\n  phase shifts "0"\n'
            + "end Harmonic Balance BC for body_contact on body\n"
            + "start Harmonic Balance BC for gate on oxide\n"
            + f"  type is contact on insulator with work function {WF!r}\n"
            + f"  small signal sweep from {v!r} to {v + 0.05!r} with amplitude {AMP!r}\n"
            + "end Harmonic Balance BC for gate on oxide\n"
            + "start sweep options\n  initial step size = 0.05\n  minimum step size = 0.05\n"
            + "  maximum step size = 0.05\n  step size aggressiveness = 0.0\nend sweep options\n"
            + solver("parameter sweep", 1e-8))
    open(f"hb_{label}.inp", "w").write(deck)
    ok, log, dt = cx.run(f"hb_{label}.inp")
    rec = {"v": v, "c_qs_f_cm2": c_qs, "hb_ok": ok}
    if ok:
        h, rows = cx.read_currents("currents-loca.dat")
        k = 2 * math.pi * F * AMP * W_CM * c_qs
        rec["ratio"] = {n: float(rows[0, i] / k) for i, n in enumerate(h) if "H1" in n}
    else:
        rec["tail"] = log[-2000:]
    out[label] = rec
    print(label, {a: b for a, b in rec.items() if a != "tail"}, flush=True)
json.dump(out, open("b4mg.json", "w"), indent=1, default=float)
