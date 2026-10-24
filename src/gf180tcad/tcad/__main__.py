# SPDX-License-Identifier: Apache-2.0
"""``python -m gf180tcad.tcad``: the :term:`TCAD` :term:`MOS capacitor <MOSCAP>` jobs.

``moscap --device D --dim 1 --params start|calibrated --out ROOT`` runs on the host. It writes
``ROOT/<device>/<params>/per_area.csv`` and ``per_area.meta.json``
(:mod:`gf180tcad.tcad.moscap1d`) and the tree root's ``ROOT/provenance.json``
(:func:`gf180tcad.tcad.tree_provenance`); the committed tree is :repo:`results/tcad/moscap1d`.
The simulation itself is ``moscap-job``, which runs inside the TCAD image through
:func:`gf180tcad.sandbox.run` with a scratch directory as ``/work/out``; the host then copies the
two files into place.

**Image.** ``moscap`` and ``meshconv`` take ``--image dev|stable``. By default (:func:`job_image`,
:data:`gf180tcad.tcad.RESULTS_IMAGE`) 1D jobs run in the dev-HEAD image
(:repo:`docker/TCAD_DEV_IMAGE`) and 2D jobs in the stable image (:repo:`docker/TCAD_IMAGE`); the
tree's ``provenance.json`` records which image made each result kind.

``--params start`` uses the tunables' starts in the device's process file ``<device>.toml``
in :repo:`data/process` (the card values); ``--params calibrated``
uses ``results/tcad/calibration/<device>.json``, written by
:repo:`Task 12 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-12-calibrate-against-spice-cggvg>` and read with
:func:`gf180tcad.tcad.calibration.read`, and refuses to run if that file is absent or does not
hold exactly the tunables. So start results are never mistaken for calibrated ones. The gate
biases are those of the :term:`SPICE` :term:`cv` sweep, in its order (:func:`job_vg`), and the
mesh is the device's selected mesh-convergence level,
``results/tcad/meshconv/moscap1d/<device>/selected.json``
(:func:`gf180tcad.tcad.meshconv.selected_spec`).

``meshconv --device D --dim 1|2 --out ROOT [--jobs N]`` runs on the host; the committed tree
root is :repo:`results/tcad/meshconv`. It runs one ``meshconv-job --level I`` per refinement
level (:data:`gf180tcad.tcad.meshconv.LEVELS`) as separate sandbox jobs, ``N`` at a time
(default: all), under the admission check jobs x memory <= 128 GiB
(:func:`gf180tcad.tcad.meshconv.check_admission`). Each simulates the device's start values
on the start spec :attr:`~gf180tcad.tcad.mesh.MeshSpec.DEFAULT_1D` scaled by its level and
writes :data:`LEVEL_NAME`. Then ``meshconv-job --assemble`` computes the report
(:func:`gf180tcad.tcad.meshconv.converge`) in the same image and writes
``report.json`` and ``selected.json``; the host copies them to ``ROOT/moscap1d/<device>/``,
writes ``ROOT/provenance.json`` and prints each level's runtime (runtimes stay out of the
results). ``--dim 2`` needs the 2D MOS capacitor of
:repo:`Task 11 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`
and is refused until then.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from gf180tcad import io, sandbox
from gf180tcad.layout import PROVENANCE_NAME
from gf180tcad.tcad import (
    IMAGES,
    RESULTS_IMAGE,
    calibration,
    calibration_file,
    check_same_image,
    gplugins_commit,
    image_ref,
    meshconv,
    moscap1d,
    process,
    recorded_images,
    tree_provenance,
)
from gf180tcad.tcad.mesh import MeshSpec

PARAMS = ("start", "calibrated")
DIMS = (1,)  # 2 arrives with Task 11
MESHCONV_DIMS = (1, 2)  # 2 is refused until Task 11 (meshconv.NeedsTask11)
JOB_MEM = "2g"  # a 1D sweep needs well under 1 GiB
JOB_CPUS = 1
MESHCONV_JOB_MEM = {1: JOB_MEM}  # Task 11 adds the 2D jobs' memory

# The file each meshconv-job --level writes into its /work/out.
LEVEL_NAME = "level.json"


def job_image(dim: int, image: str | None) -> str:
    """The TCAD image name (:data:`gf180tcad.tcad.IMAGES`) a ``dim``-D job runs in: ``image``,
    else the result kind's :data:`gf180tcad.tcad.RESULTS_IMAGE`. That is dev HEAD for 1D and,
    explicitly, the stable image for 2D (gmsh 5 meshes differ: 2D needs its own mesh convergence
    on dev, planned before the Phase 2 exit)."""
    return image if image is not None else RESULTS_IMAGE[f"moscap{dim}d"]


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


def mesh_source(device: str) -> str:
    """The repo-relative ``selected.json`` that the 1D results of ``device`` take their mesh from."""
    return (meshconv.job_dir(meshconv.TREE_ROOT, device, 1) / meshconv.SELECTED_NAME).as_posix()


def run_job(device: str, params: str, out: Path) -> None:
    """``moscap-job``: simulate the 1D MOS capacitor and write its files into ``out``."""
    if not sandbox.in_sandbox():
        raise RuntimeError("moscap-job must run inside the sandbox (see tools/sandbox-run)")
    proc, calibration_sha256 = load_params(device, params)
    mesh = meshconv.selected_spec(device, 1)
    cv = moscap1d.simulate(proc, vg=job_vg(proc), method="qs", mesh=mesh)
    moscap1d.write(
        cv, Path(out), proc=proc, params=params, mesh_source=mesh_source(device),
        calibration_sha256=calibration_sha256,
    )  # fmt: skip
    print(f"{device}/{params}: {len(cv.vg)} points", flush=True)


def run_host(device: str, params: str, root: Path, image: str | None = None) -> None:
    """``moscap``: run ``moscap-job`` in the TCAD image, then write the job dir and provenance.

    ``image`` names the TCAD image (default: :func:`job_image`)."""
    image = job_image(1, image)
    root = Path(root)
    check_same_image(
        root, "moscap1d", image,
        (root / d / p for d in process.DEVICES for p in PARAMS if (d, p) != (device, params)),
    )  # fmt: skip
    load_params(device, params)  # refuses a missing calibration before anything runs
    meshconv.selected_spec(device, 1)  # refuses a missing mesh-convergence result
    gplugins_commit()  # refuses a dirty or unpinned plugin before anything runs
    root = Path(root)
    scratch = Path(tempfile.mkdtemp(prefix="gf180tcad-moscap1d-"))
    cmd = [
        "python3", "-m", "gf180tcad.tcad", "moscap-job",
        "--device", device, "--dim", "1", "--params", params, "--out", "/work/out",
    ]  # fmt: skip
    try:
        res = sandbox.run(cmd, out_dir=scratch, image=image_ref(image), mem=JOB_MEM, cpus=JOB_CPUS)
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
    io.write_json(root / PROVENANCE_NAME, tree_provenance(root, {"moscap1d": image}))
    shutil.rmtree(scratch)


# --- meshconv ---------------------------------------------------------------------------------


def run_meshconv_level(device: str, dim: int, level: int, out: Path) -> None:
    """``meshconv-job --level``: simulate refinement level ``level``, write :data:`LEVEL_NAME`."""
    simulate, _ = meshconv.simulator(device, dim)  # refuses dim 2 (Task 11)
    if not sandbox.in_sandbox():
        raise RuntimeError("meshconv-job must run inside the sandbox (see tools/sandbox-run)")
    scale = meshconv.LEVELS[level]
    spec = MeshSpec.DEFAULT_1D.scaled(scale)
    cv = simulate(spec)
    io.write_json(
        Path(out) / LEVEL_NAME,
        {
            "c_per_area_ff_um2": list(cv.c_per_area_ff_um2),
            "node_count": cv.node_count,
            "scale": scale,
            "spec": spec.as_dict(),
            "vg": list(cv.vg),
        },
    )
    print(f"{device}/level{level}: {cv.node_count} nodes, {len(cv.vg)} points", flush=True)


class _Curve:
    """A :class:`gf180tcad.tcad.meshconv.CVCurve` read back from a :data:`LEVEL_NAME`."""

    def __init__(self, data: dict) -> None:
        self.vg = tuple(data["vg"])
        self.c_per_area_ff_um2 = tuple(data["c_per_area_ff_um2"])
        self.node_count = int(data["node_count"])


def run_meshconv_assemble(device: str, dim: int, out: Path) -> None:
    """``meshconv-job --assemble``: the report of the levels in ``out/level<i>/``.

    Writes ``report.json`` and ``selected.json`` into ``out``; raises
    :class:`gf180tcad.tcad.meshconv.NotConverged` (writing nothing) if no level qualifies.
    """
    _, settings = meshconv.simulator(device, dim)
    if not sandbox.in_sandbox():
        raise RuntimeError("meshconv-job must run inside the sandbox (see tools/sandbox-run)")
    out = Path(out)
    curves = {}
    for i, scale in enumerate(meshconv.LEVELS):
        data = json.loads((out / f"level{i}" / LEVEL_NAME).read_bytes())
        spec = MeshSpec.DEFAULT_1D.scaled(scale)
        if data["scale"] != scale or MeshSpec(**data["spec"]) != spec:
            raise RuntimeError(f"level{i}/{LEVEL_NAME} is not level {i} of the start spec")
        curves[spec] = _Curve(data)
    rep = meshconv.converge(curves.__getitem__, MeshSpec.DEFAULT_1D)
    meshconv.write(rep, out, device=device, dim=dim, settings=settings)
    print(f"{device}: selected level {rep.selected}", flush=True)


def _sandbox_job(cmd: list[str], out_dir: Path, mem: str, image: str) -> str:
    try:
        res = sandbox.run(cmd, out_dir=out_dir, image=image_ref(image), mem=mem, cpus=JOB_CPUS)
    except sandbox.SandboxError as e:
        log = out_dir / "job.log"
        log.write_text(f"{e.result.stdout or ''}\n{e.result.stderr or ''}", encoding="utf-8")
        raise RuntimeError(f"{cmd[3]} failed (exit {e.result.returncode}); log: {log}") from e
    return res.stdout


def run_meshconv(
    device: str, dim: int, root: Path, jobs: int | None = None, image: str | None = None
) -> None:
    """``meshconv``: the level jobs and the report job in the TCAD image, then the tree files.

    ``image`` names the TCAD image (default: :func:`job_image`). The tree's provenance.json
    keeps the image recorded for the other dimension's subtree."""
    meshconv.check_dim(dim)  # refuses dim 2 (Task 11)
    image = job_image(dim, image)
    root = Path(root)
    check_same_image(
        root, f"moscap{dim}d", image,
        (meshconv.job_dir(root, d, dim) for d in process.DEVICES if d != device),
    )  # fmt: skip
    mem = MESHCONV_JOB_MEM[dim]
    jobs = len(meshconv.LEVELS) if jobs is None else jobs
    meshconv.check_admission(jobs, mem)
    gplugins_commit()  # refuses a dirty or unpinned plugin before anything runs
    root = Path(root)
    scratch = Path(tempfile.mkdtemp(prefix="gf180tcad-meshconv-"))
    base = ["python3", "-m", "gf180tcad.tcad", "meshconv-job", "--device", device,
            "--dim", str(dim), "--out", "/work/out"]  # fmt: skip

    def level(i: int) -> float:
        d = scratch / f"level{i}"
        d.mkdir()
        t = time.monotonic()
        _sandbox_job([*base, "--level", str(i)], d, mem, image)
        return time.monotonic() - t

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        runtimes = list(pool.map(level, range(len(meshconv.LEVELS))))
    for i, t in enumerate(runtimes):
        print(f"{device}/level{i} (scale {meshconv.LEVELS[i]!r}): {t:.1f} s", flush=True)
    stdout = _sandbox_job([*base, "--assemble"], scratch, mem, image)
    summary = [ln for ln in stdout.splitlines() if ln.startswith(f"{device}: selected")]
    print(summary[-1] if summary else f"{device}: done", flush=True)
    dest = meshconv.job_dir(root, device, dim)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in (meshconv.REPORT_NAME, meshconv.SELECTED_NAME):
        shutil.copyfile(scratch / name, dest / name)
    images = {**recorded_images(root), f"moscap{dim}d": image}
    io.write_json(root / PROVENANCE_NAME, tree_provenance(root, images))
    shutil.rmtree(scratch)


