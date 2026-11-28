# SPDX-License-Identifier: Apache-2.0
"""The 2D-equals-1D check of one refinement level, at the calibrated values (the second criterion
of the 2D mesh selection, :data:`gf180tcad.tcad.meshconv.AGREEMENT_1D`).

Runs inside the sandbox (tools/sandbox-run, the stable TCAD image), from run.py:

    python3 /work/src/experiments/meshconv-fitted/agreement.py DEVICE LEVEL OUT_DIR

It is :func:`gf180tcad.tcad.meshconv.agreement_1d` with the calibrated values in place of the
start values: the uniform stack (the 1D stack extruded, a gate over the whole domain, no source
or drain) on level LEVEL of the committed study, against the 1D C-V of the same values on the
selected 1D mesh, QS on every ``AGREEMENT_STRIDE``-th bias of the cv grid. The uniform stack has
no gate end, so the poly length bias does not enter it; the calibrated oxide thickness, body
doping and flat-band shift do. OUT_DIR/agreement.json gets the result.
"""

import sys
from pathlib import Path

from gf180tcad import io
from gf180tcad.tcad import meshconv, moscap1d, moscap2d, process, stack
from gf180tcad.tcad.__main__ import load_params

AGREEMENT_NAME = "agreement.json"


def main(argv: list[str]) -> int:
    device, level, out = argv[0], int(argv[1]), Path(argv[2])
    meshconv.check_level(2, level)
    proc, calibration_sha256 = load_params(device, "calibrated")
    scale = meshconv.levels(2)[level]
    spec = meshconv.START[2].scaled(scale, refine_grading=meshconv.REFINE_GRADING[2])
    pol = 1.0 if proc.polarity == "n" else -1.0
    vg = tuple(pol * v + 0.0 for v in process.CV_VG[:: meshconv.AGREEMENT_STRIDE])
    cv2 = moscap2d.simulate(
        proc, None, vg=vg, with_sd=False, method="qs", mesh=spec,
        structure=stack.uniform(proc, meshconv.AGREEMENT_L_UM), mesh_file=out / "uniform.msh",
        log=lambda line: print(f"{device}/agreement{level}: {line}", flush=True),
    )  # fmt: skip
    cv1 = moscap1d.simulate(proc, vg=vg, mesh=meshconv.selected_spec(device, 1))
    rel = [a / b - 1 for a, b in zip(cv2.c_per_area_ff_um2, cv1.c_per_area_ff_um2, strict=True)]
    io.write_json(
        out / AGREEMENT_NAME,
        {
            "c1d": list(cv1.c_per_area_ff_um2),
            "c2d": list(cv2.c_per_area_ff_um2),
            "calibration_sha256": calibration_sha256,
            "max": max(abs(r) for r in rel),
            "node_count": cv2.node_count,
            "rel": rel,
            "roundoff_accepted": [dict(r) for r in cv2.roundoff_accepted],
            "scale": scale,
            "spec": spec.as_dict(),
            "vg": list(vg),
        },
    )
    print(f"{device}/agreement{level}: max {max(abs(r) for r in rel)!r}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
