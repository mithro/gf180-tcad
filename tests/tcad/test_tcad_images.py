# SPDX-License-Identifier: Apache-2.0
"""Which TCAD image makes which results (gf180tcad.tcad.RESULTS_IMAGE), on the host.

The 1D results come from the dev-HEAD image (docker/TCAD_DEV_IMAGE); the 2D results stay on the
stable image (docker/TCAD_IMAGE) until 2D has its own mesh convergence on dev. ``--image`` picks
the other one, and the tree's provenance.json records which made it. ``sandbox.run`` is replaced
by a stand-in that writes the job's files, so nothing here runs a container.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from gf180tcad import sandbox, tcad
from gf180tcad.layout import PROVENANCE_NAME
from gf180tcad.tcad import __main__ as cli
from gf180tcad.tcad import meshconv, moscap1d

REPO = Path(__file__).resolve().parents[2]
DEV_REF = (REPO / "docker" / "TCAD_DEV_IMAGE").read_text(encoding="utf-8").strip()
STABLE_REF = (REPO / "docker" / "TCAD_IMAGE").read_text(encoding="utf-8").strip()
DEV_VERSIONS = json.loads((REPO / "docker" / "tcad-dev" / "versions.json").read_bytes())
STABLE_VERSIONS = json.loads((REPO / "docker" / "tcad" / "versions.json").read_bytes())


def test_results_images():
    assert tcad.RESULTS_IMAGE == {"moscap1d": "dev", "moscap2d": "stable"}
    assert tcad.image_ref("dev") == tcad.TCAD_DEV_IMAGE == DEV_REF
    assert tcad.image_ref("stable") == tcad.TCAD_IMAGE == STABLE_REF
    assert tcad.image_versions("dev") == DEV_VERSIONS
    assert tcad.image_versions("stable") == STABLE_VERSIONS
    with pytest.raises(KeyError):
        tcad.image_ref("latest")


@pytest.mark.parametrize(("dim", "default"), [(1, "dev"), (2, "stable")])
def test_job_image_defaults_by_dimension(dim, default):
    assert cli.job_image(dim, None) == default
    for name in ("dev", "stable"):
        assert cli.job_image(dim, name) == name


class FakeSandbox:
    """``sandbox.run`` stand-in: records the image and writes the files the job would write."""

    def __init__(self):
        self.images: list[str] = []

    def __call__(self, cmd, out_dir, image, mem, cpus):
        self.images.append(image)
        out = Path(out_dir)
        if cmd[3] == "moscap-job":
            for name in (moscap1d.PER_AREA_CSV, moscap1d.PER_AREA_META):
                (out / name).write_text("data\n", encoding="utf-8")
        elif "--assemble" in cmd:
            for name in (meshconv.REPORT_NAME, meshconv.SELECTED_NAME):
                (out / name).write_text("{}\n", encoding="utf-8")
        else:
            (out / cli.LEVEL_NAME).write_text("{}\n", encoding="utf-8")
        return SimpleNamespace(stdout="", stderr="", returncode=0)


@pytest.fixture
def fake(monkeypatch) -> FakeSandbox:
    f = FakeSandbox()
    monkeypatch.setattr(sandbox, "run", f)
    return f


def _images(root: Path) -> dict:
    return json.loads((root / PROVENANCE_NAME).read_bytes())["images"]


def _entry(name: str) -> dict:
    ref, versions = {"dev": (DEV_REF, DEV_VERSIONS), "stable": (STABLE_REF, STABLE_VERSIONS)}[name]
    return {"name": name, "ref": ref, "versions": versions}


def _moscap(root: Path, *extra: str) -> int:
    argv = ["moscap", "--device", "nfet_05v0", "--dim", "1", "--params", "start"]
    return cli.main([*argv, "--out", str(root), *extra])


def _meshconv(root: Path, *extra: str) -> int:
    argv = ["meshconv", "--device", "nfet_05v0", "--dim", "1", "--out", str(root), "--jobs", "1"]
    return cli.main([*argv, *extra])


def test_moscap_1d_runs_on_dev_by_default(fake, tmp_path):
    assert _moscap(tmp_path / "root") == 0
    assert fake.images == [DEV_REF]
    assert _images(tmp_path / "root") == {"moscap1d": _entry("dev")}


def test_moscap_1d_on_stable_when_asked(fake, tmp_path):
    assert _moscap(tmp_path / "root", "--image", "stable") == 0
    assert fake.images == [STABLE_REF]
    assert _images(tmp_path / "root") == {"moscap1d": _entry("stable")}


def test_meshconv_1d_runs_on_dev_by_default(fake, tmp_path):
    assert _meshconv(tmp_path / "root") == 0
    assert set(fake.images) == {DEV_REF} and len(fake.images) == len(meshconv.LEVELS) + 1
    assert _images(tmp_path / "root") == {"moscap1d": _entry("dev")}


def test_meshconv_keeps_the_other_dimension_s_image(fake, tmp_path):
    """The meshconv tree root holds 1D and 2D results, each recorded with its own image."""
    root = tmp_path / "root"
    (root / "moscap2d" / "nfet_05v0").mkdir(parents=True)
    prov = tcad.tree_provenance(root, {"moscap2d": "stable"})
    (root / PROVENANCE_NAME).write_text(json.dumps(prov), encoding="utf-8")
    assert _meshconv(root) == 0
    assert _images(root) == {"moscap1d": _entry("dev"), "moscap2d": _entry("stable")}
    # a rerun on stable replaces the 1D entry only
    assert _meshconv(root, "--image", "stable") == 0
    assert _images(root) == {"moscap1d": _entry("stable"), "moscap2d": _entry("stable")}


def test_recorded_images_only_for_present_subtrees(tmp_path):
    root = tmp_path / "root"
    (root / "moscap1d").mkdir(parents=True)
    prov = tcad.tree_provenance(root, {"moscap1d": "dev", "moscap2d": "stable"})
    (root / PROVENANCE_NAME).write_text(json.dumps(prov), encoding="utf-8")
    assert tcad.recorded_images(root) == {"moscap1d": "dev"}
    assert tcad.recorded_images(tmp_path / "nothing") == {}


def test_image_choice_is_checked(capsys):
    with pytest.raises(SystemExit):
        _moscap(Path("unused"), "--image", "latest")
    assert "invalid choice" in capsys.readouterr().err


def test_moscap_refuses_to_mix_images_in_one_tree(fake, tmp_path):
    """A tree's provenance records one image per kind, so a run on another image is refused
    while the kind's other job directories would stay from the first one."""
    root = tmp_path / "root"
    assert _moscap(root) == 0  # nfet_05v0/start on dev
    other = ["moscap", "--device", "pfet_05v0", "--dim", "1", "--params", "start"]
    # the only job directory is the one a stable rerun replaces: allowed (the whole kind)
    assert _moscap(root, "--image", "stable") == 0
    assert _images(root) == {"moscap1d": _entry("stable")}
    # now the kind holds nfet_05v0/start from stable; pfet on dev would mix them
    with pytest.raises(ValueError, match=r"records moscap1d results made on the 'stable' image"):
        cli.main([*other, "--out", str(root)])
    assert fake.images == [DEV_REF, STABLE_REF]  # nothing was run for the refused call
    assert not (root / "pfet_05v0").exists()
    # the same image is fine
    assert cli.main([*other, "--out", str(root), "--image", "stable"]) == 0
    assert _images(root) == {"moscap1d": _entry("stable")}


def test_meshconv_refuses_to_mix_images_in_one_tree(fake, tmp_path):
    root = tmp_path / "root"
    assert _meshconv(root) == 0  # nfet_05v0 on dev
    argv = ["meshconv", "--device", "pfet_05v0", "--dim", "1", "--out", str(root), "--jobs", "1"]
    n = len(fake.images)
    with pytest.raises(ValueError, match="would keep .*nfet_05v0 from the 'dev' image"):
        cli.main([*argv, "--image", "stable"])
    assert len(fake.images) == n
    assert cli.main(argv) == 0
    assert _images(root) == {"moscap1d": _entry("dev")}


def test_check_same_image_without_provenance_or_others(tmp_path):
    tcad.check_same_image(tmp_path / "none", "moscap1d", "dev", [tmp_path / "x"])
    root = tmp_path / "root"
    root.mkdir()
    prov = tcad.tree_provenance(root, {"moscap1d": "stable"})
    (root / PROVENANCE_NAME).write_text(json.dumps(prov), encoding="utf-8")
    tcad.check_same_image(root, "moscap1d", "dev", [root / "absent"])  # nothing would be kept
