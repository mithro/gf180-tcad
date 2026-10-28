# SPDX-License-Identifier: Apache-2.0
"""``python -m gf180tcad.meshcut``: cut the reduced mesh artefact of a 2D job (issue #39).

Host commands:

- ``cut --job results/tcad/moscap2d/<device>/<params>/<gid> --out results/tcad/meshes/<image>
  --kx K --depth-um D [--cache URL|DIR] [--scratch DIR]`` reads the job's ``mesh_sha256`` from
  its ``cv.meta.json`` and pulls that mesh into the scratch directory with a
  ``tools/output-cache pull`` **subprocess** (:func:`pull`), so :mod:`gf180tcad.outcache` is in
  no generator's import closure (design spec §9.1). Then ``cut-job`` runs in the image that
  made the job (:func:`source_image`) through :func:`gf180tcad.sandbox.run` with no network
  and :data:`gf180tcad.meshcut.job.JOB_MEM`. The host installs the artefact into
  ``<out>/<device>/<params>/<gid>/`` and writes ``<out>/provenance.json``
  (:func:`gf180tcad.tcad.tree_provenance`, generator :data:`MESHCUT_MAIN`, image kind
  :data:`IMAGE_KIND`). It refuses an ``--out`` named after another image than the job's,
  and an artefact over :data:`gf180tcad.meshcut.MAX_BYTES` (:class:`OverBudget`), which
  it leaves in the scratch directory.
- ``regenerate --job ... [--cut --out ... --kx K --depth-um D] [--scratch DIR]`` runs
  ``regenerate-job`` with :data:`gf180tcad.meshcut.job.REGENERATE_MEM`, alone, like a 2D job.
  It prints the committed and the regenerated sha256. A regenerated mesh that matches is
  copied beside the job's ``cv.meta.json`` (git-ignored), where ``tools/output-cache push``
  finds it. With ``--cut`` the artefact is cut and installed only on a match.

In-image commands (inside the sandbox only): ``cut-job --job J --out /work/out --kx K
--depth-um D`` and ``regenerate-job --job J --out /work/out [--cut --kx K --depth-um D]``
(:mod:`gf180tcad.meshcut.job`). ``J`` is relative to the repository, which the sandbox mounts
read-only.

``--kx`` and ``--depth-um`` are the window rule's arguments
(:func:`gf180tcad.meshcut.window.rule_bounds`). They are required until Experiment M1 of the
renders plan fixes them as constants.

A sandbox workdir may not lie inside the repository (:func:`gf180tcad.sandbox.check_workdir`),
so the default scratch directory is a new temporary directory, as for the TCAD jobs.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from gf180tcad import io, meshcut, sandbox, tcad
from gf180tcad.layout import PROVENANCE_NAME
from gf180tcad.meshcut import artefact, job

MESHCUT_MAIN = "gf180tcad.meshcut.__main__"
"""This entry point: the generator of the ``results/tcad/meshes/<image>`` trees."""
IMAGE_KIND = "meshes"
"""The result kind under which a meshes tree's ``provenance.json`` records its image."""
OUTPUT_CACHE = sandbox.REPO_ROOT / "tools" / "output-cache"
"""The output cache's command line tool, run as a subprocess."""
JOB_CPUS = 1
"""CPUs of a sandbox job (the cut and the meshing are single-threaded)."""


class OverBudget(ValueError):
    """The artefact is larger than :data:`gf180tcad.meshcut.MAX_BYTES`."""


def source_image(job_dir: Path) -> str:
    """The TCAD image name that the 2D job ``job_dir`` (``<tree>/<device>/<params>/<gid>``) was
    made with: its tree root's recorded ``moscap2d`` image."""
    root = Path(job_dir).parents[2]
    return json.loads((root / PROVENANCE_NAME).read_bytes())["images"]["moscap2d"]["name"]


def pull(sha: str, dest: Path, cache: str | None = None) -> None:
    """Fetch the file ``sha`` from the output cache into ``dest`` with a ``tools/output-cache
    pull`` subprocess, unless ``dest`` already holds it. The tool checks the sha256."""
    dest = Path(dest)
    if dest.is_file() and job.sha256_file(dest) == sha:
        return
    cmd = [sys.executable, str(OUTPUT_CACHE), "pull", sha, "--out", str(dest)]
    if cache is not None:
        cmd += ["--cache", cache]
    if dest.exists():
        cmd.append("--force")
    subprocess.run(cmd, check=True, cwd=sandbox.REPO_ROOT)


