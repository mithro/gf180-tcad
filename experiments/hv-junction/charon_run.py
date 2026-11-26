# SPDX-License-Identifier: Apache-2.0
"""Reverse-bias sweep of a junction in Charon, from a mesh dumped by charon_mesh.py.

    python charon_run.py case PARAMS.json MESH.npz RESULT.json
    python charon_run.py diode NA LENGTH_UM VMAX VSTEP MESH.npz RESULT.json

Runs inside the Charon image, in the working directory (run.py --charon OUTDIR ...).
PARAMS is the dictionary of structure.py with "vmax" and "vstep"; optional keys
"charon_scheme" (default "cvfem"), "charon_min_step", "charon_tau" (carrier lifetime in
the sweep, default charon_deck.SEED_TAU) and "charon_quads" (QUAD4 instead of TRI3).

Stages, each a deck of charon_deck.py run through charonInterpreter.py and then
charon_mp.exe: nonlinear Poisson, drift-diffusion at 0 V, and the sweep of the well
contact with impact ionisation. Files are named after the stage (sweep.inp, sweep.exo,
sweep.log ...). RESULT holds

  v, i_well, i_sub      bias points and contact currents, A per cm of depth
  i_min                 the smaller of |i_well| and |i_sub|; the two criteria below use it
  last_converged_v      the highest bias with a solution, and reached_vmax
  bv_current_v          bias where the current is 100 times its low-bias trend
  bv_threshold_v        bias where the current passes I_THRESHOLD
  bv_integral_v         bias where the ionisation integral of ionize.py reaches 1 on
                        Charon's potential (fieldline.max_integral)
  bv_integral_low_branch_v   the same with the hole coefficient Charon's
                        control-volume scheme has (see charon_deck._avalanche_lines)
  integral              per bias: i_n, emax (peak silicon field, V/cm), where_um. Biases
                        from two steps below last_converged_v upwards come from a second
                        sweep without impact ionisation (field.exo), which goes past it
  potentials            files with the potential on DEVSIM's silicon nodes, each 10 V
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

import numpy as np

import charon_deck
import charon_field
import charon_mesh
import ionize

I_THRESHOLD = 1.0e-7  # A per cm of depth
MULTIPLICATION = 100.0
SAVE_EVERY_V = 10.0


def run_stage(stage, text):
    """Write stage.inp, translate it, run Charon. Returns (exit code, seconds)."""
    with open(f"{stage}.inp", "w") as f:
        f.write(text)
    for line in text.splitlines():
        if "output tabulated parameter currents to" in line:
            pathlib.Path(line.split()[-1]).unlink(missing_ok=True)
    t0 = time.time()
    with open(f"{stage}.log", "w") as log:
        r = subprocess.run(["charonInterpreter.py", "-i", f"{stage}.inp"],
                           stdout=log, stderr=subprocess.STDOUT)  # fmt: skip
        if r.returncode:
            raise RuntimeError(f"charonInterpreter.py failed on {stage}.inp, see {stage}.log")
        log.flush()
        r = subprocess.run(["charon_mp.exe", f"--i={stage}.inp.xml", "--current"],
                           stdout=log, stderr=subprocess.STDOUT)  # fmt: skip
    seconds = time.time() - t0
    print(f"STAGE {stage} exit {r.returncode} in {seconds:.0f}s", flush=True)
    return r.returncode, seconds


def read_currents(path):
    """The table Charon appends one row to per converged bias: {column: array}.

    Charon appends to a file left by an earlier run, with a new header line; only the
    rows after the last header count (run_stage also removes old tables).
    """
    names, rows = [], []
    with open(path) as f:
        for line in f:
            tokens = line.split()
            if tokens and not tokens[0][0].isdigit() and tokens[0][0] not in "+-.":
                names, rows = tokens, []
            elif tokens:
                rows.append([float(t) for t in tokens])
    rows = [r for r in rows if len(r) == len(names)]
    table = np.array(rows).reshape(-1, len(names))
    return {n: table[:, k] for k, n in enumerate(names)}


def _crossing(v, ratio):
    """First bias where ratio reaches 1, by interpolation of log(ratio)."""
    above = np.nonzero(ratio >= 1.0)[0]
    if len(above) == 0:
        return None
    k = int(above[0])
    if k == 0:
        return float(v[0])
    l0, l1 = np.log(ratio[k - 1]), np.log(ratio[k])
    return float(v[k - 1] + (v[k] - v[k - 1]) * (0.0 - l0) / (l1 - l0))


def bv_by_current(v, i, factor=MULTIPLICATION, window=(0.15, 0.5), vbi=0.8):
    """Bias where |i| is `factor` times its low-bias trend, and the trend.

    The trend is a power law of (v + vbi), the form of generation in a depletion layer,
    fitted where v lies between the `window` fractions of the highest bias. Returns
    (bv or None, [amplitude, exponent]).
    """
    v, i = np.asarray(v, dtype=float), np.abs(np.asarray(i, dtype=float))
    use = (v >= window[0] * v.max()) & (v <= window[1] * v.max()) & (i > 0)
    if use.sum() < 3:
        return None, None
    slope, icpt = np.polyfit(np.log(v[use] + vbi), np.log(i[use]), 1)
    trend = np.exp(icpt) * (v + vbi) ** slope
    ok = i > 0
    return _crossing(v[ok], i[ok] / (factor * trend[ok])), [float(np.exp(icpt)), float(slope)]


def bv_by_threshold(v, i, threshold=I_THRESHOLD):
    v, i = np.asarray(v, dtype=float), np.abs(np.asarray(i, dtype=float))
    ok = i > 0
    return _crossing(v[ok], i[ok] / threshold)


def field_sweep(dev, sweep, vmax, vstep, min_step, common, back=2.0, beyond=1.15):
    """Carry the potential past the bias where the avalanche sweep stopped.

    A second sweep without impact ionisation, started from the plane of the avalanche
    sweep `back` steps below its last one, up to `beyond` times the last bias. Returns
    (its planes, the bias it starts at, seconds). The ionisation integral needs these
    planes to cross 1; DEVSIM's sweep has no impact ionisation either.
    """
    last = float(sweep.v.max())
    early = np.nonzero(sweep.v <= last - back * vstep + 1e-9)[0]
    k0 = int(early.max()) if len(early) else 0
    v_from, v_to = float(sweep.v[k0]), min(vmax, beyond * last + 2 * vstep)
    text = charon_deck.deck(dev, "sweep", "sweep.exo", "field.exo", v0=v_from, v1=v_to,
                            step=vstep, min_step=min_step, avalanche=False, index=k0 + 1,
                            currents="currents_field.dat", **common)  # fmt: skip
    _, seconds = run_stage("field", text)
    field = charon_field.Sweep("field.exo", "mesh.exo.map.npz")
    field.v0 = sweep.v0
    diff = float(np.abs(field.potential(0) - sweep.potential(k0)).max())
    print(f"FIELD restart at {v_from:g} V (plane {k0}), to {v_to:g} V; "
          f"first plane differs from it by {diff:.2e} V", flush=True)  # fmt: skip
    return field, v_from, seconds


def simulate(dev, mesh_npz, vmax, vstep, step_cm, scheme="cvfem", min_step=None,
             tau=charon_deck.SEED_TAU, quads=False):  # fmt: skip
    """Mesh file, the three stages, then the post-processing. Returns the result."""
    t0 = time.time()
    meta, arrays = charon_mesh.load_dump(mesh_npz)
    merged = charon_mesh.merge(meta, arrays, quads=quads)
    charon_mesh.write_exodus(merged, "mesh.exo")
    counts = charon_mesh.summary(meta, merged)
    print("MESH", json.dumps(counts), flush=True)
    seconds = {}
    min_step = min_step if min_step is not None else vstep / 8
    common = {"scheme": scheme, "tau": tau}
    for stage, src in (("nlp", "mesh.exo"), ("dd0", "nlp.exo")):
        text = charon_deck.deck(dev, stage, src, f"{stage}.exo", **common)
        rc, seconds[stage] = run_stage(stage, text)
        if rc:
            raise RuntimeError(f"stage {stage} failed, see {stage}.log")
    text = charon_deck.deck(dev, "sweep", "dd0.exo", "sweep.exo", v0=0.0, v1=vmax, step=vstep,
                            min_step=min_step, **common)  # fmt: skip
    rc, seconds["sweep"] = run_stage("sweep", text)
    cur = read_currents("currents.dat")
    v = cur["well_Voltage"]
    i_well = cur[[n for n in cur if n.startswith("well_") and n.endswith("_Current")][0]]
    i_sub = cur[[n for n in cur if n.startswith("sub_") and n.endswith("_Current")][0]]
    # The two contact currents are equal and opposite; the one of a heavily doped contact
    # shows isolated spikes (round-off in its evaluation), so the criteria take the smaller.
    i_min = np.minimum(np.abs(i_well), np.abs(i_sub))
    bv_cur, trend = bv_by_current(v, i_min)
    sweep = charon_field.Sweep("sweep.exo", "mesh.exo.map.npz")
    field, v_join = None, np.inf
    if v.max() < vmax - 1e-9:
        field, v_join, seconds["field"] = field_sweep(dev, sweep, vmax, vstep, min_step, common)
    t1 = time.time()
    below = [k for k in range(len(sweep.v)) if sweep.v[k] < v_join - 1e-9]
    scan = charon_field.scan_both(sweep, step_cm, below)
    files = charon_field.save_potentials(sweep, SAVE_EVERY_V, "potential_", v_hi=v_join - 1e-9)
    if field is not None:
        more = charon_field.scan_both(field, step_cm)
        scan = {k: scan[k] + more[k] for k in scan}
        files += charon_field.save_potentials(field, SAVE_EVERY_V, "potential_", v_lo=v_join)
    bv_int = ionize.breakdown_voltage(scan["v"], scan["i_n"])
    bv_low = ionize.breakdown_voltage(scan["v"], scan["i_n_low_branch"])
    seconds["post"] = time.time() - t1
    seconds["total"] = time.time() - t0
    out = {
        "scheme": scheme, "tau_s": tau, "elements": "QUAD4" if quads else "TRI3",
        "sweep_exit_code": rc, "nodes": counts,
        "v": v.tolist(), "i_well": i_well.tolist(), "i_sub": i_sub.tolist(),
        "i_min": i_min.tolist(),
        "last_converged_v": float(v.max()), "reached_vmax": bool(v.max() >= vmax - 1e-9),
        "bv_current_v": bv_cur, "current_trend": trend,
        "bv_threshold_v": bv_by_threshold(v, i_min), "i_threshold": I_THRESHOLD,
        "bv_integral_v": bv_int, "bv_integral_low_branch_v": bv_low,
        "integral": scan, "v0_volts": sweep.v0, "potentials": files, "seconds": seconds,
    }  # fmt: skip
    print("RESULT", json.dumps({k: out[k] for k in (
        "last_converged_v", "reached_vmax", "bv_current_v", "bv_threshold_v", "bv_integral_v",
        "bv_integral_low_branch_v", "seconds")}), flush=True)  # fmt: skip
    return out


def main(argv):
    mode = argv[0]
    if mode == "case":
        p = json.load(open(argv[1]))
        meta, _ = charon_mesh.load_dump(argv[2])
        dev = charon_deck.describe_params(p, meta["regions"])
        out = simulate(dev, argv[2], p["vmax"], p["vstep"], 0.5 * p["mesh"]["surf"] * 1e-4,
                       scheme=p.get("charon_scheme", "cvfem"), min_step=p.get("charon_min_step"),
                       tau=p.get("charon_tau", charon_deck.SEED_TAU),
                       quads=p.get("charon_quads", False))  # fmt: skip
        out["params"] = p
        result = argv[3]
    elif mode == "diode":
        na, length, vmax, vstep = (float(a) for a in argv[1:5])
        dev = charon_deck.describe_diode(na, length_um=length)
        out = simulate(dev, argv[5], vmax, vstep, 1e-7)
        out["diode"] = {"na": na, "length_um": length}
        result = argv[6]
    else:
        sys.exit(f"unknown mode {mode}")
    json.dump(out, open(result, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
