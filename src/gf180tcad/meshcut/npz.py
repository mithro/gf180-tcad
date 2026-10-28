# SPDX-License-Identifier: Apache-2.0
"""A deterministic ``.npz`` writer: the same arrays always give the same bytes.

``numpy.savez_compressed`` stamps each member with the current time, so its output differs
from run to run. :func:`write_npz` writes the zip itself: members sorted by name, each a
``.npy`` file with a format 1.0 header from ``numpy.lib.format``, every member dated
1980-01-01 00:00:00 (the zip epoch), ``ZIP_DEFLATED`` at level 9, no extra fields and no
comments. ``numpy.load`` reads the result like any ``.npz``; :func:`read_npz` does so with
pickles refused.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Mapping
from pathlib import Path

import numpy as np
from numpy.lib import format as npy_format

_EPOCH = (1980, 1, 1, 0, 0, 0)


def _member(name: str, array: object) -> bytes:
    if not isinstance(name, str) or not name or "/" in name or name.startswith("."):
        raise ValueError(f"bad member name {name!r}")
    if not isinstance(array, np.ndarray):
        raise TypeError(f"member {name!r} is a {type(array).__name__}, not a numpy array")
    if array.dtype.hasobject:
        raise TypeError(f"member {name!r} has an object dtype, which needs a pickle")
    buf = io.BytesIO()
    npy_format.write_array(buf, np.ascontiguousarray(array), version=(1, 0), allow_pickle=False)
    return buf.getvalue()


def write_npz(path: Path | str, arrays: Mapping[str, np.ndarray]) -> None:
    """Write ``arrays`` to ``path`` as a deterministic ``.npz``."""
    members = {name: _member(name, arrays[name]) for name in sorted(arrays)}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            info = zipfile.ZipInfo(name + ".npy", date_time=_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # Unix, whatever the host
            info.external_attr = 0o644 << 16
            z.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    Path(path).write_bytes(buf.getvalue())


def read_npz(path: Path | str) -> dict[str, np.ndarray]:
    """Every member of the ``.npz`` at ``path``, pickles refused."""
    with np.load(path, allow_pickle=False) as z:
        return {name: z[name] for name in z.files}
