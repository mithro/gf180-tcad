# SPDX-License-Identifier: Apache-2.0
"""The caps of the two docs skills of spec §10.3, measured over the docs sources.

- writing-sourced-docs: the vendored ``tools/measure_docs.py`` (paragraph 100, list item 60,
  sentence 45, table cell 25 and first sentence 25 words).
- docs-writing: :func:`doc_style.lint_findings` (banned words, sentence 25 words, lists of 7,
  15 links per page), the checks of its ``docs_lint.py``, which is not vendored.

The pages do not meet every cap yet, so ``tests/doc_measure_baseline.json`` holds the current
count of each kind of finding, and a count may only fall. Lower the baseline in the PR that
fixes pages: ``uv run --locked python tests/test_doc_measure.py --write-baseline``.

Two kinds of measure_docs.py finding are not counted, by the house decision on citations of
spec §10.3 (inline links and MyST roles, no footnotes): "inline URL not in any footnote
definition" and "number with no marker or 'typical' label".
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from doc_style import ROOT, lint_findings, source_pages

TOOL = ROOT / "tools" / "measure_docs.py"
BASELINE = Path(__file__).with_name("doc_measure_baseline.json")
NOT_COUNTED = ("inline URL not in any footnote definition", "number with no marker")


def _measure() -> Counter:
    pages = [str(p) for p in source_pages()]
    r = subprocess.run(
        [sys.executable, "-I", str(TOOL), *pages], capture_output=True, text=True, check=False
    )
    assert r.returncode in (0, 1), r.stderr
    counts: Counter = Counter()
    for line in r.stdout.splitlines():
        if line.endswith("file(s) measured") or any(k in line for k in NOT_COUNTED):
            continue
        m = re.search(r": (first sentence|sentence|paragraph|item|cell) \d+ words", line)
        kind = m.group(1) if m else "footnote"
        counts[f"measure_docs {kind}"] += 1
    return counts


def _lint() -> Counter:
    counts: Counter = Counter()
    for p in source_pages():
        for kind, items in lint_findings(p.read_text(encoding="utf-8")).items():
            counts[f"docs_lint {kind}"] += len(items)
    return counts


def current() -> dict[str, int]:
    return dict(sorted((_measure() + _lint()).items()))


def test_measure_docs_selftest():
    r = subprocess.run([sys.executable, "-I", str(TOOL), "--selftest"], capture_output=True,
                       text=True, check=False)  # fmt: skip
    assert r.returncode == 0 and "selftest OK" in r.stdout, r.stdout + r.stderr


def test_counts_do_not_grow():
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    now = current()
    grown = {k: (base.get(k, 0), v) for k, v in now.items() if v > base.get(k, 0)}
    assert not grown, f"findings grew (baseline, now): {grown}; fix the pages, see spec §10.3"


def test_table_cells_meet_the_cap():
    """Table cells are at the cap already: no measure_docs.py cell finding is allowed."""
    assert current().get("measure_docs cell", 0) == 0


if __name__ == "__main__" and sys.argv[1:] == ["--write-baseline"]:
    BASELINE.write_text(json.dumps(current(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(BASELINE.read_text(encoding="utf-8"))
