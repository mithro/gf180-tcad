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
sweep.log ...; sweep1, sweep2 ... are restarts of the sweep with a smaller step). RESULT holds

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

import charon_deck
import charon_field
import charon_mesh
import ionize
import numpy as np

I_THRESHOLD = 1.0e-7  # A per cm of depth
MULTIPLICATION = 100.0
SAVE_EVERY_V = 10.0
MAX_RESTARTS = 4


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
                           stdout=log, stderr=subprocess.STDOUT, check=False)  # fmt: skip
        if r.returncode:
            raise RuntimeError(f"charonInterpreter.py failed on {stage}.inp, see {stage}.log")
        log.flush()
        r = subprocess.run(["charon_mp.exe", f"--i={stage}.inp.xml", "--current"],
                           stdout=log, stderr=subprocess.STDOUT, check=False)  # fmt: skip
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


def _column(cur, contact):
    return cur[next(n for n in cur if n.startswith(f"{contact}_") and n.endswith("_Current"))]


def avalanche_sweep(dev, vmax, vstep, min_step, common):
    """The sweep with impact ionisation, restarted with a quarter of the step while that
    still gains ground.

    Charon aborts when a Newton step overflows, wherever that happens, so an abort alone
    does not mean breakdown. A restart begins at the last converged plane; the sweep is
    over when the current has passed the 100-fold criterion, or a restart gains less than
    one of its own steps. Returns (v, i_well, i_sub, [planes of each segment], last exit
    code, seconds).
    """
    v, i_well, i_sub, segments, seconds = [], [], [], [], 0.0
    src, index, v_from, step = "dd0.exo", None, 0.0, vstep
    for attempt in range(MAX_RESTARTS + 1):
        name = "sweep" if attempt == 0 else f"sweep{attempt}"
        text = charon_deck.deck(dev, "sweep", src, f"{name}.exo", v0=v_from, v1=vmax, step=step,
                                min_step=min(min_step, step / 8), index=index,
                                currents=f"currents_{name}.dat", **common)  # fmt: skip
        rc, sec = run_stage(name, text)
        seconds += sec
        cur = read_currents(f"currents_{name}.dat")
        first = 0 if attempt == 0 else 1  # a restart repeats the plane it starts from
        v += cur["well_Voltage"][first:].tolist()
        i_well += _column(cur, "well")[first:].tolist()
        i_sub += _column(cur, "sub")[first:].tolist()
        segments.append(charon_field.Sweep(f"{name}.exo", "mesh.exo.map.npz"))
        last = max(v)
        i_min = np.minimum(np.abs(i_well), np.abs(i_sub))
        done = rc == 0 or last >= vmax - 1e-9 or bv_by_current(v, i_min)[0] is not None
        if done or (attempt > 0 and last - v_from < 0.99 * step):
            break
        print(f"RESTART {attempt + 1} from {last:g} V with step {step / 4:g} V", flush=True)
        src, index, v_from, step = f"{name}.exo", len(segments[-1].v), last, step / 4
    return np.array(v), np.array(i_well), np.array(i_sub), segments, rc, seconds


def field_sweep(dev, segments, vmax, vstep, min_step, common, back=2.0, beyond=1.15):
    """Carry the potential past the bias where the avalanche sweep stopped.

    A second sweep without impact ionisation, started from the plane of the avalanche
    sweep `back` steps below its last one, up to `beyond` times the last bias. Returns
    (its planes or None, the bias it starts at, seconds). The ionisation integral needs
    these planes to cross 1; DEVSIM's sweep has no impact ionisation either.
    """
    last = max(float(s.v.max()) for s in segments)
    names = ["sweep" if k == 0 else f"sweep{k}" for k in range(len(segments))]
    name, seg, k0 = names[0], segments[0], 0
    for n, s in zip(names, segments):
        early = np.nonzero(s.v <= last - back * vstep + 1e-9)[0]
        if len(early):
            name, seg, k0 = n, s, int(early.max())
    v_from, v_to = float(seg.v[k0]), min(vmax, beyond * last + 2 * vstep)
    text = charon_deck.deck(dev, "sweep", f"{name}.exo", "field.exo", v0=v_from, v1=v_to,
                            step=vstep, min_step=min_step, avalanche=False, index=k0 + 1,
                            currents="currents_field.dat", **common)  # fmt: skip
    _, seconds = run_stage("field", text)
    try:
        field = charon_field.Sweep("field.exo", "mesh.exo.map.npz")
    except (OSError, KeyError, ValueError) as exc:
        print(f"FIELD no planes ({exc})", flush=True)
        return None, np.inf, seconds
    field.v0 = seg.v0
    diff = float(np.abs(field.potential(0) - seg.potential(k0)).max())
    print(f"FIELD restart at {v_from:g} V ({name}.exo plane {k0}), to {v_to:g} V, reached "
          f"{field.v.max():g} V; first plane differs by {diff:.2e} V", flush=True)  # fmt: skip
    return field, v_from, seconds


