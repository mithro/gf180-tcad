# SPDX-License-Identifier: Apache-2.0
"""Xyce netlist, log checks, CSV parsing, engine_diff, and real runs (-m sandbox)."""

import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

from gf180tcad import io, sandbox
from gf180tcad.devices import DEVICES, SWEEPS, Device, Geometry, geometry_id
from gf180tcad.pdk import PdkInfo
from gf180tcad.spice import xyce
from gf180tcad.spice.common import SpiceError
from gf180tcad.spice.netlist import bias_plan, instance_params
from gf180tcad.spice.ngspice import simulate
from gf180tcad.spice.xyce import (
    XYCE_VECTORS,
    engine_diff,
    processor_count,
    read_print_csv,
    run_xyce,
    scan_xyce_log,
    simulate_xyce,
    xyce_netlist,
)

XYCE_DIR = Path("/foss/pdks/gf180mcuD/libs.tech/xyce")
NGSPICE_DIR = Path("/foss/pdks/gf180mcuD/libs.tech/ngspice")
PDK = PdkInfo(
    root=Path("/foss/pdks"),
    variant="gf180mcuD",
    open_pdks_commit="1689ac3f2dc763876eaf967227c7dfe831b031ae",
    ngspice_lib=NGSPICE_DIR / "sm141064.ngspice",
    ngspice_design=NGSPICE_DIR / "design.ngspice",
    xyce_lib=XYCE_DIR / "sm141064.xyce",
    xyce_design=XYCE_DIR / "design.xyce",
)
NFET, PFET = DEVICES["nfet_05v0"], DEVICES["pfet_05v0"]
SW = {s.name: s for s in SWEEPS}
TOL = 0.005  # spec: engines differing by more than 0.5 % flags a reference problem


def _lines(text: str) -> list[str]:
    return text.splitlines()


# --- netlist -------------------------------------------------------------------------------


def test_nfet_idvg_lin_netlist_exact():
    text = xyce_netlist(
        NFET, Geometry(10, 0.6, "calibration"), SW["idvg_lin"], "typical", 25.0, PDK
    )
    assert text == (
        "* gf180tcad Xyce nfet_05v0 w10p0_l0p60 idvg_lin corner=typical temp_c=25.0\n"
        ".include /foss/pdks/gf180mcuD/libs.tech/xyce/design.xyce\n"
        ".lib /foss/pdks/gf180mcuD/libs.tech/xyce/sm141064.xyce typical\n"
        ".options device temp=25.0\n"
        "vd d 0 dc 0.1\n"
        "vg g 0 dc 0.0\n"
        "vb b 0 dc 0.0\n"
        "xdut d g 0 b nfet_06v0 l=0.6u w=10u nf=1 ad=1.8e-12 as=1.8e-12 pd=2.036e-5"
        " ps=2.036e-5 nrd=1.8e-2 nrs=1.8e-2 sa=0 sb=0 sd=0 m=1\n"
        ".dc vg 0.0 5.0 0.01 vb 0.0 -2.0 -1.0\n"
        f".print dc format=csv precision=17 file={xyce.CSV_NAME} v(d) v(g) v(b) i(vd) i(vg) i(vb)\n"
        ".end\n"
    )


def test_instance_params_identical_to_ngspice():
    for device in (NFET, PFET):
        for g in device.geometries:
            text = xyce_netlist(device, g, SW["idvd"], "typical", 25.0, PDK)
            (dut,) = [x for x in _lines(text) if x.startswith("xdut ")]
            params = " ".join(f"{k}={v}" for k, v in instance_params(device, g).items())
            assert dut == f"xdut d g 0 b {xyce.XYCE_SUBCKT[device.spice_model]} {params}"


def test_xyce_subckt_mapping():
    # The image's Xyce lib has no *_05v0 wrappers; the ngspice *_05v0 wrappers instantiate the
    # *_06v0 model cards with the same mismatch parameters (checked in the sandbox below).
    assert xyce.XYCE_SUBCKT == {"nfet_05v0": "nfet_06v0", "pfet_05v0": "pfet_06v0"}


def test_pfet_polarity_and_corner():
    text = xyce_netlist(PFET, Geometry(10, 0.5, "calibration"), SW["idvg_sat"], "ss", 25.0, PDK)
    lines = _lines(text)
    assert "vd d 0 dc -5.0" in lines
    assert ".dc vg 0.0 -5.0 -0.01 vb 0.0 2.0 1.0" in lines
    (dut,) = [x for x in lines if x.startswith("xdut ")]
    assert dut.startswith("xdut d g 0 b pfet_06v0 ")
    assert f".lib {PDK.xyce_lib} ss" in lines