def _job_arg(job_dir: Path) -> str:
    """``job_dir`` as the in-image command takes it: relative to the repository if inside."""
    p = Path(job_dir).resolve()
    try:
        return p.relative_to(sandbox.REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(p)


def _scratch(scratch: Path | None, prefix: str) -> Path:
    if scratch is None:
        return Path(tempfile.mkdtemp(prefix=prefix))
    scratch = Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    return scratch


def _check_out(job_dir: Path, out: Path) -> str:
    image = source_image(job_dir)
    if Path(out).name != image:
        raise ValueError(
            f"{job_dir} was made on the {image!r} image, so its artefact goes to "
            f"results/tcad/meshes/{image}, not {out}"
        )
    return image


def _sandbox(cmd: list[str], scratch: Path, image: str, mem: str) -> str:
    try:
        res = sandbox.run(cmd, out_dir=scratch, image=tcad.image_ref(image), mem=mem, cpus=JOB_CPUS)
    except sandbox.SandboxError as e:
        log = scratch / "job.log"
        log.write_text(f"{e.result.stdout or ''}\n{e.result.stderr or ''}", encoding="utf-8")
        raise RuntimeError(f"{cmd[3]} failed (exit {e.result.returncode}); log: {log}") from e
    return getattr(res, "stdout", "") or ""


def install(scratch: Path, out: Path, key: dict, image: str) -> Path:
    """Copy the artefact that a job wrote into ``scratch`` to ``<out>/<device>/<params>/<gid>``
    and write ``<out>/provenance.json``; refuse one over budget (:class:`OverBudget`)."""
    size = (Path(scratch) / meshcut.ARTEFACT).stat().st_size
    if size > meshcut.MAX_BYTES:
        raise OverBudget(
            f"{scratch / meshcut.ARTEFACT} is {size} bytes, over the budget of "
            f"{meshcut.MAX_BYTES} bytes (2 MB); kept in {scratch}, nothing installed"
        )
    artefact.read(scratch)  # the meta is complete and the npz is the meta's
    meta = artefact.read_meta(scratch)
    if {k: v for k, v in meta["job"].items() if k != "cv_meta_sha256"} != key:
        raise ValueError(f"{scratch}: the artefact is of {meta['job']}, not of {key}")
    out = Path(out)
    dest = out / key["device"] / key["params"] / key["geometry_id"]
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in (meshcut.ARTEFACT, meshcut.META):
        shutil.copyfile(Path(scratch) / name, dest / name)
    io.write_json(
        out / PROVENANCE_NAME,
        tcad.tree_provenance(out, {IMAGE_KIND: image}, generator=MESHCUT_MAIN),
    )
    return dest


def run_cut(
    job_dir: Path,
    out: Path,
    *,
    kx: float,
    depth_um: float,
    cache: str | None = None,
    scratch: Path | None = None,
    results_root: Path | None = None,
) -> Path:
    """``cut``: pull the job's mesh, run ``cut-job`` in the sandbox, install the artefact."""
    job_dir = Path(job_dir)
    image = _check_out(job_dir, out)
    key = job.job_key(job_dir, results_root)
    cv_meta, _ = job.load_job(job_dir)
    scratch = _scratch(scratch, "gf180tcad-meshcut-")
    pull(cv_meta["mesh_sha256"], scratch / job.MESH_NAME, cache)
    cmd = [
        "python3", "-m", "gf180tcad.meshcut", "cut-job", "--job", _job_arg(job_dir),
        "--out", "/work/out", "--kx", repr(float(kx)), "--depth-um", repr(float(depth_um)),
    ]  # fmt: skip
    _sandbox(cmd, scratch, image, job.JOB_MEM)
    dest = install(scratch, out, key, image)
    print(f"{key['device']}/{key['params']}/{key['geometry_id']}: {dest}", flush=True)
    return dest


def _report(scratch: Path) -> dict | None:
    path = Path(scratch) / job.REGENERATE_REPORT
    if not path.is_file():
        return None
    report = json.loads(path.read_bytes())
    print(f"committed mesh_sha256   {report['committed_mesh_sha256']}", flush=True)
    print(f"regenerated mesh_sha256 {report['regenerated_mesh_sha256']}", flush=True)
    return report


def run_regenerate(
    job_dir: Path,
    *,
    cut: bool = False,
    out: Path | None = None,
    kx: float | None = None,
    depth_um: float | None = None,
    scratch: Path | None = None,
    results_root: Path | None = None,
) -> dict:
    """``regenerate``: mesh the job again in the sandbox and compare its sha256 with the
    committed one; return the report. With ``cut``, install the artefact on a match."""
    job_dir = Path(job_dir)
    if cut and (out is None or kx is None or depth_um is None):
        raise ValueError("regenerate --cut needs --out, --kx and --depth-um")
    image = _check_out(job_dir, out) if cut else source_image(job_dir)
    key = job.job_key(job_dir, results_root)
    scratch = _scratch(scratch, "gf180tcad-meshcut-regenerate-")
    cmd = ["python3", "-m", "gf180tcad.meshcut", "regenerate-job", "--job", _job_arg(job_dir),
           "--out", "/work/out"]  # fmt: skip
    if cut:
        cmd += ["--cut", "--kx", repr(float(kx)), "--depth-um", repr(float(depth_um))]
    try:
        _sandbox(cmd, scratch, image, job.REGENERATE_MEM)
    finally:
        report = _report(scratch)  # printed also when --cut refused a mismatch
    if report is None:
        raise RuntimeError(f"regenerate-job wrote no {job.REGENERATE_REPORT} in {scratch}")
    if report["match"]:
        mesh = job_dir / job.MESH_NAME
        if not (mesh.is_file() and job.sha256_file(mesh) == report["committed_mesh_sha256"]):
            shutil.copyfile(scratch / job.MESH_NAME, mesh)
    if cut:
        install(scratch, out, key, image)
    return report


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m gf180tcad.meshcut")
    sub = ap.add_subparsers(dest="command", required=True)
    specs = (
        ("cut", "cut a 2D job's artefact (host: pulls the mesh, runs cut-job in the sandbox)"),
        ("regenerate", "mesh a 2D job again and compare (host: runs regenerate-job, 16 GiB)"),
        ("cut-job", "internal: cut the artefact, inside the sandbox"),
        ("regenerate-job", "internal: mesh the job again, inside the sandbox"),
    )
    for name, help_ in specs:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--job", type=Path, required=True,
                       help="the 2D job, e.g. results/tcad/moscap2d/nfet_05v0/start/w10p0_l0p60")  # fmt: skip
        cut_required = name in ("cut", "cut-job")
        p.add_argument("--out", type=Path, required=name != "regenerate",
                       help="results/tcad/meshes/<image> (host) or /work/out (in the sandbox)")  # fmt: skip
        p.add_argument("--kx", type=float, required=cut_required, default=None,
                       help="window: gate lengths added on each side of the gate")  # fmt: skip
        p.add_argument("--depth-um", type=float, required=cut_required, default=None,
                       help="window: depth below the silicon surface (um)")  # fmt: skip
        if name.startswith("regenerate"):
            p.add_argument("--cut", action="store_true", help="cut the artefact on a match")
        if name in ("cut", "regenerate"):
            p.add_argument("--scratch", type=Path, default=None, help="the job's scratch dir")
        if name == "cut":
            p.add_argument("--cache", default=None, help="output cache checkout dir or URL")
    return ap


def _repo_path(p: Path) -> Path:
    return p if p.is_absolute() else sandbox.REPO_ROOT / p


def main(argv: Sequence[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    try:
        if a.command == "cut":
            run_cut(a.job, a.out, kx=a.kx, depth_um=a.depth_um, cache=a.cache, scratch=a.scratch)
        elif a.command == "regenerate":
            run_regenerate(a.job, cut=a.cut, out=a.out, kx=a.kx, depth_um=a.depth_um,
                           scratch=a.scratch)  # fmt: skip
        elif a.command == "cut-job":
            job.run_cut_job(_repo_path(a.job), a.out, kx=a.kx, depth_um=a.depth_um)
        else:
            if a.cut and (a.kx is None or a.depth_um is None):
                raise ValueError("regenerate-job --cut needs --kx and --depth-um")
            job.run_regenerate_job(_repo_path(a.job), a.out, cut=a.cut, kx=a.kx,
                                   depth_um=a.depth_um)  # fmt: skip
    except (ValueError, FileNotFoundError) as e:
        print(f"{a.command}: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
