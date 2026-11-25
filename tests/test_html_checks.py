# SPDX-License-Identifier: Apache-2.0
"""The built-HTML checks of docs/_ext/html_checks.py: every numbered figure, table and code
block is cited by a link from some page, every image has alt text, and no page shows a docutils
error box, an unresolved reference or a {contents} box. Each check has a positive control (it
fires) and a negative control (the house form passes), on hand-written HTML and on a small
Sphinx site built with docs/conf.py's extensions under -W."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "docs" / "_ext" / "html_checks.py"


@cache
def checks():
    spec = importlib.util.spec_from_file_location("html_checks", CHECKS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _figure(fid="fig-a", number="Figure 1 ", alt="The stack.", src="_images/a.svg"):
    return (
        f'<figure class="align-default" id="{fid}"><img alt="{alt}" src="{src}" />'
        f'<figcaption><p><span class="caption-number">{number}</span>'
        f'<span class="caption-text">The stack.</span>'
        f'<a class="headerlink" href="#{fid}" title="Link to this image">¶</a></p></figcaption>'
        "</figure>"
    )


def _table(tid="tab-a"):
    return (
        f'<div class="table-wrapper"><table class="docutils align-default" id="{tid}">'
        f'<caption><span class="caption-number">Table 1 </span>'
        f'<span class="caption-text">Values</span>'
        f'<a class="headerlink" href="#{tid}">¶</a></caption>'
        "<tbody><tr><td><p>1</p></td></tr></tbody></table></div>"
    )


def _code(cid="code-a"):
    return (
        f'<div class="literal-block-wrapper docutils container" id="{cid}">'
        '<div class="code-block-caption"><span class="caption-number">Listing 1 </span>'
        f'<span class="caption-text">run</span><a class="headerlink" href="#{cid}">¶</a></div>'
        '<div class="highlight"><pre>make</pre></div></div>'
    )


def problems(pages: dict[str, str]) -> list[str]:
    return checks().site_problems(pages)


# --- numbered and cited ---------------------------------------------------------------------


@pytest.mark.parametrize("element", [_figure(), _table(), _code()], ids=["figure", "table", "code"])
def test_uncited_number_fires(element):
    """Positive control: the caption's own headerlink is not a citation."""
    found = problems({"a.html": f"<p>Text.</p>{element}"})
    assert len(found) == 1 and "is numbered but no page refers to it" in found[0], found


@pytest.mark.parametrize(
    ("element", "target"),
    [(_figure(), "fig-a"), (_table(), "tab-a"), (_code(), "code-a")],
    ids=["figure", "table", "code"],
)
def test_number_cited_on_the_page_passes(element, target):
    page = f'<p>See <a class="reference internal" href="#{target}">Figure 1</a>.</p>{element}'
    assert problems({"a.html": page}) == []


def test_number_cited_from_another_page_passes():
    pages = {
        "explained/a.html": _figure(),
        "limitations/b.html": '<p><a href="../explained/a.html#fig-a">Figure 1</a></p>',
    }
    assert problems(pages) == []


def test_citation_of_another_page_with_the_same_id_does_not_count():
    """Figures are numbered per page, so the same label pattern can recur; a link counts only
    for the page it points at."""
    pages = {
        "a.html": _figure(),
        "b.html": _figure() + '<p><a href="#fig-a">Figure 1</a></p>',
    }
    found = problems(pages)
    assert len(found) == 1 and found[0].startswith("a.html:"), found


def test_id_inside_the_figure_counts():
    """A label can land on an element inside the figure rather than on the figure."""
    page = (
        '<figure class="align-default"><span id="fig-inner"></span>'
        '<img alt="x" src="a.svg" /><figcaption><p><span class="caption-number">Figure 1 '
        '</span>x</p></figcaption></figure><p><a href="#fig-inner">Figure 1</a></p>'
    )
    assert problems({"a.html": page}) == []


@pytest.mark.parametrize(
    "element",
    [
        '<figure class="align-default" id="x"><img alt="A plot." src="a.svg" /></figure>',
        (
            '<div class="table-wrapper"><table class="docutils align-default">'
            "<tbody><tr><td>1</td></tr></tbody></table></div>"
        ),
    ],
    ids=["figure", "table"],
)
def test_uncaptioned_figure_or_table_fires(element):
    """Positive control: a figure or a content table without a caption has no number."""
    found = problems({"a.html": element})
    assert len(found) == 1 and "has no caption" in found[0], found


def test_a_table_sphinx_draws_itself_needs_no_caption():
    """The index and the code line-number tables are not content tables (no "docutils" class)."""
    page = '<table class="indextable genindextable"><tr><td>a</td></tr></table>'
    assert problems({"a.html": page}) == []


