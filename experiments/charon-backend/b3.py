"""B3: which linear solvers the tpetra block can use, and whether a direct solver (Amesos2 KLU2)
runs and changes the result.

Runs the nfet calibrated strip: an equilibrium solve, then a 27-point LOCA sweep from -1 V to
+0.3 V (0.05 V steps; inversion does not converge, B2) with (a) the interpreter's Belos GMRES at tolerance 1e-12 and (b) Amesos2
KLU2 set through 'Direct input'. Compares the oxide-flux gate charge of every state.
"""

import json
import re
import subprocess
from pathlib import Path

import cx
import decks
import numpy as np

out = {}
cfg = Path("/opt/charon/include")
for name in ("Stratimikos_Config.h", "StratimikosConfig.h", "Amesos2_config.h"):
    p = cfg / name
    if p.exists():
        out[name] = [
            l
            for l in p.read_text().splitlines()
            if re.search(r"AMESOS2|KLU|BELOS|AZTEC|IFPACK|MUELU|AMESOS\b", l)
        ]
r = subprocess.run(  # noqa: PLW1510 - the grep exit code is not an error
    ["bash", "-c", "ls /opt/charon/lib | grep -i -E 'amesos|stratimikos|belos'"],
    capture_output=True,
    text=True,
)
out["libs"] = r.stdout.split()

job = cx.job1d("nfet_05v0", "calibrated")
xs, xy, blocks, ss = cx.stack_strip(job.stack)
ss = [("gate", *ss[0][1:]), ("body_contact", *ss[1][1:])]
cx.write_exodus("strip.exo", xy, blocks, ss)
bn = job.stack.node_positions_um()[1]

PFX = "Charon->Solution Control->NOX->Direction->Newton->Stratimikos Linear Solver->Stratimikos"
CONFIGS = {
    "belos": [],
    "amesos2_klu2": [
        f'Direct input "{PFX},Linear Solver Type,string,Amesos2"',
        f'Direct input "{PFX},Preconditioner Type,string,None"',
        f'Direct input "{PFX}->Linear Solver Types->Amesos2,Solver Type,string,KLU2"',
    ],
}


def deck(name, gate_bc, problem, mesh, init, extra, sweep=None):
    d = decks.moscap_deck(
        job,
        mesh=mesh,
        out=f"{name}.exo",
        gate_bc=gate_bc,
        problem=problem,
        init=init,
        extra=extra,
        sweep=sweep,
    )
    return d.replace("BC is ohmic for body on body", "BC is ohmic for body_contact on body")


sweep = [
    "initial step size = 0.05",
    "minimum step size = 0.05",
    "maximum step size = 0.05",
    "maximum number of steps = 60",
    "hit continuation bound = false",
    "step size aggressiveness = 0.0",
    "predictor method is secant",
]
charges = {}
for cname, extra in CONFIGS.items():
    Path(f"{cname}_eq.inp").write_text(
        deck(f"{cname}_eq", "fixed at -1.0", "steady state", "strip.exo", "equilibrium", extra)
    )
    ok, log, dt = cx.run(f"{cname}_eq.inp")
    rec = {
        "eq_ok": ok,
        "eq_time_s": dt,
        "solver_lines": sorted(
            set(
                re.findall(
                    r"Using iterative solver = .*|Amesos2[^\n]{0,80}|"
                    r"KLU2[^\n]{0,60}",
                    log,
                )
            )
        )[:10],
    }
    if not ok:
        rec["tail"] = log[-3000:]
        out[cname] = rec
        print(cname, "equilibrium failed")
        continue
    Path(f"{cname}_sw.inp").write_text(
        deck(
            f"{cname}_sw",
            "swept from -1.0 to 0.3",
            "parameter sweep",
            f"{cname}_eq.exo",
            "exodus",
            extra,
            sweep,
        )
    )
    ok, log, dt = cx.run(f"{cname}_sw.inp")
    rec.update(
        sweep_ok=ok,
        sweep_time_s=dt,
        newton_steps=len(re.findall(r"-- Nonlinear Solver Step \d+ --", log)),
        belos_iteration_blocks=log.count("Starting iterations with Belos"),
        xml_linear_solver_type=re.findall(
            r'name="Linear Solver Type" type="string" value="(\w+)"',
            Path(f"{cname}_sw.inp.xml").read_text(),
        ),
    )
    if ok:
        st = cx.read_states(f"{cname}_sw.exo")
        q = [
            cx.oxide_flux_charge(
                st,
                k,
                xs,
                bn[1],
                bn[2],
                job.stack.constants.eps_ox,
                job.stack.constants.eps0_f_per_cm,
            )[0]
            for k in range(len(st.times))
        ]
        charges[cname] = np.array(q)
        rec["states"] = len(q)
    else:
        rec["tail"] = log[-3000:]
    out[cname] = rec
    print(cname, {k: v for k, v in rec.items() if k != "tail"}, flush=True)
if len(charges) == 2:
    a, b = charges["belos"], charges["amesos2_klu2"]
    if len(a) == len(b):
        rel = np.abs(a - b) / np.max(np.abs(a))
        out["max_rel_charge_diff"] = float(np.max(rel))
        print("max |dQ|/max|Q| belos vs klu2:", float(np.max(rel)))
Path("b3.json").write_text(json.dumps(out, indent=1, default=float))
print(json.dumps({k: v for k, v in out.items() if k not in ("belos", "amesos2_klu2")}, indent=1))
