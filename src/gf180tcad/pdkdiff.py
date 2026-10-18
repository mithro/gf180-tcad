# SPDX-License-Identifier: Apache-2.0
"""The secondary-PDK comparison: open_pdks ``d658698`` (wafer.space runs 1 and 2) vs the image.

``python -m gf180tcad.pdkdiff run --out <tree>`` (the committed tree is :data:`OUT_TREE`)
reruns the SPICE reference at the TT corner (``typical``) with ngspice for every geometry of
``nfet_05v0`` and ``pfet_05v0``, with the GF180MCU models of open_pdks commit ``d658698bd8bc`` instead of those of
the pinned image, and compares the result with the committed ``results/spice``. It runs on the
host and uses the base image (``docker/IMAGE``) through :func:`gf180tcad.sandbox.run`:

1. **Fetch**, in the sandbox *with* network (the only step that has it): ``ciel fetch`` of the
   ``gf180mcu`` family at that commit (only the ``gf180mcu_fd_pr`` library; the models are in
   ``common``), from Ciel's default public data source, into the run's scratch directory.
2. **Pin**, on the host: every model file listed in ``data/pdk-d658698.sha256`` is checked and
   copied into each job's workdir, and nothing else of the fetched tree.
3. **Jobs**, in the sandbox with no network, one container per geometry:
   ``python -m gf180tcad.pdkdiff job`` locates the copied PDK
   (:func:`gf180tcad.pdk.locate`), checks it against ``data/pdk-d658698.versions.json``
   (:func:`gf180tcad.pdk.check_against`) and against every pin, then calls
   :func:`gf180tcad.reference.run_job` unchanged, with its PDK lookup (``_image_pdk``, which
   accepts only the image's PDK) replaced by that PDK for the duration of the call. So every CSV
   and ``metrics.json`` is written by the generator's own code, in the generator's layout, and
   ``reference.py`` (a SPICE generator module, frozen by ``tests/test_results_provenance.py``)
   is not modified.
4. **Cards**, in the sandbox with no network: ``python -m gf180tcad.pdkdiff cards-job`` compares
   the two PDKs' model files (sha256), the ``.lib`` sections of ``sm141064.ngspice`` and
   ``sm141064.xyce``, and the values of a fixed list of card parameters (:data:`CARD_KEYS`),
   and writes unified diffs of the two libraries.
5. **Compare**, on the host: :func:`compare` of the new tree with ``results/spice``'s TT
   ngspice tree.

The tree is written only when every step succeeded; the scratch directory (outside the repo) is
then deleted, and kept and named on failure. Layout:
``<out>/ngspice/typical/<device>/<geometry_id>/`` as in ``results/spice``, plus
:data:`CARDS_NAME`, :data:`COMPARISON_NAME`, the two ``.diff`` files and ``provenance.json``
(:func:`provenance`). No result file holds a date, host name or host path.

In every comparison ``a`` is the d658698 PDK and ``b`` the image's (the latest), so a delta is
latest − d658698.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from gf180tcad import io, reference, sandbox
from gf180tcad.devices import DEVICES
from gf180tcad.layout import METRICS_NAME, PROVENANCE_NAME
from gf180tcad.pdk import PdkInfo, check_against, locate
from gf180tcad.reference import Job
from gf180tcad.spice import ngspice
from gf180tcad.tcad.process import eval_card_expr, parse_card_assignment

#: The expected PDK: variant, open_pdks commit, Ciel family and libraries, model-file sha256s.
VERSIONS = sandbox.REPO_ROOT / "data" / "pdk-d658698.versions.json"
#: sha256 of every fetched model file, ``<sha256>  <path under the Ciel version directory>``.
PINS = sandbox.REPO_ROOT / "data" / "pdk-d658698.sha256"
#: The committed result tree, relative to the repo.
OUT_TREE = Path("results") / "spice-pdk-d658698"
#: The committed reference tree it is compared with: results/spice at TT, ngspice.
REFERENCE_DIR = sandbox.REPO_ROOT / "results" / "spice" / "ngspice" / "typical"
#: The engine and corner rerun.
ENGINE = "ngspice"
#: The TT corner, as the reference names it.
CORNER = "typical"
#: Tree root: the card comparison (:func:`cards`).
CARDS_NAME = "cards.json"
#: Tree root: the metric comparison with the reference (:func:`compare`).
COMPARISON_NAME = "comparison.json"
#: The card models whose parameters :data:`CARD_KEYS` lists, each with its ``.lib`` section.
CARD_MODELS = {
    "nfet_06v0.0": "nfet_06v0_t",
    "nfet_06v0.1": "nfet_06v0_t",
    "pfet_06v0.0": "pfet_06v0_t",
}
#: The card parameters compared (design spec §4 and the process files' card values).
CARD_KEYS = (
    "toxe", "toxp", "epsrox", "ndep", "ngate", "nsd", "xj", "vth0", "k1", "k2", "lpe0", "u0",
    "vsat", "rdsw", "dlc", "cgso", "cgdo", "cgsl", "cgdl", "acde", "moin", "capmod", "igcmod",
    "igbmod", "alpha0", "beta0", "tnom", "lmin", "lmax",
)  # fmt: skip
#: The wrapper subcircuits of the two devices, compared as text.
SUBCKTS = ("nfet_05v0", "pfet_05v0")
_MOUNT_PDK = "/work/out/pdk"
_MOUNT_OUT = "/work/out/out"
_FETCH_MEM, _FETCH_CPUS = "4g", 2
_CARDS_MEM = "2g"
_PIN_LINE = re.compile(r"^([0-9a-f]{64})  (\S.*)$")


class PinMismatch(RuntimeError):
    """A PDK file is missing or differs from ``data/pdk-d658698.sha256``."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _versions(path: Path = VERSIONS) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --- plan ----------------------------------------------------------------------------------


