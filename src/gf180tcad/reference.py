# SPDX-License-Identifier: Apache-2.0
"""Generate the SPICE golden-reference dataset (``python -m gf180tcad spice-reference``).

One *job* is one engine x corner x device x geometry. Each job runs entirely inside the pinned
image as ``python -m gf180tcad spice-job ... --out /work/out`` (one sandbox container): it checks
the image's PDK against ``docker/base/versions.json``, runs every sweep the engine supports
through :func:`~gf180tcad.spice.ngspice.simulate` / :func:`~gf180tcad.spice.xyce.simulate_xyce`,
extracts the metrics with :func:`gf180tcad.metrics.extract_all` and writes ``<sweep>.csv``
(:func:`gf180tcad.io.write_csv`) and ``metrics.json`` (:func:`gf180tcad.io.write_json`). So every
published number is computed and formatted by the image's Python and numpy, never the host's.

The host side (:func:`generate`) only schedules the sandbox jobs and copies their finished files,
byte for byte, into ``--out``:

- Admission: ``--jobs`` x the per-job memory limit must fit the 128 GiB budget of
  ``gf180-tcad.slice`` (:func:`check_admission`); the per-job limit is the engine runner's
  ``MEM`` (4 GiB).
- Each job runs in its own scratch directory outside the repo (under ``$TMPDIR``). It is
  deleted when the job succeeds and kept, and named in the report, when it fails.
- Results are assembled in a staging directory next to ``--out`` and swapped into place only
  when every job succeeded; on any failure the staging directory is deleted, ``--out`` is left
  as it was and the command exits non-zero listing the failures.
- One progress line per finished job: done/total, jobs per minute and the ETA.

Layout: ``<out>/<engine>/<corner>/<device>/<geometry_id>/<sweep>.csv`` and ``metrics.json``,
plus ``<out>/envelope.json`` (:func:`gf180tcad.specwindow.envelope_tree`, the per-metric
min/max over the corners) and ``<out>/provenance.json`` (:func:`provenance`). Xyce has no cv
analysis, so Xyce job directories have no ``cv.csv`` and their ``metrics.json`` has no ``cgg_*``
keys.

Every result file is deterministic: CSV meta lines hold only engine, corner, device,
geometry_id, w_um, l_um, sweep, temp_c and units; ``provenance.json`` holds the contents of
``versions.json``, the pinned image reference (``docker/IMAGE``, with its digest) and
:func:`generator_sha256` (of the :data:`GENERATOR_MODULES` and ``tools/sandbox-run`` only),
and deliberately no git commit or date, so a regeneration anywhere gives the same bytes.
Generation never compares the engines; the ngspice/Xyce cross-check
(``docs/limitations/engine-cross-check.md``) is a separate test.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from gf180tcad import io, metrics, sandbox, specwindow
from gf180tcad.devices import CORNERS, DEVICES, SWEEPS, TEMPS_C, Geometry, Sweep, geometry_id
from gf180tcad.pdk import PdkInfo, check_against, locate
from gf180tcad.spice import ngspice, xyce
from gf180tcad.spice.ngspice import simulate
from gf180tcad.spice.xyce import simulate_xyce

ENGINES = ("ngspice", "xyce")
BUDGET_BYTES = 128 << 30  # gf180-tcad.slice MemoryMax
DEFAULT_JOBS = 8
JOB_CPUS = 1  # both runners are single-threaded
JOB_PIDS = max(ngspice.PIDS, xyce.PIDS)
METRICS_NAME = "metrics.json"
PROVENANCE_NAME = "provenance.json"
VERSIONS = Path("docker") / "base" / "versions.json"
IMAGE = Path("docker") / "IMAGE"
# Every gf180tcad module the generator imports (tests check this against the import graph of
# gf180tcad.reference and gf180tcad.__main__). Only these feed generator_sha256, so later code
# elsewhere under src/ (e.g. TCAD) does not change the SPICE provenance.
GENERATOR_MODULES = (
    "gf180tcad",
    "gf180tcad.__main__",
    "gf180tcad.devices",
    "gf180tcad.io",
    "gf180tcad.metrics",
    "gf180tcad.pdk",
    "gf180tcad.reference",
    "gf180tcad.sandbox",
    "gf180tcad.specwindow",
    "gf180tcad.spice",
    "gf180tcad.spice.common",
    "gf180tcad.spice.netlist",
    "gf180tcad.spice.ngspice",
    "gf180tcad.spice.rawfile",
    "gf180tcad.spice.xyce",
)
# Non-module files that also shape the results: tools/sandbox-run sets the container's thread
# environment (OMP/OPENBLAS/MKL_NUM_THREADS=1), its limits and the read-only source mount.
GENERATOR_EXTRA_FILES = ("tools/sandbox-run",)
_ENGINE_MEM = {"ngspice": ngspice.MEM, "xyce": xyce.MEM}
_DC_COLUMNS = ("vd", "vg", "vb", "id", "ig", "ib")
_CV_COLUMNS = ("vg", "cgg")
_UNITS = {"vd": "V", "vg": "V", "vb": "V", "id": "A", "ig": "A", "ib": "A", "cgg": "F"}
_MEM_RE = re.compile(r"^([0-9]+)([kmg])$", re.IGNORECASE)
_MEM_UNIT = {"k": 1 << 10, "m": 1 << 20, "g": 1 << 30}


class AdmissionError(ValueError):
    """The requested concurrency does not fit the memory budget."""


@dataclass(frozen=True, order=True)
class Job:
    engine: str
    corner: str
    device: str
    geometry: str  # geometry_id

    @property
    def relpath(self) -> Path:
        return Path(self.engine, self.corner, self.device, self.geometry)


@dataclass(frozen=True)
class Failure:
    job: Job
    error: str
    scratch: Path


# --- plan --------------------------------------------------------------------------------------


def engine_sweeps(engine: str) -> tuple[str, ...]:
    """Sweep names an engine runs, in ``SWEEPS`` order (Xyce: everything but cv)."""
    if engine not in ENGINES:
        raise ValueError(f"unknown engine {engine!r}")
    return tuple(s.name for s in SWEEPS if engine == "ngspice" or s.kind != "cv")


def expected_files(engine: str) -> tuple[str, ...]:
    """The files one job of ``engine`` publishes, sorted."""
    return tuple(sorted([f"{s}.csv" for s in engine_sweeps(engine)] + [METRICS_NAME]))


def geometry_of(device: str, gid: str) -> Geometry:
    if device not in DEVICES:
        raise ValueError(f"unknown device {device!r}")
    for g in DEVICES[device].geometries:
        if geometry_id(g) == gid:
            return g
    known = [geometry_id(g) for g in DEVICES[device].geometries]
    raise ValueError(f"unknown geometry {gid!r} for {device} (known: {known})")


def plan_jobs(engines: Iterable[str], corners: Iterable[str], devices: Iterable[str]) -> list[Job]:
    corners, devices = tuple(corners), tuple(devices)
    return sorted(
        Job(e, c, d, geometry_id(g))
        for e in engines
        for c in corners
        for d in devices
        for g in DEVICES[d].geometries
    )


def temp_c() -> float:
    """The single reference temperature (the result layout has no temperature level)."""
    if len(TEMPS_C) != 1:
        raise NotImplementedError(f"the reference layout supports one temperature, got {TEMPS_C}")
    return TEMPS_C[0]


# --- admission ---------------------------------------------------------------------------------


def parse_mem(text: str) -> int:
    """Bytes of a docker-style memory size such as ``4g``, ``512m`` or ``1024k``."""
    m = _MEM_RE.match(text)
    if not m or int(m.group(1)) <= 0:
        raise ValueError(f"memory size must be a positive integer with k, m or g, got {text!r}")
    return int(m.group(1)) * _MEM_UNIT[m.group(2).lower()]


def job_mem(engines: Iterable[str]) -> str:
    """The per-job memory limit: the largest ``MEM`` of the engines' runners."""
    return max((_ENGINE_MEM[e] for e in engines), key=parse_mem)


