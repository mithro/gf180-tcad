# SPDX-License-Identifier: Apache-2.0
"""Parser for ngspice binary raw files (``set filetype=binary``), real and complex plots.

Layout: ASCII header lines ``Key: value`` (``Title``, ``Date``, ``Plotname``, ``Flags``,
``No. Variables``, ``No. Points``), a ``Variables:`` block with one ``<index> <name> <type>``
line per vector, then ``Binary:`` and the data, point by point: one little-endian float64 per
vector for a ``real`` plot, two (real, imaginary) for a ``complex`` plot.

Only single-plot files are accepted: the netlists in :mod:`gf180tcad.spice.netlist` always
``write`` exactly one plot, so a second plot means something unexpected happened and is an error
rather than something to choose from.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

_BINARY = b"Binary:\n"


def _header_value(fields: dict[str, str], key: str, path: Path) -> str:
    if key not in fields:
        raise ValueError(f"{path}: raw header has no '{key}:' line")
    return fields[key]


def read_raw(path: Path) -> dict[str, np.ndarray]:
    """Return ``{vector name: values}`` in file order (float64 or complex128 arrays)."""
    path = Path(path)
    blob = path.read_bytes()
    end = blob.find(_BINARY)
    if end < 0:
        raise ValueError(f"{path}: not a binary raw file (no 'Binary:' line; use filetype=binary)")
    lines = blob[:end].decode("ascii").split("\n")
    fields: dict[str, str] = {}
    var_lines: list[str] = []
    in_vars = False
    for line in lines:
        if in_vars:
            if line.startswith(("\t", " ")):
                var_lines.append(line)
                continue
            in_vars = False
        if line.strip() == "Variables:":
            in_vars = True
        elif line:
            key, sep, value = line.partition(":")
            if not sep:
                raise ValueError(f"{path}: malformed raw header line {line!r}")
            fields[key.strip()] = value.strip()

    flags = _header_value(fields, "Flags", path).split()
    kinds = {"real", "complex"} & set(flags)
    if len(kinds) != 1 or not set(flags) <= {"real", "complex", "padded", "unpadded"}:
        raise ValueError(f"{path}: unsupported Flags {fields['Flags']!r}")
    is_complex = kinds == {"complex"}
    nvars = int(_header_value(fields, "No. Variables", path))
    npoints = int(_header_value(fields, "No. Points", path))

    names: list[str] = []
    for line in var_lines:
        parts = line.split()
        if len(parts) < 3:
            raise ValueError(f"{path}: malformed variable line {line!r}")
        idx, name, extra = int(parts[0]), parts[1], parts[3:]
        if idx != len(names):
            raise ValueError(f"{path}: variable index {idx} out of order")
        if any(e.startswith("dims=") for e in extra):
            raise ValueError(f"{path}: multi-dimensional vector {name!r} (dims=) not supported")
        if name in names:
            raise ValueError(f"{path}: duplicate variable name {name!r}")
        names.append(name)
    if len(names) != nvars:
        raise ValueError(f"{path}: header says {nvars} variables but lists {len(names)}")

    payload = blob[end + len(_BINARY) :]
    width = 2 if is_complex else 1
    expected = npoints * nvars * width * 8
    if len(payload) > expected and payload[expected:].startswith(b"Title:"):
        raise ValueError(f"{path}: more than one plot in the raw file; expected exactly one plot")
    if len(payload) != expected:
        raise ValueError(
            f"{path}: binary data size {len(payload)} != {expected} bytes "
            f"({npoints} points x {nvars} vectors x {width * 8} bytes)"
        )
    values = np.frombuffer(payload, dtype="<f8").reshape(npoints, nvars * width)
    if is_complex:
        cols = np.empty((npoints, nvars), dtype=np.complex128)
        cols.real = values[:, 0::2]  # assigned, not computed: exact even for inf/nan parts
        cols.imag = values[:, 1::2]
    else:
        cols = values
    return {n: np.array(cols[:, i], copy=True) for i, n in enumerate(names)}
