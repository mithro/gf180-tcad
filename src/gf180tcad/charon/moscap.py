# SPDX-License-Identifier: Apache-2.0
"""The 1D MOS capacitor on Charon: the DEVSIM job's stack, mesh and biases, the DEVSIM layout.

**The same inputs.** :func:`stack_1d` builds the plugin's ``Stack1D`` from the same pieces the
DEVSIM job uses (:mod:`gf180tcad.tcad.moscap1d`): :func:`~gf180tcad.tcad.moscap1d.stack_of`, the
region and contact names, the selected mesh spec's ``to_mesh1d`` and the plugin constants with the
process's oxide permittivity. The gate biases are the job's grid (``job_vg``), solved at
``vg - dv_fb_v`` and reported at ``vg``, the DEVSIM job's rigid flat-band shift.

**The result files** (:func:`write`) are the DEVSIM job's ``per_area.csv`` and
``per_area.meta.json``, with the same columns and units, plus ``"backend": "charon"`` and a
``charon`` block in the meta: the deck's SRH lifetime (which the zero-current C-V does not depend
on, see :repo:`docs/limitations/charon.md`), the LOCA sub-steps, the tolerances, the linear
solver, the strip's node count and the meaning of the convergence columns. ``rel_error`` is
Charon's WRMS norm of the last Newton update (NOX's weighted RMS, not DEVSIM's relative error) and
``abs_error`` is NaN: Charon reports no potential update.

**Mesh identity** is defined on the description's nodes: ``mesh_sha256`` is the sha256 of the
node positions (um, ``repr`` floats, one per line), the same for both backends on one stack.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from gf180tcad import io
from gf180tcad.charon import BACKEND
from gf180tcad.tcad import moscap1d
from gf180tcad.tcad.analytic import f_per_cm2_to_ff_per_um2
from gf180tcad.tcad.calibration import param_sha256
from gf180tcad.tcad.mesh import MeshSpec
from gf180tcad.tcad.process import CONSTANTS, Constants, ProcessDescription

# The DEVSIM job's names (one definition, in moscap1d).
POLY, OXIDE, BODY = moscap1d.POLY, moscap1d.OXIDE, moscap1d.BODY
GATE_CONTACT, BODY_CONTACT = moscap1d.GATE_CONTACT, moscap1d.BODY_CONTACT
#: The central-difference half step (V): the DEVSIM job's.
DV_QS = moscap1d.DV_QS

#: The units line of per_area.csv (``abs_error`` is dimensionless NaN here).
CSV_UNITS = "vg=V c_per_area=fF/um^2 rel_error=1 abs_error=1 iterations=1"
#: The meaning of the convergence columns, recorded in the meta.
CONVERGENCE_NOTE = (
    "rel_error: Charon's WRMS norm of the last Newton update of the two LOCA steps on "
    "vg -+ dv_qs (the larger); abs_error: NaN (Charon reports no potential update); "
    "iterations: the Newton iterations of those two steps"
)


@dataclass(frozen=True)
class CharonCV:
    """A 1D MOS capacitor C-V from Charon: C per area (fF/um^2) at each gate bias ``vg`` (V)."""

    device: str
    vg: tuple[float, ...]
    c_per_area_ff_um2: tuple[float, ...]
    points: tuple[moscap1d.Point, ...]
    constants: Constants
    mesh: MeshSpec
    stack: moscap1d.Stack
    node_count: int
    strip_node_count: int
    mesh_sha256: str
    settings: dict


def stack_1d(stack: moscap1d.Stack, mesh: MeshSpec, constants: Constants = CONSTANTS):
    """The plugin's ``Stack1D`` of the DEVSIM 1D job (see the module notes)."""
    from gplugins.devsim import doping
    from gplugins.devsim.device_description import Contact, InterfaceRef, Layer1D, Stack1D

    layers = [
        Layer1D(
            POLY, "silicon", stack.poly_um, doping.constant(stack.ngate_cm3), stack.gate_dopant
        ),
        Layer1D(OXIDE, "oxide", stack.t_ox_nm * 1e-3, None),
        Layer1D(BODY, "silicon", stack.body_um, doping.constant(stack.n_ch_cm3), stack.body_dopant),
    ]
    contacts = [
        Contact(GATE_CONTACT, InterfaceRef(POLY, None), "ohmic"),
        Contact(BODY_CONTACT, InterfaceRef(BODY, None), "ohmic"),
    ]
    return Stack1D(
        "moscap1d",
        layers,
        contacts,
        mesh.to_mesh1d(POLY, OXIDE, BODY),
        moscap1d.plugin_constants(constants, stack.eps_ox),
    )


def nodes_sha256(stack1d) -> str:
    """sha256 of the description's node positions (um), ``repr`` floats, one per line."""
    xs, _ = stack1d.node_positions_um()
    return hashlib.sha256("".join(f"{x!r}\n" for x in xs).encode("utf-8")).hexdigest()


