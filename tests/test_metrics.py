# SPDX-License-Identifier: Apache-2.0
"""Metric extraction on synthetic curves with known answers (plus a real-ngspice smoke test)."""

import numpy as np
import pytest

from gf180tcad import metrics
from gf180tcad.devices import DEVICES, SWEEPS, Device, Geometry
from gf180tcad.metrics import MetricError

SW = {s.name: s for s in SWEEPS}
V05 = np.array(SW["idvg_lin"].vgs)
VT, SS_MV = 0.7, 85.0
NVTH = SS_MV / 1000 / np.log(10)  # n*kT/q for the exponential tail
K, THETA = 2e-4, 0.02  # A/V gain and mobility-degradation factor of the synthetic model
VDS_LIN, VDS_SAT = 0.1, 5.0


def model_id(vgs, vt, scale=1.0):
    """Smooth Id(Vgs): exponential below Vt, square-law-like above (softplus), with degradation.

    Softplus s = nvth*ln(1+exp((vgs-vt)/nvth)) is exp((vgs-vt)/nvth)*nvth in deep subthreshold
    (slope exactly SS_MV) and tends to vgs - vt above, where Id = K*s/(1+THETA*s) peaks in gm.
    """
    s = NVTH * np.logaddexp(0.0, (vgs - vt) / NVTH)
    return scale * K * s / (1 + THETA * s)


def vt_shift(vbs_mag, vds):
    """Body effect +0.1 V/V and DIBL 8.16 mV/V of the synthetic device."""
    return VT + VDS_LIN / 2 + 0.1 * vbs_mag - (0.04 / 4.9) * (vds - VDS_LIN)


def cgg_model(vg):
    return 2e-13 + 1e-13 * np.tanh(vg / 2)


def nfet_data():
    """Synthetic nfet-signed results on the real sweep grids (reverse Vbs is negative)."""
    d = {}
    for name, vds in (("idvg_lin", VDS_LIN), ("idvg_sat", VDS_SAT)):
        vbs_mag = np.array(SW[name].vbs)
        vg = np.tile(V05, vbs_mag.size)
        vb = np.repeat(-vbs_mag, V05.size)
        idd = np.concatenate([model_id(V05, vt_shift(m, vds)) for m in vbs_mag])
        d[name] = {
            "vd": np.full(vg.size, vds),
            "vg": vg,
            "vb": vb,
            "id": idd,
            "ig": np.zeros(vg.size),
            "ib": np.zeros(vg.size),
        }
    vgs_list, vds_grid = np.array(SW["idvd"].vgs), np.array(SW["idvd"].vds)
    vg = np.repeat(vgs_list, vds_grid.size)
    vd = np.tile(vds_grid, vgs_list.size)
    d["idvd"] = {
        "vd": vd,
        "vg": vg,
        "vb": np.zeros(vg.size),
        "id": idvd_model(vg, vd),
        "ig": np.zeros(vg.size),
        "ib": np.zeros(vg.size),
    }
    d["ioff"] = {
        "vd": np.array([5.5]),
        "vg": np.array([0.0]),
        "vb": np.array([0.0]),
        "id": np.array([3e-12]),
        "ig": np.zeros(1),
        "ib": np.zeros(1),
    }
    cvg = np.array(SW["cv"].vgs)
    d["cv"] = {"vg": cvg, "cgg": cgg_model(cvg)}
    return d


def idvd_model(vg, vd):
    return 1e-4 * (vg - 0.7) ** 2 * np.tanh(vd) * (1 + 0.02 * vd)


def pfet_data(nd):
    """The same curves with every voltage and current negated (pfet sign convention)."""
    out = {}
    for name, cols in nd.items():
        out[name] = {k: (-v if k != "cgg" else v) for k, v in cols.items()}
    out["cv"]["cgg"] = cgg_model(-out["cv"]["vg"])  # pfet inversion is at Vg = -5
    return out


NFET, PFET = DEVICES["nfet_05v0"], DEVICES["pfet_05v0"]
G = Geometry(10, 0.6, "calibration")
FAKE_P = Device("fake_p", -1, "fake_p", (Geometry(10, 0.6, "calibration"),))


# --- helpers on constructed curves --------------------------------------------------------


