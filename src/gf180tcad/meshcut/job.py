# SPDX-License-Identifier: Apache-2.0
"""The reduced mesh artefact's jobs, which run in the TCAD image (``cut-job``, ``regenerate-job``).

``cut-job`` (:func:`run_cut_job`) reads a 2D job's committed ``cv.meta.json`` from the
read-only repository and the full mesh that the host pulled into ``/work/out/mesh.msh``. In
order:

1. It refuses the mesh unless its sha256 is the job's committed ``mesh_sha256``
   (:class:`MeshShaMismatch`), before reading it.
2. It rebuilds the job's cross-section (:func:`cross_section`): the process description and
   geometry of the job (:func:`load_params`, which refuses parameters whose ``param_sha256``
   is not the job's), then :func:`gf180tcad.tcad.stack.build` of the PDK cell, as the 2D job
   built it. :func:`check_cross_section` refuses one whose L, oxide, source/drain peak or
   ``with_sd`` differ from the job's.
3. It checks that the mesh's ``gate_poly`` region spans the cross-section's gate
   (:func:`check_gate`), cuts the window of the rule (:func:`gate_window`,
   :func:`gf180tcad.meshcut.window.cut`) and evaluates the job's net doping at every window
   node (:func:`net_doping`).
4. It writes the artefact and its meta (:func:`gf180tcad.meshcut.artefact.write`) into
   ``/work/out``.

``regenerate-job`` (:func:`run_regenerate_job`) meshes the job's cross-section again with the
job's own mesh spec (:func:`gf180tcad.tcad.moscap2d.build_device`, which also solves the
equilibrium; the device is deleted at once), writes :data:`REGENERATE_REPORT` with both sha256s,
and with ``cut`` cuts the artefact only if the regenerated mesh is the committed one.

**The doping frames.** :func:`doping_frames` repeats the ``surfaces`` table of
:func:`gf180tcad.tcad.moscap2d.build_device`: the body's depth is measured down from the silicon
surface, the poly's up from the poly bottom. A test ties the two texts together. Each
profile is bound to its region's bounds in the full mesh, as
``gplugins.devsim.doping.assign_doping`` binds it with ``region_bounds``, and is evaluated
with its numpy form, the one the plugin documents for a backend other than DEVSIM.

This module imports :mod:`gf180tcad.tcad.stack` and :mod:`gf180tcad.tcad.moscap2d`, which load
gdsfactory, gf180mcu and the plugin lazily, so it imports on the host; :func:`cross_section`
and the regeneration need the TCAD image.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

import numpy as np

from gf180tcad import io, meshcut, sandbox
from gf180tcad.meshcut import artefact, msh, window
from gf180tcad.tcad import __main__ as tcad_cli
from gf180tcad.tcad import moscap2d, stack
from gf180tcad.tcad.calibration import param_sha256
from gf180tcad.tcad.mesh import MeshSpec
from gf180tcad.tcad.moscap1d import tunable_origins

JOB_MEM = "4g"
"""Memory of a ``cut-job`` sandbox run (renders plan: 4 GiB until Experiment M1 measures it)."""
REGENERATE_MEM = "16g"
"""Memory of a ``regenerate-job`` sandbox run: it meshes and solves like a 2D job."""
MESH_NAME = "mesh.msh"
"""The full mesh's file name in the job's ``/work/out``."""
REGENERATE_REPORT = "regenerate.json"
"""The file in which ``regenerate-job`` records the committed and the regenerated sha256."""
SOURCE_TREES = ("tcad/moscap2d",)
"""The committed trees whose 2D jobs record a ``mesh_sha256`` an artefact can be cut for."""


class MeshShaMismatch(ValueError):
    """The full mesh's sha256 is not the job's committed ``mesh_sha256``."""


class JobMismatch(ValueError):
    """The rebuilt cross-section, its parameters or the mesh's gate are not the job's."""


def sha256_file(path: Path) -> str:
    """The sha256 of the file at ``path``."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_mesh_sha(path: Path, expected: str) -> None:
    """Raise :class:`MeshShaMismatch` unless the file at ``path`` has the sha256 ``expected``."""
    got = sha256_file(path)
    if got != expected:
        raise MeshShaMismatch(
            f"{path}: sha256 {got}, but the job's committed mesh_sha256 is {expected}"
        )


