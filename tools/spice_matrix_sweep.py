# SPDX-License-Identifier: Apache-2.0
"""One-off: run the whole Phase-1 SPICE matrix on ngspice and Xyce and summarise what happened.

Usage: uv run python tools/spice_matrix_sweep.py OUT_DIR [--jobs 8]

Both devices x every geometry x all corners at 25 C; ngspice runs every sweep (cv and ioff
included), Xyce idvg_lin, idvg_sat, idvd and ioff. Every simulator run goes through the sandbox
(``simulate`` / ``simulate_xyce``), at most ``--jobs`` at a time. Writes ``OUT_DIR/runs.jsonl``
(one record per run: status, warnings, error, seconds) and prints a summary: failures, runs in
which the post-run working-directory guard fired or a BSIM4 report file was read, and the
distinct warnings per engine.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from gf180tcad import sandbox
from gf180tcad.devices import CORNERS, DEVICES, SWEEPS, geometry_id
from gf180tcad.pdk import PdkInfo
from gf180tcad.spice.common import SpiceError
from gf180tcad.spice.ngspice import simulate
from gf180tcad.spice.xyce import simulate_xyce

XYCE_SWEEPS = ("idvg_lin", "idvg_sat", "idvd", "ioff")


def image_pdk(work: Path) -> PdkInfo:
    code = (
        "import dataclasses, json; from gf180tcad import pdk; info = pdk.locate(); "
        "pdk.check_against(info, '/work/src/docker/base/versions.json'); "
        "print(json.dumps({k: str(v) for k, v in dataclasses.asdict(info).items()}))"
    )
    work.mkdir(parents=True, exist_ok=True)
    fields = json.loads(sandbox.run(["python3", "-c", code], out_dir=work).stdout.splitlines()[-1])
    return PdkInfo(
        **{k: (v if k in ("variant", "open_pdks_commit") else Path(v)) for k, v in fields.items()}
    )


def cases():
    for device in DEVICES.values():
        for g in device.geometries:
            for corner in CORNERS:
                for sweep in SWEEPS:
                    yield "ngspice", device, g, corner, sweep
                    if sweep.name in XYCE_SWEEPS:
                        yield "xyce", device, g, corner, sweep


def run_one(out: Path, pdk: PdkInfo, engine, device, g, corner, sweep) -> dict:
    d = out / engine / device.name / geometry_id(g) / corner / sweep.name
    d.mkdir(parents=True)
    rec = {
        "engine": engine,
        "device": device.name,
        "geometry": geometry_id(g),
        "corner": corner,
        "sweep": sweep.name,
    }
    t0 = time.monotonic()
    try:
        fn = simulate if engine == "ngspice" else simulate_xyce
        res = fn(device, g, sweep, corner, 25.0, pdk, d)
        rec |= {"status": "ok", "warnings": list(res.warnings), "points": len(res["vg"])}
    except SpiceError as e:
        rec |= {"status": "error", "error": str(e).split("\n", 1)[0], "warnings": []}
    except Exception as e:  # noqa: BLE001 - record anything, the summary reports it
        rec |= {"status": "exception", "error": f"{type(e).__name__}: {e}", "warnings": []}
    rec["seconds"] = round(time.monotonic() - t0, 3)
    rec["files_left"] = sorted(p.name for p in d.iterdir())
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()
    out = args.out.resolve()
    pdk = image_pdk(out / "pdk")
    todo = list(cases())
    n = len(todo)
    print(f"{n} runs, {args.jobs} concurrent", flush=True)
    t0 = time.monotonic()
    recs = []
    with ThreadPoolExecutor(args.jobs) as pool, (out / "runs.jsonl").open("w") as log:
        futs = [pool.submit(run_one, out, pdk, *c) for c in todo]
        for i, f in enumerate(as_completed(futs), 1):
            rec = f.result()
            recs.append(rec)
            log.write(json.dumps(rec, sort_keys=True) + "\n")
            log.flush()
            el = time.monotonic() - t0
            eta = el / i * (n - i)
            print(
                f"[{i}/{n}] {el:.0f}s elapsed, ETA {eta:.0f}s: {rec['engine']} "
                f"{rec['device']} {rec['geometry']} {rec['corner']} {rec['sweep']} "
                f"{rec['status']} {rec['seconds']}s",
                flush=True,
            )
    wall = time.monotonic() - t0
    summarise(recs, wall)
    return 0


def summarise(recs: list[dict], wall: float) -> None:
    print(f"\n== summary: {len(recs)} runs in {wall:.1f} s wall")
    by = collections.Counter((r["engine"], r["status"]) for r in recs)
    for k, v in sorted(by.items()):
        print(f"  {k[0]:8s} {k[1]:9s} {v}")
    for r in recs:
        if r["status"] != "ok":
            print(
                f"  FAIL {r['engine']} {r['device']} {r['geometry']} {r['corner']} "
                f"{r['sweep']}: {r['error']}"
            )
    guard = [r for r in recs if "unexpected files" in r.get("error", "")]
    reports = [r for r in recs if any(w.startswith("bsim4") for w in r["warnings"])]
    print(f"  post-run guard fired: {len(guard)}; BSIM4 report files read: {len(reports)}")
    extra = [
        r
        for r in recs
        if r["status"] == "ok"
        and set(r["files_left"])
        - {"ngspice.cir", "ngspice.log", "out.raw", "xyce.cir", "xyce.log", "out.csv"}
    ]
    print(f"  runs leaving other files: {len(extra)}")
    for engine in ("ngspice", "xyce"):
        w = collections.Counter(
            _shape(x) for r in recs if r["engine"] == engine for x in r["warnings"]
        )
        print(f"  {engine} distinct warnings ({sum(w.values())} total):")
        for text, c in w.most_common():
            print(f"    {c:5d}  {text}")
    secs = collections.defaultdict(list)
    for r in recs:
        secs[r["engine"]].append(r["seconds"])
    for e, s in secs.items():
        print(
            f"  {e} per-run seconds: min {min(s):.2f} median {sorted(s)[len(s) // 2]:.2f} "
            f"max {max(s):.2f}"
        )


def _shape(w: str) -> str:
    """Warning text with the model/bin name kept but line numbers dropped, for counting."""
    return re.sub(r"at or near line \d+", "at or near line N", w)


if __name__ == "__main__":
    sys.exit(main())
