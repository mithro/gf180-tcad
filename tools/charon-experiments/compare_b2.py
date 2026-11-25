"""Compare the C-V of the B2 runs: lifetime independence, tolerance noise and DEVSIM.

usage: python compare_b2.py B2DIR
Reads every B2DIR/*/b2an_*.json (written by b2an.py) and prints, per pair, the largest relative
difference of C over the common grid points and the bias where it occurs.
"""
import json
import sys
from pathlib import Path

import numpy as np

runs = {}
for p in sorted(Path(sys.argv[1]).glob("*/b2an_*.json")):
    d = json.loads(p.read_text())
    runs[p.parent.name] = d


def c_of(name):
    d = runs[name]
    return np.array(d["c_ff_um2"]), d


def pair(a, b):
    ca, da = c_of(a)
    cb, db = c_of(b)
    n = min(len(ca), len(cb))
    rel = np.abs(ca[:n] - cb[:n]) / np.abs(cb[:n])
    k = int(np.argmax(rel))
    return float(rel[k]), n, k


out = {}
names = sorted(runs)
for a in names:
    d = runs[a]
    print(f"{a}: points {len(d['c_ff_um2'])}, max |rel| vs DEVSIM {d['max_abs_rel_vs_devsim']:.3e}"
          f" at vg {d['argmax_vg']}, max|np/ni2-1| A {d.get('max_abs_np_over_ni2_minus_1_A')}"
          f" B {d.get('max_abs_np_over_ni2_minus_1_B')}")
for i, a in enumerate(names):
    for b in names[i + 1:]:
        if runs[a]["device"] != runs[b]["device"]:
            continue
        rel, n, k = pair(a, b)
        print(f"  {a} vs {b}: max rel diff {rel:.3e} over {n} points (at index {k})")
        out[f"{a}|{b}"] = {"max_rel": rel, "points": n, "index": k}
json.dump(out, open(Path(sys.argv[1]) / "compare_b2.json", "w"), indent=1)
