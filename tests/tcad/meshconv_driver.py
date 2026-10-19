# SPDX-License-Identifier: Apache-2.0
"""In-image driver of tests/tcad/test_meshconv.py::test_converges_to_exact: writes driver.json.

Run inside the TCAD image (``python3 /work/src/tests/tcad/meshconv_driver.py``). It runs
:func:`gf180tcad.tcad.meshconv.converge` on the uniformly doped nfet stack from
:attr:`MeshSpec.DEFAULT_1D` (the production start) on a coarser bias grid, and evaluates the
exact Poisson-Boltzmann reference (:mod:`gf180tcad.tcad.analytic`) in the same image.
"""

import json
from pathlib import Path

from gf180tcad.tcad import analytic, meshconv, moscap1d, process
from gf180tcad.tcad.mesh import MeshSpec

OUT = Path("/work/out/driver.json")
VG = tuple(round(-5 + 0.5 * i, 10) for i in range(21))


def main() -> None:
    proc = process.load("nfet_05v0")
    stack = moscap1d.stack_of(proc)
    rep = meshconv.converge(
        lambda spec: moscap1d.simulate(proc, vg=VG, mesh=spec), MeshSpec.DEFAULT_1D
    )
    exact = analytic.lf_cv_uniform(
        stack.body_net_cm3, stack.t_ox_nm, stack.gate_net_cm3, VG, eps_ox=stack.eps_ox
    )
    out = {"report": meshconv.report_dict(rep, device=proc.device, dim=1, settings={}),
           "exact": list(exact)}  # fmt: skip
    OUT.write_text(json.dumps(out, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
