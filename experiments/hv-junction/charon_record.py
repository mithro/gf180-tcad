# SPDX-License-Identifier: Apache-2.0
"""Write a Charon cross-check record from the run directories of charon_batch.py.

    uv run --locked python experiments/hv-junction/charon_record.py WORKDIR OUT.json \
        DEVSIM_COMMIT:DEVSIM_RECORD NAME...

WORKDIR is the one given to charon_batch.py and NAME... the cases it ran.
DEVSIM_COMMIT:DEVSIM_RECORD names the committed DEVSIM record the cases are compared with,
as git names a file of a commit (for example HEAD:results/hv-junction/main.json).

The record holds the pins every run shared (the DEVSIM image, the Charon image and the
sha256 of the modules a sweep imports, record.SWEEP_FILES), the commits the runs were made
at, and the DEVSIM record's commit, path and sha256. Per case it holds the sha256 of the
parameters, the commit of the run and the sha256 of the Charon modules at that commit
(CHARON_FILES; they may differ between cases run at different commits), DEVSIM's breakdown
voltage, Charon's breakdown voltages by each criterion, the bias points with the smaller
contact current, and the ionisation integral and peak silicon field on Charon's potential.

It refuses a case without result.json or pins.json, runs whose shared pins differ, runs
made from a checkout with uncommitted changes, and a case that the DEVSIM record does not
hold with the same parameters.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import batch
import record as devsim_record

REPO = pathlib.Path(__file__).resolve().parents[2]
# The Charon modules of a run; their hashes are kept per case.
CHARON_FILES = ("charon_deck.py", "charon_field.py", "charon_mesh.py", "charon_run.py")
# The fields of charon_run.py's result.json that the record keeps.
KEEP = ("scheme", "tau_s", "elements", "nodes", "last_converged_v", "reached_vmax",
        "bv_current_v", "bv_threshold_v", "i_threshold", "bv_integral_v",
        "bv_integral_low_branch_v", "v", "i_min")  # fmt: skip
# The per-bias lists of its "integral" table that the record keeps.
KEEP_INTEGRAL = ("v", "i_n", "i_n_low_branch", "emax")


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True).stdout


def devsim_rows(spec: str) -> tuple[dict, dict]:
    """The cases of the committed DEVSIM record ``COMMIT:PATH`` and where they come from:
    the resolved commit, the path and the sha256 of the file at that commit."""
    commit, path = spec.split(":", 1)
    commit = _git("rev-parse", f"{commit}^{{commit}}").decode().strip()
    blob = _git("show", f"{commit}:{path}")
    source = {"commit": commit, "path": path, "sha256": hashlib.sha256(blob).hexdigest()}
    return json.loads(blob)["cases"], source


def record(work: pathlib.Path, names: list[str], devsim: dict, source: dict) -> dict:
    """The record of the cases ``names`` from their run directories under ``work``."""
    shared, rows, commits = None, {}, set()
    for name in names:
        d = work / batch.safe(name)
        try:
            res = json.loads((d / "result.json").read_text(encoding="utf-8"))
            pins = json.loads((d / "pins.json").read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SystemExit(f"{name}: not run ({exc.filename})") from None
        if pins["case"] != name:
            raise SystemExit(f"{name}: pins.json is another case's")
        if pins["dirty"]:
            raise SystemExit(f"{name}: run from a checkout with uncommitted changes")
        files = pins["files_sha256"]
        same = {"image": pins["image"], "charon_image": pins["charon_image"],
                "files_sha256": {f: files[f] for f in devsim_record.SWEEP_FILES}}  # fmt: skip
        if shared is None:
            shared = same
        elif same != shared:
            raise SystemExit(f"{name}: images or simulation files differ from the first case's")
        digest = hashlib.sha256(json.dumps(res["params"], sort_keys=True).encode()).hexdigest()
        if name not in devsim or devsim[name]["params_sha256"] != digest:
            raise SystemExit(f"{name}: the DEVSIM record has no case with these parameters")
        commits.add(pins["commit"])
        rows[name] = {
            "params_sha256": digest,
            "commit": pins["commit"],
            "charon_files_sha256": {f: files[f] for f in CHARON_FILES},
            "devsim_bv_v": devsim[name]["bv_v"],
            **{k: res[k] for k in KEEP},
            "integral": {k: res["integral"][k] for k in KEEP_INTEGRAL},
        }
    if not rows:
        raise SystemExit("no case named")
    shared["commits"] = sorted(commits)
    return {"schema": 2, "pins": shared, "devsim_record": source, "cases": rows}


def main(argv: list[str]) -> int:
    work, out = (pathlib.Path(a).expanduser() for a in argv[:2])
    devsim, source = devsim_rows(argv[2])
    rec = record(work, argv[3:], devsim, source)
    out.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(rec['cases'])} cases written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
