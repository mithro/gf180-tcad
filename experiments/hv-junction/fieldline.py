# SPDX-License-Identifier: Apache-2.0
"""Ionisation integrals along field lines of a 2D potential on a tensor-product grid.

numpy and scipy only. Lengths in cm, potential in V. The grid may have holes (points
outside the silicon), marked by NaN in the potential; a field line ends there.
"""

from __future__ import annotations

import ionize
import numpy as np
from scipy.interpolate import RegularGridInterpolator


def to_grid(x, y, values):
    """Scatter node values onto the tensor grid of their coordinates (NaN where absent)."""
    xs, ix = np.unique(np.round(x, 12), return_inverse=True)
    ys, iy = np.unique(np.round(y, 12), return_inverse=True)
    grid = np.full((len(xs), len(ys)), np.nan)
    grid[ix, iy] = values
    return xs, ys, grid


def field(xs, ys, psi):
    """E = -grad(psi) on the grid; zero where psi or a neighbour is absent."""
    ex, ey = np.gradient(-psi, xs, ys, edge_order=1)
    bad = ~np.isfinite(ex) | ~np.isfinite(ey)
    ex[bad], ey[bad] = 0.0, 0.0
    return ex, ey


def trace(xs, ys, ex, ey, seeds, step, e_stop=2.0e3, max_steps=40000):
    """Follow E from each seed both ways. Returns a list of (s, |E|) per seed, ordered
    from the low-potential (P) end to the high-potential (N) end."""
    fx = RegularGridInterpolator((xs, ys), ex, bounds_error=False, fill_value=0.0)
    fy = RegularGridInterpolator((xs, ys), ey, bounds_error=False, fill_value=0.0)

    def march(sign):
        pos = np.array(seeds, dtype=float)
        alive = np.ones(len(pos), dtype=bool)
        mags = []
        for _ in range(max_steps):
            e1 = np.stack([fx(pos), fy(pos)], axis=1)
            m1 = np.hypot(e1[:, 0], e1[:, 1])
            alive &= m1 > e_stop
            mags.append(np.where(alive, m1, np.nan))
            if not alive.any():
                break
            # midpoint step along sign * (-E) for "up the potential" when sign = +1
            d1 = -sign * e1 / np.maximum(m1, 1.0)[:, None]
            mid = pos + 0.5 * step * d1
            e2 = np.stack([fx(mid), fy(mid)], axis=1)
            m2 = np.hypot(e2[:, 0], e2[:, 1])
            alive &= m2 > e_stop  # the midpoint left the silicon or the depletion region
            d2 = -sign * e2 / np.maximum(m2, 1.0)[:, None]
            pos = np.where(alive[:, None], pos + step * d2, pos)
        return np.array(mags)  # (steps, seeds)

    up = march(+1.0)  # towards the N side
    down = march(-1.0)  # towards the P side
    out = []
    for k in range(len(seeds)):
        a = down[:, k]
        a = a[np.isfinite(a)][::-1]
        b = up[:, k]
        b = b[np.isfinite(b)]
        e = np.concatenate([a, b[1:]]) if len(b) > 1 else a
        out.append((np.arange(len(e)) * step, e))
    return out


def max_integral(x, y, psi_nodes, step, n_seeds=120):
    """Largest electron ionisation integral over field lines through the high-field nodes.

    Returns (I_n max, seed position in cm, peak |E| in V/cm).
    """
    xs, ys, psi = to_grid(x, y, psi_nodes)
    ex, ey = field(xs, ys, psi)
    mag = np.hypot(ex, ey)
    flat = np.argsort(mag, axis=None)[::-1]
    # thin the candidates so that seeds are not all neighbours of the single peak
    picks = flat[: 40 * n_seeds : 40][:n_seeds]
    picks = np.unique(np.concatenate([flat[: n_seeds // 3], picks]))
    ii, jj = np.unravel_index(picks, mag.shape)
    seeds = np.stack([xs[ii], ys[jj]], axis=1)
    best, where = 0.0, None
    for seed, (s, e) in zip(seeds, trace(xs, ys, ex, ey, seeds, step)):
        if len(e) < 3:
            continue
        i_n, _ = ionize.ionisation_integrals(s, e)
        if i_n > best:
            best, where = i_n, seed
    return best, where, float(mag.max())
