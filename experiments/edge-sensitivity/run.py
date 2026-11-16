# SPDX-License-Identifier: Apache-2.0
"""Run edge-sensitivity variants one at a time in the sandbox (16 GiB, the stable TCAD image).

    uv run --locked python experiments/edge-sensitivity/run.py WORKDIR DEVICE GID VARIANT...

WORKDIR is outside the repository (the sandbox refuses the repo). Each variant writes
WORKDIR/DEVICE/GID/<variant>/result.json, its log variant.log and pins.json beside them. A variant
whose result.json exists is skipped.

The sandbox imports the checkout's sources, so a run is pinned to them: run.py refuses a checkout
with uncommitted changes under the paths a run reads (PINNED_PATHS), and pins.json holds the
commit, the TCAD image, the plugin commit, the sha256 of variant.py, the 2D writer's
``generator_sha256`` (gf180tcad.tcad.__main__: the hash of every module and process file the
cross-section and the solve use) and the device's calibration file and values. The pins are taken
before and after the run and must agree.
"""

import hashlib
import subprocess
import sys
from pathlib import Path

from gf180tcad import io
from gf180tcad.tcad import calibration, calibration_file, generator_sha256, gplugins_commit

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

# The checkout paths a run reads; any uncommitted change under them is refused.
PINNED_PATHS = ("src", "data", "experiments/edge-sensitivity", "docker", "results/tcad")

# The entry point whose generator_sha256 pins the modules and process files a run imports.
WRITER = "gf180tcad.tcad.__main__"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True,
                          text=True).stdout  # fmt: skip


def pins(device: str) -> dict:
    """What a run of ``device`` uses, from the checkout as it is now (ValueError if it has
    uncommitted changes under PINNED_PATHS)."""
    dirty = _git("status", "--porcelain", "--", *PINNED_PATHS)
    if dirty:
        raise ValueError(f"uncommitted changes under {PINNED_PATHS}:\n{dirty}")
    cal = calibration_file(device)
    return {
        "commit": _git("rev-parse", "HEAD").strip(),
        "image": (REPO / "docker" / "TCAD_IMAGE").read_text(encoding="utf-8").strip(),
        "gplugins_commit": gplugins_commit(),
        "variant_py_sha256": hashlib.sha256((HERE / "variant.py").read_bytes()).hexdigest(),
        "generator": WRITER,
        "generator_sha256": generator_sha256(WRITER),
        "calibration_file_sha256": hashlib.sha256(cal.read_bytes()).hexdigest(),
        "calibration_values": calibration.read(cal, device),
    }


def main(argv: list[str]) -> int:
    work, device, gid, *variants = argv
    rc = 0
    for v in variants:
        out = Path(work).expanduser().resolve() / device / gid / v
        out.mkdir(parents=True, exist_ok=True)
        if (out / "result.json").is_file():
            print(f"{v}: done before", flush=True)
            continue
        before = pins(device)
        cmd = [
            str(REPO / "tools" / "sandbox-run"),
            "--mem",
            "16g",
            "--cpus",
            "1",
            "--image",
            before["image"],
            "--workdir",
            str(out),
            "--",
            "python3",
            "/work/src/experiments/edge-sensitivity/variant.py",
            device,
            gid,
            v,
            "/work/out/result.json",
        ]
        with (out / "variant.log").open("w", encoding="utf-8") as log:
            r = subprocess.run(cmd, check=False, stdout=log, stderr=subprocess.STDOUT)
        if pins(device) != before:
            (out / "result.json").unlink(missing_ok=True)
            print(f"{v}: the checkout changed during the run; result removed", flush=True)
            rc = rc or 1
            continue
        io.write_json(out / "pins.json", before)
        print(f"{v}: exit {r.returncode} ({out / 'variant.log'})", flush=True)
        rc = rc or r.returncode
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
