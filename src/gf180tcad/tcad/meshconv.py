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
p = log(abs(C1 - C2) / abs(C2 - C3)) / log(sqrt(2)) at every bias and its median, with an
oscillation flag per bias (the change reverses sign, d12 * d23 < 0) and a noise floor
(:data:`NOISE_K` times the solver tolerance) below which the order is undefined; and the
:term:`Richardson extrapolation` of the three finest levels with the median order of that
triple (Roache, `J. Fluids Eng. 116, 405 (1994) <https://doi.org/10.1115/1.2910291>`_;
Celik et al., `J. Fluids Eng. 130, 078001 (2008) <https://doi.org/10.1115/1.2960953>`_). The
selected level is the coarsest whose change against the next finer one is below
:data:`CRITERION` at every bias.

The simulation is anything that satisfies :class:`CVCurve`: the 1D
:class:`~gf180tcad.tcad.moscap1d.MoscapCV` and the 2D
:class:`~gf180tcad.tcad.moscap2d.MoscapCV2D`
(:repo:`Task 11 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`).
:func:`simulator` gives each: the 1D stack from :attr:`MeshSpec.DEFAULT_1D
<gf180tcad.tcad.mesh.MeshSpec.DEFAULT_1D>`, and the 2D PDK cell at :data:`GEOMETRY_2D` with its
source and drain, from :attr:`MeshSpec.DEFAULT_2D <gf180tcad.tcad.mesh.MeshSpec.DEFAULT_2D>`
(:data:`START`).

**Result files** (:func:`write`), in ``<root>/moscap{1d,2d}/<device>/`` of the tree root
``results/tcad/meshconv``: :data:`REPORT_NAME`, the report (no runtimes), and
:data:`SELECTED_NAME`, the fields of the selected :class:`~gf180tcad.tcad.mesh.MeshSpec`, which
every 1D result uses from then on (:func:`selected_spec`).

