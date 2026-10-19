# SPDX-License-Identifier: Apache-2.0
"""The 1D :term:`MOS capacitor <MOSCAP>` of ``nfet_05v0`` and ``pfet_05v0``: its :term:`C–V`
per area, and the :term:`SPICE` bookkeeping that turns it into a gate capacitance of one geometry.

**The structure** (:class:`Stack`, built by `gplugins.devsim.create_1d_stack
<https://github.com/mithro/gplugins/blob/dddaa071321c5177c8471312c565ad86d4b245d7/gplugins/devsim/stack1d.py>`_): a poly-silicon gate region doped at :term:`NGATE` (n+ for the nfet, p+ for
the pfet), the gate oxide of thickness ``t_ox_eff_nm`` (relative permittivity :term:`EPSROX`),
and a uniformly doped silicon body at ``n_ch_cm3`` (p-type for the nfet, n-type, the n-well, for
the pfet). The contacts are ohmic, ``gate`` on the free end of the poly
(``InterfaceRef("gate_poly", None)``) and ``body`` on the free end of the body
(``InterfaceRef("body", None)``). The poly (:data:`POLY_UM`) and the body (:data:`BODY_UM`)
thicknesses are project choices, many times the widest depletion region of each, so both reach
their neutral bulk; the C-V does not depend on them (the exact reference,
:mod:`gf180tcad.tcad.analytic`, assumes semi-infinite poly and body, and the tests compare).

**The C-V** (:func:`simulate`): `gplugins.devsim.sweep_cv <https://github.com/mithro/gplugins/blob/dddaa071321c5177c8471312c565ad86d4b245d7/gplugins/devsim/cv.py>`_, quasi-static by
default: equilibrium Poisson-Boltzmann with the body at 0 V, the counterpart of the
:term:`SPICE` :term:`Cgg` of :term:`BSIM4` ``capMod=2``. The lumped flat-band offset
``dv_fb_v`` is a rigid gate-bias shift: the device is solved at ``vg - dv_fb_v`` and the result
is reported at ``vg``, which is exact for a 1D MOS capacitor
(:repo:`Task 11 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`
applies the same shift in 2D). `DEVSIM <https://devsim.org/>`_'s F/cm^2 are converted to
fF/um^2 (:func:`gf180tcad.tcad.analytic.f_per_cm2_to_ff_per_um2`). A point that does not
converge at the tolerances raises (`gplugins.devsim.CVConvergenceError <https://github.com/mithro/gplugins/blob/dddaa071321c5177c8471312c565ad86d4b245d7/gplugins/devsim/cv.py>`_); none is
dropped.

**The SPICE bookkeeping** (:meth:`MoscapCV.area_scaled`), 1D only: the intrinsic :term:`Cgg` of
the :term:`TCAD` is the C per area times the BSIM4 capacitance area LeffCV * WeffCV, with
LeffCV = L + :term:`XL` - 2 * :term:`DLC` and WeffCV = W + :term:`XW` - 2 * :term:`DWC` (the card's
length/width-dependent offsets :term:`LLC`, :term:`LWC`, :term:`LWLC`, :term:`WLC`,
:term:`WWC`, :term:`WWLC` are zero or unset); for the nfet this is (L - 2*DLC)*W. The
extrinsic (parasitic) part is reported separately, never folded in silently:
:func:`parasitic_ff`, the exact BSIM4 4.5 ``capMod=2`` overlap equations of the BSIM4 manual,
section 7.5 ("Fringing and overlap capacitances", https://bsim.berkeley.edu/models/bsim4/, the
4.5.0 release https://www.bsim.berkeley.edu/BSIM4/BSIM450.zip) and of ngspice's BSIM4 code,
`b4ld.c <https://sourceforge.net/p/ngspice/ngspice/ci/ngspice-47/tree/src/spicelib/devices/bsim4/b4ld.c>`_ and `b4temp.c <https://sourceforge.net/p/ngspice/ngspice/ci/ngspice-47/tree/src/spicelib/devices/bsim4/b4temp.c>`_:

- per side (source with CGSO, CGSL, :term:`CKAPPAS`; drain with CGDO, CGDL, :term:`CKAPPAD`),
  with V the gate bias in the NMOS sign convention (type * vg; source, drain and body at 0 V),
  Q_ov/WeffCV = (CGO + CF)*V + CGL*(V - V_ov - CKAPPA/2*(-1 + sqrt(1 - 4*V_ov/CKAPPA))),
  V_ov = (V + d1 - sqrt((V + d1)^2 + 4*d1))/2 with d1 = 0.02 V, so that
  C_ov = dQ_ov/dV = WeffCV*(CGO + CF + CGL*(1 - (1 - 1/sqrt(1 - 4*V_ov/CKAPPA))*dV_ov/dV));
- CF, the outer fringe, is added to CGSO and CGDO (`b4temp.c <https://sourceforge.net/p/ngspice/ngspice/ci/ngspice-47/tree/src/spicelib/devices/bsim4/b4temp.c>`_:
  cgso = (CGSO + CF)*WeffCV);
- the gate-bulk overlap :term:`CGBO` * LeffCV.

:term:`VFBCV` (-1 V on the nfet card) is the flat band of ``capMod=0`` only and does not enter
these equations; :term:`VFBSDOFF` is 0 on the nfet card and unset (0) on the pfet card.

This module imports the plugin lazily (it needs the TCAD image), so it imports on the host.
It is TCAD code, not one of the SPICE generator modules
(:data:`gf180tcad.reference.GENERATOR_MODULES`).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from gf180tcad import io
from gf180tcad.devices import Geometry
from gf180tcad.tcad.analytic import f_per_cm2_to_ff_per_um2
from gf180tcad.tcad.calibration import param_sha256
from gf180tcad.tcad.mesh import MeshSpec
from gf180tcad.tcad.process import CONSTANTS, TUNABLES, Constants, ProcessDescription
from gf180tcad.tcad.process import load as load_process

# Region and contact names of the 1D stack.
POLY, OXIDE, BODY = "gate_poly", "oxide", "body"
GATE_CONTACT, BODY_CONTACT = "gate", "body"

# Poly-gate and body thicknesses (um): project choices, many times the widest depletion of each
# (about 1 nm in the poly in inversion, 0.1 um in the body), so both reach a neutral bulk.
POLY_UM = 0.2
BODY_UM = 1.0

# sweep_cv settings: relative tolerance (simulate's default, used for every committed result),
# central-difference half step (V), largest potential update (V) and Newton iterations per solve.
REL_TOL = 1e-10
DV_QS = 1e-3
ABS_TOL = 1e-12
MAX_ITERATIONS = 50

# BSIM4's DELTA_1 (V) of the bias-dependent overlap capacitance (b4ld.c).
BSIM4_DELTA_1 = 0.02

# Result file names in each job directory (<root>/<device>/<params>/).
PER_AREA_CSV = "per_area.csv"
PER_AREA_META = "per_area.meta.json"


@dataclass(frozen=True)
class Point:
    """Convergence of one bias point, from `gplugins.devsim.PointInfo <https://github.com/mithro/gplugins/blob/dddaa071321c5177c8471312c565ad86d4b245d7/gplugins/devsim/cv.py>`_."""

    converged: bool
    iterations: int
    rel_error: float
    abs_error: float


@dataclass(frozen=True)
class Stack:
    """The 1D structure: polarity (``"n"``: p-body with an n+ gate), dopings (cm^-3), oxide."""

    polarity: Literal["n", "p"]
    n_ch_cm3: float
    ngate_cm3: float
    t_ox_nm: float
    eps_ox: float
    poly_um: float = POLY_UM
    body_um: float = BODY_UM

    def __post_init__(self) -> None:
        if self.polarity not in ("n", "p"):
            raise ValueError(f"polarity must be 'n' or 'p', got {self.polarity!r}")
        for name in ("n_ch_cm3", "ngate_cm3", "t_ox_nm", "eps_ox", "poly_um", "body_um"):
            v = getattr(self, name)
            if not (v > 0 and math.isfinite(v)):
                raise ValueError(f"Stack.{name} must be > 0, got {v!r}")

    @property
    def body_dopant(self) -> Literal["donor", "acceptor"]:
        return "acceptor" if self.polarity == "n" else "donor"

    @property
    def gate_dopant(self) -> Literal["donor", "acceptor"]:
        return "donor" if self.polarity == "n" else "acceptor"

    @property
    def body_net_cm3(self) -> float:
        """Net body doping N_D - N_A (signed, as :mod:`gf180tcad.tcad.analytic` takes it)."""
        return -self.n_ch_cm3 if self.polarity == "n" else self.n_ch_cm3

    @property
    def gate_net_cm3(self) -> float:
        """Net poly-gate doping N_D - N_A (signed)."""
        return self.ngate_cm3 if self.polarity == "n" else -self.ngate_cm3


def stack_of(proc: ProcessDescription) -> Stack:
    """The :class:`Stack` of a process description (its current tunable values)."""
    v = proc.values()
    return Stack(proc.polarity, v["n_ch_cm3"], v["ngate_cm3"], v["t_ox_eff_nm"], v["epsrox"])


def plugin_constants(constants: Constants, eps_ox: float):
    """The plugin's `gplugins.devsim.Constants <https://github.com/mithro/gplugins/blob/dddaa071321c5177c8471312c565ad86d4b245d7/gplugins/devsim/constants.py>`_: ``constants`` plus ``eps_ox``."""
    from gplugins.devsim import Constants as PluginConstants

    return PluginConstants(**asdict(constants), eps_ox=eps_ox)


