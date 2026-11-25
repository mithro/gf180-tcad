# SPDX-License-Identifier: Apache-2.0
"""Run one script of this folder in the sandbox (tools/sandbox-run) with a pinned image.

    uv run python experiments/hv-junction/run.py [--charon] [--mem 8g] OUTDIR SCRIPT [ARGS...]

OUTDIR is outside the repository (the sandbox refuses the repository); it is the working
directory of the script and receives run.log. The DEVSIM image is docker/TCAD_DEV_IMAGE
and the Charon image docker/CHARON_IMAGE. pins() is what a run uses: the commit, the image
and the sha256 of every file of this folder.
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
IN_SANDBOX = "/work/src/experiments/hv-junction"


def image(charon=False):
    name = "CHARON_IMAGE" if charon else "TCAD_DEV_IMAGE"
    return (REPO / "docker" / name).read_text(encoding="utf-8").split()[0]


def _git(*args):
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True, text=True).stdout


def pins(charon=False, allow_dirty=False):
    """The commit, image and file hashes of a run (ValueError if this folder has uncommitted
    changes, unless allow_dirty)."""
    dirty = _git("status", "--porcelain", "--untracked-files=no", "--",
                 "experiments/hv-junction", "docker", "tools")  # fmt: skip
    if dirty and not allow_dirty:
        raise ValueError(f"uncommitted changes:\n{dirty}")
    tracked = _git("ls-files", "--", "experiments/hv-junction").split()
    files = sorted(REPO / t for t in tracked)
    return {
        "commit": _git("rev-parse", "HEAD").strip(),
        "dirty": bool(dirty),
        "image": image(charon),
        "files_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }


def run(out, script, args=(), charon=False, mem="8g"):
    out = pathlib.Path(out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(REPO / "tools" / "sandbox-run"), "--mem", mem, "--cpus", "1",
           "--image", image(charon), "--workdir", str(out), "--",
           "env", f"PYTHONPATH={IN_SANDBOX}", "MPLCONFIGDIR=/tmp/mpl",
           "python3", f"{IN_SANDBOX}/{script}", *args]  # fmt: skip
    with open(out / "run.log", "ab") as log:
        return subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=False).returncode


def main(argv):
    charon, mem = False, "8g"
    while argv and argv[0].startswith("--"):
        opt = argv.pop(0)
        if opt == "--charon":
            charon = True
        elif opt == "--mem":
            mem = argv.pop(0)
        else:
            sys.exit(f"unknown option {opt}")
    return run(argv[0], argv[1], argv[2:], charon, mem)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