def check_admission(n: int, mem: str) -> None:
    """Raise :class:`AdmissionError` unless ``n`` >= 1 and ``n`` x ``mem`` <= 128 GiB."""
    if n < 1:
        raise AdmissionError(f"--jobs must be at least 1, got {n}")
    per = parse_mem(mem)
    if n * per > BUDGET_BYTES:
        raise AdmissionError(
            f"--jobs {n} x {mem} per job = {n * per / (1 << 30):g} GiB exceeds the 128 GiB "
            f"memory budget of gf180-tcad.slice; use --jobs {BUDGET_BYTES // per} or fewer"
        )


# --- provenance --------------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module_relpath(name: str, repo_root: Path | None = None) -> Path:
    """Repo-relative source file of module ``name`` (``__init__.py`` for a package)."""
    root = Path(repo_root) if repo_root is not None else sandbox.REPO_ROOT
    base = Path("src", *name.split("."))
    init = base / "__init__.py"
    return init if (root / init).is_file() else base.with_suffix(".py")


def generator_files(repo_root: Path | None = None) -> list[str]:
    """Repo-relative POSIX paths hashed by :func:`generator_sha256`, sorted by UTF-8 bytes.

    The files of :data:`GENERATOR_MODULES` plus :data:`GENERATOR_EXTRA_FILES`. A missing one
    raises FileNotFoundError.
    """
    root = Path(repo_root) if repo_root is not None else sandbox.REPO_ROOT
    files = []
    for name in GENERATOR_MODULES:
        rel = module_relpath(name, root)
        if not (root / rel).is_file():
            raise FileNotFoundError(f"generator module {name} not found: {root / rel}")
        files.append(rel.as_posix())
    for rel in GENERATOR_EXTRA_FILES:
        if not (root / rel).is_file():
            raise FileNotFoundError(f"generator file not found: {root / rel}")
        files.append(rel)
    return sorted(files, key=lambda s: s.encode())


