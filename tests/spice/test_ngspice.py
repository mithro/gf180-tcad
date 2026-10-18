# SPDX-License-Identifier: Apache-2.0
"""ngspice runner: log checks, result assembly, and real runs in the sandbox (-m sandbox)."""

import numpy as np
import pytest

from gf180tcad import io, sandbox
from gf180tcad.devices import DEVICES, SWEEPS, Device
from gf180tcad.spice import ngspice
from gf180tcad.spice.netlist import RAW_NAME, bias_plan, ngspice_netlist
from gf180tcad.spice.ngspice import SpiceError, SpiceResult, run_ngspice, scan_log, simulate

NFET, PFET = DEVICES["nfet_05v0"], DEVICES["pfet_05v0"]
SW = {s.name: s for s in SWEEPS}
V05 = np.array([i / 100 for i in range(501)])

CLEAN_LOG = """
Note: No compatibility mode selected!

Circuit: * gf180tcad ngspice nfet_05v0 w10p0_l0p60 idvg_sat corner=typical temp_c=25.0

Doing analysis at TEMP = 25.000000 and TNOM = 27.000000
Using SPARSE 1.3 as Direct Linear Solver
No. of Data Rows : 1503
binary raw file "out.raw"
Note: Simulation executed from .control section
"""


# --- log scanning -------------------------------------------------------------------------


def test_clean_log_has_no_warnings():
    assert scan_log(CLEAN_LOG) == []


def test_other_warnings_are_kept():
    log = CLEAN_LOG + "Warning: m=xx on .subckt line will override multiplier m hierarchy!\n"
    assert scan_log(log) == ["Warning: m=xx on .subckt line will override multiplier m hierarchy!"]


# ngspice 47 notices that it recovered by a stepping method (literal strings from the binary):
# not failures, so they are neither fatal nor dropped.
RECOVERY_NOTICES = [
    "Note: Starting dynamic gmin stepping",
    "Note: Dynamic gmin stepping completed",
    "Note: Starting true gmin stepping",
    "Note: True gmin stepping completed",
    "Note: Starting spice3 gmin stepping",
    "Note: spice3 gmin stepping completed",
    "Note: Go directly to gmin stepping",
    "Note: Starting source stepping",
    "Note: Source stepping completed",
    "Convergence reached. Final circuit time is 1e-06 seconds (iteration n = 3)",
]


@pytest.mark.parametrize("line", RECOVERY_NOTICES)
def test_recovery_notices_are_kept_not_fatal(line):
    assert scan_log(CLEAN_LOG + line + "\n") == [line]


def test_recovery_notices_keep_log_order():
    log = CLEAN_LOG + "\n".join([RECOVERY_NOTICES[0], "Warning: odd", RECOVERY_NOTICES[1]]) + "\n"
    assert scan_log(log) == [RECOVERY_NOTICES[0], "Warning: odd", RECOVERY_NOTICES[1]]


@pytest.mark.parametrize(
    "line",
    [
        "Error: unknown subckt: xdut d g 0 b nfet_05v0_typo",
        "ERROR: could not find '=' on parameter line 'x'!",
        "Warning: singular matrix:  check node y",
        "Warning: Dynamic gmin stepping failed",
        "Warning: True gmin stepping failed",
        "Warning: spice3 gmin stepping failed",
        "Warning: source stepping failed",
        "Too many iterations without convergence",
        "Warning: non-convergence, node d is nan",
        "WARNING: Convergence problems at d (voltage).  ",
        "Convergence not reached. However the most near convergence iteration has predicted",
        "doAnalyses: TRAN:  Timestep too small; time = 1e-9, timestep = 1e-21",
        "Warning: no convergence in DC sweep",
        "doAnalyses: iteration limit reached",
        "run simulation(s) aborted",
    ],
)
def test_fatal_lines_raise_with_log_tail(line):
    log = CLEAN_LOG + line + "\n" + "trailing context line\n"
    with pytest.raises(SpiceError) as exc:
        scan_log(log)
    assert line in str(exc.value)
    assert "trailing context line" in str(exc.value)  # the log tail is in the message
    assert exc.value.log_tail.endswith("trailing context line")


