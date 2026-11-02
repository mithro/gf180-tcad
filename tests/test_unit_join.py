# SPDX-License-Identifier: Apache-2.0
"""docs/_ext/unit_join.py: a number and its unit never break apart (issue #119)."""

import sys
from pathlib import Path

import pytest
from docutils import nodes

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docs" / "_ext"))
import unit_join  # noqa: E402

NB, WJ = " ", "⁠"


@pytest.mark.parametrize(
    ("src", "want"),
    [
        ("at 300 K here", f"at 300{NB}K here"),
        ("a 5 V transistor", f"a 5{NB}V transistor"),
        ("error 0.67 %.", f"error 0.67{NB}%."),
        ("W/L = 10/0.7 µm", f"W/L = 10/0.7{NB}µm"),
        ("2.15 fF/µm² of oxide", f"2.15{NB}fF/{WJ}µm² of oxide"),
        ("7 mV and 3 nm", f"7{NB}mV and 3{NB}nm"),
    ],
)
def test_joins(src, want):
    assert unit_join.join_units(src) == want


@pytest.mark.parametrize("src", ["3 Vgs", "step 2 of 3", "a V and a K", "the 5 Kelvin", "x A/B"])
def test_leaves_other_text(src):
    assert unit_join.join_units(src) == src


def test_is_idempotent():
    once = unit_join.join_units("2.15 fF/µm² at 300 K")
    assert unit_join.join_units(once) == once


def test_code_is_untouched():
    doc = nodes.paragraph("", "", nodes.Text("a 5 V rail "), nodes.literal("", "5 V"))
    unit_join.join_doctree(None, doc, "x")
    assert doc.astext() == f"a 5{NB}V rail 5 V"
