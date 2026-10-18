# SPDX-License-Identifier: Apache-2.0
"""Xyce netlist and runner, and the ngspice-vs-Xyce cross-check :func:`engine_diff`.

The Xyce netlist has the same topology, signs, bias plan and instance parameters as
:func:`~gf180tcad.spice.netlist.ngspice_netlist`; its result columns (``vd vg vb id ig ib``,
currents INTO the device terminals) go through the same :func:`gf180tcad.spice.common.assemble`
grid check and exact-grid substitution, so ngspice and Xyce results share bias columns bit for
bit. Differences from the ngspice netlist, each forced by Xyce 7.10 or the image's Xyce lib:

- **Subcircuit name.** The image's ``libs.tech/xyce/sm141064.xyce`` has no ``nfet_05v0`` /
  ``pfet_05v0`` wrappers. In the ngspice lib those wrappers instantiate the ``nfet_06v0`` /
  ``pfet_06v0`` model cards and are line-for-line the ``nfet_06v0`` / ``pfet_06v0`` wrappers
  (only the subcircuit's default ``w``/``l`` differ, and every instance passes ``w`` and ``l``),
  so Xyce uses the ``*_06v0`` wrapper (:data:`XYCE_SUBCKT`). The sandbox test
  ``test_xyce_lib_matches_ngspice_lib_structure`` re-checks this against the image.
- **Temperature.** Xyce ignores ``.temp`` ("Unrecognized dot line will be ignored") and would
  run at 27 °C; ``.options device temp=<T>`` is used instead.
- **Output.** ``.print dc format=csv precision=17`` writes :data:`CSV_NAME`; columns are read by
  header name (:func:`read_print_csv`), never by position. 17 significant digits make the bias
  values round-trip, so the 1e-9 V grid check is meaningful.
- **cv** is not implemented for Xyce (out of scope): :func:`xyce_netlist` raises
  NotImplementedError.

The working directory is guarded exactly as for ngspice: only :data:`OWN_FILES` and the
caller's named ``inputs`` may be in it (:func:`gf180tcad.spice.common.prepare_out_dir`).

Xyce always runs as a single process (plain ``Xyce``, never ``mpirun``) and :func:`run_xyce`
requires the log's "Timing summary of 1 processor" line.

Failure policy (:func:`scan_xyce_log`): :class:`XyceError` (a
:class:`~gf180tcad.spice.common.SpiceError`) for a non-zero exit, a timeout, any message
matching :data:`FATAL_PATTERNS` (errors, aborts, failed steps, convergence or step-size
failures, singular matrices, nodes without a DC path, ignored netlist lines), any non-zero
"Number ... Fail..." counter in the solution summary, a processor count other than 1, a missing
or malformed CSV, a point count different from the plan, or bias values off the plan's grid.
Every other warning message is kept, joined into one line, in :attr:`SpiceResult.warnings`.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from gf180tcad import sandbox
from gf180tcad.devices import CORNERS, Device, Geometry, Sweep, geometry_id
from gf180tcad.pdk import PdkInfo
from gf180tcad.spice import common
from gf180tcad.spice.common import SpiceError, SpiceResult
from gf180tcad.spice.netlist import (
    _MODEL_RE,
    _TERMINALS,
    BiasPlan,
    _dc_range,
    bias_plan,
    instance_params,
)

NETLIST_NAME = "xyce.cir"
LOG_NAME = "xyce.log"
CSV_NAME = "out.csv"
TIMEOUT_S = 600  # a hung Xyce (seen with a pathological diode) must not hold a slot forever
TIMEOUT_EXIT = 124  # coreutils timeout(1)
OWN_FILES = (NETLIST_NAME, LOG_NAME, CSV_NAME)

# Xyce lib wrapper used for each device model (see the module docstring).
XYCE_SUBCKT: dict[str, str] = {"nfet_05v0": "nfet_06v0", "pfet_05v0": "pfet_06v0"}

# result column -> (CSV header, factor); I(Vx) is the branch current into the source's + node
# (as in ngspice), so the current INTO the device terminal is -I(Vx).
XYCE_VECTORS: dict[str, tuple[str, float]] = {
    "vd": ("V(D)", 1.0),
    "vg": ("V(G)", 1.0),
    "vb": ("V(B)", 1.0),
    "id": ("I(VD)", -1.0),
    "ig": ("I(VG)", -1.0),
    "ib": ("I(VB)", -1.0),
}

FATAL_PATTERNS = (
    "error",
    "abort",  # "Simulation aborted due to error", "*** Xyce Abort ***", MPI_ABORT
    "fail",  # "DC Operating Point Failed", "Failed DC sweep steps", "... failed to converge"
    "converge",
    "time step too small",
    "timestep too small",
    "minimum step size",  # "Step size reached minimum step size bound"
    "singular",  # "Numerically singular matrix found by Amesos"
    "dc path to ground",  # "Voltage Node (X) does not have a DC path to ground"
    "unrecognized",  # "Unrecognized dot line will be ignored" (e.g. .temp)
)
_COUNTER_RE = re.compile(r"^\s*Number ([^:]+):\s*(\d+)\s*$")
_PROCS_RE = re.compile(r"^Timing summary of (\d+) processors?\s*$", re.MULTILINE)

# One Xyce job: serial, a few tens of MB of RSS in practice.
MEM, CPUS, PIDS = "4g", 1, 256


class XyceError(SpiceError):
    """Xyce failed, reported a convergence problem, or produced unexpected data."""

    engine = "Xyce"


def xyce_netlist(
    device: Device, g: Geometry, sweep: Sweep, corner: str, temp_c: float, pdk: PdkInfo
) -> str:
    """Return the Xyce netlist text (see the module docstring for conventions)."""
    if corner not in CORNERS:
        raise ValueError(f"corner must be one of {CORNERS}, got {corner!r}")
    if not math.isfinite(temp_c):
        raise ValueError(f"temp_c must be finite, got {temp_c!r}")
    if not _MODEL_RE.fullmatch(device.spice_model):
        raise ValueError(f"bad spice model name {device.spice_model!r}")
    if sweep.kind == "cv":
        raise NotImplementedError(
            f"cv sweep {sweep.name!r}: C-V is not implemented for Xyce (only idvg and idvd are "
            "cross-checked against ngspice)"
        )
    plan = bias_plan(device, sweep)
    start = {**dict(plan.fixed), plan.inner.terminal: plan.inner.values[0]}
    if plan.outer is not None:
        start[plan.outer.terminal] = plan.outer.values[0]
    subckt = XYCE_SUBCKT.get(device.spice_model, device.spice_model)
    params = " ".join(f"{k}={v}" for k, v in instance_params(device, g).items())
    dc = _dc_range(plan.inner)
    if plan.outer is not None:
        dc += " " + _dc_range(plan.outer)  # Xyce, like SPICE: the first sweep is the inner loop
    printed = " ".join(name.lower() for name, _ in XYCE_VECTORS.values())
    lines = [
        (
            f"* gf180tcad Xyce {device.name} {geometry_id(g)} {sweep.name} "
            f"corner={corner} temp_c={float(temp_c)!r}"
        ),
        f".include {pdk.xyce_design}",
        f".lib {pdk.xyce_lib} {corner}",
        f".options device temp={float(temp_c)!r}",
        *(f"v{t} {t} 0 dc {start[t]!r}" for t in _TERMINALS),
        f"xdut d g 0 b {subckt} {params}",
        f".dc {dc}",
        f".print dc format=csv precision=17 file={CSV_NAME} {printed}",
        ".end",
    ]
    return "\n".join(lines) + "\n"


def read_print_csv(path: Path) -> dict[str, np.ndarray]:
    """Parse a ``.print ... format=csv`` file into columns keyed by upper-cased header name."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].strip():
        raise XyceError(f"{path.name}: empty CSV output")
    header = [h.strip().upper() for h in lines[0].split(",")]
    if len(set(header)) != len(header):
        raise XyceError(f"{path.name}: duplicate column in header {header}")
    rows = []
    for n, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        fields = line.split(",")
        try:
            values = [float(f) for f in fields]
        except ValueError:
            values = []
        if len(values) != len(header) or not all(math.isfinite(v) for v in values):
            raise XyceError(f"{path.name} line {n}: bad row {line!r} for header {header}")
        rows.append(values)
    if not rows:
        raise XyceError(f"{path.name}: no data rows")
    data = np.array(rows, dtype=np.float64)
    return {h: data[:, i].copy() for i, h in enumerate(header)}