def test_idvd_sweeps_vd_inner_vg_outer():
    text = xyce_netlist(PFET, Geometry(10, 1, "validation"), SW["idvd"], "ff", 25.0, PDK)
    assert ".dc vd 0.0 -5.0 -0.01 vg -1.0 -5.0 -1.0" in _lines(text)
    assert "vb b 0 dc 0.0" in _lines(text)


def test_temperature_is_a_device_option_not_dot_temp():
    # Xyce 7.10 ignores ".temp" ("Unrecognized dot line will be ignored") and would run at 27 C.
    lines = _lines(xyce_netlist(NFET, NFET.geometries[0], SW["idvd"], "typical", 27.5, PDK))
    assert ".options device temp=27.5" in lines
    assert not any(x.lower().startswith(".temp") for x in lines)


def test_netlist_has_no_stat():
    for device in (NFET, PFET):
        for name in ("idvg_lin", "idvg_sat", "idvd", "ioff"):
            text = xyce_netlist(device, device.geometries[0], SW[name], "typical", 25.0, PDK)
            lines = _lines(text)
            assert f".include {PDK.xyce_design}" in lines
            libs = [x for x in lines if x.lower().startswith(".lib")]
            assert libs == [f".lib {PDK.xyce_lib} typical"]
            assert lines.index(f".include {PDK.xyce_design}") < lines.index(libs[0])
            for word in ("statistical", "agauss", "sw_stat", ".param", "mc_skew"):
                assert word not in text.lower()


def test_cv_not_implemented():
    with pytest.raises(NotImplementedError, match="cv"):
        xyce_netlist(NFET, NFET.geometries[0], SW["cv"], "typical", 25.0, PDK)


def test_netlist_rejects_bad_inputs():
    g = NFET.geometries[0]
    with pytest.raises(ValueError, match="corner"):
        xyce_netlist(NFET, g, SW["idvg_lin"], "tt", 25.0, PDK)
    with pytest.raises(ValueError, match="temp"):
        xyce_netlist(NFET, g, SW["idvg_lin"], "typical", math.nan, PDK)
    bad = Device("bad", 1, "nfet_05v0\nvx d 0 dc 1", NFET.geometries)
    with pytest.raises(ValueError, match="model"):
        xyce_netlist(bad, g, SW["idvg_lin"], "typical", 25.0, PDK)


def test_xyce_vectors_sign_convention():
    # Xyce's I(Vx) is the branch current into the source's + node, as in ngspice
    assert XYCE_VECTORS == {
        "vd": ("V(D)", 1.0),
        "vg": ("V(G)", 1.0),
        "vb": ("V(B)", 1.0),
        "id": ("I(VD)", -1.0),
        "ig": ("I(VG)", -1.0),
        "ib": ("I(VB)", -1.0),
    }


# --- CSV .print output ---------------------------------------------------------------------


def test_read_print_csv_by_header_name(tmp_path):
    p = tmp_path / "out.csv"
    p.write_text("I(VD),V(D)\n1.5e-3,0.00000000000000000e+00\n-2.25e-07,1.00000000000000002e-02\n")
    cols = read_print_csv(p)
    assert list(cols) == ["I(VD)", "V(D)"]
    np.testing.assert_array_equal(cols["V(D)"], [0.0, 0.01])
    np.testing.assert_array_equal(cols["I(VD)"], [1.5e-3, -2.25e-7])


def test_read_print_csv_normalises_header_case_and_space(tmp_path):
    p = tmp_path / "out.csv"
    p.write_text(" v(d) , i(vd)\n1,2\n")
    assert list(read_print_csv(p)) == ["V(D)", "I(VD)"]


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("", "empty"),
        ("V(D),I(VD)\n", "no data"),
        ("V(D),V(D)\n1,2\n", "duplicate"),
        ("V(D),I(VD)\n1,2\n3\n", "line 3"),
        ("V(D),I(VD)\n1,abc\n", "line 2"),
        ("V(D),I(VD)\n1,nan\n", "line 2"),
    ],
)
def test_read_print_csv_rejects_malformed(tmp_path, text, match):
    p = tmp_path / "out.csv"
    p.write_text(text)
    with pytest.raises(SpiceError, match=match):
        read_print_csv(p)


# --- log scanning --------------------------------------------------------------------------

