# SPDX-License-Identifier: Apache-2.0
"""docs/_ext/figure_numbers.py: per-page figure numbers, one number per light and dark twin pair."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location(
        "figure_numbers", ROOT / "docs" / "_ext" / "figure_numbers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_twins_share_a_number_and_pages_start_at_one():
    page_numbers = _module().page_numbers
    figures = [
        ("a", ["only-light"]),
        ("b", ["only-dark"]),
        ("photo", []),
        ("c", ["only-light"]),
        ("d", ["only-dark"]),
        ("e", []),
    ]
    assert page_numbers(figures) == {"a": 1, "b": 1, "photo": 2, "c": 3, "d": 3, "e": 4}


def test_a_dark_figure_without_a_light_one_before_it_counts():
    page_numbers = _module().page_numbers
    assert page_numbers([("x", []), ("y", ["only-dark"]), ("z", ["only-dark"])]) == {
        "x": 1,
        "y": 2,
        "z": 3,
    }


def test_conf_enables_numbering_with_the_extension():
    conf = (ROOT / "docs" / "conf.py").read_text(encoding="utf-8")
    assert "numfig = True" in conf and '"figure_numbers"' in conf
