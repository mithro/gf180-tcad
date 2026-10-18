# SPDX-License-Identifier: Apache-2.0
"""Shared helpers of the plugin-history check drivers (``checks_v080.py``, ``checks_v142.py``).

Runs inside the sandbox, in the venv of the gplugins version under test (Python 3.11 for v0.8.0,
3.12 for v1.4.2), so it uses the standard library only and imports nothing of gplugins at module
level. The host side (``python -m gf180tcad.history``) reads the raw JSON a driver writes and
re-writes it with ``gf180tcad.io.write_json``.
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import re
import traceback
from collections.abc import Callable
from pathlib import Path

GPLUGINS_ROOT = Path("/work/out/gplugins")  # the `git archive` of the tag (see gf180tcad.history)
CHECKS = ("import", "pin_test", "ddcomponent_mesh", "ddsolver", "ramp", "refine")

# The `resolutions` dict of the `if __name__ == "__main__":` block of gplugins v0.8.0
# gplugins/devsim/get_solver.py (the PN slab of straight_pn).
PN_RESOLUTIONS = {
    "core": {"resolution": 0.02, "distance": 1},
    "slab90": {"resolution": 0.02, "distance": 1},
}


def scaled_resolutions(mesh_scale: float) -> dict[str, dict[str, float]]:
    """:data:`PN_RESOLUTIONS` with every value multiplied by ``mesh_scale`` (1: unchanged)."""
    if mesh_scale == 1:
        return {k: dict(v) for k, v in PN_RESOLUTIONS.items()}
    return {k: {n: x * mesh_scale for n, x in v.items()} for k, v in PN_RESOLUTIONS.items()}


def run_check(fn: Callable[[], object], gplugins_root: Path = GPLUGINS_ROOT):
    """``(record, value)``: run ``fn``; the record is ``{"status": "pass"}`` or a failure.

    A failure records the exception's type name and message exactly, and ``location``, the
    innermost traceback frame inside ``gplugins_root`` as ``<path relative to it>:<line>``
    (None if no frame is inside it). ``value`` is ``fn()``'s result, or None on failure.
    """
    try:
        value = fn()
    except Exception as e:  # noqa: BLE001 - every failure is the record
        root = str(Path(gplugins_root)) + "/"
        location = None
        for frame in traceback.extract_tb(e.__traceback__):
            if frame.filename.startswith(root):
                location = f"{frame.filename[len(root) :]}:{frame.lineno}"
        return {
            "status": "fail",
            "exception_type": type(e).__name__,
            "message": str(e),
            "location": location,
        }, None
    return {"status": "pass"}, value


def not_run(reason: str) -> dict[str, str]:
    return {"status": "not_run", "reason": reason}


def versions(gplugins_root: Path = GPLUGINS_ROOT) -> dict[str, str]:
    """Every distribution in the running venv, plus ``python`` and ``gplugins``.

    The gplugins version is read from the source (``__version__`` in ``gplugins/__init__.py``),
    because v0.8.0 is on ``sys.path`` through a ``.pth`` file, not installed, and v1.4.2 cannot
    be imported.
    """
    out = {}
    for dist in importlib.metadata.distributions():
        name = re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower()
        out[name] = dist.version
    text = (Path(gplugins_root) / "gplugins" / "__init__.py").read_text(encoding="utf-8")
    out["gplugins"] = re.search(r'^__version__ = "([^"]+)"', text, re.MULTILINE).group(1)
    out["python"] = platform.python_version()
    return out


def contact_currents(device: str, contacts) -> dict[str, dict[str, float]]:
    """Electron, hole and total current of each contact (DEVSIM, A/cm in 2D)."""
    import devsim

    out = {}
    for contact in contacts:
        e = devsim.get_contact_current(
            device=device, contact=contact, equation="ElectronContinuityEquation"
        )
        h = devsim.get_contact_current(
            device=device, contact=contact, equation="HoleContinuityEquation"
        )
        out[contact] = {"electron": e, "hole": h, "total": e + h}
    return out


def depletion_width(x, y, n, p, net_doping, *, y_target: float):
    """``(width, y_cut, depleted_nodes)`` along the mesh row nearest ``y_target``.

    The row is the node y value closest to ``y_target`` (the smaller one on a tie). A node is
    depleted where both carrier densities are below 1e-2 |NetDoping|. The width is the span
    (max x - min x) of the depleted nodes of the row, in the units of ``x``; 0 if none.
    """
    y_cut = min(sorted(set(y)), key=lambda v: abs(v - y_target))
    row = sorted(
        {
            xi: (ni, pi, di) for xi, yi, ni, pi, di in zip(x, y, n, p, net_doping) if yi == y_cut
        }.items()
    )
    depleted = [xi for xi, (ni, pi, di) in row if ni < 1e-2 * abs(di) and pi < 1e-2 * abs(di)]
    width = max(depleted) - min(depleted) if depleted else 0.0
    return width, y_cut, len(depleted)


def write(path: Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
