# SPDX-License-Identifier: Apache-2.0
"""Device metrics extracted from simulated curves (SPICE now, TCAD later).

Every helper takes *magnitudes* (|Vgs|, |Vds|, |Id|, W and L in um) and returns plain floats in
the units given below; it raises :class:`MetricError` instead of returning NaN when a metric is
undefined (no crossing, too few fit points, non-finite or non-increasing inputs).
:func:`extract_all` strips device polarity by multiplying voltages and currents by
``device.polarity`` (never ``abs()``, so a sign error shows up as an error instead of being
hidden), then splits the nested sweeps by their outer-axis value.

Definitions (all at 25 C, the voltages of ``gf180tcad.devices.SWEEPS``).

Sign convention of the results of :func:`extract_all`: the three ``vt_*`` keys are reported as
``device.polarity * magnitude`` (nfet positive, pfet negative, matching the PDK convention, e.g.
a pfet VT0 of about -0.83 V). Every other key is a magnitude (positive for both polarities);
``dibl_mv_per_v`` and ``body_effect_v`` are computed from the Vt magnitudes before the sign is
applied. The helper functions always take and return magnitudes.

``vt_lin_maxgm`` [V, signed by polarity]
    ``idvg_lin`` (Vds = 0.1 V) at |Vbs| = 0. Linear extrapolation of Id(Vgs) at the point of
    maximum gm = dId/dVgs (first maximum): ``Vgs* - Id*/gm* - Vds/2``.
``vt_lin_cc`` [V, signed by polarity]
    Constant-current Vt on the same curve: the first Vgs (increasing) where
    ``Id = 100 nA * W/L``, log-linear interpolation between the bracketing points.
``vt_sat_cc`` [V, signed by polarity]
    The same constant-current Vt on ``idvg_sat`` (Vds = 5 V) at |Vbs| = 0.
``dibl_mv_per_v`` [mV/V, magnitude]
    ``(vt_lin_cc - vt_sat_cc) / (5.0 - 0.1) * 1000``.
``body_effect_v`` [V, magnitude]
    ``vt_lin_cc(|Vbs| = 2 V) - vt_lin_cc(|Vbs| = 0)`` from ``idvg_lin`` (positive for both
    polarities: reverse body bias raises |Vt|).
``idsat_ua_per_um`` [uA/um]
    ``|Id| / W`` on ``idvg_sat`` at |Vbs| = 0, |Vgs| = 5 V (Vds = 5 V).
``id_lin_a`` [A]
    Total (not per um) Id on ``idvg_lin`` at |Vbs| = 0, Vgs = ``vt_lin_maxgm`` + 0.5 V, linearly
    interpolated.
``gm_peak_s`` [S]
    Maximum of gm = dId/dVgs on ``idvg_lin`` at |Vbs| = 0 (total, not per um).
``gds_at_5v_s`` [S]
    dId/dVds on ``idvd`` at Vgs = 5 V, Vds = 5 V (last point, 2nd-order one-sided difference).
``ss_mv_per_dec`` [mV/dec]
    ``idvg_lin`` at |Vbs| = 0: least-squares slope of Vgs against log10(Id) over the points whose
    Id/W lies in [1e-11, 1e-8] A/um (the fit is log10(Id) against Vgs, inverted to mV/dec).
``ioff_pa_per_um`` [pA/um]
    ``Id / W`` of the ``ioff`` sweep (Vgs = 0, Vds = 5.5 V).
``cgg_inv_ff`` / ``cgg_acc_ff`` [fF]
    ``cgg`` of the ``cv`` sweep (1 MHz) at polarity * Vg = +5 V (inversion) and -5 V (accumulation).
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from gf180tcad.devices import Device, Geometry

__all__ = [
    "MetricError",
    "body_effect",
    "dibl",
    "extract_all",
    "gds",
    "gm",
    "id_lin",
    "idsat_per_um",
    "ioff_per_um",
    "subthreshold_slope",
    "vt_cc",
    "vt_maxgm",
]

I0_CC = 100e-9  # A, constant-current Vt criterion at W/L = 1
ID_LIN_OVERDRIVE_V = 0.5
SS_I_LO, SS_I_HI = 1e-11, 1e-8  # A/um window for the subthreshold-slope fit
VBS_BODY_V = 2.0
VGS_ON_V = 5.0
VDS_LIN_V = 0.1
VDS_SAT_V = 5.0
VDS_OFF_V = 5.5
_TOL = 1e-9  # V, grid-point matching


class MetricError(ValueError):
    """A metric is undefined for the given curve (no crossing, bad window or bad input)."""


def _curve(x, y, what: str = "curve", *, min_points: int = 2) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.ndim != 1 or x.shape != y.shape:
        raise MetricError(f"{what}: x and y must be 1-D arrays of equal length")
    if x.size < min_points:
        raise MetricError(f"{what}: need at least {min_points} points, got {x.size}")
    if not (np.all(np.isfinite(x)) and np.all(np.isfinite(y))):
        raise MetricError(f"{what}: non-finite values")
    if not np.all(np.diff(x) > 0):
        raise MetricError(f"{what}: voltage axis must be strictly increasing")
    return x, y


def _positive(value: float, name: str) -> float:
    if not (np.isfinite(value) and value > 0):
        raise MetricError(f"{name} must be finite and > 0, got {value}")
    return float(value)


def gm(vgs, id) -> np.ndarray:
    """dId/dVgs: 2nd-order central differences inside, 2nd-order one-sided at both ends."""
    x, y = _curve(vgs, id, "gm", min_points=3)
    return np.gradient(y, x, edge_order=2)


def gds(vds, id) -> np.ndarray:
    """dId/dVds: 2nd-order central differences inside, 2nd-order one-sided at both ends."""
    x, y = _curve(vds, id, "gds", min_points=3)
    return np.gradient(y, x, edge_order=2)


def vt_maxgm(vgs, id, vds: float) -> float:
    """Vt by linear extrapolation at max gm, minus Vds/2: ``Vgs* - Id*/gm* - Vds/2``."""
    x, y = _curve(vgs, id, "vt_maxgm", min_points=3)
    g = gm(x, y)
    k = int(np.argmax(g))
    if not g[k] > 0:
        raise MetricError("vt_maxgm: gm is nowhere positive")
    return float(x[k] - y[k] / g[k] - vds / 2)


def vt_cc(vgs, id, w_um: float, l_um: float, i0: float = I0_CC) -> float:
    """Vgs where Id = i0 * W/L: first crossing in increasing Vgs, log-linear interpolation."""
    x, y = _curve(vgs, id, "vt_cc")
    target = i0 * _positive(w_um, "w_um") / _positive(l_um, "l_um")
    hits = np.flatnonzero((y[:-1] < target) & (y[1:] >= target))
    if hits.size == 0:
        raise MetricError(f"vt_cc: Id never crosses {target:.3e} A going up in Vgs")
    k = int(hits[0])
    if not y[k] > 0:
        raise MetricError("vt_cc: lower bracketing current is not positive, cannot interpolate")
    frac = (np.log10(target) - np.log10(y[k])) / (np.log10(y[k + 1]) - np.log10(y[k]))
    return float(x[k] + frac * (x[k + 1] - x[k]))


def idsat_per_um(id_at_5v5v: float, w_um: float) -> float:
    """Saturation current density in uA/um from |Id| at Vgs = Vds = 5 V."""
    if not (np.isfinite(id_at_5v5v) and id_at_5v5v > 0):
        raise MetricError(f"idsat: on-current must be finite and > 0, got {id_at_5v5v}")
    return float(id_at_5v5v * 1e6 / _positive(w_um, "w_um"))


def id_lin(vgs, id, vt: float) -> float:
    """Id (A) at Vgs = vt + 0.5 V, linearly interpolated (error if outside the sweep)."""
    x, y = _curve(vgs, id, "id_lin")
    at = vt + ID_LIN_OVERDRIVE_V
    if not (np.isfinite(at) and x[0] <= at <= x[-1]):
        raise MetricError(f"id_lin: Vgs = {at} V is outside the sweep {x[0]}..{x[-1]} V")
    return float(np.interp(at, x, y))


def subthreshold_slope(
    vgs,
    id,
    w_um: float,
    i_lo: float = SS_I_LO,
    i_hi: float = SS_I_HI,
) -> float:
    """Subthreshold slope in mV/dec.

    The window ``i_lo <= Id/W <= i_hi`` (A/um) selects the points; log10(Id) is fitted against
    Vgs by least squares and the inverse slope is returned. At least 3 points are required.
    """
    x, y = _curve(vgs, id, "subthreshold_slope")
    w = _positive(w_um, "w_um")
    sel = (y / w >= i_lo) & (y / w <= i_hi)
    if int(sel.sum()) < 3:
        raise MetricError(
            f"subthreshold_slope: only {int(sel.sum())} points with Id/W in [{i_lo}, {i_hi}] A/um"
        )
    slope = np.polyfit(x[sel], np.log10(y[sel]), 1)[0]  # decades per volt
    if not slope > 0:
        raise MetricError("subthreshold_slope: fitted slope is not positive")
    return float(1000.0 / slope)


def ioff_per_um(id, w_um: float) -> float:
    """Off-current density in pA/um from the total off-state |Id| (A)."""
    if not (np.isfinite(id) and id >= 0):
        raise MetricError(f"ioff: off-current must be finite and >= 0, got {id}")
    return float(id * 1e12 / _positive(w_um, "w_um"))


def dibl(vt_lin: float, vt_sat: float, vds_lin: float = 0.1, vds_sat: float = 5.0) -> float:
    """DIBL in mV/V: ``(vt_lin - vt_sat) / (vds_sat - vds_lin) * 1000``."""
    if not (np.isfinite(vt_lin) and np.isfinite(vt_sat)):
        raise MetricError("dibl: non-finite Vt")
    if not vds_sat > vds_lin:
        raise MetricError("dibl: vds_sat must exceed vds_lin")
    return float((vt_lin - vt_sat) / (vds_sat - vds_lin) * 1000.0)


def body_effect(vt_vbs0: float, vt_vbs2: float) -> float:
    """Body effect in V: ``Vt(|Vbs| = 2 V) - Vt(|Vbs| = 0)``."""
    if not (np.isfinite(vt_vbs0) and np.isfinite(vt_vbs2)):
        raise MetricError("body_effect: non-finite Vt")
    return float(vt_vbs2 - vt_vbs0)


def _strip(d: Mapping[str, np.ndarray], polarity: int, volts: tuple, amps: tuple) -> dict:
    out = {}
    for key in volts + amps:
        if key not in d:
            raise MetricError(f"missing column {key!r}")
        out[key] = np.asarray(d[key], dtype=float) * polarity
    return out


def _select(mask: np.ndarray, what: str) -> np.ndarray:
    if not mask.any():
        raise MetricError(f"no points for {what}")
    return mask


def _idvg(d: Mapping[str, np.ndarray], polarity: int, vbs_mag: float, vds: float, what: str):
    """(vgs, id) magnitudes of the nested idvg sweep at the given |Vbs|; every Vds must be ``vds``."""
    s = _strip(d, polarity, ("vd", "vg", "vb"), ("id",))
    if not np.all(np.isclose(s["vd"], vds, rtol=0, atol=_TOL)):
        raise MetricError(f"{what}: every Vds must be {vds} V")
    m = _select(np.isclose(-s["vb"], vbs_mag, rtol=0, atol=_TOL), f"{what} |Vbs|={vbs_mag}")
    return s["vg"][m], s["id"][m]


def _at(x: np.ndarray, y: np.ndarray, x0: float, what: str) -> float:
    k = np.flatnonzero(np.isclose(x, x0, rtol=0, atol=_TOL))
    if k.size != 1:
        raise MetricError(f"{what}: expected exactly one point at {x0} V, found {k.size}")
    return float(y[k[0]])


def extract_all(
    device: Device, g: Geometry, data: Mapping[str, Mapping[str, np.ndarray]]
) -> dict[str, float]:
    """All metrics of one device/geometry from ``data`` = {sweep name -> column dict}.

    The columns are true signed volts/amps as produced by the SPICE runners (and later TCAD);
    see the module docstring for the definition and sweep of every key.
    """
    p = device.polarity
    w, ln = g.w_um, g.l_um

    vg, i_lin = _idvg(data["idvg_lin"], p, 0.0, VDS_LIN_V, "idvg_lin")
    vt_mg = vt_maxgm(vg, i_lin, VDS_LIN_V)
    vt_lin = vt_cc(vg, i_lin, w, ln)
    vg2, i_lin2 = _idvg(data["idvg_lin"], p, VBS_BODY_V, VDS_LIN_V, "idvg_lin")
    vt_lin2 = vt_cc(vg2, i_lin2, w, ln)

    vgs_s, i_sat = _idvg(data["idvg_sat"], p, 0.0, VDS_SAT_V, "idvg_sat")
    vt_sat = vt_cc(vgs_s, i_sat, w, ln)

    dv = _strip(data["idvd"], p, ("vd", "vg"), ("id",))
    m = _select(np.isclose(dv["vg"], VGS_ON_V, rtol=0, atol=_TOL), "idvd Vgs=5")
    g_ds = gds(dv["vd"][m], dv["id"][m])
    if not np.isclose(dv["vd"][m][-1], VDS_SAT_V, rtol=0, atol=_TOL):
        raise MetricError("idvd: curve does not end at Vds = 5 V")

    off = _strip(data["ioff"], p, ("vd", "vg"), ("id",))
    if off["id"].size != 1:
        raise MetricError("ioff sweep must hold exactly one point")
    if not (
        np.isclose(off["vg"][0], 0.0, rtol=0, atol=_TOL)
        and np.isclose(off["vd"][0], VDS_OFF_V, rtol=0, atol=_TOL)
    ):
        raise MetricError(f"ioff: point must be at Vgs = 0 and polarity*Vds = {VDS_OFF_V} V")

    cv = _strip(data["cv"], p, ("vg",), ())
    cgg = np.asarray(data["cv"]["cgg"], dtype=float)
    if not np.all(np.isfinite(cgg)):
        raise MetricError("cv: non-finite cgg")

    return {
        "vt_lin_maxgm": p * vt_mg,
        "vt_lin_cc": p * vt_lin,
        "vt_sat_cc": p * vt_sat,
        "dibl_mv_per_v": dibl(vt_lin, vt_sat, VDS_LIN_V, VDS_SAT_V),
        "body_effect_v": body_effect(vt_lin, vt_lin2),
        "idsat_ua_per_um": idsat_per_um(_at(vgs_s, i_sat, VGS_ON_V, "idvg_sat"), w),
        "id_lin_a": id_lin(vg, i_lin, vt_mg),
        "gm_peak_s": float(np.max(gm(vg, i_lin))),
        "gds_at_5v_s": float(g_ds[-1]),
        "ss_mv_per_dec": subthreshold_slope(vg, i_lin, w),
        "ioff_pa_per_um": ioff_per_um(float(off["id"][0]), w),
        "cgg_inv_ff": _at(cv["vg"], cgg, 5.0, "cv") * 1e15,
        "cgg_acc_ff": _at(cv["vg"], cgg, -5.0, "cv") * 1e15,
    }
