# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for the SPICE tests."""

import json
from pathlib import Path

import pytest

from gf180tcad import sandbox
from gf180tcad.pdk import PdkInfo


@pytest.fixture(scope="session")
def image_pdk(tmp_path_factory) -> PdkInfo:
    """The image's PDK, located and checked against versions.json inside the sandbox."""
    code = (
        "import dataclasses, json; from gf180tcad import pdk; info = pdk.locate(); "
        "pdk.check_against(info, '/work/src/docker/base/versions.json'); "
        "print(json.dumps({k: str(v) for k, v in dataclasses.asdict(info).items()}))"
    )
    res = sandbox.run(["python3", "-c", code], out_dir=tmp_path_factory.mktemp("pdk"))
    fields = json.loads(res.stdout.splitlines()[-1])
    return PdkInfo(
        **{k: (v if k in ("variant", "open_pdks_commit") else Path(v)) for k, v in fields.items()}
    )
