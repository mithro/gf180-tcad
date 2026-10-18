# SPDX-License-Identifier: Apache-2.0
"""Open-source TCAD for GF180MCU transistors, validated against PDK SPICE models."""

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _version() -> str:
    try:
        return version("gf180tcad")
    except PackageNotFoundError:
        # Not installed: run from a source checkout (the container uses PYTHONPATH=/work/src/src).
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]


__version__: str = _version()
