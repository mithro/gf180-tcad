# SPDX-License-Identifier: Apache-2.0
"""Write the Charon experiment records from run.py's work directory.

    uv run --locked python experiments/charon-backend/record.py WORKDIR results/charon-experiments

Every step of run.py must have run with the same pins (the commit, the Charon image, the plugin
commit and the scripts); each record holds them once. The records:

- ``cv.json``: the C-V runs (``cv-*`` steps): their settings, the gate biases, Charon's and
  DEVSIM's C per area (fF/um^2) and the per-state checks of b2an.py;
- ``hard-range.json``: the solver variants through the onset of inversion (b2h.py), the solves
  from the inversion side (b2d.py) and the nonlinear-Poisson check (b2nlp.py);
- ``probes.json``: the nodal doping (b5.py), the linear solvers (b3.py), the harmonic-balance
  columns (b4.py) and the TRI3 meshes (b1.py, b1an.py);
- ``harmonic-balance.json``: the harmonic-balance columns on an oxide-only parallel plate
  (b4pp.py) and on a metal-gate MOS capacitor (b4mg.py), from a work directory of their own.
"""

import json
import sys
from pathlib import Path

from gf180tcad import io

# The fields of b2an.py's result that cv.json keeps.
CV_KEEP = (
    "device", "params", "n", "vg", "c_devsim", "c_ff_um2", "x_um", "boundary_nodes", "layers",
    "contacts", "dv_fb_v", "polarity", "strip_width_um", "rel_vs_devsim", "max_abs_rel_vs_devsim", "argmax_vg",
    "align_A", "align_B", "extra_states_A", "extra_states_B", "extra_max_dev_A",
    "extra_max_dev_B", "strip_y_asym_A", "strip_y_asym_B", "oxide_flux_spread_A",
    "oxide_flux_spread_B", "poly_vs_gate_A", "poly_vs_gate_B", "body_vs_gate_A",
    "body_vs_gate_B", "max_abs_np_over_ni2_minus_1_A", "max_abs_np_over_ni2_minus_1_B",
    "np_dev_per_state_A", "np_dev_per_state_B",
)  # fmt: skip


def _json(path: Path) -> dict:
    return json.loads(path.read_bytes())


def _pins(work: Path) -> dict:
    pins = {p.parent.name: _json(p) for p in sorted(work.glob("*/pins.json"))}
    if not pins:
        raise ValueError(f"{work}: no step ran")
    first = next(iter(pins.values()))
    for step, p in pins.items():
        if p != first:
            diff = sorted(k for k in {*p, *first} if p.get(k) != first.get(k))
            raise ValueError(f"{step} ran with other pins: {diff}")
    for step in pins:
        done = _json(work / step / "done.json")
        if done["exit"] != 0:
            raise ValueError(f"{step} exited {done['exit']}")
    return first


def cv(work: Path) -> dict:
    runs = {}
    for step in sorted(p.name for p in work.iterdir() if p.name.startswith("cv-")):
        d = work / step
        an = _json(d / "b2an_result.json")
        (raw_path,) = sorted(d.glob("b2_*.json"))
        raw = _json(raw_path)
        cmd = _json(d / "done.json")["command"]
        words = cmd.split()
        settings = dict(kv.split("=", 1) for kv in words[1:words.index("python3")])
        rec = {k: an[k] for k in CV_KEEP}
        rec["settings"] = settings
        rec["iterations_A"] = raw["statsA"]["iters"]
        rec["iterations_B"] = raw["statsB"]["iters"]
        runs[step] = rec
    return {"runs": runs}


def _reached(v: dict) -> dict:
    """A b2h.py variant in brief: did the equilibrium and the sweep converge, the last converged
    bias (V; the sweep starts at 0 V with fixed steps) and the iterations per step."""
    sweep = v.get("sweep") or {}
    its = sweep.get("iters", [])
    return {"settings": v["settings"], "step_v": v["step"], "end_v": v["vend"],
            "equilibrium_converged": v["eq_ok"], "sweep_converged": bool(v.get("sweep_ok")),
            # LOCA step 0 is the solve at the start bias, 0 V; a sweep that converged throughout
            # ends at its end bias (its last step is the zero-length one onto the bound)
            "last_converged_v": (v["vend"] if v.get("sweep_ok")
                                 else round((len(its) - 1) * v["step"], 12) if its else None),
            "iterations": its, "failed_at": sweep.get("failed_at", [])}  # fmt: skip


def hard_range(work: Path) -> dict:
    variants = _json(work / "b2-hard-range" / "b2h.json")
    return {
        "variants": {name: _reached(v) for name, v in variants.items()},
        "inversion_side": _json(work / "b2-inversion-side" / "b2d.json"),
        "nlp": _json(work / "b2-nlp" / "b2nlp.json"),
    }


def probes(work: Path) -> dict:
    b4 = {p.stem: _json(p) for p in sorted((work / "b4-harmonic-balance").glob("b4_*.json"))}
    for v in b4.values():
        for side in ("accumulation", "depletion"):
            v[side].pop("tail", None)
    return {
        "doping": _json(work / "b5-doping" / "b5.json"),
        "solvers": _json(work / "b3-solvers" / "b3.json"),
        "harmonic_balance": b4,
        "tri3": {**_json(work / "b1-tri3" / "b1.json"), **_json(work / "b1-tri3" / "b1an.json")},
    }


def harmonic_balance(work: Path) -> dict:
    """The analytic checks of the harmonic-balance columns (b4pp.py, b4mg.py)."""
    pp = _json(work / "b4-parallel-plate" / "b4pp.json")
    mg = _json(work / "b4-metal-gate" / "b4mg.json")
    for rec in (*pp["runs"].values(), *mg.values()):
        rec.pop("tail", None)
        rec.pop("rows", None)
    return {"parallel_plate": pp, "metal_gate": mg}


#: record name -> (the steps it reads, its builder). A work directory holds the steps of the
#: records it is used for; run.py runs the harmonic-balance checks in a work directory of their
#: own, so each record's steps share one set of pins.
RECORDS = {
    "cv": ("cv-", cv),
    "hard-range": ("b2-", hard_range),
    "probes": ("b5-doping", probes),
    "harmonic-balance": ("b4-parallel-plate", harmonic_balance),
}


def main(argv: list[str]) -> int:
    work, out = (Path(a).expanduser().resolve() for a in argv)
    pins = _pins(work)
    out.mkdir(parents=True, exist_ok=True)
    steps = [p.name for p in work.iterdir() if p.is_dir()]
    for name, (prefix, build) in RECORDS.items():
        if not any(s.startswith(prefix) for s in steps):
            continue
        io.write_json(out / f"{name}.json", {"schema": 1, **pins, **build(work)})
        print(f"wrote {out / name}.json", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
