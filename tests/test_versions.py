# SPDX-License-Identifier: Apache-2.0
"""docker/base/versions.json is exactly what probe_versions.py reports inside the pinned image."""

import json
from pathlib import Path

import pytest

from gf180tcad import sandbox

VERSIONS = Path(__file__).resolve().parents[1] / "docker" / "base" / "versions.json"
KEYS = {
    "base_image",
    "python",
    "ngspice",
    "xyce",
    "xyce_parallel",
    "klayout",
    "klayout_python",
    "gdsfactory",
    "devsim",
    "pdk_root",
    "gf180mcu_variant",
    "open_pdks_commit",
    "sm141064_ngspice_sha256",
    "sm141064_xyce_sha256",
    "design_ngspice_sha256",
}


def test_versions_json_shape():
    text = VERSIONS.read_text(encoding="utf-8")
    data = json.loads(text)
    assert set(data) == KEYS
    assert all(isinstance(v, str) and v for v in data.values())
    assert data["gf180mcu_variant"] == "gf180mcuD"
    assert text == json.dumps(data, indent=2, sort_keys=True) + "\n"


@pytest.mark.sandbox
def test_versions_json_matches_image(tmp_path):
    res = sandbox.run(["python3", "/work/src/docker/base/probe_versions.py"], out_dir=tmp_path)
    assert res.stdout == VERSIONS.read_text(encoding="utf-8")
