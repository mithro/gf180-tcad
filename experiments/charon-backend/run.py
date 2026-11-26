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
pins.json holds the last commit that changed a pinned path, the Charon image, the plugin commit and the sha256 of every script.
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

# The checkout paths a run reads; any uncommitted change under them is refused. The figure
# module of the write-up and this directory's Markdown are excluded: no step reads them.
PINNED_PATHS = ("src", ":(exclude)src/gf180tcad/limitations_figures.py",
                "experiments/charon-backend", ":(exclude)experiments/charon-backend/*.md",
                "docker", "results/tcad",
                "third_party/gplugins", "tools/sandbox-run")  # fmt: skip

# step -> shell command run in the step directory inside the sandbox. The C-V runs (cv-*) are
# b2.py then b2an.py with their settings in the environment (see b2.py).
_HARD = (
    "ref_1e-10 tol_1e-8 tol_1e-6 tol_1e-4 scale_1e20 scale_1e10 step_5mV gfem belos nosrh "
    "tau_1e-12 tau_1e-13 tau_1e-14 tau_1e-15 tau_1e-15_step_5mV tau_1e-12_tol_1e-8"
)


def _env(rel: str, abs_: str, *, tau: str = "", vgmax: str = "", vgmin: str = "", sub: str = "",
         pred: str = "", reverse: str = "", partial: str = "", norescue: str = "") -> str:  # fmt: skip
    return (f"CX_REL={rel} CX_ABS={abs_} CX_LIN=klu2 CX_TAU={tau} CX_VGMAX={vgmax} "
            f"CX_VGMIN={vgmin} CX_SUB={sub} CX_PRED={pred} CX_REVERSE={reverse} "
            f"CX_PARTIAL={partial} CX_NORESCUE={norescue}")  # fmt: skip


def _cv(dev: str, rel: str, abs_: str, *, params: str = "calibrated", **kw: str) -> str:
    env = _env(rel, abs_, **kw)
    return (
        f"env {env} python3 b2.py {dev} {params} ni && "
        f"env {env} python3 b2an.py {dev} {params} result"
    )


def _study(dev: str, rel: str, abs_: str, *, params: str = "calibrated", **kw: str) -> str:
    """A sweep that may stop: b2.py records where (b2_failed.json); the step exits 0."""
    return f"env {_env(rel, abs_, **kw)} python3 b2.py {dev} {params} ni; echo $? > b2_exit.txt"


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
    "cv-pfet-tau15-1e-9": _cv("pfet_05v0", "1e-9", "1e-11", tau="1e-15", sub="5"),
    "cv-nfet-start-tau15-1e-10": _cv(
        "nfet_05v0", "1e-10", "1e-12", params="start", tau="1e-15", sub="5"
    ),
    "cv-nfet-start-tau15-1e-9": _cv(
        "nfet_05v0", "1e-9", "1e-11", params="start", tau="1e-15", sub="5"
    ),
    "cv-pfet-start-tau15-1e-9": _cv(
        "pfet_05v0", "1e-9", "1e-11", params="start", tau="1e-15", sub="5"
    ),
    # the pfet start values at 1e-10 from -5 V up; the converged grid points are kept
    "cv-pfet-start-tau15-1e-10-from-minus-5": _cv(
        "pfet_05v0",
        "1e-10",
        "1e-12",
        params="start",
        tau="1e-15",
        sub="5",
        reverse="1",
        partial="1",
    ),
    # the pfet start values at 1e-10 stop at 0.569 V (the studies below); compared above it
    "cv-pfet-start-tau15-1e-10-above-0.6": _cv(
        "pfet_05v0", "1e-10", "1e-12", params="start", tau="1e-15", sub="5", vgmin="0.6"
    ),
    "b4-harmonic-balance": (
        "for fa in '1e6 1e-4' '1e3 1e-4' '1e0 1e-4' '1e6 1e-3' '1e6 1e-5'; do "
        "set -- $fa; env CX_REL=1e-8 CX_ABS=1e-10 CX_F=$1 CX_AMP=$2 "
        "python3 b4.py || exit 1; done"
    ),
    "b1-tri3": "python3 b1.py && python3 b1an.py",
    # Step study: one LOCA step per 50 mV grid step with the secant predictor. It may stop in
    # inversion; the step records where (b2_failed.json) and exits 0.
    "study-nfet-tau15-secant-50mV": (
        "env CX_REL=1e-10 CX_ABS=1e-12 CX_LIN=klu2 CX_TAU=1e-15 CX_VGMAX= CX_SUB=1 "
        "CX_PRED=secant python3 b2.py nfet_05v0 calibrated ni; echo $? > b2_exit.txt"
    ),
    # Step study (B7): a ten times tighter WRMS tolerance than the reference, where the default
    # lifetime converges. It may fail; the step records where and exits 0.
    "study-nfet-default-1e-11": (
        "env CX_REL=1e-11 CX_ABS=1e-13 CX_LIN=klu2 CX_TAU= CX_VGMAX=0.35 CX_SUB= "
        "CX_PRED= python3 b2.py nfet_05v0 calibrated ni; echo $? > b2_exit.txt"
    ),
    # The pfet start values' stall at 1e-10 and the settings tried on it (each may stop).
    "study-pfet-start-1e-10": _study(
        "pfet_05v0", "1e-10", "1e-12", params="start", tau="1e-15", sub="5"
    ),
    "study-pfet-start-1e-10-rescue-off": _study(
        "pfet_05v0", "1e-10", "1e-12", params="start", tau="1e-15", sub="5", norescue="1"
    ),
    "study-pfet-start-1e-10-5mV": _study(
        "pfet_05v0", "1e-10", "1e-12", params="start", tau="1e-15", sub="10"
    ),
    "study-pfet-start-1e-10-tau16": _study(
        "pfet_05v0", "1e-10", "1e-12", params="start", tau="1e-16", sub="5"
    ),
    "study-pfet-start-1e-11": _study(
        "pfet_05v0", "1e-11", "1e-13", params="start", tau="1e-15", sub="5"
    ),
    "study-pfet-start-rel-1e-9-abs-1e-12": _study(
        "pfet_05v0", "1e-9", "1e-12", params="start", tau="1e-15", sub="5"
    ),
    "study-pfet-start-rel-1e-10-abs-1e-11": _study(
        "pfet_05v0", "1e-10", "1e-11", params="start", tau="1e-15", sub="5"
    ),
    "b4-parallel-plate": "python3 b4pp.py",
    "b4-metal-gate": "python3 b4mg.py",
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
        # the last commit that changed a pinned path: later commits elsewhere (docs) leave it
        "commit": _git("log", "-1", "--format=%H", "--", *PINNED_PATHS).strip(),
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
        rc = subprocess.run(cmd, check=False, stdout=log, stderr=subprocess.STDOUT).returncode
    after = pins()
    if after != before:
        raise RuntimeError(f"{step}: the pins changed during the run")
    (out / "done.json").write_text(
        json.dumps(
            {"exit": rc, "wall_s": round(time.time() - t0, 1), "command": STEPS[step]}, indent=1
        )
        + "\n"
    )
    print(
        f"{step}: exit {rc} ({time.time() - t0:.0f} s), log {shlex.quote(str(out / 'run.log'))}",
        flush=True,
    )
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
    pins()  # refuse a dirty checkout before any wait
    rc = 0
    for s in steps:
        rc |= run_step(work, s)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
