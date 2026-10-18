# SPDX-License-Identifier: Apache-2.0
import dataclasses

import pytest

from gf180tcad.devices import (
    CORNERS,
    DEVICES,
    SWEEPS,
    TEMPS_C,
    Device,
    Geometry,
    Sweep,
    geometry_id,
)

NFET = [(10, 0.6), (10, 0.7), (10, 1), (10, 2), (10, 10), (1.6, 0.7)]
PFET = [(10, 0.5), (10, 0.7), (10, 1), (10, 2), (10, 10), (1.6, 0.7)]


def test_device_keys_and_models():
    assert list(DEVICES) == ["nfet_05v0", "pfet_05v0"]
    assert DEVICES["nfet_05v0"].polarity == 1
    assert DEVICES["pfet_05v0"].polarity == -1
    for name, dev in DEVICES.items():
        assert dev.name == name
        assert dev.spice_model == name


@pytest.mark.parametrize("name,expected", [("nfet_05v0", NFET), ("pfet_05v0", PFET)])
def test_geometries_in_order(name, expected):
    got = [(g.w_um, g.l_um) for g in DEVICES[name].geometries]
    assert got == expected


@pytest.mark.parametrize(
    "name,lmin,", [("nfet_05v0", 0.6), ("pfet_05v0", 0.5)]
)
def test_roles(name, lmin):
    geoms = DEVICES[name].geometries
    cal = {(g.w_um, g.l_um) for g in geoms if g.role == "calibration"}
    val = {(g.w_um, g.l_um) for g in geoms if g.role == "validation"}
    assert cal == {(10, 10), (10, 2), (10, lmin)}
    assert val == {(10, 0.7), (10, 1), (1.6, 0.7)}


def test_geometry_ids():
    assert geometry_id(Geometry(10, 0.6, "calibration")) == "w10p0_l0p60"
    assert geometry_id(Geometry(1.6, 0.7, "validation")) == "w1p6_l0p70"
    assert geometry_id(Geometry(10, 10, "calibration")) == "w10p0_l10p00"
    for dev in DEVICES.values():
        ids = [geometry_id(g) for g in dev.geometries]
        assert len(set(ids)) == len(ids)


def test_corners_temps_order():
    assert CORNERS == ("typical", "ff", "ss", "fs", "sf")
    assert TEMPS_C == (25.0,)
    assert [s.name for s in SWEEPS] == ["idvg_lin", "idvg_sat", "idvd", "cv", "ioff"]


def test_idvg_sweeps():
    s = {x.name: x for x in SWEEPS}
    grid = tuple(i / 100 for i in range(501))
    for name, vds in (("idvg_lin", 0.1), ("idvg_sat", 5.0)):
        sw = s[name]
        assert sw.kind == "idvg"
        assert sw.vds == (vds,)
        assert sw.vgs == grid
        assert len(sw.vgs) == 501
        assert sw.vgs[1] == 0.01
        assert sw.vgs[-1] == 5.0
        assert sw.vbs == (0.0, 1.0, 2.0)
        assert sw.freq_hz is None


def test_idvd():
    sw = next(x for x in SWEEPS if x.name == "idvd")
    assert sw.kind == "idvd"
    assert sw.vgs == (1.0, 2.0, 3.0, 4.0, 5.0)
    assert sw.vds == tuple(i / 100 for i in range(501))
    assert sw.vbs == (0.0,)
    assert sw.freq_hz is None


def test_cv():
    sw = next(x for x in SWEEPS if x.name == "cv")
    assert sw.kind == "cv"
    assert sw.vgs == tuple((i - 100) / 20 for i in range(201))
    assert len(sw.vgs) == 201
    assert sw.vgs[0] == -5.0
    assert sw.vgs[100] == 0.0
    assert sw.vgs[-1] == 5.0
    assert sw.vds == (0.0,)
    assert sw.vbs == (0.0,)
    assert sw.freq_hz == 1e6


def test_ioff():
    sw = next(x for x in SWEEPS if x.name == "ioff")
    assert sw.kind == "idvg"
    assert sw.vds == (5.5,)
    assert sw.vgs == (0.0,)
    assert sw.vbs == (0.0,)
    assert sw.freq_hz is None


def test_hashable_and_frozen():
    hash(DEVICES["nfet_05v0"])
    hash(SWEEPS[0])
    with pytest.raises(dataclasses.FrozenInstanceError):
        SWEEPS[0].name = "x"  # type: ignore[misc]


@pytest.mark.parametrize(
    "make",
    [
        lambda: Geometry(0, 1, "calibration"),
        lambda: Geometry(1, -1, "calibration"),
        lambda: Geometry(1, 1, "bogus"),
        lambda: Device("d", 1, "m", ()),
        lambda: Device("d", 2, "m", (Geometry(1, 1, "validation"),)),
        lambda: Sweep("s", "bogus", (0.0,), (0.0,), (0.0,)),
        lambda: Sweep("s", "idvg", (), (0.0,), (0.0,)),
        lambda: Sweep("s", "idvg", (0.0,), (), (0.0,)),
        lambda: Sweep("s", "idvg", (0.0,), (0.0,), ()),
    ],
)
def test_invalid_raises(make):
    with pytest.raises(ValueError):
        make()