def test_log_tail_is_bounded():
    log = "\n".join(f"line {i}" for i in range(1000)) + "\nError: boom\n"
    with pytest.raises(SpiceError) as exc:
        scan_log(log)
    tail = exc.value.log_tail.splitlines()
    assert len(tail) == ngspice.LOG_TAIL_LINES
    assert tail[-1] == "Error: boom"


# --- result assembly (no simulator) -------------------------------------------------------


def _fake_raw(plan, *, drift=0.0):
    grid = plan.grid()
    n = plan.npoints
    acc = np.cumsum(np.full(n, drift))  # mimics ngspice's accumulated sweep error
    return {
        "v(v-sweep)": grid["vg"] + acc,
        "v(d)": grid["vd"] + acc,
        "v(g)": grid["vg"] + acc,
        "v(b)": grid["vb"],
        "i(vd)": -np.linspace(1e-12, 1e-3, n),
        "i(vg)": np.zeros(n),
        "i(vb)": np.full(n, -0.0),
    }


def test_assemble_dc_signs_and_exact_grid():
    plan = bias_plan(PFET, SW["idvg_sat"])
    res = ngspice.assemble(plan, _fake_raw(plan, drift=1e-14))
    assert list(res) == ["vd", "vg", "vb", "id", "ig", "ib"]
    grid = plan.grid()
    for k in ("vd", "vg", "vb"):
        assert res[k].tobytes() == grid[k].tobytes()  # bit-identical to the devices.py grid
    np.testing.assert_array_equal(res["id"], np.linspace(1e-12, 1e-3, plan.npoints))
    for k in ("ig", "ib"):
        assert not np.any(np.signbit(res[k])), "-0.0 must not reach the CSV"


def test_assemble_rejects_wrong_point_count():
    plan = bias_plan(NFET, SW["idvg_lin"])
    raw = {k: v[:-1] for k, v in _fake_raw(plan).items()}
    with pytest.raises(SpiceError, match="1503"):
        ngspice.assemble(plan, raw)


def test_assemble_rejects_grid_mismatch():
    plan = bias_plan(NFET, SW["idvg_lin"])
    raw = _fake_raw(plan)
    raw["v(b)"] = raw["v(b)"].copy()
    raw["v(b)"][700] += 2e-9
    with pytest.raises(SpiceError, match="vb"):
        ngspice.assemble(plan, raw)


def test_assemble_rejects_missing_vector():
    plan = bias_plan(NFET, SW["idvg_lin"])
    raw = _fake_raw(plan)
    del raw["i(vb)"]
    with pytest.raises(SpiceError, match=r"i\(vb\)"):
        ngspice.assemble(plan, raw)


def test_assemble_cv_and_unfilled_sentinel():
    plan = bias_plan(NFET, SW["cv"])
    vg = plan.grid()["vg"].copy()
    res = ngspice.assemble(plan, {"vg": vg, "cgg": np.full(201, 2e-13)})
    assert list(res) == ["vg", "cgg"]
    vg[50] = 1e30  # a loop iteration that never assigned its point
    with pytest.raises(SpiceError, match="vg"):
        ngspice.assemble(plan, {"vg": vg, "cgg": np.full(201, 2e-13)})


def test_spice_result_is_a_dict_with_warnings():
    r = SpiceResult({"a": np.zeros(1)}, ["Warning: x"])
    assert isinstance(r, dict) and list(r) == ["a"]
    assert r.warnings == ("Warning: x",)
    assert SpiceResult({}).warnings == ()


def test_run_refuses_spiceinit_in_out_dir(tmp_path):
    (tmp_path / ".spiceinit").write_text("set ngbehavior=hsa\n")
    with pytest.raises(SpiceError, match="spiceinit"):
        run_ngspice("* x\n.end\n", tmp_path)


