# SPDX-License-Identifier: Apache-2.0
"""Write one record from the run directories of a batch.

    uv run python experiments/hv-junction/record.py WORKDIR CASES.json OUT.json [--allow-missing]

The record holds the pins every run shared (the image, the sha256 of the modules a sweep
imports, and the commits the runs were made at) and, per case,
its parameters' sha256, the breakdown voltage, the bias points with the ionisation
integral, the peak silicon and oxide fields, the well current and the probe (floating
ring) potentials. It refuses runs whose pins differ, runs made from a checkout with
uncommitted changes, and a missing case (with --allow-missing a case whose run left no
result is listed under "not_converged" instead).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import batch

# the modules a sweep imports; their hashes pin what a case computed
SWEEP_FILES = ("dd.py", "fieldline.py", "ionize.py", "structure.py", "sweep.py")
KEEP = ("v", "i_n", "emax", "eox_max", "i_well", "probes", "where_um")


def main(argv):
    work, cases_path, out = (pathlib.Path(a).expanduser() for a in argv[:3])
    cases = json.loads(cases_path.read_text())
    shared, rows, missing, commits = None, {}, [], set()
    for name, params in cases.items():
        d = work / batch.safe(name)
        try:
            res = json.loads((d / "result.json").read_text())
            pins = json.loads((d / "pins.json").read_text())
        except FileNotFoundError as exc:
            if "--allow-missing" not in argv:
                raise SystemExit(f"{name}: not run ({exc.filename})") from None
            missing.append(name)
            continue
        pins.pop("case")
        if pins["dirty"]:
            raise SystemExit(f"{name}: run from a checkout with uncommitted changes")
        # A batch that is restarted after an unrelated commit has a new commit and may see
        # new files in the folder. What must be equal is what a sweep runs: the image and
        # the modules sweep.py imports. Every commit a case ran at is kept.
        commits.add(pins["commit"])
        pins = {"image": pins["image"],
                "files_sha256": {f: pins["files_sha256"][f] for f in SWEEP_FILES}}  # fmt: skip
        if shared is None:
            shared = pins
        elif pins != shared:
            raise SystemExit(f"{name}: image or simulation files differ from the first case's")
        if res["params"] != params:
            raise SystemExit(f"{name}: the run's parameters are not those of {cases_path}")
        digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
        rows[name] = {
            "params_sha256": digest,
            "bv_v": res["bv_v"],
            "reached_v": res["reached_v"],
            "nodes": res["nodes"],
            **{k: res[k] for k in KEEP},
        }
    shared["commit"] = min(commits) if len(commits) == 1 else None
    shared["commits"] = sorted(commits)
    record = {"schema": 2, "pins": shared, "cases": rows, "not_converged": missing}
    out.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
    print(f"{len(rows)} cases written to {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