def sweep_stack(
    stack: Stack,
    vg_device: Sequence[float],
    *,
    mesh: MeshSpec,
    constants: Constants = CONSTANTS,
    method: Literal["qs", "ac"] = "qs",
    freq_hz: float | None = None,
    rel_tol: float = REL_TOL,
    name: str = "moscap1d",
):
    """Build ``stack`` and step its gate over ``vg_device`` (V): a `gplugins.devsim.CVResult <https://github.com/mithro/gplugins/blob/dddaa071321c5177c8471312c565ad86d4b245d7/gplugins/devsim/cv.py>`_.

    One live device per call: the device (and its mesh) is deleted afterwards, also when
    ``sweep_cv`` raises.
    """
    return _sweep_stack(
        stack, vg_device, mesh=mesh, constants=constants, method=method, freq_hz=freq_hz,
        rel_tol=rel_tol, name=name,
    )[0]  # fmt: skip


def _node_count(device: str) -> int:
    """The number of distinct mesh nodes of the live 1D ``device`` (interface nodes once)."""
    import devsim

    xs = set()
    for region in devsim.get_region_list(device=device):
        xs.update(devsim.get_node_model_values(device=device, region=region, name="x"))
    return len(xs)


def _sweep_stack(
    stack: Stack,
    vg_device: Sequence[float],
    *,
    mesh: MeshSpec,
    constants: Constants,
    method: Literal["qs", "ac"],
    freq_hz: float | None,
    rel_tol: float,
    name: str,
):
    """:func:`sweep_stack` and the node count of the mesh: ``(CVResult, node_count)``."""
    from gplugins.devsim import Contact, InterfaceRef, Layer1D, create_1d_stack, doping, sweep_cv

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
    dd = create_1d_stack(
        name,
        layers,
        contacts,
        mesh.to_mesh1d(POLY, OXIDE, BODY),
        plugin_constants(constants, stack.eps_ox),
        relative_error=rel_tol,
    )
    try:
        nodes = _node_count(name)
        res = sweep_cv(
            dd,
            GATE_CONTACT,
            vg_device,
            method=method,
            freq_hz=freq_hz,
            dv_qs=DV_QS,
            rel_tol=rel_tol,
            abs_tol=ABS_TOL,
            max_iterations=MAX_ITERATIONS,
        )
    finally:
        dd.delete_device()
    return res, nodes


