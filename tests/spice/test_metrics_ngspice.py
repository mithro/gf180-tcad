# SPDX-License-Identifier: Apache-2.0
"""Metric extraction on real ngspice results (-m sandbox): plausible ranges only."""

import pytest

from gf180tcad import metrics
from gf180tcad.devices import DEVICES, SWEEPS
from gf180tcad.spice.ngspice import simulate

NFET, PFET = DEVICES["nfet_05v0"], DEVICES["pfet_05v0"]


@pytest.mark.sandbox
@pytest.mark.parametrize("device", [NFET, PFET], ids=lambda d: d.name)
def test_ngspice_smoke_plausible_ranges(image_pdk, tmp_path, device, capsys):
    lmin = {"nfet_05v0": 0.6, "pfet_05v0": 0.5}
    g = next(x for x in device.geometries if x.w_um == 10 and x.l_um == lmin[device.name])
    data = {}
    for sweep in SWEEPS:
        out = tmp_path / sweep.name
        out.mkdir()
        data[sweep.name] = simulate(device, g, sweep, "typical", 25.0, image_pdk, out)
    m = metrics.extract_all(device, g, data)
    with capsys.disabled():
        print(f"\nSMOKE {device.name} {g}: {m}")
    assert 0.4 < m["vt_lin_maxgm"] < 1.0
    assert 0.4 < m["vt_lin_cc"] < 1.0
    lo, hi = (300, 700) if device.polarity > 0 else (100, 500)  # pfet has ~2-3x lower mobility
    assert lo < m["idsat_ua_per_um"] < hi
    assert m["body_effect_v"] > 0
