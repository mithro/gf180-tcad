"""B2: zero-current drift-diffusion LOCA sweeps of the 1D strip, central-difference C-V.

usage: python3 b2.py DEVICE PARAMS [ni|dos] [disc]
Writes b2_<device>_<params>.json with C (fF/um^2) per vg, DEVSIM C, and per-step solver data.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import cx
import decks
import numpy as np
import opts

dev, params = sys.argv[1], sys.argv[2]
ni_mode = sys.argv[3] if len(sys.argv) > 3 else "ni"
disc = sys.argv[4] if len(sys.argv) > 4 else "drift diffusion cvfem"
oxd = "laplace cvfem" if "cvfem" in disc else "laplace gfem"
TAU = float(os.environ["CX_TAU"]) if os.environ.get("CX_TAU") else None
tag = f"{dev}_{params}_{ni_mode}_{opts.LIN}_{opts.REL:g}_tau{TAU}"
job = cx.truncate_grid(cx.job1d(dev, params))
xs, xy, blocks, ss = cx.stack_strip(job.stack)
ss = [("gate", *ss[0][1:]), ("body_contact", *ss[1][1:])]
cx.write_exodus("strip.exo", xy, blocks, ss)
DV = 1e-3
step = round(job.vg[1] - job.vg[0], 12)
n = len(job.vg)


def deck(**kw):
    d = decks.moscap_deck(
        job,
        mesh=kw.pop("mesh"),
        out=kw.pop("out"),
        ni_mode=ni_mode,
        disc=disc,
        ox_disc=oxd,
        rel=opts.REL,
        abs_=opts.ABS,
        extra=opts.EXTRA,
        tau=TAU,
        **kw,
    )
    return d.replace("BC is ohmic for body on body", "BC is ohmic for body_contact on body")


def newton_stats(log):
    """Per continuation step: (iterations, last ||F||, last WRMS) from the NOX output."""
    out = []
    for blk in log.split("-- Final Status Test Results --")[1:]:
        f = re.search(r"F-Norm = ([0-9.e+-]+)", blk)
        w = re.search(r"WRMS-Norm = ([0-9.e+-]+)", blk)
        out.append((float(f.group(1)) if f else None, float(w.group(1)) if w else None))
    steps = re.findall(r"-- Nonlinear Solver Step (\d+) --", log)
    its = [int(k) for k in re.findall(r"Step Converged in (\d+) Nonlinear", log)]
    fails = re.findall(r"Value of continuation parameter at failed step = (\S+)", log)
    return {"final": out, "iters": its, "failed_at": fails}, len(steps)


def solve(name, gate_bc, problem, *, mesh, idx=None, init="equilibrium", sweep=None):
    Path(f"{name}.inp").write_text(
        deck(
            mesh=mesh,
            out=f"{name}.exo",
            gate_bc=gate_bc,
            problem=problem,
            import_index=idx,
            init=init,
            sweep=sweep,
        )
    )
    ok, out, dt = cx.run(f"{name}.inp")
    stats, nsteps = newton_stats(out)
    fails = len(stats["failed_at"])
    print(
        f"{name}: ok={ok} {dt:.1f}s newton_steps={nsteps} final_tests={len(stats)} "
        f"failed_msgs={fails}",
        flush=True,
    )
    if not ok:
        print("failed_at", stats["failed_at"][:5], "iters tail", stats["iters"][-5:])
        Path("b2_failed.json").write_text(json.dumps({
            "deck": name, "failed_at": stats["failed_at"], "iterations": stats["iters"],
            "final": stats["final"],
            # the failed step's Newton iterations against the limit, from its last status test
            "newton_limit": [list(map(int, m)) for m in
                             re.findall(r"Number of Iterations = (\d+) < (\d+)", out)[-1:]],
        }, indent=1))  # fmt: skip
        raise SystemExit(f"{name} failed")
    return out, dt, stats


res = {"device": dev, "params": params, "ni_mode": ni_mode, "disc": disc}
t0 = time.time()
# equilibrium at 0 V
solve("eq", "fixed at 0.0", "steady state", mesh="strip.exo")
va0 = job.vg[0] - job.dv_fb - DV
vb0 = job.vg[0] - job.dv_fb + DV
# ramp 0 -> va0 (and vb0) with LOCA, then sweeps A and B with the grid step
ramp_opts = [
    f"initial step size = {abs(step)!r}",
    f"minimum step size = {1e-4!r}",
    f"maximum step size = {abs(step)!r}",
    "hit continuation bound = true",
    "predictor method is constant",
]
for side, v0 in (("A", va0), ("B", vb0)):
    solve(
        f"ramp{side}",
        f"swept from 0.0 to {v0!r}",
        "parameter sweep",
        mesh="eq.exo",
        idx=None,
        init="exodus",
        sweep=ramp_opts,
    )
    head, rows = cx.read_currents("currents-loca.dat")
    import shutil

    shutil.copy("currents-loca.dat", f"currents-ramp{side}.dat")
    res[f"ramp{side}_last_v"] = rows[-1][head.index("gate_Voltage")]
    v1 = v0 + (n - 1) * step
    sub = int(
        os.environ.get("CX_SUB") or 1
    )  # LOCA steps per grid step (every sub-th state is a grid point)
    h = abs(step) / sub  # LOCA takes the direction from the bounds
    sw_opts = [
        f"initial step size = {h!r}",
        f"minimum step size = {h!r}",
        f"maximum step size = {h!r}",
        f"maximum number of steps = {(n - 1) * sub + 5}",
        "hit continuation bound = false",
        "step size aggressiveness = 0.0",
        f"predictor method is {os.environ.get('CX_PRED') or 'secant'}",
    ]
    res["sub"] = sub
    out, dt, stats = solve(
        f"sweep{side}",
        f"swept from {v0!r} to {v1!r}",
        "parameter sweep",
        mesh=f"ramp{side}.exo",
        idx=-1,
        init="exodus",
        sweep=sw_opts,
    )
    shutil.copy("currents-loca.dat", f"currents-sweep{side}.dat")
    head, rows = cx.read_currents("currents-loca.dat")
    res[f"v{side}"] = list(rows[:, head.index("gate_Voltage")])
    res[f"time{side}"] = dt
    res[f"stats{side}"] = stats
    st = cx.read_states(f"sweep{side}.exo")
    bn = job.stack.node_positions_um()[1]
    q = [
        cx.oxide_flux_charge(
            st, k, xs, bn[1], bn[2], job.stack.constants.eps_ox, job.stack.constants.eps0_f_per_cm
        )
        for k in range(len(st.times))
    ]
    res[f"q{side}"] = q
    res[f"t{side}"] = list(st.times)
for side, sgn in (("A", -1), ("B", 1)):
    want = np.array(job.vg) - job.dv_fb + sgn * DV
    got = np.array(res[f"v{side}"])
    res[f"align{side}"] = float(np.max(np.abs(got - want))) if len(got) == len(want) else None
    print(side, "states", len(got), "max |v - grid|", res[f"align{side}"])
res["wall_s"] = time.time() - t0  # C, alignment and charge checks: b2an.py
Path(f"b2_{tag}.json").write_text(json.dumps(res, indent=1, default=float))