def plan() -> list[Job]:
    """The jobs: :func:`gf180tcad.reference.plan_jobs` restricted to ngspice at TT."""
    return reference.plan_jobs((ENGINE,), (CORNER,), tuple(DEVICES))


# --- pins ----------------------------------------------------------------------------------


def load_pins(path: Path = PINS) -> dict[str, str]:
    """``{relpath: sha256}`` of a pins file (``<sha256>  <relpath>`` lines, as sha256sum).

    Raises ValueError on a malformed, absolute, ``..`` or duplicate path, or an empty file.
    """
    pins: dict[str, str] = {}
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").split("\n"), 1):
        if not line:
            continue
        m = _PIN_LINE.match(line)
        if not m:
            raise ValueError(f"{path}:{n}: malformed line {line!r}")
        digest, rel = m.groups()
        if rel.startswith("/") or ".." in rel.split("/"):
            raise ValueError(f"{path}:{n}: path must be relative, without '..': {rel!r}")
        if rel in pins:
            raise ValueError(f"{path}:{n}: duplicate entry for {rel!r}")
        pins[rel] = digest
    if not pins:
        raise ValueError(f"{path}: no files pinned")
    return pins


def pin_problems(root: Path, pins: Mapping[str, str]) -> list[str]:
    """One line per pinned file under ``root`` that is missing or has another sha256."""
    out = []
    for rel, want in sorted(pins.items()):
        p = Path(root) / rel
        if not p.is_file() or p.is_symlink():
            out.append(f"{rel}: missing (or not a regular file)")
        elif (got := _sha256(p)) != want:
            out.append(f"{rel}: sha256 {got}, pinned {want}")
    return out


def check_pins(root: Path, pins: Mapping[str, str]) -> None:
    """Raise :class:`PinMismatch` listing every :func:`pin_problems` line."""
    probs = pin_problems(root, pins)
    if probs:
        raise PinMismatch(f"PDK at {root} differs from the pins:\n  " + "\n  ".join(probs))


