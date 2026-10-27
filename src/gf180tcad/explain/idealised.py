# SPDX-License-Identifier: Apache-2.0
"""The closed table of idealised-example formulas of the explainer pages.

An explainer page labels a value computed here as an idealised example: a textbook formula
applied to stated inputs (this repo's committed dopings and constants, or textbook values), not
a simulation result. The formulas the explainer shares with the renders live in
:mod:`gf180tcad.derive` and are not defined again here (tested); these stay outside the render
hash, so adding one stales no committed render.

Each function is pure numpy, states its equation in its docstring and in
:attr:`gf180tcad.derive.Formula.equation`, and ends its docstring with its reference. Densities
are in cm⁻³, energies in eV and the thermal voltage V_t = kT/q in V.
"""

from __future__ import annotations

import inspect
import math
from collections.abc import Callable, Mapping
from types import MappingProxyType

import numpy as np

from gf180tcad.derive import Formula

_SZE = "Sze and Ng 2006 (lit-sze)"
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


@_formula("n·p = n_i²", f"{_SZE}, ch. 1 (the mass-action law)")
def mass_action(n_i_cm3, majority_cm3):
    """The minority density from the mass-action law n·p = n_i², as n_i²/N (cm⁻³), with N the
    majority density (the doping, when every :term:`dopant` is ionised).

    Reference: Sze and Ng 2006 (lit-sze), ch. 1 (the mass-action law).
    """
    return n_i_cm3**2 / majority_cm3


@_formula("E_F − E_i = V_t·ln(n/n_i)", f"{_SZE}, ch. 1 (Boltzmann statistics)")
def boltzmann_fermi(n_cm3, n_i_cm3, vt_v):
    """The Fermi level above the intrinsic level, E_F − E_i = V_t·ln(n/n_i) (eV), for the
    electron density n under Boltzmann statistics.

    Reference: Sze and Ng 2006 (lit-sze), ch. 1 (Boltzmann statistics).
    """
    return vt_v * math.log(n_cm3 / n_i_cm3)


def fermi_dirac_half(eta):
    """The Fermi–Dirac integral of order one half, normalised so that it tends to exp(η) for
    η ≪ 0: F_½(η) = (2/√π)·∫₀^∞ √ε / (1 + exp(ε − η)) dε, by the trapezoid rule in t = √ε."""
    top = math.sqrt(max(eta, 0.0) + 60.0)
    t = np.linspace(0.0, top, 20001)
    f = t**2 / (1.0 + np.exp(np.minimum(t**2 - eta, 700.0)))
    return float(4.0 / math.sqrt(math.pi) * np.trapezoid(f, t))


def _inverse_fermi_dirac_half(r: float) -> float:
    lo, hi = math.log(r) - 1.0, math.log(r) + max(2.0, 2.0 * r)
    for _ in range(100):
        mid = (lo + hi) / 2
        if fermi_dirac_half(mid) < r:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@_formula(
    "ΔE_F = V_t·[F_½⁻¹(n/N_c) − ln(n/N_c)]",
    f"{_SZE}, ch. 1 (Fermi–Dirac statistics and the degenerate semiconductor)",
)
def degenerate_offset(n_cm3, nc_cm3, vt_v):
    """How far Boltzmann statistics misplace the Fermi level at the electron density n:
    ΔE_F = V_t·[F_½⁻¹(n/N_c) − ln(n/N_c)] (eV), the Fermi–Dirac position minus the Boltzmann
    one, both measured from the conduction-band edge with the effective density of states N_c.
    Positive: the true Fermi level sits higher than Boltzmann statistics place it.

    Reference: Sze and Ng 2006 (lit-sze), ch. 1 (Fermi–Dirac statistics and the degenerate
    semiconductor).
    """
    r = n_cm3 / nc_cm3
    return vt_v * (_inverse_fermi_dirac_half(r) - math.log(r))


