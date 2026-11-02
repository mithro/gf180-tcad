# SPDX-License-Identifier: Apache-2.0
"""docs/_ext/theme_figures.py: a light/dark figure pair becomes one figure, so numfig gives it
one number and {numref} names the figure every reader sees, in either theme."""

import sys
from pathlib import Path

from optional import importorskip

nodes = importorskip("docutils.nodes")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docs" / "_ext"))
import theme_figures


def _figure(uri: str, figclass: str, caption: str, ids: list[str]) -> nodes.figure:
    fig = nodes.figure(classes=[figclass], ids=ids)
    fig += nodes.image(uri=uri, alt="alt")
    fig += nodes.caption(text=caption)
    return fig


def _section(*children: nodes.Node) -> nodes.section:
    sec = nodes.section(ids=["s"])
    for child in children:
        sec += child
    return sec


def test_twins_merge_into_one_figure():
    light = _figure("a-light.svg", "only-light", "The cell.", ["mesh-window-figure"])
    dark = _figure("a-dark.svg", "only-dark", "The cell.", ["id1"])
    doc = _section(nodes.paragraph(text="before"), light, dark, nodes.paragraph(text="after"))
    assert theme_figures.merge_twins(doc) == 1
    figures = list(doc.findall(nodes.figure))
    assert figures == [light]
    assert light["ids"] == ["mesh-window-figure"] and "only-light" not in light["classes"]
    images = list(light.findall(nodes.image))
    assert [(i["uri"], i["classes"]) for i in images] == [
        ("a-light.svg", ["only-light"]),
        ("a-dark.svg", ["only-dark"]),
    ]
    assert [c.astext() for c in light.findall(nodes.caption)] == ["The cell."]
    assert [p.astext() for p in doc.findall(nodes.paragraph)] == ["before", "after"]


def test_twins_with_other_captions_stay_apart():
    light = _figure("a-light.svg", "only-light", "One.", ["x"])
    dark = _figure("a-dark.svg", "only-dark", "Another.", ["y"])
    doc = _section(light, dark)
    assert theme_figures.merge_twins(doc) == 0
    assert len(list(doc.findall(nodes.figure))) == 2


def test_lone_figures_are_left_alone():
    plain = _figure("p.svg", "", "Plain.", ["p"])
    dark = _figure("a-dark.svg", "only-dark", "Plain.", ["y"])
    doc = _section(plain, dark)
    assert theme_figures.merge_twins(doc) == 0
    assert len(list(doc.findall(nodes.figure))) == 2
