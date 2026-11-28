# SPDX-License-Identifier: Apache-2.0
"""Fit the deep parts of the doping family to the public capacitance models (development
script; scipy on the host).

    uv run --locked python experiments/hv-junction/fit.py

The N-well is fitted with the deep P layer under it. It prints the fitted values, which
hvsite.DEFAULT_PROCESS holds rounded.
"""

import numpy as np
import profile1d as p1
from scipy.optimize import least_squares

UM = 1e-4
Q, EPS = p1.Q, p1.EPS
V = np.array([0.0, 1, 2, 5, 10])
NWM = p1.model_c(V, 1.4914e-8, 0.30525, 0.43905)
DNM = p1.model_c(V, 2.2998e-8, 0.14716, 0.35175)
y = np.linspace(0, 16e-4, 32001)
SH = (2.5e17, 0.32 * UM, 0.13 * UM)


def plane_bv(n):
    """Plane breakdown of the deepest junction, depletion approximation (applied + built-in)."""
    return p1.plane_breakdown(y, n)


def build(x):
    sub, pk2, rp2, sy2, pkP, rpP, syP, pkD, rpD, syD = x
    nw = [SH, (pk2, rp2 * UM, sy2 * UM)]
    dn = [(pkD, rpD * UM, syD * UM)]
    pf = [(pkP, rpP * UM, syP * UM)]
    return sub, nw, dn, pf


def metrics(x):
    sub, nw, dn, pf = build(x)
    n, tot = p1.net(y, nw, sub, pf)
    cn = p1.cv(y, n, V)
    yj = p1.junction_depth(y, n)
    m = (y > 0.32 * UM) & (y < yj) & (n > 0)
    rs = 1 / (Q * np.trapezoid(p1.mobility_n(tot[m]) * n[m], y[m]))
    bvn = plane_bv(n)
    nd, _ = p1.net(y, dn, sub, pf)
    cd = p1.cv(y, nd, V)
    bvd = plane_bv(nd)
    return cn, rs, bvn, cd, bvd, yj / UM, p1.junction_depth(y, nd) / UM


def resid(lx):
    x = np.exp(lx)
    try:
        cn, rs, _, cd, bvd, _, _ = metrics(x)
    except Exception:  # noqa: BLE001 (any failed profile is a bad fit)
        return np.full(13, 10.0)
    r = (
        list(np.log(cn / NWM))
        + [0.5 * np.log(rs / 1000)]
        + list(np.log(cd / DNM))
        + [np.log((bvd - 0.5) / 30.48) if not np.isnan(bvd) else 3.0, 0.0]
    )
    return np.nan_to_num(np.array(r), nan=5.0)


x0 = np.array([3.0e15, 3e16, 0.9, 0.5, 6e16, 4.6, 0.6, 4e16, 2.4, 0.7])
lo = np.log([1.5e15, 5e15, 0.5, 0.25, 5e15, 3.0, 0.3, 1e16, 1.2, 0.3])
hi = np.log([6e15, 1e17, 1.5, 0.8, 5e17, 7.0, 1.5, 2e17, 3.5, 1.2])
sol = least_squares(resid, np.log(x0), bounds=(lo, hi), x_scale=1.0, diff_step=0.02)
x = np.exp(sol.x)
names = ["sub", "pk2", "rp2", "sy2", "pkP", "rpP", "syP", "pkD", "rpD", "syD"]
print({k: float(f"{v:.3g}") for k, v in zip(names, x)}, "cost", sol.cost)
cn, rs, bvn, cd, bvd, yjn, yjd = metrics(x)
print(
    "NW C ratio",
    np.round(cn / NWM, 3),
    "Rs under STI",
    round(rs),
    "plane BV",
    round(bvn, 1),
    "xj",
    round(yjn, 2),
)
print("DNW C ratio", np.round(cd / DNM, 3), "plane BV", round(bvd, 1), "xj", round(yjd, 2))
