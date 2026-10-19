# SPDX-License-Identifier: Apache-2.0
"""Mesh convergence of the :term:`TCAD` :term:`MOS capacitors <MOSCAP>`: uniform refinement.

The :repo:`design spec, section 5.2 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#52-technical-definition>`
requires that uniform refinement of the mesh changes every metric by less than 1 %
(:data:`CRITERION`). :func:`converge` runs a simulation at the levels :data:`LEVELS`, each the
start :class:`~gf180tcad.tcad.mesh.MeshSpec` scaled by ``r`` (:meth:`MeshSpec.scaled
<gf180tcad.tcad.mesh.MeshSpec.scaled>`: every spacing times ``r``, the grading fixed), so that
neighbouring levels differ by a factor sqrt(2) in every spacing. Its
:class:`ConvergenceReport` holds, per level, the curve, the node count and the relative change
against the next finer level at every bias; per triple of neighbouring levels the
:term:`observed order of convergence`
p = log(abs(C1 - C2) / abs(C2 - C3)) / log(sqrt(2)) at every bias and its median; and the
:term:`Richardson extrapolation` of the three finest levels with the median order of that
triple (Roache, `J. Fluids Eng. 116, 405 (1994) <https://doi.org/10.1115/1.2910291>`_;
Celik et al., `J. Fluids Eng. 130, 078001 (2008) <https://doi.org/10.1115/1.2960953>`_). The
selected level is the coarsest whose change against the next finer one is below
:data:`CRITERION` at every bias.

The simulation is anything that satisfies :class:`CVCurve`: the 1D
:class:`~gf180tcad.tcad.moscap1d.MoscapCV` now, and the 2D ``MoscapCV2D`` of
:repo:`Task 11 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`,
which :func:`simulator` does not have yet (it raises :class:`NeedsTask11` for ``dim=2``).

**Result files** (:func:`write`), in ``<root>/moscap{1d,2d}/<device>/`` of the tree root
``results/tcad/meshconv``: :data:`REPORT_NAME`, the report (no runtimes), and
:data:`SELECTED_NAME`, the fields of the selected :class:`~gf180tcad.tcad.mesh.MeshSpec`, which
every 1D result uses from then on (:func:`selected_spec`).

This module is TCAD code. It is not one of the SPICE generator modules
(:data:`gf180tcad.reference.GENERATOR_MODULES`).
"""

from __future__ import annotations

import itertools
import json
import math
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from gf180tcad import io, sandbox
from gf180tcad.tcad.mesh import MeshSpec

# The refinement levels: scale factors of the start spec, a factor sqrt(2) apart.
LEVELS = (1, 2**-0.5, 0.5, 2**-1.5)

# The largest relative change against the next finer level a selected level may have.
CRITERION = 0.01

# Result file names in each job directory (<root>/moscap{1d,2d}/<device>/).
REPORT_NAME = "report.json"
SELECTED_NAME = "selected.json"

# The committed tree root.
TREE_ROOT = Path("results") / "tcad" / "meshconv"

# The memory budget of gf180-tcad.slice (as gf180tcad.reference.BUDGET_BYTES, which a test ties
# it to; the SPICE module is not imported, so it stays out of the TCAD generator modules).
BUDGET_BYTES = 128 << 30
_MEM_UNIT = {"k": 1 << 10, "m": 1 << 20, "g": 1 << 30}


@runtime_checkable
class CVCurve(Protocol):
    """A C-V curve on one mesh: C per area (fF/um^2) at each gate bias (V), and its node count."""

    vg: tuple[float, ...]
    c_per_area_ff_um2: tuple[float, ...]
    node_count: int


class NotConverged(RuntimeError):
    """No level changes by less than :data:`CRITERION` against the next finer one."""


class NeedsTask11(NotImplementedError):
    """``dim=2`` needs the 2D MOS capacitor of Task 11, which does not exist yet."""


class AdmissionError(ValueError):
    """The requested concurrency does not fit the memory budget."""


@dataclass(frozen=True)
class Level:
    """One refinement level: ``spec`` = start scaled by ``scale``, and its curve.

    ``rel_change`` is abs(C/C_finer - 1) at each bias against the next finer level and
    ``max_rel_change`` its maximum (both None on the finest level).
    """

    scale: float
    spec: MeshSpec
    node_count: int
    c_per_area_ff_um2: tuple[float, ...]
    rel_change: tuple[float, ...] | None
    max_rel_change: float | None


@dataclass(frozen=True)
class Order:
    """The observed order of the neighbouring levels ``levels`` (coarse to fine).

    ``per_bias`` is None where a difference between the levels is exactly zero; ``median`` is
    the median of the defined ones (None if there are none).
    """

    levels: tuple[int, int, int]
    per_bias: tuple[float | None, ...]
    median: float | None


