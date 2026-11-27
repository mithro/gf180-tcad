# SPDX-License-Identifier: Apache-2.0
"""Run levels of the 2D mesh-convergence check at the fitted poly length bias, one at a time.

    uv run --locked python experiments/meshconv-fitted/run.py WORKDIR DEVICE LEVEL...

Each level runs level.py in the sandbox (16 GiB, one CPU, the stable TCAD image) and writes
WORKDIR/DEVICE/level<i>/level.json, its log level.log and pins.json beside them. A level whose
level.json exists is skipped. A level that was cut off (for example killed at its memory limit)
resumes at its last saved QS point when the same command runs again.

The sandbox imports the checkout's sources, so a run is pinned to them: run.py refuses a checkout
with uncommitted changes under the paths a run reads (PINNED_PATHS). pins.json holds the commit,
the TCAD image, the plugin commit, the sha256 of level.py, the 2D writer's ``generator_sha256``
(gf180tcad.tcad.__main__), the device's calibration file and values and the sha256 of its fit
file. The pins are taken before and after the run and must agree.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from gf180tcad import io
from gf180tcad.tcad import calibration, calibration_file, edgefit, generator_sha256, gplugins_commit

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

# The checkout paths a run reads; any uncommitted change under them is refused.
PINNED_PATHS = ("src", "data", "experiments/meshconv-fitted", "docker", "results/tcad")

# The entry point whose generator_sha256 pins the modules and process files a run imports.
WRITER = "gf180tcad.tcad.__main__"

# The memory of each level job (the 2D job limit, gf180tcad.tcad.__main__.JOB_MEM_2D).
MEM = "16g"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True,
                          text=True).stdout  # fmt: skip


def pins(device: str) -> dict:
    """What a run of ``device`` uses, from the checkout as it is now (ValueError if it has
    uncommitted changes under PINNED_PATHS, or no committed fit)."""
    dirty = _git("status", "--porcelain", "--", *PINNED_PATHS)
    if dirty:
        raise ValueError(f"uncommitted changes under {PINNED_PATHS}:\n{dirty}")
    fit_sha256 = edgefit.sha256(device)
    if fit_sha256 is None:
        raise ValueError(f"{device}: no committed fit in {edgefit.TREE_ROOT}")
    cal = calibration_file(device)
    return {
        "commit": _git("rev-parse", "HEAD").strip(),
        "image": (REPO / "docker" / "TCAD_IMAGE").read_text(encoding="utf-8").strip(),
        "gplugins_commit": gplugins_commit(),
        "level_py_sha256": hashlib.sha256((HERE / "level.py").read_bytes()).hexdigest(),
        "generator": WRITER,
        "generator_sha256": generator_sha256(WRITER),
        "calibration_file_sha256": hashlib.sha256(cal.read_bytes()).hexdigest(),
        "calibration_values": calibration.read(cal, device),
        "edge_fit_sha256": fit_sha256,
    }


def main(argv: list[str]) -> int:
    work, device, *levels = argv
    rc = 0
    for level in levels:
        out = Path(work).expanduser().resolve() / device / f"level{int(level)}"
        out.mkdir(parents=True, exist_ok=True)
        if (out / "level.json").is_file():
            print(f"level{level}: done before", flush=True)
            continue
        before = pins(device)
        if (out / "pins.json").is_file() and json.loads((out / "pins.json").read_bytes()) != before:
            raise SystemExit(f"{out}: a cut-off run with other pins; remove the directory")
        io.write_json(out / "pins.json", before)
        cmd = [
            str(REPO / "tools" / "sandbox-run"),
            "--mem", MEM, "--cpus", "1", "--image", before["image"], "--workdir", str(out),
            "--",
            "python3", "/work/src/experiments/meshconv-fitted/level.py", device, str(int(level)),
            "/work/out",
        ]  # fmt: skip
        with (out / "level.log").open("a", encoding="utf-8") as log:
            r = subprocess.run(cmd, check=False, stdout=log, stderr=subprocess.STDOUT)
        if pins(device) != before:
            (out / "level.json").unlink(missing_ok=True)
            print(f"level{level}: the checkout changed during the run; result removed", flush=True)
            rc = rc or 1
            continue
        print(f"level{level}: exit {r.returncode} ({out / 'level.log'})", flush=True)
        rc = rc or r.returncode
        if r.returncode:
            break  # the next level waits until this one resumes and finishes
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
