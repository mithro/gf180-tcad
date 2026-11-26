"""B7: the Newton iterations where the WRMS test stalls (issue #223).

usage: python3 b7n.py DEVICE PARAMS

Runs after b2.py in the same directory and environment (CX_TAU, CX_REL, CX_ABS, CX_SUB). If b2.py
stopped (b2_failed.json), it takes the last failed LOCA step of the failed deck, "failed at V1 from
V0", and solves the steady state at V1 from the deck's last Exodus state, the converged state at V0.
It does so twice, at the WRMS tolerances 1e-10/1e-12 and 1e-11/1e-13, with Charon's "write linear
system is on": after every Newton iteration Charon writes the Jacobian J, the iterate x, the
previous iterate and the residual f as Matrix Market files (charon::NOXObserver_EorTpetraOutput).

Amesos2's KLU2 adapter in the image never calls KLU's klu_rcond or klu_condest, and NOX prints no
condition number, so Charon cannot report one; this script computes it from the written Jacobian:
per iteration the 1-norm condition estimate (Hager-Higham, scipy's onenormest on the LU solve) of
J and of J with each row divided by the sum of its magnitudes (NOX's "Function Scaling = Row
Sum"); at the last iteration the exact 1-norm and 2-norm condition numbers too. Per iteration it
also records the update norms, the residual norm, the WRMS norm recomputed from the files and the
relative residual of the linear solve. At the last iteration it records the two floors of the WRMS
norm the issue compares (see FLOORS). Writes b7n.json; keeps the files of the last iteration.
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

import cx
import decks
import numpy as np
import opts
import scipy.io
import scipy.sparse
import scipy.sparse.linalg

EPS = float(np.finfo(np.float64).eps)
TOLERANCES = ((1e-10, 1e-12), (1e-11, 1e-13))
LOCA_FAILED = re.compile(r"Value of continuation parameter at failed step = (\S+) from (\S+)")
STEP = re.compile(
    r"-- Nonlinear Solver Step (\d+) -- \s*\n\|\|F\|\| = (\S+)\s+step = (\S+)\s+dx = (\S+)"
)
STATUS = re.compile(
    r"-- (?:Final )?Status Test Results --\n.*?F-Norm = (\S+) <.*?WRMS-Norm = (\S+) <.*?"
    r"Number of Iterations = (\d+) <",
    re.DOTALL,
)
FLOORS = """floor_x: the WRMS norm of an update of eps*|x_i| in every unknown, the round-off of the
scaled unknowns themselves; floor_f: the WRMS norm of |J^-1| (eps |J| |x|), the update that a
change of eps*(|J| |x|)_i in each residual row produces, a bound in the Skeel sense, where |.|
is the elementwise magnitude and x the previous iterate (the one the WRMS weights use)."""


def wrms(dx, x, rel, abs_):
    return float(np.sqrt(np.mean((dx / (rel * np.abs(x) + abs_)) ** 2)))


def last_failure(log: Path):
    """The last failed LOCA step of a log: (failed at, stepped from), V."""
    (*_, (v1, v0)) = LOCA_FAILED.findall(log.read_text(errors="replace"))
    return float(v1), float(v0)


def mm(path):
    a = scipy.io.mmread(str(path))
    return a.tocsc() if scipy.sparse.issparse(a) else np.asarray(a).ravel()


def cond1_est(a):
    """The 1-norm condition estimate of a sparse matrix: ||A||_1 times onenormest of A^-1."""
    lu = scipy.sparse.linalg.splu(a.tocsc())
    inv = scipy.sparse.linalg.LinearOperator(
        a.shape, matvec=lu.solve, rmatvec=lambda v: lu.solve(v, trans="T")
    )
    return float(scipy.sparse.linalg.norm(a, 1) * scipy.sparse.linalg.onenormest(inv))


def row_scaled(a):
    return scipy.sparse.diags(1.0 / np.asarray(abs(a).sum(axis=1)).ravel()) @ a


def field_map(px, state, v0_scale, c0):
    """Which field each unknown is, by matching the first iteration's previous iterate (the
    imported state, scaled) to the imported Exodus state: {index: field}, and the counts."""
    # the log prints V0 to six digits, so a potential matches within 1e-5 relative; C0 is exact
    cand = {
        "potential": (state["ELECTRIC_POTENTIAL"] / v0_scale, 1e-5),
        "electrons": (state["ELECTRON_DENSITY"] / c0, 1e-9),
        "holes": (state["HOLE_DENSITY"] / c0, 1e-9),
    }
    out, ambiguous, unmatched = {}, 0, 0
    for i, v in enumerate(px):
        hits = {
            f for f, (c, tol) in cand.items() if np.any(np.abs(c - v) <= tol * max(abs(v), 1e-30))
        }
        if len(hits) == 1:
            out[i] = hits.pop()
        elif hits:
            ambiguous += 1
        else:
            unmatched += 1
    return out, {"matched": len(out), "ambiguous": ambiguous, "unmatched": unmatched}


def analyse(d: Path, rel, abs_, log_text, state, scales):
    """Per-iteration records from the Matrix Market files in d, and the last iteration's
    condition numbers and floors."""
    steps = {int(k): (float(f), float(s), float(dx)) for k, f, s, dx in STEP.findall(log_text)}
    status = {int(k): (float(f), float(w)) for f, w, k in STATUS.findall(log_text)}
    count = len(list(d.glob("J_*.mm")))
    its, fmap, fcounts = [], None, None
    for c in range(count):
        J, x, px, f = (mm(d / f"{n}_{c}.mm") for n in ("J", "x", "prev_x", "f"))
        if c == 0:
            fmap, fcounts = field_map(px, state, scales["V0"], scales["C0"])
        dx = x - px
        k = c + 1  # NOX's iteration number of this update
        it = {
            "iteration": k,
            "dx_2": float(np.linalg.norm(dx)),
            "dx_inf": float(np.max(np.abs(dx))),
            "f_2": float(np.linalg.norm(f)),
            "wrms": wrms(dx, px, rel, abs_),
            "linear_rel_residual": float(np.linalg.norm(J @ dx + f) / np.linalg.norm(f)),
            "cond1_est": cond1_est(J),
            "cond1_est_row_scaled": cond1_est(row_scaled(J)),
            "log_wrms": status.get(k, (None, None))[1],
            "log_fnorm": status.get(k, (None, None))[0],
            "log_dx": steps.get(k, (None, None, None))[2],
            "log_step": steps.get(k, (None, None, None))[1],
        }
        its.append(it)
    if not its:
        return {"iterations": []}
    last = count - 1
    J, px = mm(d / f"J_{last}.mm"), mm(d / f"prev_x_{last}.mm")
    x = mm(d / f"x_{last}.mm")
    dense = J.toarray()
    scaled = row_scaled(J).toarray()
    inv = np.linalg.inv(dense)
    weights = 1.0 / (rel * np.abs(px) + abs_)
    skeel = np.abs(inv) @ (EPS * (np.abs(dense) @ np.abs(px)))
    dx = x - px
    contrib = (dx * weights) ** 2
    by_field = None
    if fmap and len(fmap) == len(px):
        by_field = {
            fld: float(sum(contrib[i] for i, g in fmap.items() if g == fld) / contrib.sum())
            for fld in ("potential", "electrons", "holes")
        }
    top = int(np.argmax(contrib))
    final = {
        "unknowns": len(px),
        "cond1": float(np.linalg.norm(dense, 1) * np.linalg.norm(inv, 1)),
        "cond2": float(np.linalg.cond(dense, 2)),
        "cond1_row_scaled": float(np.linalg.cond(scaled, 1)),
        "cond2_row_scaled": float(np.linalg.cond(scaled, 2)),
        "floor_x": float(np.sqrt(np.mean((EPS * np.abs(px) * weights) ** 2))),
        "floor_f": float(np.sqrt(np.mean((skeel * weights) ** 2))),
        "f_roundoff_2": float(np.linalg.norm(EPS * (np.abs(dense) @ np.abs(px)))),
        "wrms_share_by_field": by_field,
        "wrms_share_top10": float(np.sort(contrib)[-10:].sum() / contrib.sum()),
        "top_unknown": {
            "index": top,
            "field": (fmap or {}).get(top),
            "x": float(px[top]),
            "dx": float(dx[top]),
        },
    }
    for c in range(last):  # keep the last iteration's files only
        for n in ("J", "x", "prev_x", "f"):
            (d / f"{n}_{c}.mm").unlink()
    return {"iterations": its, "last": final, "field_map_counts": fcounts}


def main(dev, params):
    out = {
        "device": dev,
        "params": params,
        "tau": os.environ.get("CX_TAU") or None,
        "search_rel": opts.REL,
        "search_abs": opts.ABS,
        "floors": " ".join(FLOORS.split()),
    }
    b2_exit = int(Path("b2_exit.txt").read_text())
    if (b2_exit == 0) == Path("b2_failed.json").is_file():
        raise SystemExit(
            f"b2.py exited {b2_exit} with b2_failed.json {'present' if b2_exit == 0 else 'missing'}"
        )
    if b2_exit == 0:
        out["stalled"] = False
        Path("b7n.json").write_text(json.dumps(out, indent=1))
        return 0
    failed = json.loads(Path("b2_failed.json").read_text())
    deck = failed["deck"]
    v1, v0 = last_failure(Path(f"{deck}.inp.log"))
    head, rows = cx.read_currents("currents-loca.dat")  # the failed deck's converged states
    vs = rows[:, head.index("gate_Voltage")]
    st = cx.read_states(f"{deck}.exo")
    if len(st.times) != len(vs) or abs(vs[-1] - v0) > 1e-9:
        raise SystemExit(
            f"{deck}.exo: {len(st.times)} states, {len(vs)} converged rows, last "
            f"{vs[-1]} V, want {v0} V"
        )
    state = {k: v[-1, :] for k, v in st.nodal.items()}
    out.update(stalled=True, deck=deck, failed_at_v=v1, from_v=v0)
    tau = float(os.environ["CX_TAU"]) if os.environ.get("CX_TAU") else None
    job = cx.job1d(dev, params)
    out["solves"] = {}
    for rel, abs_ in TOLERANCES:
        name = f"diag_{rel:g}"
        d = Path(name)
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir()
        shutil.copy(f"{deck}.exo", d / "state.exo")
        text = decks.moscap_deck(
            job,
            mesh="state.exo",
            out="diag.exo",
            gate_bc=f"fixed at {v1!r}",
            problem="steady state",
            import_index=-1,
            init="exodus",
            rel=rel,
            abs_=abs_,
            extra=[*opts.EXTRA, "write linear system is on"],
            tau=tau,
        )
        text = text.replace("BC is ohmic for body on body", "BC is ohmic for body_contact on body")
        (d / "diag.inp").write_text(text)
        cwd = Path.cwd()
        os.chdir(d)
        try:
            ok, log, dt = cx.run("diag.inp", current=False)
            scales = {k: float(re.search(rf"{k} = (\S+)", log).group(1)) for k in ("V0", "C0")}
            Path("state.exo").unlink()
            rec = {
                "rel": rel,
                "abs": abs_,
                "converged": ok,
                "wall_s": round(dt, 1),
                "newton_limit": [
                    list(map(int, m))
                    for m in re.findall(r"Number of Iterations = (\d+) < (\d+)", log)[-1:]
                ],
                "scales": scales,
                **analyse(Path("."), rel, abs_, log, state, scales),
            }
        finally:
            os.chdir(cwd)
        out["solves"][f"{rel:g}"] = rec
        last = rec["iterations"][-1] if rec["iterations"] else {}
        print(
            name,
            "converged",
            ok,
            "iterations",
            len(rec["iterations"]),
            "last wrms",
            last.get("wrms"),
            "log",
            last.get("log_wrms"),
            flush=True,
        )
    Path("b7n.json").write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