# --- the SPICE bookkeeping -------------------------------------------------------------------


def cv_geometry_um(card: Mapping[str, float], geometry: Geometry) -> tuple[float, float]:
    """``(LeffCV, WeffCV)`` (um): L + XL - 2*DLC and W + XW - 2*DWC (BSIM4, one finger)."""
    leff = geometry.l_um + (card["xl"] - 2 * card["dlc"]) * 1e6
    weff = geometry.w_um + (card["xw"] - 2 * card["dwc"]) * 1e6
    return leff, weff


def _overlap_f_per_m(v: float, cgo: float, cgl: float, ckappa: float, cf: float) -> float:
    """dQ_ov/dV per WeffCV (F/m) of one side at the NMOS-convention gate bias ``v`` (V)."""
    d1 = BSIM4_DELTA_1
    t0 = v + d1
    t1 = math.sqrt(t0 * t0 + 4 * d1)
    v_ov = 0.5 * (t0 - t1)
    dv_ov = 0.5 * (1 - t0 / t1)
    t4 = math.sqrt(1 - 4 * v_ov / ckappa)
    return cgo + cf + cgl * (1 - (1 - 1 / t4) * dv_ov)


def parasitic_ff(
    card: Mapping[str, float], vg: Sequence[float], geometry: Geometry
) -> tuple[float, ...]:
    """The extrinsic Cgg (fF) at each gate bias ``vg`` (true sign): both overlaps, CF and CGBO.

    ``card`` is :meth:`~gf180tcad.tcad.process.ProcessDescription.card_values` (card units).
    """
    leff, weff = cv_geometry_um(card, geometry)
    w_m, l_m = weff * 1e-6, leff * 1e-6
    out = []
    for v in vg:
        vn = card["type"] * v
        cs = _overlap_f_per_m(vn, card["cgso"], card["cgsl"], card["ckappas"], card["cf"])
        cd = _overlap_f_per_m(vn, card["cgdo"], card["cgdl"], card["ckappad"], card["cf"])
        out.append(((cs + cd) * w_m + card["cgbo"] * l_m) * 1e15)
    return tuple(out)


