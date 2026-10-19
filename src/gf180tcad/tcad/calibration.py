# SPDX-License-Identifier: Apache-2.0
"""The calibration file of one device, ``results/tcad/calibration/<device>.json``: its one schema.

Task 12 writes it with :func:`write`, and every reader (``python -m gf180tcad.tcad moscap
--params calibrated``) reads it with :func:`read`, so writer and reader share this schema:

- ``schema``: :data:`SCHEMA` (1);
- ``device``: the device name, which must match the file name;
- ``values``: exactly the tunables of :data:`gf180tcad.tcad.process.TUNABLES`, each a finite
  number. A missing or an extra tunable is refused, so a partial fit can never be labelled
  calibrated.

No other top-level key is accepted. Floats are written by :func:`gf180tcad.io.write_json`.
:func:`param_sha256` hashes a canonical JSON form of the applied values, recorded in the
provenance and in each job's metadata.

This module is TCAD code, not one of the SPICE generator modules
(:data:`gf180tcad.reference.GENERATOR_MODULES`).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path

from gf180tcad import io
from gf180tcad.tcad.process import DEVICES, TUNABLES

SCHEMA = 1
KEYS = frozenset({"schema", "device", "values"})


class CalibrationFileError(ValueError):
    """A calibration file does not follow the schema."""


def check_values(values: Mapping[str, float], what: str = "values") -> dict[str, float]:
    """``values`` as a dict if it has exactly the :data:`~gf180tcad.tcad.process.TUNABLES`, each a finite number."""
    if not isinstance(values, Mapping):
        raise CalibrationFileError(f"{what} must be an object, got {type(values).__name__}")
    missing = sorted(set(TUNABLES) - set(values))
    extra = sorted(set(values) - set(TUNABLES))
    if missing or extra:
        raise CalibrationFileError(
            f"{what} must hold exactly the tunables {list(TUNABLES)}: missing {missing}, "
            f"unknown {extra}"
        )
    out = {}
    for name in TUNABLES:
        v = values[name]
        if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
            raise CalibrationFileError(f"{what}[{name!r}] must be a finite number, got {v!r}")
        out[name] = float(v)
    return out


def read(path: Path, device: str) -> dict[str, float]:
    """The tunable values of ``device`` from the calibration file ``path`` (validated)."""
    if device not in DEVICES:
        raise CalibrationFileError(f"unknown device {device!r}")
    data = json.loads(Path(path).read_bytes())
    if not isinstance(data, dict):
        raise CalibrationFileError(f"{path}: the top level must be an object")
    if set(data) != KEYS:
        raise CalibrationFileError(f"{path}: the keys must be {sorted(KEYS)}, got {sorted(data)}")
    if data["schema"] != SCHEMA:
        raise CalibrationFileError(f"{path}: schema {data['schema']!r}, expected {SCHEMA}")
    if data["device"] != device:
        raise CalibrationFileError(f"{path}: device {data['device']!r}, expected {device!r}")
    return check_values(data["values"], f"{path}: values")


def write(path: Path, device: str, values: Mapping[str, float]) -> None:
    """Write the calibration file of ``device`` (the reverse of :func:`read`)."""
    if device not in DEVICES:
        raise CalibrationFileError(f"unknown device {device!r}")
    io.write_json(Path(path), {"device": device, "schema": SCHEMA, "values": check_values(values)})


def sha256_file(path: Path) -> str:
    """sha256 of a file's bytes (the calibration file as committed)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def param_sha256(values: Mapping[str, float]) -> str:
    """sha256 of the canonical JSON of the applied tunable values.

    Canonical: sorted keys, no whitespace, ``repr`` floats, UTF-8.
    """
    text = json.dumps(check_values(values), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