def job_key(job_dir: Path, results_root: Path | None = None) -> dict[str, str]:
    """``tree``, ``device``, ``params`` and ``geometry_id`` of the 2D job ``job_dir``, from its
    path relative to ``results_root`` (default: the repository's ``results/``)."""
    results_root = Path(results_root) if results_root is not None else sandbox.REPO_ROOT / "results"
    try:
        rel = Path(job_dir).resolve().relative_to(Path(results_root).resolve())
    except ValueError:
        raise ValueError(f"{job_dir} is not a job directory under {results_root}") from None
    *tree, device, params, gid = rel.parts
    tree = "/".join(tree)
    if tree not in SOURCE_TREES:
        raise ValueError(
            f"{job_dir}: the job's tree is {tree!r}; artefacts are cut for the 2D jobs of "
            f"{list(SOURCE_TREES)}"
        )
    return {"device": device, "geometry_id": gid, "params": params, "tree": tree}


def load_job(job_dir: Path) -> tuple[dict, str]:
    """The committed ``cv.meta.json`` of the 2D job ``job_dir`` and its sha256."""
    path = Path(job_dir) / moscap2d.META_JSON
    return json.loads(path.read_bytes()), sha256_file(path)


def load_params(job_dir: Path, cv_meta: dict):
    """``(proc, geometry)`` of the 2D job ``job_dir``: its device's process description with
    the job's tunable values, and its SPICE geometry, as ``moscap-job --dim 2`` loads them.

    Raises :class:`JobMismatch` unless the values give the job's committed ``param_sha256``
    and the geometry is the job's.
    """
    device, params, gid = cv_meta["device"], cv_meta["params"], Path(job_dir).name
    proc, calibration_sha256 = tcad_cli.load_params(device, params)
    origins = tunable_origins(proc, params, calibration_sha256)
    got = param_sha256({n: o["value"] for n, o in origins.items()})
    if got != cv_meta["param_sha256"]:
        raise JobMismatch(
            f"{job_dir}: today's {params} values of {device} give param_sha256 {got}, the job "
            f"recorded {cv_meta['param_sha256']}"
        )
    geometry = tcad_cli.geometry_of(device, gid)
    if asdict(geometry) != cv_meta["geometry"]:
        raise JobMismatch(
            f"{job_dir}: geometry {asdict(geometry)}, the job recorded {cv_meta['geometry']}"
        )
    return proc, geometry


def check_cross_section(xs, cv_meta: dict) -> None:
    """Raise :class:`JobMismatch` unless ``xs`` has the job's drawn L, oxide thickness,
    source/drain peak and ``with_sd`` (exactly: the same floats)."""
    for field in ("l_um", "t_ox_nm", "sd_peak_cm3", "with_sd"):
        if getattr(xs, field) != cv_meta[field]:
            raise JobMismatch(
                f"the rebuilt cross-section has {field} = {getattr(xs, field)!r}, the job "
                f"recorded {cv_meta[field]!r}"
            )


def cross_section(job_dir: Path, cv_meta: dict):
    """The 2D job's cross-section, rebuilt from the PDK cell as the job built it (in the TCAD
    image: it needs gdsfactory and gf180mcu)."""
    proc, geometry = load_params(job_dir, cv_meta)
    xs = stack.build(proc, stack.cell(proc.device, geometry), with_sd=cv_meta["with_sd"])
    check_cross_section(xs, cv_meta)
    return xs


def doping_frames(xs) -> dict[str, tuple[float, int]]:
    """Per silicon region, ``(surface_um, depth_sign)`` of its doping frame: the ``surfaces``
    of :func:`gf180tcad.tcad.moscap2d.build_device`."""
    return {stack.BODY: (0.0, -1), stack.POLY: (xs.t_ox_nm * 1e-3, 1)}


def _poly_top_um(xs) -> float:
    _, zmin, thickness, _ = xs.levels[stack.POLY]
    return zmin + thickness


def gate_window(xs, *, kx: float, depth_um: float):
    """``(x_um, y_um, rule)``: the window of the rule around the gate of ``xs``, and the
    arguments that set it. The silicon surface is at y = 0 (:mod:`gf180tcad.tcad.stack`)."""
    rule = {
        "depth_um": depth_um,
        "gate_x_um": tuple(xs.gate_u),
        "kx": kx,
        "poly_top_um": _poly_top_um(xs),
        "surface_um": 0.0,
    }
    x_um, y_um = window.rule_bounds(**rule)
    return x_um, y_um, rule