@dataclass(frozen=True)
class ConvergenceReport:
    """The result of :func:`converge`; ``selected`` is the selected level's index or None."""

    start: MeshSpec
    vg: tuple[float, ...]
    levels: tuple[Level, ...]
    orders: tuple[Order, ...]
    richardson_order: float | None
    richardson: tuple[float, ...] | None
    selected: int | None

    @property
    def selected_spec(self) -> MeshSpec:
        """The selected level's spec; raises :class:`NotConverged` if none is selected."""
        if self.selected is None:
            worst = [lv.max_rel_change for lv in self.levels[:-1]]
            raise NotConverged(
                f"no level changes by less than {CRITERION:g} against the next finer one "
                f"(largest relative changes, coarse to fine: {worst})"
            )
        return self.levels[self.selected].spec


def observed_order(c1: float, c2: float, c3: float, ratio: float) -> float | None:
    """p = log(abs(c1 - c2) / abs(c2 - c3)) / log(ratio) of three levels ``ratio`` apart.

    None if either difference is exactly zero.
    """
    d12, d23 = abs(c1 - c2), abs(c2 - c3)
    if d12 == 0 or d23 == 0:
        return None
    return math.log(d12 / d23) / math.log(ratio)


def _check_levels(levels: Sequence[float]) -> tuple[float, ...]:
    levels = tuple(float(r) for r in levels)
    if len(levels) < 3:
        raise ValueError(f"mesh convergence needs at least 3 levels, got {levels}")
    if not all(math.isfinite(r) and r > 0 for r in levels):
        raise ValueError(f"levels must be finite and > 0, got {levels}")
    if not all(a > b for a, b in itertools.pairwise(levels)):
        raise ValueError(f"levels must go from coarse to fine (decreasing), got {levels}")
    ratios = [a / b for a, b in itertools.pairwise(levels)]
    if not all(math.isclose(q, ratios[0], rel_tol=1e-9) for q in ratios):
        raise ValueError(f"levels must have a constant ratio, got ratios {ratios}")
    return levels


def converge(
    simulate: Callable[[MeshSpec], CVCurve],
    spec: MeshSpec,
    levels: Sequence[float] = LEVELS,
) -> ConvergenceReport:
    """Run ``simulate`` at ``spec.scaled(r)`` for each level ``r`` (coarse to fine) and report.

    Every level must give the same biases. The selected level is the coarsest whose
    ``max_rel_change`` is below :data:`CRITERION`.
    """
    levels = _check_levels(levels)
    ratio = levels[0] / levels[1]
    specs = [spec.scaled(r) for r in levels]
    curves = [simulate(s) for s in specs]
    vg = tuple(curves[0].vg)
    for r, c in zip(levels, curves, strict=True):
        if tuple(c.vg) != vg or len(c.c_per_area_ff_um2) != len(vg):
            raise ValueError(f"level {r!r}: the biases differ from the coarsest level's")
    cs = [tuple(c.c_per_area_ff_um2) for c in curves]

    out_levels = []
    for i, (r, s, c) in enumerate(zip(levels, specs, curves, strict=True)):
        if i + 1 < len(levels):
            rel = tuple(abs(a / b - 1) for a, b in zip(cs[i], cs[i + 1], strict=True))
            worst = max(rel)
        else:
            rel, worst = None, None
        out_levels.append(Level(r, s, int(c.node_count), cs[i], rel, worst))

    orders = []
    for i in range(len(levels) - 2):
        per = tuple(
            observed_order(a, b, c, ratio)
            for a, b, c in zip(cs[i], cs[i + 1], cs[i + 2], strict=True)
        )
        defined = [p for p in per if p is not None]
        orders.append(
            Order((i, i + 1, i + 2), per, statistics.median(defined) if defined else None)
        )

    p = orders[-1].median
    if p is not None and p > 0:
        f = ratio**p - 1
        richardson = tuple(c3 + (c3 - c2) / f for c2, c3 in zip(cs[-2], cs[-1], strict=True))
    else:
        richardson = None

    selected = next(
        (i for i, lv in enumerate(out_levels[:-1]) if lv.max_rel_change < CRITERION), None
    )
    return ConvergenceReport(spec, vg, tuple(out_levels), tuple(orders), p, richardson, selected)


