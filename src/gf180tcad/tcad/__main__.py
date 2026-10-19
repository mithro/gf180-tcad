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
results). ``--dim 2`` does the same for the 2D MOS capacitor
(:mod:`gf180tcad.tcad.moscap2d`) at :data:`gf180tcad.tcad.meshconv.GEOMETRY_2D`, from
:attr:`~gf180tcad.tcad.mesh.MeshSpec.DEFAULT_2D`, into ``ROOT/moscap2d/<device>/``.

``moscap --device D --dim 2 --params P --geometry GID --out ROOT`` runs the 2D MOS capacitor
of the PDK cell at the SPICE geometry ``GID`` (e.g. ``w10p0_l10p00``) with its source and drain,
on the device's selected 2D mesh (``results/tcad/meshconv/moscap2d/<device>/selected.json``):
the QS sweep (``cv.csv``), the 1 MHz AC sweep with every non-gate contact's Cxg
(``cgx.csv``), the mesh (``mesh.msh``) and ``cv.meta.json`` go to ``ROOT/<device>/<P>/<GID>/``;
the committed tree is :repo:`results/tcad/moscap2d`, with its ``ROOT/provenance.json``.

**Progress.** A 2D job appends one line per bias point (stage, index, gate bias, elapsed
time) to ``progress.log`` in its scratch directory, whose path the host prints when the job
starts; ``--progress-log FILE`` copies the finished log there. Runtimes stay out of the
results.
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
from gf180tcad.devices import DEVICES as SPICE_DEVICES
from gf180tcad.devices import Geometry, geometry_id
from gf180tcad.layout import PROVENANCE_NAME
from gf180tcad.tcad import (
    TCAD_IMAGE,
    calibration,
    calibration_file,
    gplugins_commit,
    meshconv,
    moscap1d,
    moscap2d,
    process,
    tree_provenance,
)
from gf180tcad.tcad.mesh import MeshSpec

PARAMS = ("start", "calibrated")
DIMS = (1, 2)
MESHCONV_DIMS = (1, 2)
JOB_MEM = "2g"  # a 1D sweep needs well under 1 GiB
JOB_CPUS = 1
# A 2D job's memory cap: meshing the L = 10 um cell alone takes 5.2 GiB and its AC sweep runs in
# extended precision; 16 GiB (the sandbox default) leaves room. 8 of them fit 128 GiB.
JOB_MEM_2D = "16g"
MESHCONV_JOB_MEM = {1: JOB_MEM, 2: JOB_MEM_2D}

# The file each meshconv-job --level writes into its /work/out, and the progress log of a job.
LEVEL_NAME = "level.json"
PROGRESS_NAME = "progress.log"


class _Progress:
    """Append progress lines to ``<out>/progress.log`` (and stdout)."""

    def __init__(self, out: Path, prefix: str) -> None:
        self.path = Path(out) / PROGRESS_NAME
        self.prefix = prefix

    def __call__(self, line: str) -> None:
        text = f"{self.prefix}: {line}"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
        print(text, flush=True)


class BadGeometry(ValueError):
    """``--dim 2`` without ``--geometry``, or a geometry id the device does not have."""


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


def mesh_source(device: str, dim: int = 1) -> str:
    """The repo-relative ``selected.json`` that the ``dim``-D results of ``device`` use."""
    return (meshconv.job_dir(meshconv.TREE_ROOT, device, dim) / meshconv.SELECTED_NAME).as_posix()


def geometry_of(device: str, gid: str) -> Geometry:
    """The SPICE geometry of ``device`` with the id ``gid`` (e.g. ``w10p0_l10p00``)."""
    found = [g for g in SPICE_DEVICES[device].geometries if geometry_id(g) == gid]
    if not found:
        ids = [geometry_id(g) for g in SPICE_DEVICES[device].geometries]
        raise BadGeometry(f"{device} has no geometry {gid!r}; known: {ids}")
    return found[0]


