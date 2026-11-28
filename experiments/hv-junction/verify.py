# SPDX-License-Identifier: Apache-2.0
"""Rerun recorded cases and compare them with the records.

    uv run --locked python experiments/hv-junction/verify.py WORKDIR CASE [CASE ...]
    uv run --locked python experiments/hv-junction/verify.py WORKDIR --sample N [--seed S]
    options: [--jobs N] [--mem 8g] [--tol VOLTS] [--allow-dirty]

A case is named as in the records, for example 'NT20|BL|edge'. Each named case is rebuilt from
predict.py, checked to be the case the records hold (same parameter hash), run in the sandbox
as batch.py runs it, and compared with its row in the last prediction record that holds it:

- the breakdown voltage, within --tol (default 0.05 V);
- the bias points and the node count, which are equal when the sweep code is the code the
  record's run used.

One line per case goes to standard output and to WORKDIR/verify.log. The exit status is 0
when every case agrees in breakdown voltage, 1 when one differs or fails, and 2 when a named
case is not in the records with its present parameters. --sample picks N cases at random
from those that have a breakdown value, hold no floating ring and run in double precision:
the cases that take minutes, not hours.

WORKDIR must be outside the repository (the sandbox refuses the repository). A case whose
result.json exists there is not run again, so remove WORKDIR to force a rerun.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

import batch
import predict

REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = REPO / "results" / "hv-junction"


def record_order() -> tuple[str, ...]:
    """The prediction records, earliest first: the order the page and the tests use."""
    sys.path.insert(0, str(REPO / "src"))
    from gf180tcad import hvjunction_figures

    return tuple(hvjunction_figures.PREDICTION_RECORDS)


def recorded(root: pathlib.Path = ROOT) -> tuple[dict, dict]:
    """(cases predict.py gives now, each one's row in the last record that holds it with the
    present parameters)."""
    now = {**predict.main_cases(), **predict.family_cases()}
    rows: dict = {}
    for name in record_order():
        path = root / f"{name}.json"
        if path.is_file():
            for case, row in json.loads(path.read_text("utf-8"))["cases"].items():
                rows[case] = {**row, "record": name}
    keep = {
        c: r for c, r in rows.items() if c in now and r["params_sha256"] == predict.digest(now[c])
    }
    return now, keep


def compare(want: dict, got: dict, tol: float) -> tuple[bool, str]:
    """(agrees, description) for a recorded row and a rerun's result."""
    same_path = got["v"] == want["v"] and got["nodes"] == want["nodes"]
    path = "bias points equal" if same_path else "bias points differ"
    a, b = want["bv_v"], got["bv_v"]
    if a is None or b is None:
        ok = a is None and b is None and abs(got["reached_v"] - want["reached_v"]) <= tol
        return ok, (
            f"no breakdown value; reached {got['reached_v']:.2f} V, "
            f"record {want['reached_v']:.2f} V; {path}"
        )
    return abs(
        a - b
    ) <= tol, f"rerun {b:.4f} V, record {a:.4f} V, difference {b - a:+.4f} V; {path}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Rerun recorded cases and compare them with the records."
    )
    ap.add_argument("workdir")
    ap.add_argument("cases", nargs="*")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--mem", default="8g")
    ap.add_argument("--tol", type=float, default=0.05)
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    now, rows = recorded()
    names = list(args.cases)
    if args.sample:
        struct = predict.structures()
        quick = sorted(
            c
            for c, r in rows.items()
            if r["bv_v"] is not None
            and not now[c].get("extended")
            and not struct[c.split("|")[0].split("@")[0]]["rings"]
        )
        names += random.Random(args.seed).sample(quick, min(args.sample, len(quick)))
    if not names:
        ap.error("name at least one case or give --sample N")
    missing = [n for n in names if n not in rows]
    if missing:
        for n in missing:
            why = (
                "is not a case of predict.py"
                if n not in now
                else "has no row with its present parameters"
            )
            print(f"{n}: {why}")
        return 2

    work = pathlib.Path(args.workdir).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    (work / "cases.json").write_text(json.dumps({n: now[n] for n in names}, indent=1))
    flags = ["--jobs", str(args.jobs), "--mem", args.mem] + (
        ["--allow-dirty"] if args.allow_dirty else []
    )
    batch.main([str(work), str(work / "cases.json"), *flags])

    bad = 0
    with open(work / "verify.log", "a") as log:
        for n in names:
            result = work / batch.safe(n) / "result.json"
            if result.is_file():
                ok, text = compare(rows[n], json.loads(result.read_text()), args.tol)
            else:
                ok, text = False, f"the rerun failed; see {result.parent / 'run.log'}"
            bad += not ok
            line = f"{'ok      ' if ok else 'MISMATCH'} {n} ({rows[n]['record']}): {text}"
            print(line)
            log.write(line + "\n")
        summary = f"{len(names) - bad} of {len(names)} cases agree within {args.tol} V"
        print(summary)
        log.write(summary + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
