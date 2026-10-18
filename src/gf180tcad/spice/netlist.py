# SPDX-License-Identifier: Apache-2.0
"""SPICE netlists for one device / geometry / sweep / corner / temperature.

Engine-agnostic parts (reused by the Xyce netlister):

- :func:`instance_params`: the PDK xschem symbol defaults (``nfet_05v0.sym``/``pfet_05v0.sym``)
  for nf = 1, computed in exact decimal arithmetic.
- :func:`bias_plan`: which terminal is swept (inner, fastest), which is nested (outer), which are
  fixed, with device polarity applied, and the exact bias grid in simulation order.

Topology: the source is node 0; independent voltage sources ``vd``, ``vg``, ``vb`` drive the
drain, gate and bulk nodes ``d``, ``g``, ``b`` against ground; the device is the PDK wrapper
subcircuit ``xdut d g 0 b <model> ...``. Polarity: Vds = polarity*|Vds|, Vgs = polarity*Vgs,
Vbs = -polarity*|Vbs| (``cv``'s signed gate grid is multiplied by the polarity too, so a positive
grid value means inversion for both nfet and pfet).

Result columns (:data:`NGSPICE_VECTORS` maps each to the raw-file vector and its sign):

- DC sweeps: ``vd vg vb`` (node voltages) and ``id ig ib``, the current flowing INTO the device
  terminal, i.e. minus the source branch current (ngspice's branch current flows into the source's
  + node). An on-state pfet therefore has negative ``id``.
- ``cv``: ``vg`` and ``cgg`` = -imag(i(vg)) / (2*pi*f) with a 1 V AC source on the gate: the
  current into the gate is -i(vg) = j*2*pi*f*Cgg, so this is Cgg itself, positive. It is computed
  in the ``.control`` loop, which collects one ``ac`` point per gate bias into a single plot.

ngspice setup (no ~/.spiceinit is read in the sandbox; the PDK's own
``libs.tech/ngspice/.spiceinit`` is empty, so no compatibility mode is selected):

- ``set num_threads=1`` in the ``.control`` block before the first analysis. ngspice 47's
  system ``spinit`` sets ``num_threads=8``; a ``.option num_threads=1`` line is NOT honoured
  (the BSIM4 OpenMP loop still ran 8 threads), the ``.control`` variable is (1 thread).
- ``set filetype=binary`` and an explicit ``write`` of the result vectors to :data:`RAW_NAME`
  (relative to the working directory), so ngspice is run as ``ngspice -b <netlist>`` without
  ``-r`` (``-r`` together with a ``.control`` ``run`` makes ngspice simulate twice).
- ``.include design.ngspice`` (sw_stat_global = 0, sw_stat_mismatch = 0) and
  ``.lib sm141064.ngspice <corner>``; nothing statistical is included or overridden.
"""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass
from decimal import Decimal

import numpy as np

from gf180tcad.devices import CORNERS, Device, Geometry, Sweep, geometry_id
from gf180tcad.pdk import PdkInfo

RAW_NAME = "out.raw"
# result column -> (vector name in the raw file, factor); ngspice's ``write`` renames ``let``
# vectors by type (``let vd = v(d)`` is written as ``v(vd)``), so the sign is applied in Python.
NGSPICE_VECTORS: dict[str, dict[str, tuple[str, float]]] = {
    "dc": {
        "vd": ("v(d)", 1.0),
        "vg": ("v(g)", 1.0),
        "vb": ("v(b)", 1.0),
        "id": ("i(vd)", -1.0),
        "ig": ("i(vg)", -1.0),
        "ib": ("i(vb)", -1.0),
    },
    "cv": {"vg": ("vg", 1.0), "cgg": ("cgg", 1.0)},
}

_TERMINALS = ("d", "g", "b")
_DIFF = Decimal("0.18")  # S/D diffusion length in µm (xschem symbol: 0.18u)
_MICRO = Decimal("1e-6")
_MODEL_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _dec(x: float) -> Decimal:
    return Decimal(repr(x))


def _fmt(d: Decimal) -> str:
    return format(d.normalize(), "e")