# --- real ngspice runs --------------------------------------------------------------------


def _w10(device, l_um):
    return next(g for g in device.geometries if g.w_um == 10 and g.l_um == l_um)


@pytest.mark.sandbox
def test_idvg_nfet_w10_l0p6_runs(image_pdk, tmp_path):
    sweep = SW["idvg_sat"]
    res = simulate(NFET, _w10(NFET, 0.6), sweep, "typical", 25.0, image_pdk, tmp_path)
    assert list(res) == ["vd", "vg", "vb", "id", "ig", "ib"]
    assert all(v.shape == (501 * 3,) for v in res.values())
    assert res.warnings == ()
    assert (tmp_path / ngspice.LOG_NAME).is_file() and (tmp_path / RAW_NAME).is_file()
    np.testing.assert_array_equal(res["vg"], np.tile(V05, 3))
    np.testing.assert_array_equal(res["vb"], np.repeat([0.0, -1.0, -2.0], 501))
    assert np.all(res["vd"] == 5.0)
    idv = res["id"].reshape(3, 501)
    d_id = np.diff(idv, axis=1)
    # Under reverse Vbs the off-state Id sits on a flat ~6 pA drain-junction leakage floor where
    # ngspice's branch current carries ~7e-15 A of round-off, so allow dips of that size there;
    # above 1 nA it must rise strictly.
    assert np.all(d_id > -1e-13), "Id must not fall with Vgs at Vds = 5"
    assert np.all(d_id[idv[:, 1:] > 1e-9] > 0)
    assert np.all(idv[:, -1] > 1e-3)  # on-state, current into the drain is positive for nfet
    on = idv[:, 100:]  # Vgs >= 1 V (below, junction leakage grows with reverse Vbs)
    assert np.all(on[0] > on[1]) and np.all(on[1] > on[2])  # reverse body bias lowers Id


@pytest.mark.sandbox
@pytest.mark.parametrize("device", [NFET, PFET], ids=lambda d: d.name)
def test_bin_boundary_l0p7(image_pdk, tmp_path, device):
    for sweep in (SW["idvg_lin"], SW["idvg_sat"], SW["idvd"]):
        out = tmp_path / sweep.name
        out.mkdir()
        res = simulate(device, _w10(device, 0.7), sweep, "typical", 25.0, image_pdk, out)
        assert res.warnings == ()
        on = res["id"][np.argmax(np.abs(res["id"]))]
        assert np.sign(on) == device.polarity  # pfet Id is negative in on-state
        assert abs(on) > 1e-4


@pytest.mark.sandbox
@pytest.mark.parametrize("device", [NFET, PFET], ids=lambda d: d.name)
def test_two_runs_byte_identical(image_pdk, tmp_path, device):
    blobs = []
    for run in ("a", "b"):
        out = tmp_path / run
        out.mkdir()
        res = simulate(
            device, device.geometries[0], SW["idvg_sat"], "typical", 25.0, image_pdk, out
        )
        io.write_csv(out / "idvg_sat.csv", res, {"device": device.name, "engine": "ngspice"})
        blobs.append((out / "idvg_sat.csv").read_bytes())
    assert blobs[0] == blobs[1]
    # the raw data (after the header, which carries a Date line) is identical too
    raw = [(tmp_path / r / RAW_NAME).read_bytes() for r in ("a", "b")]
    assert raw[0].split(b"Binary:\n", 1)[1] == raw[1].split(b"Binary:\n", 1)[1]


@pytest.mark.sandbox
def test_failure_on_bad_model(image_pdk, tmp_path):
    typo = Device("nfet_05v0", 1, "nfet_05v0_typo", NFET.geometries)
    with pytest.raises(SpiceError, match="unknown subckt"):
        simulate(typo, typo.geometries[0], SW["idvg_lin"], "typical", 25.0, image_pdk, tmp_path)
    assert not (tmp_path / RAW_NAME).exists()


