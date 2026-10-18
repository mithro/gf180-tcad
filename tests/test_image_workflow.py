# SPDX-License-Identifier: Apache-2.0
"""Structure of .github/workflows/image.yml and of the TCAD image docs/tool links.

- every matrix entry's from-scratch rebuild runs even when another entry's build failed (a
  base-only change makes the tcad entry fail until its pins are refreshed);
- the published tags (pr-<n>, latest, sha-<commit>) are applied only after the IMAGE_ID, pin and
  versions checks passed; the build itself pushes only the staging tag `unverified`.
"""

import ast
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "image.yml"


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def test_rebuild_runs_for_every_entry_unless_cancelled():
    rebuild = _jobs()["rebuild"]
    assert rebuild["needs"] == "build"
    assert rebuild["if"] == "${{ !cancelled() }}"


def _step_index(steps: list[dict], name: str) -> int:
    names = [s.get("name") for s in steps]
    assert name in names, f"no step {name!r} in build: {names}"
    return names.index(name)


def test_published_tags_are_applied_after_the_checks():
    steps = _jobs()["build"]["steps"]
    build = steps[_step_index(steps, "Build (and push the staging tag on PRs / main)")]
    # The build pushes only the staging tag, never a published one.
    assert ':unverified"' in build["run"]
    assert "pr-" not in build["run"] and "latest" not in build["run"]
    tag = _step_index(steps, "Tag the verified image")
    for check in (
        "Config digest matches IMAGE_ID",
        "Manifest matches the pin file",
        "versions.json matches the probe run in the pinned image",
    ):
        assert _step_index(steps, check) < tag, check
    run = steps[tag]["run"]
    assert steps[tag]["if"] == "env.PUSH == 'true'"
    for published in ("pr-${{ github.event.pull_request.number }}", ":latest", ":sha-"):
        assert published in run, published
    # retag by digest (the pin), keeping the manifest digest, then verify it
    assert "imagetools create --prefer-index=false" in run
    assert "imagetools inspect" in run


def _conf_tools() -> dict[str, tuple[str, str]]:
    tree = ast.parse((REPO_ROOT / "docs" / "conf.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "_TOOLS":
            return ast.literal_eval(node.value)
    raise AssertionError("no _TOOLS in docs/conf.py")


def test_gplugins_links_upstream_and_the_fork_separately():
    tools = _conf_tools()
    assert tools["gplugins"][1] == "https://github.com/gdsfactory/gplugins"
    assert tools["gplugins_fork"][1] == "https://github.com/mithro/gplugins"


def test_image_docs_name_the_sandbox_environment():
    text = (REPO_ROOT / "docs" / "reproduce" / "image.md").read_text(encoding="utf-8")
    tcad = text[text.index("(tcad-image)=") :]
    assert "NPY_DISABLE_CPU_FEATURES" in tcad
    assert "{{ gplugins_fork }}" in tcad
    # the single-PR base-change sequence
    base_change = tcad[tcad.index("### Changing the base image") :]
    step1 = re.search(r"^1\. (.*?)^2\. ", base_change, re.MULTILINE | re.DOTALL)
    assert step1 and "{repo}`docker/IMAGE`" in step1.group(1)
    assert re.search(r"^5\. .*green", base_change, re.MULTILINE)
