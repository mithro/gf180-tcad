# SPDX-License-Identifier: Apache-2.0
"""1D quantities of a well profile: sheet resistance and junction C-V (numpy only).

The vertical net doping is the same Gaussian-plus-substrate form structure.py uses, so a
profile checked here against the public anchors (the PDK's well sheet resistance and its
junction capacitance model) is the one the 2D cross-section simulates.

Units: cm, cm^-3, V, F/cm^2, ohm/square.
"""

from __future__ import annotations

import ionize
import numpy as np

Q = 1.602176634e-19
EPS = 11.7 * 8.8541878128e-14
VT = 0.025852
NI = 1.0e10


def mobility_n(n):
    """Electron mobility against total doping at 300 K (Masetti et al., IEEE TED 30, 1983,
    arsenic/phosphorus-like majority fit), cm^2/Vs."""
    n = np.asarray(n, dtype=float)
    return (
        68.5
        + (1414.0 - 68.5) / (1.0 + (n / 9.2e16) ** 0.711)
        - 56.1 / (1.0 + (3.41e20 / n) ** 1.98)
    )


def net(y, wells, sub, pfield=()):
    """Donors minus acceptors at depth y (cm); wells and pfield are (peak, rp, sy) in cm."""
    d = sum(pk * np.exp(-0.5 * ((y - rp) / sy) ** 2) for pk, rp, sy in wells)
    a = sub + sum(pk * np.exp(-0.5 * ((y - rp) / sy) ** 2) for pk, rp, sy in pfield)
    return d - a, d + a


def junction_depth(y, n):
    """Deepest sign change from N to P."""
    k = np.nonzero((n[:-1] > 0) & (n[1:] <= 0))[0]
    if len(k) == 0:
        return None
    k = k[-1]
    return y[k] + (y[k + 1] - y[k]) * n[k] / (n[k] - n[k + 1])


def sheet_resistance(y, n, total, top=0.0):
    """Of the N layer between depth `top` and the deepest junction, ohm/square (neutral,
    undepleted). top = 0.32e-4 gives the well under trench oxide, which is what the PDK's
    N-well resistor is."""
    yj = junction_depth(y, n)
    m = (y >= top) & (y < yj) & (n > 0)
    return 1.0 / (Q * np.trapezoid(mobility_n(total[m]) * n[m], y[m]))


def cv(y, n, volts):
    """Depletion capacitance per area of the deepest junction at each reverse voltage.

    Depletion approximation on the given profile: for each P-side edge xp the N-side edge
    xn balances the charge; the potential across is the second moment. Returns F/cm^2.
    """
    yj = junction_depth(y, n)
    j = int(np.searchsorted(y, yj))
    # cumulative charge and its first moment measured from the junction
    qp = np.cumsum(-n[j:] * np.gradient(y[j:]))  # acceptors exposed below the junction
    mp = np.cumsum(-n[j:] * (y[j:] - yj) * np.gradient(y[j:]))
    yn = y[:j][::-1]
    nn = n[:j][::-1]
    qn = np.cumsum(nn * np.abs(np.gradient(yn)))
    mn = np.cumsum(nn * (yj - yn) * np.abs(np.gradient(yn)))
    # for each P edge index find the N edge with equal charge
    kn = np.searchsorted(qn, qp)
    ok = kn < len(qn)
    v_tot = (Q / EPS) * (mp[ok] + mn[kn[ok]])
    w = (y[j:][ok] - yj) + (yj - yn[kn[ok]])
    # built-in potential from the neutral concentrations at the two edges
    vbi = VT * np.log(np.maximum(nn[kn[ok]], 1.0) * np.maximum(-n[j:][ok], 1.0) / NI**2)
    vr = v_tot - vbi
    return EPS / np.interp(volts, vr, w)


def model_c(volts, cjo, mj, pb):
    """The SPICE junction capacitance, same units as cjo."""
    return cjo / (1.0 + np.asarray(volts) / pb) ** mj


def plane_breakdown(y, n):
    """Plane breakdown voltage of the deepest junction of the net doping n on the uniform
    grid y, in the depletion approximation: the junction potential (applied bias plus
    built-in potential) at which ionize.py's electron integral over the depletion field
    reaches 1. NaN when it is not reached below 400 V."""
    sg = np.sign(n)
    j = np.nonzero(sg[:-1] != sg[1:])[0][-1]
    dy = y[1] - y[0]
    cum = np.cumsum(n) * dy
    prev = None
    for a in range(j - 1, 0, -max(1, j // 300)):
        seg = cum[j:] - cum[a]
        k = np.nonzero(np.sign(seg[:-1]) != np.sign(seg[1:]))[0]
        if len(k) == 0:
            break
        b = j + k[0]
        field = np.abs(Q / EPS * (cum[a : b + 1] - cum[a]))
        volts = np.trapezoid(field, y[a : b + 1])
        s = y[a : b + 1] - y[a]
        i_n, _ = ionize.ionisation_integrals(s, field[::-1])
        if prev and i_n >= 1:
            return float(np.interp(0, [np.log(prev[1]), np.log(i_n)], [prev[0], volts]))
        prev = (volts, max(i_n, 1e-300))
        if volts > 400:
            break
    return float("nan")
