# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures: pretend to be inside a confined sandbox container."""

import pytest
from confined_root import make_confined_root

from gf180tcad import sandbox


@pytest.fixture
def inside(monkeypatch, tmp_path):
    """Pretend to be inside the sandbox: marker set and a confined fake filesystem root."""
    monkeypatch.setenv(sandbox.IN_SANDBOX_ENV, "1")
    monkeypatch.setattr(sandbox, "CONFINEMENT_ROOT", make_confined_root(tmp_path / "fakeroot"))
