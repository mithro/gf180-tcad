# SPDX-License-Identifier: Apache-2.0
"""docs/_ext/figure_numbers.py: only named figures take a number, counted from 1 on each page.

A page names the light twin of each figure and refers to it with {numref}; the dark twin has no
name, so it must take no number, or the numbers the reader sees skip one in two.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from docutils import nodes

EXT = Path(__file__).resolve().parents[1] / "docs" / "_ext"


@pytest.fixture
def ext():
    sys.path.insert(0, str(EXT))
    try:
        yield importlib.import_module("figure_numbers")
    finally:
        sys.path.remove(str(EXT))


def _figure(name: str | None, ident: str) -> nodes.figure:
    fig = nodes.figure(ids=[ident])
    if name:
        fig["names"].append(name)
    return fig


def _doc(*figs: nodes.figure) -> nodes.document:
    doc = nodes.document(None, None)
    doc += list(figs)
    return doc


def test_unnamed_figure_ids(ext):
    doc = _doc(_figure("fig-a", "fig-a"), _figure(None, "id1"))
    assert ext.unnamed_figure_ids(doc) == {"id1"}


def test_named_figures_numbered_from_one_on_each_page(ext):
    docs = {
        "a": _doc(_figure("fig-x", "fig-x"), _figure(None, "id1"), _figure("fig-y", "fig-y")),
        "b": _doc(_figure("fig-z", "fig-z"), _figure(None, "id2")),
    }
    env = SimpleNamespace(
        toc_fignumbers={
            "a": {"figure": {"fig-x": (26,), "id1": (27,), "fig-y": (28,)}},
            "b": {"figure": {"fig-z": (30,), "id2": (31,)}, "table": {"t": (4,)}},
        },
        get_doctree=docs.__getitem__,
    )
    changed = ext.renumber_per_page(None, env)
    assert env.toc_fignumbers == {
        "a": {"figure": {"fig-x": (1,), "fig-y": (2,)}},
        "b": {"figure": {"fig-z": (1,)}, "table": {"t": (1,)}},
    }
    assert sorted(changed) == ["a", "b"]
    assert ext.renumber_per_page(None, env) == []  # already per page: nothing to rewrite