def copy_pinned(src: Path, dst: Path, pins: Mapping[str, str]) -> None:
    """Copy exactly the pinned files from ``src`` to ``dst``; check them before and after."""
    check_pins(src, pins)
    for rel in sorted(pins):
        (Path(dst) / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(src) / rel, Path(dst) / rel)
    check_pins(dst, pins)


# --- the in-image jobs ---------------------------------------------------------------------


def _checked_pdk(pdk_root: Path, versions: Path, pins: Path) -> PdkInfo:
    info = locate(pdk_root=pdk_root, variant=_versions(versions)["gf180mcu_variant"])
    check_against(info, versions)
    check_pins(pdk_root, load_pins(pins))
    return info


def run_pdk_job(
    job: Job, out: Path, pdk_root: Path, versions: Path = VERSIONS, pins: Path = PINS
) -> None:
    """Run :func:`gf180tcad.reference.run_job` for ``job`` with the PDK at ``pdk_root``.

    Inside the sandbox only. The PDK must match ``versions`` and every pin; the generator's PDK
    lookup is replaced by it for the duration of the call and restored afterwards.
    """
    if not sandbox.in_sandbox():
        raise RuntimeError("pdkdiff job must run inside the sandbox (see tools/sandbox-run)")
    info = _checked_pdk(Path(pdk_root), versions, pins)
    original = reference._image_pdk
    reference._image_pdk = lambda: info
    try:
        reference.run_job(job, Path(out))
    finally:
        reference._image_pdk = original


def lib_sections(text: str) -> dict[str, tuple[int, list[str]]]:
    """``{name: (first line number, lines)}`` of each ``.lib <name>`` … ``.endl`` section.

    Only section definitions count (a ``.lib '<file>' <name>`` call has two words). A repeated
    name gets the suffix ``#2``, ``#3``, ….
    """
    out: dict[str, tuple[int, list[str]]] = {}
    cur: str | None = None
    for n, line in enumerate(text.split("\n"), 1):
        words = line.split()
        if cur is None and len(words) == 2 and words[0].lower() == ".lib":
            name, k = words[1], 2
            while name in out:
                name, k = f"{words[1]}#{k}", k + 1
            cur = name
            out[cur] = (n, [line])
        elif cur is not None:
            out[cur][1].append(line)
            if words and words[0].lower() == ".endl":
                cur = None
    return out


def section_diff(a: str, b: str) -> dict:
    """Names of the ``.lib`` sections that differ between two libraries, in ``a``'s order."""
    sa, sb = lib_sections(a), lib_sections(b)
    changed = [n for n in sa if n in sb and sa[n][1] != sb[n][1]]
    return {
        "changed": changed,
        "only_in_a": [n for n in sa if n not in sb],
        "only_in_b": [n for n in sb if n not in sa],
        "same": sum(1 for n in sa if n in sb and sa[n][1] == sb[n][1]),
    }


def tt_params(text: str) -> dict[str, float]:
    """The numeric ``.param`` values of the library's ``.lib typical`` section."""
    out = {}
    for line in lib_sections(text)["typical"][1]:
        if line.lower().startswith(".param"):
            key, expr = parse_card_assignment(line)
            out[key] = float(expr)
    return out


def model_values(
    text: str, section: str, model: str, keys: Sequence[str], params: Mapping[str, float]
) -> dict[str, dict | None]:
    """``{key: {"expr", "line", "tt"} | None}`` of ``.model <model>`` in ``.lib <section>``.

    ``line`` is the 1-based line in the file, ``tt`` the expression evaluated with ``params``
    (:func:`gf180tcad.tcad.process.eval_card_expr`), or None where it is not a ``+``/``*``
    expression of numbers and parameters. A key the model does not set is None.
    """
    start, lines = lib_sections(text)[section]
    found: dict[str, dict] = {}
    inside = False
    for i, line in enumerate(lines):
        words = line.split()
        if words[:2] == [".model", model]:
            inside = True
            continue
        if inside:
            if not words or line.startswith("*"):
                continue  # blank and comment lines inside the parameter list
            if not line.startswith("+"):
                break
            key, expr = parse_card_assignment(line)
            try:
                tt = eval_card_expr(expr, params)
            except (ValueError, KeyError):
                tt = None
            found[key.lower()] = {"expr": expr, "line": start + i, "tt": tt}
    if not inside:
        raise ValueError(f".model {model} not found in .lib {section}")
    return {k: found.get(k) for k in keys}