def test_vt_maxgm_within_2mv():
    idd = model_id(V05, VT + VDS_LIN / 2)  # model Vt includes the Vds/2 offset
    assert metrics.vt_maxgm(V05, idd, VDS_LIN) == pytest.approx(VT, abs=2e-3)


def test_subthreshold_slope_within_half_mv():
    idd = model_id(V05, VT)
    assert metrics.subthreshold_slope(V05, idd, 10.0, 1e-11, 1e-8) == pytest.approx(SS_MV, abs=0.5)


def test_vt_cc_exact_at_constructed_point():
    # an exact exponential Id = 1e-7*(W/L)*10**((vgs-0.65)/0.085): log-linear interp is exact
    w, ln = 10.0, 0.6
    idd = 1e-7 * w / ln * 10 ** ((V05 - 0.65) / 0.085)
    assert metrics.vt_cc(V05, idd, w, ln) == pytest.approx(0.65, abs=1e-12)


def test_vt_cc_takes_first_crossing():
    vgs = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    idd = np.array([1e-9, 1e-6, 1e-8, 1e-5, 1e-4])  # crosses 1e-7 at 0.x, dips, crosses again
    v = metrics.vt_cc(vgs, idd, 1.0, 1.0)
    assert v == pytest.approx(2 / 3, abs=1e-12)  # 1e-7 is 2/3 of the way from 1e-9 to 1e-6 in log
    assert v < 1.0


def test_gm_of_quadratic_including_endpoints():
    k, vt = 3e-4, 0.5
    vgs = np.linspace(0, 5, 501)
    g = metrics.gm(vgs, k * (vgs - vt) ** 2)
    np.testing.assert_allclose(g, 2 * k * (vgs - vt), rtol=1e-6, atol=1e-12)
    # endpoints are 2nd-order (exact for a quadratic), not 1st-order
    assert g[0] == pytest.approx(2 * k * (0 - vt), rel=1e-9)
    assert g[-1] == pytest.approx(2 * k * (5 - vt), rel=1e-9)


def test_gds_of_quadratic_in_vds():
    vds = np.linspace(0, 5, 501)
    np.testing.assert_allclose(metrics.gds(vds, 1e-4 * vds**2), 2e-4 * vds, rtol=1e-6, atol=1e-12)


def test_dibl_and_body_effect():
    assert metrics.dibl(0.70, 0.66) == pytest.approx(8.163265306122449, rel=1e-9)
    assert metrics.body_effect(0.70, 0.95) == pytest.approx(0.25)


def test_simple_scalings():
    assert metrics.idsat_per_um(5e-3, 10.0) == pytest.approx(500.0)
    assert metrics.ioff_per_um(3e-12, 10.0) == pytest.approx(0.3)
    assert metrics.id_lin(np.array([0.0, 1.0, 2.0]), np.array([0.0, 1e-3, 3e-3]), 1.0) == (
        pytest.approx(2e-3)
    )


# --- failure modes ------------------------------------------------------------------------


def test_vt_cc_no_crossing():
    with pytest.raises(MetricError, match="never crosses"):
        metrics.vt_cc(V05, np.full(V05.size, 1e-12), 10.0, 0.6)
    with pytest.raises(MetricError, match="never crosses"):  # starts above the target
        metrics.vt_cc(V05, np.full(V05.size, 1e-3), 10.0, 0.6)


def test_ss_window_too_small():
    vgs = np.array([0.0, 0.1, 0.2, 0.3])
    idd = np.array([1e-12, 1e-11, 1e-10, 1e-5])  # only 2 points inside 1e-11..1e-8 A/um (W=1)
    with pytest.raises(MetricError, match="only 2 points"):
        metrics.subthreshold_slope(vgs, idd, 1.0)


