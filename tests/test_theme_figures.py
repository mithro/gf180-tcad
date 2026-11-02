# SPDX-License-Identifier: Apache-2.0
"""docs/_ext/theme_figures.py: a light/dark figure pair becomes one figure, so numfig gives it
one number and {numref} names the figure every reader sees, in either theme."""

import re
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


_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"></svg>\n'


def _page(title: str, prefix: str) -> str:
    """An rST page with a light/dark twin pair (named, cited) and then a plain figure."""
    return f""".. _{prefix}-top:

{title}
{"=" * len(title)}

See :numref:`{prefix}-pair` and :numref:`{prefix}-plain`.

.. figure:: {prefix}-light.svg
   :figclass: only-light
   :name: {prefix}-pair

   The pair on {title}.

.. figure:: {prefix}-dark.svg
   :figclass: only-dark

   The pair on {title}.

.. figure:: {prefix}-plain.svg
   :name: {prefix}-plain

   The plain figure on {title}.
"""


def _site(src: Path) -> None:
    src.mkdir()
    (src / "conf.py").write_text(
        f"import sys\nsys.path.insert(0, {str(Path(theme_figures.__file__).parent)!r})\n"
        'extensions = ["theme_figures"]\nnumfig = True\n'
        'numfig_format = {"figure": "Figure %s"}\n'
    )
    (src / "index.rst").write_text("Site\n====\n\n.. toctree::\n\n   one\n   two\n")
    for prefix, title in (("one", "Page one"), ("two", "Page two")):
        (src / f"{prefix}.rst").write_text(_page(title, prefix))
        for kind in ("light", "dark", "plain"):
            (src / f"{prefix}-{kind}.svg").write_text(_SVG)


def test_each_page_numbers_its_figures_from_one(tmp_path):
    """Two pages with a twin pair and a plain figure each: both pages show Figure 1 and Figure 2,
    and the pair, merged, takes one number (built by Sphinx with -W)."""
    build_main = importorskip("sphinx.cmd.build").build_main
    src, out = tmp_path / "src", tmp_path / "out"
    _site(src)
    assert build_main(["-W", "-q", "-b", "html", str(src), str(out)]) == 0
    for prefix in ("one", "two"):
        html = (out / f"{prefix}.html").read_text()
        numbers = re.findall(r'<span class="caption-number">(Figure \d+) </span>', html)
        assert numbers == ["Figure 1", "Figure 2"], prefix
        assert html.count("<figure") == 2, prefix  # the twins are one figure
        assert f'src="_images/{prefix}-light.svg"' in html
        assert f'src="_images/{prefix}-dark.svg"' in html
        cited = re.findall(r'<span class="std std-numref">(Figure \d+)</span>', html)
        assert cited == ["Figure 1", "Figure 2"], prefix