This module is TCAD code. It is not one of the SPICE generator modules
(:data:`gf180tcad.reference.GENERATOR_MODULES`).
"""

from __future__ import annotations

import dataclasses
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

# The levels each dimension's study runs (see levels()). 2D stops at level 2: its level 3 is out
# of reach (EXCLUDED_2D), so levels 0 and 1 are the candidates, each with a finer neighbour.
LEVELS_BY_DIM = {1: LEVELS, 2: LEVELS[:3]}

# Why the 2D study leaves out level 3 (recorded in its report; Task 11, measured by meshing every
# level without solving and timing against the first study's s/bias = 3.25e-6 * nodes^1.278).
EXCLUDED_2D = (
    {
        "level": 3,
        "scale": LEVELS[3],
        "reason": (
            "the Lmin cell has 862k (nfet) and 788k (pfet) nodes: an estimated 9.7 h and 8.7 h "
            "of QS, over the 8 h job rule, and the size at which the equilibrium drift-diffusion "
            "solve fails in UMFPACK 5.1 (the L = 10 um cell, 0.86 M Poisson unknowns)"
        ),
    },
)

# The largest relative change against the next finer level a selected level may have.
CRITERION = 0.01

# The second criterion of a 2D study: the selected level must also reproduce 1D within this
# (largest relative difference of the extruded uniform stack's C per area against 1D, 21 biases;
# the 2D-equals-1D check of Task 11). The selected level is the coarsest meeting both.
AGREEMENT_1D = 0.5 / 100  # 0.5 %, an independent criterion (not the Xyce engine-diff threshold)

# The noise floor of a level difference, as a multiple of the solver's relative tolerance: a
# difference |C_i - C_j| <= NOISE_K * rel_tol * |C| is solver noise, so the observed order there
# is undefined (None), not an arbitrary number. Why 1e4: a QS C is the central difference
# (Q(vg + dv) - Q(vg - dv)) / (2 dv) with dv = 1 mV (moscap1d.DV_QS), and each charge carries a
# relative error up to about rel_tol, so the noise in C is about rel_tol * |Q| / dv. With
# |Q| <= C * |vg - vfb| and |vg - vfb| <= 6.1 V over the +-5 V sweep, rel_tol * |Q| / dv is at
# most 6.1e3 * rel_tol * |C|; 1e4 rounds that up.
NOISE_K = 1e4

# The solver relative tolerance the noise floor assumes by default (moscap1d.REL_TOL).
DEFAULT_REL_TOL = 1e-10

# Result file names in each job directory (<root>/moscap{1d,2d}/<device>/).
REPORT_NAME = "report.json"
SELECTED_NAME = "selected.json"

# The committed tree root.
TREE_ROOT = Path("results") / "tcad" / "meshconv"

# The start spec of each dimension's study.
START = {1: MeshSpec.DEFAULT_1D, 2: MeshSpec.DEFAULT_2D}

# Whether a level scales the grading too (MeshSpec.scaled(refine_grading=...)): in 2D the meshwell
# size field grows at the slope (grading - 1), which a uniform refinement must scale as well,
# else the depletion region is never refined (Task 11); in 1D the grading is only a cap.
REFINE_GRADING = {1: False, 2: True}

# The geometry of the 2D study (W um, L um) per device: the calibration geometry at Lmin, the
# one whose C-V the 2D structure (gate edges, overlap, fringe) shapes most. The selected spec
# applies to every 2D geometry; the interface spacing it fixes is local and does not depend
# on L.
GEOMETRY_2D = {"nfet_05v0": (10.0, 0.6), "pfet_05v0": (10.0, 0.5)}

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


class AdmissionError(ValueError):
    """The requested concurrency does not fit the memory budget."""


@dataclass(frozen=True)
class Level:
    """One refinement level: ``spec`` = start scaled by ``scale``, and its curve.

    ``rel_change`` is abs(C/C_finer - 1) at each bias against the next finer level and
    ``max_rel_change`` its maximum (both None on the finest level). ``extended_fallback`` lists
    the bias indices that the 2D QS sweep solved in extended precision after a stalled
    double-precision solve (the curve's ``extended_fallback``; empty in 1D), and
    ``roundoff_accepted`` the solves accepted at round-off near psi = 0 (``roundoff_accepted``).
    """

    scale: float
    spec: MeshSpec
    node_count: int
    c_per_area_ff_um2: tuple[float, ...]
    rel_change: tuple[float, ...] | None
    max_rel_change: float | None
    extended_fallback: tuple[int, ...] = ()
    roundoff_accepted: tuple[dict, ...] = ()
    agreement_1d: float | None = None
    agreement_1d_curve: dict | None = None


@dataclass(frozen=True)
class Order:
    """The observed order of the neighbouring levels ``levels`` (coarse to fine).

    ``per_bias`` is None where a difference between the levels is at or below the noise floor
    (:data:`NOISE_K`; exactly zero included). ``oscillating`` flags, per bias, a change that
    reverses sign between the levels (d12 * d23 < 0, with d12 = C1 - C2 and d23 = C2 - C3:
    oscillatory convergence, where the order and the Richardson extrapolation do not apply);
    it is None where the order is undefined. ``median`` is the median of the defined orders of
    the monotone (not oscillating) biases, None if there are none.
    """

    levels: tuple[int, int, int]
    per_bias: tuple[float | None, ...]
    median: float | None
    oscillating: tuple[bool | None, ...] = ()


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
    rel_tol: float = DEFAULT_REL_TOL
    convergence_level: int | None = None
    agreement_level: int | None = None
    refine_grading: bool = False

    @property
    def criteria(self) -> dict:
        """The selection criteria, the level each one chooses, and the selected level."""
        out = {
            "convergence": {"level": self.convergence_level, "max": CRITERION},
            "selected": self.selected,
        }
        if any(lv.agreement_1d is not None for lv in self.levels):
            out["agreement_1d"] = {"level": self.agreement_level, "max": AGREEMENT_1D}
        return out

    @property
    def noise_floor_rel(self) -> float:
        """The relative noise floor of a level difference, :data:`NOISE_K` * ``rel_tol``."""
        return NOISE_K * self.rel_tol

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


def observed_order(
    c1: float, c2: float, c3: float, ratio: float, *, floor: float = 0.0
) -> float | None:
    """p = log(abs(c1 - c2) / abs(c2 - c3)) / log(ratio) of three levels ``ratio`` apart.

    None if either difference is at most ``floor`` (absolute; 0: exactly zero), i.e. noise.
    """
    d12, d23 = abs(c1 - c2), abs(c2 - c3)
    if d12 <= floor or d23 <= floor:
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
    *,
    rel_tol: float = DEFAULT_REL_TOL,
    agreement: Sequence[float] | None = None,
    agreement_curves: Sequence[dict] | None = None,
    refine_grading: bool = False,
) -> ConvergenceReport:
    """Run ``simulate`` at ``spec.scaled(r)`` for each level ``r`` (coarse to fine) and report.

    Every level must give the same biases. The selected level is the coarsest whose
    ``max_rel_change`` is below :data:`CRITERION`. ``rel_tol`` is the solver's relative
    tolerance, which sets the noise floor of the observed order (:data:`NOISE_K`).
    ``agreement`` (2D) gives each level's largest relative difference from 1D on the uniform
    stack; then the selected level is the coarsest that also has ``agreement`` <=
    :data:`AGREEMENT_1D`. ``agreement_curves`` (per level, e.g. the output of
    :func:`agreement_1d`) are kept in the report.
    """
    if not (rel_tol > 0 and math.isfinite(rel_tol)):
        raise ValueError(f"rel_tol must be > 0, got {rel_tol!r}")
    levels = _check_levels(levels)
    if agreement is not None:
        agreement = tuple(float(a) for a in agreement)
        if len(agreement) != len(levels):
            raise ValueError(f"agreement needs one value per level, got {agreement}")
    ratio = levels[0] / levels[1]
    specs = [spec.scaled(r, refine_grading=refine_grading) for r in levels]
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
        fallback = tuple(int(k) for k in getattr(c, "extended_fallback", ()))
        roundoff = tuple(dict(x) for x in getattr(c, "roundoff_accepted", ()))
        out_levels.append(
            Level(
                r, s, int(c.node_count), cs[i], rel, worst, fallback, roundoff,
                None if agreement is None else agreement[i],
                None if agreement_curves is None else dict(agreement_curves[i]),
            )
        )  # fmt: skip

    orders = []
    for i in range(len(levels) - 2):
        per, osc = [], []
        for a, b, c in zip(cs[i], cs[i + 1], cs[i + 2], strict=True):
            q = observed_order(a, b, c, ratio, floor=NOISE_K * rel_tol * abs(b))
            per.append(q)
            osc.append(None if q is None else (a - b) * (b - c) < 0)
        defined = [q for q, o in zip(per, osc, strict=True) if q is not None and not o]
        orders.append(
            Order(
                (i, i + 1, i + 2),
                tuple(per),
                statistics.median(defined) if defined else None,
                tuple(osc),
            )
        )

    p = orders[-1].median
    if p is not None and p > 0:
        f = ratio**p - 1
        richardson = tuple(c3 + (c3 - c2) / f for c2, c3 in zip(cs[-2], cs[-1], strict=True))
    else:
        richardson = None

    conv = next((i for i, lv in enumerate(out_levels[:-1]) if lv.max_rel_change < CRITERION), None)
    agree = None
    if agreement is not None:
        agree = next((i for i, a in enumerate(agreement) if a <= AGREEMENT_1D), None)
    selected = next(
        (
            i
            for i, lv in enumerate(out_levels[:-1])
            if lv.max_rel_change < CRITERION and (agreement is None or agreement[i] <= AGREEMENT_1D)
        ),
        None,
    )
    return ConvergenceReport(
        spec, vg, tuple(out_levels), tuple(orders), p, richardson, selected, rel_tol,
        conv, agree, refine_grading,
    )  # fmt: skip


def report_dict(
    rep: ConvergenceReport, *, device: str, dim: int, settings: Mapping[str, object]
) -> dict:
    """The JSON of :data:`REPORT_NAME`: ``settings`` are the solver settings fixed across levels."""
    n = len(rep.levels)
    extra = {"excluded_levels": [dict(x) for x in EXCLUDED_2D]} if dim == 2 else {}
    return extra | {
        "criterion": CRITERION,
        "device": device,
        "dim": dim,
        "levels": [
            {
                "c_per_area_ff_um2": list(lv.c_per_area_ff_um2),
                "agreement_1d": lv.agreement_1d,
                "agreement_1d_curve": lv.agreement_1d_curve,
                "extended_fallback": list(lv.extended_fallback),
                "roundoff_accepted": [dict(x) for x in lv.roundoff_accepted],
                "max_rel_change": lv.max_rel_change,
                "node_count": lv.node_count,
                "rel_change": None if lv.rel_change is None else list(lv.rel_change),
                "scale": lv.scale,
                "spec": lv.spec.as_dict(),
            }
            for lv in rep.levels
        ],
        "noise_floor": {"k": NOISE_K, "rel": rep.noise_floor_rel, "rel_tol": rep.rel_tol},
        "observed_order": [
            {
                "levels": list(o.levels),
                "median": o.median,
                "oscillating": list(o.oscillating),
                "per_bias": list(o.per_bias),
            }
            for o in rep.orders
        ],
        "params": "start",
        "refine_grading": rep.refine_grading,
        "richardson": {
            "c_per_area_ff_um2": None if rep.richardson is None else list(rep.richardson),
            "levels": [n - 3, n - 2, n - 1],
            "order": rep.richardson_order,
        },
        "selected": None
        if rep.selected is None
        else {
            "criteria": rep.criteria,
            "level": rep.selected,
            "scale": rep.levels[rep.selected].scale,
        },
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
    io.write_json(out / SELECTED_NAME, {**selected.as_dict(), "criteria": rep.criteria})


def job_dir(root: Path, device: str, dim: int) -> Path:
    """``<root>/moscap{dim}d/<device>``."""
    return Path(root) / f"moscap{dim}d" / device


def read_selected(path: Path) -> MeshSpec:
    """The :class:`~gf180tcad.tcad.mesh.MeshSpec` of a :data:`SELECTED_NAME` file (its spec
    fields; the ``criteria`` record is not part of the spec)."""
    data = json.loads(Path(path).read_bytes())
    return MeshSpec(**{f.name: data[f.name] for f in dataclasses.fields(MeshSpec)})


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
    return read_selected(path)


def check_dim(dim: int) -> None:
    """Raise ValueError unless ``dim`` is 1 or 2."""
    if dim not in (1, 2):
        raise ValueError(f"dim must be 1 or 2, got {dim!r}")


def levels(dim: int) -> tuple[float, ...]:
    """The refinement levels of the ``dim``-dimensional study (:data:`LEVELS_BY_DIM`)."""
    check_dim(dim)
    return LEVELS_BY_DIM[dim]


def check_level(dim: int, level: int) -> None:
    """Raise ValueError unless ``level`` is an index of :func:`levels` of ``dim``."""
    n = len(levels(dim))
    if not 0 <= level < n:
        raise ValueError(f"level {level} is not part of the {dim}D study (levels 0-{n - 1})")


def geometry_2d(device: str):
    """The :class:`gf180tcad.devices.Geometry` of the 2D study (:data:`GEOMETRY_2D`)."""
    from gf180tcad.devices import DEVICES

    w, l_um = GEOMETRY_2D[device]
    (g,) = [g for g in DEVICES[device].geometries if (g.w_um, g.l_um) == (w, l_um)]
    return g


def simulator(device: str, dim: int, log=None):
    """``(simulate, settings)`` of ``device``'s start values in ``dim`` dimensions.

    ``simulate(spec)`` is the QS C-V on the SPICE ``cv`` biases (2D: the PDK cell at
    :func:`geometry_2d`, with source and drain); ``settings`` are the solver settings it fixes
    across levels. ``log`` receives the 2D progress lines. Runs in the TCAD image.
    """
    check_dim(dim)
    from gf180tcad.tcad import moscap1d, process

    proc = process.load(device)
    pol = 1.0 if proc.polarity == "n" else -1.0
    vg = tuple(pol * v + 0.0 for v in process.CV_VG)  # as gf180tcad.tcad.__main__.job_vg

    if dim == 1:

        def simulate(spec: MeshSpec) -> moscap1d.MoscapCV:
            return moscap1d.simulate(proc, vg=vg, method="qs", mesh=spec)

    else:
        from gf180tcad.tcad import moscap2d

        geometry = geometry_2d(device)

        def simulate(spec: MeshSpec) -> moscap2d.MoscapCV2D:
            return moscap2d.simulate(
                proc, geometry, vg=vg, with_sd=True, method="qs", mesh=spec, log=log
            )

    settings = {
        "abs_tol_v": moscap1d.ABS_TOL,
        "constants": moscap1d.constants_dict(),
        "dv_qs_v": moscap1d.DV_QS,
        "max_iterations": moscap1d.MAX_ITERATIONS,
        "method": "qs",
        "rel_tol": moscap1d.REL_TOL,
    }
    if dim == 2:
        from gf180tcad.devices import geometry_id
        from gf180tcad.tcad import stack

        settings |= {
            "geometry": geometry_id(geometry_2d(device)),
            "point_tolerance_um": stack.POINT_TOLERANCE_UM,
            "qs_extended_precision": False,
            "with_sd": True,
        }
    return simulate, settings


# The uniform-stack check of the second criterion: its biases (every 10th of the cv grid, in
# the SPICE order) and its length (um; the result does not depend on it, the sides are Neumann).
AGREEMENT_STRIDE = 10
AGREEMENT_L_UM = 1.0


def agreement_1d(device: str, spec: MeshSpec) -> dict:
    """The 2D-equals-1D check at ``spec``: the extruded uniform stack (gate over the whole
    domain, no S/D, Neumann sides) against the selected 1D C-V, QS on every
    :data:`AGREEMENT_STRIDE`-th bias of the cv grid. ``max`` is the largest ``abs(2D/1D - 1)``. Runs in
    the TCAD image."""
    from gf180tcad.tcad import moscap1d, moscap2d, process, stack

    proc = process.load(device)
    pol = 1.0 if proc.polarity == "n" else -1.0
    vg = tuple(pol * v + 0.0 for v in process.CV_VG[::AGREEMENT_STRIDE])
    cv2 = moscap2d.simulate(
        proc, None, vg=vg, with_sd=False, method="qs", mesh=spec,
        structure=stack.uniform(proc, AGREEMENT_L_UM), mesh_file="uniform.msh",
    )  # fmt: skip
    cv1 = moscap1d.simulate(proc, vg=vg, mesh=selected_spec(device, 1))
    rel = [a / b - 1 for a, b in zip(cv2.c_per_area_ff_um2, cv1.c_per_area_ff_um2, strict=True)]
    return {
        "c1d": list(cv1.c_per_area_ff_um2),
        "c2d": list(cv2.c_per_area_ff_um2),
        "max": max(abs(r) for r in rel),
        "node_count": cv2.node_count,
        "rel": rel,
        "roundoff_accepted": [dict(r) for r in cv2.roundoff_accepted],
        "spec": spec.as_dict(),
        "vg": list(vg),
    }


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
