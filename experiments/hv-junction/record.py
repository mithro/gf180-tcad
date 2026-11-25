# SPDX-License-Identifier: Apache-2.0
"""Write one record from the run directories of a batch.

    uv run python experiments/hv-junction/record.py WORKDIR CASES.json OUT.json

The record holds the pins every run shared (commit, image, file hashes) and, per case,
its parameters' sha256, the breakdown voltage, the bias points with the ionisation
integral, the peak silicon and oxide fields, the well current and the probe (floating
ring) potentials. It refuses runs whose pins differ, runs made from a checkout with
uncommitted changes, and a missing case.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import batch

KEEP = ("v", "i_n", "emax", "eox_max", "i_well", "probes", "where_um")


def main(argv):
    work, cases_path, out = (pathlib.Path(a).expanduser() for a in argv[:3])
    cases = json.loads(cases_path.read_text())
    shared, rows = None, {}
    for name, params in cases.items():
        d = work / batch.safe(name)
        try:
            res = json.loads((d / "result.json").read_text())
            pins = json.loads((d / "pins.json").read_text())
        except FileNotFoundError as exc:
            raise SystemExit(f"{name}: not run ({exc.filename})") from None
        pins.pop("case")
        if pins["dirty"]:
            raise SystemExit(f"{name}: run from a checkout with uncommitted changes")
        if shared is None:
            shared = pins
        elif pins != shared:
            raise SystemExit(f"{name}: pins differ from the first case's")
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
    record = {"schema": 1, "pins": shared, "cases": rows}
    out.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
    print(f"{len(rows)} cases written to {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
