# SPDX-License-Identifier: Apache-2.0
"""Netlist generation: instance parameters, bias plan (polarity, grids) and ngspice text."""

import math
from pathlib import Path

import numpy as np
import pytest

from gf180tcad.devices import DEVICES, SWEEPS, Device, Geometry, Sweep
from gf180tcad.pdk import PdkInfo
from gf180tcad.spice.netlist import (
    NGSPICE_VECTORS,
    RAW_NAME,
    bias_plan,
    instance_params,
    ngspice_netlist,
)

NGSPICE_DIR = Path("/foss/pdks/gf180mcuD/libs.tech/ngspice")
PDK = PdkInfo(
    root=Path("/foss/pdks"),
    variant="gf180mcuD",
    open_pdks_commit="1689ac3f2dc763876eaf967227c7dfe831b031ae",
    ngspice_lib=NGSPICE_DIR / "sm141064.ngspice",
    ngspice_design=NGSPICE_DIR / "design.ngspice",
    xyce_lib=Path("/foss/pdks/gf180mcuD/libs.tech/xyce/sm141064.xyce"),
    xyce_design=Path("/foss/pdks/gf180mcuD/libs.tech/xyce/design.xyce"),
)
NFET, PFET = DEVICES["nfet_05v0"], DEVICES["pfet_05v0"]
SW = {s.name: s for s in SWEEPS}
V05 = np.array([i / 100 for i in range(501)])
VCV = np.array([(i - 100) / 20 for i in range(201)])


def _lines(text: str) -> list[str]:
    return text.splitlines()


# --- instance parameters (PDK xschem symbol defaults, nf = 1) -----------------------------


def test_instance_params_w10():
    p = instance_params(NFET, Geometry(10, 0.6, "calibration"))
    assert p == {
        "l": "0.6u",
        "w": "10u",
        "nf": "1",
        "ad": "1.8e-12",
        "as": "1.8e-12",
        "pd": "2.036e-5",
        "ps": "2.036e-5",
        "nrd": "1.8e-2",
        "nrs": "1.8e-2",
        "sa": "0",
        "sb": "0",
        "sd": "0",
        "m": "1",
    }
    assert list(p) == ["l", "w", "nf", "ad", "as", "pd", "ps", "nrd", "nrs", "sa", "sb", "sd", "m"]


def test_instance_params_w1p6():
    p = instance_params(PFET, Geometry(1.6, 0.7, "validation"))
    assert p == {
        "l": "0.7u",
        "w": "1.6u",
        "nf": "1",
        "ad": "2.88e-13",
        "as": "2.88e-13",
        "pd": "3.56e-6",
        "ps": "3.56e-6",
        "nrd": "1.125e-1",
        "nrs": "1.125e-1",
        "sa": "0",
        "sb": "0",
        "sd": "0",
        "m": "1",
    }


def test_instance_params_float_w_same_values():
    p = instance_params(NFET, Geometry(10.0, 2.0, "calibration"))
    assert (p["w"], p["l"]) == ("10.0u", "2.0u")
    assert (p["ad"], p["pd"], p["nrd"]) == ("1.8e-12", "2.036e-5", "1.8e-2")


def test_instance_params_exact_not_float_product():
    # 3.3 * 0.18 = 0.594 exactly in decimal; the float product is 0.5940000000000001.
    p = instance_params(NFET, Geometry(3.3, 1, "validation"))
    assert (p["ad"], p["pd"]) == ("5.94e-13", "6.96e-6")
    assert float(p["nrd"]) == pytest.approx(0.18 / 3.3, rel=1e-15)


# --- bias plan: polarity and grids --------------------------------------------------------


def test_bias_plan_nfet_idvg_order_and_values():
    plan = bias_plan(NFET, SW["idvg_sat"])
    assert plan.npoints == 501 * 3
    grid = plan.grid()
    assert list(grid) == ["vd", "vg", "vb"]
    np.testing.assert_array_equal(grid["vg"], np.tile(V05, 3))  # vgs fastest
    np.testing.assert_array_equal(grid["vb"], np.repeat([0.0, -1.0, -2.0], 501))
    np.testing.assert_array_equal(grid["vd"], np.full(1503, 5.0))


def test_bias_plan_pfet_polarity_and_no_negative_zero():
    grid = bias_plan(PFET, SW["idvg_lin"]).grid()
    np.testing.assert_array_equal(grid["vg"], np.tile(-V05, 3) + 0.0)
    np.testing.assert_array_equal(grid["vb"], np.repeat([0.0, 1.0, 2.0], 501))
    np.testing.assert_array_equal(grid["vd"], np.full(1503, -0.1))
    for v in grid.values():
        assert not np.any(np.signbit(v) & (v == 0)), "-0.0 would be written as '-0.0' in CSV"


