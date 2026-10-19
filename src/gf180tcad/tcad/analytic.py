# SPDX-License-Identifier: Apache-2.0
"""The exact 1D Poisson-Boltzmann low-frequency C-V of a uniformly doped MOS capacitor.

This is the reference the 1D TCAD MOS capacitor (:mod:`gf180tcad.tcad.moscap1d`) is tested
against. It is exact for the model the TCAD solves: Boltzmann statistics, uniform doping, a
silicon body and a poly-silicon gate each thick enough to reach their neutral bulk, an oxide
without charge, and every carrier in equilibrium with its own contact (the quasi-static, or
low-frequency, curve). Nothing here is the depletion approximation, whose minimum is the
high-frequency one and several percent off the low-frequency minimum.

The semiconductor charge function (Sze & Ng, *Physics of Semiconductor Devices*, 3rd ed.,
ch. 4, https://doi.org/10.1002/0470068329): a semiconductor of net doping N = N_D - N_A with
the neutral equilibrium densities n0 = N/2 + sqrt(N^2/4 + n_i^2) and p0 = n_i^2/n0, whose
potential at its surface is psi above its bulk (u = psi/V_t), holds the charge per area

    Q(psi) = -sign(psi) * sqrt(2 eps_si q V_t F(u)),
    F(u) = p0 (e^-u + u - 1) + n0 (e^u - u - 1),

and its small-signal capacitance is C(psi) = -dQ/dpsi = sqrt(2 eps_si q V_t) abs(dF/du) /
(2 V_t sqrt(F(u))), with dF/du = n0 (e^u - 1) - p0 (e^-u - 1); at psi = 0 this is
eps_si/L_D, L_D = sqrt(eps_si V_t / (q (n0 + p0))).

Poly depletion is included by applying the same Q to the gate: the poly-silicon gate is a
second semiconductor, of net doping ``gate_doping``, with its own surface potential psi_g.
For the degenerate gates (1e20, 3.6e19 cm^-3) Boltzmann statistics is approximate, but it is
also what the :term:`TCAD` (`DEVSIM <https://devsim.org/>`_) uses (`gplugins.devsim.materials <https://github.com/mithro/gplugins/blob/dddaa071321c5177c8471312c565ad86d4b245d7/gplugins/devsim/materials.py>`_), so the two are consistent; the
difference to Fermi-Dirac statistics is a documented limitation absorbed by the tunable
:ref:`dv_fb_v <process-data-tunables>`.

With the intrinsic level as the potential reference, the body's bulk is at
V_t ln(n0/n_i) (body contact at 0 V) and the gate's at Vg + V_t ln(n0g/n_i). Gauss's law across
the oxide and charge neutrality, Q_gate = -Q_body = C_ox (phi_gate_surface - phi_body_surface),
give

    Vg = Vfb + psi_s - psi_g - Q_body(psi_s)/C_ox,   Q_gate(psi_g) = -Q_body(psi_s),
    Vfb = V_t ln(n0/n0g),

and C = dQ_gate/dVg is the series combination of C_ox, the body's C(psi_s) and the gate's
C(psi_g). :meth:`MosCap.solve` finds psi_s for each Vg (bracketed Newton) to 1e-12 relative on Vg.

Units: densities cm^-3, lengths nm, potentials V, charge C/cm^2; :func:`lf_cv_uniform` returns
fF/um^2 (1 F/cm^2 = 1e7 fF/um^2).

This module is TCAD code. It is not one of the SPICE generator modules
(:data:`gf180tcad.reference.GENERATOR_MODULES`).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from gf180tcad.tcad.process import CONSTANTS, Constants

# 1 F/cm^2 in fF/um^2: 1e15 fF per F over 1e8 um^2 per cm^2.
F_PER_CM2_TO_FF_PER_UM2 = 1e7

# The relative tolerance on Vg of MosCap.solve (the brief's "solved to 1e-12").
TOL = 1e-12

# Below this abs(u) = abs(psi)/V_t, F(u) and dF/du are evaluated from their Taylor series, where the
# closed forms lose digits to cancellation.
_SERIES_U = 1e-3


def f_per_cm2_to_ff_per_um2(c_f_per_cm2: float) -> float:
    """A capacitance per area from F/cm^2 (DEVSIM's 1D unit) to fF/um^2."""
    return c_f_per_cm2 * F_PER_CM2_TO_FF_PER_UM2


def cox_f_per_cm2(t_ox_nm: float, eps_ox: float, constants: Constants = CONSTANTS) -> float:
    """The oxide capacitance eps_ox eps0 / t_ox (F/cm^2)."""
    return eps_ox * constants.eps0_f_per_cm / (t_ox_nm * 1e-7)


def series(*caps: float) -> float:
    """The series combination 1 / sum(1/C) of capacitances (any one unit)."""
    return 1.0 / math.fsum(1.0 / c for c in caps)


@dataclass(frozen=True)
class Semiconductor:
    """A uniformly doped semiconductor: net doping N = N_D - N_A (cm^-3) and its equilibrium."""

    net_doping_cm3: float
    constants: Constants = CONSTANTS

    @property
    def n0(self) -> float:
        """Neutral equilibrium electron density (cm^-3), exact (no N >> n_i approximation)."""
        n, ni = self.net_doping_cm3, self.constants.n_i_cm3
        if n >= 0:
            return n / 2 + math.sqrt(n * n / 4 + ni * ni)
        return ni * ni / self.p0

    @property
    def p0(self) -> float:
        """Neutral equilibrium hole density (cm^-3)."""
        n, ni = self.net_doping_cm3, self.constants.n_i_cm3
        if n < 0:
            return -n / 2 + math.sqrt(n * n / 4 + ni * ni)
        return ni * ni / self.n0

    @property
    def bulk_potential_v(self) -> float:
        """The neutral bulk's potential above the intrinsic level at 0 V bias: V_t ln(n0/n_i)."""
        return self.constants.vt_v * math.log(self.n0 / self.constants.n_i_cm3)

    @property
    def debye_length_cm(self) -> float:
        """L_D = sqrt(eps_si V_t / (q (n0 + p0))) (cm)."""
        c = self.constants
        return math.sqrt(_eps_si(c) * c.vt_v / (c.q_c * (self.n0 + self.p0)))

    def _f(self, u: float) -> float:
        n0, p0 = self.n0, self.p0
        if abs(u) < _SERIES_U:
            # e^u - u - 1 = u^2/2 + u^3/6 + u^4/24 + u^5/120 + ...; e^-u + u - 1 alternates.
            even = u * u / 2 + u**4 / 24
            odd = u**3 / 6 + u**5 / 120
            return p0 * (even - odd) + n0 * (even + odd)
        return p0 * (math.expm1(-u) + u) + n0 * (math.expm1(u) - u)

    def _df(self, u: float) -> float:
        return self.n0 * math.expm1(u) - self.p0 * math.expm1(-u)

    def charge(self, psi: float) -> float:
        """Q(psi) (C/cm^2): the space charge per area when the surface is ``psi`` above the bulk."""
        if psi == 0.0:
            return 0.0
        c = self.constants
        q = math.sqrt(2 * _eps_si(c) * c.q_c * c.vt_v * self._f(psi / c.vt_v))
        return -q if psi > 0 else q

    def capacitance(self, psi: float) -> float:
        """C(psi) = -dQ/dpsi (F/cm^2), > 0; eps_si/L_D at psi = 0."""
        c = self.constants
        if psi == 0.0:
            return _eps_si(c) / self.debye_length_cm
        u = psi / c.vt_v
        return (
            math.sqrt(2 * _eps_si(c) * c.q_c * c.vt_v)
            * abs(self._df(u))
            / (2 * c.vt_v * math.sqrt(self._f(u)))
        )

    def potential_of_charge(self, q: float) -> float:
        """The inverse of :meth:`charge`: the psi (V) at which this semiconductor holds ``q``."""
        if q == 0.0:
            return 0.0
        psi = _root(lambda p: self.charge(p) - q, self.capacitance, 1e-15 * abs(q))
        # the root may also stop on a 1e-15 V step: check the charge it gives
        if abs(self.charge(psi) - q) > 1e-12 * abs(q):
            raise ArithmeticError(f"analytic MOS capacitor: charge residual at psi = {psi!r}")
        return psi


def _eps_si(c: Constants) -> float:
    return c.eps_si * c.eps0_f_per_cm


def _root(f, neg_df, ftol: float) -> float:
    """The root (V) of a strictly decreasing ``f`` (derivative ``-neg_df``) by bracketed Newton.

    It stops when ``|f| <= ftol`` or the step is below 1e-15 V (relative above 1 V). The
    bracket starts at ±1 V and doubles until it holds the root; a Newton step leaving the
    bracket is replaced by bisection.
    """
    lo, hi = -1.0, 1.0
    while f(lo) < 0:
        lo *= 2
    while f(hi) > 0:
        hi *= 2
    x = 0.0 if lo < 0.0 < hi else (lo + hi) / 2
    for _ in range(400):
        fx = f(x)
        if abs(fx) <= ftol:
            return x
        if fx > 0:
            lo = x
        else:
            hi = x
        d = neg_df(x)
        step = fx / d if d > 0 else math.inf
        nx = x + step
        if not (lo < nx < hi):
            nx = (lo + hi) / 2
        if abs(nx - x) <= 1e-15 * max(1.0, abs(x)):
            return nx
        x = nx
    raise ArithmeticError("analytic MOS capacitor: root not found in 400 iterations")


@dataclass(frozen=True)
class Point:
    """The solution at one gate bias: surface potentials (V), body charge (C/cm^2) and C."""

    vg: float
    psi_s: float
    psi_g: float
    q_body_c_per_cm2: float
    c_f_per_cm2: float


@dataclass(frozen=True)
class MosCap:
    """A uniform-body, uniform-poly-gate MOS capacitor (signed net dopings, cm^-3)."""

    body: Semiconductor
    gate: Semiconductor
    cox_f_per_cm2: float

    @property
    def vfb_v(self) -> float:
        """The flat band V_t ln(n0/n0g) (V): -1.029 V for the nfet, +1.003 V for the pfet."""
        return self.body.bulk_potential_v - self.gate.bulk_potential_v

    def vg_of(self, psi_s: float) -> tuple[float, float, float]:
        """``(Vg, psi_g, Q_body)`` at the body surface potential ``psi_s``."""
        q_body = self.body.charge(psi_s)
        psi_g = self.gate.potential_of_charge(-q_body)
        return self.vfb_v + psi_s - psi_g - q_body / self.cox_f_per_cm2, psi_g, q_body

    def solve(self, vg: float) -> Point:
        """The bias point at ``vg``: psi_s to 1e-12 relative on Vg (:data:`TOL`)."""

        def f(psi_s: float) -> float:
            return vg - self.vg_of(psi_s)[0]  # strictly decreasing in psi_s

        def neg_df(psi_s: float) -> float:
            # dVg/dpsi_s = 1 + C_body/C_gate + C_body/C_ox = C_body / C
            return self.body.capacitance(psi_s) / self.capacitance(psi_s)

        psi_s = _root(f, neg_df, TOL * max(1.0, abs(vg)))
        v, psi_g, q_body = self.vg_of(psi_s)
        if abs(v - vg) > TOL * max(1.0, abs(vg)):
            raise ArithmeticError(f"analytic MOS capacitor: Vg residual {v - vg!r} at {vg!r}")
        c = series(self.cox_f_per_cm2, self.body.capacitance(psi_s), self.gate.capacitance(psi_g))
        return Point(vg, psi_s, psi_g, q_body, c)

    def capacitance(self, psi_s: float) -> float:
        """C (F/cm^2) at the body surface potential ``psi_s``: Cox, C_body, C_gate in series."""
        q_body = self.body.charge(psi_s)
        psi_g = self.gate.potential_of_charge(-q_body)
        return series(
            self.cox_f_per_cm2, self.body.capacitance(psi_s), self.gate.capacitance(psi_g)
        )


def moscap(
    n_cm3: float,
    t_ox_nm: float,
    gate_doping: float,
    constants: Constants = CONSTANTS,
    *,
    eps_ox: float,
) -> MosCap:
    """The :class:`MosCap` of signed net body doping ``n_cm3`` and gate doping ``gate_doping``.

    Net doping is N_D - N_A: the nfet MOS capacitor is ``n_cm3 = -1.7e17`` (p-body) with
    ``gate_doping = +1e20`` (n+ poly), the pfet ``+1.7e17`` with ``-3.6e19``.
    """
    return MosCap(
        Semiconductor(n_cm3, constants),
        Semiconductor(gate_doping, constants),
        cox_f_per_cm2(t_ox_nm, eps_ox, constants),
    )


def lf_cv_uniform(
    n_cm3: float,
    t_ox_nm: float,
    gate_doping: float,
    vg: Iterable[float],
    constants: Constants = CONSTANTS,
    *,
    eps_ox: float,
) -> tuple[float, ...]:
    """The exact low-frequency (quasi-static) C per area (fF/um^2) at each gate bias ``vg``.

    Signed net dopings as in :func:`moscap`; ``eps_ox`` is the oxide's relative permittivity
    (the card's :term:`EPSROX`).
    """
    cap = moscap(n_cm3, t_ox_nm, gate_doping, constants, eps_ox=eps_ox)
    return tuple(f_per_cm2_to_ff_per_um2(cap.solve(float(v)).c_f_per_cm2) for v in vg)