def instance_params(device: Device, g: Geometry) -> dict[str, str]:
    """Instance parameters from the PDK xschem symbol template, evaluated for nf = 1.

    ``ad = as = W*0.18u``, ``pd = ps = 2*(W + 0.18u)``, ``nrd = nrs = 0.18u/W``,
    ``sa = sb = sd = 0``, ``m = 1``. Values are computed exactly from ``repr`` of the µm sizes
    (no float rounding) and written in shortest exponent form, e.g. W = 10 → ad ``1.8e-12``.
    The template is the same for nfet_05v0 and pfet_05v0.
    """
    del device  # same template for both polarities; kept for the engine-agnostic signature
    w = _dec(g.w_um)
    area = _fmt(w * _DIFF * _MICRO * _MICRO)
    perim = _fmt(2 * (w + _DIFF) * _MICRO)
    nrs = _fmt(_DIFF / w)
    return {
        "l": f"{g.l_um!r}u",
        "w": f"{g.w_um!r}u",
        "nf": "1",
        "ad": area,
        "as": area,
        "pd": perim,
        "ps": perim,
        "nrd": nrs,
        "nrs": nrs,
        "sa": "0",
        "sb": "0",
        "sd": "0",
        "m": "1",
    }


@dataclass(frozen=True)
class Axis:
    terminal: str  # "d", "g" or "b"
    values: tuple[float, ...]  # node voltages with polarity applied


@dataclass(frozen=True)
class BiasPlan:
    """Terminal voltages (polarity applied) for one sweep; ``outer`` varies slowest."""

    kind: str
    fixed: tuple[tuple[str, float], ...]  # (terminal, volts) pairs: immutable and hashable
    inner: Axis
    outer: Axis | None
    freq_hz: float | None

    @property
    def npoints(self) -> int:
        return len(self.inner.values) * (len(self.outer.values) if self.outer else 1)

    def grid(self) -> dict[str, np.ndarray]:
        """Exact node voltages ``vd``, ``vg``, ``vb`` per simulated point, in simulation order."""
        n_out = len(self.outer.values) if self.outer else 1
        n_in = len(self.inner.values)
        cols: dict[str, np.ndarray] = {}
        for t in _TERMINALS:
            if t == self.inner.terminal:
                col = np.tile(np.array(self.inner.values, dtype=np.float64), n_out)
            elif self.outer is not None and t == self.outer.terminal:
                col = np.repeat(np.array(self.outer.values, dtype=np.float64), n_in)
            else:
                col = np.full(n_in * n_out, dict(self.fixed)[t], dtype=np.float64)
            cols[f"v{t}"] = col
        return cols


def _signed(sign: int, values: tuple[float, ...]) -> tuple[float, ...]:
    # "+ 0.0" turns -0.0 into 0.0, so a pfet's zero bias is written "0.0", not "-0.0".
    return tuple(sign * v + 0.0 for v in values)


def bias_plan(device: Device, sweep: Sweep) -> BiasPlan:
    """Map a magnitude sweep onto terminal voltages for ``device``.

    idvg: Vgs inner, Vbs outer (Vds fixed); idvd: Vds inner, Vgs outer (Vbs fixed);
    cv: Vgs inner (Vds, Vbs fixed). An outer axis with a single value becomes fixed.
    """
    p = device.polarity
    signed = {"d": _signed(p, sweep.vds), "g": _signed(p, sweep.vgs), "b": _signed(-p, sweep.vbs)}
    names = {"d": "vds", "g": "vgs", "b": "vbs"}
    if sweep.kind == "idvg":
        inner, outer = "g", "b"
    elif sweep.kind == "idvd":
        inner, outer = "d", "g"
    elif sweep.kind == "cv":
        inner, outer = "g", None
        if sweep.freq_hz is None or not (math.isfinite(sweep.freq_hz) and sweep.freq_hz > 0):
            raise ValueError(f"cv sweep {sweep.name!r} needs a positive freq_hz")
    else:
        raise ValueError(f"unknown sweep kind {sweep.kind!r}")
    if outer is not None and len(signed[outer]) == 1:
        outer = None
    fixed = {}
    for t in _TERMINALS:
        if t in (inner, outer):
            continue
        if len(signed[t]) != 1:
            raise ValueError(
                f"{sweep.kind} sweep {sweep.name!r}: {names[t]} must have exactly one value, "
                f"got {len(signed[t])}"
            )
        fixed[t] = signed[t][0]
    return BiasPlan(
        kind=sweep.kind,
        fixed=tuple(fixed.items()),
        inner=Axis(inner, signed[inner]),
        outer=Axis(outer, signed[outer]) if outer else None,
        freq_hz=sweep.freq_hz,
    )