def generator_sha256(repo_root: Path | None = None) -> str:
    """sha256 over the sorted ``(relpath, sha256)`` pairs of the :func:`generator_files`.

    The hashed text is one line ``<file sha256>  <relpath>\\n`` per file, relpath relative
    to the repo root in POSIX form, sorted by its UTF-8 bytes. It depends on file contents and
    paths only (not on mtimes, the checkout location or git), so it is the same in every clone.
    """
    root = Path(repo_root) if repo_root is not None else sandbox.REPO_ROOT
    lines = [f"{_sha256(root / r)}  {r}\n" for r in generator_files(root)]
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def provenance(repo_root: Path | None = None) -> dict:
    """``versions.json`` contents, the pinned image reference and :func:`generator_sha256`."""
    root = Path(repo_root) if repo_root is not None else sandbox.REPO_ROOT
    image = (root / IMAGE).read_text(encoding="utf-8").splitlines()[0].strip()
    return {
        "generator_sha256": generator_sha256(root),
        "image": image,
        "versions": json.loads((root / VERSIONS).read_text(encoding="utf-8")),
    }


# --- the in-image job --------------------------------------------------------------------------


def csv_meta(job: Job, g: Geometry, sweep: Sweep, temp: float) -> dict[str, str]:
    """The ``# key: value`` header of one result CSV: deterministic fields only."""
    cols = _CV_COLUMNS if sweep.kind == "cv" else _DC_COLUMNS
    return {
        "corner": job.corner,
        "device": job.device,
        "engine": job.engine,
        "geometry_id": job.geometry,
        "l_um": repr(float(g.l_um)),
        "sweep": sweep.name,
        "temp_c": repr(float(temp)),
        "units": " ".join(f"{c}={_UNITS[c]}" for c in cols),
        "w_um": repr(float(g.w_um)),
    }


def _image_pdk() -> PdkInfo:
    info = locate()
    check_against(info, sandbox.REPO_ROOT / VERSIONS)
    return info


