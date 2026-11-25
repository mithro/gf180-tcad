# SPDX-License-Identifier: Apache-2.0
"""Run many sweeps in parallel, one container each.

    uv run python experiments/hv-junction/batch.py WORKDIR CASES.json [--jobs N] [--mem 8g]

CASES.json maps a case name to a parameter dictionary (see structure.py and sweep.py).
Each case runs in WORKDIR/<name>/ and is skipped when its result.json exists. Progress
lines go to WORKDIR/batch.log: one line per case finished, with the count and an ETA.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = pathlib.Path(__file__).resolve().parent


def one(work, name, params, mem):
    out = work / name
    out.mkdir(parents=True, exist_ok=True)
    if (out / "result.json").is_file():
        return name, "done before"
    (out / "params.json").write_text(json.dumps(params, indent=1))
    r = subprocess.run([sys.executable, str(HERE / "run.py"), "--mem", mem, str(out),
                        "sweep.py", "params.json", "result.json"], check=False)  # fmt: skip
    if not (out / "result.json").is_file():
        return name, f"FAILED exit {r.returncode}"
    res = json.loads((out / "result.json").read_text())
    return name, f"bv {res['bv_v']} reached {res['reached_v']:.1f} in {res['seconds']:.0f}s"


def main(argv):
    work = pathlib.Path(argv[0]).expanduser().resolve()
    cases = json.loads(pathlib.Path(argv[1]).read_text())
    jobs = int(argv[argv.index("--jobs") + 1]) if "--jobs" in argv else 40
    mem = argv[argv.index("--mem") + 1] if "--mem" in argv else "8g"
    work.mkdir(parents=True, exist_ok=True)
    t0, done = time.time(), 0
    with open(work / "batch.log", "a") as log, ThreadPoolExecutor(jobs) as pool:
        futs = [pool.submit(one, work, n, p, mem) for n, p in cases.items()]
        for f in as_completed(futs):
            name, status = f.result()
            done += 1
            el = time.time() - t0
            eta = el / done * (len(futs) - done)
            clock = time.strftime("%H:%M", time.localtime(time.time() + eta))
            log.write(f"{done}/{len(futs)} {name}: {status} | elapsed {el / 60:.1f} min, "
                      f"ETA {eta / 60:.1f} min ({clock})\n")  # fmt: skip
            log.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
