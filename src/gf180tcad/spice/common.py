# SPDX-License-Identifier: Apache-2.0
"""Engine-agnostic pieces of the SPICE runners (ngspice and Xyce).

- :class:`SpiceError`: a simulator failed, reported a convergence problem or produced unexpected
  data. Subclasses only change the engine name shown in the message.
- :class:`SpiceResult`: a ``dict[str, np.ndarray]`` of result columns plus the kept ``warnings``.
- :func:`prepare_out_dir` / :func:`check_out_dir`: the working-directory guard. A simulator's
  working directory may hold only that runner's own files (netlist, log, data file) and the
  extra inputs the caller names explicitly. Anything else (a ``.spiceinit``, a stray
  ``sm141064.spice`` that ngspice's nested ``.lib`` lookup could pick up instead of the PDK's,
  any other file or directory) makes the run refuse to start, and a file the simulator itself
  writes beyond its own outputs (e.g. ngspice's ``bsim4v5.out`` parameter-check report) fails it.
- :func:`assemble`: map an engine's output vectors to result columns, check the point count and
  the bias values against the :class:`~gf180tcad.spice.netlist.BiasPlan` grid (within
  :data:`GRID_TOL`), and substitute the exact grid. Both engines go through this one function, so
  their results share bias columns bit for bit.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import numpy as np

from gf180tcad.spice.netlist import BiasPlan

LOG_TAIL_LINES = 40
GRID_TOL = 1e-9  # V; ngspice's .dc accumulates the step, ~1e-13 V off after 500 steps

# result column -> (engine vector name, factor applied to it)
Vectors = Mapping[str, tuple[str, float]]


def _tail(log: str) -> str:
    return "\n".join(log.rstrip("\n").splitlines()[-LOG_TAIL_LINES:])


class SpiceError(RuntimeError):
    """A simulator failed, reported a convergence problem, or produced unexpected data."""

    engine = "ngspice"

    def __init__(self, message: str, log: str = ""):
        self.log_tail = _tail(log)
        super().__init__(
            f"{message}\n--- {self.engine} log (last {LOG_TAIL_LINES} lines) ---\n{self.log_tail}"
        )


class SpiceResult(dict):
    """Result columns (``dict[str, np.ndarray]``) plus the simulator's non-fatal ``warnings``."""

    def __init__(self, columns: Mapping[str, np.ndarray], warnings: Iterable[str] = ()):
        super().__init__(columns)
        self.warnings: tuple[str, ...] = tuple(warnings)


def _foreign(out_dir: Path, own: Iterable[str], inputs: Iterable[str]) -> list[str]:
    allowed = set(own) | set(inputs)
    return sorted(p.name for p in out_dir.iterdir() if p.name not in allowed)


def prepare_out_dir(
    out_dir: Path,
    own: Iterable[str],
    inputs: Iterable[str] = (),
    *,
    error: type[SpiceError] = SpiceError,
) -> None:
    """Refuse foreign entries in ``out_dir``; delete the runner's ``own`` files from a past run.

    ``inputs`` names extra top-level entries (files or directories) the caller placed there on
    purpose, e.g. a patched model library in a subdirectory; they must not be ``own`` names.
    Foreign entries are never deleted.
    """
    own, inputs = tuple(own), tuple(inputs)
    clash = sorted(set(own) & set(inputs))
    if clash:
        raise ValueError(f"inputs {clash} are the runner's own output names")
    foreign = _foreign(out_dir, own, inputs)
    if foreign:
        raise error(
            f"{out_dir} holds files this {error.engine} run did not write: {foreign}. A model "
            "or init file there (e.g. .spiceinit, *.spice, *.lib) could be read instead of the "
            "PDK's; use an empty directory or name deliberate inputs explicitly"
        )
    for name in own:
        (out_dir / name).unlink(missing_ok=True)  # never parse a previous run's output


def check_out_dir(
    out_dir: Path,
    own: Iterable[str],
    inputs: Iterable[str] = (),
    log: str = "",
    *,
    error: type[SpiceError] = SpiceError,
) -> None:
    """After a run: fail if the simulator wrote any entry other than ``own`` (and ``inputs``)."""
    extra = _foreign(out_dir, own, inputs)
    if extra:
        raise error(f"{error.engine} wrote unexpected files in {out_dir}: {extra}", log)


def assemble(
    plan: BiasPlan,
    raw: Mapping[str, np.ndarray],
    log: str = "",
    *,
    vectors: Vectors,
    error: type[SpiceError] = SpiceError,
) -> dict[str, np.ndarray]:
    """Map ``raw`` vectors to result columns, check them against ``plan``, substitute the grid.

    ``vectors`` maps each result column to ``(raw vector name, factor)``. Bias columns are
    replaced by the plan's grid (bit-identical to the devices.py values with polarity applied)
    after checking the simulator's values agree within :data:`GRID_TOL`. Failures raise
    ``error`` (a :class:`SpiceError`).
    """
    grid = plan.grid()
    out: dict[str, np.ndarray] = {}
    for col, (name, factor) in vectors.items():
        if name not in raw:
            raise error(f"raw file has no vector {name!r} (has {sorted(raw)})", log)
        v = raw[name]
        if np.iscomplexobj(v):
            raise error(f"raw vector {name!r} is complex, expected real", log)
        if v.shape != (plan.npoints,):
            raise error(
                f"expected {plan.npoints} points, raw vector {name!r} has {v.shape[0]}", log
            )
        # "+ 0.0" turns -0.0 into 0.0 (e.g. a zero gate current negated)
        v = factor * np.asarray(v, dtype=np.float64) + 0.0
        if col in grid:
            err = float(np.max(np.abs(v - grid[col])))
            if not err <= GRID_TOL:
                raise error(
                    f"{col}: {error.engine} bias values differ from the sweep grid by up to "
                    f"{err!r} V (> {GRID_TOL} V)",
                    log,
                )
            v = grid[col].copy()
        out[col] = v
    return out
