# SPDX-License-Identifier: Apache-2.0
"""Run many sweeps in parallel, one sandbox container each.

    uv run python experiments/hv-junction/batch.py WORKDIR CASES.json [--jobs N] [--allow-dirty]

CASES.json maps a case name to a parameter dictionary (see structure.py and sweep.py).
Each case runs in WORKDIR/<name>/ and is skipped when its result.json exists. A finished
case gets pins.json (see run.pins); the batch refuses a checkout with uncommitted changes
unless --allow-dirty, which is recorded in the pins. Progress goes to WORKDIR/batch.log:
one line per finished case with the count and an ETA.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import run as runner


def safe(name):
    """A directory name for a case name."""
    return name.replace("|", "__").replace("@", "-at-")


def one(work, name, params, pins):
    out = work / safe(name)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "result.json").is_file():
        return name, "done before"
    (out / "params.json").write_text(json.dumps(params, indent=1))
    rc = runner.run(out, "sweep.py", ["params.json", "result.json"])
    if not (out / "result.json").is_file():
        return name, f"FAILED exit {rc}"
    (out / "pins.json").write_text(json.dumps({"case": name, **pins}, indent=1))
    res = json.loads((out / "result.json").read_text())
    bv = "none" if res["bv_v"] is None else f"{res['bv_v']:.1f}"
    return name, f"bv {bv} reached {res['reached_v']:.1f} in {res['seconds']:.0f}s"


def main(argv):
    work = pathlib.Path(argv[0]).expanduser().resolve()
    cases = json.loads(pathlib.Path(argv[1]).read_text())
    jobs = int(argv[argv.index("--jobs") + 1]) if "--jobs" in argv else 40
    pins = runner.pins(allow_dirty="--allow-dirty" in argv)
    work.mkdir(parents=True, exist_ok=True)
    t0, done = time.time(), 0
    with open(work / "batch.log", "a") as log, ThreadPoolExecutor(jobs) as pool:
        futs = [pool.submit(one, work, n, p, pins) for n, p in cases.items()]
        for f in as_completed(futs):
            name, status = f.result()
            done += 1
            el = time.time() - t0
            eta = el / done * (len(futs) - done)
            clock = time.strftime("%H:%M", time.localtime(time.time() + eta))
            log.write(f"{done}/{len(futs)} {name}: {status} | elapsed {el / 60:.1f} min, "
                      f"ETA {eta / 60:.1f} min ({clock})\n")  # fmt: skip
            log.flush()
        if runner.pins(allow_dirty=True) != {**pins, "dirty": runner.pins(allow_dirty=True)["dirty"]}:
            log.write("WARNING: the checkout changed during the batch\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
