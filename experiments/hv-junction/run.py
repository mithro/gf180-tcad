"""Run a simulation script of this folder inside a gf180-tcad container image.

    uv run python docs/high-voltage/sim/run.py [--charon] [--mem 16g] [--cpus 1] OUTDIR SCRIPT [ARGS...]

The folder is mounted read-only at /sim and OUTDIR read-write at /out (the working
directory). No network. Output goes to OUTDIR/run.log. Images are the ones gf180-tcad
pins (docker/TCAD_DEV_IMAGE and docker/CHARON_IMAGE of mithro/gf180-tcad at 4e14465).
"""

import os
import pathlib
import subprocess
import sys

DEVSIM = "ghcr.io/mithro/gf180-tcad-tcad-dev@sha256:fe34752893b8078bb9053875fd43d4b45b75ca757d75150b2dca4b9ada9c0c44"
CHARON = "ghcr.io/mithro/gf180-tcad-charon@sha256:b2b981c4606c8b65113add4824c1c449d46d5a4525ad8323d7f2aafa5a7ee4af"


def main(argv):
    image, mem, cpus = DEVSIM, "16g", "1"
    while argv and argv[0].startswith("--"):
        opt = argv.pop(0)
        if opt == "--charon":
            image = CHARON
        elif opt == "--mem":
            mem = argv.pop(0)
        elif opt == "--cpus":
            cpus = argv.pop(0)
        else:
            sys.exit(f"unknown option {opt}")
    out = pathlib.Path(argv.pop(0)).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sim = pathlib.Path(__file__).resolve().parent
    cmd = [
        "docker", "run", "--rm", "--network", "none",
        "-u", f"{os.getuid()}:{os.getgid()}",
        "--memory", mem, "--memory-swap", mem, "--cpus", cpus,
        "-e", "PYTHONPATH=/sim", "-e", "HOME=/out", "-e", "MPLCONFIGDIR=/out/.mpl",
        "-e", "OMP_NUM_THREADS=1", "-e", "OPENBLAS_NUM_THREADS=1",
        "-v", f"{sim}:/sim:ro", "-v", f"{out}:/out", "-w", "/out",
        image, "python", f"/sim/{argv[0]}", *argv[1:],
    ]
    with open(out / "run.log", "ab") as log:
        return subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
