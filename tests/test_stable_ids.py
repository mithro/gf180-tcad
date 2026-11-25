# SPDX-License-Identifier: Apache-2.0
"""docs/_ext/stable_ids.py: each figure and table is identified by its label, less its "fig-"
or "tab-" prefix, not by a running number. Built as small Sphinx sites under -W with
stable_ids and theme_figures, as docs/conf.py loads them."""

import os
import re
import subprocess
import sys
from pathlib import Path

from optional import importorskip

EXT = Path(__file__).resolve().parents[1] / "docs" / "_ext"
sys.path.insert(0, str(EXT))
stable_ids = importorskip("stable_ids", reason="needs sphinx")

_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"></svg>\n'

_ONE = """\
Page one
========

See :numref:`fig-stack`, :numref:`tab-values` and :numref:`Figure %s of Page two <fig-plot>`.
Also :numref:`fig-under_score`.

.. figure:: light.svg
   :figclass: only-light
   :name: fig-stack

   The stack.

.. figure:: dark.svg
   :figclass: only-dark

   The stack.

.. table:: The values.
   :name: tab-values

   = =
   a b
   = =

.. figure:: plain.svg
   :name: fig-under_score

   A label with an underscore.
"""

_TWO = """\
Page two
========

See :numref:`fig-plot` and :numref:`Table %s of Page one <tab-values>`.

.. figure:: plain.svg
   :name: fig-plot

   The plot.
"""


def _site(src: Path, one: str = _ONE, two: str = _TWO, extensions=("theme_figures", "stable_ids")):
    src.mkdir()
    (src / "conf.py").write_text(
        f"import sys\nsys.path.insert(0, {str(EXT)!r})\n"
        f"extensions = {list(extensions)!r}\nnumfig = True\n"
        'numfig_format = {"figure": "Figure %s", "table": "Table %s"}\n',
        encoding="utf-8",
    )
    (src / "index.rst").write_text("Site\n====\n\n.. toctree::\n\n   one\n   two\n", "utf-8")
    (src / "one.rst").write_text(one, "utf-8")
    (src / "two.rst").write_text(two, "utf-8")
    for name in ("light", "dark", "plain"):
        (src / f"{name}.svg").write_text(_SVG, "utf-8")


def _build(src: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "sphinx", "-N", "-W", "--keep-going", "-b", "html", str(src),
         str(out)],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip


def _captions(html: str) -> list[str]:
    return re.findall(r'<span class="caption-number">([^<]*)</span>', html)


def _numrefs(html: str) -> list[str]:
    return re.findall(r'<span class="std std-numref">([^<]*)</span>', html)


def test_stable_id_drops_the_kind_prefix_only():
    assert stable_ids.stable_id("table", "tab-poe-pairs") == "poe-pairs"
    assert stable_ids.stable_id("figure", "fig-overview") == "overview"
    assert stable_ids.stable_id("figure", "tab-x") == "tab-x"  # not a figure's prefix
    assert stable_ids.stable_id("table", "mesh-window") == "mesh-window"


def test_captions_and_numrefs_show_the_label(tmp_path):
    """The caption reads "Figure stack: ", a {numref} "Figure stack" (no colon), across pages
    with the page title too; a light/dark pair is one figure with one identifier, and a label
    with an underscore is shown as written, not as its id."""
    importorskip("sphinx")
    _site(tmp_path / "src")
    r = _build(tmp_path / "src", tmp_path / "out")
    assert r.returncode == 0, r.stdout + r.stderr
    one = (tmp_path / "out" / "one.html").read_text("utf-8")
    two = (tmp_path / "out" / "two.html").read_text("utf-8")
    assert _captions(one) == ["Figure stack: ", "Table values: ", "Figure under_score: "]
    assert _numrefs(one) == [
        "Figure stack", "Table values", "Figure plot of Page two", "Figure under_score",
    ]  # fmt: skip
    assert _captions(two) == ["Figure plot: "]
    assert _numrefs(two) == ["Figure plot", "Table values of Page one"]
    assert one.count("<figure") == 2  # the twins are one figure
    assert 'src="_images/light.svg"' in one and 'src="_images/dark.svg"' in one


def test_without_stable_ids_the_numbers_show(tmp_path):
    """Negative control of the test above: without the extension, Sphinx's running numbers
    show, so the assertions above see the extension's work."""
    importorskip("sphinx")
    _site(tmp_path / "src", extensions=("theme_figures",))
    r = _build(tmp_path / "src", tmp_path / "out")
    assert r.returncode == 0, r.stdout + r.stderr
    one = (tmp_path / "out" / "one.html").read_text("utf-8")
    assert _captions(one) == ["Figure 1 ", "Table 1 ", "Figure 2 "]


def test_a_numbered_item_without_a_label_fails_the_build(tmp_path):
    """Positive control: a captioned figure with no :name: has no identifier to show."""
    importorskip("sphinx")
    one = _ONE + "\n.. figure:: plain.svg\n\n   No name.\n"
    _site(tmp_path / "src", one=one)
    r = _build(tmp_path / "src", tmp_path / "out")
    assert r.returncode != 0
    assert "a numbered figure has no label" in r.stderr, r.stderr


