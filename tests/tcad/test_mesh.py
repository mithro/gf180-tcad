# SPDX-License-Identifier: Apache-2.0
"""MeshSpec (gf180tcad.tcad.mesh): spacings, uniform refinement and the plugin's mesh objects.

The sandbox-marked test builds the plugin's Mesh1D and meshwell resolution specs inside the
TCAD image (run with ``pytest -m sandbox``); the others run on the host.
"""

import dataclasses
import json
import math

import pytest

from gf180tcad import sandbox
from gf180tcad.tcad import TCAD_IMAGE
from gf180tcad.tcad.mesh import MeshSpec

SPEC = MeshSpec(h_poly_nm=0.1, h_ox_nm=0.5, h_si_surface_nm=0.2, h_si_bulk_nm=20.0, grading=1.2)
FIELDS = ("h_poly_nm", "h_ox_nm", "h_si_surface_nm", "h_si_bulk_nm")


def test_mesh_poly_refined():
    half = SPEC.scaled(0.5)
    assert half.h_poly_nm == SPEC.h_poly_nm / 2  # poly depletion is refined too
    for f in FIELDS:
        assert getattr(half, f) == getattr(SPEC, f) * 0.5, f
    assert half.grading == SPEC.grading


def test_scaled_refines_the_2d_size_field_everywhere():
    """2D uniform refinement: the threshold size h_min + (grading - 1) * d must scale by r at
    every distance d, so the growth slope (grading - 1) scales too; distmax is unchanged.

    With the grading fixed, the size beyond a few nm (the depletion region) was the same at every
    level, and the 2D/1D agreement at the C-V minimum did not converge (Task 11 report).
    """
    for r in (2**-0.5, 0.5, 2**-1.5):
        s = SPEC.scaled(r, refine_grading=True)
        assert math.isclose(s.grading - 1, (SPEC.grading - 1) * r, rel_tol=1e-12)
        for f in FIELDS:
            assert math.isclose(getattr(s, f), getattr(SPEC, f) * r, rel_tol=1e-12), f
        for d_nm in (0.0, 5.0, 50.0):
            size = min(SPEC.h_si_surface_nm + (SPEC.grading - 1) * d_nm, SPEC.h_si_bulk_nm)
            size_r = min(s.h_si_surface_nm + (s.grading - 1) * d_nm, s.h_si_bulk_nm)
            assert math.isclose(size_r, r * size, rel_tol=1e-12), (r, d_nm)
        assert math.isclose(
            s.threshold_distmax_um(s.h_si_surface_nm),
            SPEC.threshold_distmax_um(SPEC.h_si_surface_nm),
            rel_tol=1e-12,
        )
    assert SPEC.scaled(0.5).grading == SPEC.grading  # the default (1D) keeps the grading


def test_scaled_rejects_bad_factors():
    for r in (0, -1, math.inf, math.nan):
        with pytest.raises(ValueError):
            SPEC.scaled(r)


@pytest.mark.parametrize("field", [*FIELDS, "grading"])
@pytest.mark.parametrize("bad", [0, -0.1, math.nan, math.inf, True, "1"])
def test_fields_validated(field, bad):
    with pytest.raises(ValueError):
        dataclasses.replace(SPEC, **{field: bad})


def test_grading_above_one():
    with pytest.raises(ValueError, match="grading"):
        dataclasses.replace(SPEC, grading=1.0)


def test_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        SPEC.h_poly_nm = 1.0


def test_spacing_um():
    s = SPEC.spacing_um("gate_poly", "oxide", "body")
    assert list(s) == ["gate_poly", "oxide", "body"]
    assert s["gate_poly"] == (20.0e-3, 0.1e-3)  # bulk at the contact, h_poly at the oxide
    assert s["oxide"] == (0.1e-3, 0.2e-3)  # min(h_ox, neighbour) at each face
    assert s["body"] == (0.2e-3, 20.0e-3)
    coarse_ox = dataclasses.replace(SPEC, h_ox_nm=0.05)
    assert coarse_ox.spacing_um("p", "o", "b")["o"] == (0.05e-3, 0.05e-3)


def test_default_1d_is_a_spec():
    d = MeshSpec.DEFAULT_1D
    assert isinstance(d, MeshSpec)
    assert d.as_dict() == {f.name: getattr(d, f.name) for f in dataclasses.fields(d)}


def test_default_2d_is_coarser_at_the_interfaces():
    """The 2D start spec: isotropic triangles cannot be 0.05 nm along a 10 um interface, so the
    interfaces start at 0.5 nm (1D error at that spacing: <= 0.44 %, Task 11 report)."""
    d = MeshSpec.DEFAULT_2D
    assert d.h_si_surface_nm == d.h_poly_nm == 0.5
    assert d.h_si_surface_nm > MeshSpec.DEFAULT_1D.h_si_surface_nm
    assert MeshSpec.MAX_SAMPLING >= 10**6


def test_threshold_distmax_follows_the_grading():
    # a size growing at slope (grading - 1) reaches h_bulk at (h_bulk - h_min)/(grading - 1)
    assert math.isclose(SPEC.threshold_distmax_um(0.2), (20.0 - 0.2) / 0.2 * 1e-3, rel_tol=1e-12)


@pytest.mark.sandbox
def test_plugin_objects_in_the_image(tmp_path):
    code = f"""
import json
from gf180tcad.tcad.mesh import MeshSpec
spec = MeshSpec(**{json.dumps(dataclasses.asdict(SPEC))})
m = spec.to_mesh1d("gate_poly", "oxide", "body")
r = spec.to_resolution_specs("gate_poly", "oxide", "body")
rb = spec.to_resolution_specs("gate_poly", "oxide", "body", background="ild")
out = {{
    "res_background": {{k: [(type(x).__name__, x.model_dump(exclude_none=True)) for x in v] for k, v in rb.items()}},
    "type": type(m).__module__ + "." + type(m).__name__,
    "max_ratio": m.max_ratio,
    "spacing": {{k: list(v) for k, v in m.spacing_um.items()}},
    "res": {{k: [(type(x).__name__, x.model_dump(exclude_none=True)) for x in v] for k, v in r.items()}},
}}
print(json.dumps(out, default=str))
"""
    res = sandbox.run(["python3", "-c", code], out_dir=tmp_path, image=TCAD_IMAGE, mem="2g", cpus=1)
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["type"] == "gplugins.devsim.stack1d.Mesh1D"
    assert out["max_ratio"] == 1.2
    assert out["spacing"] == {
        k: list(v) for k, v in SPEC.spacing_um("gate_poly", "oxide", "body").items()
    }
    res_specs = out["res"]
    (ox,) = res_specs["oxide"]
    assert ox[0] == "ConstantInField" and ox[1]["resolution"] == 0.5e-3
    (body,) = res_specs["body"]
    assert body[0] == "ThresholdField" and body[1]["sharing"] == ["oxide"]
    assert body[1]["sizemin"] == 0.2e-3 and body[1]["sizemax"] == 20e-3
    (poly,) = res_specs["gate_poly"]
    assert poly[1]["sizemin"] == 0.1e-3 and poly[1]["apply_to"] == "curves"
    # meshwell samples each curve's distance field at mass / (sizemin / 2) points, capped by
    # max_sampling (default 100: a 10 nm sample pitch on a 1 um interface); the cap is lifted
    assert body[1]["max_sampling"] == poly[1]["max_sampling"] == MeshSpec.MAX_SAMPLING
    rb = out["res_background"]["body"]
    assert rb[0][1]["sharing"] == ["oxide", "ild"]