@pytest.mark.sandbox
def test_singular_matrix_is_error(image_pdk, tmp_path):
    # ngspice recovers from the floating node (exit 0, full point count): only the log tells.
    text = ngspice_netlist(NFET, NFET.geometries[0], SW["idvg_lin"], "typical", 25.0, image_pdk)
    text = text.replace("\n.dc ", "\nc1 x 0 1p\nr1 x y 1k\nc2 y 0 1p\n.dc ", 1)
    with pytest.raises(SpiceError, match="singular matrix"):
        run_ngspice(text, tmp_path, plan=bias_plan(NFET, SW["idvg_lin"]))


@pytest.mark.sandbox
@pytest.mark.parametrize("device", [NFET, PFET], ids=lambda d: d.name)
def test_cv_cgg_positive(image_pdk, tmp_path, device):
    g = _w10(device, 10)
    res = simulate(device, g, SW["cv"], "typical", 25.0, image_pdk, tmp_path)
    assert list(res) == ["vg", "cgg"]
    assert res["vg"].shape == (201,)
    vg = res["vg"] * device.polarity  # signed grid: -5 = accumulation, +5 = inversion
    cox_area = 3.9 * 8.854e-12 / 15.2e-9 * (g.w_um * g.l_um * 1e-12)  # ~2.3e-13 F
    for v in (-5.0, 5.0):
        c = res["cgg"][vg == v][0]
        assert 0.7 * cox_area < c < 1.1 * cox_area, (v, c)
    assert np.all(res["cgg"] > 0)
    assert res["cgg"][vg == 0.0][0] < res["cgg"][vg == 5.0][0]  # depletion dip


@pytest.mark.sandbox
@pytest.mark.parametrize("device", [NFET, PFET], ids=lambda d: d.name)
def test_ioff_single_point(image_pdk, tmp_path, device):
    res = simulate(device, device.geometries[0], SW["ioff"], "typical", 25.0, image_pdk, tmp_path)
    assert all(v.shape == (1,) for v in res.values())
    assert res["vd"][0] == 5.5 * device.polarity and res["vg"][0] == 0.0
    assert 0 < abs(res["id"][0]) < 1e-9


def _max_threads(tmp_path, netlist: str) -> int:
    (tmp_path / "t.cir").write_text(netlist)
    script = (
        "ngspice -b t.cir > t.log 2>&1 & p=$!; m=0; "
        'while kill -0 $p; do n=$(ls /proc/$p/task | wc -l); [ "$n" -gt "$m" ] && m=$n; '
        "sleep 0.02; done; wait $p; echo $m"
    )
    res = sandbox.run(["sh", "-c", script], out_dir=tmp_path, mem="4g", cpus=2)
    return int(res.stdout.split()[-1])


@pytest.mark.sandbox
def test_num_threads_honoured(image_pdk, tmp_path):
    text = ngspice_netlist(NFET, NFET.geometries[0], SW["idvd"], "typical", 25.0, image_pdk)
    assert "set num_threads=1\n" in text
    (tmp_path / "ours").mkdir()
    (tmp_path / "ctrl").mkdir()
    assert _max_threads(tmp_path / "ours", text) == 1
    # control: without the line, the system spinit's num_threads=8 applies (OpenMP BSIM4 loop)
    assert _max_threads(tmp_path / "ctrl", text.replace("set num_threads=1\n", "")) > 1


@pytest.mark.sandbox
def test_stale_raw_is_not_reused(image_pdk, tmp_path):
    simulate(NFET, NFET.geometries[0], SW["ioff"], "typical", 25.0, image_pdk, tmp_path)
    assert (tmp_path / RAW_NAME).is_file()
    # a clean ngspice run that writes no raw file must not pick up the previous run's
    no_write = "* no write\nr1 a 0 1k\nv1 a 0 dc 1\n.control\nop\n.endc\n.end\n"
    with pytest.raises(SpiceError, match="no raw file"):
        run_ngspice(no_write, tmp_path)
