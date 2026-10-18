# SPDX-License-Identifier: Apache-2.0
"""Run ngspice in the sandbox and turn its raw file into result columns.

:func:`run_ngspice` writes the netlist to ``out_dir/ngspice.cir``, runs ``ngspice -b`` there in
the sandbox (log in ``out_dir/ngspice.log``, raw file :data:`~gf180tcad.spice.netlist.RAW_NAME`
written by the netlist's ``.control`` block) and parses the raw file.

Failure policy (a non-converged or skipped point must fail the run, never shorten the data):
:class:`SpiceError` is raised for a non-zero exit, any log line containing "error", any
convergence trouble (:data:`FATAL_PATTERNS`, matched case-insensitively; a singular-matrix or
stepping-failure warning is fatal even when a later method succeeded), a missing or malformed
raw file, a point count different from the plan, or bias values that differ from the plan's
grid by more than :data:`GRID_TOL` volts. Every other log line containing "warning", and every
recovery notice (a "...stepping..." line without "fail", "error", "converge", "abort" or
"singular"; or "Convergence reached"), is kept in :attr:`SpiceResult.warnings`.

The result is a :class:`SpiceResult`: a ``dict[str, np.ndarray]`` of columns that also carries
the kept warnings as ``.warnings``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import numpy as np

from gf180tcad import sandbox
from gf180tcad.devices import Device, Geometry, Sweep
from gf180tcad.pdk import PdkInfo
from gf180tcad.spice.netlist import NGSPICE_VECTORS, RAW_NAME, BiasPlan, bias_plan, ngspice_netlist
from gf180tcad.spice.rawfile import read_raw

NETLIST_NAME = "ngspice.cir"
LOG_NAME = "ngspice.log"
LOG_TAIL_LINES = 40
GRID_TOL = 1e-9  # V; ngspice's .dc accumulates the step, ~1e-13 V off after 500 steps
FATAL_PATTERNS = (
    "error",
    "timestep too small",
    "singular matrix",
    "gmin stepping failed",
    "source stepping failed",
    "converge",  # "Too many iterations without convergence", "did not converge", ...
    "iteration limit",
    "abort",  # "simulation(s) aborted", "... stepping aborted"
)
# A "...stepping..." line without "fail" is ngspice reporting that it recovered (e.g. "Note:
# Starting dynamic gmin stepping", "Note: Source stepping completed"); "Convergence reached" ends
# a successful PSS. These notices are kept in SpiceResult.warnings, never fatal and never dropped.
BENIGN_PREFIXES = ("convergence reached",)

# Sandbox limits for one ngspice job: single-threaded, a few MB of RSS in practice.
MEM, CPUS, PIDS = "4g", 1, 256


def _tail(log: str) -> str:
    return "\n".join(log.rstrip("\n").splitlines()[-LOG_TAIL_LINES:])


class SpiceError(RuntimeError):
    """ngspice failed, reported a convergence problem, or produced unexpected data."""

    def __init__(self, message: str, log: str = ""):
        self.log_tail = _tail(log)
        super().__init__(
            f"{message}\n--- ngspice log (last {LOG_TAIL_LINES} lines) ---\n{self.log_tail}"
        )


class SpiceResult(dict):
    """Result columns (``dict[str, np.ndarray]``) plus the non-fatal ngspice ``warnings``."""

    def __init__(self, columns: Mapping[str, np.ndarray], warnings: Iterable[str] = ()):
        super().__init__(columns)
        self.warnings: tuple[str, ...] = tuple(warnings)


def scan_log(log: str) -> list[str]:
    """Raise :class:`SpiceError` on a fatal line; return the other warning lines, in order."""
    warnings = []
    for line in log.splitlines():
        low = line.strip().lower()
        if _is_recovery_notice(low):
            warnings.append(line.strip())
            continue
        hit = next((p for p in FATAL_PATTERNS if p in low), None)
        if hit is None and "stepping" in low:
            hit = "stepping"  # a stepping line that is not a recovery notice is never dropped
        if hit is not None:
            raise SpiceError(f"ngspice reported {hit!r}: {line.strip()}", log)
        if "warning" in low:
            warnings.append(line.strip())
    return warnings


def _is_recovery_notice(low: str) -> bool:
    if low.startswith(BENIGN_PREFIXES):
        return True
    # "converge" also covers "convergence"; any of these words means a failure, not a recovery
    if any(w in low for w in ("fail", "error", "converge", "abort", "singular")):
        return False
    return "stepping" in low


def assemble(plan: BiasPlan, raw: Mapping[str, np.ndarray], log: str = "") -> dict[str, np.ndarray]:
    """Map raw vectors to result columns, check them against ``plan``, substitute the exact grid.

    Bias columns are replaced by the plan's grid (bit-identical to the devices.py values with
    polarity applied) after checking ngspice's values agree within :data:`GRID_TOL`.
    """
    vectors = NGSPICE_VECTORS["cv" if plan.kind == "cv" else "dc"]
    grid = plan.grid()
    out: dict[str, np.ndarray] = {}
    for col, (name, factor) in vectors.items():
        if name not in raw:
            raise SpiceError(f"raw file has no vector {name!r} (has {sorted(raw)})", log)
        v = raw[name]
        if np.iscomplexobj(v):
            raise SpiceError(f"raw vector {name!r} is complex, expected real", log)
        if v.shape != (plan.npoints,):
            raise SpiceError(
                f"expected {plan.npoints} points, raw vector {name!r} has {v.shape[0]}", log
            )
        # "+ 0.0" turns -0.0 into 0.0 (e.g. a zero gate current negated)
        v = factor * np.asarray(v, dtype=np.float64) + 0.0
        if col in grid:
            err = float(np.max(np.abs(v - grid[col])))
            if not err <= GRID_TOL:
                raise SpiceError(
                    f"{col}: ngspice bias values differ from the sweep grid by up to {err!r} V "
                    f"(> {GRID_TOL} V)",
                    log,
                )
            v = grid[col].copy()
        out[col] = v
    return out


def run_ngspice(
    netlist: str, out_dir: Path, *, plan: BiasPlan | None = None, image: str | None = None
) -> SpiceResult:
    """Run ``netlist`` in the sandbox with ``out_dir`` as working directory.

    Without ``plan`` the raw vectors are returned as read; with ``plan`` they are checked and
    mapped to result columns by :func:`assemble`. ngspice's own exit code is checked too, but
    the sandbox's OOM error (:class:`~gf180tcad.sandbox.SandboxOOM`) is passed through.
    """
    out_dir = Path(out_dir)
    if (out_dir / ".spiceinit").exists():
        raise SpiceError(f"{out_dir}/.spiceinit exists; ngspice would read it from its cwd")
    for name in (RAW_NAME, LOG_NAME):
        (out_dir / name).unlink(missing_ok=True)  # never parse a previous run's output
    (out_dir / NETLIST_NAME).write_text(netlist, encoding="utf-8")
    cmd = ["sh", "-c", f"exec ngspice -b {NETLIST_NAME} > {LOG_NAME} 2>&1"]
    log_path = out_dir / LOG_NAME
    try:
        sandbox.run(cmd, out_dir=out_dir, mem=MEM, cpus=CPUS, pids=PIDS, image=image)
    except sandbox.SandboxOOM:
        raise
    except sandbox.SandboxError as e:
        log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        scan_log(log)  # prefer the specific ngspice error, if the log has one
        raise SpiceError(f"ngspice exited with status {e.result.returncode}", log) from e
    log = log_path.read_text(encoding="utf-8", errors="replace")
    warnings = scan_log(log)
    raw_path = out_dir / RAW_NAME
    if not raw_path.is_file():
        raise SpiceError(f"ngspice wrote no raw file {RAW_NAME}", log)
    try:
        raw = read_raw(raw_path)
    except ValueError as e:
        raise SpiceError(f"bad raw file: {e}", log) from e
    if plan is None:
        return SpiceResult(raw, warnings)
    return SpiceResult(assemble(plan, raw, log), warnings)


def simulate(
    device: Device,
    g: Geometry,
    sweep: Sweep,
    corner: str,
    temp_c: float,
    pdk: PdkInfo,
    out_dir: Path,
    *,
    image: str | None = None,
) -> SpiceResult:
    """Netlist, run and check one device / geometry / sweep / corner / temperature."""
    text = ngspice_netlist(device, g, sweep, corner, temp_c, pdk)
    return run_ngspice(text, out_dir, plan=bias_plan(device, sweep), image=image)
