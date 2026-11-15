# SPDX-License-Identifier: Apache-2.0
"""Write the edge-sensitivity record of one cell from its run directories (issue #189).

    uv run --locked python experiments/edge-sensitivity/record.py WORKDIR DEVICE GID OUT.json

WORKDIR is run.py's work directory; each WORKDIR/DEVICE/GID/<variant>/result.json becomes one
entry of the record. The record pins what the runs used: the TCAD image (docker/TCAD_IMAGE), the
plugin commit, the sha256 of variant.py and of the device's calibration file, and that file's
values. Only the values a
reader needs are kept: per variant its gate biases, Cgg per unit width (fF/um), the node count, the
meshed gate length and the variant's parameters.
"""

import hashlib
import json
import sys
from pathlib import Path

from gf180tcad import io
from gf180tcad.tcad import calibration, calibration_file, gplugins_commit

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

# The fields of a run's result.json that the record keeps.
KEEP = ("vg", "cgg_ff_per_um", "node_count", "meshed_l_um", "bias_um", "plugs", "plug_um", "ldd")


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(work: Path, device: str, gid: str) -> dict:
    """The record of ``device``'s cell ``gid`` from the run directories under ``work``."""
    root = Path(work) / device / gid
    variants = {}
    for run in sorted(p for p in root.iterdir() if (p / "result.json").is_file()):
        d = json.loads((run / "result.json").read_bytes())
        if d["variant"] != run.name:
            raise ValueError(f"{run}: result.json is variant {d['variant']!r}")
        variants[run.name] = {k: d.get(k) for k in KEEP}
    if "base" not in variants:
        raise ValueError(f"{root}: no base variant")
    return {
        "schema": 1,
        "device": device,
        "geometry": gid,
        "params": "calibrated",
        "image": (REPO / "docker" / "TCAD_IMAGE").read_text(encoding="utf-8").strip(),
        "gplugins_commit": gplugins_commit(),
        "variant_py_sha256": _sha256(HERE / "variant.py"),
        "calibration_file_sha256": _sha256(calibration_file(device)),
        "calibration_values": calibration.read(calibration_file(device), device),
        "variants": variants,
    }


def main(argv: list[str]) -> int:
    work, device, gid, out = argv
    io.write_json(Path(out), record(Path(work).expanduser(), device, gid))
    print(f"wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
