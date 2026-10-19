# SPDX-License-Identifier: Apache-2.0
"""The 2D :term:`MOS capacitor <MOSCAP>` of ``nfet_05v0`` and ``pfet_05v0`` from the PDK cell.

:func:`simulate` builds the cross-section of the `gf180mcu
<https://github.com/gdsfactory/gf180mcu>`_ cell across its gate (:mod:`gf180tcad.tcad.stack`),
meshes it with `gplugins.devsim.create_2Duz_simulation
<https://github.com/mithro/gplugins/blob/e3ea06c6b8bd0f4c8f1f3da4c40c1e3d7f9a6f5b/gplugins/devsim/get_simulation.py>`_
(the plugin's single-threaded meshwell path, :meth:`MeshSpec.to_resolution_specs
<gf180tcad.tcad.mesh.MeshSpec.to_resolution_specs>`), assigns the analytic doping
(``gplugins.devsim.doping``), solves the equilibrium with the typed contacts and sweeps the gate
with ``gplugins.devsim.sweep_cv``:

- ``method="qs"``: equilibrium Poisson-Boltzmann with every non-gate contact at 0 V, the
  counterpart of the :term:`SPICE` :term:`Cgg` of :term:`BSIM4` ``capMod=2`` (as in 1D). Solved
  in double precision (``extended_precision=False``), which the plugin checks agrees within the
  QS solver noise and which is about twice as fast on a 2D mesh;
- ``method="ac"``: small-signal AC at ``freq_hz`` on the drift-diffusion point, every contact
  with its own source (in extended precision, which AC needs). With ``with_sd`` the source and
  drain supply the inversion charge, so 1 MHz recovers to inversion as SPICE does, and
  ``cgx`` holds Cxg = -dQ_x/dVg of every non-gate contact (charge conservation:
  Cgg = sum of Cxg).

``dv_fb_v`` is the same rigid gate-bias shift as in 1D: solved at ``vg - dv_fb_v``, reported at
``vg``. The C per area divides the per-width Cgg (F/cm) by the drawn gate length L; the per-width
values times the drawn W give the whole device. DLC and the BSIM4 parasitics are never applied
in 2D: the cross-section has its own overlap and fringe.

**The meshed geometry is checked** (:class:`GeometryError`): the oxide's node coordinates must
span exactly ``t_ox_eff_nm`` (within the vertex grid
:data:`gf180tcad.tcad.stack.POINT_TOLERANCE_UM`) and the gate exactly L. meshwell's default
vertex grid would round a 15.2 nm oxide to 15 nm, a 1.3 % too large Cox; that was the C/Cox > 1
artefact of the Phase 2 research spike (:doc:`/limitations/moscap2d`).

This module imports the plugin lazily (it needs the TCAD image), so it imports on the host. It
is TCAD code, not one of the SPICE generator modules
(:data:`gf180tcad.reference.GENERATOR_MODULES`).
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from gf180tcad import io
from gf180tcad.devices import Geometry, geometry_id
from gf180tcad.tcad import stack as stack_mod
from gf180tcad.tcad.analytic import f_per_cm2_to_ff_per_um2
from gf180tcad.tcad.calibration import param_sha256
from gf180tcad.tcad.mesh import MeshSpec
from gf180tcad.tcad.moscap1d import (
    ABS_TOL,
    DV_QS,
    MAX_ITERATIONS,
    REL_TOL,
    Point,
    _write_csv,
    constants_dict,
    plugin_constants,
    tunable_origins,
)
from gf180tcad.tcad.process import CONSTANTS, Constants, ProcessDescription

# The AC frequency of the SPICE cv sweep (devices.SWEEPS "cv": 1 MHz), used for cgx.
AC_FREQ_HZ = 1e6

# Result file names in each job directory (<root>/<device>/<params>/<gid>/).
CV_CSV = "cv.csv"
CGX_CSV = "cgx.csv"
MESH_FILE = "mesh.msh"
META_JSON = "cv.meta.json"

# 1 F/cm (per unit width) = 1e11 fF/um.
F_PER_CM_TO_FF_PER_UM = 1e11

# The DEVSIM names of the 2D device and its mesh.
_DEVICE, _MESH = "moscap2d", "moscap2d_mesh"


class GeometryError(RuntimeError):
    """The meshed cross-section does not have the requested oxide thickness or gate length."""


@dataclass(frozen=True)
class MoscapCV2D:
    """A 2D MOS capacitor C-V: a :class:`gf180tcad.tcad.meshconv.CVCurve` and more.

    ``c_per_area_ff_um2`` is Cgg per drawn gate area; ``cgg_ff_per_um`` the same per unit
    width (fF/um); ``cgx`` (AC only, else empty) maps every non-gate contact to Cxg per unit
    width (fF/um). ``meshed_t_ox_nm`` and ``meshed_l_um`` are the oxide thickness and gate
    length the mesh actually has.
    """

    device: str
    geometry: Geometry | None
    vg: tuple[float, ...]
    c_per_area_ff_um2: tuple[float, ...]
    cgg_ff_per_um: tuple[float, ...]
    cgx: dict[str, tuple[float, ...]]
    points: tuple[Point, ...]
    method: str
    freq_hz: float | None
    with_sd: bool
    mesh: MeshSpec
    node_count: int
    l_um: float
    w_um: float
    t_ox_nm: float
    meshed_t_ox_nm: float
    meshed_l_um: float
    rel_tol: float
    sd_peak_cm3: float | None
    constants: Constants

    @property
    def non_gate_contacts(self) -> tuple[str, ...]:
        """The contacts of the device other than the gate, sorted."""
        return tuple(sorted(self.cgx))


def _node_count(device: str) -> int:
    import devsim

    pts = set()
    for region in devsim.get_region_list(device=device):
        xs = devsim.get_node_model_values(device=device, region=region, name="x")
        ys = devsim.get_node_model_values(device=device, region=region, name="y")
        pts.update(zip(xs, ys, strict=True))
    return len(pts)


def _span_um(device: str, region: str, axis: str) -> tuple[float, float]:
    import devsim

    v = devsim.get_node_model_values(device=device, region=region, name=axis)
    return min(v) * 1e4, max(v) * 1e4


def check_geometry(xs: stack_mod.CrossSection, device: str = _DEVICE) -> tuple[float, float]:
    """``(t_ox_nm, l_um)`` of the meshed device; raises :class:`GeometryError` unless exact.

    Exact means that every region of the stack spans exactly its level (z from ``zmin`` to
    ``zmin + thickness``: the oxide, the poly, the body and every electrode) and its drawn u
    extent (the gate's L, the body's whole domain), within
    :data:`gf180tcad.tcad.stack.POINT_TOLERANCE_UM`. meshwell's default vertex grid would
    round every z to 1 nm.
    """
    tol = stack_mod.POINT_TOLERANCE_UM
    u_extent = {
        stack_mod.OXIDE: xs.gate_u,
        stack_mod.POLY: xs.gate_u,
        stack_mod.BODY: (0.0, xs.length_um),
    }
    for region, (_, zmin, thickness, _) in xs.levels.items():
        y0, y1 = _span_um(device, region, "y")
        if abs(y0 - zmin) > tol or abs(y1 - (zmin + thickness)) > tol:
            raise GeometryError(
                f"the meshed {region} spans y = {y0!r}..{y1!r} um, not "
                f"{zmin!r}..{zmin + thickness!r} um"
            )
        if region in u_extent:
            x0, x1 = _span_um(device, region, "x")
            u0, u1 = u_extent[region]
            if abs(x0 - u0) > tol or abs(x1 - u1) > tol:
                raise GeometryError(
                    f"the meshed {region} spans u = {x0!r}..{x1!r} um, not {u0!r}..{u1!r} um"
                )
    y0, y1 = _span_um(device, stack_mod.OXIDE, "y")
    x0, x1 = _span_um(device, stack_mod.OXIDE, "x")
    return (y1 - y0) * 1e3, x1 - x0


def build_device(
    xs: stack_mod.CrossSection,
    mesh: MeshSpec,
    *,
    constants: Constants = CONSTANTS,
    rel_tol: float = REL_TOL,
    mesh_file: Path | str = MESH_FILE,
):
    """Mesh and solve (at equilibrium) the cross-section ``xs``: the plugin's ``DDComponent``.

    The mesh is written to ``mesh_file`` (MSH 2.2). The caller deletes the device
    (``.delete_device()``); on failure it is deleted here.
    """
    import devsim
    from gplugins.devsim import Contact, InterfaceRef
    from gplugins.devsim.doping import assign_doping
    from gplugins.devsim.get_simulation import create_2Duz_simulation
    from gplugins.devsim.get_solver import DDComponent

    contacts = [
        Contact(name, InterfaceRef(electrode, xs.contact_region(name)), "ohmic")
        for name, electrode in xs.contacts.items()
    ]
    layer_stack = xs.layer_stack()
    res = mesh.to_resolution_specs(
        stack_mod.POLY, stack_mod.OXIDE, stack_mod.BODY, background=xs.background
    )
    h_min = min(mesh.h_poly_nm, mesh.h_si_surface_nm, mesh.h_ox_nm) * 1e-3
    create_2Duz_simulation(
        component=xs.component,
        xsection_bounds=xs.line,
        full_layer_stack=layer_stack,
        physical_layer_stack=layer_stack,
        doping_info={},
        contacts=contacts,
        resolutions=dict(res),
        default_resolution_min=0.5 * h_min,
        default_resolution_max=mesh.h_si_bulk_nm * 1e-3,
        background_tag=xs.background,
        background_padding=(0.0, 0.0, 0.0, 0.0),
        temp_file_name=str(mesh_file),
        devsim_mesh_name=_MESH,
        devsim_device_name=_DEVICE,
        devsim_simulation_filename=None,
        point_tolerance=stack_mod.POINT_TOLERANCE_UM,
    )
    try:
        surfaces = {stack_mod.BODY: (0.0, -1), stack_mod.POLY: (xs.t_ox_nm * 1e-3, 1)}
        for region, (donors, acceptors) in xs.doping.items():
            surface, sign = surfaces[region]
            assign_doping(
                _DEVICE, region, donors=donors, acceptors=acceptors, depth_axis="y",
                surface_um=surface, depth_sign=sign,
            )  # fmt: skip
        return DDComponent.from_device(
            device=_DEVICE,
            mesh=_MESH,
            region_classes=xs.region_classes,
            contacts=contacts,
            constants=plugin_constants(constants, xs.eps_ox),
            atol=1e30,
            rtol=rel_tol,
            max_iter=MAX_ITERATIONS,
            extended_precision=True,  # the equilibrium drift-diffusion solve needs it
        )
    except BaseException:
        if _DEVICE in devsim.get_device_list():
            devsim.delete_device(device=_DEVICE)
        devsim.delete_mesh(mesh=_MESH)
        raise


def simulate(
    proc: ProcessDescription,
    geometry: Geometry | None,
    *,
    vg: Sequence[float],
    with_sd: bool,
    method: Literal["qs", "ac"],
    mesh: MeshSpec,
    freq_hz: float | None = None,
    rel_tol: float = REL_TOL,
    structure: stack_mod.CrossSection | None = None,
    mesh_file: Path | str = MESH_FILE,
    log: Callable[[str], None] | None = None,
    constants: Constants = CONSTANTS,
) -> MoscapCV2D:
    """The 2D C-V of ``proc`` at ``geometry`` (the PDK cell), at the gate biases ``vg`` (V).

    ``structure`` replaces the cell's cross-section (e.g. :func:`gf180tcad.tcad.stack.uniform`;
    ``geometry`` may then be None). ``log`` receives one progress line per bias point (index,
    gate bias and elapsed time). Raises the plugin's ``CVConvergenceError`` if any point does
    not converge, and :class:`GeometryError` if the mesh does not have the drawn geometry.
    """
    from gplugins.devsim import sweep_cv

    vg = tuple(float(v) for v in vg)
    dv_fb = proc.values()["dv_fb_v"]
    if structure is None:
        if geometry is None:
            raise ValueError("pass a geometry (the PDK cell) or a structure")
        structure = stack_mod.build(proc, stack_mod.cell(proc.device, geometry), with_sd=with_sd)
    elif structure.with_sd != with_sd:
        raise ValueError(f"the structure has with_sd={structure.with_sd}, not {with_sd}")
    if method == "ac" and freq_hz is None:
        freq_hz = AC_FREQ_HZ
    t0 = time.monotonic()
    dd = build_device(structure, mesh, constants=constants, rel_tol=rel_tol, mesh_file=mesh_file)
    try:
        nodes = _node_count(_DEVICE)
        t_ox_nm, l_um = check_geometry(structure)
        if log is not None:
            log(f"meshed: {nodes} nodes, t_ox {t_ox_nm!r} nm, L {l_um!r} um, "
                f"{time.monotonic() - t0:.1f} s")  # fmt: skip

        def progress(stage: str, i: int, v: float) -> None:
            if log is not None:
                log(f"{stage} bias {i + 1}/{len(vg)} vg {v + dv_fb!r} V "
                    f"elapsed {time.monotonic() - t0:.1f} s")  # fmt: skip

        res = sweep_cv(
            dd,
            stack_mod.GATE,
            [v - dv_fb for v in vg],
            method=method,
            freq_hz=freq_hz if method == "ac" else None,
            dv_qs=DV_QS,
            rel_tol=rel_tol,
            abs_tol=ABS_TOL,
            max_iterations=MAX_ITERATIONS,
            extended_precision=method == "ac",
            progress=progress,
        )
    finally:
        dd.delete_device()
    if res.unit != "F/cm":
        raise RuntimeError(f"a 2D sweep gives F/cm, got {res.unit!r}")
    points = tuple(Point(p.converged, p.iterations, p.rel_error, p.abs_error) for p in res.points)
    if len(res.cgg) != len(vg) or not all(p.converged for p in points):
        raise RuntimeError("sweep_cv returned a short or unconverged sweep")
    l_cm = structure.l_um * 1e-4
    others = sorted(c for c in structure.contacts if c != stack_mod.GATE)
    if method == "ac" and sorted(res.cgx) != others:
        raise RuntimeError(f"cgx has {sorted(res.cgx)}, the device's non-gate contacts {others}")
    return MoscapCV2D(
        device=proc.device,
        geometry=geometry,
        vg=vg,
        c_per_area_ff_um2=tuple(f_per_cm2_to_ff_per_um2(c / l_cm) for c in res.cgg),
        cgg_ff_per_um=tuple(c * F_PER_CM_TO_FF_PER_UM for c in res.cgg),
        cgx={c: tuple(x * F_PER_CM_TO_FF_PER_UM for x in v) for c, v in res.cgx.items()},
        points=points,
        method=method,
        freq_hz=freq_hz if method == "ac" else None,
        with_sd=with_sd,
        mesh=mesh,
        node_count=nodes,
        l_um=structure.l_um,
        w_um=structure.w_um,
        t_ox_nm=structure.t_ox_nm,
        meshed_t_ox_nm=t_ox_nm,
        meshed_l_um=l_um,
        rel_tol=rel_tol,
        sd_peak_cm3=structure.sd_peak_cm3,
        constants=constants,
    )


# --- result files ----------------------------------------------------------------------------

CV_COLUMNS = ("vg", "c_per_area", "cgg_per_um", "cgg_total", "rel_error", "abs_error",
              "iterations")  # fmt: skip
CV_UNITS = (
    "vg=V c_per_area=fF/um^2 cgg_per_um=fF/um cgg_total=fF rel_error=1 abs_error=V iterations=1"
)


def job_dir(root: Path, device: str, params: str, geometry: Geometry) -> Path:
    """``<root>/<device>/<params>/<gid>``."""
    return Path(root) / device / params / geometry_id(geometry)


def write(
    qs: MoscapCV2D,
    ac: MoscapCV2D,
    out: Path,
    *,
    proc: ProcessDescription,
    params: str,
    mesh_source: str,
    calibration_sha256: str | None = None,
) -> None:
    """Write :data:`CV_CSV` (the QS sweep ``qs``), :data:`CGX_CSV` (the AC sweep ``ac``) and
    :data:`META_JSON` into ``out``. The mesh file is written by :func:`simulate` itself."""
    out = Path(out)
    if qs.method != "qs" or ac.method != "ac" or qs.vg != ac.vg or qs.device != proc.device:
        raise ValueError("write() takes a QS and an AC sweep of the same device and biases")
    w = qs.w_um
    _write_csv(
        out / CV_CSV,
        {
            "vg": qs.vg,
            "c_per_area": qs.c_per_area_ff_um2,
            "cgg_per_um": qs.cgg_ff_per_um,
            "cgg_total": [c * w for c in qs.cgg_ff_per_um],
            "rel_error": [p.rel_error for p in qs.points],
            "abs_error": [p.abs_error for p in qs.points],
            "iterations": [int(p.iterations) for p in qs.points],
        },
        {"device": qs.device, "dim": "2", "method": "qs", "params": params, "units": CV_UNITS},
    )
    contacts = ac.non_gate_contacts
    cols = {"vg": ac.vg, "cgg_per_um": ac.cgg_ff_per_um}
    cols.update({f"c{c}g_per_um": ac.cgx[c] for c in contacts})
    cols["sum_rel_error"] = [
        math.fsum(ac.cgx[c][i] for c in contacts) / ac.cgg_ff_per_um[i] - 1
        for i in range(len(ac.vg))
    ]
    cols["rel_error"] = [p.rel_error for p in ac.points]
    cols["iterations"] = [int(p.iterations) for p in ac.points]
    _write_csv(
        out / CGX_CSV,
        cols,
        {
            "device": ac.device,
            "dim": "2",
            "freq_hz": repr(ac.freq_hz),
            "method": "ac",
            "params": params,
            "units": "vg=V c*_per_um=fF/um (per unit width) sum_rel_error=1 rel_error=1 "
            "iterations=1",
        },
    )
    origins = tunable_origins(proc, params, calibration_sha256)
    io.write_json(
        out / META_JSON,
        {
            "ac_freq_hz": ac.freq_hz,
            "constants": constants_dict(qs.constants),
            "contacts": ["gate", *contacts],
            "device": qs.device,
            "dim": 2,
            "dv_fb_shift": "rigid: solved at vg - dv_fb_v, reported at vg",
            "geometry": None if qs.geometry is None else asdict(qs.geometry),
            "l_um": qs.l_um,
            "mesh": qs.mesh.as_dict(),
            "mesh_source": mesh_source,
            "meshed_l_um": qs.meshed_l_um,
            "meshed_t_ox_nm": qs.meshed_t_ox_nm,
            "node_count": qs.node_count,
            "normalisation": "c_per_area = Cgg per unit width / drawn L; cgg_total = per unit "
            "width * drawn W; no DLC or BSIM4 parasitics",
            "param_sha256": param_sha256({n: o["value"] for n, o in origins.items()}),
            "params": params,
            "points": len(qs.vg),
            "point_tolerance_um": stack_mod.POINT_TOLERANCE_UM,
            "sd_peak_cm3": qs.sd_peak_cm3,
            "sweep": {
                "abs_tol_v": ABS_TOL,
                "dv_qs_v": DV_QS,
                "max_iterations": MAX_ITERATIONS,
                "qs_extended_precision": False,
                "rel_tol": qs.rel_tol,
            },
            "t_ox_nm": qs.t_ox_nm,
            "tunables": origins,
            "w_um": qs.w_um,
            "with_sd": qs.with_sd,
        },
    )


def read_cv(job: Path) -> tuple[tuple[float, ...], tuple[float, ...], dict]:
    """``(vg, c_per_area, meta)`` of a job directory (bit-exact floats)."""
    cols, _ = io.read_csv(Path(job) / CV_CSV)
    meta = json.loads((Path(job) / META_JSON).read_bytes())
    return tuple(cols["vg"]), tuple(cols["c_per_area"]), meta