def _subckt(text: str, name: str) -> list[str]:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.split()[:2] == [".subckt", name]:
            for j in range(i, len(lines)):
                if lines[j].split()[:1] == [".ends"]:
                    return lines[i : j + 1]
    raise ValueError(f".subckt {name} not found")


def _unified(a: str, b: str, name: str) -> str:
    return "".join(
        difflib.unified_diff(
            a.splitlines(keepends=True),
            b.splitlines(keepends=True),
            fromfile=f"d658698/{name}",
            tofile=f"latest/{name}",
        )
    )


def cards(a: Path, b: Path, pins: Mapping[str, str]) -> tuple[dict, dict[str, str]]:
    """The card comparison of PDK roots ``a`` (d658698) and ``b`` (the image), and the diffs.

    Returns ``(cards.json contents, {diff file name: unified diff})``.
    """
    files = {}
    for rel in sorted(pins):
        pa, pb = Path(a) / rel, Path(b) / rel
        sa, sb = _sha256(pa), (_sha256(pb) if pb.is_file() else None)
        files[rel] = {"a": sa, "b": sb, "same": sa == sb}
    variant = next(iter(sorted(pins))).split("/")[0]
    libs = {}
    diffs = {}
    for sub, name in (("ngspice", "sm141064.ngspice"), ("xyce", "sm141064.xyce")):
        rel = f"{variant}/libs.tech/{sub}/{name}"
        ta = (Path(a) / rel).read_text(encoding="utf-8")
        tb = (Path(b) / rel).read_text(encoding="utf-8")
        libs[name] = section_diff(ta, tb)
        diffs[f"{name}.diff"] = _unified(ta, tb, rel)
    rel = f"{variant}/libs.tech/ngspice/sm141064.ngspice"
    ta = (Path(a) / rel).read_text(encoding="utf-8")
    tb = (Path(b) / rel).read_text(encoding="utf-8")
    pa, pb = tt_params(ta), tt_params(tb)
    models = {}
    for model, section in CARD_MODELS.items():
        va = model_values(ta, section, model, CARD_KEYS, pa)
        vb = model_values(tb, section, model, CARD_KEYS, pb)
        models[model] = {
            k: {"a": va[k], "b": vb[k], "same": _same(va[k], vb[k])} for k in CARD_KEYS
        }
    subckts = {n: {"same": _subckt(ta, n) == _subckt(tb, n)} for n in SUBCKTS}
    tt = {
        "a": dict(sorted(pa.items())),
        "b": dict(sorted(pb.items())),
        "same": pa == pb,
    }
    return (
        {"files": files, "libraries": libs, "models": models, "subckts": subckts, "tt_params": tt},
        diffs,
    )


def _same(x: dict | None, y: dict | None) -> bool:
    if x is None or y is None:
        return x is y
    return x["expr"] == y["expr"] and x["tt"] == y["tt"]


def run_cards_job(old_root: Path, out: Path, versions: Path = VERSIONS, pins: Path = PINS) -> None:
    """In the sandbox: write :data:`CARDS_NAME` and the ``.diff`` files of the two PDKs.

    ``old_root`` is the copied d658698 PDK (checked as in :func:`run_pdk_job`); the image's PDK
    is ``$PDK_ROOT``, checked against ``docker/base/versions.json`` as the reference does.
    """
    if not sandbox.in_sandbox():
        raise RuntimeError("pdkdiff cards-job must run inside the sandbox (see tools/sandbox-run)")
    _checked_pdk(Path(old_root), versions, pins)
    image = locate()
    check_against(image, sandbox.REPO_ROOT / reference.VERSIONS)
    data, diffs = cards(Path(old_root), image.root, load_pins(pins))
    out = Path(out)
    io.write_json(out / CARDS_NAME, data)
    for name, text in diffs.items():
        (out / name).write_bytes(text.encode("utf-8"))


