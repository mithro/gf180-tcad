# SPDX-License-Identifier: Apache-2.0
"""``python -m gf180tcad.calibrate``: the C-V calibration and its validation, in the TCAD image.

``run --device D --out ROOT`` runs on the host (the committed tree root is
:repo:`results/tcad/calibration`). It runs ``calibrate-job`` in the 1D results image
(:data:`gf180tcad.tcad.RESULTS_IMAGE`, the dev-HEAD image) through
:func:`gf180tcad.sandbox.run`, with a scratch directory as ``/work/out``: the whole
``least_squares`` fit (:func:`gf180tcad.calibrate.cv.calibrate_cv`) is one sandbox job of one
CPU and 2 GiB, each evaluation one 1D DEVSIM sweep. The host then copies ``<device>.json`` and
``<device>.result.json`` into ``ROOT`` and writes ``ROOT/provenance.json``
(:func:`gf180tcad.tcad.tree_provenance`). The job appends one line per evaluation to
``progress.log`` in the scratch directory, whose path the host prints when the job starts.

``validate --device D --out ROOT`` runs on the host (the committed tree root is
:repo:`results/tcad/validation`). It refuses unless ``results/tcad/calibration/<device>.json``
and its ``.result.json`` are committed and unmodified (``git ls-files``, ``git diff HEAD``),
then runs ``validate-job`` in the same image, which loads the frozen calibration
(:func:`gf180tcad.calibrate.cv.load_frozen`), runs
:func:`gf180tcad.calibrate.cv.validate_cv` and writes ``<device>.json``; the host copies it into
``ROOT`` and writes ``ROOT/provenance.json`` with the calibration file's sha256 and
``param_sha256`` of every device validated there.

Comparisons and verdicts are computed inside the image, from the SPICE CSVs parsed bit-exactly.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from gf180tcad import io, sandbox
from gf180tcad.calibrate import cv
from gf180tcad.devices import DEVICES
from gf180tcad.layout import PROVENANCE_NAME
from gf180tcad.tcad import (
    RESULTS_IMAGE,
    calibration_file,
    gplugins_commit,
    image_ref,
    meshconv,
    process,
    tree_provenance,
)

JOB_MEM = "2g"  # one 1D sweep at a time needs well under 1 GiB
JOB_CPUS = 1
IMAGE = RESULTS_IMAGE["moscap1d"]  # the 1D model's image
PROGRESS_NAME = "progress.log"


class NotCommitted(RuntimeError):
    """``validate`` before the calibration files are committed and clean."""


class _Progress:
    def __init__(self, out: Path, prefix: str) -> None:
        self.path = Path(out) / PROGRESS_NAME
        self.prefix = prefix

    def __call__(self, line: str) -> None:
        text = f"{self.prefix}: {line}"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
        print(text, flush=True)


def calibration_geometries(device: str):
    """The calibration geometries of ``device`` (``role == "calibration"``)."""
    return tuple(g for g in DEVICES[device].geometries if g.role == "calibration")


def run_job(device: str, out: Path) -> None:
    """``calibrate-job``: the fit, inside the sandbox; writes both calibration files to ``out``."""
    if not sandbox.in_sandbox():
        raise RuntimeError("calibrate-job must run inside the sandbox (see tools/sandbox-run)")
    log = _Progress(out, device)
    res = cv.calibrate_cv(
        device, geometries=calibration_geometries(device), simulate=cv.devsim_simulator(device),
        log=log,
    )  # fmt: skip
    res.write(Path(out))
    hits = ", ".join(f"{k} at the {v} bound" for k, v in res.bound_hits.items()) or "no bound hit"
    print(f"{device}: {res.values} ({hits}); verdict {res.verdict}", flush=True)


def run_validate_job(device: str, out: Path) -> None:
    """``validate-job``: the validation of the committed calibration, inside the sandbox."""
    if not sandbox.in_sandbox():
        raise RuntimeError("validate-job must run inside the sandbox (see tools/sandbox-run)")
    frozen = cv.load_frozen(device)
    res = cv.validate_cv(device, frozen)
    res.write(Path(out))
    print(f"{device}: 1D validation verdict {res.verdict_1d}", flush=True)


def _sandbox_job(cmd: list[str], scratch: Path, what: str) -> str:
    try:
        res = sandbox.run(
            cmd, out_dir=scratch, image=image_ref(IMAGE), mem=JOB_MEM, cpus=JOB_CPUS
        )
    except sandbox.SandboxError as e:
        log = scratch / "job.log"
        log.write_text(f"{e.result.stdout or ''}\n{e.result.stderr or ''}", encoding="utf-8")
        raise RuntimeError(f"{what} failed (exit {e.result.returncode}); log: {log}") from e
    (scratch / "job.log").write_text(f"{res.stdout or ''}\n{res.stderr or ''}", encoding="utf-8")
    return res.stdout


def _summary(stdout: str, device: str) -> str:
    lines = [ln for ln in stdout.splitlines() if ln.startswith(f"{device}: ")]
    return lines[-1] if lines else f"{device}: done"


def run_host(device: str, root: Path) -> None:
    """``run``: ``calibrate-job`` in the TCAD image, then the tree files under ``root``."""
    meshconv.selected_spec(device, 1)  # refuses a missing mesh-convergence result
    gplugins_commit()  # refuses a dirty or unpinned plugin before anything runs
    root = Path(root)
    scratch = Path(tempfile.mkdtemp(prefix="gf180tcad-calibrate-"))
    print(f"{device}: progress in {scratch / PROGRESS_NAME}", flush=True)
    cmd = ["python3", "-m", "gf180tcad.calibrate", "calibrate-job", "--device", device,
           "--out", "/work/out"]  # fmt: skip
    print(_summary(_sandbox_job(cmd, scratch, "calibrate-job"), device), flush=True)
    root.mkdir(parents=True, exist_ok=True)
    for name in (f"{device}.json", f"{device}{cv.RESULT_SUFFIX}"):
        shutil.copyfile(scratch / name, root / name)
    io.write_json(root / PROVENANCE_NAME, tree_provenance(root, {"moscap1d": IMAGE}))
    shutil.rmtree(scratch)


def check_committed(device: str) -> None:
    """Raise :class:`NotCommitted` unless the calibration files of ``device`` are tracked by git
    and unchanged against ``HEAD``."""
    cal = calibration_file(device)
    files = [cal, cal.with_name(f"{device}{cv.RESULT_SUFFIX}")]
    for f in files:
        rel = f.relative_to(sandbox.REPO_ROOT).as_posix()
        for args in (["ls-files", "--error-unmatch", rel], ["diff", "--quiet", "HEAD", "--", rel]):
            res = subprocess.run(
                ["git", *args], cwd=sandbox.REPO_ROOT, capture_output=True, text=True, check=False
            )
            if res.returncode != 0:
                raise NotCommitted(
                    f"{rel} must be committed and unchanged before validation "
                    f"(git {' '.join(args)} failed)"
                )


def run_validate_host(device: str, root: Path) -> None:
    """``validate``: ``validate-job`` in the TCAD image, then the tree files under ``root``."""
    check_committed(device)
    cv.load_frozen(device)  # refuses an inconsistent pair before anything runs
    meshconv.selected_spec(device, 1)
    gplugins_commit()
    root = Path(root)
    scratch = Path(tempfile.mkdtemp(prefix="gf180tcad-validate-"))
    cmd = ["python3", "-m", "gf180tcad.calibrate", "validate-job", "--device", device,
           "--out", "/work/out"]  # fmt: skip
    print(_summary(_sandbox_job(cmd, scratch, "validate-job"), device), flush=True)
    root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(scratch / f"{device}.json", root / f"{device}.json")
    io.write_json(root / PROVENANCE_NAME, tree_provenance(root, {"moscap1d": IMAGE}))
    shutil.rmtree(scratch)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m gf180tcad.calibrate")
    sub = ap.add_subparsers(dest="command", required=True)
    for name, help_ in (
        ("run", "fit the 1D MOS capacitor to the TT ngspice Cgg-Vg (host: runs calibrate-job)"),
        ("calibrate-job", "internal: the fit, inside the sandbox"),
        ("validate", "validate the committed calibration (host: runs validate-job)"),
        ("validate-job", "internal: the validation, inside the sandbox"),
    ):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--device", choices=process.DEVICES, required=True)
        p.add_argument(
            "--out", type=Path, required=True,
            help="tree root: results/tcad/calibration or results/tcad/validation",
        )  # fmt: skip
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    try:
        if a.command == "run":
            run_host(a.device, a.out)
        elif a.command == "calibrate-job":
            run_job(a.device, a.out)
        elif a.command == "validate":
            run_validate_host(a.device, a.out)
        else:
            run_validate_job(a.device, a.out)
    except (NotCommitted, cv.NotFrozen, FileNotFoundError) as e:
        print(f"{a.command}: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