def test_bias_plan_idvd_nests_over_vgs():
    plan = bias_plan(NFET, SW["idvd"])
    grid = plan.grid()
    assert plan.npoints == 501 * 5
    np.testing.assert_array_equal(grid["vd"], np.tile(V05, 5))
    np.testing.assert_array_equal(grid["vg"], np.repeat([1.0, 2.0, 3.0, 4.0, 5.0], 501))
    np.testing.assert_array_equal(grid["vb"], np.zeros(2505))


def test_bias_plan_cv_polarity():
    np.testing.assert_array_equal(bias_plan(NFET, SW["cv"]).grid()["vg"], VCV)
    np.testing.assert_array_equal(bias_plan(PFET, SW["cv"]).grid()["vg"], -VCV + 0.0)


def test_bias_plan_rejects_unsupported_shapes():
    with pytest.raises(ValueError, match="vds"):
        bias_plan(NFET, Sweep("x", "idvg", vds=(0.1, 5.0), vgs=(0.0, 1.0), vbs=(0.0,)))
    with pytest.raises(ValueError, match="vbs"):
        bias_plan(NFET, Sweep("x", "idvd", vds=(0.0, 1.0), vgs=(1.0,), vbs=(0.0, 1.0)))
    with pytest.raises(ValueError, match="freq"):
        bias_plan(NFET, Sweep("x", "cv", vds=(0.0,), vgs=(0.0, 1.0), vbs=(0.0,)))


# --- ngspice netlist ----------------------------------------------------------------------


def test_nfet_idvg_lin_netlist_exact():
    text = ngspice_netlist(
        NFET, Geometry(10, 0.6, "calibration"), SW["idvg_lin"], "typical", 25.0, PDK
    )
    assert text == (
        "* gf180tcad ngspice nfet_05v0 w10p0_l0p60 idvg_lin corner=typical temp_c=25.0\n"
        ".include /foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice\n"
        ".lib /foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice typical\n"
        ".temp 25.0\n"
        "vd d 0 dc 0.1\n"
        "vg g 0 dc 0.0\n"
        "vb b 0 dc 0.0\n"
        "xdut d g 0 b nfet_05v0 l=0.6u w=10u nf=1 ad=1.8e-12 as=1.8e-12 pd=2.036e-5"
        " ps=2.036e-5 nrd=1.8e-2 nrs=1.8e-2 sa=0 sb=0 sd=0 m=1\n"
        ".dc vg 0.0 5.0 0.01 vb 0.0 -2.0 -1.0\n"
        ".control\n"
        "set num_threads=1\n"
        "set filetype=binary\n"
        "run\n"
        f"write {RAW_NAME} v(d) v(g) v(b) i(vd) i(vg) i(vb)\n"
        ".endc\n"
        ".end\n"
    )


def test_ngspice_vectors_sign_convention():
    # currents INTO the device terminal = minus the source branch current
    assert NGSPICE_VECTORS["dc"] == {
        "vd": ("v(d)", 1.0),
        "vg": ("v(g)", 1.0),
        "vb": ("v(b)", 1.0),
        "id": ("i(vd)", -1.0),
        "ig": ("i(vg)", -1.0),
        "ib": ("i(vb)", -1.0),
    }
    assert NGSPICE_VECTORS["cv"] == {"vg": ("vg", 1.0), "cgg": ("cgg", 1.0)}


def test_pfet_polarity():
    text = ngspice_netlist(PFET, Geometry(10, 0.5, "calibration"), SW["idvg_sat"], "ss", 25.0, PDK)
    lines = _lines(text)
    assert "vd d 0 dc -5.0" in lines  # negative Vds
    assert ".dc vg 0.0 -5.0 -0.01 vb 0.0 2.0 1.0" in lines  # negative Vgs, positive bulk
    dut = [x for x in lines if x.startswith("xdut ")]
    assert len(dut) == 1 and dut[0].startswith("xdut d g 0 b pfet_05v0 ")  # source tied to 0
    assert ".lib /foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice ss" in lines


def test_idvd_netlist_sweeps_vd_inner_vg_outer():
    text = ngspice_netlist(PFET, Geometry(10, 1, "validation"), SW["idvd"], "ff", 25.0, PDK)
    assert ".dc vd 0.0 -5.0 -0.01 vg -1.0 -5.0 -1.0" in _lines(text)
    assert "vb b 0 dc 0.0" in _lines(text)


