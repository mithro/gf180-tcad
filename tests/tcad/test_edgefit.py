# SPDX-License-Identifier: Apache-2.0
"""The frozen poly length bias fit (gf180tcad.tcad.edgefit) and how a 2D job applies it."""

import hashlib
import json

import pytest
from test_moscap2d import _synthetic_cv

from gf180tcad.tcad import __main__ as cli
from gf180tcad.tcad import edgefit, moscap2d, process


def _fit_file(root, device="nfet_05v0", delta=40.25):
    root.mkdir(parents=True, exist_ok=True)
    path = edgefit.fit_file(device, root)
    path.write_text(
        json.dumps({"device": device, "poly_bias_nm": delta, "schema": edgefit.SCHEMA}),
        encoding="utf-8",
    )
    return path


def test_no_fit_leaves_the_process_alone(tmp_path):
    proc = process.load("nfet_05v0")
    got, record = edgefit.apply(proc, tmp_path)
    assert got is proc and record is None
    assert edgefit.read("nfet_05v0", tmp_path) is None
    assert edgefit.sha256("nfet_05v0", tmp_path) is None


def test_a_fit_sets_the_bias_and_records_its_file(tmp_path):
    path = _fit_file(tmp_path)
    proc = process.load("nfet_05v0")
    assert proc.values()[edgefit.PARAM] == 0.0
    got, record = edgefit.apply(proc, tmp_path)
    assert got.values()[edgefit.PARAM] == 40.25
    assert got.params[edgefit.PARAM].provenance == "calibrated"
    # every other value is untouched
    assert {k: v for k, v in got.values().items() if k != edgefit.PARAM} == {
        k: v for k, v in proc.values().items() if k != edgefit.PARAM
    }
    assert record == {
        edgefit.PARAM: 40.25,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"device": "pfet_05v0", "poly_bias_nm": 1.0, "schema": edgefit.SCHEMA},
        {"device": "nfet_05v0", "poly_bias_nm": 1.0, "schema": edgefit.SCHEMA + 1},
        {"device": "nfet_05v0", "schema": edgefit.SCHEMA},
    ],
)
def test_a_wrong_file_is_refused(tmp_path, bad):
    edgefit.fit_file("nfet_05v0", tmp_path).write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="edge fit"):
        edgefit.read("nfet_05v0", tmp_path)


def test_a_fit_outside_the_bounds_is_refused(tmp_path):
    _fit_file(tmp_path, delta=500.0)
    with pytest.raises(ValueError, match="outside its bounds"):
        edgefit.apply(process.load("nfet_05v0"), tmp_path)


def test_load_params_2d_applies_the_fit_to_calibrated_only(tmp_path, monkeypatch):
    _fit_file(tmp_path)
    monkeypatch.setattr(edgefit, "TREE_ROOT", tmp_path)
    proc, cal, fit = cli.load_params_2d("nfet_05v0", "start")
    assert cal is None and fit is None and proc.values()[edgefit.PARAM] == 0.0
    proc, cal, fit = cli.load_params_2d("nfet_05v0", "calibrated")
    assert cal is not None and fit[edgefit.PARAM] == 40.25
    assert proc.values()[edgefit.PARAM] == 40.25
    # the 1D values are the 1D calibration's, unchanged by the fit
    one_d, _ = cli.load_params("nfet_05v0", "calibrated")
    for name in process.TUNABLES:
        assert proc.values()[name] == one_d.values()[name]


def _write(tmp_path, params, edge_fit):
    out = tmp_path / params
    out.mkdir()
    (out / moscap2d.MESH_FILE).write_bytes(b"mesh")
    cv = _synthetic_cv("qs")
    proc = process.load("nfet_05v0")
    cal = "ab" * 32 if params == "calibrated" else None
    moscap2d.write(
        cv, None, out, proc=proc, params=params, mesh_source="m", calibration_sha256=cal,
        edge_fit=edge_fit,
    )  # fmt: skip
    return json.loads((out / moscap2d.META_JSON).read_bytes())


def test_meta_has_no_fit_key_without_a_fit(tmp_path):
    """Without a fit the meta has no ``edge_fit`` key, so the committed δ = 0 cells keep their
    bytes when this code lands."""
    assert "edge_fit" not in _write(tmp_path, "calibrated", None)
    assert "edge_fit" not in _write(tmp_path, "start", None)


def test_meta_with_a_fit(tmp_path):
    rec = {edgefit.PARAM: 40.25, "sha256": "cd" * 32}
    out = tmp_path / "c"
    out.mkdir()
    (out / moscap2d.MESH_FILE).write_bytes(b"mesh")
    moscap2d.write(
        _synthetic_cv("qs"), None, out, proc=process.load("nfet_05v0"), params="calibrated",
        mesh_source="m", calibration_sha256="ab" * 32, edge_fit=rec,
    )  # fmt: skip
    assert json.loads((out / moscap2d.META_JSON).read_bytes())["edge_fit"] == rec


def test_a_fit_on_start_values_is_refused(tmp_path):
    out = tmp_path / "s"
    out.mkdir()
    (out / moscap2d.MESH_FILE).write_bytes(b"mesh")
    with pytest.raises(ValueError, match="calibrated 2D jobs only"):
        moscap2d.write(
            _synthetic_cv("qs"), None, out, proc=process.load("nfet_05v0"), params="start",
            mesh_source="m", edge_fit={edgefit.PARAM: 1.0, "sha256": "x"},
        )  # fmt: skip
