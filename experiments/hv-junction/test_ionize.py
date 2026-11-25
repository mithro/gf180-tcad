"""Host tests of ionize.py: uv run --with numpy --with pytest pytest docs/high-voltage/sim"""

import numpy as np

import ionize

Q, EPS = 1.602176634e-19, 11.7 * 8.8541878128e-14


def _abrupt_bv(n):
    """Breakdown of a one-sided abrupt junction of doping n, from the triangular field."""
    volts = np.geomspace(2.0, 2000.0, 400)
    ints = []
    for v in volts:
        w = np.sqrt(2 * EPS * v / (Q * n))
        s = np.linspace(0.0, w, 4000)
        e = Q * n * s / EPS  # zero at the P-side depletion edge, peak at the junction
        ints.append(ionize.ionisation_integrals(s, e)[0])
    return ionize.breakdown_voltage(volts, ints)


def test_integrals_agree():
    s = np.linspace(0, 2e-4, 2000)
    e = 3.5e5 * s / s[-1]
    i_n, i_p = ionize.ionisation_integrals(s, e)
    # I_n = 1 and I_p = 1 are the same condition; away from 1 they differ but both < 1 or both > 1
    assert (i_n - 1) * (i_p - 1) > 0


def test_abrupt_junction_breakdown_matches_textbook():
    # Sze & Ng, Physics of Semiconductor Devices 3rd ed., Fig. 2.19 / eq. (104):
    # BV ~ 60 (N/1e16)^-0.75 V. The van Overstraeten coefficients give this within ~25 %.
    for n, lo, hi in ((1e15, 250, 380), (1e16, 45, 75), (1e17, 9, 16)):
        bv = _abrupt_bv(n)
        assert lo < bv < hi, (n, bv)
