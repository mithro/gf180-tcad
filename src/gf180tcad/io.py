# SPDX-License-Identifier: Apache-2.0
"""Deterministic result files: CSV with a ``# key: value`` header, and sorted-key JSON.

Floats are written with ``repr`` (shortest round-trip, ``.`` decimal separator, independent of
the process locale), lines end in ``\\n`` and files are UTF-8, so the bytes are reproducible.
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np


def _check_text(kind: str, s: str, forbidden: str) -> None:
    if any(c in s for c in forbidden):
        raise ValueError(f"{kind} {s!r} contains a forbidden character")


def write_csv(path: Path, columns: Mapping[str, Sequence[float]], meta: Mapping[str, str]) -> None:
    """Write ``# key: value`` header lines (sorted keys), a column-name row, then data rows."""
    names = list(columns)
    data = [[float(x) for x in columns[n]] for n in names]
    if len({len(c) for c in data}) > 1:
        raise ValueError("all CSV columns must have the same length")
    lines = []
    for key in sorted(meta):
        _check_text("meta key", key, ":\r\n")
        _check_text("meta value", str(meta[key]), "\r\n")
        lines.append(f"# {key}: {meta[key]}")
    for n in names:
        _check_text("column name", n, ",\r\n#")
    lines.append(",".join(names))
    lines.extend(",".join(repr(x) for x in row) for row in zip(*data, strict=True))
    Path(path).write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def read_csv(path: Path) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    """Inverse of :func:`write_csv`; values are parsed with ``float`` so they are bit-exact."""
    text = Path(path).read_bytes().decode("utf-8")
    meta: dict[str, str] = {}
    rows = []
    for line in text.split("\n"):
        if line.startswith("# "):
            key, _, value = line[2:].partition(": ")
            meta[key] = value
        elif line:
            rows.append(line.split(","))
    if not rows:
        raise ValueError(f"{path}: no CSV header row")
    names, body = rows[0], rows[1:]
    if any(len(r) != len(names) for r in body):
        raise ValueError(f"{path}: ragged CSV row")
    cols = {n: np.array([float(r[i]) for r in body], dtype=np.float64) for i, n in enumerate(names)}
    return cols, meta


def _default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, Path):
        return o.as_posix()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


def write_json(path: Path, obj) -> None:
    """Sorted keys, indent 2, ``repr`` floats, NaN/Inf rejected, trailing newline, UTF-8."""
    text = json.dumps(
        obj, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False, default=_default
    )
    Path(path).write_bytes((text + "\n").encode("utf-8"))