def report_dict(
    rep: ConvergenceReport, *, device: str, dim: int, settings: Mapping[str, object]
) -> dict:
    """The JSON of :data:`REPORT_NAME`: ``settings`` are the solver settings fixed across levels."""
    n = len(rep.levels)
    return {
        "criterion": CRITERION,
        "device": device,
        "dim": dim,
        "levels": [
            {
                "c_per_area_ff_um2": list(lv.c_per_area_ff_um2),
                "max_rel_change": lv.max_rel_change,
                "node_count": lv.node_count,
                "rel_change": None if lv.rel_change is None else list(lv.rel_change),
                "scale": lv.scale,
                "spec": lv.spec.as_dict(),
            }
            for lv in rep.levels
        ],
        "observed_order": [
            {"levels": list(o.levels), "median": o.median, "per_bias": list(o.per_bias)}
            for o in rep.orders
        ],
        "params": "start",
        "richardson": {
            "c_per_area_ff_um2": None if rep.richardson is None else list(rep.richardson),
            "levels": [n - 3, n - 2, n - 1],
            "order": rep.richardson_order,
        },
        "selected": None
        if rep.selected is None
        else {"level": rep.selected, "scale": rep.levels[rep.selected].scale},
        "settings": dict(settings),
        "start": rep.start.as_dict(),
        "unit": "fF/um^2",
        "vg": list(rep.vg),
    }


def write(
    rep: ConvergenceReport,
    out: Path,
    *,
    device: str,
    dim: int,
    settings: Mapping[str, object],
) -> None:
    """Write :data:`REPORT_NAME` and :data:`SELECTED_NAME` into ``out``.

    Raises :class:`NotConverged` (and writes nothing) if no level is selected.
    """
    selected = rep.selected_spec
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    io.write_json(out / REPORT_NAME, report_dict(rep, device=device, dim=dim, settings=settings))
    io.write_json(out / SELECTED_NAME, selected.as_dict())


def job_dir(root: Path, device: str, dim: int) -> Path:
    """``<root>/moscap{dim}d/<device>``."""
    return Path(root) / f"moscap{dim}d" / device


def selected_spec(device: str, dim: int, root: Path | None = None) -> MeshSpec:
    """The selected :class:`~gf180tcad.tcad.mesh.MeshSpec` of ``device`` from :data:`SELECTED_NAME`.

    ``root`` defaults to the committed tree root ``results/tcad/meshconv``.
    """
    root = Path(root) if root is not None else sandbox.REPO_ROOT / TREE_ROOT
    path = job_dir(root, device, dim) / SELECTED_NAME
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} does not exist: run `python -m gf180tcad.tcad meshconv --device {device} "
            f"--dim {dim} --out results/tcad/meshconv` first"
        )
    return MeshSpec(**json.loads(path.read_bytes()))


def check_dim(dim: int) -> None:
    """Raise :class:`NeedsTask11` for ``dim=2`` and ValueError unless ``dim`` is 1."""
    if dim == 2:
        raise NeedsTask11(
            "meshconv --dim 2 requires Task 11's MoscapCV2D (gf180tcad.tcad.moscap2d), which "
            "does not exist yet"
        )
    if dim != 1:
        raise ValueError(f"dim must be 1 or 2, got {dim!r}")


def simulator(device: str, dim: int):
    """``(simulate, settings)`` of ``device``'s start values in ``dim`` dimensions.

    ``simulate(spec)`` is the QS C-V on the SPICE ``cv`` biases; ``settings`` are the solver
    settings it fixes across levels. Runs in the TCAD image. ``dim=2`` raises
    :class:`NeedsTask11`.
    """
    check_dim(dim)
    from gf180tcad.tcad import moscap1d, process

    proc = process.load(device)
    pol = 1.0 if proc.polarity == "n" else -1.0
    vg = tuple(pol * v + 0.0 for v in process.CV_VG)  # as gf180tcad.tcad.__main__.job_vg

    def simulate(spec: MeshSpec) -> moscap1d.MoscapCV:
        return moscap1d.simulate(proc, vg=vg, method="qs", mesh=spec)

    settings = {
        "abs_tol_v": moscap1d.ABS_TOL,
        "constants": moscap1d.constants_dict(),
        "dv_qs_v": moscap1d.DV_QS,
        "max_iterations": moscap1d.MAX_ITERATIONS,
        "method": "qs",
        "rel_tol": moscap1d.REL_TOL,
    }
    return simulate, settings


def parse_mem(text: str) -> int:
    """Bytes of a docker-style memory size such as ``2g`` or ``512m``."""
    unit = _MEM_UNIT.get(text[-1:].lower())
    if unit is None or not text[:-1].isdigit() or int(text[:-1]) <= 0:
        raise ValueError(f"memory size must be a positive integer with k, m or g, got {text!r}")
    return int(text[:-1]) * unit


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
