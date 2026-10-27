# SPDX-License-Identifier: Apache-2.0
"""The closed formula table of :mod:`gf180tcad.derive`, each formula against a hand value."""

import ast
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from gf180tcad import derive

ROOT = Path(__file__).resolve().parents[1]
MOSCAP1D = ROOT / "results" / "tcad" / "moscap1d"


def test_table_is_closed_and_documented():
    assert set(derive.FORMULAS) == {
        "area_scale",
        "band_edge_ec",
        "band_edge_ev",
        "boltzmann_n",
        "boltzmann_p",
        "depletion_edge",
        "envelope_minmax",
        "gate_fermi_level",
        "intrinsic_level",
        "log10_abs",
        "midgap_offset",
        "oxide_band_edge_ec",
        "oxide_band_edge_ev",
        "oxide_capacitance",
        "region_boundaries",
        "sheet_charge",
    }
    for name, f in derive.FORMULAS.items():
        assert f.name == name
        assert f.equation and f.reference, name
        doc = " ".join((f.fn.__doc__ or "").split())
        assert f.equation in doc, name
        # The rendered API page shows the docstring, so the reference must be in it too.
        assert f"Reference: {f.reference}." in doc, name
        assert f.inputs, name


def test_evaluate_refuses_unknown_formula_and_wrong_arity():
    with pytest.raises(KeyError, match="no formula"):
        derive.evaluate("band_gap_from_nothing", [])
    with pytest.raises(ValueError, match="takes 2 inputs"):
        derive.evaluate("band_edge_ec", [0.3])


def test_band_edges_hand_value():
    # psi = 0.3 V: E_i = -0.3 eV; E_c = -0.3 + 1.12/2 = 0.26 eV; E_v = -0.3 - 0.56 = -0.86 eV.
    assert derive.intrinsic_level(0.3) == pytest.approx(-0.3, abs=1e-15)
    assert derive.band_edge_ec(0.3, 1.12) == pytest.approx(0.26, abs=1e-15)
    assert derive.band_edge_ev(0.3, 1.12) == pytest.approx(-0.86, abs=1e-15)
    assert derive.evaluate("band_edge_ec", [0.3, 1.12]) == pytest.approx(0.26, abs=1e-15)


def test_boltzmann_densities_hand_value():
    # n_i = 1e10, V_t = 0.025 V, psi - phi = 0.1 V: n = 1e10 e^4 = 5.4598150033e11 and
    # p = 1e10 e^-4 = 1.8315638889e8 (cm^-3); n p = n_i^2.
    n = derive.boltzmann_n(0.1, 0.0, 1e10, 0.025)
    p = derive.boltzmann_p(0.1, 0.0, 1e10, 0.025)
    assert n == pytest.approx(5.4598150033e11, rel=1e-10)
    assert p == pytest.approx(1.8315638889e8, rel=1e-10)
    assert n * p == pytest.approx(1e20, rel=1e-12)
    arr = derive.boltzmann_n(np.array([0.0, 0.1]), 0.0, 1e10, 0.025)
    assert arr == pytest.approx([1e10, 5.4598150033e11], rel=1e-10)


def test_oxide_band_edges_follow_psi_per_node():
    # Each oxide node has its own psi, so the edges slope with the oxide field.
    psi = np.array([0.5, 0.3, 0.1])
    ec = derive.oxide_band_edge_ec(psi, 1.12, 3.2)
    ev = derive.oxide_band_edge_ev(psi, 1.12, 4.7)
    assert ec == pytest.approx([3.26, 3.46, 3.66], abs=1e-12)
    assert ev == pytest.approx([-5.76, -5.56, -5.36], abs=1e-12)
    assert np.all(np.diff(ec) > 0)


def test_gate_fermi_level_and_midgap_offset():
    assert derive.gate_fermi_level(1.5) == -1.5
    # (kT/2) ln(Nv/Nc) with V_t = 0.025852 V, Nc = 2.8e19, Nv = 2.65e19:
    # 0.012926 * ln(0.94643) = 0.012926 * -0.0550588 = -7.1169e-4 eV.
    assert derive.midgap_offset(0.025852, 2.8e19, 2.65e19) == pytest.approx(-7.1169e-4, rel=1e-4)


