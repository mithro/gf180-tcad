# SPDX-License-Identifier: Apache-2.0
"""In-image driver of tests/tcad/test_moscap2d.py: runs one case, writes <case>.json.

Run inside the TCAD image (``python3 /work/src/tests/tcad/moscap2d_driver.py CASE``) by the
sandbox-marked fixture of test_moscap2d.py, one sandbox job per case so that they run in
parallel; the tests assert on the numbers. The 1D references are computed here too, so 2D and
1D are compared within one image. Every 2D case uses the device's committed selected 2D mesh
(results/tcad/meshconv/moscap2d/<device>/selected.json).
"""

import json
import sys
from pathlib import Path

from gf180tcad.tcad import analytic, meshconv, moscap1d, moscap2d, process, stack

OUT = Path("/work/out")
# A coarse grid of the cv sweep (every 10th point, 0.5 V apart), in the SPICE order.
VG21 = tuple(round(-5 + 0.5 * i, 10) for i in range(21))
# The AC biases: accumulation, depletion, inversion (true sign comes from the polarity).
VG_AC = (-5.0, -2.0, 0.0, 1.0, 2.0, 5.0)
# The uniform (2D = 1D) structure's length (um): the result does not depend on it (Neumann
# sides); 1 um keeps the mesh small.
UNIFORM_L_UM = 1.0
SD_PEAKS = (5e19, 1e20, 2e20)


def _pol(proc) -> float:
    return 1.0 if proc.polarity == "n" else -1.0


def _cox(proc) -> float:
    v = proc.values()
    return analytic.f_per_cm2_to_ff_per_um2(analytic.cox_f_per_cm2(v["t_ox_eff_nm"], v["epsrox"]))


def _curve(cv) -> dict:
    return {
        "c_per_area": list(cv.c_per_area_ff_um2),
        "cgg_per_um": list(cv.cgg_ff_per_um),
        "cgx": {k: list(v) for k, v in cv.cgx.items()},
        "meshed_l_um": cv.meshed_l_um,
        "meshed_t_ox_nm": cv.meshed_t_ox_nm,
        "node_count": cv.node_count,
        "rel_error": [p.rel_error for p in cv.points],
        "vg": list(cv.vg),
    }


def case_uniform(device: str) -> dict:
    """The 1D stack extruded (gate over the whole domain, no S/D, Neumann sides) vs 1D."""
    proc = process.load(device)
    vg = tuple(_pol(proc) * v + 0.0 for v in VG21)
    mesh = meshconv.selected_spec(device, 2)
    cv2 = moscap2d.simulate(
        proc, None, vg=vg, with_sd=False, method="qs", mesh=mesh,
        structure=stack.uniform(proc, UNIFORM_L_UM), mesh_file=OUT / "uniform.msh",
    )  # fmt: skip
    cv1 = moscap1d.simulate(proc, vg=vg, mesh=meshconv.selected_spec(device, 1))
    return {"cox": _cox(proc), "c1d": list(cv1.c_per_area_ff_um2), **_curve(cv2)}


def case_nosd(device: str) -> dict:
    """The PDK cell at the meshconv geometry without S/D, at |vg| = 5 V: with and without the
    background dielectric (the gate's fringe path to the silicon outside the gate)."""
    proc = process.load(device)
    g = meshconv.geometry_2d(device)
    mesh = meshconv.selected_spec(device, 2)
    out = {"cox": _cox(proc)}
    for background in (True, False):
        xs = stack.build(proc, stack.cell(device, g), with_sd=False, background=background)
        cv = moscap2d.simulate(
            proc, g, vg=(-5.0, 5.0), with_sd=False, method="qs", mesh=mesh, structure=xs,
            mesh_file=OUT / f"nosd_{background}.msh",
        )  # fmt: skip
        out["background" if background else "neumann"] = _curve(cv)
    return out


def case_ac(device: str) -> dict:
    """The PDK cell with S/D: 1 MHz AC (Cgg, every Cxg) and QS at the same biases."""
    proc = process.load(device)
    g = meshconv.geometry_2d(device)
    mesh = meshconv.selected_spec(device, 2)
    vg = tuple(_pol(proc) * v + 0.0 for v in VG_AC)
    ac = moscap2d.simulate(
        proc, g, vg=vg, with_sd=True, method="ac", mesh=mesh, freq_hz=1e6,
        mesh_file=OUT / "ac.msh",
    )  # fmt: skip
    qs = moscap2d.simulate(
        proc, g, vg=vg, with_sd=True, method="qs", mesh=mesh, mesh_file=OUT / "qs.msh"
    )
    xs = stack.build(proc, stack.cell(device, g), with_sd=True)
    return {
        "ac": _curve(ac),
        "qs": _curve(qs),
        "contacts": sorted(xs.contacts),
        "non_gate": sorted(c for c in xs.contacts if c != stack.GATE),
        "polarity": proc.polarity,
    }


def case_sd(l_um: float) -> dict:
    """pfet Cgg for three source/drain peaks at W = 10 um and gate length ``l_um``."""
    from gf180tcad.devices import Geometry

    proc = process.load("pfet_05v0")
    g = Geometry(10.0, l_um, "calibration")
    mesh = meshconv.selected_spec("pfet_05v0", 2)
    vg = tuple(-v + 0.0 for v in VG21)
    out = {}
    for peak in SD_PEAKS:
        xs = stack.build(proc, stack.cell("pfet_05v0", g), with_sd=True, sd_peak_cm3=peak)
        cv = moscap2d.simulate(
            proc, g, vg=vg, with_sd=True, method="qs", mesh=mesh, structure=xs,
            mesh_file=OUT / f"sd_{peak!r}.msh",
        )  # fmt: skip
        out[repr(peak)] = {**_curve(cv), "straggle_um": xs.sd_straggle_um}
    return out


def _without(component, layer):
    """A flat copy of ``component`` without the polygons on ``layer``."""
    import gdsfactory as gf

    c = gf.Component()
    for lay in component.layers:
        if tuple(lay) == tuple(layer):
            continue
        for pts in component.get_polygons_points(layers=[lay]).values():
            for p in pts:
                c.add_polygon([tuple(xy) for xy in p], layer=lay)
    return c


def case_dualgate() -> dict:
    """stack.build accepts the cells and refuses them without Dualgate."""
    out = {}
    for device in process.DEVICES:
        proc = process.load(device)
        g = meshconv.geometry_2d(device)
        cell = stack.cell(device, g)
        xs = stack.build(proc, cell, with_sd=True)
        try:
            stack.build(proc, _without(cell, stack.DUALGATE), with_sd=True)
            refused = None
        except stack.DualgateMissing as e:
            refused = str(e)
        out[device] = {
            "l_um": xs.l_um,
            "w_um": xs.w_um,
            "gate_u": list(xs.gate_u),
            "length_um": xs.length_um,
            "contacts": sorted(xs.contacts),
            "refused": refused,
        }
    return out


CASES = {
    **{f"uniform_{d}": (lambda d=d: case_uniform(d)) for d in process.DEVICES},
    **{f"nosd_{d}": (lambda d=d: case_nosd(d)) for d in process.DEVICES},
    **{f"ac_{d}": (lambda d=d: case_ac(d)) for d in process.DEVICES},
    "sd_pfet_05v0_lmin": lambda: case_sd(0.5),
    "sd_pfet_05v0_l2": lambda: case_sd(2.0),
    "dualgate": case_dualgate,
}


def main(case: str) -> None:
    data = CASES[case]()
    (OUT / f"{case}.json").write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
