# SPDX-License-Identifier: Apache-2.0
"""The curve readers the explainer figures share with the results pages.

:mod:`gf180tcad.results_figures` calls these, so a results-page plot and an explainer figure read a
committed curve the same way and nothing is copied. Of the explain modules, this one alone reads
through :mod:`gf180tcad.tcad`, and only its two standard-library readers,
:mod:`gf180tcad.tcad.moscap1d` and :mod:`gf180tcad.tcad.process` (tested). It sits outside every
hashed generator closure (tested), so a change here restamps no committed result.

- :func:`spice_columns`: the columns of one committed SPICE sweep CSV;
- :func:`spice_cv`: a ``cv`` sweep's gate capacitance in fF against u = polarity × Vg;
- :func:`read_moscap`: a committed 1D C per area and the device's process description;
- :func:`tcad_cgg`: the gate capacitance of one geometry from a 1D C per area, with the fixed
  BSIM4 bookkeeping (:meth:`gf180tcad.tcad.moscap1d.MoscapCV.area_scaled`);
- :func:`u_sorted`: u = polarity × Vg ascending, with curves in the same order;
- :func:`two_d_cgg`: a committed 2D cell's total gate capacitance in fF against u.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from gf180tcad import io
from gf180tcad.tcad import moscap1d, process

#: fF per F: the SPICE ``cv`` sweep gives Cgg in F, the pages show fF.
FF_PER_F = 1e15


def u_sorted(vg, pol: int, *ys) -> list[np.ndarray]:
    """``u = polarity * vg`` ascending, and each of ``ys`` in the same order."""
    u = pol * np.asarray(vg, dtype=float)
    order = np.argsort(u, kind="stable")
    return [u[order], *(np.asarray(y, dtype=float)[order] for y in ys)]


def spice_columns(root: Path, engine: str, corner: str, device: str, gid: str, sweep: str) -> dict:
    """Columns of one committed CSV; FileNotFoundError if it is missing (never a silent gap)."""
    path = Path(root) / engine / corner / device / gid / f"{sweep}.csv"
    if not path.is_file():
        raise FileNotFoundError(f"missing result file {path}")
    return io.read_csv(path)[0]


def spice_cv(cols: dict, pol: int) -> tuple[np.ndarray, np.ndarray]:
    """``(u, cgg_ff)`` of a ``cv`` sweep's columns: u = polarity × Vg ascending, Cgg in fF."""
    order = np.argsort(pol * cols["vg"], kind="stable")
    return (pol * cols["vg"])[order], (cols["cgg"] * FF_PER_F)[order]


def read_moscap(tcad_root: Path, device: str, params: str):
    """``(MoscapCV, ProcessDescription)``: the committed 1D C per area of ``device`` at
    ``params`` under ``tcad_root`` and the device's process description."""
    m = moscap1d.read(Path(tcad_root) / "moscap1d" / device / params)
    return m, process.load(device)


def tcad_cgg(moscap, geometry, proc, pol: int) -> list[np.ndarray]:
    """``[u, intrinsic, parasitic, total]`` of one geometry (fF, u ascending) from a 1D C per
    area (a :class:`gf180tcad.tcad.moscap1d.MoscapCV`) and its process description."""
    vg, intrinsic, parasitic, total = moscap.area_scaled(geometry, proc)
    return u_sorted(vg, pol, intrinsic, parasitic, total)


def two_d_cgg(tcad_root: Path, device: str, params: str, gid: str, pol: int) -> list[np.ndarray]:
    """``[u, cgg_fF]`` of one committed 2D cell (``moscap2d/<device>/<params>/<gid>/cv.csv``):
    its ``cgg_total``, the 2D gate capacitance per unit width times the drawn width, with the
    cell's own fringe and overlap and no BSIM4 parasitics. FileNotFoundError if it is missing."""
    path = Path(tcad_root) / "moscap2d" / device / params / gid / "cv.csv"
    if not path.is_file():
        raise FileNotFoundError(f"missing result file {path}")
    cols = io.read_csv(path)[0]
    return u_sorted(cols["vg"], pol, cols["cgg_total"])