BINNING_WARNING = (
    "Netlist warning in file /foss/pdks/gf180mcuD/libs.tech/xyce/sm141064.spice at\n"
    " or near line 105\n"
    " MODEL_BINNING:  duplicate PARSER parameter.  Using the first value found = true\n"
    " \n"
)
SUMMARY = """
***** Solution Summary *****
\tNumber Successful Steps Taken:\t\t2505
\tNumber Failed Steps Attempted:\t\t0
\tNumber Jacobians Evaluated:\t\t5199
\tNumber Linear Solves:\t\t\t5199
\tNumber Failed Linear Solves:\t\t0
\tNumber Residual Evaluations:\t\t7705
\tNumber Nonlinear Convergence Failures:\t0
\tTotal Residual Load Time:\t\t0.0297205 seconds

***** End of Xyce(TM) Simulation
*****

Timing summary of 1 processor
                 Stats                   Count       CPU Time              Wall Time
Xyce                                         1        0.576 (100.0%)        1.154 (100.0%)
"""
CLEAN_LOG = (
    "\n*****\n***** Welcome to the Xyce(TM) Parallel Electronic Simulator\n*****\n"
    "***** Executing netlist xyce.cir\n\n***** Reading and parsing netlist...\n"
    + BINNING_WARNING
    + "***** Setting up topology...\n"
    + SUMMARY
)


def test_clean_log_keeps_joined_warning():
    assert scan_xyce_log(CLEAN_LOG) == [
        (
            "Netlist warning in file /foss/pdks/gf180mcuD/libs.tech/xyce/sm141064.spice at"
            " or near line 105"
            " MODEL_BINNING:  duplicate PARSER parameter.  Using the first value found = true"
        )
    ]


def test_processor_count():
    assert processor_count(CLEAN_LOG) == 1
    assert processor_count(CLEAN_LOG.replace("of 1 processor", "of 4 processors")) == 4
    with pytest.raises(SpiceError, match="processor"):
        processor_count(CLEAN_LOG.replace("Timing summary of 1 processor\n", ""))


@pytest.mark.parametrize(
    "fatal",
    [
        "Netlist error in file x.cir at or near line 3\n Subcircuit NOSUCH has not been defined\n",
        "Simulation aborted due to error.  There are 0 MSG_FATAL errors and 1 MSG_ERROR\n errors\n",
        "*** Xyce Abort ***\n",
        "\tStep size reached minimum step size bound\n",
        "Time step too small near step number: 3  Exiting transient loop.\n",
        "DC Operating Point Failed.  Exiting transient loop\n",
        "\tFailed DC sweep steps:\t\t\n",
        (
            "Netlist warning: Numerically singular matrix found by Amesos, returning zero\n"
            " solution to nonlinear solver!\n"
        ),
        "Netlist warning: Voltage Node (Y) does not have a DC path to ground\n",
        (
            "Netlist warning in file xyce.cir at or near line 4\n"
            " Unrecognized dot line will be ignored\n"
        ),
        "Nonlinear solver failed to converge\n",
    ],
)
def test_fatal_messages_raise(fatal):
    log = CLEAN_LOG.replace("***** Setting up topology...\n", fatal + "***** Setting up topology\n")
    with pytest.raises(SpiceError) as exc:
        scan_xyce_log(log)
    assert fatal.splitlines()[0].strip() in str(exc.value)
    assert "--- Xyce log" in str(exc.value)


@pytest.mark.parametrize(
    "counter",
    [
        "Number Failed Steps Attempted",
        "Number Failed Linear Solves",
        "Number Nonlinear Convergence Failures",
    ],
)
def test_nonzero_failure_counters_are_fatal(counter):
    log = re.sub(rf"({counter}:\s*)0", r"\g<1>7", CLEAN_LOG)
    assert log != CLEAN_LOG
    with pytest.raises(SpiceError, match=counter):
        scan_xyce_log(log)


# --- engine_diff ---------------------------------------------------------------------------


def _res(id_, *, vd=None):
    n = len(id_)
    return {
        "vd": np.linspace(0, 5, n) if vd is None else vd,
        "vg": np.full(n, 5.0),
        "vb": np.zeros(n),
        "id": np.asarray(id_, dtype=np.float64),
        "ig": np.zeros(n),
        "ib": np.zeros(n),
    }


