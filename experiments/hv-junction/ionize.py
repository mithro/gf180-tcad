"""Impact-ionisation coefficients of silicon and the ionisation integral.

Pure numpy, no simulator needed. The coefficients are those of van Overstraeten
and de Man (Solid-State Electronics 13, 1970, p. 583), the Chynoweth form
alpha = a * exp(-b / E), which Charon's "vanOverstraeten" model also uses.

Units: field in V/cm, length in cm, alpha in 1/cm.
"""

from __future__ import annotations

import numpy as np

# van Overstraeten - de Man, 300 K.
AN, BN = 7.03e5, 1.231e6
AP_LO, BP_LO = 1.582e6, 2.036e6  # E <= 4e5 V/cm
AP_HI, BP_HI = 6.71e5, 1.693e6  # E > 4e5 V/cm
E_SWITCH = 4.0e5


def alpha_n(e):
    """Electron ionisation coefficient, 1/cm, for field magnitude e in V/cm."""
    e = np.maximum(np.abs(np.asarray(e, dtype=float)), 1.0)
    return AN * np.exp(-BN / e)


def alpha_p(e):
    """Hole ionisation coefficient, 1/cm, for field magnitude e in V/cm."""
    e = np.maximum(np.abs(np.asarray(e, dtype=float)), 1.0)
    lo = AP_LO * np.exp(-BP_LO / e)
    hi = AP_HI * np.exp(-BP_HI / e)
    return np.where(e > E_SWITCH, hi, lo)


def _cumtrapz(y, s):
    out = np.zeros_like(y, dtype=float)
    out[1:] = np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(s))
    return out


def ionisation_integrals(s, e):
    """Electron and hole ionisation integrals along one field line.

    s: arc length in cm, increasing from the P side (low potential) to the N side
       (high potential). Electrons drift in the direction of increasing s.
    e: field magnitude in V/cm at each s.

    Returns (I_n, I_p). Avalanche breakdown is I_n = 1 (equivalently I_p = 1):
      I_n = int alpha_n(s) exp(-int_0^s (alpha_n - alpha_p) ds') ds
      I_p = int alpha_p(s) exp(-int_s^W (alpha_p - alpha_n) ds') ds
    """
    s = np.asarray(s, dtype=float)
    an, ap = alpha_n(e), alpha_p(e)
    diff = _cumtrapz(an - ap, s)  # int_0^s (an - ap)
    total = diff[-1]
    i_n = _cumtrapz(an * np.exp(-diff), s)[-1]
    i_p = _cumtrapz(ap * np.exp(diff - total), s)[-1]
    return float(i_n), float(i_p)


def breakdown_voltage(volts, integrals):
    """Voltage at which the ionisation integral crosses 1, by log interpolation.

    Returns None when the integral never reaches 1 in the sweep.
    """
    v = np.asarray(volts, dtype=float)
    i = np.maximum(np.asarray(integrals, dtype=float), 1e-300)
    above = np.nonzero(i >= 1.0)[0]
    if len(above) == 0:
        return None
    k = int(above[0])
    if k == 0:
        return float(v[0])
    l0, l1 = np.log(i[k - 1]), np.log(i[k])
    return float(v[k - 1] + (v[k] - v[k - 1]) * (0.0 - l0) / (l1 - l0))
