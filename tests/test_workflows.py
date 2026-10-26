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


def test_crosscheck_runs_the_sandbox_card_fidelity_test():
    """The card-line test of the process files needs Docker; crosscheck has the sandbox."""
    lines = _lines("crosscheck.yml")
    runs = [ln for ln in lines if "pytest" in ln]
    assert any(
        "uv run --locked pytest -m sandbox tests/tcad/test_process.py" in ln for ln in runs
    ), runs
    paths = {ln.strip() for ln in lines[: lines.index("  schedule:")]}
    assert {'- "data/process/**"', '- "tests/tcad/**"'} <= paths
    # after the sandbox is set up and the image is pulled
    i = next(i for i, ln in enumerate(lines) if "pytest -m sandbox" in ln)
    assert lines.index("      - name: Pull docker/IMAGE by digest") < i
    assert lines.index("      - run: uv sync --locked") < i


def test_crosscheck_tcad_job():
    """crosscheck-tcad: submodule checkout, image by digest, temporary tree root, --kind tcad."""
    lines = _lines("crosscheck.yml")
    body = _jobs(lines)["crosscheck-tcad"]
    text = "\n".join(body)
    assert "          submodules: true" in body
    # the images the subset's jobs run in, pulled by digest
    assert "tools/crosscheck-tcad-run tests/crosscheck_tcad_subset.txt \\" in text
    assert "--images" in text and "*@sha256:*" in text and 'docker pull --quiet "$image"' in text
    assert 'echo "OUT=$RUNNER_TEMP/crosscheck-tcad/tcad"' in text
    assert '--out "$OUT"' in text and "--out results" not in text
    assert (
        'verify-subset "$OUT" --kind tcad \\\n'
        "            --against results/MANIFEST.sha256 --prefix tcad/ "
        "--subset tests/crosscheck_tcad_subset.txt"
    ) in text
    # order: uv, then the image, then the jobs, then the comparison
    steps = [ln for ln in body if ln.startswith("      - ")]
    order = [
        "      - run: uv sync --locked",
        "      - name: Pull the TCAD image of the subset's jobs by digest",
        "      - name: Regenerate the TCAD subset (temporary --out tree root, never results/tcad)",
        "      - name: verify-subset --kind tcad against results/MANIFEST.sha256",
    ]
    assert [steps.index(s) for s in order] == sorted(steps.index(s) for s in order)
    paths = {ln.strip() for ln in lines[: lines.index("  schedule:")]}
    assert {
        f'- "{p}"'
        for p in (
            "third_party/**", "data/process/**", "docker/TCAD_IMAGE", "docker/TCAD_DEV_IMAGE",
            "src/gf180tcad/tcad/**", "results/tcad/**", "tests/crosscheck_tcad_subset.txt",
        )
    } <= paths  # fmt: skip