@_formula("V_bi = V_t·ln(N_A·N_D / n_i²)", f"{_SZE}, ch. 2 (the built-in potential)")
def built_in_potential(n_a_cm3, n_d_cm3, n_i_cm3, vt_v):
    """The built-in potential of an abrupt p-n junction, V_bi = V_t·ln(N_A·N_D / n_i²) (V), with
    N_A the acceptor density of the p side and N_D the donor density of the n side, under
    Boltzmann statistics with every dopant ionised.

    Reference: Sze and Ng 2006 (lit-sze), ch. 2 (the built-in potential).
    """
    return vt_v * math.log(n_a_cm3 * n_d_cm3 / n_i_cm3**2)


@_formula(
    "W = √(2·ε_r·ε_0·V_bi·(1/N_A + 1/N_D) / q)",
    f"{_SZE}, ch. 2 (the depletion approximation, abrupt junction)",
)
def depletion_width(n_a_cm3, n_d_cm3, vbi_v, eps_r, eps0_f_per_cm, q_c):
    """The zero-bias width of the depletion region of an abrupt p-n junction in the
    :term:`depletion approximation`, W = √(2·ε_r·ε_0·V_bi·(1/N_A + 1/N_D) / q) (cm).

    Reference: Sze and Ng 2006 (lit-sze), ch. 2 (the depletion approximation, abrupt junction).
    """
    return math.sqrt(2 * eps_r * eps0_f_per_cm * vbi_v * (1 / n_a_cm3 + 1 / n_d_cm3) / q_c)


@_formula(
    "ρ = q·N_D on −x_n < x < 0, −q·N_A on 0 < x < x_p; dE/dx = ρ/ε; dψ/dx = −E",
    f"{_SZE}, ch. 2 (the depletion approximation, abrupt junction)",
)
def abrupt_junction(x_cm, n_a_cm3, n_d_cm3, vbi_v, eps_r, eps0_f_per_cm, q_c):
    """The charge, field and potential of an abrupt p-n junction at zero bias in the
    :term:`depletion approximation`, at the positions ``x_cm`` (cm; the n side at x < 0, the p side at x > 0):
    ρ = q·N_D on −x_n < x < 0, −q·N_A on 0 < x < x_p; dE/dx = ρ/ε; dψ/dx = −E, with
    x_n = W·N_A/(N_A + N_D), x_p = W·N_D/(N_A + N_D) and W from :func:`depletion_width`.
    Returns ``charge_cm3`` (ρ/q, cm⁻³), ``field_v_per_cm`` and ``potential_v`` (zero at the
    p-side edge, V_bi at the n-side edge).

    Reference: Sze and Ng 2006 (lit-sze), ch. 2 (the depletion approximation, abrupt junction).
    """
    x = np.asarray(x_cm, dtype=float)
    w = depletion_width(n_a_cm3, n_d_cm3, vbi_v, eps_r, eps0_f_per_cm, q_c)
    x_n = w * n_a_cm3 / (n_a_cm3 + n_d_cm3)
    x_p = w * n_d_cm3 / (n_a_cm3 + n_d_cm3)
    eps = eps_r * eps0_f_per_cm
    e_max = q_c * n_a_cm3 * x_p / eps
    on_n = (x > -x_n) & (x <= 0)
    on_p = (x > 0) & (x < x_p)
    charge = np.where(on_n, n_d_cm3, 0.0) - np.where(on_p, n_a_cm3, 0.0)
    field = np.where(on_n, e_max * (x + x_n) / x_n, 0.0) + np.where(
        on_p, e_max * (x_p - x) / x_p, 0.0
    )
    # ψ(x_p) = 0 and dψ/dx = −E: integrate the two triangles in closed form.
    psi_p = np.where(on_p, e_max * (x_p - x) ** 2 / (2 * x_p), 0.0)
    v_n_edge = e_max * (x_n + x_p) / 2
    psi_n = np.where(on_n, v_n_edge - e_max * (x + x_n) ** 2 / (2 * x_n), 0.0)
    psi = np.where(x <= -x_n, v_n_edge, psi_n + psi_p)
    return {"charge_cm3": charge, "field_v_per_cm": field, "potential_v": psi}


FORMULAS: Mapping[str, Formula] = MappingProxyType(dict(sorted(_TABLE.items())))
