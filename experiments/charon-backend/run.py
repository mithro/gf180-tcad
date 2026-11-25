# SPDX-License-Identifier: Apache-2.0
"""Run the Charon backend experiments (Task B, B1 to B7) one at a time in the Charon image.

    uv run --locked python experiments/charon-backend/run.py WORKDIR STEP...

WORKDIR is outside the repository (the sandbox refuses the repo). Each step runs in
WORKDIR/<step>/ through tools/sandbox-run (2 GiB, one CPU, no network, the pinned Charon image),
with this directory's scripts copied in; its complete output goes to <step>/run.log and its pins
to <step>/pins.json. A step whose done.json exists is skipped, so a cut-off run resumes. The
steps are listed in STEPS; ``all`` runs every one in order.

The sandbox imports the checkout's sources (gf180tcad and the gplugins submodule), so a run is
pinned to them: run.py refuses a checkout with uncommitted changes under PINNED_PATHS, and
pins.json holds the commit, the Charon image, the plugin commit and the sha256 of every script.
The pins are taken before and after a step and must agree. Before each step it waits while two
or more gf180-tcad containers run, so it never adds a third job to the host.
"""

import hashlib
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

# The checkout paths a run reads; any uncommitted change under them is refused.
PINNED_PATHS = ("src", "experiments/charon-backend", "docker", "results/tcad",
                "third_party/gplugins", "tools/sandbox-run")  # fmt: skip

# step -> shell command run in the step directory inside the sandbox. The C-V runs (cv-*) are
# b2.py then b2an.py with their settings in the environment (see b2.py).
_HARD = ("ref_1e-10 tol_1e-8 tol_1e-6 tol_1e-4 scale_1e20 scale_1e10 step_5mV gfem belos nosrh "
         "tau_1e-12 tau_1e-13 tau_1e-14 tau_1e-15 tau_1e-15_step_5mV tau_1e-12_tol_1e-8")


def _cv(dev: str, rel: str, abs_: str, *, tau: str = "", vgmax: str = "", sub: str = "",
        pred: str = "") -> str:
    env = (f"CX_REL={rel} CX_ABS={abs_} CX_LIN=klu2 CX_TAU={tau} CX_VGMAX={vgmax} "
           f"CX_SUB={sub} CX_PRED={pred}")  # fmt: skip
    return (f"env {env} python3 b2.py {dev} calibrated ni && "
            f"env {env} python3 b2an.py {dev} calibrated result")


STEPS = {
    "b5-doping": "python3 b5.py",
    "b3-solvers": "python3 b3.py",
    "b2-hard-range": f"env CX_VEND=5.0 python3 b2h.py {_HARD}",
    "b2-inversion-side": "python3 b2d.py",
    "b2-nlp": "python3 b2nlp.py",
    "cv-nfet-default-1e-10": _cv("nfet_05v0", "1e-10", "1e-12", vgmax="0.35"),
    "cv-nfet-default-1e-8": _cv("nfet_05v0", "1e-8", "1e-10", vgmax="0.35"),
    "cv-nfet-tau15-1e-10": _cv("nfet_05v0", "1e-10", "1e-12", tau="1e-15", sub="5"),
    "cv-nfet-tau14-1e-10": _cv("nfet_05v0", "1e-10", "1e-12", tau="1e-14", sub="5"),
    "cv-nfet-tau15-1e-9": _cv("nfet_05v0", "1e-9", "1e-11", tau="1e-15", sub="5"),
    "cv-nfet-tau15-constant": _cv("nfet_05v0", "1e-10", "1e-12", tau="1e-15", pred="constant"),
    "cv-pfet-tau15-1e-10": _cv("pfet_05v0", "1e-10", "1e-12", tau="1e-15", sub="5"),
    "cv-pfet-tau14-1e-10": _cv("pfet_05v0", "1e-10", "1e-12", tau="1e-14", sub="5"),
    "b4-harmonic-balance": ("for fa in '1e6 1e-4' '1e3 1e-4' '1e0 1e-4' '1e6 1e-3' '1e6 1e-5'; do "
                            "set -- $fa; env CX_REL=1e-8 CX_ABS=1e-10 CX_F=$1 CX_AMP=$2 "
                            "python3 b4.py || exit 1; done"),  # fmt: skip
    "b1-tri3": "python3 b1.py && python3 b1an.py",
}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True,
                          text=True).stdout  # fmt: skip


def pins() -> dict:
    """What a step uses, from the checkout as it is now (ValueError if it has uncommitted
    changes under PINNED_PATHS)."""
    dirty = _git("status", "--porcelain", "--", *PINNED_PATHS)
    if dirty:
        raise ValueError(f"uncommitted changes under {PINNED_PATHS}:\n{dirty}")
    scripts = sorted(p for p in HERE.iterdir() if p.suffix in (".py", ".sh"))
    return {
        "commit": _git("rev-parse", "HEAD").strip(),
        "image": (REPO / "docker" / "CHARON_IMAGE").read_text(encoding="utf-8").strip(),
        "gplugins_commit": _git("rev-parse", "HEAD:third_party/gplugins").strip(),
        "scripts_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in scripts},
    }


def _busy() -> int:
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], check=True,
                         capture_output=True, text=True).stdout  # fmt: skip
    return sum(1 for n in out.split() if n.startswith("gf180tcad-"))


def run_step(work: Path, step: str) -> int:
    out = work / step
    out.mkdir(parents=True, exist_ok=True)
    if (out / "done.json").is_file():
        print(f"{step}: done before", flush=True)
        return 0
    while _busy() >= 2:
        print(f"{step}: two or more gf180-tcad containers run; waiting", flush=True)
        time.sleep(60)
    before = pins()
    for p in HERE.iterdir():
        if p.suffix == ".py":
            (out / p.name).write_bytes(p.read_bytes())
    (out / "pins.json").write_text(json.dumps(before, indent=1, sort_keys=True) + "\n")
    cmd = [str(REPO / "tools" / "sandbox-run"), "--mem", "2g", "--cpus", "1",
           "--network", "none", "--image", before["image"], "--workdir", str(out), "--",
           "bash", "-o", "pipefail", "-c", STEPS[step]]  # fmt: skip
    t0 = time.time()
    with open(out / "run.log", "wb") as log:
        rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode
    after = pins()
    if after != before:
        raise RuntimeError(f"{step}: the pins changed during the run")
    (out / "done.json").write_text(json.dumps({"exit": rc, "wall_s": round(time.time() - t0, 1),
                                               "command": STEPS[step]}, indent=1) + "\n")
    print(f"{step}: exit {rc} ({time.time() - t0:.0f} s), log {shlex.quote(str(out / 'run.log'))}",
          flush=True)
    return rc


def main(argv: list[str]) -> int:
    work, *steps = argv
    work = Path(work).expanduser().resolve()
    if work == REPO or REPO in work.parents:
        raise SystemExit("WORKDIR must be outside the repository")
    if steps == ["all"]:
        steps = list(STEPS)
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        raise SystemExit(f"unknown steps {unknown}; known: {list(STEPS)}")
    rc = 0
    for s in steps:
        rc |= run_step(work, s)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