def _region_nodes(mesh: msh.Mesh, region: str) -> np.ndarray:
    tags = [t for (d, t), name in mesh.names.items() if d == 2 and name == region]
    if len(tags) != 1:
        raise JobMismatch(f"the mesh has {len(tags)} regions named {region!r}, expected one")
    return np.unique(mesh.triangles[mesh.triangle_tag == tags[0]])


def check_gate(mesh: msh.Mesh, xs) -> None:
    """Raise :class:`JobMismatch` unless the mesh's ``gate_poly`` region spans the gate of
    ``xs`` in x and the poly level in y, within :data:`gf180tcad.tcad.stack.POINT_TOLERANCE_UM`
    (as :func:`gf180tcad.tcad.moscap2d.check_geometry` checks the meshed device)."""
    nodes = mesh.nodes[_region_nodes(mesh, stack.POLY)] * meshcut.UM_PER_MSH_UNIT
    _, zmin, thickness, _ = xs.levels[stack.POLY]
    want = ((xs.gate_u[0], xs.gate_u[1]), (zmin, zmin + thickness))
    got = ((nodes[:, 0].min(), nodes[:, 0].max()), (nodes[:, 1].min(), nodes[:, 1].max()))
    tol = stack.POINT_TOLERANCE_UM
    if abs(zmin - xs.t_ox_nm * 1e-3) > tol:
        raise JobMismatch(
            f"the cross-section's {stack.POLY} level starts at y = {zmin!r} um, not at its oxide "
            f"top {xs.t_ox_nm * 1e-3!r} um"
        )
    if any(
        abs(g - w) > tol
        for gp, wp in zip(got, want, strict=True)
        for g, w in zip(gp, wp, strict=True)
    ):
        raise JobMismatch(
            f"the mesh's {stack.POLY} spans x, y = {got} um, the cross-section's gate {want} um"
        )


def _total(profiles, x_range, y_range, x_um, depth_um) -> np.ndarray:
    out = np.zeros(len(x_um))
    for p in profiles:
        out = out + p.open_edges(x_range, y_range)(x_um, depth_um)
    return out


def net_doping(mesh: msh.Mesh, win: window.Window, xs) -> np.ndarray:
    """The job's net doping (cm^-3) at each node of ``win``: :data:`artefact.NET_DOPING`.

    A node of a silicon region gets that region's Donors - Acceptors at its position in the
    region's frame (:func:`doping_frames`), each profile bound to the region's bounds over
    all its nodes in the full ``mesh``. A node of no silicon region gets 0. The silicon
    regions of a cross-section (body, poly) share no node; one that did is refused.
    """
    um = meshcut.UM_PER_MSH_UNIT
    full_index = np.searchsorted(mesh.node_id, win.node_id)
    out = np.zeros(len(win.node_id), dtype=np.float64)
    done = np.zeros(len(win.node_id), dtype=bool)
    for region, (donors, acceptors) in sorted(xs.doping.items()):
        surface_um, sign = doping_frames(xs)[region]
        nodes = _region_nodes(mesh, region)
        lateral = mesh.nodes[nodes, 0] * um
        depth = sign * (mesh.nodes[nodes, 1] * um - surface_um)
        x_range = (float(lateral.min()), float(lateral.max()))
        y_range = (float(depth.min()), float(depth.max()))
        here = np.isin(full_index, nodes)
        if np.any(done & here):
            raise JobMismatch(f"a window node lies in {region} and in another silicon region")
        x_um = win.nodes_cm[here, 0] * um
        depth_um = sign * (win.nodes_cm[here, 1] * um - surface_um)
        out[here] = _total(donors, x_range, y_range, x_um, depth_um) - _total(
            acceptors, x_range, y_range, x_um, depth_um
        )
        done |= here
    return out


