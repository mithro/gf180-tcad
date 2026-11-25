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

The verdict table of the status page is checked cell by cell against the calibration and
validation result files.
"""

import json
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


# --- the verdict table of the status page against the result files (review of #204) ---------

DEVICES = ("nfet_05v0", "pfet_05v0")
# Each 2D row label -> the geometry id of each device (the first row is each one's shortest gate).
TWO_D_ROWS = {
    "2D, W10/L0.6 or W10/L0.5": ("w10p0_l0p60", "w10p0_l0p50"),
    "2D, W10/L0.7": ("w10p0_l0p70",) * 2,
    "2D, W1.6/L0.7": ("w1p6_l0p70",) * 2,
    "2D, W10/L1": ("w10p0_l1p00",) * 2,
    "2D, W10/L2": ("w10p0_l2p00",) * 2,
    "2D, W10/L10": ("w10p0_l10p00",) * 2,
}


def verdict_table(text: str) -> dict[str, tuple[str, ...]]:
    """{row label: (nfet cell, pfet cell)} of the table under "## The verdicts", with the
    {term} roles reduced to their text."""
    section = text.split("## The verdicts", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.startswith("|") or cells[0] in ("Model", "") or set(cells[0]) <= {"-"}:
            continue
        rows[cells[0]] = tuple(
            re.sub(r"\{term\}`([^`<]+?)\s*(<[^`]*>)?`", r"\1", c) for c in cells[1:]
        )
    return rows


def expected_verdicts() -> dict[str, tuple[str, ...]]:
    """The same table from results/tcad/calibration/*.result.json (the fit's overall verdict)
    and results/tcad/validation/*.json (the held-out 1D verdict and each 2D cell's)."""
    cal = {
        d: json.loads((TCAD_RESULTS / "calibration" / f"{d}.result.json").read_text("utf-8"))
        for d in DEVICES
    }
    val = {
        d: json.loads((TCAD_RESULTS / "validation" / f"{d}.json").read_text("utf-8"))
        for d in DEVICES
    }

    def two_d(device: str, geo: str) -> str:
        cell = val[device]["two_d"][geo]
        return cell["verdict"] if cell["status"] == "compared" else cell["status"]

    out = {
        "1D, the fitted geometries": tuple(cal[d]["verdict"] for d in DEVICES),
        "1D, the held-out geometries": tuple(val[d]["verdict_1d"] for d in DEVICES),
    }
    for label, geos in TWO_D_ROWS.items():
        out[label] = tuple(two_d(d, g) for d, g in zip(DEVICES, geos, strict=True))
    return out


def test_status_verdict_table_is_the_result_files():
    assert verdict_table(page_text(STATUS_PAGE)) == expected_verdicts()


def test_positive_control_verdict_table_mismatch():
    page = page_text(STATUS_PAGE).replace("| 2D, W10/L1 | Same process |", "| 2D, W10/L1 | Agree |")
    assert verdict_table(page) != expected_verdicts()
