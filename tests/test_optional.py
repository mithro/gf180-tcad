# SPDX-License-Identifier: Apache-2.0
"""tests/optional.py: an optional dependency skips locally but fails on CI."""

import pytest
from optional import importorskip

MISSING = "gf180tcad_no_such_module"


def test_missing_module_skips_locally(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(pytest.skip.Exception):
        importorskip(MISSING, reason="needs it")


@pytest.mark.parametrize("value", ["true", "1"])
def test_missing_module_fails_on_ci(monkeypatch, value):
    monkeypatch.setenv("CI", value)
    with pytest.raises(ImportError, match=MISSING):
        importorskip(MISSING, reason="needs it")


def test_present_module_is_returned(monkeypatch):
    import json

    for ci in (None, "true"):
        if ci is None:
            monkeypatch.delenv("CI", raising=False)
        else:
            monkeypatch.setenv("CI", ci)
        assert importorskip("json") is json