def run_job(job: Job, out: Path) -> None:
    """Run one job's sweeps and metrics; write ``<sweep>.csv`` and ``metrics.json`` in ``out``.

    Must run inside the sandbox (``spice-job``): the simulators then run in this container, and
    the numbers are computed by the image's Python. Simulator working directories are
    ``out/work/<sweep>/``; they are not published.
    """
    if not sandbox.in_sandbox():
        raise RuntimeError("spice-job must run inside the sandbox (see tools/sandbox-run)")
    out = Path(out)
    device = DEVICES[job.device]
    g = geometry_of(job.device, job.geometry)
    temp = temp_c()
    pdk = _image_pdk()
    sim = simulate if job.engine == "ngspice" else simulate_xyce
    sweeps = {s.name: s for s in SWEEPS}
    data = {}
    for name in engine_sweeps(job.engine):
        sweep = sweeps[name]
        work = out / "work" / name
        work.mkdir(parents=True)
        res = sim(device, g, sweep, job.corner, temp, pdk, work)
        meta = csv_meta(job, g, sweep, temp)
        want = _CV_COLUMNS if sweep.kind == "cv" else _DC_COLUMNS
        if tuple(res) != want:
            raise RuntimeError(f"{name}: columns {tuple(res)}, expected {want}")
        io.write_csv(out / f"{name}.csv", res, meta)
        data[name] = res
        nwarn = len(getattr(res, "warnings", ()))
        print(f"{job.relpath.as_posix()} {name}: {len(res['vg'])} points, {nwarn} warnings")
    result = {
        "corner": job.corner,
        "device": job.device,
        "engine": job.engine,
        "geometry_id": job.geometry,
        "l_um": float(g.l_um),
        "metrics": metrics.extract_all(device, g, data),
        "temp_c": float(temp),
        "w_um": float(g.w_um),
    }
    io.write_json(out / METRICS_NAME, result)


# --- host orchestration ------------------------------------------------------------------------


def run_job_sandboxed(job: Job, scratch: Path, mem: str) -> None:
    """Run ``spice-job`` for ``job`` in one sandbox container with ``scratch`` as /work/out.

    The job's stdout and stderr are saved in ``scratch/job.log`` (kept when the job fails).
    """
    cmd = [
        "python3", "-m", "gf180tcad", "spice-job",
        "--engine", job.engine, "--corner", job.corner, "--device", job.device,
        "--geometry", job.geometry, "--out", "/work/out",
    ]  # fmt: skip
    try:
        res = sandbox.run(cmd, out_dir=scratch, mem=mem, cpus=JOB_CPUS, pids=JOB_PIDS)
    except sandbox.SandboxNotConfined:
        raise  # no process ran, so there is no result to log; keep the real message
    except sandbox.SandboxError as e:
        _save_log(scratch, e.result.stdout, e.result.stderr)
        tail = "\n".join((e.result.stderr or "").rstrip("\n").splitlines()[-30:])
        raise RuntimeError(f"spice-job exited with status {e.result.returncode}\n{tail}") from e
    _save_log(scratch, res.stdout, res.stderr)


def _save_log(scratch: Path, stdout: str | None, stderr: str | None) -> None:
    text = f"--- stdout ---\n{stdout or ''}--- stderr ---\n{stderr or ''}"
    (Path(scratch) / "job.log").write_text(text, encoding="utf-8")


def progress_line(
    done: int,
    total: int,
    elapsed: float,
    job: Job,
    status: str,
    secs: float,
    *,
    now: float | None = None,
) -> str:
    """``[done/total] status relpath secs | elapsed, jobs/min, ETA (clock time)``."""
    now = time.time() if now is None else now
    rate = done / elapsed * 60 if elapsed > 0 else 0.0
    eta = elapsed / done * (total - done) if done else 0.0
    at = time.strftime("%H:%M:%S", time.localtime(now + eta))
    return (
        f"[{done}/{total}] {status} {job.relpath.as_posix()} {secs:.1f}s | elapsed "
        f"{elapsed:.0f}s, {rate:.1f} jobs/min, ETA {eta:.0f}s (at {at})"
    )


