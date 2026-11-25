# SPDX-License-Identifier: Apache-2.0
"""In-image driver of tests/charon/test_charon_moscap.py: runs Charon, DEVSIM and the exact
reference on the same 1D stacks and writes driver.json.

Run inside the Charon image (``python3 /work/src/tests/charon/charon_driver.py``) by the
sandbox-marked fixture of test_charon_moscap.py, which asserts on the numbers. Both devices at
their start values on ``MeshSpec.DEFAULT_1D``, at 0.25 V steps from -5 V to +5 V; the nfet runs
twice so the test can compare the two result files byte for byte.
"""

import hashlib
import json
from pathlib import Path

from gf180tcad.charon import moscap as charon_moscap
from gf180tcad.tcad import analytic, moscap1d, process
from gf180tcad.tcad.mesh import MeshSpec

OUT = Path("/work/out")
MESH = MeshSpec.DEFAULT_1D
VG = tuple(round(-5 + 0.25 * i, 10) for i in range(41))


def stacks() -> dict:
    """Per device and params: the Charon description's node count, spacings, constants and
    node hash, as the job builds it; and the nfet calibrated strip, written to strip.exo."""
    from gf180tcad.tcad import meshconv
    from gf180tcad.tcad.__main__ import load_params

    names = ("eps0_f_per_cm", "eps_si", "eps_ox", "k_b_j_per_k", "mu_n_cm2_per_vs",
             "mu_p_cm2_per_vs", "n_i300_cm3", "n_i_cm3", "q_c", "t_k", "tau_n_s", "tau_p_s",
             "vt_v")  # fmt: skip
    out = {}
    for device in process.DEVICES:
        for params in ("start", "calibrated"):
            proc, _ = load_params(device, params)
            desc = charon_moscap.stack_1d(
                moscap1d.stack_of(proc), meshconv.selected_spec(device, 1)
            )
            xs, _ = desc.node_positions_um()
            out[f"{device}/{params}"] = {
                "node_count": len(xs),
                "spacing": {k: list(v) for k, v in desc.mesh.spacing_um.items()},
                "constants": {k: getattr(desc.constants, k) for k in names},
                "nodes_sha256": charon_moscap.nodes_sha256(desc),
            }
            if (device, params) == ("nfet_05v0", "calibrated"):
                from gplugins.devsim.backends.charon import exodus

                mesh = exodus.strip_of(desc)
                exodus.write_exodus(mesh, OUT / "strip.exo")
                out["strip_xy_um"] = mesh.xy_um.tolist()
                out["strip_blocks"] = [len(b.connectivity) for b in mesh.blocks]
    return out


def main() -> None:
    out = {"vg": list(VG), "stacks": stacks()}
    for device in process.DEVICES:
        proc = process.load(device)
        stack = moscap1d.stack_of(proc)
        pol = 1.0 if proc.polarity == "n" else -1.0
        vg = tuple(pol * v + 0.0 for v in VG)
        cv = charon_moscap.simulate(proc, vg=vg, mesh=MESH, workdir=OUT / f"run_{device}")
        dev = moscap1d.simulate(proc, vg=vg, mesh=MESH)
        dv_fb = proc.values()["dv_fb_v"]
        exact = analytic.lf_cv_uniform(
            stack.body_net_cm3, stack.t_ox_nm, stack.gate_net_cm3, [v - dv_fb for v in vg],
            eps_ox=stack.eps_ox,
        )  # fmt: skip
        job = OUT / f"job_{device}"
        job.mkdir(parents=True, exist_ok=True)
        charon_moscap.write(cv, job, proc=proc, params="start", mesh_source="test",
                            image="test")  # fmt: skip
        out[device] = {
            "vg": list(vg),
            "charon": list(cv.c_per_area_ff_um2),
            "devsim": list(dev.c_per_area_ff_um2),
            "exact": list(exact),
            "iterations": [p.iterations for p in cv.points],
            "csv_sha256": hashlib.sha256((job / moscap1d.PER_AREA_CSV).read_bytes()).hexdigest(),
        }
    proc = process.load("nfet_05v0")
    pol_vg = VG
    cv = charon_moscap.simulate(proc, vg=pol_vg, mesh=MESH, workdir=OUT / "run_again")
    job = OUT / "job_again"
    job.mkdir(parents=True, exist_ok=True)
    charon_moscap.write(cv, job, proc=proc, params="start", mesh_source="test", image="test")
    out["nfet_again_csv_sha256"] = hashlib.sha256(
        (job / moscap1d.PER_AREA_CSV).read_bytes()
    ).hexdigest()
    (OUT / "driver.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
