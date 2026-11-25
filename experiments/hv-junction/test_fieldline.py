"""Host test: fieldline.max_integral on a 1D triangular field laid out on a 2D grid."""

import numpy as np

import fieldline
import ionize

Q, EPS = 1.602176634e-19, 11.7 * 8.8541878128e-14


def test_matches_1d_integral():
    n, v = 1e16, 50.0
    w = np.sqrt(2 * EPS * v / (Q * n))
    ys = np.linspace(0, 1.5 * w, 600)  # junction at y = 0 (N side), P depletion edge at y = w
    xs = np.linspace(0, 1e-4, 12)
    e = np.where(ys < w, Q * n * (w - ys) / EPS, 0.0)  # field points to +y
    psi = v - np.concatenate([[0], np.cumsum(0.5 * (e[1:] + e[:-1]) * np.diff(ys))])
    xx, yy = np.meshgrid(xs, ys, indexing="ij")
    pp = np.broadcast_to(psi, xx.shape)
    got, _, emax = fieldline.max_integral(xx.ravel(), yy.ravel(), pp.ravel(), step=w / 2000)
    s = np.linspace(0, w, 4000)
    want, _ = ionize.ionisation_integrals(s, Q * n * s / EPS)
    assert abs(emax - Q * n * w / EPS) / emax < 0.01
    assert abs(got - want) / want < 0.03, (got, want)