def _dc_range(axis: Axis) -> str:
    """``<source> <start> <stop> <step>`` for an evenly spaced axis (exact decimal spacing)."""
    vals = axis.values
    if len(vals) == 1:
        step = 1.0
    else:
        steps = {_dec(b) - _dec(a) for a, b in itertools.pairwise(vals)}
        if len(steps) != 1 or 0 in steps:
            raise ValueError(f"v{axis.terminal} values are not evenly spaced: cannot use .dc")
        step = float(steps.pop())
    return f"v{axis.terminal} {vals[0]!r} {vals[-1]!r} {step!r}"


def ngspice_netlist(
    device: Device, g: Geometry, sweep: Sweep, corner: str, temp_c: float, pdk: PdkInfo
) -> str:
    """Return the ngspice netlist text (see the module docstring for conventions)."""
    if corner not in CORNERS:
        raise ValueError(f"corner must be one of {CORNERS}, got {corner!r}")
    if not math.isfinite(temp_c):
        raise ValueError(f"temp_c must be finite, got {temp_c!r}")
    if not _MODEL_RE.fullmatch(device.spice_model):
        raise ValueError(f"bad spice model name {device.spice_model!r}")
    plan = bias_plan(device, sweep)
    start = {**dict(plan.fixed), plan.inner.terminal: plan.inner.values[0]}
    if plan.outer is not None:
        start[plan.outer.terminal] = plan.outer.values[0]

    params = " ".join(f"{k}={v}" for k, v in instance_params(device, g).items())
    title = (
        f"* gf180tcad ngspice {device.name} {geometry_id(g)} {sweep.name} "
        f"corner={corner} temp_c={float(temp_c)!r}"
    )
    lines = [
        title,
        f".include {pdk.ngspice_design}",
        f".lib {pdk.ngspice_lib} {corner}",
        f".temp {float(temp_c)!r}",
    ]
    for t in _TERMINALS:
        ac = " ac 1" if plan.kind == "cv" and t == "g" else ""
        lines.append(f"v{t} {t} 0 dc {start[t]!r}{ac}")
    lines.append(f"xdut d g 0 b {device.spice_model} {params}")
    if plan.kind == "cv":
        lines += _cv_control(plan)
    else:
        dc = _dc_range(plan.inner)
        if plan.outer is not None:
            dc += " " + _dc_range(plan.outer)
        lines += [
            f".dc {dc}",
            ".control",
            "set num_threads=1",
            "set filetype=binary",
            "run",
            f"write {RAW_NAME} {' '.join(v for v, _ in NGSPICE_VECTORS['dc'].values())}",
            ".endc",
        ]
    lines.append(".end")
    return "\n".join(lines) + "\n"


def _cv_control(plan: BiasPlan) -> list[str]:
    """One ``ac`` point per gate bias; results collected into a single plot and written once.

    ``vg`` records ``@vg[dc]``, the gate source's DC value read back from the circuit after the
    ``ac`` run, not the loop variable: if ``alter`` had not taken effect the grid check fails
    (shown in the sandbox: with the ``alter`` line removed the check fails by 10 V, whereas
    recording ``$v`` passed with a constant Cgg). ``vg`` starts as a 1e30 sentinel, so a point the
    loop skipped cannot pass the grid check either.
    """
    f = repr(float(plan.freq_hz))
    n = len(plan.inner.values)
    return [
        ".control",
        "set num_threads=1",
        "set filetype=binary",
        "setplot new",
        "set resplot=$curplot",
        f"let vg = vector({n})*0 + 1e30",
        f"let cgg = vector({n})*0",
        "let k = 0",
        "foreach v " + " ".join(repr(v) for v in plan.inner.values),
        "alter vg dc = $v",
        f"ac lin 1 {f} {f}",
        f"let {{$resplot}}.cgg[{{$resplot}}.k] = -imag(i(vg))/(2*pi*{f})",
        "let {$resplot}.vg[{$resplot}.k] = @vg[dc]",
        "let {$resplot}.k = {$resplot}.k + 1",
        "destroy $curplot",
        "end",
        "setplot $resplot",
        f"write {RAW_NAME} {' '.join(v for v, _ in NGSPICE_VECTORS['cv'].values())}",
        ".endc",
    ]
