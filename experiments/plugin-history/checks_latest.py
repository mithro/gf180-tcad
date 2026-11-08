# SPDX-License-Identifier: Apache-2.0
"""Check driver for the plugin on the latest stack: the PN slab of the v0.8.0 record, solved by
the gplugins fork at the submodule pin in the stable TCAD image (issue #162).

Runs in the sandbox with no network, in the stable TCAD image's own venv, where ``gplugins``
imports from the submodule (``/work/src/third_party/gplugins``). It calls the fork's own PN-slab
solve, ``_solve`` of ``gplugins/devsim/tests/test_mesh.py``, with the ported topology: every
meshwell interface, the rib-slab one included, is a DEVSIM interface. That solve builds the same
PN slab as the v0.8.0 record (``straight_pn(length=10)`` trimmed, the same contacts,
``resolutions`` times ``--mesh-scale``), solves it at equilibrium and ramps the cathode to 0.1
and 0.2 V. It records the anode − cathode contact potential, the contact currents and the
junction probe at each step.

Usage: ``python checks_latest.py --mesh-scale R --out RAW.json``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness

#: The gplugins source in the stable TCAD image: the submodule, mounted read-only.
GPLUGINS_ROOT = Path("/work/src/third_party/gplugins")


def solve(mesh_scale: float, workdir: Path) -> dict:
    """The fork's PN-slab solve with the ported topology."""
    from gplugins.devsim.tests import test_mesh

    return test_mesh._solve(workdir, mesh_scale, v080_topology=False)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh-scale", type=float, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    result = {
        "mesh_scale": args.mesh_scale,
        "pn_slab": solve(args.mesh_scale, Path.cwd() / "pn_slab"),
        "versions": harness.versions(GPLUGINS_ROOT),
    }
    harness.write(args.out, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
