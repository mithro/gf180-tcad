"""B2, option 2: time stepping to the steady state at a fixed bias in the hard range.

Starting from the last converged state of the default-lifetime LOCA sweep (device bias 0.30 V,
the last state of ref_1e-10.exo from b2h.py, copied into this directory), the gate is held at
0.35 V (and then 0.5 V) and the transient drift-diffusion problem is integrated with variable
time steps to a final time long against the generation time (about tau * N_A / n_i, 100 s
for tau = 1e-5 s). The last state is then used as the start of a steady-state solve at the same
bias. Writes b2t.json.
"""
import json
import re

import cx
import decks
import opts

job = cx.job1d("nfet_05v0", "calibrated")
out = {}


def deck(name, mesh, gate_bc, problem, init, extra_solver=(), tau=None):
    d = decks.moscap_deck(job, mesh=mesh, out=f"{name}.exo", gate_bc=gate_bc, problem=problem,
                          init=init, rel=opts.REL, abs_=opts.ABS, extra=opts.KLU2,
                          extra_solver=extra_solver, tau=tau)
    return d.replace("BC is ohmic for body on body", "BC is ohmic for body_contact on body")


TRANSIENT = [
    "time step size is variable",
    "time integrator initial step size = 1e-12",
    "time integrator minimum step size = 1e-16",
    "time integrator maximum step size = 1e3",
    "time integrator final time = 1e4",
]
start = "ref_1e-10.exo"
for v in (0.35, 0.5):
    name = f"tr_{v}"
    open(f"{name}.inp", "w").write(deck(name, start, f"fixed at {v!r}", "transient", "exodus",
                                        TRANSIENT))
    ok, log, dt = cx.run(f"{name}.inp")
    times = re.findall(r"[Tt]ime = ([0-9.e+-]+)", log)
    fails = len(re.findall(r"(?i)fail", log))
    rec = {"ok": ok, "time_s": dt, "last_times": times[-3:], "fail_mentions": fails}
    if ok:
        st = cx.read_states(f"{name}.exo")
        rec["states"] = len(st.times)
        rec["final_time"] = float(st.times[-1]) if len(st.times) else None
        # steady state from the transient's last state
        ss = f"ss_{v}"
        open(f"{ss}.inp", "w").write(deck(ss, f"{name}.exo", f"fixed at {v!r}", "steady state",
                                          "exodus"))
        ok2, log2, dt2 = cx.run(f"{ss}.inp")
        w = re.findall(r"WRMS-Norm = ([0-9.e+-]+)", log2)
        rec.update(steady_ok=ok2, steady_last_wrms=w[-1] if w else None,
                   steady_newton=len(re.findall(r"-- Nonlinear Solver Step \d+ --", log2)))
        if ok2:
            start = f"{ss}.exo"
    else:
        rec["tail"] = log[-2500:]
    out[str(v)] = rec
    print(v, {k: x for k, x in rec.items() if k != "tail"}, flush=True)
    if not ok:
        break
json.dump(out, open("b2t.json", "w"), indent=1)
