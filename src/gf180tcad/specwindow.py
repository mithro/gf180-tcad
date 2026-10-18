# SPDX-License-Identifier: Apache-2.0
"""PDK spec windows and the corner envelope (design spec 5.2, "Same process" window).

Two pieces:

- :func:`envelope` / :func:`envelope_tree`: per metric, the (min, max) over the five process
  corners of the published SPICE reference. ``spice-reference`` writes the result as
  ``results/spice/envelope.json``, shaped ``{engine: {device: {geometry_id: {metric: [lo, hi]}}}}``.
  This is pure min/max selection of published floats; no arithmetic is done on them.
- :func:`window`: the "Same process" agreement window for one metric, the hull of the PDK's
  own spec min-max and the corner envelope, together with which of the two sets it.

The spec table is ``data/pdk_elec_spec.json`` (public GF180MCU PDK documentation, see its
``source_url``). It is stored as published; :func:`spec_range` converts one entry to the
convention of the metric it is compared with (``vt_*`` signed by polarity, every other metric a
magnitude) as a closed interval with ``-inf`` / ``inf`` for an open side.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from gf180tcad import io
from gf180tcad.devices import CORNERS
from gf180tcad.layout import ENVELOPE_NAME, METRICS_NAME
from gf180tcad.sandbox import REPO_ROOT

SPEC_PATH = REPO_ROOT / "data" / "pdk_elec_spec.json"


def envelope(
    metrics_by_corner: Mapping[str, Mapping[str, float]],
) -> dict[str, tuple[float, float]]:
    """Per metric, ``(min, max)`` over the corners. Every corner must hold the same metrics."""
    if not metrics_by_corner:
        raise ValueError("empty corner set")
    names = None
    for corner, m in metrics_by_corner.items():
        if names is None:
            names = set(m)
        elif set(m) != names:
            diff = sorted(set(m) ^ names)
            raise ValueError(f"corner {corner!r} differs in metrics: {diff!r}")
    return {
        k: (
            min(m[k] for m in metrics_by_corner.values()),
            max(m[k] for m in metrics_by_corner.values()),
        )
        for k in sorted(names)
    }


def _collect(root: Path) -> dict[str, dict[tuple[str, str], dict[str, dict[str, float]]]]:
    """``{engine: {(device, geometry_id): {corner: metrics}}}`` of the corners under ``root``."""
    root = Path(root)
    out: dict = {}
    for edir in sorted(p for p in root.iterdir() if p.is_dir()):
        per: dict = out.setdefault(edir.name, {})
        for corner in CORNERS:
            cdir = edir / corner
            if not cdir.is_dir():
                continue
            for ddir in sorted(p for p in cdir.iterdir() if p.is_dir()):
                for gdir in sorted(p for p in ddir.iterdir() if p.is_dir()):
                    data = json.loads((gdir / METRICS_NAME).read_text(encoding="utf-8"))
                    per.setdefault((ddir.name, gdir.name), {})[corner] = data["metrics"]
    return out


def incomplete(root: Path) -> list[tuple[str, str, str]]:
    """``(engine, device, geometry_id)`` under ``root`` that lack some corner of ``CORNERS``."""
    return sorted(
        (engine, device, gid)
        for engine, per in _collect(root).items()
        for (device, gid), by_corner in per.items()
        if set(by_corner) != set(CORNERS)
    )


def envelope_tree(root: Path) -> dict:
    """``{engine: {device: {geometry_id: {metric: [lo, hi]}}}}`` over the corners under ``root``.

    ``root`` is a reference tree ``<engine>/<corner>/<device>/<geometry_id>/metrics.json``.
    An entry is written only when all five corners of ``CORNERS`` are present, so a partial
    envelope never looks complete; the others are listed by :func:`incomplete`.
    """
    out: dict = {}
    for engine, per in _collect(root).items():
        for (device, gid), by_corner in per.items():
            if set(by_corner) != set(CORNERS):
                continue
            env = envelope(by_corner)
            out.setdefault(engine, {}).setdefault(device, {})[gid] = {
                k: list(v) for k, v in env.items()
            }
    return out


def write_envelope(root: Path, path: Path | None = None) -> Path:
    """Write :func:`envelope_tree` of ``root`` to ``path`` (default ``root/envelope.json``)."""
    path = Path(path) if path is not None else Path(root) / ENVELOPE_NAME
    io.write_json(path, envelope_tree(root))
    return path


@dataclass(frozen=True)
class Window:
    """An agreement window ``[lo, hi]`` and where it came from.

    ``source`` says which interval sets the window: ``"spec"`` (the PDK spec min-max),
    ``"envelope"`` (the corner envelope) or ``"hull"`` (neither contains the other). This is the
    "which one is shown" of the docs. Open sides are ``-inf`` / ``inf``.
    """

    metric: str
    lo: float
    hi: float
    source: str

    def contains(self, value: float) -> bool:
        return self.lo <= value <= self.hi


def window(metric: str, spec: tuple[float, float], envelope: tuple[float, float]) -> Window:
    """The convex hull ``[min(lo), max(hi)]`` of the spec interval and the corner envelope.

    ``source`` says which one sets the window: ``"spec"`` if the spec contains the envelope
    (including equal intervals), ``"envelope"`` if the envelope contains the spec, ``"hull"``
    for partial overlap or disjoint intervals. An unbounded spec side (``-inf`` / ``inf``)
    stays unbounded.
    """
    for name, (lo, hi) in (("spec", spec), ("envelope", envelope)):
        if not lo <= hi:
            raise ValueError(f"{metric}: {name} interval is inverted: ({lo}, {hi})")
    lo, hi = min(spec[0], envelope[0]), max(spec[1], envelope[1])
    if (lo, hi) == tuple(spec):
        source = "spec"
    elif (lo, hi) == tuple(envelope):
        source = "envelope"
    else:
        source = "hull"
    return Window(metric, lo, hi, source)


def load_spec(path: Path | None = None) -> dict:
    """The parsed ``data/pdk_elec_spec.json``."""
    return json.loads(Path(path or SPEC_PATH).read_text(encoding="utf-8"))


def spec_range(entry: Mapping) -> tuple[float, float]:
    """Spec interval of one entry, in the convention of the metric it is compared with.

    ``vt_*`` metrics are signed by polarity, as published. Every other metric is a magnitude:
    pfet entries (published negative) are negated and swapped, and the lower bound is clamped to
    0, so a one-sided Ioff <= 10 becomes ``(0.0, 10.0)``. An open side of a signed metric is
    ``-inf`` / ``inf``.
    """
    metric = entry.get("metric")
    if not metric:
        raise ValueError(f"{entry.get('symbol')}: no metric to compare with")
    lo = -math.inf if entry["min"] is None else float(entry["min"])
    hi = math.inf if entry["max"] is None else float(entry["max"])
    if metric.startswith("vt_"):
        return lo, hi
    if entry["device"].startswith("pfet"):
        lo, hi = -hi, -lo
    return max(lo, 0.0), hi