def simulate(dev, mesh_npz, vmax, vstep, step_cm, scheme="cvfem", min_step=None,
             tau=charon_deck.SEED_TAU, quads=False):  # fmt: skip
    """Mesh file, the stages, then the post-processing. Returns the result."""
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
    v, i_well, i_sub, segments, rc, seconds["sweep"] = avalanche_sweep(
        dev, vmax, vstep, min_step, common)  # fmt: skip
    # The two contact currents are equal and opposite; the one of a heavily doped contact
    # shows isolated spikes (round-off in its evaluation), so the criteria take the smaller.
    i_min = np.minimum(np.abs(i_well), np.abs(i_sub))
    bv_cur, trend = bv_by_current(v, i_min)
    field, v_join = None, np.inf
    if v.max() < vmax - 1e-9:
        field, v_join, seconds["field"] = field_sweep(dev, segments, vmax, vstep, min_step, common)
    t1 = time.time()
    scan, files, seen = None, [], -np.inf
    for seg in segments + ([field] if field is not None else []):
        hi = np.inf if seg is field else v_join - 1e-9
        planes = [k for k in range(len(seg.v)) if seen + 1e-9 < seg.v[k] <= hi]
        if not planes:
            continue
        more = charon_field.scan_both(seg, step_cm, planes)
        scan = more if scan is None else {k: scan[k] + more[k] for k in scan}
        files += charon_field.save_potentials(
            seg, SAVE_EVERY_V, "potential_", v_lo=seen + 1e-9, v_hi=hi
        )
        seen = max(more["v"])
    bv_int = ionize.breakdown_voltage(scan["v"], scan["i_n"])
    bv_low = ionize.breakdown_voltage(scan["v"], scan["i_n_low_branch"])
    seconds["post"] = time.time() - t1
    seconds["total"] = time.time() - t0
    out = {
        "scheme": scheme, "tau_s": tau, "elements": "QUAD4" if quads else "TRI3",
        "sweep_exit_code": rc, "sweep_segments": len(segments), "nodes": counts,
        "v": v.tolist(), "i_well": i_well.tolist(), "i_sub": i_sub.tolist(),
        "i_min": i_min.tolist(),
        "last_converged_v": float(v.max()), "reached_vmax": bool(v.max() >= vmax - 1e-9),
        "bv_current_v": bv_cur, "current_trend": trend,
        "bv_threshold_v": bv_by_threshold(v, i_min), "i_threshold": I_THRESHOLD,
        "bv_integral_v": bv_int, "bv_integral_low_branch_v": bv_low,
        "integral": scan, "v0_volts": segments[0].v0, "potentials": files, "seconds": seconds,
    }  # fmt: skip
    print("RESULT", json.dumps({k: out[k] for k in (
        "last_converged_v", "reached_vmax", "bv_current_v", "bv_threshold_v", "bv_integral_v",
        "bv_integral_low_branch_v", "seconds")}), flush=True)  # fmt: skip
    return out


def main(argv):
    mode = argv[0]
    if mode == "case":
        with open(argv[1]) as params_file:
            p = json.load(params_file)
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
    with open(result, "w") as out_file:
        json.dump(out, out_file, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
