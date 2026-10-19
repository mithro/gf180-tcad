# SPDX-License-Identifier: Apache-2.0
"""``python -m gf180tcad.tcad``: the :term:`TCAD` :term:`MOS capacitor <MOSCAP>` jobs.

``moscap --device D --dim 1 --params start|calibrated --out ROOT`` runs on the host. It writes
``ROOT/<device>/<params>/per_area.csv`` and ``per_area.meta.json``
(:mod:`gf180tcad.tcad.moscap1d`) and the tree root's ``ROOT/provenance.json``
(:func:`gf180tcad.tcad.tree_provenance`); the committed tree is :repo:`results/tcad/moscap1d`.
The simulation itself is ``moscap-job``, which runs inside the TCAD image
(:repo:`docker/TCAD_IMAGE`) through :func:`gf180tcad.sandbox.run` with a scratch directory as
``/work/out``; the host then copies the two files into place.

``--params start`` uses the tunables' starts in the device's process file ``<device>.toml``
in :repo:`data/process` (the card values); ``--params calibrated``
uses ``results/tcad/calibration/<device>.json``, written by
:repo:`Task 12 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-12-calibrate-against-spice-cggvg>` and read with
:func:`gf180tcad.tcad.calibration.read`, and refuses to run if that file is absent or does not
hold exactly the tunables. So start results are never mistaken for calibrated ones. The gate
biases are those of the :term:`SPICE` :term:`cv` sweep, in its order (:func:`job_vg`), and the
mesh is :attr:`gf180tcad.tcad.mesh.MeshSpec.DEFAULT_1D`.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from gf180tcad import io, sandbox
from gf180tcad.layout import PROVENANCE_NAME
from gf180tcad.tcad import (
    TCAD_IMAGE,
    calibration,
    calibration_file,
    gplugins_commit,
    moscap1d,
    process,
    tree_provenance,
)
from gf180tcad.tcad.mesh import MeshSpec

PARAMS = ("start", "calibrated")
DIMS = (1,)  # 2 arrives with Task 11
JOB_MEM = "2g"  # a 1D sweep needs well under 1 GiB
JOB_CPUS = 1


class MissingCalibration(FileNotFoundError):
    """``--params calibrated`` without ``results/tcad/calibration/<device>.json``."""


def load_params(device: str, params: str) -> tuple[process.ProcessDescription, str | None]:
    """``device``'s process description with its ``params`` tunable values.

    Returns it with the calibration file's sha256 (None for ``start``). The calibration file
    is read with :func:`gf180tcad.tcad.calibration.read`, which refuses a partial or unknown
    set of tunables.
    """
    proc = process.load(device)
    if params == "start":
        return proc, None
    path = calibration_file(device)
    if not path.is_file():
        raise MissingCalibration(
            f"--params calibrated needs {path.relative_to(sandbox.REPO_ROOT)} (Task 12), which "
            "does not exist"
        )
    return proc.with_values(calibration.read(path, device)), calibration.sha256_file(path)


def job_vg(proc: process.ProcessDescription) -> tuple[float, ...]:
    """The gate biases (V) of the SPICE ``cv`` sweep in its order: polarity times ``CV_VG``.

    The nfet sweeps from -5 to +5 V and the pfet from +5 to -5 V, both from accumulation, as
    the SPICE ``cv.csv`` files do, so TCAD and SPICE rows match one to one.
    """
    pol = 1.0 if proc.polarity == "n" else -1.0
    return tuple(pol * v + 0.0 for v in process.CV_VG)  # + 0.0: no -0.0


def run_job(device: str, params: str, out: Path) -> None:
    """``moscap-job``: simulate the 1D MOS capacitor and write its files into ``out``."""
    if not sandbox.in_sandbox():
        raise RuntimeError("moscap-job must run inside the sandbox (see tools/sandbox-run)")
    proc, calibration_sha256 = load_params(device, params)
    cv = moscap1d.simulate(proc, vg=job_vg(proc), method="qs", mesh=MeshSpec.DEFAULT_1D)
    moscap1d.write(cv, Path(out), proc=proc, params=params, calibration_sha256=calibration_sha256)
    print(f"{device}/{params}: {len(cv.vg)} points", flush=True)


def run_host(device: str, params: str, root: Path) -> None:
    """``moscap``: run ``moscap-job`` in the TCAD image, then write the job dir and provenance."""
    load_params(device, params)  # refuses a missing calibration before anything runs
    gplugins_commit()  # refuses a dirty or unpinned plugin before anything runs
    root = Path(root)
    scratch = Path(tempfile.mkdtemp(prefix="gf180tcad-moscap1d-"))
    cmd = [
        "python3", "-m", "gf180tcad.tcad", "moscap-job",
        "--device", device, "--dim", "1", "--params", params, "--out", "/work/out",
    ]  # fmt: skip
    try:
        res = sandbox.run(cmd, out_dir=scratch, image=TCAD_IMAGE, mem=JOB_MEM, cpus=JOB_CPUS)
    except sandbox.SandboxError as e:
        log = scratch / "job.log"
        log.write_text(f"{e.result.stdout or ''}\n{e.result.stderr or ''}", encoding="utf-8")
        raise RuntimeError(f"moscap-job failed (exit {e.result.returncode}); log: {log}") from e
    # DEVSIM logs every Newton iteration; echo only the job's summary line.
    summary = [ln for ln in res.stdout.splitlines() if ln.startswith(f"{device}/{params}:")]
    print(summary[-1] if summary else f"{device}/{params}: done", flush=True)
    dest = root / device / params
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in (moscap1d.PER_AREA_CSV, moscap1d.PER_AREA_META):
        shutil.copyfile(scratch / name, dest / name)
    io.write_json(root / PROVENANCE_NAME, tree_provenance(root))
    shutil.rmtree(scratch)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m gf180tcad.tcad")
    sub = ap.add_subparsers(dest="command", required=True)
    for name, help_ in (
        ("moscap", "simulate a MOS capacitor C-V (host: runs moscap-job in the TCAD image)"),
        ("moscap-job", "internal: one MOS capacitor job, inside the sandbox"),
    ):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--device", choices=process.DEVICES, required=True)
        p.add_argument("--dim", type=int, choices=DIMS, required=True)
        p.add_argument("--params", choices=PARAMS, required=True)
        p.add_argument(
            "--out", type=Path, required=True, help="tree root, e.g. results/tcad/moscap1d"
        )
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    try:
        if a.command == "moscap-job":
            run_job(a.device, a.params, a.out)
        else:
            run_host(a.device, a.params, a.out)
    except MissingCalibration as e:
        print(f"{a.command}: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