# --- alt text -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "alt", ["", "   ", "_images/a.svg", "a.svg", "plots/cv-light.png"],
    ids=["empty", "blank", "src", "basename", "a-file"],
)  # fmt: skip
def test_image_without_alt_fires(alt):
    """Positive control: docutils fills a missing :alt: with the image's path."""
    page = _figure(alt=alt) + '<p><a href="#fig-a">Figure 1</a></p>'
    found = problems({"a.html": page})
    assert len(found) == 1 and "has no alt text" in found[0], found


def test_image_without_alt_attribute_fires():
    found = problems({"a.html": '<img src="a.svg" />'})
    assert len(found) == 1 and "has no alt text" in found[0], found


# --- error boxes ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "marker",
    [
        '<div class="system-message"><p>Error</p></div>',
        '<a href="#id1"><span class="problematic" id="id2">{ref}`x`</span></a>',
        '<nav class="contents local" id="contents"><ul></ul></nav>',
    ],
    ids=["system-message", "problematic", "contents"],
)
def test_error_marker_fires(marker):
    found = problems({"a.html": f"<p>Text.</p>{marker}"})
    assert len(found) == 1, found


def test_clean_page_passes():
    assert problems({"a.html": "<p>Text with <a href='b.html'>a link</a>.</p>"}) == []


# --- the extension in a Sphinx build --------------------------------------------------------


def _site(src: Path, page: str) -> None:
    """A one-page site with docs/conf.py's extensions list, numfig and numfig_format."""
    sys.path.insert(0, str(ROOT / "tests"))
    try:
        from test_docs_lint_rules import _site_conf
    finally:
        sys.path.remove(str(ROOT / "tests"))
    site = _site_conf()
    assert "html_checks" in site["extensions"], "docs/conf.py does not load html_checks"
    extensions = site["extensions"]
    src.mkdir()
    (src / "conf.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT / 'docs' / '_ext')!r})\n"
        f"extensions = {extensions!r}\n"
        f"myst_enable_extensions = {site['myst_enable_extensions']!r}\n"
        "numfig = True\n"
        f"numfig_format = {site['numfig_format']!r}\n",
        encoding="utf-8",
    )
    for name in ("pic.svg", "pic-dark.svg"):
        (src / name).write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>', "utf-8"
        )
    (src / "index.md").write_text(textwrap.dedent(page).lstrip("\n"), "utf-8")


def _build(src: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "sphinx", "-W", "-q", "-b", "html", str(src), str(out)],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip


_TWINS = """
    # T

    {cite}

    ```{{figure}} pic.svg
    :name: fig-stack
    :alt: The stack.
    :figclass: only-light

    The stack.
    ```

    ```{{figure}} pic-dark.svg
    :alt: The stack.
    :figclass: only-dark

    The stack.
    ```

    ```{{list-table}} Values
    :name: tab-values

    * - 1
    ```
    """


def test_sphinx_build_fails_on_an_uncited_figure_and_table(tmp_path):
    """Positive control: -W turns each finding into a failed build, and the light/dark twin
    pair is one numbered figure (one finding, not two)."""
    pytest.importorskip("sphinx")
    pytest.importorskip("myst_parser")
    _site(tmp_path / "src", _TWINS.format(cite="The stack and the values."))
    r = _build(tmp_path / "src", tmp_path / "o")
    assert r.returncode != 0, r.stdout + r.stderr
    found = [ln for ln in r.stderr.splitlines() if "is numbered but no page refers to it" in ln]
    assert len(found) == 2, r.stderr
    assert any("'Figure 1'" in ln for ln in found) and any("'Table 1'" in ln for ln in found)


def test_sphinx_build_passes_when_every_number_is_cited(tmp_path):
    pytest.importorskip("sphinx")
    pytest.importorskip("myst_parser")
    cite = "{numref}`fig-stack` draws the stack; {numref}`tab-values` lists the values."
    _site(tmp_path / "src", _TWINS.format(cite=cite))
    r = _build(tmp_path / "src", tmp_path / "o")
    assert r.returncode == 0, r.stdout + r.stderr


def test_cli_reports_and_exits_nonzero(tmp_path):
    (tmp_path / "a.html").write_text(_figure(), "utf-8")
    r = subprocess.run(
        [sys.executable, str(CHECKS), str(tmp_path)], capture_output=True, text=True, check=False
    )
    assert r.returncode == 1 and "1 problem(s) found" in r.stdout, r.stdout + r.stderr
    (tmp_path / "b.html").write_text('<a href="a.html#fig-a">Figure 1</a>', "utf-8")
    r = subprocess.run(
        [sys.executable, str(CHECKS), str(tmp_path)], capture_output=True, text=True, check=False
    )
    assert r.returncode == 0 and "0 problem(s) found" in r.stdout, r.stdout + r.stderr