# --- compare -------------------------------------------------------------------------------


def _jobs_of(root: Path) -> dict[str, Path]:
    root = Path(root)
    found = {p.parent.relative_to(root).as_posix(): p.parent for p in root.rglob(METRICS_NAME)}
    if not found:
        raise ValueError(f"no {METRICS_NAME} under {root}")
    return found


def _files(d: Path) -> dict[str, str]:
    return {p.name: _sha256(p) for p in sorted(Path(d).iterdir()) if p.is_file()}


def compare(a_metrics_dir: Path, b_metrics_dir: Path) -> dict:
    """Per-metric differences of two trees of ``<device>/<geometry_id>/metrics.json``.

    For each job in both trees and each metric in both: ``a``, ``b``, ``delta`` = b − a and
    ``rel`` = delta / |a| (0.0 when both are equal, None when a = 0 and b ≠ 0), plus whether
    the job directories' files are byte-identical. ``max_abs_rel`` is, per metric, the largest
    |rel| over the jobs (None if any is undefined). ``identical`` is true only if both trees
    hold the same jobs and metrics and every file is byte-identical.
    """
    ja, jb = _jobs_of(a_metrics_dir), _jobs_of(b_metrics_dir)
    jobs: dict[str, dict] = {}
    worst: dict[str, float | None] = {}
    identical = ja.keys() == jb.keys()
    for rel in sorted(ja.keys() & jb.keys()):
        ma = json.loads((ja[rel] / METRICS_NAME).read_bytes())["metrics"]
        mb = json.loads((jb[rel] / METRICS_NAME).read_bytes())["metrics"]
        entry: dict = {"files_identical": _files(ja[rel]) == _files(jb[rel]), "metrics": {}}
        for name in sorted(ma.keys() & mb.keys()):
            x, y = float(ma[name]), float(mb[name])
            d = y - x
            r = 0.0 if d == 0 else (None if x == 0 else d / abs(x))
            entry["metrics"][name] = {"a": x, "b": y, "delta": d, "rel": r}
            if name not in worst or worst[name] is not None:
                worst[name] = None if r is None else max(worst.get(name) or 0.0, abs(r))
        if ma.keys() != mb.keys():
            entry["metrics_only_in_a"] = sorted(ma.keys() - mb.keys())
            entry["metrics_only_in_b"] = sorted(mb.keys() - ma.keys())
            identical = False
        identical = identical and entry["files_identical"]
        jobs[rel] = entry
    return {
        "identical": identical,
        "jobs": jobs,
        "max_abs_rel": dict(sorted(worst.items())),
        "only_in_a": sorted(ja.keys() - jb.keys()),
        "only_in_b": sorted(jb.keys() - ja.keys()),
    }


# --- provenance ----------------------------------------------------------------------------


def provenance(repo_root: Path | None = None) -> dict:
    """What produced the tree: the SPICE generator, this module, the image and both PDKs."""
    root = Path(repo_root) if repo_root is not None else sandbox.REPO_ROOT
    return {
        "generator_sha256": reference.generator_sha256(root),
        "image": (root / reference.IMAGE).read_text(encoding="utf-8").splitlines()[0].strip(),
        "image_versions": json.loads((root / reference.VERSIONS).read_text(encoding="utf-8")),
        "pdk": _versions(root / VERSIONS.relative_to(sandbox.REPO_ROOT)),
        "pdk_pins_sha256": _sha256(root / PINS.relative_to(sandbox.REPO_ROOT)),
        "pdkdiff_sha256": _sha256(root / "src" / "gf180tcad" / "pdkdiff.py"),
    }


# --- host orchestration --------------------------------------------------------------------


