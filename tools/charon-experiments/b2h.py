"""B2, the hard range: the zero-current drift-diffusion LOCA sweep of the nfet calibrated strip
through the depletion-to-inversion transition (device bias 0 V to 1.5 V), under variants of the
solver settings, to find which (if any) passes and where each one stops.

Each variant: equilibrium at 0 V, then a LOCA sweep 0 -> 1.5 V at a fixed step. Records per
continuation step the Newton iterations and the final F-norm and WRMS norm, and the bias of
the first failed step. Writes b2h.json.

usage: python3 b2h.py VARIANT [VARIANT ...]   (names in VARIANTS below)
"""
import json
import os
import re
import sys
from pathlib import Path

import cx
import decks
import opts

job = cx.job1d("nfet_05v0", "calibrated")
_, xy, blocks, ss = cx.stack_strip(job.stack)
ss = [("gate", *ss[0][1:]), ("body_contact", *ss[1][1:])]
cx.write_exodus("strip.exo", xy, blocks, ss)

# name -> (deck keyword overrides, step V)
VARIANTS = {
    "ref_1e-10": (dict(rel=1e-10, abs_=1e-12), 0.05),
    "tol_1e-8": (dict(rel=1e-8, abs_=1e-10), 0.05),
    "tol_1e-6": (dict(rel=1e-6, abs_=1e-8), 0.05),
    "tol_1e-4": (dict(rel=1e-4, abs_=1e-6), 0.05),
    "scale_1e20": (dict(rel=1e-10, abs_=1e-12, conc_scaling=1e20), 0.05),
    "scale_1e10": (dict(rel=1e-10, abs_=1e-12, conc_scaling=1e10), 0.05),
    "step_5mV": (dict(rel=1e-10, abs_=1e-12), 0.005),
    "gfem": (dict(rel=1e-10, abs_=1e-12, disc="drift diffusion gfem", ox_disc="laplace gfem"), 0.05),
    "belos": (dict(rel=1e-10, abs_=1e-12, linear="belos", extra=[]), 0.05),
    "nosrh": (dict(rel=1e-10, abs_=1e-12, srh=False), 0.05),
    "tau_1e-12": (dict(rel=1e-10, abs_=1e-12, tau=1e-12), 0.05),
    "tau_1e-13": (dict(rel=1e-10, abs_=1e-12, tau=1e-13), 0.05),
    "tau_1e-15": (dict(rel=1e-10, abs_=1e-12, tau=1e-15), 0.05),
    "tau_1e-14": (dict(rel=1e-10, abs_=1e-12, tau=1e-14), 0.05),
    "tau_1e-15_step_5mV": (dict(rel=1e-10, abs_=1e-12, tau=1e-15), 0.005),
    "tau_1e-12_tol_1e-8": (dict(rel=1e-8, abs_=1e-10, tau=1e-12), 0.05),
}
VEND = float(os.environ.get("CX_VEND", "1.5"))


def deck(name, mesh, gate_bc, problem, init, kw, sweep=None):
    kw = dict(kw)
    kw.setdefault("extra", opts.KLU2)
    d = decks.moscap_deck(job, mesh=mesh, out=f"{name}.exo", gate_bc=gate_bc, problem=problem,
                          init=init, sweep=sweep, **kw)
    return d.replace("BC is ohmic for body on body", "BC is ohmic for body_contact on body")


def steps(log):
    """Per continuation step: (bias, converged, iterations, final F-norm, final WRMS)."""
    out = []
    for m in re.finditer(r"Start of Continuation Step (\d+) : Parameter: Varying Voltage = (\S+)",
                         log):
        out.append(float(m.group(2)))
    blocks = log.split("-- Final Status Test Results --")[1:]
    fin = []
    for b in blocks:
        f = re.search(r"F-Norm = ([0-9.e+-]+)", b)
        w = re.search(r"WRMS-Norm = ([0-9.e+-]+)", b)
        fin.append((float(f.group(1)) if f else None, float(w.group(1)) if w else None,
                    b.lstrip().startswith("Converged")))
    its = [int(k) for k in re.findall(r"Step Converged in (\d+) Nonlinear", log)]
    fails = re.findall(r"Value of continuation parameter at failed step = (\S+)", log)
    return {"biases": out, "final": fin, "iters": its, "failed_at": fails}


results = json.loads(Path("b2h.json").read_text()) if Path("b2h.json").exists() else {}
for name in sys.argv[1:]:
    kw, step = VARIANTS[name]
    Path(f"{name}_eq.inp").write_text(deck(f"{name}_eq", "strip.exo", "fixed at 0.0",
                                           "steady state", "equilibrium", kw))
    ok, log, dt = cx.run(f"{name}_eq.inp")
    rec = {"eq_ok": ok, "settings": {k: v for k, v in kw.items() if k != "extra"}, "step": step,
           "eq": steps(log)}
    if ok:
        nsteps = int(round(VEND / step))
        sweep = [f"initial step size = {step!r}", f"minimum step size = {step!r}",
                 f"maximum step size = {step!r}", f"maximum number of steps = {nsteps + 5}",
                 "hit continuation bound = false", "step size aggressiveness = 0.0",
                 "predictor method is secant"]
        Path(f"{name}.inp").write_text(deck(name, f"{name}_eq.exo", f"swept from 0.0 to {VEND!r}",
                                            "parameter sweep", "exodus", kw, sweep))
        ok2, log2, dt2 = cx.run(f"{name}.inp")
        s = steps(log2)
        rec.update(sweep_ok=ok2, sweep_time_s=dt2, sweep=s,
                   failing_bias=(s["biases"][len(s["iters"])] if len(s["biases"]) > len(s["iters"]) else None))
    results[name] = rec
    print(name, "eq_ok", ok, "sweep_ok", rec.get("sweep_ok"), "failed_at",
          rec.get("sweep", {}).get("failed_at", [])[:2], "iters",
          rec.get("sweep", {}).get("iters", [])[-6:], flush=True)
    Path("b2h.json").write_text(json.dumps(results, indent=1))
