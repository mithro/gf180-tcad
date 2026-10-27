# SPDX-License-Identifier: Apache-2.0
"""Write the synthetic render manifest ``r-test.render.json`` from the files in ``sources/``.

Run from the repo root: ``uv run --locked python tests/fixtures/renders/make_fixture.py``.
``tests/test_renders.py::test_fixture_is_the_builder_output`` checks that the committed file
is this function's output.
"""

from pathlib import Path

from gf180tcad.render.manifest import Builder, Manifest

HERE = Path("tests") / "fixtures" / "renders"
SRC = HERE / "sources"


def build(root: Path) -> Manifest:
    b = Builder(root, "r-test", device="synthetic", params="start")
    meta, curve, display = (SRC / n for n in ("stack.meta.json", "curve.csv", "display.toml"))
    b.source(
        "t_ox",
        meta.as_posix(),
        {"json": ["stack", "t_ox_nm"]},
        "nm",
        role="geometry",
        scale=40.0,
        label="oxide thickness",
    )
    b.source(
        "poly",
        meta.as_posix(),
        {"json": ["stack", "poly_um"]},
        "um",
        role="geometry",
        scale=1.0,
        label="poly thickness",
    )
    b.source(
        "vg",
        curve.as_posix(),
        {"csv": {"columns": ["vg"], "rows": "all"}},
        "V",
        role="axis",
        scale=1.0,
    )
    b.source("psi", curve.as_posix(), {"csv": {"columns": ["psi_v"], "rows": "all"}}, "V")
    b.source(
        "cv",
        curve.as_posix(),
        {"csv": {"columns": ["vg", "c_per_area"], "rows": "all"}},
        ["V", "fF/um^2"],
    )
    b.source(
        "psi_at_0", curve.as_posix(), {"csv": {"columns": ["psi_v"], "where": {"vg": 0.0}}}, "V"
    )
    b.source(
        "first_c", curve.as_posix(), {"csv": {"columns": ["c_per_area"], "index": 0}}, "fF/um^2"
    )
    b.source("e_g", display.as_posix(), {"toml": ["silicon", "band_gap_ev"]}, "eV", role="display")
    b.derived("e_c", "band_edge_ec", ["psi", "e_g"], "eV")
    b.derived("e_c_at_0", "band_edge_ec", ["psi_at_0", "e_g"], "eV")
    return b.build(["depth axis: log scale from 1 nm"])


if __name__ == "__main__":
    build(Path.cwd()).dump(HERE / "r-test.render.json")
