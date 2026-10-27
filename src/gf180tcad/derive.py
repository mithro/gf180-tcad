# SPDX-License-Identifier: Apache-2.0
"""The closed table of formulas a render may use to derive a quantity from committed outputs.

A render manifest (:mod:`gf180tcad.render.manifest`) names a derived quantity's formula by its
key in :data:`FORMULAS`, lists the manifest entries that are its inputs, in the order of the
function's parameters, and records the value. The test re-evaluates the formula from the inputs
(:func:`evaluate`). Each function is pure numpy, carries its equation in its docstring and
:attr:`Formula.equation`, and names a reference. None of them solves anything: a render never
recomputes physics that a simulation job computes.

Energies are in eV with the body's Fermi level at 0 and the electrostatic potential ψ in V
referred to the intrinsic level, as DEVSIM reports it, so E_i = −ψ. Lengths are in µm and
densities in cm⁻³. The explainer pages import the formulas they share with the renders from
here and keep their idealised-example formulas elsewhere, outside the render hash.

The module imports only numpy and the standard library (tested).
"""

from __future__ import annotations

import inspect
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from types import MappingProxyType

import numpy as np

# The calibration's region rule (gf180tcad.calibrate.cv), restated here so that this module
# imports no calibration code; tests/test_render_derive.py pins both to the same values.
FB_FRACTION = 0.9
PLATEAU_OFFSET_V = 1.0
U_END_V = 5.0

_SZE = "Sze and Ng 2006"


@dataclass(frozen=True)
class Formula:
    """One entry of :data:`FORMULAS`: its ``name``, the function ``fn``, the parameter names
    ``inputs`` (in order), the ``equation`` and its ``reference``."""

    name: str
    fn: Callable
    inputs: tuple[str, ...]
    equation: str
    reference: str


_TABLE: dict[str, Formula] = {}


def _formula(equation: str, reference: str):
    def register(fn: Callable) -> Callable:
        doc = " ".join((fn.__doc__ or "").split())
        if equation not in doc:
            raise AssertionError(f"{fn.__name__}: the docstring must state {equation!r}")
        if f"Reference: {reference}." not in doc:
            raise AssertionError(f"{fn.__name__}: the docstring must end 'Reference: {reference}.'")
        inputs = tuple(inspect.signature(fn).parameters)
        _TABLE[fn.__name__] = Formula(fn.__name__, fn, inputs, equation, reference)
        return fn

    return register


def _scalar_or_array(x):
    a = np.asarray(x, dtype=np.float64)
    return float(a) if a.ndim == 0 else a


@_formula("E_i = −ψ", "DEVSIM's potential reference: ψ = 0 at the intrinsic level")
def intrinsic_level(psi_v):
    """The intrinsic level E_i = −ψ (eV) at the potential ψ (V).

    Reference: DEVSIM's potential reference: ψ = 0 at the intrinsic level.
    """
    return _scalar_or_array(-np.asarray(psi_v, dtype=np.float64))


@_formula("E_c = −ψ + E_g/2", f"{_SZE}, ch. 1 (E_i at midgap; error stated by midgap_offset)")
def band_edge_ec(psi_v, e_g_ev):
    """The conduction-band edge in silicon, E_c = −ψ + E_g/2 (eV), midgap approximation.

    Reference: Sze and Ng 2006, ch. 1 (E_i at midgap; error stated by midgap_offset).
    """
    return _scalar_or_array(-np.asarray(psi_v, dtype=np.float64) + e_g_ev / 2)


@_formula("E_v = −ψ − E_g/2", f"{_SZE}, ch. 1 (E_i at midgap; error stated by midgap_offset)")
def band_edge_ev(psi_v, e_g_ev):
    """The valence-band edge in silicon, E_v = −ψ − E_g/2 (eV), midgap approximation.

    Reference: Sze and Ng 2006, ch. 1 (E_i at midgap; error stated by midgap_offset).
    """
    return _scalar_or_array(-np.asarray(psi_v, dtype=np.float64) - e_g_ev / 2)


@_formula("E_c,ox = −ψ + E_g/2 + ΔE_c", f"{_SZE}, ch. 4 (the Si–SiO2 band diagram)")
def oxide_band_edge_ec(psi_v, e_g_ev, conduction_offset_ev):
    """The oxide conduction-band edge at each oxide node, E_c,ox = −ψ + E_g/2 + ΔE_c (eV), with
    ψ the node's own potential, so the edge slopes with the oxide field.

    Reference: Sze and Ng 2006, ch. 4 (the Si–SiO2 band diagram).
    """
    return _scalar_or_array(
        -np.asarray(psi_v, dtype=np.float64) + e_g_ev / 2 + conduction_offset_ev
    )


@_formula("E_v,ox = −ψ − E_g/2 − ΔE_v", f"{_SZE}, ch. 4 (the Si–SiO2 band diagram)")
def oxide_band_edge_ev(psi_v, e_g_ev, valence_offset_ev):
    """The oxide valence-band edge at each oxide node, E_v,ox = −ψ − E_g/2 − ΔE_v (eV).

    Reference: Sze and Ng 2006, ch. 4 (the Si–SiO2 band diagram).
    """
    return _scalar_or_array(-np.asarray(psi_v, dtype=np.float64) - e_g_ev / 2 - valence_offset_ev)