def test_engine_diff_max_relative_with_max_denominator():
    a = _res([1e-3, 2e-6, -4e-4])
    b = _res([1.001e-3, 2e-6, -4.04e-4])
    # |a-b| / max(|a|,|b|): 1e-6/1.001e-3, 0, 4e-6/4.04e-4
    assert engine_diff(a, b) == pytest.approx(4e-6 / 4.04e-4, rel=1e-12)
    assert engine_diff(b, a) == engine_diff(a, b)  # symmetric


def test_engine_diff_ignores_points_below_floor_in_both():
    a = _res([1e-13, 5e-13, 1e-3])
    b = _res([9e-13, -5e-13, 1e-3])
    assert engine_diff(a, b) == 0.0  # both tiny at the first two points
    # above the floor in EITHER engine counts: 2e-12 vs 1e-13 is a ~95 % difference
    assert engine_diff(_res([2e-12]), _res([1e-13])) == pytest.approx(0.95)


def test_engine_diff_sign_flip_is_large():
    assert engine_diff(_res([1e-6]), _res([-1e-6])) == pytest.approx(2.0)


def test_engine_diff_all_below_floor_is_zero():
    assert engine_diff(_res([0.0, 1e-15]), _res([1e-14, 0.0])) == 0.0


def test_engine_diff_other_key():
    a, b = _res([1.0]), _res([1.0])
    b["ib"] = np.array([1e-9])
    assert engine_diff(a, b, key="ib") == pytest.approx(1.0)


def test_engine_diff_requires_identical_bias_columns():
    a = _res([1e-3, 1e-3])
    b = _res([1e-3, 1e-3], vd=np.array([0.0, 5.0 + 1e-15]))
    with pytest.raises(ValueError, match="vd"):
        engine_diff(a, b)
    c = _res([1e-3, 1e-3])
    del c["vb"]
    with pytest.raises(ValueError, match="vb"):
        engine_diff(a, c)
    with pytest.raises(ValueError, match="shape"):
        engine_diff(a, _res([1e-3, 1e-3, 1e-3]))


def test_engine_diff_rejects_non_finite():
    with pytest.raises(ValueError, match="finite"):
        engine_diff(_res([np.nan]), _res([1.0]))


# --- real Xyce runs ------------------------------------------------------------------------


def _w10(device, l_um):
    return next(g for g in device.geometries if g.w_um == 10 and g.l_um == l_um)


_PDK_CHECK = r"""
import json, re, sys
from gf180tcad import pdk
info = pdk.locate()

def sections(path):
    return re.findall(r"(?im)^\.lib\s+(\S+)\s*$", open(path).read())

def subckts(path):
    out, cur = {}, None
    for line in open(path):
        low = line.strip().lower()
        if low.startswith(".subckt "):
            cur = line.split()[1]
            out[cur] = []  # body lines only: the header's w/l defaults may differ
        elif low.startswith(".ends"):
            cur = None
        elif cur is not None:
            out[cur].append(line.strip().replace("'", ""))
    return out

xs, ns = subckts(info.xyce_lib), subckts(info.ngspice_lib)
json.dump({
    "xyce_sections": sections(info.xyce_lib),
    "ngspice_sections": sections(info.ngspice_lib),
    "xyce_subckts": {k: v for k, v in xs.items() if "fet_0" in k},
    "ngspice_subckts": {k: v for k, v in ns.items() if "fet_0" in k},
    "xyce_design": open(info.xyce_design).read(),
}, sys.stdout)
"""


@pytest.mark.sandbox
def test_xyce_lib_matches_ngspice_lib_structure(tmp_path):
    res = sandbox.run(["python3", "-c", _PDK_CHECK], out_dir=tmp_path)
    info = json.loads(res.stdout)
    # same corner (and all other) section names
    assert info["xyce_sections"] == info["ngspice_sections"]
    for corner in ("typical", "ff", "ss", "fs", "sf"):
        assert corner in info["xyce_sections"]
    # design file disables statistics as design.ngspice does
    assert ".param sw_stat_global=0" in info["xyce_design"].splitlines()
    assert ".param sw_stat_mismatch=0" in info["xyce_design"].splitlines()
    xs, ns = info["xyce_subckts"], info["ngspice_subckts"]
    for model, target in xyce.XYCE_SUBCKT.items():
        # the Xyce lib lacks the 5 V wrappers ...
        assert model not in xs and model in ns
        # ... and the ngspice 5 V wrapper is the 6 V wrapper body (only the w/l defaults differ)
        assert ns[model] == ns[target], model
        assert target in xs


