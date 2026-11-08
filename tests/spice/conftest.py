# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for the SPICE tests."""

import pytest

from gf180tcad import engine46
from gf180tcad.pdk import PdkInfo


@pytest.fixture(scope="session")
def image_pdk(tmp_path_factory) -> PdkInfo:
    """The image's PDK, located and checked against versions.json inside the sandbox
    (engine46.image_pdk)."""
    return engine46.image_pdk(tmp_path_factory.mktemp("pdk"))
