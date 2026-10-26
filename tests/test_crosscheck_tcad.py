# SPDX-License-Identifier: Apache-2.0
"""tools/crosscheck-tcad-run: the TCAD subset's jobs as the real ``gf180tcad.tcad`` commands."""

import importlib.machinery
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from gf180tcad import manifest
from gf180tcad.tcad import TCAD_DEV_IMAGE, image_ref
from gf180tcad.tcad.__main__ import _parser as tcad_parser

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "crosscheck-tcad-run"
SUBSET = REPO / "tests" / "crosscheck_tcad_subset.txt"


def _load():
    loader = importlib.machinery.SourceFileLoader("crosscheck_tcad_run", str(TOOL))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


tool = _load()


def test_commands_are_the_real_moscap_command_lines(tmp_path):
    jobs = manifest.load_subset(SUBSET, kind="tcad")
    cmds = tool.commands(jobs, tmp_path / "out")
    assert len(cmds) == len(jobs) == 2
    for job, cmd in zip(jobs, cmds, strict=True):
        assert cmd[:3] == [sys.executable, "-m", "gf180tcad.tcad"]
        a = tcad_parser().parse_args(cmd[3:])  # exits (SystemExit) on a bad flag
        tree, device, params = job.split("/")
        assert (a.command, a.device, a.dim, a.params) == ("moscap", device, 1, params)
        assert a.out == tmp_path / "out" / tree
        # the committed configuration: default method, image and memory, no overrides
        assert (a.method, a.image, a.mem, a.resume) == ("both", None, None, None)


def test_2d_jobs_are_refused(tmp_path):
    with pytest.raises(ValueError, match="1D"):
        tool.commands(("moscap2d/nfet_05v0/start",), tmp_path)


def test_images_are_the_1d_results_image():
    jobs = manifest.load_subset(SUBSET, kind="tcad")
    assert tool.images(jobs) == [TCAD_DEV_IMAGE] == [image_ref("dev")]
    assert "@sha256:" in TCAD_DEV_IMAGE
    r = subprocess.run(
        [sys.executable, str(TOOL), str(SUBSET), "--images"],
        check=False, capture_output=True, text=True,
    )  # fmt: skip
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == [TCAD_DEV_IMAGE]


def test_out_must_not_overlap_results(tmp_path, monkeypatch):
    # A disposable stand-in for the checkout: if the guard regressed, clean=True would delete
    # this tree, never the real repository or results/.
    fake_repo = tmp_path / "repo"
    fake_results = fake_repo / "results"
    (fake_results / "tcad").mkdir(parents=True)
    (fake_results / "x" / "y").mkdir(parents=True)
    (fake_repo / "keep").write_text("x")
    (fake_results / "tcad" / "keep").write_text("x")
    monkeypatch.setattr(tool, "RESULTS", fake_results.resolve())
    for out in (fake_results, fake_results / "tcad", fake_results / "x" / "y", fake_repo):
        with pytest.raises(ValueError, match="overlaps"):
            tool.check_out(out, clean=True)
    # inside the repository, only tmp/ may be written (and cleaned): QUICK_OUT=src must not
    # delete src
    monkeypatch.setattr(tool, "REPO_ROOT", fake_repo.resolve())
    (fake_repo / "src").mkdir()
    (fake_repo / "src" / "code.py").write_text("x")
    (fake_repo / "tmp" / "q").mkdir(parents=True)
    (fake_repo / "tmp" / "q" / "f").write_text("x")
    # tmp/ itself holds other sessions' logs, so it is refused too: only a directory under it
    for out in (
        fake_repo / "src",
        fake_repo / "src" / "sub",
        fake_repo / "tmpx",
        fake_repo / "tmp",
    ):
        with pytest.raises(ValueError, match="not under tmp/"):
            tool.check_out(out, clean=True)
    assert (fake_repo / "src" / "code.py").exists()
    assert (fake_repo / "tmp" / "q" / "f").exists()
    tool.check_out(fake_repo / "tmp" / "q", clean=True)
    assert not (fake_repo / "tmp" / "q").exists()
    assert (fake_repo / "keep").exists() and (fake_results / "tcad" / "keep").exists()
    full = tmp_path / "full"
    full.mkdir()
    (full / "f").write_text("x")
    with pytest.raises(ValueError, match="not empty"):
        tool.check_out(full, clean=False)
    tool.check_out(full, clean=True)
    assert not full.exists()
    tool.check_out(tmp_path / "absent", clean=False)
    (tmp_path / "empty").mkdir()
    tool.check_out(tmp_path / "empty", clean=False)


def test_cli_refuses_before_running_anything(tmp_path):
    full = tmp_path / "full"
    full.mkdir()
    (full / "keep").write_text("x")
    r = subprocess.run(
        [sys.executable, str(TOOL), str(SUBSET), "--out", str(full)],
        check=False, capture_output=True, text=True,
    )  # fmt: skip
    assert r.returncode != 0 and "not empty" in r.stderr
    assert (full / "keep").read_text() == "x"
