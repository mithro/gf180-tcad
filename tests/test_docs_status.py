# SPDX-License-Identifier: Apache-2.0
"""The status pages keep up with the committed results (CONTRIBUTING.md, PR checklist).

``docs/index.md`` (its Status admonition) and ``README.md`` (its Status section) are hand
written, so nothing regenerates them when a result tree is added. These checks catch the
coarsest lag: a top-level tree under ``results/tcad`` that a Status does not name, and phrases
from statuses that are known to have gone stale.
"""

import re
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


def docs_index_status() -> str:
    text = (ROOT / "docs" / "index.md").read_text("utf-8")
    m = re.search(r"^```\{admonition\} Status\n(.*?)^```$", text, re.DOTALL | re.MULTILINE)
    assert m, "docs/index.md has no Status admonition"
    return m.group(1)


def readme_status() -> str:
    text = (ROOT / "README.md").read_text("utf-8")
    m = re.search(r"^## Status\n(.*?)(?=^## )", text, re.DOTALL | re.MULTILINE)
    assert m, "README.md has no Status section"
    return m.group(1)


STATUSES = {"docs/index.md": docs_index_status, "README.md": readme_status}


def tcad_trees() -> list[str]:
    return sorted(p.name for p in TCAD_RESULTS.iterdir() if p.is_dir())


def test_there_are_tcad_trees():
    # Guards the test below against an empty or moved results/tcad.
    assert tcad_trees()


@pytest.mark.parametrize("page", sorted(STATUSES))
def test_status_names_every_tcad_tree(page):
    status = STATUSES[page]()
    missing = [t for t in tcad_trees() if f"results/tcad/{t}" not in status]
    assert not missing, f"the {page} Status does not name results/tcad/{missing}"


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
    monkeypatch.setitem(STATUSES, "README.md", lambda: "results/tcad/moscap1d only")
    with pytest.raises(AssertionError, match="does not name"):
        test_status_names_every_tcad_tree("README.md")