def test_ioff_single_point():
    lines = _lines(ngspice_netlist(PFET, Geometry(10, 1, "validation"), SW["ioff"], "sf", 25, PDK))
    assert "vd d 0 dc -5.5" in lines
    assert ".dc vg 0.0 0.0 1.0" in lines
    assert "vb b 0 dc 0.0" in lines


def test_netlist_has_no_stat():
    for device in (NFET, PFET):
        for sweep in SWEEPS:
            text = ngspice_netlist(device, device.geometries[0], sweep, "typical", 25.0, PDK)
            lines = _lines(text)
            # design.ngspice sets sw_stat_global=0 and sw_stat_mismatch=0; nothing overrides it.
            assert f".include {PDK.ngspice_design}" in lines
            libs = [x for x in lines if x.lower().startswith(".lib")]
            assert libs == [f".lib {PDK.ngspice_lib} typical"]
            assert lines.index(f".include {PDK.ngspice_design}") < lines.index(libs[0])
            low = text.lower()
            for word in ("statistical", "agauss", "sw_stat", ".param", "mc_skew"):
                assert word not in low


def test_control_block_sets_threads_and_binary_before_analysis():
    for sweep in SWEEPS:
        lines = _lines(ngspice_netlist(NFET, NFET.geometries[0], sweep, "typical", 25.0, PDK))
        start = lines.index(".control")
        assert lines[start + 1 : start + 3] == ["set num_threads=1", "set filetype=binary"]
        first_analysis = min(
            i for i, x in enumerate(lines) if i > start and x.split()[0] in ("run", "ac")
        )
        assert first_analysis > start + 2
        assert sum(x.startswith("write ") for x in lines) == 1
        assert lines[-2:] == [".endc", ".end"]


def test_cv_netlist():
    text = ngspice_netlist(NFET, Geometry(10, 10, "calibration"), SW["cv"], "typical", 25.0, PDK)
    lines = _lines(text)
    assert "vg g 0 dc -5.0 ac 1" in lines
    assert "vd d 0 dc 0.0" in lines and "vb b 0 dc 0.0" in lines
    assert not any(x.startswith((".dc", ".ac")) for x in lines)
    (loop,) = [x for x in lines if x.startswith("foreach ")]
    assert loop.split()[2:] == [repr(v) for v in VCV.tolist()]
    assert "alter vg dc = $v" in lines
    assert "ac lin 1 1000000.0 1000000.0" in lines
    # Current into the gate is -i(vg) = j*2*pi*f*Cgg*vac (vac = 1), so Cgg = -imag(i(vg))/(2*pi*f)
    assert "let {$resplot}.cgg[{$resplot}.k] = -imag(i(vg))/(2*pi*1000000.0)" in lines
    # vg is read back from the circuit (the source's DC value after alter), not the loop variable
    assert "let {$resplot}.vg[{$resplot}.k] = @vg[dc]" in lines
    assert lines.index("alter vg dc = $v") < lines.index("ac lin 1 1000000.0 1000000.0")
    assert lines[-4:] == ["setplot $resplot", f"write {RAW_NAME} vg cgg", ".endc", ".end"]


def test_cv_pfet_applies_polarity():
    lines = _lines(ngspice_netlist(PFET, PFET.geometries[0], SW["cv"], "typical", 25.0, PDK))
    assert "vg g 0 dc 5.0 ac 1" in lines
    (loop,) = [x for x in lines if x.startswith("foreach ")]
    assert loop.split()[2:] == [repr(-v + 0.0) for v in VCV.tolist()]


def test_netlist_rejects_bad_inputs():
    g = NFET.geometries[0]
    with pytest.raises(ValueError, match="corner"):
        ngspice_netlist(NFET, g, SW["idvg_lin"], "tt", 25.0, PDK)
    with pytest.raises(ValueError, match="temp"):
        ngspice_netlist(NFET, g, SW["idvg_lin"], "typical", math.nan, PDK)
    uneven = Sweep("x", "idvg", vds=(0.1,), vgs=(0.0, 0.1, 0.3), vbs=(0.0,))
    with pytest.raises(ValueError, match="evenly spaced"):
        ngspice_netlist(NFET, g, uneven, "typical", 25.0, PDK)
    bad = Device("bad", 1, "nfet_05v0\nvx d 0 dc 1", NFET.geometries)
    with pytest.raises(ValueError, match="model"):
        ngspice_netlist(bad, g, SW["idvg_lin"], "typical", 25.0, PDK)