@dataclass(frozen=True)
class MoscapCV:
    """A 1D MOS capacitor C-V: C per area (fF/um^2) at each gate bias ``vg`` (V, true sign)."""

    device: str
    vg: tuple[float, ...]
    c_per_area_ff_um2: tuple[float, ...]
    points: tuple[Point, ...]
    method: str
    constants: Constants
    mesh: MeshSpec
    stack: Stack
    rel_tol: float
    node_count: int

    def area_scaled(
        self, geometry: Geometry, proc: ProcessDescription | None = None
    ) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
        """``(vg, cgg_intrinsic_ff, cgg_parasitic_ff, cgg_total_ff)`` of one geometry (1D only).

        Intrinsic: C per area times LeffCV * WeffCV (:func:`cv_geometry_um`). Parasitic: the
        BSIM4 overlap, fringe and gate-bulk terms (:func:`parasitic_ff`) from the fixed
        bookkeeping values of ``proc`` (default: the device's process file). Total: their sum.
        """
        proc = proc if proc is not None else load_process(self.device)
        if proc.device != self.device:
            raise ValueError(f"process {proc.device} is not {self.device}")
        card = proc.card_values()
        leff, weff = cv_geometry_um(card, geometry)
        intrinsic = tuple(c * leff * weff for c in self.c_per_area_ff_um2)
        parasitic = parasitic_ff(card, self.vg, geometry)
        total = tuple(a + b for a, b in zip(intrinsic, parasitic, strict=True))
        return self.vg, intrinsic, parasitic, total


