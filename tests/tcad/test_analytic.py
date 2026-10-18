# SPDX-License-Identifier: Apache-2.0
"""The exact 1D Poisson-Boltzmann low-frequency C-V (gf180tcad.tcad.analytic).

Every hand value uses :data:`gf180tcad.tcad.process.CONSTANTS` on both sides. These tests run
on the host; the TCAD-against-analytic comparison is in tests/tcad/test_moscap1d.py.
"""

import math

import pytest

from gf180tcad.tcad import analytic
from gf180tcad.tcad.process import CONSTANTS

C = CONSTANTS
EPS_OX = 3.9
NFET = {"n_cm3": -1.7e17, "t_ox_nm": 15.2, "gate_doping": 1e20}
PFET = {"n_cm3": 1.7e17, "t_ox_nm": 15.6, "gate_doping": -3.6e19}
VG = tuple(round(-5 + 0.05 * i, 10) for i in range(201))


def _cap(case):
    return analytic.moscap(case["n_cm3"], case["t_ox_nm"], case["gate_doping"], eps_ox=EPS_OX)


def test_unit_conversion():
    assert analytic.F_PER_CM2_TO_FF_PER_UM2 == 1e7
    # 1 F/cm^2 = 1e15 fF / 1e8 um^2
    assert analytic.f_per_cm2_to_ff_per_um2(1.0) == 1e15 / 1e8


def test_cox_hand_value():
    cox = analytic.f_per_cm2_to_ff_per_um2(analytic.cox_f_per_cm2(15.2, EPS_OX))
    assert math.isclose(cox, 2.2718, rel_tol=1e-4)
    assert cox == 3.9 * 8.8541878128e-14 / 15.2e-7 * 1e7


@pytest.mark.parametrize(("case", "vfb"), [(NFET, -1.029), (PFET, 1.003)], ids=["nfet", "pfet"])
def test_boltzmann_flat_band(case, vfb):
    cap = _cap(case)
    assert round(cap.vfb_v, 3) == vfb
    ng, nb = abs(case["gate_doping"]), abs(case["n_cm3"])
    # -pol Vt ln(NGATE N / n_i^2) up to the exact (not N >> n_i) neutral densities
    pol = 1 if case["n_cm3"] < 0 else -1
    assert math.isclose(cap.vfb_v, -pol * C.vt_v * math.log(ng * nb / C.n_i_cm3**2), rel_tol=1e-12)


@pytest.mark.parametrize("case", [NFET, PFET], ids=["nfet", "pfet"])
def test_flat_band_is_the_debye_series(case):
    cap = _cap(case)
    p = cap.solve(cap.vfb_v)
    assert abs(p.psi_s) < 1e-12 and abs(p.psi_g) < 1e-12
    eps = C.eps_si * C.eps0_f_per_cm
    want = analytic.series(
        cap.cox_f_per_cm2, eps / cap.body.debye_length_cm, eps / cap.gate.debye_length_cm
    )
    assert math.isclose(p.c_f_per_cm2, want, rel_tol=1e-9)


def test_debye_length_hand_value():
    s = analytic.Semiconductor(-1.7e17)
    want = math.sqrt(C.eps_si * C.eps0_f_per_cm * C.vt_v / (C.q_c * 1.7e17))
    assert math.isclose(s.debye_length_cm, want, rel_tol=1e-12)  # n0 = n_i^2/N is negligible


@pytest.mark.parametrize("case", [NFET, PFET], ids=["nfet", "pfet"])
def test_capacitance_is_dq_dvg(case):
    """The series formula equals the numerical derivative of the solved gate charge."""
    cap = _cap(case)
    h = 1e-5
    for vg in (-5.0, -2.0, -1.2, -0.5, 0.0, 0.4, 1.0, 2.0, 5.0):
        qp = -cap.solve(vg + h).q_body_c_per_cm2
        qm = -cap.solve(vg - h).q_body_c_per_cm2
        assert math.isclose(cap.solve(vg).c_f_per_cm2, (qp - qm) / (2 * h), rel_tol=1e-6), vg


@pytest.mark.parametrize("case", [NFET, PFET], ids=["nfet", "pfet"])
def test_solved_to_1e12(case):
    cap = _cap(case)
    for vg in VG:
        p = cap.solve(vg)
        v, psi_g, q = cap.vg_of(p.psi_s)
        assert abs(v - vg) <= 1e-12 * max(1.0, abs(vg))
        # charge neutrality: the gate holds minus the body's charge
        assert math.isclose(cap.gate.charge(psi_g), -q, rel_tol=1e-12, abs_tol=1e-30)


def test_charge_function_series_matches_closed_form():
    s = analytic.Semiconductor(-1.7e17)
    for u in (9.99e-4, 1.001e-3, -9.99e-4, -1.001e-3):
        psi = u * C.vt_v
        assert math.isclose(s.charge(psi), s.charge(psi * (1 + 1e-9)), rel_tol=1e-6)
    assert s.charge(0.0) == 0.0
    assert s.charge(-0.1) > 0 > s.charge(0.1)  # p-body: holes accumulate at psi < 0


def test_potential_of_charge_inverts_charge():
    g = analytic.Semiconductor(1e20)
    for psi in (-0.3, -0.01, 1e-6, 0.02, 0.2):
        assert math.isclose(g.potential_of_charge(g.charge(psi)), psi, rel_tol=1e-9)


def test_mirror_symmetry():
    """n-body/p+ gate at vg equals p-body/n+ gate at -vg (same |N|, NGATE and t_ox)."""
    a = analytic.lf_cv_uniform(-1.7e17, 15.2, 1e20, VG, eps_ox=EPS_OX)
    b = analytic.lf_cv_uniform(1.7e17, 15.2, -1e20, [-v for v in VG], eps_ox=EPS_OX)
    for ca, cb in zip(a, b, strict=True):
        assert math.isclose(ca, cb, rel_tol=1e-12)


@pytest.mark.parametrize("case", [NFET, PFET], ids=["nfet", "pfet"])
def test_lf_curve_shape(case):
    cox = analytic.f_per_cm2_to_ff_per_um2(analytic.cox_f_per_cm2(case["t_ox_nm"], EPS_OX))
    c = analytic.lf_cv_uniform(
        case["n_cm3"], case["t_ox_nm"], case["gate_doping"], VG, eps_ox=EPS_OX
    )
    assert all(0 < x < cox for x in c)
    i = min(range(len(c)), key=c.__getitem__)
    # the LF minimum lies between flat band and strong inversion, and both ends recover
    assert 0.3 * cox < c[i] < 0.5 * cox
    assert c[0] > 0.94 * cox and c[-1] > 0.94 * cox


def test_lf_cv_uniform_returns_ff_per_um2():
    cap = _cap(NFET)
    (c,) = analytic.lf_cv_uniform(-1.7e17, 15.2, 1e20, [1.0], eps_ox=EPS_OX)
    assert c == analytic.f_per_cm2_to_ff_per_um2(cap.solve(1.0).c_f_per_cm2)