def test_two_labels_with_one_identifier_fail_the_build(tmp_path):
    """Positive control: "fig-plot" and "plot" both show as "Figure plot"."""
    importorskip("sphinx")
    two = _TWO + "\nSee :numref:`plot`.\n\n.. figure:: plain.svg\n   :name: plot\n\n   Again.\n"
    _site(tmp_path / "src", two=two)
    r = _build(tmp_path / "src", tmp_path / "out")
    assert r.returncode != 0
    assert "has the same identifier 'plot'" in r.stderr, r.stderr


def test_a_named_dark_twin_fails_the_build(tmp_path):
    """Positive control: the dark twin's label would vanish with it in the merge."""
    importorskip("sphinx")
    one = _ONE.replace(
        "   :figclass: only-dark\n", "   :figclass: only-dark\n   :name: fig-stack-dark\n"
    )
    assert ":name: fig-stack-dark" in one
    _site(tmp_path / "src", one=one)
    r = _build(tmp_path / "src", tmp_path / "out")
    assert r.returncode != 0
    assert "the only-dark twin carries the label 'fig-stack-dark'" in r.stderr, r.stderr


def _age(src: Path) -> None:
    """Date every source a minute back. Sphinx treats a page whose source is not older than its
    output as out of date, so on a fast machine a page built in the same second as its source
    was written would be rebuilt for that reason alone."""
    for f in src.iterdir():
        t = f.stat().st_mtime_ns - 60 * 10**9
        os.utime(f, ns=(t, t))


def test_a_rebuild_with_no_change_writes_no_page(tmp_path):
    """Sphinx rewrites every page whose numbers differ from the last build's; stable_ids puts
    the real numbers back before that comparison, so a second build writes nothing."""
    importorskip("sphinx")
    _site(tmp_path / "src")
    _age(tmp_path / "src")
    out = tmp_path / "out"
    assert _build(tmp_path / "src", out).returncode == 0
    pages = [out / f"{name}.html" for name in ("index", "one", "two")]  # genindex is always written
    before = {p: p.stat().st_mtime_ns for p in pages}
    r = _build(tmp_path / "src", out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 added, 0 changed, 0 removed" in r.stdout, r.stdout
    assert "no targets are out of date" in r.stdout, r.stdout
    assert {p: p.stat().st_mtime_ns for p in pages} == before, r.stdout


def test_a_rebuild_without_the_restore_rewrites_pages(tmp_path):
    """Positive control of the test above: with restore_numbers switched off, Sphinx sees
    identifiers where it saved numbers and writes the pages again."""
    importorskip("sphinx")
    _site(tmp_path / "src")
    conf = tmp_path / "src" / "conf.py"
    conf.write_text(
        conf.read_text("utf-8")
        + "import stable_ids\nstable_ids.restore_numbers = lambda app, env: []\n",
        "utf-8",
    )
    _age(tmp_path / "src")
    out = tmp_path / "out"
    assert _build(tmp_path / "src", out).returncode == 0
    r = _build(tmp_path / "src", out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert re.search(r"writing output\.\.\. \[\s*\d+%\] one", r.stdout), r.stdout


def test_a_label_without_its_kind_prefix_fails_the_build(tmp_path):
    """Positive control: a figure label without "fig-" and a table label without "tab-" are
    warnings, so -W fails (CONTRIBUTING: a label starts with its kind)."""
    importorskip("sphinx")
    one = _ONE.replace("fig-under_score", "under_score").replace("tab-values", "values")
    two = _TWO.replace("<tab-values>", "<values>")
    _site(tmp_path / "src", one=one, two=two)
    r = _build(tmp_path / "src", tmp_path / "out")
    assert r.returncode != 0
    assert "the figure label 'under_score' does not start with 'fig-'" in r.stderr, r.stderr
    assert "the table label 'values' does not start with 'tab-' or 'tbl-'" in r.stderr, r.stderr


def test_adding_a_figure_keeps_every_identifier(tmp_path):
    """An incremental build after a figure is added before the others: Sphinx's numbers shift,
    but no identifier changes, the new figure shows its own, and page two's {numref}s to page
    one still name the same items. Then a rebuild with no change writes no page."""
    importorskip("sphinx")
    two = _TWO.replace(
        "See :numref:`fig-plot`",
        "See :numref:`Figure %s of Page one <fig-stack>`, :numref:`fig-plot`",
    )
    _site(tmp_path / "src", two=two)
    _age(tmp_path / "src")
    out = tmp_path / "out"
    assert _build(tmp_path / "src", out).returncode == 0
    page_one = tmp_path / "src" / "one.rst"
    added = page_one.read_text("utf-8").replace(
        "See :numref:",
        "See :numref:`fig-added`.\n\n.. figure:: plain.svg\n   :name: fig-added\n\n   Added.\n\nSee :numref:",
        1,
    )
    page_one.write_text(added, "utf-8")
    r = _build(tmp_path / "src", out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 added, 1 changed, 0 removed" in r.stdout, r.stdout
    one = (out / "one.html").read_text("utf-8")
    assert _captions(one) == [
        "Figure added: ", "Figure stack: ", "Table values: ", "Figure under_score: ",
    ]  # fmt: skip
    assert _numrefs(one)[0] == "Figure added"
    assert _numrefs((out / "two.html").read_text("utf-8")) == [
        "Figure stack of Page one", "Figure plot", "Table values of Page one",
    ]  # fmt: skip
    r = _build(tmp_path / "src", out)
    assert "no targets are out of date" in r.stdout, r.stdout