def simulate(
    proc: ProcessDescription,
    *,
    vg: Sequence[float],
    method: Literal["qs", "ac"] = "qs",
    mesh: MeshSpec,
    rel_tol: float = REL_TOL,
    freq_hz: float | None = None,
    constants: Constants = CONSTANTS,
) -> MoscapCV:
    """The 1D C-V of ``proc`` at the gate biases ``vg`` (V), with ``dv_fb_v`` as a rigid shift.

    The device is solved at ``vg - dv_fb_v`` and the result reported at ``vg``. Runs in the TCAD
    image. Raises `gplugins.devsim.CVConvergenceError <https://github.com/mithro/gplugins/blob/dddaa071321c5177c8471312c565ad86d4b245d7/gplugins/devsim/cv.py>`_ if any point does not converge.
    """
    vg = tuple(float(v) for v in vg)
    dv_fb = proc.values()["dv_fb_v"]
    stack = stack_of(proc)
    res, nodes = _sweep_stack(
        stack,
        [v - dv_fb for v in vg],
        mesh=mesh,
        constants=constants,
        method=method,
        freq_hz=freq_hz,
        rel_tol=rel_tol,
        name=f"moscap1d_{proc.device}",
    )
    if res.unit != "F/cm^2":
        raise RuntimeError(f"a 1D sweep gives F/cm^2, got {res.unit!r}")
    points = tuple(Point(p.converged, p.iterations, p.rel_error, p.abs_error) for p in res.points)
    if len(res.cgg) != len(vg) or not all(p.converged for p in points):
        raise RuntimeError("sweep_cv returned a short or unconverged sweep")
    return MoscapCV(
        device=proc.device,
        vg=vg,
        c_per_area_ff_um2=tuple(f_per_cm2_to_ff_per_um2(c) for c in res.cgg),
        points=points,
        method=method,
        constants=constants,
        mesh=mesh,
        stack=stack,
        rel_tol=rel_tol,
        node_count=nodes,
    )


# --- result files ----------------------------------------------------------------------------

CSV_COLUMNS = ("vg", "c_per_area", "rel_error", "abs_error", "iterations")
CSV_UNITS = "vg=V c_per_area=fF/um^2 rel_error=1 abs_error=V iterations=1"


def _write_csv(path: Path, columns: dict, meta: dict[str, str]) -> None:
    """:func:`gf180tcad.io.write_csv`'s format, with ``int`` cells written as integers.

    io.write_csv (a SPICE generator module, which this task may not edit) writes every cell as
    a float; the iteration counts are integers. Floats are written with ``repr`` as there, and
    :func:`gf180tcad.io.read_csv` reads the file back.
    """
    names = list(columns)
    lines = [f"# {k}: {meta[k]}" for k in sorted(meta)]
    lines.append(",".join(names))
    for row in zip(*(columns[n] for n in names), strict=True):
        cells = []
        for x in row:
            if isinstance(x, bool) or not isinstance(x, int | float):
                raise TypeError(f"CSV cell {x!r} is not a number")
            cells.append(str(x) if isinstance(x, int) else repr(float(x)))
        lines.append(",".join(cells))
    Path(path).write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def tunable_origins(
    proc: ProcessDescription, params: str, calibration_sha256: str | None = None
) -> dict[str, dict]:
    """Where each applied tunable value comes from, for the result metadata.

    ``start``: the process file's ``start_kind`` and ``start_source``. ``calibrated``: the
    sha256 of the calibration file the value was read from.
    """
    out = {}
    for n in TUNABLES:
        p = proc.params[n]
        if params == "start":
            if calibration_sha256 is not None:
                raise ValueError("start values come from the process file, not a calibration")
            out[n] = {
                "origin": "start",
                "start_kind": p.start_kind,
                "start_source": p.start_source,
                "value": p.value,
            }
        elif params == "calibrated":
            if calibration_sha256 is None:
                raise ValueError("calibrated values need the calibration file's sha256")
            out[n] = {
                "calibration_sha256": calibration_sha256,
                "origin": "calibrated",
                "value": p.value,
            }
        else:
            raise ValueError(f"params must be 'start' or 'calibrated', got {params!r}")
    return out