def fetch_cmd(commit: str, versions: Path = VERSIONS) -> list[str]:
    """``ciel fetch`` of ``commit`` into the workdir's ``pdk/``."""
    v = _versions(versions)
    libs = [a for lib in v["ciel_libraries"] for a in ("-l", lib)]
    return [
        "ciel", "fetch", "--pdk-root", _MOUNT_PDK, "--pdk-family", v["ciel_pdk_family"],
        *libs, commit,
    ]  # fmt: skip


def job_cmd(job: Job) -> list[str]:
    return [
        "python3", "-m", "gf180tcad.pdkdiff", "job", "--device", job.device,
        "--geometry", job.geometry, "--pdk-root", _MOUNT_PDK, "--out", _MOUNT_OUT,
    ]  # fmt: skip


def _cards_cmd() -> list[str]:
    return [
        "python3", "-m", "gf180tcad.pdkdiff", "cards-job", "--pdk-root", _MOUNT_PDK,
        "--out", _MOUNT_OUT,
    ]  # fmt: skip


def _log_result(scratch: Path, name: str, res) -> None:
    if res is not None and hasattr(res, "stdout"):
        text = f"--- stdout ---\n{res.stdout or ''}--- stderr ---\n{res.stderr or ''}"
        (scratch / f"{name}.log").write_text(text, encoding="utf-8")


def _sandboxed(sb, cmd, wd: Path, log_name: str, **kw):
    try:
        res = sb(cmd, out_dir=wd, **kw)
    except sandbox.SandboxError as e:
        _log_result(wd, log_name, e.result)
        raise
    _log_result(wd, log_name, res)
    return res


def run(
    out: Path,
    *,
    scratch_root: Path | None = None,
    jobs_n: int = reference.DEFAULT_JOBS,
    sb: Callable | None = sandbox.run,
    pins_file: Path = PINS,
    versions: Path = VERSIONS,
    reference_dir: Path = REFERENCE_DIR,
    commit: str | None = None,
    log: Callable[[str], None] = print,
) -> int:
    """Fetch, pin, run every job and the cards job, compare, and replace ``out``. 0 on success.

    On any failure ``out`` is left as it was, the scratch directory is kept and 1 is returned.
    """
    reference.check_admission(jobs_n, ngspice.MEM)
    if scratch_root is not None:
        Path(scratch_root).mkdir(parents=True, exist_ok=True)
        if Path(scratch_root).resolve().is_relative_to(sandbox.REPO_ROOT):
            raise ValueError(f"scratch directory must be outside the repo: {scratch_root}")
    scratch = Path(tempfile.mkdtemp(prefix="gf180tcad-pdkdiff-", dir=scratch_root))
    if scratch.resolve().is_relative_to(sandbox.REPO_ROOT):
        shutil.rmtree(scratch)
        raise ValueError(f"scratch directory must be outside the repo: {scratch}")
    commit = commit or _versions(versions)["open_pdks_commit"]
    pins = load_pins(pins_file)
    staging = scratch / "staging"
    t0 = time.monotonic()
    try:
        fetch = scratch / "fetch"
        fetch.mkdir()
        log(f"fetch: ciel {commit} (network on, this step only)")
        _sandboxed(
            sb, fetch_cmd(commit, versions), fetch, "fetch",
            mem=_FETCH_MEM, cpus=_FETCH_CPUS, network=True,
        )  # fmt: skip
        fetched = fetch / "pdk" / "ciel" / "gf180mcu" / "versions" / commit
        check_pins(fetched, pins)
        log(f"fetch: {len(pins)} pinned files match {pins_file.name}")

        def workdir(name: Path) -> Path:
            wd = scratch / "jobs" / name
            copy_pinned(fetched, wd / "pdk", pins)
            (wd / "out").mkdir(parents=True)
            return wd

        wd = workdir(Path("cards"))
        _sandboxed(sb, _cards_cmd(), wd, "job", mem=_CARDS_MEM, cpus=1, pids=reference.JOB_PIDS)
        staging.mkdir()
        for p in sorted((wd / "out").iterdir()):
            shutil.copyfile(p, staging / p.name)
        log("cards: ok")

        jobs = plan()

        def one(job: Job) -> tuple[Job, float, str | None]:
            t_job = time.monotonic()
            try:
                wd = workdir(job.relpath)
                _sandboxed(
                    sb, job_cmd(job), wd, "job",
                    mem=ngspice.MEM, cpus=reference.JOB_CPUS, pids=reference.JOB_PIDS,
                )  # fmt: skip
                names = reference.expected_files(job.engine)
                missing = [n for n in names if not (wd / "out" / n).is_file()]
                if missing:
                    raise RuntimeError(f"job finished without writing {missing}")
                dest = staging / job.relpath
                dest.mkdir(parents=True)
                for n in names:
                    shutil.copyfile(wd / "out" / n, dest / n)
                shutil.rmtree(wd)
                return job, time.monotonic() - t_job, None
            except Exception as e:  # noqa: BLE001 - every failure is reported, none is dropped
                return job, time.monotonic() - t_job, f"{type(e).__name__}: {e}"

        failures = []
        with ThreadPoolExecutor(jobs_n) as pool:
            futures = [pool.submit(one, j) for j in jobs]
            for done, fut in enumerate(as_completed(futures), 1):
                job, secs, err = fut.result()
                if err:
                    failures.append((job, err))
                el = time.monotonic() - t0
                log(
                    reference.progress_line(
                        done, len(jobs), el, job, "FAILED" if err else "ok", secs
                    )
                )
        if failures:
            for job, err in sorted(failures):
                log(f"  {job.relpath.as_posix()}: {err}")
            raise RuntimeError(f"{len(failures)} of {len(jobs)} jobs failed")
        cmp = compare(staging / ENGINE / CORNER, reference_dir)
        io.write_json(staging / COMPARISON_NAME, cmp)
        io.write_json(staging / PROVENANCE_NAME, provenance())
    except Exception as e:  # noqa: BLE001 - reported, out untouched, scratch kept
        log(f"FAILED: {type(e).__name__}: {e}")
        log(f"{out} was not changed; scratch kept at {scratch}")
        return 1
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(staging, out)
    shutil.rmtree(scratch)
    log(f"wrote {out} in {time.monotonic() - t0:.0f}s; identical to the reference: "
        f"{cmp['identical']}")  # fmt: skip
    return 0


