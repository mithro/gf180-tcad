# SPDX-License-Identifier: Apache-2.0
"""Run edge-sensitivity variants one at a time in the sandbox (16 GiB, the stable TCAD image).

    uv run --locked python experiments/edge-sensitivity/run.py WORKDIR DEVICE GID VARIANT...

WORKDIR is outside the repository (the sandbox refuses the repo); each variant writes
WORKDIR/<variant>/result.json and its log WORKDIR/<variant>/variant.log. A variant whose
result.json exists is skipped.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    work, device, gid, *variants = argv
    image = (REPO / "docker" / "TCAD_IMAGE").read_text(encoding="utf-8").strip()
    rc = 0
    for v in variants:
        out = Path(work).expanduser().resolve() / device / gid / v
        out.mkdir(parents=True, exist_ok=True)
        if (out / "result.json").is_file():
            print(f"{v}: done before", flush=True)
            continue
        cmd = [
            str(REPO / "tools" / "sandbox-run"),
            "--mem",
            "16g",
            "--cpus",
            "1",
            "--image",
            image,
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
        print(f"{v}: exit {r.returncode} ({out / 'variant.log'})", flush=True)
        rc = rc or r.returncode
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
