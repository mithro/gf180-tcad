# SPDX-License-Identifier: Apache-2.0
"""The figures of the comparison pages (gf180tcad.comparison_figures): deterministic light and
dark twins, drawn from the committed files, each embedded as a pair and cited on its page."""

import json
import math
import os
import re
import subprocess
import sys
import textwrap

import pytest
from optional import importorskip

importorskip("matplotlib", reason="needs the docs dependency group")

from test_explained import numeric_literals

from gf180tcad import comparison_figures as cf
from gf180tcad.devices import DEVICES, geometry_id
from gf180tcad.sandbox import REPO_ROOT

PAGES = sorted((REPO_ROOT / "docs" / "comparison").glob("*.md"))
SRC = REPO_ROOT / "src" / "gf180tcad" / "comparison_figures.py"

# Every figure (test_figures_listed_here_are_all_the_figures holds the list complete).
FIGURES = [
    "process-cell",
    "instance-plan",
    "geometries",
    "meshconv",
    "cv-fit",
    "cv-validation",
    "cv-metric",
    "pfet-edge",
    "fitted-stack",
    "start-stack",
    "cgg-split",
    "centroid",
    "pdk-sweeps",
]

_RENDER = textwrap.dedent(
    """
    import sys
    from gf180tcad import comparison_figures
    sys.stdout.buffer.write(comparison_figures.FIGURES[sys.argv[1]](sys.argv[2]))
    """
)


def test_figures_listed_here_are_all_the_figures():
    assert sorted(FIGURES) == sorted(cf.FIGURES)


@pytest.mark.parametrize("figure", FIGURES)
@pytest.mark.parametrize("palette", ["light", "dark"])
def test_svg_deterministic(figure, palette):
    """Two fresh processes with different hash seeds give the same bytes, with text kept as text,
    no date and no host path."""
    runs = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run(
            [sys.executable, "-c", _RENDER, figure, palette],
            env=env, capture_output=True, check=True, timeout=300,
        )  # fmt: skip
        runs.append(r.stdout)
    a, b = runs
    assert a.startswith(b"<?xml") and b"<text" in a and a == b
    assert b"<dc:date>" not in a and str(REPO_ROOT).encode() not in a


def test_figure_code_has_no_numeric_literals():
    found = numeric_literals(SRC.read_text(encoding="utf-8"))
    assert not found, f"number literals outside STYLE and UNITS: {found}"


def test_figures_have_dark_twins_and_every_page_embeds_pairs(tmp_path):
    cf.write_all(tmp_path)
    light = sorted(p.name.removesuffix("-light.svg") for p in tmp_path.glob("*-light.svg"))
    dark = sorted(p.name.removesuffix("-dark.svg") for p in tmp_path.glob("*-dark.svg"))
    assert light == dark == sorted(cf.FIGURES)
    for name in light:
        assert (tmp_path / f"{name}-light.svg").read_bytes() != (
            tmp_path / f"{name}-dark.svg"
        ).read_bytes()
    used = set()
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        for name in re.findall(r"/_generated/comparison/([\w-]+)-light\.svg", text):
            assert f"/_generated/comparison/{name}-dark.svg" in text, (page.name, name)
            assert name in cf.FIGURES, (page.name, name)
            used.add(name)
        assert text.count(":figclass: only-light") == text.count(":figclass: only-dark"), page
    assert used == set(cf.FIGURES), f"drawn but on no page: {sorted(set(cf.FIGURES) - used)}"


def test_instance_plan_reads_the_netlist_template():
    """The source/drain length is the template's AS / W (0.18 µm, the xschem symbol's value)."""
    e = cf.instance_extents()
    assert (e["w_um"], e["l_um"]) == (1.6, 0.7)
    assert math.isclose(e["sd_um"], 0.18, rel_tol=1e-12)


def _result(device: str) -> dict:
    path = REPO_ROOT / "results" / "tcad" / "calibration" / f"{device}.result.json"
    return json.loads(path.read_text("utf-8"))


def test_metric_figure_marks_the_calibration_regions():
    """The u_fb, u_t, C_mid and crossings drawn are the ones the calibration recorded."""
    _u, _c, r = cf.metric_regions()
    rec = _result(cf.METRIC_DEVICE)["per_geometry"][cf.METRIC_GEOMETRY]["spice_regions"]
    for key in ("u_fb", "u_t", "c_mid", "u_dep", "u_inv", "c_acc", "c_inv"):
        assert math.isclose(getattr(r, key), rec[key], rel_tol=1e-12), key


def test_pfet_edge_marks_the_recorded_crossings():
    """Each marked SPICE u_dep is the calibration's (calibration geometries) or the page's."""
    curves = cf.edge_curves()
    assert [c["geometry"].l_um for c in curves] == [10, 2, 1, 0.7, 0.5]
    per = _result("pfet_05v0")["per_geometry"]
    for c in curves:
        gid = geometry_id(c["geometry"])
        if gid in per:
            assert math.isclose(c["u_dep"], per[gid]["spice_regions"]["u_dep"], rel_tol=1e-12)
    # The values the cv-agreement page prints for the five lengths (mismatch analysis).
    printed = [-0.590, -0.688, -0.827, -0.961, -1.160]
    assert [round(c["u_dep"], 3) for c in curves] == printed


def test_centroid_figure_marks_the_allowance_maximum():
    """The marked point is the largest accumulation X_DC in the window, as the process file's
    allowance computes it, and lies on the drawn curve."""
    for device in DEVICES:
        k = cf.centroid_curves(device)
        cen = k["centroid"]
        u_max = cen.vg_at_max_v * k["polarity"]
        drawn = dict(zip(k["u"].tolist(), k["x_acc_nm"].tolist(), strict=True))
        assert math.isclose(drawn[u_max], cen.x_dc_acc_max_m * 1e9, rel_tol=1e-12)
        window = [x for u, x in drawn.items() if u <= -cen.plateau_v]
        assert math.isclose(max(window), cen.x_dc_acc_max_m * 1e9, rel_tol=1e-12)


def test_meshconv_points_skip_the_finest_level():
    for dim in (1, 2):
        for device in DEVICES:
            report = cf.meshconv_report(dim, device)
            nodes, change = cf.meshconv_points(report)
            assert len(nodes) == len(report["levels"]) - 1 == len(change)
            assert all(c < report["criterion"] for c in change)


def test_pdk_sweeps_are_one_curve_per_body_bias():
    for device in DEVICES:
        new = cf.pdk_sweep_curves(device, cf.SPICE_ROOT)
        old = cf.pdk_sweep_curves(device, cf.OLDER_PDK_ROOT)
        assert len(new) == len(old) == 3
        for (a, b), (c, d) in zip(new, old, strict=True):
            assert a.tolist() == c.tolist() and b.tolist() == d.tolist()


_DOCS_GROUP_ONLY = textwrap.dedent(
    """
    import sys
    for name in ("gdsfactory", "gplugins", "shapely", "gf180mcu", "devsim"):
        sys.modules[name] = None
    from pathlib import Path
    from gf180tcad import comparison_figures
    comparison_figures.write_all(Path(sys.argv[1]))
    print(sorted(p.name for p in Path(sys.argv[1]).iterdir()))
    """
)


def test_figures_draw_without_the_simulators(tmp_path):
    """docgen draws them in the docs build, which has no simulator installed."""
    r = subprocess.run(
        [sys.executable, "-c", _DOCS_GROUP_ONLY, str(tmp_path)],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip
    assert r.returncode == 0, r.stderr[-3000:]
    assert "-dark.svg" in r.stdout and "-light.svg" in r.stdout