def _messages(log: str) -> list[str]:
    """Xyce log lines, with a message's wrapped continuation lines (leading space) joined."""
    out: list[str] = []
    joining = False
    for line in log.splitlines():
        if joining and line.startswith(" ") and line.strip():
            out[-1] += " " + line.strip()
            continue
        out.append(line.strip())
        low = line.lower()
        joining = bool(line.strip()) and ("warning" in low or "error" in low or "abort" in low)
    return out


def scan_xyce_log(log: str) -> list[str]:
    """Raise :class:`XyceError` on a fatal message; return the other warnings, in order."""
    warnings = []
    for msg in _messages(log):
        counter = _COUNTER_RE.match(msg)
        if counter:
            name, count = counter.group(1).strip(), int(counter.group(2))
            if "fail" in name.lower() and count > 0:
                raise XyceError(f"Xyce reported {name}: {count}", log)
            continue
        low = msg.lower()
        hit = next((p for p in FATAL_PATTERNS if p in low), None)
        if hit is not None:
            raise XyceError(f"Xyce reported {hit!r}: {msg}", log)
        if "warning" in low:
            warnings.append(msg)
    return warnings


def processor_count(log: str) -> int:
    """The N of Xyce's final "Timing summary of N processor(s)" line (exactly one such line)."""
    found = _PROCS_RE.findall(log)
    if len(found) != 1:
        raise XyceError(f"expected one 'Timing summary of N processor' line, found {found}", log)
    return int(found[0])


