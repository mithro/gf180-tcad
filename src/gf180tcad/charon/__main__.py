# SPDX-License-Identifier: Apache-2.0
"""``python -m gf180tcad.charon``: the MOS capacitor jobs on Charon.

``moscap --device D --dim 1 --params start|calibrated --out ROOT`` runs on the host. It runs
``moscap-job`` in the pinned Charon image (:repo:`docker/CHARON_IMAGE`) through
:func:`gf180tcad.sandbox.run` (2 GiB, one CPU, no network) with a scratch directory as
``/work/out``, then copies ``per_area.csv`` and ``per_area.meta.json`` to
``ROOT/<device>/<params>/`` and writes ``ROOT/provenance.json``
(:func:`gf180tcad.tcad.tree_provenance`, generator :data:`gf180tcad.charon.CHARON_MAIN`). The
parameters, gate biases and mesh are those of the DEVSIM job (:mod:`gf180tcad.tcad.__main__`:
``load_params``, ``job_vg``, the selected mesh-convergence level). The tree root is
:data:`gf180tcad.charon.TREE_ROOT` ``/moscap1d``. ``--dim 2`` is Task E of the Charon plan and is
refused.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from gf180tcad import io, sandbox
from gf180tcad.charon import CHARON_IMAGE_NAME, CHARON_MAIN
from gf180tcad.charon import moscap as charon_moscap
from gf180tcad.layout import PROVENANCE_NAME
from gf180tcad.tcad import gplugins_commit, image_ref, meshconv, moscap1d, process, tree_provenance
from gf180tcad.tcad.__main__ import MissingCalibration, job_vg, load_params, mesh_source

PARAMS = ("start", "calibrated")
JOB_MEM = "2g"
JOB_CPUS = 1
#: The scratch directory of a job's Charon run (the mesh, decks, logs and Exodus states).
RUN_DIR = "charon_run"


def run_job(device: str, params: str, out: Path) -> None:
    """``moscap-job``: simulate the 1D MOS capacitor on Charon and write its files into ``out``."""
    if not sandbox.in_sandbox():
        raise RuntimeError("moscap-job must run inside the sandbox (see tools/sandbox-run)")
    proc, calibration_sha256 = load_params(device, params)
    mesh = meshconv.selected_spec(device, 1)
    out = Path(out)
    cv = charon_moscap.simulate(proc, vg=job_vg(proc), mesh=mesh, workdir=out / RUN_DIR)
    charon_moscap.write(
        cv, out, proc=proc, params=params, mesh_source=mesh_source(device),
        image=image_ref(CHARON_IMAGE_NAME), calibration_sha256=calibration_sha256,
    )  # fmt: skip
    print(f"{device}/{params}: {len(cv.vg)} points", flush=True)


def run_host(device: str, params: str, root: Path, dim: int = 1, mem: str = JOB_MEM) -> None:
    """``moscap``: run ``moscap-job`` in the Charon image, then write the job dir and provenance."""
    if dim != 1:
        raise NotImplementedError("the 2D MOS capacitor on Charon is Task E of the Charon plan")
    root = Path(root)
    load_params(device, params)  # refuses a missing calibration before anything runs
    meshconv.selected_spec(device, 1)  # refuses a missing mesh-convergence result
    gplugins_commit()  # refuses a dirty or unpinned plugin before anything runs
    scratch = Path(tempfile.mkdtemp(prefix="gf180tcad-charon-moscap1d-"))
    cmd = ["python3", "-m", "gf180tcad.charon", "moscap-job", "--device", device,
           "--params", params, "--out", "/work/out"]  # fmt: skip
    try:
        res = sandbox.run(cmd, out_dir=scratch, image=image_ref(CHARON_IMAGE_NAME), mem=mem,
                          cpus=JOB_CPUS)  # fmt: skip
    except sandbox.SandboxError as e:
        log = scratch / "job.log"
        log.write_text(f"{e.result.stdout or ''}\n{e.result.stderr or ''}", encoding="utf-8")
        raise RuntimeError(f"moscap-job failed (exit {e.result.returncode}); log: {log}") from e
    tag = f"{device}/{params}"
    summary = [ln for ln in res.stdout.splitlines() if ln.startswith(tag)]
    print(summary[-1] if summary else f"{tag}: done", flush=True)
    dest = root / device / params
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in (moscap1d.PER_AREA_CSV, moscap1d.PER_AREA_META):
        shutil.copyfile(scratch / name, dest / name)
    io.write_json(
        root / PROVENANCE_NAME,
        tree_provenance(root, {"moscap1d": CHARON_IMAGE_NAME}, generator=CHARON_MAIN),
    )
    shutil.rmtree(scratch)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m gf180tcad.charon")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("moscap", help="the 1D MOS capacitor C-V on Charon (host)")
    p.add_argument("--device", choices=process.DEVICES, required=True)
    p.add_argument("--dim", type=int, choices=(1, 2), default=1)
    p.add_argument("--params", choices=PARAMS, required=True)
    p.add_argument(
        "--out", type=Path, required=True, help="tree root: results/tcad-charon/moscap1d"
    )
    p.add_argument("--mem", default=JOB_MEM, help="memory of the sandbox job")
    p = sub.add_parser("moscap-job", help="internal: one Charon MOS capacitor job, in the sandbox")
    p.add_argument("--device", choices=process.DEVICES, required=True)
    p.add_argument("--params", choices=PARAMS, required=True)
    p.add_argument("--out", type=Path, required=True)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    try:
        if a.command == "moscap-job":
            run_job(a.device, a.params, a.out)
        else:
            run_host(a.device, a.params, a.out, a.dim, a.mem)
    except (MissingCalibration, NotImplementedError) as e:
        print(f"{a.command}: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