def simulate(
    proc: ProcessDescription,
    *,
    vg: Sequence[float],
    mesh: MeshSpec,
    workdir: Path,
    constants: Constants = CONSTANTS,
) -> CharonCV:
    """The quasi-static 1D C-V of ``proc`` on Charon at ``vg`` (V); runs in the Charon image."""
    from gplugins.devsim.backends import charon
    from gplugins.devsim.backends.charon import deck as charon_deck
    from gplugins.devsim.device_description import CVSweep

    vg = tuple(float(v) for v in vg)
    dv_fb = proc.values()["dv_fb_v"]
    stack = moscap1d.stack_of(proc)
    desc = stack_1d(stack, mesh, constants)
    sweep = CVSweep(GATE_CONTACT, tuple(v - dv_fb for v in vg), "qs", dv_qs=DV_QS)
    dev = charon.create_1d_device(desc, workdir=workdir)
    try:
        res = charon.run_cv_sweep(dev, sweep)
        checks = dev.checks
    finally:
        dev.delete_device()
    if res.unit != "F/cm^2" or len(res.cgg) != len(vg):
        raise RuntimeError(f"a 1D Charon sweep gives {len(vg)} points in F/cm^2, got {res.unit}")
    tol = charon_deck.Tolerances()
    xs, _ = desc.node_positions_um()
    settings = {
        "srh_lifetime_s": charon_deck.SRH_LIFETIME_S,
        "loca_step_v": charon.LOCA_STEP_V,
        "substeps": charon.substeps_for(vg[1] - vg[0]),
        "charge_checks": checks,
        "linear_solver": "Amesos2 KLU2",
        "discretization": "drift diffusion cvfem (silicon), laplace cvfem (oxide)",
        "wrms_rel_tol": tol.rel,
        "wrms_abs_tol": tol.abs,
        "max_iterations": tol.max_iterations,
        "linear_tol": tol.linear,
        "convergence_columns": CONVERGENCE_NOTE,
    }
    points = tuple(
        moscap1d.Point(p.converged, p.iterations, p.rel_error, p.abs_error) for p in res.points
    )
    return CharonCV(
        device=proc.device,
        vg=vg,
        c_per_area_ff_um2=tuple(f_per_cm2_to_ff_per_um2(c) for c in res.cgg),
        points=points,
        constants=constants,
        mesh=mesh,
        stack=stack,
        node_count=len(xs),
        strip_node_count=2 * len(xs),
        mesh_sha256=nodes_sha256(desc),
        settings=settings,
    )


def write(
    cv: CharonCV,
    out: Path,
    *,
    proc: ProcessDescription,
    params: str,
    mesh_source: str,
    image: str,
    calibration_sha256: str | None = None,
) -> None:
    """Write :data:`moscap1d.PER_AREA_CSV` and :data:`moscap1d.PER_AREA_META` of ``cv``."""
    out = Path(out)
    if proc.device != cv.device or moscap1d.stack_of(proc) != cv.stack:
        raise ValueError(f"{proc.device}: not the process description of this C-V")
    columns = {
        "vg": cv.vg,
        "c_per_area": cv.c_per_area_ff_um2,
        "rel_error": [p.rel_error for p in cv.points],
        "abs_error": [p.abs_error for p in cv.points],
        "iterations": [int(p.iterations) for p in cv.points],
    }
    meta = {"backend": BACKEND, "device": cv.device, "dim": "1", "method": "qs",
            "params": params, "units": CSV_UNITS}  # fmt: skip
    moscap1d._write_csv(out / moscap1d.PER_AREA_CSV, columns, meta)
    origins = moscap1d.tunable_origins(proc, params, calibration_sha256)
    spacing = cv.mesh.spacing_um(POLY, OXIDE, BODY)
    io.write_json(
        out / moscap1d.PER_AREA_META,
        {
            "backend": BACKEND,
            "charon": {**cv.settings, "image": image, "strip_node_count": cv.strip_node_count},
            "constants": moscap1d.constants_dict(cv.constants),
            "device": cv.device,
            "dim": 1,
            "dv_fb_shift": "rigid: solved at vg - dv_fb_v, reported at vg",
            "mesh": cv.mesh.as_dict(),
            "mesh_1d_spacing_um": {k: list(v) for k, v in spacing.items()},
            "mesh_sha256": cv.mesh_sha256,
            "mesh_source": mesh_source,
            "method": "qs",
            "node_count": cv.node_count,
            "param_sha256": param_sha256({n: o["value"] for n, o in origins.items()}),
            "params": params,
            "points": len(cv.vg),
            "stack": asdict(cv.stack),
            "sweep": {"dv_qs_v": DV_QS},
            "tunables": origins,
            "unit": "fF/um^2",
        },
    )