def test_depletion_edge_on_step_profile():
    # Majority density 0 for x < 0.25 um, 1e17 beyond; half the body doping (5e16) is crossed
    # halfway between 0.2 and 0.3 um.
    x = np.array([0.0, 0.1, 0.2, 0.3, 0.4])
    maj = np.array([0.0, 0.0, 0.0, 1e17, 1e17])
    assert derive.depletion_edge(x, maj, 1e17) == pytest.approx(0.25, abs=1e-15)
    # No depletion: the surface node already holds the majority density.
    assert derive.depletion_edge(x, np.full(5, 1e17), 1e17) == 0.0
    with pytest.raises(ValueError, match="never reaches"):
        derive.depletion_edge(x, np.zeros(5), 1e17)


def test_sheet_charge_trapezoid():
    # q (p - n + N) = q * 1e16 cm^-3 over 2 um = 2e-4 cm: 2e12 cm^-2 * q = 3.204353268e-7 C/cm^2.
    q = 1.602176634e-19
    x = np.array([0.0, 1.0, 2.0])
    flat = derive.sheet_charge(x, np.full(3, 1e16), np.zeros(3), np.zeros(3), q)
    assert flat == pytest.approx(3.204353268e-7, rel=1e-12)
    # A triangle of peak 2e16 has the same area.
    tri = derive.sheet_charge(x, np.array([0.0, 2e16, 0.0]), np.zeros(3), np.zeros(3), q)
    assert tri == pytest.approx(flat, rel=1e-12)
    # Electrons count negative, net doping positive (donors).
    neg = derive.sheet_charge(x, np.zeros(3), np.full(3, 1e16), np.zeros(3), q)
    assert neg == pytest.approx(-flat, rel=1e-12)


def test_log10_abs_signed():
    got = derive.log10_abs(np.array([-1e17, 0.0, 1e15, 0.5, -3.0]))
    assert got == pytest.approx([-17.0, 0.0, 15.0, 0.0, -math.log10(3.0)], abs=1e-12)


def test_envelope_minmax_and_area_scale():
    curves = np.array([[1.0, 5.0], [3.0, 2.0], [2.0, 4.0]])
    assert derive.envelope_minmax(curves).tolist() == [[1.0, 2.0], [3.0, 5.0]]
    assert derive.area_scale(2.0, 10.0) == 20.0


def test_oxide_capacitance_hand_value():
    # 3.9 * 8.8541878128e-14 F/cm / 16.4e-7 cm = 2.1055690530e-7 F/cm^2 = 2.1055690530 fF/um^2.
    got = derive.oxide_capacitance(3.9, 8.8541878128e-14, 16.4)
    assert got == pytest.approx(2.1055690530, rel=1e-10)


def _per_area(device: str):
    path = MOSCAP1D / device / "calibrated" / "per_area.csv"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    head = lines[0].split(",")
    rows = [[float(v) for v in ln.split(",")] for ln in lines[1:]]
    cols = {h: np.array([r[i] for r in rows]) for i, h in enumerate(head)}
    return cols["vg"], cols["c_per_area"]


@pytest.mark.parametrize("device,polarity", [("nfet_05v0", "n"), ("pfet_05v0", "p")])
def test_region_boundaries_match_calibrate(device, polarity):
    """derive reimplements the calibration's region rule; this pins it to calibrate.cv."""
    from gf180tcad.calibrate import cv

    vg, c = _per_area(device)
    sign = 1 if polarity == "n" else -1
    order = np.argsort(sign * vg)
    u, cu = (sign * vg)[order].tolist(), c[order].tolist()
    r = cv.regions(u, cu)
    got = derive.region_boundaries(vg, c, polarity)
    want = [
        r.u_fb - cv.PLATEAU_OFFSET_V,
        r.u_fb,
        r.u_dep,
        r.u_min,
        r.u_inv,
        r.u_t,
        r.u_t + cv.PLATEAU_OFFSET_V,
    ]
    assert got.tolist() == [sign * w for w in want]
    assert derive.FB_FRACTION == cv.FB_FRACTION
    assert derive.PLATEAU_OFFSET_V == cv.PLATEAU_OFFSET_V
    assert derive.U_END_V == cv.U_END_V


def _imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"{path}: relative import"
            out.add(node.module.split(".")[0])
    return out


@pytest.mark.parametrize("module", ["derive.py", "quantity.py"])
def test_no_solver_imports(module):
    """derive and quantity import only numpy and the standard library: no solver, no bpy."""
    mods = _imports(ROOT / "src" / "gf180tcad" / module)
    assert mods - {"numpy"} <= set(sys.stdlib_module_names), mods