@_formula("ΔE_i = (kT/2)·ln(N_v/N_c)", f"{_SZE}, ch. 1 (the intrinsic Fermi level)")
def midgap_offset(vt_v, nc_cm3, nv_cm3):
    """How far the intrinsic level sits above midgap, ΔE_i = (kT/2)·ln(N_v/N_c) (eV): the error
    of the midgap approximation of :func:`band_edge_ec` and :func:`band_edge_ev`.

    Reference: Sze and Ng 2006, ch. 1 (the intrinsic Fermi level).
    """
    return vt_v / 2 * math.log(nv_cm3 / nc_cm3)


@_formula("n = n_i·exp((ψ − φ)/V_t)", f"{_SZE}, ch. 1 (Boltzmann statistics)")
def boltzmann_n(psi_v, phi_v, n_i_cm3, vt_v):
    """The electron density n = n_i·exp((ψ − φ)/V_t) (cm⁻³), with φ the region's contact Fermi
    potential (V): exact for the quasi-static Poisson–Boltzmann solve.

    Reference: Sze and Ng 2006, ch. 1 (Boltzmann statistics).
    """
    psi = np.asarray(psi_v, dtype=np.float64)
    return _scalar_or_array(n_i_cm3 * np.exp((psi - phi_v) / vt_v))


@_formula("p = n_i·exp((φ − ψ)/V_t)", f"{_SZE}, ch. 1 (Boltzmann statistics)")
def boltzmann_p(psi_v, phi_v, n_i_cm3, vt_v):
    """The hole density p = n_i·exp((φ − ψ)/V_t) (cm⁻³).

    Reference: Sze and Ng 2006, ch. 1 (Boltzmann statistics).
    """
    psi = np.asarray(psi_v, dtype=np.float64)
    return _scalar_or_array(n_i_cm3 * np.exp((phi_v - psi) / vt_v))


@_formula("E_F,gate = −V_g,held", "the body Fermi level is 0 eV; the gate is held at V_g,held")
def gate_fermi_level(vg_held_v):
    """The gate Fermi level E_F,gate = −V_g,held (eV) at the bias the device holds (V).

    Reference: the body Fermi level is 0 eV; the gate is held at V_g,held.
    """
    return -vg_held_v


@_formula("C_ox = ε_ox·ε_0/t_ox", f"{_SZE}, ch. 4 (the MIS capacitor)")
def oxide_capacitance(eps_ox, eps0_f_per_cm, t_ox_nm):
    """The oxide capacitance per area C_ox = ε_ox·ε_0/t_ox, in fF/µm² (ε_0 in F/cm, t_ox in nm;
    1 F/cm² = 1e7 fF/µm²).

    Reference: Sze and Ng 2006, ch. 4 (the MIS capacitor).
    """
    return eps_ox * eps0_f_per_cm / (t_ox_nm * 1e-7) * 1e7


@_formula(
    "x_d = first x where the majority density reaches N/2",
    "this repo's rule, renders plan Task R1 (linear between the two nodes either side)",
)
def depletion_edge(x_um, majority_cm3, body_doping_cm3):
    """The depletion edge x_d = first x where the majority density reaches N/2 (µm), walking
    from the first node, linearly interpolated; the first node when it already holds N/2.
    Raises ValueError if the density never reaches it.

    Reference: this repo's rule, renders plan Task R1 (linear between the two nodes either
    side).
    """
    x = np.asarray(x_um, dtype=np.float64)
    m = np.asarray(majority_cm3, dtype=np.float64)
    half = body_doping_cm3 / 2
    hits = np.flatnonzero(m >= half)
    if not len(hits):
        raise ValueError(f"the majority density never reaches {half!r} cm^-3")
    k = int(hits[0])
    if k == 0:
        return float(x[0])
    t = (half - m[k - 1]) / (m[k] - m[k - 1])
    return float(x[k - 1] + t * (x[k] - x[k - 1]))


@_formula("Q = q·∫(p − n + N_net) dx", "the trapezoid rule over the node values")
def sheet_charge(x_um, p_cm3, n_cm3, net_doping_cm3, q_c):
    """The sheet charge Q = q·∫(p − n + N_net) dx (C/cm²) over the nodes ``x_um`` (µm), by the
    trapezoid rule; ``net_doping_cm3`` is positive for donors.

    Reference: the trapezoid rule over the node values.
    """
    rho = np.asarray(p_cm3) - np.asarray(n_cm3) + np.asarray(net_doping_cm3)
    return float(q_c * np.trapezoid(rho, np.asarray(x_um, dtype=np.float64) * 1e-4))


