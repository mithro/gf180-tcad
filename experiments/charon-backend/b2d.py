"""B2, the hard range from the other side: can the inversion states be reached without
stepping up from depletion?

(1) steady-state solves of the nfet calibrated strip at fixed device biases 0.5, 1.0, 1.5, 3 and
5 V, each straight from the equilibrium initial guess; (2) from the highest bias that converged,
a LOCA sweep down to 0 V at 0.05 V steps. WRMS 1e-10 / 1e-12, KLU2. Writes b2d.json.
"""

import json
import re
from pathlib import Path

import cx
import decks
import opts

job = cx.job1d("nfet_05v0", "calibrated")
_, xy, blocks, ss = cx.stack_strip(job.stack)
ss = [("gate", *ss[0][1:]), ("body_contact", *ss[1][1:])]
cx.write_exodus("strip.exo", xy, blocks, ss)


def deck(name, mesh, gate_bc, problem, init, sweep=None):
    d = decks.moscap_deck(
        job,
        mesh=mesh,
        out=f"{name}.exo",
        gate_bc=gate_bc,
        problem=problem,
        init=init,
        sweep=sweep,
        rel=opts.REL,
        abs_=opts.ABS,
        extra=opts.KLU2,
    )
    return d.replace("BC is ohmic for body on body", "BC is ohmic for body_contact on body")


out = {"direct": {}}
best = None
for v in (0.5, 1.0, 1.5, 3.0, 5.0):
    name = f"direct_{v}"
    Path(f"{name}.inp").write_text(
        deck(name, "strip.exo", f"fixed at {v!r}", "steady state", "equilibrium")
    )
    ok, log, dt = cx.run(f"{name}.inp")
    its = len(re.findall(r"-- Nonlinear Solver Step \d+ --", log))
    w = re.findall(r"WRMS-Norm = ([0-9.e+-]+)", log)
    f = re.findall(r"F-Norm = ([0-9.e+-]+)", log)
    out["direct"][v] = {
        "ok": ok,
        "newton_steps": its,
        "last_wrms": w[-1] if w else None,
        "last_fnorm": f[-1] if f else None,
    }
    print("direct", v, out["direct"][v], flush=True)
    if ok:
        best = v
if best is not None:
    n = round(best / 0.05)
    sweep = [
        "initial step size = 0.05",
        "minimum step size = 0.05",
        "maximum step size = 0.05",
        f"maximum number of steps = {n + 5}",
        "hit continuation bound = false",
        "step size aggressiveness = 0.0",
        "predictor method is secant",
    ]
    Path("down.inp").write_text(
        deck(
            "down",
            f"direct_{best}.exo",
            f"swept from {best!r} to 0.0",
            "parameter sweep",
            "exodus",
            sweep,
        )
    )
    ok, log, dt = cx.run("down.inp")
    its = [int(k) for k in re.findall(r"Step Converged in (\d+) Nonlinear", log)]
    biases = [
        float(m)
        for m in re.findall(
            r"Start of Continuation Step \d+ : Parameter: Varying "
            r"Voltage = (\S+)",
            log,
        )
    ]
    fails = re.findall(r"Value of continuation parameter at failed step = (\S+)", log)
    out["down"] = {
        "from": best,
        "ok": ok,
        "iters": its,
        "failed_at": fails,
        "last_converged_bias": biases[len(its)] if len(biases) > len(its) else None,
    }
    print("down", out["down"], flush=True)
Path("b2d.json").write_text(json.dumps(out, indent=1))
