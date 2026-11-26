# SPDX-License-Identifier: Apache-2.0
"""The pinned check cases of the method: precision, voltage step, mesh and the 1D diodes.

    uv run --locked python experiments/hv-junction/checks.py cases OUT.json
    uv run --locked python experiments/hv-junction/checks.py diodes WORKDIR
    uv run --locked python experiments/hv-junction/checks.py record WORKDIR OUT.json

``cases`` writes the 2D check cases for batch.py; record.py then writes their record
(results/hv-junction/checks.json). Their names:

  bare-f0.1-x128-v2   the bare N-well edge of cases.base() on the 0.1 um mesh, 128-bit
                      floats, 2 V steps
  bare-f0.1-f64-v2    the same in double precision
  bare-f0.1-f64-v4    4 V steps (the first mesh level)
  bare-f0.1-f64-v5    5 V steps
  bare-f0.05-f64-v4   the 0.05 um mesh
  abut-f0.07          the N-well with the generated P-well abutting (cases.calib3) on the
                      mesh of the abutting prediction cases
  abut-f0.05, abut-f0.02   the same on finer meshes

``diodes`` runs diode1d.py (three abrupt N+/P diodes) in the sandbox and writes
WORKDIR/diode1d.json, its log and pins.json. ``record`` writes the diode record
(results/hv-junction/diodes.json) from them; it refuses a run made from a checkout with
uncommitted changes. WORKDIR is outside the repository.
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys

import cases
import run as runner

BARE_MESH = {
    "f0.1": {"fine": 0.1, "surf": 0.04, "coarse": 0.5},
    "f0.05": {"fine": 0.05, "surf": 0.02, "coarse": 0.5},
}
# name: (mesh, 128-bit floats, voltage step in V)
BARE = {
    "bare-f0.1-x128-v2": ("f0.1", True, 2.0),
    "bare-f0.1-f64-v2": ("f0.1", False, 2.0),
    "bare-f0.1-f64-v4": ("f0.1", False, 4.0),
    "bare-f0.1-f64-v5": ("f0.1", False, 5.0),
    "bare-f0.05-f64-v4": ("f0.05", False, 4.0),
}
# The abutting junction: cases.calib3's section on three meshes; 0.07 is the mesh
# predict.py gives a case with an abutting P-well.
ABUT_MESH = {
    "abut-f0.07": {"fine": 0.07, "surf": 0.03, "coarse": 0.5},
    "abut-f0.05": {"fine": 0.05, "surf": 0.02, "coarse": 0.5},
    "abut-f0.02": {"fine": 0.02, "surf": 0.02, "coarse": 0.5},
}
DIODES = ("1e+15", "1e+16", "1e+17")


def check_cases() -> dict:
    """The 2D check cases, {name: parameters of sweep.py}."""
    out = {}
    for name, (mesh, extended, vstep) in BARE.items():
        p = cases.base()
        p["mesh"] = dict(BARE_MESH[mesh])
        p["extended"] = extended
        p["vstep"] = vstep
        out[name] = p
    abut = cases.calib3()["nw-abut-f0.05"]
    for name, mesh in ABUT_MESH.items():
        p = copy.deepcopy(abut)
        p["mesh"] = dict(mesh)
        out[name] = p
    return out


def diodes(work: pathlib.Path) -> int:
    """Run diode1d.py in the sandbox; pins.json is written when it leaves a result."""
    work = work.expanduser().resolve()
    pins = runner.pins()
    result = work / "diode1d.json"
    result.unlink(missing_ok=True)
    rc = runner.run(work, "diode1d.py", ["diode1d.json"])
    if not result.is_file():
        print(f"FAILED exit {rc}, see {work / 'run.log'}")
        return rc or 1
    if runner.pins(allow_dirty=True) != pins:
        result.unlink()
        print("the checkout changed during the run; result removed")
        return 1
    (work / "pins.json").write_text(json.dumps(pins, indent=1), encoding="utf-8")
    return 0


def diode_record(work: pathlib.Path) -> dict:
    """The diode record from WORKDIR (SystemExit when the run is unpinned or dirty)."""
    work = work.expanduser()
    try:
        res = json.loads((work / "diode1d.json").read_text(encoding="utf-8"))
        pins = json.loads((work / "pins.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"not run ({exc.filename})") from None
    if pins["dirty"]:
        raise SystemExit("run from a checkout with uncommitted changes")
    if sorted(res) != sorted(DIODES):
        raise SystemExit(f"diode1d.json holds {sorted(res)}, not {sorted(DIODES)}")
    return {"schema": 1, "pins": pins, "diodes": res}


def main(argv: list[str]) -> int:
    mode = argv[0]
    if mode == "cases":
        got = check_cases()
        pathlib.Path(argv[1]).write_text(json.dumps(got, indent=1), encoding="utf-8")
        print(f"{len(got)} cases")
        return 0
    if mode == "diodes":
        return diodes(pathlib.Path(argv[1]))
    if mode == "record":
        rec = diode_record(pathlib.Path(argv[1]))
        text = json.dumps(rec, indent=1, sort_keys=True) + "\n"
        pathlib.Path(argv[2]).write_text(text, encoding="utf-8")
        print(f"wrote {argv[2]}")
        return 0
    sys.exit(f"unknown mode {mode}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
