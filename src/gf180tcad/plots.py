# SPDX-License-Identifier: Apache-2.0
"""The deterministic SVG settings every generated figure is saved with.

The explainer figures (:mod:`gf180tcad.explain.figures`), the comparison figures
(:mod:`gf180tcad.comparison_figures`), the results figures (:mod:`gf180tcad.results_figures`) and
the image page's figures (:mod:`gf180tcad.imagefig`) draw inside :data:`RC` and save with
:data:`METADATA`. The SVG bytes then depend only on the input arrays and the pinned matplotlib
version: fixed hash salt (element ids), no date, text kept as text (no font outlines), fixed dpi,
and path simplification off.
"""

from __future__ import annotations

RC = {
    "svg.hashsalt": "gf180tcad",
    "svg.fonttype": "none",
    "path.simplify": False,
    "figure.dpi": 100,
    "savefig.dpi": 100,
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans"],
    "axes.unicode_minus": False,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
}
METADATA = {"Date": None, "Creator": "gf180tcad"}