@pytest.mark.sandbox
def test_xyce_runs_single_process(image_pdk, tmp_path):
    sweep = SW["idvg_sat"]
    res = simulate_xyce(NFET, _w10(NFET, 0.6), sweep, "typical", 25.0, image_pdk, tmp_path)
    assert list(res) == ["vd", "vg", "vb", "id", "ig", "ib"]
    assert all(v.shape == (501 * 3,) for v in res.values())
    log = (tmp_path / xyce.LOG_NAME).read_text()
    assert "Timing summary of 1 processor\n" in log
    assert processor_count(log) == 1
    grid = bias_plan(NFET, sweep).grid()
    for k in ("vd", "vg", "vb"):
        assert res[k].tobytes() == grid[k].tobytes()
    assert np.all(res["id"].reshape(3, 501)[:, -1] > 1e-3)
    # kept, non-fatal: the lib's repeated ".options parser model_binning", Xyce's BSIM4 version
    # mapping (4.5 -> 4.6.1) and BSIM4's own pbswgd clamp
    known = ("MODEL_BINNING", "older than the oldest version supported", "Pbswgd is set to 0.1")
    assert res.warnings and all(any(k in w for k in known) for w in res.warnings), res.warnings


@pytest.mark.sandbox
def test_xyce_failure_on_bad_model(image_pdk, tmp_path):
    typo = Device("nfet_05v0", 1, "nfet_05v0_typo", NFET.geometries)
    with pytest.raises(SpiceError, match="(?i)subcircuit"):
        simulate_xyce(typo, typo.geometries[0], SW["idvd"], "typical", 25.0, image_pdk, tmp_path)
    assert not (tmp_path / xyce.CSV_NAME).exists()


@pytest.mark.sandbox
def test_xyce_wrong_point_count_is_error(image_pdk, tmp_path):
    text = xyce_netlist(NFET, NFET.geometries[0], SW["idvd"], "typical", 25.0, image_pdk)
    text = text.replace(".dc vd 0.0 5.0 0.01 ", ".dc vd 0.0 4.99 0.01 ")
    with pytest.raises(SpiceError, match="2505 points"):
        run_xyce(text, tmp_path, plan=bias_plan(NFET, SW["idvd"]))


@pytest.mark.sandbox
def test_xyce_floating_node_is_error(image_pdk, tmp_path):
    text = xyce_netlist(NFET, NFET.geometries[0], SW["ioff"], "typical", 25.0, image_pdk)
    text = text.replace("\n.dc ", "\nc1 x 0 1p\nr1 x y 1k\nc2 y 0 1p\n.dc ", 1)
    with pytest.raises(SpiceError):
        run_xyce(text, tmp_path, plan=bias_plan(NFET, SW["ioff"]))


@pytest.mark.sandbox
@pytest.mark.parametrize("device", [NFET, PFET], ids=lambda d: d.name)
def test_xyce_two_runs_byte_identical(image_pdk, tmp_path, device):
    blobs = []
    for run in ("a", "b"):
        out = tmp_path / run
        out.mkdir()
        res = simulate_xyce(
            device, device.geometries[0], SW["idvg_sat"], "typical", 25.0, image_pdk, out
        )
        io.write_csv(out / "idvg_sat.csv", res, {"device": device.name, "engine": "xyce"})
        blobs.append((out / "idvg_sat.csv").read_bytes())
    assert blobs[0] == blobs[1]
    raw = [(tmp_path / r / xyce.CSV_NAME).read_bytes() for r in ("a", "b")]
    assert raw[0] == raw[1]


_CASES = [
    pytest.param(d, g, s, id=f"{d.name}-{geometry_id(g)}-{s}")
    for d in (NFET, PFET)
    for g in d.geometries
    for s in ("idvg_sat", "idvd")
]


@pytest.mark.sandbox
@pytest.mark.parametrize(("device", "g", "sweep_name"), _CASES)
def test_engines_agree(image_pdk, tmp_path, device, g, sweep_name):
    sweep = SW[sweep_name]
    (tmp_path / "ng").mkdir()
    (tmp_path / "xy").mkdir()
    a = simulate(device, g, sweep, "typical", 25.0, image_pdk, tmp_path / "ng")
    b = simulate_xyce(device, g, sweep, "typical", 25.0, image_pdk, tmp_path / "xy")
    d = engine_diff(a, b)
    print(f"engine_diff {device.name} {geometry_id(g)} {sweep_name} {d!r}")
    assert d < TOL, f"ngspice vs Xyce max relative Id difference {d:.3%} > {TOL:.1%}"
