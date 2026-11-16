# SPDX-License-Identifier: Apache-2.0
"""Write the edge-sensitivity record of one cell from its run directories (issue #189).

    uv run --locked python experiments/edge-sensitivity/record.py WORKDIR DEVICE GID OUT.json

WORKDIR is run.py's work directory; each WORKDIR/DEVICE/GID/<variant>/ with a result.json and a
pins.json becomes one entry of the record. Every variant must have the same pins (run.py's
pins.json: the commit, the TCAD image, the plugin commit, the sha256 of variant.py, the 2D writer's
generator_sha256 and the calibration file and values); the record holds them once. Of each run it
keeps only the values a reader needs: the gate biases, Cgg per unit width (fF/um), the node count,
the meshed gate length and the variant's parameters.
"""

import json
import sys
from pathlib import Path

from gf180tcad import io

# The fields of a run's result.json that the record keeps.
KEEP = ("vg", "cgg_ff_per_um", "node_count", "meshed_l_um", "bias_um", "plugs", "plug_um", "ldd")


def record(work: Path, device: str, gid: str) -> dict:
    """The record of ``device``'s cell ``gid`` from the run directories under ``work``."""
    root = Path(work) / device / gid
    variants, pinned = {}, {}
    for run in sorted(p for p in root.iterdir() if (p / "result.json").is_file()):
        d = json.loads((run / "result.json").read_bytes())
        if d["variant"] != run.name:
            raise ValueError(f"{run}: result.json is variant {d['variant']!r}")
        if not (run / "pins.json").is_file():
            raise ValueError(f"{run}: no pins.json (run it with run.py)")
        pinned[run.name] = json.loads((run / "pins.json").read_bytes())
        variants[run.name] = {k: d.get(k) for k in KEEP}
    if "base" not in variants:
        raise ValueError(f"{root}: no base variant")
    first = pinned["base"]
    for name, p in pinned.items():
        if p != first:
            diff = sorted(k for k in {*p, *first} if p.get(k) != first.get(k))
            raise ValueError(f"{root}: {name} ran with other pins than base: {diff}")
    return {
        "schema": 2,
        "device": device,
        "geometry": gid,
        "params": "calibrated",
        **first,
        "variants": variants,
    }


def main(argv: list[str]) -> int:
    work, device, gid, out = argv
    io.write_json(Path(out), record(Path(work).expanduser(), device, gid))
    print(f"wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
