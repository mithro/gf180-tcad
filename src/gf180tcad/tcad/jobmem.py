# SPDX-License-Identifier: Apache-2.0
"""Memory of a long 2D sweep job: per-point readings, heap trimming and a restart budget.

The QS sweep of the nfet L = 2 um cell (512,591 nodes) grows glibc's main heap (the ``[heap]``
mapping) by 0.19 GiB per bias point (points 132 to 148 of the calibrated E3b run) until the
16 GiB container limit kills it. The same sweep on the source/drain cell at 115,689 nodes holds
steady (`issue #233 <https://github.com/mithro/gf180-tcad/issues/233>`_). :func:`after_point`
runs after each saved point (:func:`gf180tcad.tcad.moscap2d.simulate` with ``state_dir``):

- it hands the heap's free pages back with glibc's ``malloc_trim(0)`` and reports how much that
  freed, which tells heap fragmentation (freed) from memory still in use (not freed);
- it reports the resident memory (VmRSS) and the container's memory limit;
- once the resident memory passes :data:`~gf180tcad.tcad.jobmem.BUDGET_FRACTION` of the
  limit, and has grown by :data:`~gf180tcad.tcad.jobmem.GROWTH_FRACTION` of the limit since
  this process's first point, it raises :class:`BudgetReached`, and the job restarts itself
  in a fresh process (:func:`gf180tcad.tcad.__main__.run_job_2d`), which resumes at the next
  point.

The point is saved before the check, so a restart repeats no work but the mesh and equilibrium.
The growth condition keeps a job whose memory is high from the start (a large mesh) from
restarting after every point: a restart only helps where the memory grew.

The readings are Linux ones (``/proc/self/status``, the cgroup files). Where they are missing,
:func:`after_point` logs that and never raises.
"""

from __future__ import annotations

import ctypes
import functools
from pathlib import Path

#: Restart once the resident memory passes this fraction of the container's memory limit. A
#: 16 GiB job then restarts near 12 GiB, which leaves room for one more point's growth and the
#: solver's transient memory. The resident memory is the process's VmRSS, not the container's
#: ``memory.current``: the latter also counts reclaimable page cache (the mesh and state files),
#: which the kernel frees before an out-of-memory kill. The sweep process holds nearly all of
#: the rest.
BUDGET_FRACTION = 0.75
#: Restart only when the resident memory has grown by this fraction of the limit since the
#: process's first point.
GROWTH_FRACTION = 0.2

# The resident memory after the first point this process ran (set by after_point).
_first_rss: int | None = None

_MIB = 1024 * 1024

#: The cgroup v2 and v1 files that hold the memory limit of the container the job runs in.
CGROUP_LIMIT_FILES = (
    Path("/sys/fs/cgroup/memory.max"),
    Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
)
#: The file whose ``VmRSS`` line is the process's resident memory.
STATUS_FILE = Path("/proc/self/status")

# A cgroup v1 "no limit" reads as a huge number (PAGE_COUNTER_MAX pages); treat anything above
# this as no limit.
_NO_LIMIT_ABOVE = 1 << 60


class BudgetReached(RuntimeError):
    """The job's resident memory passed the budget after a saved point; restart to go on."""

    def __init__(self, index: int, rss: int, limit: int) -> None:
        super().__init__(
            f"resident memory {rss // _MIB} MiB after point {index + 1} is above "
            f"{BUDGET_FRACTION:g} of the {limit // _MIB} MiB limit"
        )
        self.index = index


def rss_bytes(status: Path = STATUS_FILE) -> int | None:
    """The process's resident memory (VmRSS) in bytes, or None where ``status`` is missing."""
    try:
        text = status.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            value, unit = line.split()[1:3]
            if unit != "kB":
                raise ValueError(f"unexpected VmRSS unit {unit!r} in {status}")
            return int(value) * 1024
    raise ValueError(f"no VmRSS line in {status}")


def limit_bytes(files: tuple[Path, ...] = CGROUP_LIMIT_FILES) -> int | None:
    """The container's memory limit in bytes, or None where there is none (or no cgroup file)."""
    for path in files:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue
        if text == "max":
            return None
        value = int(text)
        return None if value > _NO_LIMIT_ABOVE else value
    return None


@functools.cache
def _malloc_trim():
    """glibc's ``malloc_trim`` from the loaded C library, or None where there is none (not
    glibc); looked up once per process."""
    fn = getattr(ctypes.CDLL(None), "malloc_trim", None)
    if fn is not None:
        fn.argtypes = [ctypes.c_size_t]
        fn.restype = ctypes.c_int
    return fn


def trim() -> int | None:
    """Hand the heap's free pages back (``malloc_trim(0)``); returns the resident bytes freed,
    or None where there is no ``malloc_trim`` or no resident memory reading."""
    fn = _malloc_trim()
    before = rss_bytes()
    if fn is None or before is None:
        return None
    fn(0)
    return max(before - rss_bytes(), 0)


def over_budget(rss: int, first_rss: int, limit: int | None) -> bool:
    """Whether a job at resident memory ``rss`` (``first_rss`` after its first point) should
    restart: above :data:`~gf180tcad.tcad.jobmem.BUDGET_FRACTION` of ``limit`` and grown
    by :data:`~gf180tcad.tcad.jobmem.GROWTH_FRACTION` of it."""
    if limit is None:
        return False
    return rss > BUDGET_FRACTION * limit and rss - first_rss >= GROWTH_FRACTION * limit


def after_point(index: int, last: bool, log=None) -> None:
    """Trim the heap, log the memory after point ``index`` and raise :class:`BudgetReached`
    when :func:`over_budget` (never after the ``last`` point, nor without a reading)."""
    global _first_rss
    freed = trim()
    rss, limit = rss_bytes(), limit_bytes()
    if rss is not None and _first_rss is None:
        _first_rss = rss
    if log is not None:
        mem = "rss unavailable" if rss is None else f"rss {rss // _MIB} MiB"
        trimmed = "trim unavailable" if freed is None else f"trim freed {freed // _MIB} MiB"
        cap = "no limit" if limit is None else f"limit {limit // _MIB} MiB"
        log(f"memory after point {index + 1}: {mem}, {trimmed}, {cap}")
    if not last and rss is not None and over_budget(rss, _first_rss, limit):
        raise BudgetReached(index, rss, limit)