def run_xyce(
    netlist: str,
    out_dir: Path,
    *,
    plan: BiasPlan | None = None,
    image: str | None = None,
    inputs: Sequence[str] = (),
) -> SpiceResult:
    """Run ``netlist`` with serial Xyce in the sandbox, ``out_dir`` as working directory.

    Without ``plan`` the CSV columns are returned as read (keyed by header); with ``plan`` they
    are checked and mapped to result columns by :func:`gf180tcad.spice.common.assemble`.
    ``out_dir`` may hold only :data:`OWN_FILES` (replaced) and the entries named in ``inputs``
    (see :func:`gf180tcad.spice.common.prepare_out_dir`).
    """
    out_dir = Path(out_dir)
    common.prepare_out_dir(out_dir, OWN_FILES, inputs, error=XyceError)
    (out_dir / NETLIST_NAME).write_text(netlist, encoding="utf-8")
    cmd = ["sh", "-c", f"exec timeout {TIMEOUT_S} Xyce {NETLIST_NAME} > {LOG_NAME} 2>&1"]
    log_path = out_dir / LOG_NAME
    try:
        sandbox.run(cmd, out_dir=out_dir, mem=MEM, cpus=CPUS, pids=PIDS, image=image)
    except sandbox.SandboxOOM:
        raise
    except sandbox.SandboxError as e:
        log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        if e.result.returncode == TIMEOUT_EXIT:
            raise XyceError(f"Xyce timed out after {TIMEOUT_S} s", log) from e
        scan_xyce_log(log)  # prefer the specific Xyce message, if the log has one
        raise XyceError(f"Xyce exited with status {e.result.returncode}", log) from e
    log = log_path.read_text(encoding="utf-8", errors="replace")
    warnings = scan_xyce_log(log)
    warnings += common.check_out_dir(out_dir, OWN_FILES, inputs, log, error=XyceError)
    nproc = processor_count(log)
    if nproc != 1:
        raise XyceError(f"Xyce ran on {nproc} processors, expected exactly 1", log)
    csv_path = out_dir / CSV_NAME
    if not csv_path.is_file():
        raise XyceError(f"Xyce wrote no CSV file {CSV_NAME}", log)
    try:
        raw = read_print_csv(csv_path)
    except XyceError as e:
        raise XyceError(str(e).split("\n", 1)[0], log) from e
    if plan is None:
        return SpiceResult(raw, warnings)
    cols = common.assemble(plan, raw, log, vectors=XYCE_VECTORS, error=XyceError)
    return SpiceResult(cols, warnings)


def simulate_xyce(
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
    """Netlist, run and check one device / geometry / sweep / corner / temperature in Xyce."""
    text = xyce_netlist(device, g, sweep, corner, temp_c, pdk)
    return run_xyce(text, out_dir, plan=bias_plan(device, sweep), image=image)


ENGINE_DIFF_FLOOR = 1e-12  # A
BIAS_COLUMNS = ("vd", "vg", "vb")


def engine_diff(a: Mapping[str, np.ndarray], b: Mapping[str, np.ndarray], key: str = "id") -> float:
    """Maximum relative difference of column ``key`` between two engines' results.

    Per point, ``|a - b| / max(|a|, |b|)``; the maximum is taken over the points where
    ``max(|a|, |b|) > 1e-12`` A (:data:`ENGINE_DIFF_FLOOR`), i.e. above the floor in EITHER
    engine; 0.0 if there is no such point. The symmetric ``max`` denominator makes the result
    independent of argument order and bounded by 2 (reached for equal magnitudes, opposite signs).

    Both results must have exactly equal bias columns ``vd``, ``vg``, ``vb`` (both engines
    substitute the exact plan grid, so any difference means two different sweeps are being
    compared): ValueError otherwise, and also for a non-finite value in ``key``.
    """
    for col in (*BIAS_COLUMNS, key):
        for name, res in (("a", a), ("b", b)):
            if col not in res:
                raise ValueError(f"result {name} has no column {col!r}")
        if np.shape(a[col]) != np.shape(b[col]):
            raise ValueError(f"{col}: shape {np.shape(a[col])} != {np.shape(b[col])}")
    for col in BIAS_COLUMNS:
        if not np.array_equal(a[col], b[col]):
            raise ValueError(f"bias column {col!r} differs between the two results")
    x = np.asarray(a[key], dtype=np.float64)
    y = np.asarray(b[key], dtype=np.float64)
    if not (np.all(np.isfinite(x)) and np.all(np.isfinite(y))):
        raise ValueError(f"{key}: non-finite values, cannot compare")
    den = np.maximum(np.abs(x), np.abs(y))
    mask = den > ENGINE_DIFF_FLOOR
    if not np.any(mask):
        return 0.0
    return float(np.max(np.abs(x[mask] - y[mask]) / den[mask]))