def generate(
    jobs: Sequence[Job],
    out: Path,
    *,
    jobs_n: int = DEFAULT_JOBS,
    mem: str = ngspice.MEM,
    runner: Callable[[Job, Path, str], None] = run_job_sandboxed,
    scratch_root: Path | None = None,
    repo_root: Path | None = None,
    log: Callable[[str], None] = print,
) -> list[Failure]:
    """Run ``jobs`` (at most ``jobs_n`` at a time) and publish them as ``out``.

    Returns the failures (empty on success). ``out`` is replaced only if every job succeeded;
    otherwise it is untouched and the failed jobs' scratch directories are kept.
    """
    check_admission(jobs_n, mem)
    out = Path(out).absolute()
    _check_replaceable(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="gf180tcad-spice-reference-", dir=scratch_root))
    if run_dir.resolve().is_relative_to(sandbox.REPO_ROOT):
        shutil.rmtree(run_dir)
        raise ValueError(f"scratch directory must be outside the repo: {run_dir}")
    staging = Path(tempfile.mkdtemp(prefix=f".{out.name}.staging-", dir=out.parent))
    lock = threading.Lock()

    def one(job: Job) -> tuple[Job, float, Failure | None]:
        scratch = run_dir / job.relpath
        scratch.mkdir(parents=True)
        t0 = time.monotonic()
        try:
            runner(job, scratch, mem)
            names = expected_files(job.engine)
            missing = [n for n in names if not (scratch / n).is_file()]
            if missing:
                raise RuntimeError(f"job finished without writing {missing}")
            dest = staging / job.relpath
            with lock:
                dest.mkdir(parents=True)
            for n in names:
                shutil.copyfile(scratch / n, dest / n)
            shutil.rmtree(scratch)
            return job, time.monotonic() - t0, None
        except Exception as e:  # noqa: BLE001 - every failure is reported, none is dropped
            return job, time.monotonic() - t0, Failure(job, f"{type(e).__name__}: {e}", scratch)

    failures: list[Failure] = []
    t_start = time.monotonic()
    try:
        pool = ThreadPoolExecutor(jobs_n)
        try:
            futures = [pool.submit(one, j) for j in jobs]
            for done, fut in enumerate(as_completed(futures), 1):
                job, secs, fail = fut.result()
                if fail:
                    failures.append(fail)
                status = "FAILED" if fail else "ok"
                el = time.monotonic() - t_start
                log(progress_line(done, len(jobs), el, job, status, secs))
        except BaseException:
            # Ctrl-C (or any error here): drop the queued jobs, let the running ones end (their
            # containers get the same SIGINT from the terminal), then clean up and re-raise.
            pool.shutdown(wait=True, cancel_futures=True)
            log(f"interrupted; {out} was not changed; scratch dirs are under {run_dir}")
            raise
        pool.shutdown(wait=True)
        if failures:
            failures.sort(key=lambda f: f.job)
            log(f"{len(failures)} of {len(jobs)} jobs FAILED; {out} was not changed:")
            for f in failures:
                log(f"  {f.job.relpath.as_posix()}: scratch kept at {f.scratch}")
                for line in f.error.splitlines():
                    log(f"    {line}")
            return failures
        # Corner envelope (pure min/max of the staged, published floats): written here so the
        # atomic swap never drops it and `make reproduce` regenerates it.
        specwindow.write_envelope(staging)
        skipped = specwindow.incomplete(staging)
        if skipped:
            log(
                f"envelope: {len(skipped)} incomplete (engine, device, geometry) entries "
                f"omitted: fewer than the {len(CORNERS)} corners present"
            )
        io.write_json(staging / PROVENANCE_NAME, provenance(repo_root))
        _swap(staging, out)
        shutil.rmtree(run_dir)
        log(f"{len(jobs)} jobs ok in {time.monotonic() - t_start:.1f}s; wrote {out}")
        return []
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _check_replaceable(out: Path) -> None:
    """``out`` must be absent, an empty directory or an earlier reference tree."""
    if out.is_symlink() or (out.exists() and not out.is_dir()):
        raise ValueError(f"--out {out} exists and is not a directory")
    if out.is_dir() and any(out.iterdir()) and not (out / PROVENANCE_NAME).is_file():
        raise ValueError(
            f"--out {out} is a non-empty directory without {PROVENANCE_NAME}, so it is not an "
            "earlier reference tree; refusing to replace it"
        )


_AT_FDCWD = -100
_RENAME_EXCHANGE = 2  # linux/fs.h


