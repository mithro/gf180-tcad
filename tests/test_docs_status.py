# SPDX-License-Identifier: Apache-2.0
"""The status page keeps up with the committed results (CONTRIBUTING.md, PR checklist).

``docs/limitations/status.md`` is hand written, so nothing regenerates it when a result tree is
added. The landing page (``docs/index.md``) and ``README.md`` give an overview and link to it;
they hold no list of results to fall behind. These checks catch only the coarsest lag: a
top-level tree under ``results/tcad`` that the status page does not name, and phrases from
statuses that are known to have gone stale, on the status page, the landing page and the README.

Blind spots: only the top-level directories of ``results/tcad`` are checked (not their
subtrees, ``results/spice`` or other docs pages); a tree counts as named when
``results/tcad/<tree>`` appears anywhere on the status page as a substring, whatever the
sentence says about it; and only the phrases in ``STALE`` are caught. A passing test does not
mean the status is current; the review does (CONTRIBUTING.md, PR checklist).
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TCAD_RESULTS = ROOT / "results" / "tcad"

# Phrases of earlier statuses that are no longer true; matched case-insensitively.
STALE = (
    "No TCAD simulation has been run yet",
    "there are no results yet",
    "Next are the TCAD results and comparison pages",
    "Phases 0 and 1` (foundations and the SPICE reference dataset) are in progress",
)


STATUS_PAGE = "docs/limitations/status.md"


def page_text(page: str) -> str:
    return (ROOT / page).read_text("utf-8")


# The pages whose text is checked for stale phrases; the first is the status page.
STATUSES = {
    page: (lambda page=page: page_text(page))
    for page in (STATUS_PAGE, "docs/index.md", "README.md")
}


def tcad_trees() -> list[str]:
    return sorted(p.name for p in TCAD_RESULTS.iterdir() if p.is_dir())


def test_there_are_tcad_trees():
    # Guards the test below against an empty or moved results/tcad.
    assert tcad_trees()


def test_status_names_every_tcad_tree(page=STATUS_PAGE):
    status = STATUSES[page]()
    missing = [t for t in tcad_trees() if f"results/tcad/{t}" not in status]
    named = ", ".join(f"results/tcad/{t}" for t in missing)
    assert not missing, f"the {page} Status does not name {named}"


@pytest.mark.parametrize("page", ["docs/index.md", "README.md"])
def test_overview_links_the_status_page(page):
    """The landing page and README hold no result list; each links the status page instead."""
    text = page_text(page)
    assert "limitations/status" in text, f"{page} does not link {STATUS_PAGE}"


@pytest.mark.parametrize("page", sorted(STATUSES))
def test_status_has_no_stale_phrase(page):
    status = STATUSES[page]().lower()
    found = [p for p in STALE if p.lower() in status]
    assert not found, f"the {page} Status still says {found}"


def test_positive_control_stale_phrase_is_found(monkeypatch):
    monkeypatch.setitem(STATUSES, "docs/index.md", lambda: "**No TCAD simulation has been run yet")
    with pytest.raises(AssertionError, match="still says"):
        test_status_has_no_stale_phrase("docs/index.md")


def test_positive_control_missing_tree_is_found(monkeypatch):
    monkeypatch.setitem(STATUSES, STATUS_PAGE, lambda: "results/tcad/moscap1d only")
    with pytest.raises(AssertionError, match="does not name"):
        test_status_names_every_tcad_tree()