def run_job_2d(device: str, params: str, gid: str, out: Path) -> None:
    """``moscap-job --dim 2``: QS and 1 MHz AC sweeps of the 2D MOS capacitor into ``out``."""
    proc, calibration_sha256 = load_params(device, params)
    geometry = geometry_of(device, gid)
    mesh = meshconv.selected_spec(device, 2)
    vg = job_vg(proc)
    out = Path(out)
    qs = moscap2d.simulate(
        proc, geometry, vg=vg, with_sd=True, method="qs", mesh=mesh,
        mesh_file=out / moscap2d.MESH_FILE, log=_Progress(out, f"{device}/{params}/{gid}/qs"),
    )  # fmt: skip
    ac = moscap2d.simulate(
        proc, geometry, vg=vg[:: moscap2d.AC_STRIDE], with_sd=True, method="ac", mesh=mesh,
        freq_hz=moscap2d.AC_FREQ_HZ, mesh_file=out / "mesh_ac.msh",
        log=_Progress(out, f"{device}/{params}/{gid}/ac"),
    )  # fmt: skip
    if (out / "mesh_ac.msh").read_bytes() != (out / moscap2d.MESH_FILE).read_bytes():
        raise RuntimeError("the QS and AC sweeps were meshed differently")
    (out / "mesh_ac.msh").unlink()
    moscap2d.write(
        qs, ac, out, proc=proc, params=params, mesh_source=mesh_source(device, 2),
        calibration_sha256=calibration_sha256,
    )  # fmt: skip
    print(f"{device}/{params}/{gid}: {len(qs.vg)} points", flush=True)


def run_job(device: str, params: str, out: Path, dim: int = 1, gid: str | None = None) -> None:
    """``moscap-job``: simulate the MOS capacitor and write its files into ``out``."""
    if not sandbox.in_sandbox():
        raise RuntimeError("moscap-job must run inside the sandbox (see tools/sandbox-run)")
    if dim == 2:
        if gid is None:
            raise BadGeometry("moscap-job --dim 2 needs --geometry")
        run_job_2d(device, params, gid, out)
        return
    proc, calibration_sha256 = load_params(device, params)
    mesh = meshconv.selected_spec(device, 1)
    cv = moscap1d.simulate(proc, vg=job_vg(proc), method="qs", mesh=mesh)
    moscap1d.write(
        cv, Path(out), proc=proc, params=params, mesh_source=mesh_source(device),
        calibration_sha256=calibration_sha256,
    )  # fmt: skip
    print(f"{device}/{params}: {len(cv.vg)} points", flush=True)


def _copy_progress(scratch: Path, progress_log: Path | None) -> None:
    if progress_log is not None and (scratch / PROGRESS_NAME).is_file():
        shutil.copyfile(scratch / PROGRESS_NAME, progress_log)