def _exchange(a: Path, b: Path) -> bool:
    """Atomically exchange two paths with renameat2(RENAME_EXCHANGE).

    Returns False (nothing changed) if the kernel, libc or filesystem does not support it;
    raises OSError on any other failure (nothing changed either).
    """
    fn = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if fn is None:
        return False
    rc = fn(_AT_FDCWD, os.fsencode(a), _AT_FDCWD, os.fsencode(b), _RENAME_EXCHANGE)
    if rc == 0:
        return True
    err = ctypes.get_errno()
    if err in (errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP):
        return False
    raise OSError(err, os.strerror(err), str(a), None, str(b))


def _swap(staging: Path, out: Path) -> None:
    """Replace ``out`` by the complete ``staging`` tree (both in the same directory).

    If ``out`` exists the two are exchanged atomically, so ``out`` is never missing, even if
    the process is killed; the old tree (now at ``staging``) is then deleted. Where the
    exchange is unsupported, ``out`` is renamed aside and ``staging`` renamed into place; if
    that second rename fails, the old tree is renamed back before the error is re-raised.
    """
    if not out.exists():
        os.rename(staging, out)
        return
    if _exchange(staging, out):
        shutil.rmtree(staging)
        return
    old = Path(tempfile.mkdtemp(prefix=f".{out.name}.old-", dir=out.parent))
    os.rename(out, old / out.name)
    try:
        os.rename(staging, out)
    except BaseException:
        os.rename(old / out.name, out)
        old.rmdir()
        raise
    shutil.rmtree(old)


# --- CLI ---------------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m gf180tcad")
    sub = ap.add_subparsers(dest="command", required=True)
    ref = sub.add_parser(
        "spice-reference",
        help="generate the SPICE reference dataset (sandboxed jobs)",
        description="Generate the SPICE golden-reference dataset; see gf180tcad.reference.",
    )
    ref.add_argument("--engine", choices=[*ENGINES, "both"], default="both")
    ref.add_argument(
        "--corner", action="append", choices=CORNERS, help="repeatable; default: all corners"
    )
    ref.add_argument(
        "--device", action="append", choices=tuple(DEVICES), help="repeatable; default: all"
    )
    ref.add_argument(
        "--jobs", type=int, default=DEFAULT_JOBS, help="concurrent jobs (N x 4 GiB <= 128 GiB)"
    )
    ref.add_argument("--out", type=Path, required=True, help="results directory to replace")
    job = sub.add_parser("spice-job", help="internal: one reference job, inside the sandbox")
    job.add_argument("--engine", choices=ENGINES, required=True)
    job.add_argument("--corner", choices=CORNERS, required=True)
    job.add_argument("--device", choices=tuple(DEVICES), required=True)
    job.add_argument("--geometry", required=True, help="geometry_id, e.g. w10p0_l0p60")
    job.add_argument("--out", type=Path, required=True)
    return ap


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    ap = _parser()
    a = ap.parse_args(argv)
    if a.command == "spice-reference":
        a.engines = ENGINES if a.engine == "both" else (a.engine,)
        a.corners = tuple(c for c in CORNERS if c in set(a.corner or CORNERS))
        a.devices = tuple(d for d in DEVICES if d in set(a.device or DEVICES))
    else:
        try:
            geometry_of(a.device, a.geometry)
        except ValueError as e:
            ap.error(str(e))
        a.job = Job(a.engine, a.corner, a.device, a.geometry)
    return a


def main(argv: Sequence[str] | None = None) -> int:
    a = parse_args(argv)
    if a.command == "spice-job":
        run_job(a.job, a.out)
        return 0
    mem = job_mem(a.engines)
    try:
        check_admission(a.jobs, mem)
    except AdmissionError as e:
        print(f"spice-reference: {e}", file=sys.stderr)
        return 2
    jobs = plan_jobs(a.engines, a.corners, a.devices)
    print(f"{len(jobs)} jobs, {a.jobs} concurrent, {mem} per job, into {a.out}", flush=True)
    failures = generate(jobs, a.out, jobs_n=a.jobs, mem=mem, log=lambda s: print(s, flush=True))
    return 1 if failures else 0
