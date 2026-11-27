# SPDX-License-Identifier: Apache-2.0
"""One refinement level of the 2D mesh-convergence check at the fitted poly length bias.

Runs inside the sandbox (tools/sandbox-run, the stable TCAD image), from run.py:

    python3 /work/src/experiments/meshconv-fitted/level.py DEVICE LEVEL OUT_DIR

It solves the committed study's cell (:data:`gf180tcad.tcad.meshconv.GEOMETRY_2D`, the Lmin cell
with its source and drain) with the calibrated values and the committed fit of
:mod:`gf180tcad.tcad.edgefit`, the process every calibrated 2D cell uses (plan Task E3,
Decision 5). The mesh is level LEVEL of the committed study: the start spec scaled by
``meshconv.levels(2)[LEVEL]``, the grading scaled too. The QS sweep runs on the SPICE ``cv``
biases and is saved point by point in OUT_DIR/state_qs, so a cut-off job resumes there when it
runs again. OUT_DIR/level.json gets the curve.
"""

import sys
import time
from pathlib import Path

from gf180tcad import io
from gf180tcad.tcad import meshconv, moscap2d
from gf180tcad.tcad.__main__ import job_vg, load_params_2d

LEVEL_NAME = "level.json"
STATE_NAME = "state_qs"
PROGRESS_NAME = "progress.log"


def main(argv: list[str]) -> int:
    device, level, out = argv[0], int(argv[1]), Path(argv[2])
    meshconv.check_level(2, level)
    proc, calibration_sha256, edge_fit = load_params_2d(device, "calibrated")
    if edge_fit is None:
        raise SystemExit(f"{device}: no committed poly length bias fit (results/tcad/edgefit)")
    scale = meshconv.levels(2)[level]
    spec = meshconv.START[2].scaled(scale, refine_grading=meshconv.REFINE_GRADING[2])
    progress = out / PROGRESS_NAME

    def log(line: str) -> None:
        text = f"{device}/level{level}: {line}"
        with progress.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
        print(text, flush=True)

    t0 = time.monotonic()
    cv = moscap2d.simulate(
        proc,
        meshconv.geometry_2d(device),
        vg=job_vg(proc),
        with_sd=True,
        method="qs",
        mesh=spec,
        mesh_file=out / "mesh.msh",
        log=log,
        state_dir=out / STATE_NAME,
    )
    io.write_json(
        out / LEVEL_NAME,
        {
            "c_per_area_ff_um2": list(cv.c_per_area_ff_um2),
            "cgg_ff_per_um": list(cv.cgg_ff_per_um),
            "calibration_sha256": calibration_sha256,
            "edge_fit": edge_fit,
            "extended_fallback": list(cv.extended_fallback),
            "roundoff_accepted": [dict(r) for r in cv.roundoff_accepted],
            "meshed_l_um": cv.meshed_l_um,
            "node_count": cv.node_count,
            "resumed": moscap2d.resume_count(out / STATE_NAME),
            "scale": scale,
            "spec": spec.as_dict(),
            "vg": list(cv.vg),
        },
    )
    log(f"{cv.node_count} nodes, {len(cv.vg)} points, {time.monotonic() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
