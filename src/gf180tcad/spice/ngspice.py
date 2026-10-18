# SPDX-License-Identifier: Apache-2.0
"""Run ngspice in the sandbox and turn its raw file into result columns.

:func:`run_ngspice` writes the netlist to ``out_dir/ngspice.cir``, runs ``ngspice -b`` there in
the sandbox (log in ``out_dir/ngspice.log``, raw file :data:`~gf180tcad.spice.netlist.RAW_NAME`
written by the netlist's ``.control`` block) and parses the raw file.

Working directory: ngspice reads ``.spiceinit`` from its cwd, and it resolved the PDK lib's
nested relative ``.lib 'sm141064.spice' ...`` lines to a file in its cwd rather than the copy
next to the top-level lib (seen in the sandbox with patched scratch libs). So ``out_dir`` may
hold only this runner's own files (:data:`OWN_FILES`, replaced on each run), optional BSIM4
reports (:data:`OPTIONAL_FILES`, read into the warnings and deleted) and the entries the caller
names in ``inputs``; anything else refuses the run, and any other file written by ngspice fails
it (:func:`gf180tcad.spice.common.prepare_out_dir`). ngspice is killed after :data:`TIMEOUT_S`.

Failure policy (a non-converged or skipped point must fail the run, never shorten the data):
:class:`SpiceError` is raised for a non-zero exit, any log line containing "error", any
convergence trouble (:data:`FATAL_PATTERNS`, matched case-insensitively; a singular-matrix or
stepping-failure warning is fatal even when a later method succeeded), a missing or malformed
raw file, a timeout, a point count different from the plan, or bias values that differ from the
plan's grid by more than :data:`GRID_TOL` volts. Every other log line containing "warning", and
every recovery notice (a "...stepping..." line without "fail", "error", "converge", "abort" or
"singular"; or "Convergence reached"), is kept in :attr:`SpiceResult.warnings`.

The result is a :class:`SpiceResult`: a ``dict[str, np.ndarray]`` of columns that also carries
the kept warnings as ``.warnings``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from gf180tcad import sandbox
from gf180tcad.devices import Device, Geometry, Sweep
from gf180tcad.pdk import PdkInfo
from gf180tcad.spice import common
from gf180tcad.spice.common import GRID_TOL, LOG_TAIL_LINES, SpiceError, SpiceResult, Vectors
from gf180tcad.spice.netlist import NGSPICE_VECTORS, RAW_NAME, BiasPlan, bias_plan, ngspice_netlist
from gf180tcad.spice.rawfile import read_raw

__all__ = [
    "GRID_TOL",
    "LOG_TAIL_LINES",
    "SpiceError",
    "SpiceResult",
    "assemble",
    "run_ngspice",
    "scan_log",
    "simulate",
]

NETLIST_NAME = "ngspice.cir"
LOG_NAME = "ngspice.log"
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
TIMEOUT_S = 600  # a hung ngspice must end as a reported failure, not hold a slot forever
TIMEOUT_EXIT = 124  # coreutils timeout(1)
OWN_FILES = (NETLIST_NAME, LOG_NAME, RAW_NAME)
# ngspice's BSIM4 parameter check (checkModel) may write its warnings to bsim4v5.out,
# bsim4v6.out, bsim4v7.out or bsim4.out in the cwd (names from the ngspice 47 binary). Such a
# file is an expected optional output: its lines go into SpiceResult.warnings, prefixed with the
# file name, and it is deleted.
OPTIONAL_FILES = ("bsim4*.out",)


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


def assemble(
    plan: BiasPlan,
    raw: Mapping[str, np.ndarray],
    log: str = "",
    *,
    vectors: Vectors | None = None,
) -> dict[str, np.ndarray]:
    """Map raw vectors to result columns, check them against ``plan``, substitute the exact grid.

    ``vectors`` defaults to :data:`~gf180tcad.spice.netlist.NGSPICE_VECTORS` for the plan's
    kind. Bias columns are replaced by the plan's grid (bit-identical to the devices.py values
    with polarity applied) after checking ngspice's values agree within :data:`GRID_TOL`; see
    :func:`gf180tcad.spice.common.assemble`, which the Xyce runner shares.
    """
    if vectors is None:
        vectors = NGSPICE_VECTORS["cv" if plan.kind == "cv" else "dc"]
    return common.assemble(plan, raw, log, vectors=vectors)


def run_ngspice(
    netlist: str,
    out_dir: Path,
    *,
    plan: BiasPlan | None = None,
    image: str | None = None,
    inputs: Sequence[str] = (),
) -> SpiceResult:
    """Run ``netlist`` in the sandbox with ``out_dir`` as working directory.

    Without ``plan`` the raw vectors are returned as read; with ``plan`` they are checked and
    mapped to result columns by :func:`assemble`. ngspice's own exit code is checked too, but
    the sandbox's OOM error (:class:`~gf180tcad.sandbox.SandboxOOM`) is passed through.

    ``out_dir`` may hold only :data:`OWN_FILES` (replaced) and the entries named in ``inputs``
    (see :func:`gf180tcad.spice.common.prepare_out_dir`); ngspice is killed after
    :data:`TIMEOUT_S` seconds, which raises :class:`SpiceError`.
    """
    out_dir = Path(out_dir)
    common.prepare_out_dir(out_dir, OWN_FILES, inputs, optional=OPTIONAL_FILES)
    (out_dir / NETLIST_NAME).write_text(netlist, encoding="utf-8")
    cmd = ["sh", "-c", f"exec timeout {TIMEOUT_S} ngspice -b {NETLIST_NAME} > {LOG_NAME} 2>&1"]
    log_path = out_dir / LOG_NAME
    try:
        sandbox.run(cmd, out_dir=out_dir, mem=MEM, cpus=CPUS, pids=PIDS, image=image)
    except sandbox.SandboxOOM:
        raise
    except sandbox.SandboxError as e:
        log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        if e.result.returncode == TIMEOUT_EXIT:
            raise SpiceError(f"ngspice timed out after {TIMEOUT_S} s", log) from e
        scan_log(log)  # prefer the specific ngspice error, if the log has one
        raise SpiceError(f"ngspice exited with status {e.result.returncode}", log) from e
    log = log_path.read_text(encoding="utf-8", errors="replace")
    warnings = scan_log(log)
    warnings += common.check_out_dir(out_dir, OWN_FILES, inputs, log, optional=OPTIONAL_FILES)
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