def _image_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--image", choices=sorted(IMAGES), default=None,
        help="TCAD image (default: dev for 1D, stable for 2D; gf180tcad.tcad.RESULTS_IMAGE)",
    )  # fmt: skip


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
        if name == "moscap":
            _image_arg(p)
    p = sub.add_parser(
        "meshconv", help="mesh convergence of a MOS capacitor (host: runs meshconv-job)"
    )
    p.add_argument("--device", choices=process.DEVICES, required=True)
    p.add_argument("--dim", type=int, choices=MESHCONV_DIMS, required=True)
    p.add_argument("--out", type=Path, required=True, help="tree root: results/tcad/meshconv")
    p.add_argument("--jobs", type=int, default=None, help="concurrent level jobs (default: all)")
    _image_arg(p)
    p = sub.add_parser("meshconv-job", help="internal: one mesh-convergence job, in the sandbox")
    p.add_argument("--device", choices=process.DEVICES, required=True)
    p.add_argument("--dim", type=int, choices=MESHCONV_DIMS, required=True)
    p.add_argument("--out", type=Path, required=True)
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("--level", type=int, choices=range(len(meshconv.LEVELS)))
    which.add_argument("--assemble", action="store_true")
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    try:
        if a.command == "moscap-job":
            run_job(a.device, a.params, a.out)
        elif a.command == "moscap":
            run_host(a.device, a.params, a.out, a.image)
        elif a.command == "meshconv-job" and a.assemble:
            run_meshconv_assemble(a.device, a.dim, a.out)
        elif a.command == "meshconv-job":
            run_meshconv_level(a.device, a.dim, a.level, a.out)
        else:
            run_meshconv(a.device, a.dim, a.out, a.jobs, a.image)
    except (MissingCalibration, meshconv.NeedsTask11, meshconv.AdmissionError) as e:
        print(f"{a.command}: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
