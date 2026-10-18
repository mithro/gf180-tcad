# SPDX-License-Identifier: Apache-2.0
"""In-image driver of tests/tcad/test_moscap1d.py: runs the TCAD sweeps, writes driver.json.

Run inside the TCAD image (``python3 /work/src/tests/tcad/moscap1d_driver.py``) by the
sandbox-marked fixture of test_moscap1d.py, which asserts on the numbers. The exact reference
(:mod:`gf180tcad.tcad.analytic`) is evaluated here too, so TCAD and reference are compared
within one image.
"""

import json
import math
from pathlib import Path

from gf180tcad.tcad import analytic, moscap1d, process
from gf180tcad.tcad.mesh import MeshSpec

OUT = Path("/work/out/driver.json")
MESH = MeshSpec.DEFAULT_1D
MIRROR_VG = tuple(round(-5 + 0.25 * i, 10) for i in range(41))
SHIFT_VG = (-3.0, -1.0, -0.2, 0.3, 0.8, 2.0)


def curve(stack, vg):
    res = moscap1d.sweep_stack(stack, vg, mesh=MESH, name="driver")
    return [analytic.f_per_cm2_to_ff_per_um2(c) for c in res.cgg]


def main() -> None:
    out = {}
    for device in process.DEVICES:
        proc = process.load(device)
        stack = moscap1d.stack_of(proc)
        cv = moscap1d.simulate(proc, vg=process.CV_VG, mesh=MESH)
        ref = analytic.lf_cv_uniform(
            stack.body_net_cm3, stack.t_ox_nm, stack.gate_net_cm3, cv.vg, eps_ox=stack.eps_ox
        )
        cap = analytic.moscap(
            stack.body_net_cm3, stack.t_ox_nm, stack.gate_net_cm3, eps_ox=stack.eps_ox
        )
        vfb = cap.vfb_v
        (c_fb,) = curve(stack, [vfb])
        e = analytic.CONSTANTS.eps_si * analytic.CONSTANTS.eps0_f_per_cm
        series_fb = analytic.f_per_cm2_to_ff_per_um2(
            analytic.series(
                cap.cox_f_per_cm2, e / cap.body.debye_length_cm, e / cap.gate.debye_length_cm
            )
        )
        shifted = moscap1d.simulate(proc.with_values({"dv_fb_v": 0.1}), vg=SHIFT_VG, mesh=MESH)
        unshifted = moscap1d.simulate(proc, vg=[v - 0.1 for v in SHIFT_VG], mesh=MESH)
        out[device] = {
            "vg": list(cv.vg),
            "tcad": list(cv.c_per_area_ff_um2),
            "exact": list(ref),
            "rel_error": [p.rel_error for p in cv.points],
            "converged": [p.converged for p in cv.points],
            "cox": analytic.f_per_cm2_to_ff_per_um2(cap.cox_f_per_cm2),
            "vfb": vfb,
            "c_fb_tcad": c_fb,
            "c_fb_series": series_fb,
            "shifted": list(shifted.c_per_area_ff_um2),
            "unshifted": list(unshifted.c_per_area_ff_um2),
        }
    # mirror: A = p-body N with an n+ gate, B = n-body N with a p+ gate (same |N|, NGATE, t_ox)
    nf = moscap1d.stack_of(process.load("nfet_05v0"))
    a = moscap1d.Stack("n", nf.n_ch_cm3, nf.ngate_cm3, nf.t_ox_nm, nf.eps_ox)
    b = moscap1d.Stack("p", nf.n_ch_cm3, nf.ngate_cm3, nf.t_ox_nm, nf.eps_ox)
    out["mirror"] = {
        "vg": list(MIRROR_VG),
        "a_at_minus_vg": curve(a, [-v for v in MIRROR_VG]),
        "b": curve(b, list(MIRROR_VG)),
    }
    assert all(math.isfinite(x) for d in process.DEVICES for x in out[d]["tcad"])
    OUT.write_text(json.dumps(out, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