def run_host(
    device: str,
    params: str,
    root: Path,
    dim: int = 1,
    gid: str | None = None,
    progress_log: Path | None = None,
) -> None:
    """``moscap``: run ``moscap-job`` in the TCAD image, then write the job dir and provenance."""
    if dim == 2:
        if gid is None:
            raise BadGeometry("moscap --dim 2 needs --geometry")
        geometry_of(device, gid)
    load_params(device, params)  # refuses a missing calibration before anything runs
    meshconv.selected_spec(device, dim)  # refuses a missing mesh-convergence result
    gplugins_commit()  # refuses a dirty or unpinned plugin before anything runs
    root = Path(root)
    scratch = Path(tempfile.mkdtemp(prefix=f"gf180tcad-moscap{dim}d-"))
    cmd = [
        "python3", "-m", "gf180tcad.tcad", "moscap-job", "--device", device, "--dim", str(dim),
        "--params", params, "--out", "/work/out",
    ]  # fmt: skip
    if dim == 2:
        cmd += ["--geometry", gid]
        print(f"{device}/{params}/{gid}: progress in {scratch / PROGRESS_NAME}", flush=True)
    mem = JOB_MEM if dim == 1 else JOB_MEM_2D
    try:
        res = sandbox.run(cmd, out_dir=scratch, image=TCAD_IMAGE, mem=mem, cpus=JOB_CPUS)
    except sandbox.SandboxError as e:
        _copy_progress(scratch, progress_log)
        log = scratch / "job.log"
        log.write_text(f"{e.result.stdout or ''}\n{e.result.stderr or ''}", encoding="utf-8")
        raise RuntimeError(f"moscap-job failed (exit {e.result.returncode}); log: {log}") from e
    _copy_progress(scratch, progress_log)
    # DEVSIM logs every Newton iteration; echo only the job's summary line.
    tag = f"{device}/{params}" + (f"/{gid}" if dim == 2 else "")
    summary = [ln for ln in res.stdout.splitlines() if ln.startswith(f"{tag}:")]
    print(summary[-1] if summary else f"{tag}: done", flush=True)
    if dim == 1:
        dest = root / device / params
        names = (moscap1d.PER_AREA_CSV, moscap1d.PER_AREA_META)
    else:
        dest = moscap2d.job_dir(root, device, params, geometry_of(device, gid))
        names = (moscap2d.CV_CSV, moscap2d.CGX_CSV, moscap2d.MESH_FILE, moscap2d.META_JSON)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in names:
        shutil.copyfile(scratch / name, dest / name)
    io.write_json(root / PROVENANCE_NAME, tree_provenance(root))
    shutil.rmtree(scratch)


# --- meshconv ---------------------------------------------------------------------------------


