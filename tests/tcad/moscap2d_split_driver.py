# SPDX-License-Identifier: Apache-2.0
"""In-image driver of test_moscap2d.py's split/resume test: one ``moscap-job --dim 2`` step.

``python3 /work/src/tests/tcad/moscap2d_split_driver.py STEP DIR`` runs, in ``/work/out/DIR``,
the 2D job of the nfet Lmin cell (with S/D) on a small case: the start values, a coarse mesh
(``START[2].scaled(2, refine_grading=True)``), 5 QS biases and every 2nd of them for AC. STEP is

- ``both``, ``qs``, ``ac`` or ``combine``: :func:`gf180tcad.tcad.__main__.run_job_2d` with that
  method (the production code path);
- ``qs-interrupt`` / ``ac-interrupt``: that sweep, stopped by an exception after its 2nd point
  (:data:`gf180tcad.tcad.moscap2d.AFTER_POINT`), as a cut-off job would be;
- ``mono``: the QS and AC sweeps in one ``sweep_cv`` call each (no per-point state), written to
  ``mono.json`` for the comparison with the per-point sweeps.
"""

import json
import sys
from pathlib import Path

from gf180tcad.tcad import __main__ as cli
from gf180tcad.tcad import meshconv, moscap2d, process

DEVICE, GID = "nfet_05v0", "w10p0_l0p60"
SPEC = meshconv.START[2].scaled(2.0, refine_grading=True)
VG = (-5.0, -2.5, 0.0, 2.5, 5.0)

meshconv.selected_spec = lambda device, dim: SPEC
cli.meshconv.selected_spec = meshconv.selected_spec
cli.job_vg = lambda proc: VG
moscap2d.AC_STRIDE = 2


class Interrupt(RuntimeError):
    pass


def main(step: str, sub: str) -> None:
    out = Path("/work/out") / sub
    out.mkdir(parents=True, exist_ok=True)
    if step.endswith("-interrupt"):
        seen = []

        def stop(i: int) -> None:
            seen.append(i)
            if len(seen) == 2:
                raise Interrupt(f"interrupted after point {i}")

        moscap2d.AFTER_POINT = stop
        try:
            cli.run_job_2d(DEVICE, "start", GID, out, method=step.split("-")[0])
        except Interrupt as e:
            print(e, flush=True)
            return
        raise RuntimeError("the sweep was not interrupted")
    if step == "mono":
        proc = process.load(DEVICE)
        g = cli.geometry_of(DEVICE, GID)
        res = {}
        for method, vg in (("qs", VG), ("ac", VG[::2])):
            cv = moscap2d.simulate(
                proc, g, vg=vg, with_sd=True, method=method, mesh=SPEC,
                freq_hz=moscap2d.AC_FREQ_HZ if method == "ac" else None,
                mesh_file=out / f"mono_{method}.msh",
            )  # fmt: skip
            res[method] = {
                "cgg": list(cv.cgg_ff_per_um),
                "cgx": {k: list(v) for k, v in cv.cgx.items()},
            }
        (out / "mono.json").write_text(json.dumps(res), encoding="utf-8")
        return
    cli.run_job_2d(DEVICE, "start", GID, out, method=step)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