def constants_dict(c: Constants = CONSTANTS) -> dict[str, float]:
    """The constants as recorded in result metadata, with the derived ``n_i_cm3`` and ``vt_v``."""
    return {**asdict(c), "n_i_cm3": c.n_i_cm3, "vt_v": c.vt_v}


def write(
    cv: MoscapCV,
    out: Path,
    *,
    proc: ProcessDescription,
    params: str,
    mesh_source: str,
    calibration_sha256: str | None = None,
) -> None:
    """Write :data:`PER_AREA_CSV` and :data:`PER_AREA_META` of ``cv`` into ``out``.

    ``proc`` is the process description ``cv`` was simulated with (its device and stack must
    match); ``mesh_source`` the repo-relative file its mesh spec was read from;
    ``calibration_sha256`` is the calibration file's sha256 for ``params="calibrated"``.
    """
    out = Path(out)
    if proc.device != cv.device or stack_of(proc) != cv.stack:
        raise ValueError(f"{proc.device}: not the process description of this C-V")
    columns = {
        "vg": cv.vg,
        "c_per_area": cv.c_per_area_ff_um2,
        "rel_error": [p.rel_error for p in cv.points],
        "abs_error": [p.abs_error for p in cv.points],
        "iterations": [int(p.iterations) for p in cv.points],
    }
    meta = {
        "device": cv.device,
        "dim": "1",
        "method": cv.method,
        "params": params,
        "units": CSV_UNITS,
    }
    _write_csv(out / PER_AREA_CSV, columns, meta)
    c = cv.constants
    origins = tunable_origins(proc, params, calibration_sha256)
    spacing = cv.mesh.spacing_um(POLY, OXIDE, BODY)
    io.write_json(
        out / PER_AREA_META,
        {
            "constants": constants_dict(c),
            "device": cv.device,
            "dim": 1,
            "dv_fb_shift": "rigid: solved at vg - dv_fb_v, reported at vg",
            "mesh": cv.mesh.as_dict(),
            "mesh_source": mesh_source,
            "mesh_1d_spacing_um": {k: list(v) for k, v in spacing.items()},
            "mesh_1d_note": "oxide spacing is min(h_ox, neighbour) at each face (exact: the "
            "oxide potential is linear)",
            "method": cv.method,
            "node_count": cv.node_count,
            "param_sha256": param_sha256({n: o["value"] for n, o in origins.items()}),
            "params": params,
            "points": len(cv.vg),
            "stack": asdict(cv.stack),
            "sweep": {
                "abs_tol_v": ABS_TOL,
                "dv_qs_v": DV_QS,
                "max_iterations": MAX_ITERATIONS,
                "rel_tol": cv.rel_tol,
            },
            "tunables": origins,
            "unit": "fF/um^2",
        },
    )


def read(job_dir: Path) -> MoscapCV:
    """A :class:`MoscapCV` from a job directory written by :func:`write` (bit-exact floats)."""
    job_dir = Path(job_dir)
    cols, meta = io.read_csv(job_dir / PER_AREA_CSV)
    info = json.loads((job_dir / PER_AREA_META).read_bytes())
    consts = {k: v for k, v in info["constants"].items() if k not in ("n_i_cm3", "vt_v")}
    points = tuple(
        Point(True, int(it), float(r), float(a))
        for r, a, it in zip(cols["rel_error"], cols["abs_error"], cols["iterations"], strict=True)
    )
    return MoscapCV(
        device=meta["device"],
        vg=tuple(float(v) for v in cols["vg"]),
        c_per_area_ff_um2=tuple(float(v) for v in cols["c_per_area"]),
        points=points,
        method=meta["method"],
        constants=Constants(**consts),
        mesh=MeshSpec(**info["mesh"]),
        stack=Stack(**info["stack"]),
        rel_tol=info["sweep"]["rel_tol"],
        node_count=info["node_count"],
    )