def run_meshconv_level(device: str, dim: int, level: int, out: Path) -> None:
    """``meshconv-job --level``: simulate refinement level ``level``, write :data:`LEVEL_NAME`."""
    log = _Progress(out, f"{device}/level{level}") if dim == 2 else None
    simulate, _ = meshconv.simulator(device, dim, log=log)
    if not sandbox.in_sandbox():
        raise RuntimeError("meshconv-job must run inside the sandbox (see tools/sandbox-run)")
    scale = meshconv.LEVELS[level]
    spec = meshconv.START[dim].scaled(scale)
    cv = simulate(spec)
    io.write_json(
        Path(out) / LEVEL_NAME,
        {
            "c_per_area_ff_um2": list(cv.c_per_area_ff_um2),
            "extended_fallback": list(getattr(cv, "extended_fallback", ())),
            "roundoff_accepted": [dict(r) for r in getattr(cv, "roundoff_accepted", ())],
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
        # a level written before the fallback existed converged everywhere in double precision
        self.extended_fallback = tuple(data.get("extended_fallback", ()))
        self.roundoff_accepted = tuple(data.get("roundoff_accepted", ()))


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
        spec = meshconv.START[dim].scaled(scale)
        if data["scale"] != scale or MeshSpec(**data["spec"]) != spec:
            raise RuntimeError(f"level{i}/{LEVEL_NAME} is not level {i} of the start spec")
        curves[spec] = _Curve(data)
    rep = meshconv.converge(curves.__getitem__, meshconv.START[dim], rel_tol=settings["rel_tol"])
    meshconv.write(rep, out, device=device, dim=dim, settings=settings)
    print(f"{device}: selected level {rep.selected}", flush=True)


def _sandbox_job(cmd: list[str], out_dir: Path, mem: str) -> str:
    try:
        res = sandbox.run(cmd, out_dir=out_dir, image=TCAD_IMAGE, mem=mem, cpus=JOB_CPUS)
    except sandbox.SandboxError as e:
        log = out_dir / "job.log"
        log.write_text(f"{e.result.stdout or ''}\n{e.result.stderr or ''}", encoding="utf-8")
        raise RuntimeError(f"{cmd[3]} failed (exit {e.result.returncode}); log: {log}") from e
    return res.stdout


def run_meshconv(
    device: str,
    dim: int,
    root: Path,
    jobs: int | None = None,
    progress_dir: Path | None = None,
    resume: Path | None = None,
) -> None:
    """``meshconv``: the level jobs and the report job in the TCAD image, then the tree files.

    ``progress_dir`` receives each level's progress log (``<device>_level<i>.log``) when it ends.
    ``resume`` is the scratch directory of an earlier, failed run: the levels that finished there
    (their ``level<i>/level.json``) are kept and only the others run again. A level job is
    deterministic, so a kept level is the one a rerun would give.
    """
    meshconv.check_dim(dim)
    mem = MESHCONV_JOB_MEM[dim]
    jobs = len(meshconv.LEVELS) if jobs is None else jobs
    meshconv.check_admission(jobs, mem)
    gplugins_commit()  # refuses a dirty or unpinned plugin before anything runs
    root = Path(root)
    scratch = (
        Path(resume) if resume is not None else Path(tempfile.mkdtemp(prefix="gf180tcad-meshconv-"))
    )
    base = ["python3", "-m", "gf180tcad.tcad", "meshconv-job", "--device", device,
            "--dim", str(dim), "--out", "/work/out"]  # fmt: skip

    def level(i: int) -> float:
        d = scratch / f"level{i}"
        if (d / LEVEL_NAME).is_file():
            print(f"{device}/level{i}: kept from {d}", flush=True)
            return 0.0
        if d.exists():
            shutil.rmtree(d)
        d.mkdir()
        if dim == 2:
            print(f"{device}/level{i}: progress in {d / PROGRESS_NAME}", flush=True)
        t = time.monotonic()
        try:
            _sandbox_job([*base, "--level", str(i)], d, mem)
        finally:
            if progress_dir is not None:
                _copy_progress(d, Path(progress_dir) / f"{device}_level{i}.log")
        return time.monotonic() - t

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        runtimes = list(pool.map(level, range(len(meshconv.LEVELS))))
    for i, t in enumerate(runtimes):
        print(f"{device}/level{i} (scale {meshconv.LEVELS[i]!r}): {t:.1f} s", flush=True)
    stdout = _sandbox_job([*base, "--assemble"], scratch, mem)
    summary = [ln for ln in stdout.splitlines() if ln.startswith(f"{device}: selected")]
    print(summary[-1] if summary else f"{device}: done", flush=True)
    dest = meshconv.job_dir(root, device, dim)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in (meshconv.REPORT_NAME, meshconv.SELECTED_NAME):
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
        p.add_argument("--geometry", default=None, help="2D: the SPICE geometry id")
        if name == "moscap":
            p.add_argument("--progress-log", type=Path, default=None)
    p = sub.add_parser(
        "meshconv", help="mesh convergence of a MOS capacitor (host: runs meshconv-job)"
    )
    p.add_argument("--device", choices=process.DEVICES, required=True)
    p.add_argument("--dim", type=int, choices=MESHCONV_DIMS, required=True)
    p.add_argument("--out", type=Path, required=True, help="tree root: results/tcad/meshconv")
    p.add_argument("--jobs", type=int, default=None, help="concurrent level jobs (default: all)")
    p.add_argument("--progress-dir", type=Path, default=None, help="copy level progress logs")
    p.add_argument("--resume", type=Path, default=None, help="scratch dir of a failed run")
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
            run_job(a.device, a.params, a.out, a.dim, a.geometry)
        elif a.command == "moscap":
            run_host(a.device, a.params, a.out, a.dim, a.geometry, a.progress_log)
        elif a.command == "meshconv-job" and a.assemble:
            run_meshconv_assemble(a.device, a.dim, a.out)
        elif a.command == "meshconv-job":
            run_meshconv_level(a.device, a.dim, a.level, a.out)
        else:
            run_meshconv(a.device, a.dim, a.out, a.jobs, a.progress_dir, a.resume)
    except (MissingCalibration, BadGeometry, meshconv.AdmissionError) as e:
        print(f"{a.command}: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
