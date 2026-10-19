# SPDX-License-Identifier: Apache-2.0
"""The calibration-file schema (gf180tcad.tcad.calibration) and its use by the CLI."""

import json
import math

import pytest

from gf180tcad.tcad import __main__ as cli
from gf180tcad.tcad import calibration, process

VALUES = {"t_ox_eff_nm": 15.9, "n_ch_cm3": 2.0e17, "dv_fb_v": 0.05}


def _file(tmp_path, data, name="nfet_05v0.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_write_then_read(tmp_path):
    p = tmp_path / "nfet_05v0.json"
    calibration.write(p, "nfet_05v0", VALUES)
    assert calibration.read(p, "nfet_05v0") == VALUES
    data = json.loads(p.read_bytes())
    assert set(data) == {"device", "schema", "values"} and data["schema"] == 1


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"device": "nfet_05v0", "schema": 1, "values": {"t_ox_eff_nm": 15.9}}, "missing"),
        (
            {"device": "nfet_05v0", "schema": 1, "values": {**VALUES, "k1": 0.9}},
            "unknown",
        ),
        ({"device": "nfet_05v0", "schema": 1, "values": VALUES, "fit": {}}, "keys"),
        ({"device": "nfet_05v0", "values": VALUES}, "keys"),
        ({"device": "pfet_05v0", "schema": 1, "values": VALUES}, "device"),
        ({"device": "nfet_05v0", "schema": 2, "values": VALUES}, "schema"),
        ({"device": "nfet_05v0", "schema": 1, "values": {**VALUES, "dv_fb_v": "0"}}, "finite"),
        ({"device": "nfet_05v0", "schema": 1, "values": {**VALUES, "dv_fb_v": True}}, "finite"),
        ([1, 2], "object"),
    ],
)
def test_read_refuses(tmp_path, data, match):
    with pytest.raises(calibration.CalibrationFileError, match=match):
        calibration.read(_file(tmp_path, data), "nfet_05v0")


def test_read_refuses_nan(tmp_path):
    p = tmp_path / "nfet_05v0.json"
    p.write_text(
        '{"device": "nfet_05v0", "schema": 1, "values": '
        '{"t_ox_eff_nm": NaN, "n_ch_cm3": 1.7e17, "dv_fb_v": 0.0}}',
        encoding="utf-8",
    )
    with pytest.raises(calibration.CalibrationFileError, match="finite"):
        calibration.read(p, "nfet_05v0")


def test_write_refuses_a_partial_fit(tmp_path):
    with pytest.raises(calibration.CalibrationFileError, match="missing"):
        calibration.write(tmp_path / "x.json", "nfet_05v0", {"t_ox_eff_nm": 15.9})


def test_param_sha256_is_canonical():
    a = calibration.param_sha256(VALUES)
    b = calibration.param_sha256(dict(reversed(list(VALUES.items()))))
    assert a == b and len(a) == 64
    assert a != calibration.param_sha256({**VALUES, "dv_fb_v": math.nextafter(0.05, 1)})


def test_cli_loads_a_valid_calibration(tmp_path, monkeypatch):
    p = tmp_path / "nfet_05v0.json"
    calibration.write(p, "nfet_05v0", VALUES)
    monkeypatch.setattr(cli, "calibration_file", lambda d: tmp_path / f"{d}.json")
    proc, sha = cli.load_params("nfet_05v0", "calibrated")
    assert {n: proc.params[n].value for n in process.TUNABLES} == VALUES
    assert sha == calibration.sha256_file(p)
    assert cli.load_params("nfet_05v0", "start")[1] is None


def test_cli_refuses_a_partial_calibration(tmp_path, monkeypatch):
    _file(tmp_path, {"device": "nfet_05v0", "schema": 1, "values": {"t_ox_eff_nm": 15.9}})
    monkeypatch.setattr(cli, "calibration_file", lambda d: tmp_path / f"{d}.json")
    with pytest.raises(calibration.CalibrationFileError, match="missing"):
        cli.load_params("nfet_05v0", "calibrated")
