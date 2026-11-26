# SPDX-License-Identifier: Apache-2.0
"""Read Charon's Exodus output and run the DEVSIM-side post-processing on it.

Needs netCDF4, numpy and scipy (the Charon image has them). A sweep file holds one
"time" plane per converged bias point. Charon writes scaled variables: the potential in
units of V0 = kT/q, densities in units of the concentration scaling. The potential has
the same zero as DEVSIM's (zero where the silicon is intrinsic).

charon_mesh.write_exodus stored, next to the mesh, the Exodus node of every DEVSIM node;
with it the potential comes back on DEVSIM's silicon nodes, in DEVSIM's order and with
DEVSIM's coordinates in cm, ready for fieldline.max_integral.
"""

from __future__ import annotations

import contextlib

import numpy as np

import fieldline
import ionize

V0_300K = 0.025852  # V, what Charon prints for T = 300 K


def _names(d, var):
    rows = np.ma.filled(d.variables[var][:], b"")
    return [b"".join(r).decode().strip("\x00").strip() for r in rows]


class Sweep:
    """The planes of one Exodus output file."""

    def __init__(self, exo_path, map_path, region="si", well="well"):
        import netCDF4

        self.d = netCDF4.Dataset(exo_path)
        z = np.load(map_path)
        self.node = z[f"map_{region}"]
        xy = z["xy_cm"][self.node]
        self.x, self.y = xy[:, 0], xy[:, 1]
        got = np.stack([self.d.variables["coordx"][:], self.d.variables["coordy"][:]], axis=1)
        if got.shape[0] != z["xy_cm"].shape[0] or np.abs(got - z["xy_cm"] * 1e4).max() > 1e-9:
            raise ValueError("the output file does not have the node order of the mesh file")
        self.nodal = _names(self.d, "name_nod_var")
        glo = _names(self.d, "name_glo_var")
        vals = np.ma.filled(self.d.variables["vals_glo_var"][:], np.nan)
        self.v = vals[:, glo.index(f"{well}_Voltage")]
        cur = [k for k, n in enumerate(glo) if n.startswith(f"{well}_") and n.endswith("_Current")]
        self.i_well = vals[:, cur[0]]
        self.v0 = self._voltage_scale()

    def _voltage_scale(self):
        """V0 from how far the scaled potential maximum moves between two biases.

        The potential maximum is on the swept contact, where the potential is the bias
        plus a constant. Falls back on the printed value when the file has one bias.
        """
        k0, k1 = int(np.argmin(self.v)), int(np.argmax(self.v))
        if self.v[k1] - self.v[k0] < 1.0:
            return V0_300K
        top = [float(self.scaled("ELECTRIC_POTENTIAL", k).max()) for k in (k0, k1)]
        return float((self.v[k1] - self.v[k0]) / (top[1] - top[0]))

    def scaled(self, name, plane):
        """One nodal variable on every Exodus node, as written."""
        k = self.nodal.index(name) + 1
        return np.ma.filled(self.d.variables[f"vals_nod_var{k}"][plane], np.nan)

    def potential(self, plane):
        """Potential in volts on the region's nodes, DEVSIM order."""
        return self.scaled("ELECTRIC_POTENTIAL", plane)[self.node] * self.v0

    def nearest_plane(self, volts):
        return int(np.argmin(np.abs(self.v - volts)))


@contextlib.contextmanager
def hole_low_branch_only():
    """Within the block ionize.alpha_p uses its low-field branch at every field.

    That is the hole coefficient Charon's Selberherr model has in the control-volume
    scheme (see charon_deck._avalanche_lines), so an ionisation integral computed here
    predicts where that Charon run should break down by its current.
    """
    keep = ionize.AP_HI, ionize.BP_HI
    ionize.AP_HI, ionize.BP_HI = ionize.AP_LO, ionize.BP_LO
    try:
        yield
    finally:
        ionize.AP_HI, ionize.BP_HI = keep


def scan(sweep, step_cm, planes=None):
    """fieldline.max_integral on each plane. Returns {v, i_n, emax, where_um}."""
    planes = range(len(sweep.v)) if planes is None else planes
    out = {"v": [], "i_n": [], "emax": [], "where_um": []}
    for k in planes:
        i_n, where, emax = fieldline.max_integral(sweep.x, sweep.y, sweep.potential(k), step_cm)
        out["v"].append(float(sweep.v[k]))
        out["i_n"].append(float(i_n))
        out["emax"].append(float(emax))
        um = None if where is None else [float(where[0] * 1e4), float(where[1] * 1e4)]
        out["where_um"].append(um)
    return out


def scan_both(sweep, step_cm, planes=None):
    """scan() with ionize.py's coefficients, plus "i_n_low_branch": the integral with the
    hole low-field branch only."""
    full = scan(sweep, step_cm, planes)
    with hole_low_branch_only():
        low = scan(sweep, step_cm, planes)
    full["i_n_low_branch"] = low["i_n"]
    return full


def save_potentials(sweep, every_v, prefix, v_lo=-np.inf, v_hi=np.inf):
    """Write prefix<V>.npz (x_cm, y_cm, psi, v) at each multiple of every_v the file
    holds within [v_lo, v_hi]."""
    written = []
    vmax = float(np.nanmax(sweep.v))
    for target in np.arange(0.0, vmax + 1e-9, every_v):
        k = sweep.nearest_plane(target)
        if abs(sweep.v[k] - target) > 0.26 * every_v or not v_lo <= sweep.v[k] <= v_hi:
            continue
        path = f"{prefix}{target:g}.npz"
        np.savez_compressed(path, x_cm=sweep.x, y_cm=sweep.y, psi=sweep.potential(k), v=sweep.v[k])
        written.append(path)
    return written