@_formula("y = sign(x)·log10(max(|x|, 1))", "a display transform for signed doping")
def log10_abs(x):
    """The signed logarithm y = sign(x)·log10(max(|x|, 1)), so that −1e17 maps to −17 and
    magnitudes below 1 map to 0.

    Reference: a display transform for signed doping.
    """
    a = np.asarray(x, dtype=np.float64)
    return _scalar_or_array(np.sign(a) * np.log10(np.maximum(np.abs(a), 1.0)))


@_formula("[min_k c_k, max_k c_k] at each point", "design spec §5.3 (the five-corner bounds)")
def envelope_minmax(curves):
    """The envelope [min_k c_k, max_k c_k] at each point over the curves (rows) of ``curves``:
    an array of shape (2, points).

    Reference: design spec §5.3 (the five-corner bounds).
    """
    a = np.asarray(curves, dtype=np.float64)
    return np.stack([a.min(axis=0), a.max(axis=0)])


@_formula("C = (C/A)·A", "the area scaling of gf180tcad.tcad.moscap1d")
def area_scale(c_per_area, area_um2):
    """A per-area value times an area, C = (C/A)·A.

    Reference: the area scaling of gf180tcad.tcad.moscap1d.
    """
    return _scalar_or_array(np.asarray(c_per_area, dtype=np.float64) * area_um2)


def _crossing(u: Sequence[float], c: Sequence[float], level: float, i0: int, step: int) -> float:
    above = c[i0] >= level
    k = i0 + step
    while 0 <= k < len(u):
        if (c[k] >= level) != above:
            a, b = k - step, k
            t = (level - c[a]) / (c[b] - c[a])
            return u[a] + t * (u[b] - u[a])
        k += step
    raise ValueError(f"the curve never crosses C = {level!r} from index {i0} (step {step})")


@_formula(
    "C(u_fb) = 0.9·C_acc, C(u_t) = (C_min + C_inv)/2",
    "the calibration's region rule, gf180tcad.calibrate.cv.regions",
)
def region_boundaries(vg_v, c, polarity):
    """The region boundaries of a C–V curve, in true-sign Vg (V), in this order: accumulation
    plateau edge (u_fb − 1 V), flat band u_fb, depletion-side crossing u_dep, the minimum
    u_min, inversion-side crossing u_inv, threshold u_t and inversion plateau edge (u_t + 1 V).

    With u = polarity·Vg ascending from −5 to +5 V, C_acc = C(u = −5 V), C_inv = C(u = +5 V):
    C(u_fb) = 0.9·C_acc, C(u_t) = (C_min + C_inv)/2, the plateaus start 1 V beyond them, and
    the crossings are where C passes (C_min + C_acc)/2 either side of the minimum, linearly
    interpolated between grid points.
    ``polarity`` is ``"n"`` or ``"p"``. The same arithmetic as the calibration, so the result
    is bit-equal to it (tested on the committed calibrated curves).

    Reference: the calibration's region rule, gf180tcad.calibrate.cv.regions.
    """
    if polarity not in ("n", "p"):
        raise ValueError(f"polarity must be 'n' or 'p', got {polarity!r}")
    sign = 1 if polarity == "n" else -1
    vg = np.asarray(vg_v, dtype=np.float64)
    order = np.argsort(sign * vg, kind="stable")
    u = (sign * vg)[order].tolist()
    cu = np.asarray(c, dtype=np.float64)[order].tolist()
    if any(not a < b for a, b in pairwise(u)):
        raise ValueError("u must be strictly increasing")
    if not (
        math.isclose(u[0], -U_END_V, abs_tol=1e-9) and math.isclose(u[-1], U_END_V, abs_tol=1e-9)
    ):
        raise ValueError(f"the grid must span u = -{U_END_V:g}..+{U_END_V:g} V")
    i = min(range(len(cu)), key=cu.__getitem__)
    c_acc, c_min, c_inv = cu[0], cu[i], cu[-1]
    mid = (cu[i] + cu[0]) / 2
    u_fb = _crossing(u, cu, FB_FRACTION * c_acc, 0, +1)
    u_t = _crossing(u, cu, (c_min + c_inv) / 2, i, +1)
    u_dep = _crossing(u, cu, mid, i, -1)
    u_inv = _crossing(u, cu, mid, i, +1)
    bounds = [u_fb - PLATEAU_OFFSET_V, u_fb, u_dep, u[i], u_inv, u_t, u_t + PLATEAU_OFFSET_V]
    return np.array([sign * b for b in bounds])


FORMULAS: Mapping[str, Formula] = MappingProxyType(dict(sorted(_TABLE.items())))


def evaluate(name: str, args: Sequence):
    """Formula ``name`` of :data:`FORMULAS` applied to ``args`` (in its parameter order).

    KeyError if there is no such formula; ValueError if the number of inputs is wrong."""
    if name not in FORMULAS:
        raise KeyError(f"no formula {name!r} (the table: {sorted(FORMULAS)})")
    f = FORMULAS[name]
    if len(args) != len(f.inputs):
        raise ValueError(f"{name} takes {len(f.inputs)} inputs {f.inputs}, got {len(args)}")
    return f.fn(*args)
