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
CHECKS = ("import", "pin_test", "ddcomponent_mesh", "ddsolver", "ramp", "refine", "refined_solve")

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


def contact_potential(device: str, contact: str, regions) -> float:
    """Mean ``Potential`` (V) over the nodes of ``contact``, found in whichever of ``regions``."""
    import devsim

    for region in regions:
        try:
            elements = devsim.get_element_node_list(device=device, region=region, contact=contact)
        except devsim.error:
            continue
        if not elements:
            continue
        nodes = sorted({i for element in elements for i in element})
        pot = devsim.get_node_model_values(device=device, region=region, name="Potential")
        return sum(pot[i] for i in nodes) / len(nodes)
    raise ValueError(f"contact {contact!r} has no nodes in regions {list(regions)}")


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


def msh2_physical_names(path: Path) -> list[str]:
    """The sorted names of the ``$PhysicalNames`` section of a gmsh MSH 2.2 file."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    start = lines.index("$PhysicalNames")
    count = int(lines[start + 1])
    names = [line.split(maxsplit=2)[2].strip('"') for line in lines[start + 2 : start + 2 + count]]
    if lines[start + 2 + count] != "$EndPhysicalNames":
        raise ValueError(f"{path}: malformed $PhysicalNames section")
    return sorted(names)


def junction_probe(rows, *, rib: str, slab: str, offset_um: float) -> dict:
    """The Potential across the junction on the bottom mesh row (the node y nearest 0).

    ``rows`` maps a silicon region to its nodes ``(x, y, Potential, NetDoping)``, x and y in cm
    (DEVSIM). The definitions are those of the junction probe ``_junction`` of the
    ``mithro/gplugins`` fork's ``gplugins/devsim/tests/test_mesh.py``:

    - ``x_um``: the metallurgical junction, midway between the last NetDoping > 0 and the first
      NetDoping < 0 node of the row;
    - ``junction_v``, ``n_v``, ``p_v``: the Potential at the row node nearest ``x_um``,
      ``x_um - offset_um`` (neutral n side) and ``x_um + offset_um`` (neutral p side); a tie
      goes to the smaller x, then to the region name;
    - ``drop_v = n_v - p_v``: the junction's potential drop;
    - ``boundary_jump_v``: the larger Potential difference between the ``rib`` and ``slab``
      nodes nearest the rib's two bottom corners (its first and last bottom-row node), 0 if the
      two regions are coupled.
    """
    y_cut = min(sorted({yi for nodes in rows.values() for _, yi, _, _ in nodes}), key=abs)
    bottom = {
        r: sorted((xi * 1e4, r, pi, di) for xi, yi, pi, di in nodes if yi == y_cut)
        for r, nodes in rows.items()
    }
    row = sorted(t for nodes in bottom.values() for t in nodes)
    xj = 0.5 * (max(x for x, _, _, d in row if d > 0) + min(x for x, _, _, d in row if d < 0))

    def at(x0, nodes=row):
        return min(nodes, key=lambda t: (abs(t[0] - x0), t[1]))[2]

    corners = (bottom[rib][0][0], bottom[rib][-1][0])
    jump = max(abs(at(x0, bottom[rib]) - at(x0, bottom[slab])) for x0 in corners)
    n_v, p_v = at(xj - offset_um), at(xj + offset_um)
    return {
        "x_um": xj,
        "junction_v": at(xj),
        "n_v": n_v,
        "p_v": p_v,
        "drop_v": n_v - p_v,
        "boundary_jump_v": jump,
    }


def write(path: Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