# --- CLI -----------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m gf180tcad.pdkdiff")
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="fetch d658698, rerun TT ngspice, compare (host)")
    r.add_argument("--out", type=Path, required=True, help="result tree to replace")
    r.add_argument("--scratch", type=Path, help="parent of the scratch dir (outside the repo)")
    r.add_argument("--jobs", type=int, default=reference.DEFAULT_JOBS)
    c = sub.add_parser("compare", help="per-metric deltas of two metrics trees, as JSON")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    j = sub.add_parser("job", help="internal: one TT ngspice job with the d658698 PDK")
    j.add_argument("--device", choices=tuple(DEVICES), required=True)
    j.add_argument("--geometry", required=True)
    j.add_argument("--pdk-root", type=Path, required=True)
    j.add_argument("--out", type=Path, required=True)
    k = sub.add_parser("cards-job", help="internal: compare the two PDKs' model files")
    k.add_argument("--pdk-root", type=Path, required=True)
    k.add_argument("--out", type=Path, required=True)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    if a.command == "job":
        reference.geometry_of(a.device, a.geometry)
        run_pdk_job(Job(ENGINE, CORNER, a.device, a.geometry), a.out, a.pdk_root)
        return 0
    if a.command == "cards-job":
        run_cards_job(a.pdk_root, a.out)
        return 0
    if a.command == "compare":
        print(json.dumps(compare(a.a, a.b), sort_keys=True, indent=2, allow_nan=False))
        return 0
    return run(a.out, scratch_root=a.scratch, jobs_n=a.jobs, log=lambda s: print(s, flush=True))


if __name__ == "__main__":
    sys.exit(main())
