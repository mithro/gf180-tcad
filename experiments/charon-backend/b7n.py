"""B7: the Newton iterations where the WRMS test stalls (issue #223).

usage: python3 b7n.py DEVICE PARAMS

Runs after b2.py in the same directory and environment (CX_TAU, CX_REL, CX_ABS, CX_SUB). If b2.py
stopped (b2_failed.json), it repeats the failed Newton solve as a steady-state solve with
Charon's "write linear system is on", twice: at the WRMS tolerances 1e-10/1e-12 and 1e-11/1e-13.
After every Newton iteration Charon then writes the Jacobian J, the iterate x, the previous
iterate and the residual f as Matrix Market files (charon::NOXObserver_EorTpetraOutput).

- A failed LOCA step ("failed at V1 from V0", the last one in the deck's log): the steady state at
  V1 from the deck's last Exodus state, the converged state at V0.
- A failed equilibrium: the equilibrium deck itself.

Amesos2's KLU2 adapter in the image never calls KLU's klu_rcond or klu_condest, and NOX prints no
condition number, so Charon cannot report one. This script computes the exact 1-norm condition
number of the written Jacobian per iteration (its LU factors solve for every column of J^-1), of
J as written and of J with each row divided by the sum of its magnitudes (NOX's "Function
Scaling = Row Sum"), and the 2-norm condition numbers at the last iteration.

The vector files list the unknowns in Panzer's local order, the first appearance of each node in
the elements of the blocks in alphabetical order; the matrix lists them by node. ``gid_order``
maps one onto the other, and the linear residual ||J dx + f|| / ||f|| of every iteration checks
the map. Per iteration it records the update and residual norms, the WRMS norm recomputed from
the files beside the one NOX prints, and the condition numbers. At the last iteration it records
the WRMS floors of FLOORS and the share of the WRMS norm per field. Writes b7n.json and keeps the
files of the last iteration only.
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
FIELDS = ("potential", "electrons", "holes")  # per drift-diffusion node; oxide nodes: potential
LAPLACE_BLOCKS = ("oxide",)
SEED = 0  # the signs of floor_f_signed
LOCA_FAILED = re.compile(r"Value of continuation parameter at failed step = (\S+) from (\S+)")
STEP = re.compile(
    r"-- Nonlinear Solver Step (\d+) -- \s*\n\|\|F\|\| = (\S+)\s+step = (\S+)\s+dx = (\S+)"
)
STATUS = re.compile(
    r"-- (?:Final )?Status Test Results --\n.*?F-Norm = (\S+) <.*?WRMS-Norm = (\S+) <.*?"
    r"Number of Iterations = (\d+) <",
    re.DOTALL,
)
FLOORS = """With x the previous iterate (the one the WRMS weights use), eps the double precision
unit round-off and |.| elementwise: floor_x is the WRMS norm of an update eps*|x_i| in every
unknown, the round-off of the scaled unknowns; f_roundoff_2 is the 2-norm of eps*(|J| |x|), the
round-off of a residual whose terms have the size of |J| |x|; floor_f_signed is the WRMS norm
of J^-1 (s * eps*(|J| |x|)), the update that residual round-off of that size produces, for signs
s of +-1 drawn with numpy's default_rng(SEED); floor_f_bound is the WRMS norm of |J^-1| eps*(|J|
|x|), the bound on that update."""


def wrms(dx, x, rel, abs_):
    return float(np.sqrt(np.mean((dx / (rel * np.abs(x) + abs_)) ** 2)))


def gid_order(blocks: dict) -> tuple[np.ndarray, list[str]]:
    """``perm`` with ``perm[i]`` the matrix index of vector entry i, and the field of each matrix
    index. Each node of a drift-diffusion block carries FIELDS, an oxide node the potential; the
    matrix numbers them node by node, the vectors by first appearance in the elements of the
    blocks in alphabetical order (Panzer's DOF manager)."""
    nodes = 1 + max(int(c.max()) for c in blocks.values())
    nf = np.ones(nodes, dtype=int)
    for name, conn in blocks.items():
        if name not in LAPLACE_BLOCKS:
            nf[np.unique(conn)] = len(FIELDS)
    start = np.concatenate([[0], np.cumsum(nf)[:-1]])
    fields = [FIELDS[k] for n in range(nodes) for k in range(nf[n])]
    seen, perm = set(), []
    for name in sorted(blocks):
        for element in blocks[name]:
            for n in map(int, element):
                if n not in seen:
                    seen.add(n)
                    perm += [start[n] + k for k in range(nf[n])]
    if len(perm) != nf.sum():
        raise ValueError(f"{len(perm)} unknowns from the elements, {nf.sum()} from the nodes")
    return np.asarray(perm), fields


def mm(path, perm=None):
    """A Matrix Market file: a sparse matrix (CSC), or a vector put into matrix order."""
    a = scipy.io.mmread(str(path))
    if scipy.sparse.issparse(a):
        return scipy.sparse.csc_matrix(a)
    v = np.asarray(a).ravel()
    out = np.empty_like(v)
    out[perm] = v
    return out


def inverse(a):
    """J^-1 as a dense array, from the sparse LU factors."""
    return scipy.sparse.linalg.splu(a).solve(np.eye(a.shape[0]))


def row_sums(a):
    return np.asarray(abs(a).sum(axis=1)).ravel()


def conditions(a):
    """The exact 1-norm condition numbers of J and of D^-1 J (D the row sums of |J|), and J^-1."""
    inv = inverse(a)
    d = row_sums(a)
    scaled = scipy.sparse.diags(1.0 / d) @ a
    # (D^-1 J)^-1 = J^-1 D: J^-1 with column j times d_j
    return (
        float(scipy.sparse.linalg.norm(a, 1) * np.abs(inv).sum(axis=0).max()),
        float(scipy.sparse.linalg.norm(scaled, 1) * np.abs(inv * d).sum(axis=0).max()),
        inv,
    )


def analyse(d: Path, rel, abs_, log_text, perm, fields, state, scales):
    """Per-iteration records from the Matrix Market files in d, and the last iteration's
    floors, 2-norm condition numbers and WRMS shares."""
    steps = {int(k): (float(f), float(s), float(dx)) for k, f, s, dx in STEP.findall(log_text)}
    status = {int(k): (float(f), float(w)) for f, w, k in STATUS.findall(log_text)}
    count = len(list(d.glob("J_*.mm")))
    its = []
    for c in range(count):
        J = mm(d / f"J_{c}.mm")
        x, px, f = (mm(d / f"{n}_{c}.mm", perm) for n in ("x", "prev_x", "f"))
        dx = x - px
        cond1, cond1_scaled, inv = conditions(J)
        k = c + 1  # NOX's iteration number of this update
        its.append(
            {
                "iteration": k,
                "dx_2": float(np.linalg.norm(dx)),
                "dx_inf": float(np.max(np.abs(dx))),
                "f_2": float(np.linalg.norm(f)),
                "wrms": wrms(dx, px, rel, abs_),
                "linear_rel_residual": float(np.linalg.norm(J @ dx + f) / np.linalg.norm(f)),
                "cond1": cond1,
                "cond1_row_scaled": cond1_scaled,
                "log_fnorm": status.get(k, (None, None))[0],
                "log_wrms": status.get(k, (None, None))[1],
                "log_step": steps.get(k, (None, None, None))[1],
                "log_dx": steps.get(k, (None, None, None))[2],
            }
        )
    if not its:
        return {"iterations": []}
    last = count - 1
    J = mm(d / f"J_{last}.mm")
    x, px = (mm(d / f"{n}_{last}.mm", perm) for n in ("x", "prev_x"))
    dense = J.toarray()
    inv = inverse(J)
    weights = 1.0 / (rel * np.abs(px) + abs_)
    roundoff = EPS * (np.abs(dense) @ np.abs(px))
    signs = np.random.default_rng(SEED).choice([-1.0, 1.0], size=len(px))
    contrib = ((x - px) * weights) ** 2
    fld = np.asarray(fields)
    # the imported state against the first previous iterate, field by field (scaled)
    first = mm(d / "prev_x_0.mm", perm) if (d / "prev_x_0.mm").is_file() else None
    final = {
        "unknowns": len(px),
        "cond2": float(np.linalg.cond(dense, 2)),
        "cond2_row_scaled": float(np.linalg.cond(dense / row_sums(J)[:, None], 2)),
        "floor_x": float(np.sqrt(np.mean((EPS * np.abs(px) * weights) ** 2))),
        "f_roundoff_2": float(np.linalg.norm(roundoff)),
        "floor_f_signed": float(np.sqrt(np.mean(((inv @ (signs * roundoff)) * weights) ** 2))),
        "floor_f_bound": float(np.sqrt(np.mean(((np.abs(inv) @ roundoff) * weights) ** 2))),
        "wrms_share_by_field": {f: float(contrib[fld == f].sum() / contrib.sum()) for f in FIELDS},
        "unknowns_by_field": {f: int(np.sum(fld == f)) for f in FIELDS},
    }
    if first is not None and state is not None:
        final["state_check_max_rel"] = state_check(first, fields, state, scales)
    for c in range(last):  # keep the last iteration's files only
        for n in ("J", "x", "prev_x", "f"):
            (d / f"{n}_{c}.mm").unlink()
    return {"iterations": its, "last": final}


EXODUS_FIELD = {"potential": ("ELECTRIC_POTENTIAL", "V0"), "electrons": ("ELECTRON_DENSITY", "C0"),
                "holes": ("HOLE_DENSITY", "C0")}  # fmt: skip


def state_check(px, fields, state, scales):
    """The largest relative difference, per field, between the first iteration's previous iterate
    (matrix order) and the imported Exodus state, scaled (the log prints V0 to six digits)."""
    nodes = len(state["ELECTRIC_POTENTIAL"])
    node_of, n = [], 0
    for f in fields:  # matrix order is node by node, the fields of a node consecutive
        if f == "potential" and node_of:
            n += 1
        node_of.append(n)
    if node_of[-1] != nodes - 1:
        raise ValueError(f"{node_of[-1] + 1} nodes in the matrix order, {nodes} in the state")
    out = {}
    for f in FIELDS:
        idx = [i for i, g in enumerate(fields) if g == f]
        name, scale = EXODUS_FIELD[f]
        want = state[name][[node_of[i] for i in idx]] / scales[scale]
        got = px[idx]
        out[f] = float(np.max(np.abs(got - want) / np.maximum(np.abs(want), np.finfo(float).tiny)))
    return out


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
    deck = json.loads(Path("b2_failed.json").read_text())["deck"]
    tau = float(os.environ["CX_TAU"]) if os.environ.get("CX_TAU") else None
    job = cx.job1d(dev, params)
    if deck == "eq":  # the equilibrium itself: its own deck again
        mesh, kw, state = "strip.exo", {"gate_bc": "fixed at 0.0", "init": "equilibrium"}, None
        out.update(stalled=True, deck=deck, failed_at_v=0.0, from_v=None)
    else:
        failures = LOCA_FAILED.findall(Path(f"{deck}.inp.log").read_text(errors="replace"))
        v1, v0_log = (float(v) for v in failures[-1])
        head, rows = cx.read_currents("currents-loca.dat")  # the failed deck's converged states
        v0 = float(rows[-1, head.index("gate_Voltage")])
        st = cx.read_states(f"{deck}.exo")
        # the log prints the bias to four significant digits, the currents file to nine
        if len(st.times) != len(rows) or abs(v0 - v0_log) > 5e-4 * abs(v0_log):
            raise SystemExit(
                f"{deck}.exo: {len(st.times)} states, {len(rows)} converged rows, last {v0} V, "
                f"log {v0_log} V"
            )
        state = {k: v[-1, :] for k, v in st.nodal.items()}
        mesh = f"{deck}.exo"
        kw = {"gate_bc": f"fixed at {v1!r}", "init": "exodus", "import_index": -1}
        out.update(stalled=True, deck=deck, failed_at_v=v1, from_v=v0, from_v_log=v0_log)
    perm, fields = gid_order(cx.read_states(mesh).blocks)
    out["solves"] = {}
    for rel, abs_ in TOLERANCES:
        name = f"diag_{rel:g}"
        d = Path(name)
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir()
        shutil.copy(mesh, d / "mesh.exo")
        text = decks.moscap_deck(
            job,
            mesh="mesh.exo",
            out="diag.exo",
            problem="steady state",
            rel=rel,
            abs_=abs_,
            extra=[*opts.EXTRA, "write linear system is on"],
            tau=tau,
            **kw,
        )
        text = text.replace("BC is ohmic for body on body", "BC is ohmic for body_contact on body")
        (d / "diag.inp").write_text(text)
        cwd = Path.cwd()
        os.chdir(d)
        try:
            ok, log, dt = cx.run("diag.inp", current=False)
            scales = {k: float(re.search(rf"{k} = (\S+)", log).group(1)) for k in ("V0", "C0")}
            Path("mesh.exo").unlink()
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
                **analyse(Path("."), rel, abs_, log, perm, fields, state, scales),
            }
        finally:
            os.chdir(cwd)
        out["solves"][f"{rel:g}"] = rec
        last = rec["iterations"][-1] if rec["iterations"] else {}
        print(name, "converged", ok, "iterations", len(rec["iterations"]), "last wrms",
              last.get("wrms"), "log", last.get("log_wrms"), "linear residual",
              last.get("linear_rel_residual"), flush=True)  # fmt: skip
    Path("b7n.json").write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
