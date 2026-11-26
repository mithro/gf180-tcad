# SPDX-License-Identifier: Apache-2.0
"""Write the Charon cross-check record from the run directories of charon_batch.py.

    uv run --locked python experiments/hv-junction/charon_record.py WORKDIR CASES.json OUT.json NAME...

WORKDIR and CASES.json are those given to charon_batch.py, NAME... the cases it ran. The
record holds the pins every run shared (commit, DEVSIM image, Charon image, file hashes)
and, per case, the sha256 of its parameters, Charon's breakdown voltages by each
criterion, the bias points with the smaller contact current, and the ionisation integral
and peak silicon field on Charon's potential. It refuses a case without result.json or
pins.json, runs whose pins differ, runs made from a checkout with uncommitted changes,
and a run whose parameters are not those of CASES.json.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import batch

# The fields of charon_run.py's result.json that the record keeps.
KEEP = ("scheme", "tau_s", "elements", "nodes", "last_converged_v", "reached_vmax",
        "bv_current_v", "bv_threshold_v", "i_threshold", "bv_integral_v",
        "bv_integral_low_branch_v", "v", "i_min")  # fmt: skip
# The per-bias lists of its "integral" table that the record keeps.
KEEP_INTEGRAL = ("v", "i_n", "i_n_low_branch", "emax")
PIN_KEYS = ("charon_image", "commit", "dirty", "files_sha256", "image")


def record(work: pathlib.Path, cases: dict, names: list[str]) -> dict:
    """The record of the cases ``names`` from their run directories under ``work``."""
    shared, rows = None, {}
    for name in names:
        d = work / batch.safe(name)
        try:
            res = json.loads((d / "result.json").read_text(encoding="utf-8"))
            pins = json.loads((d / "pins.json").read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SystemExit(f"{name}: not run ({exc.filename})") from None
        if pins.pop("case") != name:
            raise SystemExit(f"{name}: pins.json is another case's")
        if sorted(pins) != sorted(PIN_KEYS):
            raise SystemExit(f"{name}: pins.json holds {sorted(pins)}, not {sorted(PIN_KEYS)}")
        if pins["dirty"]:
            raise SystemExit(f"{name}: run from a checkout with uncommitted changes")
        if shared is None:
            shared = pins
        elif pins != shared:
            raise SystemExit(f"{name}: pins differ from the first case's")
        if res["params"] != cases[name]:
            raise SystemExit(f"{name}: the run's parameters are not those of the cases file")
        digest = hashlib.sha256(json.dumps(cases[name], sort_keys=True).encode()).hexdigest()
        rows[name] = {
            "params_sha256": digest,
            **{k: res[k] for k in KEEP},
            "integral": {k: res["integral"][k] for k in KEEP_INTEGRAL},
        }
    if not rows:
        raise SystemExit("no case named")
    return {"schema": 1, "pins": shared, "cases": rows}


def main(argv: list[str]) -> int:
    work, cases_path, out = (pathlib.Path(a).expanduser() for a in argv[:3])
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    rec = record(work, cases, argv[3:])
    out.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(rec['cases'])} cases written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