def test_non_finite_and_non_increasing_inputs():
    good = np.array([0.0, 1.0, 2.0, 3.0])
    cur = np.array([1e-9, 1e-8, 1e-7, 1e-6])
    bad_i = cur.copy()
    bad_i[1] = np.nan
    bad_v = good.copy()
    bad_v[2] = np.inf
    for fn in (
        lambda v, i: metrics.vt_cc(v, i, 1.0, 1.0),
        lambda v, i: metrics.vt_maxgm(v, i, 0.1),
        lambda v, i: metrics.subthreshold_slope(v, i, 1.0),
        metrics.gm,
        metrics.gds,
    ):
        with pytest.raises(MetricError, match="non-finite"):
            fn(good, bad_i)
        with pytest.raises(MetricError, match="non-finite"):
            fn(bad_v, cur)
        with pytest.raises(MetricError, match="increasing"):
            fn(good[::-1], cur)
        with pytest.raises(MetricError, match="increasing"):
            fn(np.array([0.0, 1.0, 1.0, 2.0]), cur)
    with pytest.raises(MetricError):
        metrics.dibl(float("nan"), 0.6)
    with pytest.raises(MetricError):
        metrics.id_lin(good, cur, 10.0)  # Vt + 0.5 beyond the sweep
    with pytest.raises(MetricError):
        metrics.idsat_per_um(-1e-3, 10.0)  # wrong sign is an error, not a silent abs()
    assert issubclass(MetricError, ValueError)


def test_maxgm_without_positive_gm():
    with pytest.raises(MetricError, match="gm is nowhere positive"):
        metrics.vt_maxgm(V05, -V05, 0.1)


# --- extract_all --------------------------------------------------------------------------

KEYS = {
    "vt_lin_maxgm", "vt_lin_cc", "vt_sat_cc", "dibl_mv_per_v", "body_effect_v",
    "idsat_ua_per_um", "id_lin_a", "gm_peak_s", "gds_at_5v_s", "ss_mv_per_dec",
    "ioff_pa_per_um", "cgg_inv_ff", "cgg_acc_ff",
}  # fmt: skip


def test_extract_all_nfet_values():
    m = metrics.extract_all(NFET, G, nfet_data())
    assert set(m) == KEYS
    assert all(isinstance(v, float) and np.isfinite(v) for v in m.values())
    assert m["vt_lin_maxgm"] == pytest.approx(VT, abs=3e-3)
    assert m["ss_mv_per_dec"] == pytest.approx(SS_MV, abs=0.5)
    assert m["dibl_mv_per_v"] == pytest.approx(8.163265, abs=0.5)
    assert m["body_effect_v"] == pytest.approx(0.2, abs=5e-3)
    assert m["idsat_ua_per_um"] == pytest.approx(
        model_id(5.0, vt_shift(0, VDS_SAT)) * 1e6 / 10, rel=1e-9
    )
    assert m["ioff_pa_per_um"] == pytest.approx(0.3)
    d = 1e-4 * (5 - 0.7) ** 2
    t = np.tanh(5.0)
    analytic = d * ((1 - t * t) * (1 + 0.02 * 5) + t * 0.02)
    assert m["gds_at_5v_s"] == pytest.approx(analytic, rel=1e-3)
    assert m["cgg_inv_ff"] == pytest.approx(cgg_model(5.0) * 1e15)
    assert m["cgg_acc_ff"] == pytest.approx(cgg_model(-5.0) * 1e15)
    assert m["cgg_inv_ff"] > m["cgg_acc_ff"] > 0


def test_extract_all_pfet_identical_to_nfet():
    nd = nfet_data()
    pd_ = pfet_data(nd)
    assert np.all(pd_["idvg_sat"]["id"] < 0) and np.all(pd_["idvg_sat"]["vg"] <= 0)
    mn = metrics.extract_all(NFET, G, nd)
    mp = metrics.extract_all(FAKE_P, FAKE_P.geometries[0], pd_)
    assert mp.keys() == mn.keys()
    for k in mn:
        assert mp[k] == pytest.approx(mn[k], rel=1e-12), k


def test_extract_all_sign_error_is_not_hidden():
    # nfet-signed data given to a pfet device must fail loudly, not be rescued by abs()
    with pytest.raises(MetricError):
        metrics.extract_all(FAKE_P, FAKE_P.geometries[0], nfet_data())


def test_extract_all_missing_body_bias_group():
    nd = nfet_data()
    keep = np.abs(nd["idvg_lin"]["vb"]) < 1.5
    nd["idvg_lin"] = {k: v[keep] for k, v in nd["idvg_lin"].items()}
    with pytest.raises(MetricError, match="no points"):
        metrics.extract_all(NFET, G, nd)
