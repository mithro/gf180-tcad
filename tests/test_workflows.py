# SPDX-License-Identifier: Apache-2.0
"""GitHub Actions hygiene: pinned actions, minimal permissions, timeouts, one uv version.

Checked by line patterns (no YAML parser needed). ``image.yml`` grants ``packages: write`` to its
build-push job only, below the workflow-level ``contents: read``.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CHECKED = ("ci.yml", "crosscheck.yml", "linkcheck.yml", "image.yml")
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)(.*)$")
PINNED = re.compile(r"^[\w.-]+/[\w.-]+(/[\w./-]+)?@[0-9a-f]{40}$")
COMMENT = re.compile(r"^\s+# v\d+\.\d+\.\d+$")


def _lines(name: str) -> list[str]:
    return (WORKFLOWS / name).read_text(encoding="utf-8").splitlines()


def _jobs(lines: list[str]) -> dict[str, list[str]]:
    start = lines.index("jobs:")
    jobs: dict[str, list[str]] = {}
    current = None
    for line in lines[start + 1 :]:
        if line and not line.startswith(" "):
            break
        m = re.match(r"^  ([\w-]+):\s*$", line)
        if m:
            current = jobs.setdefault(m.group(1), [])
        elif current is not None:
            current.append(line)
    return jobs


@pytest.mark.parametrize("name", CHECKED)
def test_every_action_is_pinned_to_a_commit_with_its_version(name):
    uses = [USES.match(ln) for ln in _lines(name)]
    uses = [m for m in uses if m]
    assert uses, f"{name} uses no actions?"
    for m in uses:
        ref, rest = m.group(1), m.group(2)
        assert PINNED.match(ref), f"{name}: {ref} is not pinned to a full commit SHA"
        assert COMMENT.match(rest), f"{name}: {ref} lacks a '# vX.Y.Z' comment"


@pytest.mark.parametrize("name", CHECKED)
def test_minimal_permissions(name):
    lines = _lines(name)
    i = lines.index("permissions:")
    assert lines[i + 1] == "  contents: read"
    assert not lines[i + 2].startswith("  "), f"{name}: more permissions than contents: read"


@pytest.mark.parametrize("name", CHECKED)
def test_every_job_has_a_timeout(name):
    jobs = _jobs(_lines(name))
    assert jobs
    for job, body in jobs.items():
        assert any(re.match(r"^    timeout-minutes: \d+$", ln) for ln in body), (
            f"{name}: job {job} has no timeout-minutes"
        )


def test_docs_job_installs_from_the_lock_file():
    body = _jobs(_lines("ci.yml"))["docs"]
    runs = [ln for ln in body if "uv run" in ln or "uv sync" in ln]
    assert runs and all("--locked" in ln for ln in runs)


def _ci_uv_versions() -> set[str]:
    out = set()
    for name in CHECKED:
        lines = _lines(name)
        for i, ln in enumerate(lines):
            if "astral-sh/setup-uv@" in ln:
                m = re.match(r'^\s+version: "([^"]+)"$', lines[i + 2])
                assert lines[i + 1].strip() == "with:" and m, f"{name}: setup-uv has no version"
                out.add(m.group(1))
    return out


def test_one_uv_version_for_ci_and_read_the_docs():
    versions = _ci_uv_versions()
    assert len(versions) == 1, versions
    (uv,) = versions
    rtd = (ROOT / ".readthedocs.yaml").read_text(encoding="utf-8")
    assert "uv latest" not in rtd
    assert f"asdf install uv {uv}" in rtd and f"asdf global uv {uv}" in rtd