def cut(
    mesh_path: Path,
    *,
    job_dir: Path,
    xs,
    kx: float,
    depth_um: float,
    source: str,
    out: Path,
    results_root: Path | None = None,
) -> dict:
    """Cut the artefact of the 2D job ``job_dir`` from the full mesh at ``mesh_path``, with
    the cross-section ``xs``, into ``out``; return its meta record."""
    cv_meta, cv_meta_sha256 = load_job(job_dir)
    key = job_key(job_dir, results_root)
    check_mesh_sha(mesh_path, cv_meta["mesh_sha256"])
    mesh = msh.read(mesh_path)
    check_gate(mesh, xs)
    x_um, y_um, rule = gate_window(xs, kx=kx, depth_um=depth_um)
    win = window.cut(mesh, x_um=x_um, y_um=y_um)
    win = win.with_net_doping(net_doping(mesh, win, xs))
    return artefact.write(
        out,
        win,
        job={**key, "cv_meta_sha256": cv_meta_sha256},
        full_mesh_sha256=cv_meta["mesh_sha256"],
        full_mesh_node_count=len(mesh.node_id),
        full_mesh_triangle_count=len(mesh.triangles),
        rule=rule,
        source=source,
    )


def _require_sandbox(name: str) -> None:
    if not sandbox.in_sandbox():
        raise RuntimeError(f"{name} must run inside the sandbox (see tools/sandbox-run)")


def run_cut_job(
    job_dir: Path,
    out: Path,
    *,
    kx: float,
    depth_um: float,
    results_root: Path | None = None,
) -> dict:
    """``cut-job``: the artefact of ``job_dir`` from ``out/mesh.msh`` (pulled from the output
    cache by the host) into ``out``."""
    _require_sandbox("cut-job")
    cv_meta, _ = load_job(job_dir)
    out = Path(out)
    check_mesh_sha(out / MESH_NAME, cv_meta["mesh_sha256"])
    xs = cross_section(job_dir, cv_meta)
    return cut(out / MESH_NAME, job_dir=job_dir, xs=xs, kx=kx, depth_um=depth_um,
               source="cache", out=out, results_root=results_root)  # fmt: skip


def _mesh_device(xs, spec: MeshSpec, path: Path) -> None:
    """Mesh ``xs`` with ``spec`` into ``path`` as the 2D job did (and delete the device)."""
    moscap2d.build_device(xs, spec, mesh_file=path).delete_device()


def run_regenerate_job(
    job_dir: Path,
    out: Path,
    *,
    cut: bool,
    kx: float | None,
    depth_um: float | None,
    results_root: Path | None = None,
    mesh_it: Callable[[object, MeshSpec, Path], None] = _mesh_device,
) -> dict | None:
    """``regenerate-job``: mesh the job's cross-section into ``out/mesh.msh`` with the job's mesh
    spec and record both sha256s in ``out/`` :data:`REGENERATE_REPORT`. With ``cut``, cut the
    artefact (``source: regenerated``) and return its meta; raise :class:`MeshShaMismatch`,
    after the report, if the regenerated mesh is not the committed one."""
    _require_sandbox("regenerate-job")
    cv_meta, _ = load_job(job_dir)
    out = Path(out)
    xs = cross_section(job_dir, cv_meta)
    spec = MeshSpec(**cv_meta["mesh"])
    mesh_it(xs, spec, out / MESH_NAME)
    committed, regenerated = cv_meta["mesh_sha256"], sha256_file(out / MESH_NAME)
    report = {
        "committed_mesh_sha256": committed,
        "match": committed == regenerated,
        "regenerated_mesh_sha256": regenerated,
    }
    io.write_json(out / REGENERATE_REPORT, report)
    print(f"committed mesh_sha256   {committed}", flush=True)
    print(f"regenerated mesh_sha256 {regenerated}", flush=True)
    print("match" if report["match"] else "no match", flush=True)
    if not cut:
        return None
    if not report["match"]:
        raise MeshShaMismatch(
            f"the regenerated mesh {regenerated} is not the committed {committed}; regenerate "
            "refuses to cut: the 2D job is rerun instead (renders plan, Decision: the four "
            "uncached start meshes)"
        )
    return cut_regenerated(job_dir, out, xs, kx=kx, depth_um=depth_um, results_root=results_root)


def cut_regenerated(job_dir, out, xs, *, kx, depth_um, results_root=None) -> dict:
    """The artefact of ``job_dir`` from the regenerated ``out/mesh.msh``."""
    return cut(Path(out) / MESH_NAME, job_dir=job_dir, xs=xs, kx=kx, depth_um=depth_um,
               source="regenerated", out=out, results_root=results_root)  # fmt: skip
