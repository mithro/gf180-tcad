# SPDX-License-Identifier: Apache-2.0
"""Run prediction cases on Charon: mesh dump in the DEVSIM image, then charon_run.py.

    uv run python experiments/hv-junction/charon_batch.py WORKDIR CASES.json NAME...

Each case runs in WORKDIR/<name>/ and is skipped when its result.json exists. The cases
run in parallel, one container at a time each; pins.json is written beside each result.
"""

from __future__ import annotations

import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor

import batch
import run as runner


def one(work, name, params, pins):
    out = work / batch.safe(name)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "result.json").is_file():
        return name, "done before"
    (out / "params.json").write_text(json.dumps(params, indent=1))
    rc = runner.run(out, "charon_mesh.py", ["dump", "params.json", "mesh.npz"])
    if rc == 0:
        rc = runner.run(out, "charon_run.py", ["case", "params.json", "mesh.npz", "result.json"],
                        charon=True, mem="16g")  # fmt: skip
    if not (out / "result.json").is_file():
        return name, f"FAILED exit {rc}"
    both = {"case": name, **pins, "charon_image": runner.image(charon=True)}
    (out / "pins.json").write_text(json.dumps(both, indent=1))
    return name, "done"


def main(argv):
    work = pathlib.Path(argv[0]).expanduser().resolve()
    cases = json.loads(pathlib.Path(argv[1]).read_text())
    pins = runner.pins(allow_dirty="--allow-dirty" in argv)
    names = [a for a in argv[2:] if not a.startswith("--")]
    work.mkdir(parents=True, exist_ok=True)
    with open(work / "batch.log", "a") as log, ThreadPoolExecutor(len(names)) as pool:
        for name, status in pool.map(lambda n: one(work, n, cases[n], pins), names):
            log.write(f"{name}: {status}\n")
            log.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
