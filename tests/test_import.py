# SPDX-License-Identifier: Apache-2.0
"""Smoke test: the package imports and its version matches pyproject.toml."""

import tomllib
from pathlib import Path

import gf180tcad


def test_version():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    expected = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert expected == "0.1.0.dev0"
    assert gf180tcad.__version__ == expected
