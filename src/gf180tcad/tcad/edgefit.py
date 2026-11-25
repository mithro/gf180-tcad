# SPDX-License-Identifier: Apache-2.0
"""The fitted poly length bias δ of the 2D cells (issue #189, plan Task E3).

The fit is made once, by ``python -m gf180tcad.calibrate edge-fit``
(:mod:`gf180tcad.calibrate.edge`), and frozen in ``results/tcad/edgefit/<device>.json`` with
every input it used. This module only reads that file. A calibrated 2D job applies δ when the
file exists (:func:`apply`). Without it, the job keeps the process file's start value of 0.

The file stands outside ``results/tcad/calibration``. So the 1D calibration, its
``param_sha256``, the 1D jobs and the corner fits do not depend on it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.tcad.process import TUNABLES_2D, ProcessDescription

#: The tree root of the frozen fits: ``<device>.json`` and ``provenance.json``.
TREE_ROOT = REPO_ROOT / "results" / "tcad" / "edgefit"
#: The schema version of a fit file.
SCHEMA = 1
#: The tunable the fit sets: the poly length bias at each gate end (nm).
PARAM = "poly_bias_nm"

if PARAM not in TUNABLES_2D:  # pragma: no cover - guards a rename in process.py
    raise ImportError(f"{PARAM} is not in process.TUNABLES_2D {TUNABLES_2D}")


def fit_file(device: str, root: Path | None = None) -> Path:
    """``<root>/<device>.json`` (default root :data:`TREE_ROOT`)."""
    return Path(root if root is not None else TREE_ROOT) / f"{device}.json"


def read(device: str, root: Path | None = None) -> dict | None:
    """The frozen fit of ``device``, or None when no fit is committed.

    Raises ValueError for a file of another device or schema."""
    path = fit_file(device, root)
    if not path.is_file():
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("schema") != SCHEMA or d.get("device") != device or PARAM not in d:
        raise ValueError(f"{path}: not a schema-{SCHEMA} edge fit of {device}")
    return d


def sha256(device: str, root: Path | None = None) -> str | None:
    """The sha256 of ``device``'s fit file, or None when there is none."""
    path = fit_file(device, root)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def apply(
    proc: ProcessDescription, root: Path | None = None
) -> tuple[ProcessDescription, dict | None]:
    """``proc`` with the fitted δ, and the record of the fit for the job meta.

    Returns ``(proc, None)`` unchanged when no fit is committed. Otherwise returns
    ``proc.with_values({PARAM: δ})`` and ``{"poly_bias_nm": δ, "sha256": <file sha256>}``.
    Only a calibrated 2D job calls this. The 1D jobs, the 1D calibration and the corner fits
    never do."""
    fit = read(proc.device, root)
    if fit is None:
        return proc, None
    delta = float(fit[PARAM])
    return proc.with_values({PARAM: delta}), {PARAM: delta, "sha256": sha256(proc.device, root)}
