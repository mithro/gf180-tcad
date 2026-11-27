# SPDX-License-Identifier: Apache-2.0
"""Write the record of one device's 2D mesh-convergence check at the fitted poly length bias.

    uv run --locked python experiments/meshconv-fitted/record.py WORKDIR DEVICE OUT.json

WORKDIR is run.py's work directory. Every level of the committed 2D study
(:func:`gf180tcad.tcad.meshconv.levels`) must have a level.json and a pins.json under
WORKDIR/DEVICE/level<i>/, and every level must have the same pins; the record holds them once.

The record holds the report of :func:`gf180tcad.tcad.meshconv.converge` over the levels (the
relative change of each level against the next finer one, the observed order and the
Richardson extrapolation), without the second criterion of the committed study (the uniform
stack's agreement with 1D: that stack has no gate end, so the poly length bias does not enter
it). ``check`` holds the plan's question (Task E3, Decision 5): the level the committed study
selected, its largest change against the next finer level at the fitted bias, and whether that
is below :data:`gf180tcad.tcad.meshconv.CRITERION`. ``cell`` compares that level's curve with
the committed calibrated cell of the same geometry, which ran on the same mesh.
"""

import json
import sys
from pathlib import Path

from gf180tcad import io
from gf180tcad.devices import geometry_id
from gf180tcad.tcad import meshconv, moscap1d, moscap2d

SCHEMA = 1


class _Curve:
    def __init__(self, d: dict) -> None:
        self.vg = tuple(d["vg"])
        self.c_per_area_ff_um2 = tuple(d["c_per_area_ff_um2"])
        self.node_count = int(d["node_count"])
        self.extended_fallback = tuple(d["extended_fallback"])
        self.roundoff_accepted = tuple(d["roundoff_accepted"])


def cell_dir(device: str) -> Path:
    """The committed calibrated cell of the study's geometry."""
    gid = geometry_id(meshconv.geometry_2d(device))
    return Path("results") / "tcad" / "moscap2d" / device / "calibrated" / gid


def record(work: Path, device: str, repo: Path) -> dict:
    """The record of ``device`` from the level directories under ``work``."""
    levels = meshconv.levels(2)
    data, pinned = [], []
    for i, scale in enumerate(levels):
        d = Path(work) / device / f"level{i}"
        if not (d / "level.json").is_file() or not (d / "pins.json").is_file():
            raise ValueError(f"{d}: no level.json and pins.json (run it with run.py)")
        lv = json.loads((d / "level.json").read_bytes())
        spec = meshconv.START[2].scaled(scale, refine_grading=meshconv.REFINE_GRADING[2])
        if lv["scale"] != scale or meshconv.MeshSpec(**lv["spec"]) != spec:
            raise ValueError(f"{d}: level.json is not level {i} of the start spec")
        data.append(lv)
        pinned.append(json.loads((d / "pins.json").read_bytes()))
    for i, p in enumerate(pinned):
        if p != pinned[0]:
            diff = sorted(k for k in {*p, *pinned[0]} if p.get(k) != pinned[0].get(k))
            raise ValueError(f"level{i} ran with other pins than level0: {diff}")
    edge = {json.dumps(lv["edge_fit"], sort_keys=True) for lv in data}
    if len(edge) != 1:
        raise ValueError(f"the levels used different fits: {sorted(edge)}")
    curves = {meshconv.MeshSpec(**lv["spec"]): _Curve(lv) for lv in data}
    rep = meshconv.converge(
        curves.__getitem__, meshconv.START[2], levels,
        rel_tol=moscap1d.REL_TOL, refine_grading=meshconv.REFINE_GRADING[2],
    )  # fmt: skip
    committed = json.loads(
        (repo / meshconv.job_dir(meshconv.TREE_ROOT, device, 2) / meshconv.REPORT_NAME).read_bytes()
    )
    selected = committed["selected"]["level"]
    worst = rep.levels[selected].max_rel_change
    vg, c_cell, meta = moscap2d.read_cv(repo / cell_dir(device))
    c_level = rep.levels[selected].c_per_area_ff_um2
    if tuple(vg) != tuple(rep.vg):
        raise ValueError(f"{cell_dir(device)}: other biases than the levels")
    report = meshconv.report_dict(rep, device=device, dim=2, settings={})
    del report["settings"], report["excluded_levels"]
    report["params"] = "calibrated"
    return {
        "schema": SCHEMA,
        "device": device,
        "geometry": geometry_id(meshconv.geometry_2d(device)),
        "params": "calibrated",
        "edge_fit": data[0]["edge_fit"],
        "calibration_sha256": data[0]["calibration_sha256"],
        **pinned[0],
        "check": {
            "criterion": meshconv.CRITERION,
            "selected_level": selected,
            "max_rel_change": worst,
            "meets_criterion": worst < meshconv.CRITERION,
        },
        "cell": {
            "job": cell_dir(device).as_posix(),
            "edge_fit": meta.get("edge_fit"),
            "node_count": meta["node_count"],
            "level_node_count": rep.levels[selected].node_count,
            "max_rel_diff": max(abs(a / b - 1) for a, b in zip(c_level, c_cell, strict=True)),
        },
        "meshed_l_um": [lv["meshed_l_um"] for lv in data],
        "resumed": [lv["resumed"] for lv in data],
        "report": report,
    }


def main(argv: list[str]) -> int:
    work, device, out = argv
    repo = Path(__file__).resolve().parents[2]
    io.write_json(Path(out), record(Path(work).expanduser(), device, repo))
    print(f"wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
