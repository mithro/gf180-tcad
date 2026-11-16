# SPDX-License-Identifier: Apache-2.0
"""tools/crosscheck-history-run and ``manifest verify-files``: the committed latest-stack
plugin-history records rebuilt by the real ``gf180tcad.history`` commands and compared byte for
byte (issue #181)."""

import hashlib
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from gf180tcad import history, manifest

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "crosscheck-history-run"
WORKFLOW = REPO / ".github" / "workflows" / "crosscheck.yml"


def _load():
    loader = importlib.machinery.SourceFileLoader("crosscheck_history_run", str(TOOL))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


tool = _load()


def test_latest_records_are_the_committed_ones():
    """Both latest-stack records, each at the mesh scale it holds, and the name history gives a
    record of that scale is the committed file's."""
    recs = tool.latest_records()
    assert recs == {"latest-mesh0p5.json": 0.5, "latest.json": 1.0}
    for name, scale in recs.items():
        assert history.result_name(history.LATEST, scale) == name


def test_commands_are_the_real_history_command_lines(tmp_path):
    cmds = tool.commands(tmp_path / "out")
    assert len(cmds) == 2
    scales = []
    for cmd in cmds:
        assert cmd[:3] == [sys.executable, "-m", "gf180tcad.history"]
        a = history.parse_args(cmd[3:])  # exits (SystemExit) on a bad flag
        assert (a.version, a.out, a.workdir) == (history.LATEST, tmp_path / "out", None)
        scales.append(a.mesh_scale)
    assert sorted(scales) == [0.5, 1.0]


def test_images_is_the_stable_tcad_image(capsys):
    assert tool.main(["--images"]) == 0
    ref = capsys.readouterr().out.strip()
    assert ref == (REPO / "docker" / "TCAD_IMAGE").read_text("utf-8").splitlines()[0].strip()
    assert "@sha256:" in ref


@pytest.mark.parametrize("where", ["results", "results/plugin-history", "repo", "tmp"])
def test_out_must_not_overlap_results_or_the_repo(where):
    out = {"results": REPO / "results", "results/plugin-history": REPO / "results/plugin-history",
           "repo": REPO / "docs", "tmp": REPO / "tmp"}[where]  # fmt: skip
    with pytest.raises(ValueError):
        tool.check_out(out, clean=False)


def test_out_must_be_empty_unless_clean(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "x").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="not empty"):
        tool.check_out(out, clean=False)
    tool.check_out(out, clean=True)
    assert not out.exists()


def test_check_written_requires_exactly_the_committed_names(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "latest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="not the committed records"):
        tool.check_written(out)  # one missing
    (out / "latest-mesh0p5.json").write_text("{}", encoding="utf-8")
    tool.check_written(out)
    (out / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="not the committed records"):
        tool.check_written(out)


def _manifest(tmp_path: Path, entries: dict[str, bytes]) -> Path:
    lines = sorted(f"{hashlib.sha256(b).hexdigest()}  {rel}\n" for rel, b in entries.items())
    m = tmp_path / "MANIFEST.sha256"
    m.write_text("".join(lines), encoding="utf-8")
    return m


def test_verify_files(tmp_path):
    m = _manifest(tmp_path, {"plugin-history/a.json": b"a", "plugin-history/b.json": b"b",
                             "plugin-history/old.json": b"o"})  # fmt: skip
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.json").write_bytes(b"a")
    assert manifest.verify_files(out, m, "plugin-history/") == []  # other entries not required
    (out / "b.json").write_bytes(b"B")
    (out / "c.json").write_bytes(b"c")
    assert manifest.verify_files(out, m, "plugin-history/") == [
        ("plugin-history/b.json", "changed"),
        ("plugin-history/c.json", "not in manifest"),
    ]
    assert manifest.main(["verify-files", str(out), "--against", str(m),
                          "--prefix", "plugin-history/"]) == 1  # fmt: skip


def test_verify_files_refuses_an_empty_tree_and_a_bad_prefix(tmp_path):
    m = _manifest(tmp_path, {"plugin-history/a.json": b"a"})
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(ValueError, match="no files"):
        manifest.verify_files(out, m, "plugin-history/")
    (out / "a.json").write_bytes(b"a")
    with pytest.raises(ValueError, match="prefix"):
        manifest.verify_files(out, m, "plugin-history")


def test_committed_records_verify_against_the_manifest(tmp_path):
    """The committed latest-stack records pass verify-files against the committed manifest, as
    the workflow's rebuilt ones must."""
    out = tmp_path / "out"
    out.mkdir()
    for name in tool.latest_records():
        (out / name).write_bytes((REPO / "results" / "plugin-history" / name).read_bytes())
    assert manifest.verify_files(out, REPO / "results" / "MANIFEST.sha256", "plugin-history/") == []


def test_workflow_runs_the_tool_and_verify_files():
    """The crosscheck-tcad job pulls the image, rebuilds the records and compares them."""
    text = WORKFLOW.read_text("utf-8")
    job = text.split("\n  crosscheck-tcad:\n", 1)[1]
    assert "tools/crosscheck-history-run --images" in job
    assert "tools/crosscheck-history-run --out" in job
    assert "verify-files" in job and "--prefix plugin-history/" in job
    steps = job.split("      - name: ")
    for title in ("Pull the image of the latest-stack", "Rebuild the latest-stack",
                  "verify-files of the plugin-history"):  # fmt: skip
        (step,) = [s for s in steps if s.startswith(title)]
        assert "if: success() || failure()" in step, title


def test_records_hold_their_mesh_scale():
    for name, scale in tool.latest_records().items():
        rec = json.loads((REPO / "results" / "plugin-history" / name).read_bytes())
        assert rec["gplugins_tag"] == history.LATEST and rec["mesh_scale"] == scale
