# SPDX-License-Identifier: Apache-2.0
"""tools/restamp-tcad-provenance: bring a TCAD tree's provenance.json to the per-tree generator
hash (issue #34) without regenerating its data, and only that."""

import importlib.machinery
import importlib.util
import json
from pathlib import Path

import pytest

from gf180tcad import io, tcad
from gf180tcad.layout import PROVENANCE_NAME

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "restamp-tcad-provenance"
OLD = "f" * 64  # a generator_sha256 of the old scheme (one hash for every tree)


def _load():
    loader = importlib.machinery.SourceFileLoader("restamp_tcad_provenance", str(TOOL))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


tool = _load()


@pytest.fixture(autouse=True)
def results_root(tmp_path, monkeypatch):
    """The registry's tree paths are relative to results/: here, a results/ under tmp_path."""
    monkeypatch.setattr(tool, "RESULTS_ROOT", tmp_path / "results")
    return tmp_path / "results"


def _old_scheme_tree(tmp_path: Path, rel: str = "results/tcad/moscap1d") -> Path:
    """A tree root as the old scheme wrote it: no ``generator``, one shared hash, at
    ``tmp_path/rel``."""
    root = tmp_path / rel
    (root / "nfet_05v0" / "start").mkdir(parents=True)
    prov = tcad.tree_provenance(root, {"moscap1d": "dev"}, generator=tcad.TCAD_MAIN)
    del prov["generator"]
    prov["generator_sha256"] = OLD
    io.write_json(root / PROVENANCE_NAME, prov)
    return root


def _expected(root: Path, generator: str) -> bytes:
    path = root.parent / "expected.json"
    io.write_json(path, tcad.tree_provenance(root, {"moscap1d": "dev"}, generator=generator))
    return path.read_bytes()


def test_restamp_an_old_scheme_tree(tmp_path):
    root = _old_scheme_tree(tmp_path)
    assert tool.restamp(root, tcad.TCAD_MAIN) == (OLD, tcad.generator_sha256(tcad.TCAD_MAIN))
    assert (root / PROVENANCE_NAME).read_bytes() == _expected(root, tcad.TCAD_MAIN)
    # a second restamp finds it current and leaves it alone
    before = (root / PROVENANCE_NAME).stat().st_mtime_ns
    new = tcad.generator_sha256(tcad.TCAD_MAIN)
    assert tool.restamp(root, tcad.TCAD_MAIN) == (new, new)
    assert (root / PROVENANCE_NAME).stat().st_mtime_ns == before


def test_restamp_dry_run_writes_nothing(tmp_path):
    root = _old_scheme_tree(tmp_path)
    before = (root / PROVENANCE_NAME).read_bytes()
    assert tool.restamp(root, tcad.TCAD_MAIN, write=False)[0] == OLD
    assert (root / PROVENANCE_NAME).read_bytes() == before


@pytest.mark.parametrize(
    "spoil",
    [
        lambda p: p.update(gplugins_commit="0" * 40),
        lambda p: p["images"]["moscap1d"].update(ref="ghcr.io/x/y@sha256:" + "0" * 64),
        lambda p: p["images"]["moscap1d"].update(name="stable"),
        lambda p: p.update(calibration={"nfet_05v0": {"file_sha256": "0", "param_sha256": "0"}}),
    ],
    ids=["plugin", "image-ref", "image-name", "calibration"],
)
def test_restamp_refuses_anything_but_the_generator_hash(tmp_path, spoil):
    root = _old_scheme_tree(tmp_path)
    prov = json.loads((root / PROVENANCE_NAME).read_bytes())
    spoil(prov)
    io.write_json(root / PROVENANCE_NAME, prov)
    before = (root / PROVENANCE_NAME).read_bytes()
    with pytest.raises(ValueError, match="regenerate"):
        tool.restamp(root, tcad.TCAD_MAIN)
    assert (root / PROVENANCE_NAME).read_bytes() == before


def test_restamp_refuses_a_tree_without_provenance(tmp_path):
    with pytest.raises(FileNotFoundError):
        tool.restamp(tmp_path, tcad.TCAD_MAIN)


def test_restamp_refuses_another_writer(tmp_path):
    """A tree already stamped by one entry point is never restamped to the other."""
    root = _old_scheme_tree(tmp_path)
    tool.restamp(root, tcad.TCAD_MAIN)
    with pytest.raises(ValueError, match="gf180tcad.tcad.__main__"):
        tool.restamp(root, tcad.CALIBRATE_MAIN)


def test_main_picks_the_writer_by_tree_path(tmp_path, capsys):
    root = _old_scheme_tree(tmp_path, "results/tcad/validation")
    assert tool.main([str(root)]) == 0
    out = capsys.readouterr().out
    new = tcad.generator_sha256(tcad.CALIBRATE_MAIN)
    assert f"{OLD} -> {new}" in out and "gf180tcad.calibrate.__main__" in out
    assert "not regenerated" in out
    assert (root / PROVENANCE_NAME).read_bytes() == _expected(root, tcad.CALIBRATE_MAIN)
    assert tool.main([str(root)]) == 0
    assert "current" in capsys.readouterr().out


def test_main_needs_a_known_tree_or_generator(tmp_path, capsys):
    root = _old_scheme_tree(tmp_path, "elsewhere")
    assert tool.main([str(root)]) == 2
    assert "--generator" in capsys.readouterr().err
    assert tool.main([str(root), "--generator", tcad.TCAD_MAIN, "--dry-run"]) == 0
    assert json.loads((root / PROVENANCE_NAME).read_bytes())["generator_sha256"] == OLD
    assert tool.main([str(root), "--generator", tcad.TCAD_MAIN]) == 0
    assert (root / PROVENANCE_NAME).read_bytes() == _expected(root, tcad.TCAD_MAIN)


def test_main_reports_a_refusal(tmp_path, capsys):
    root = _old_scheme_tree(tmp_path)
    prov = json.loads((root / PROVENANCE_NAME).read_bytes())
    prov["gplugins_commit"] = "0" * 40
    io.write_json(root / PROVENANCE_NAME, prov)
    assert tool.main([str(root)]) == 2
    assert "gplugins_commit" in capsys.readouterr().err


def test_main_refuses_a_generator_other_than_the_tree_s_writer(tmp_path, capsys):
    """For a registered tree, --generator may only repeat TREE_GENERATORS, never override it."""
    root = _old_scheme_tree(tmp_path, "results/tcad/moscap2d")
    before = (root / PROVENANCE_NAME).read_bytes()
    assert tool.main([str(root), "--generator", tcad.CALIBRATE_MAIN]) == 2
    err = capsys.readouterr().err
    assert "gf180tcad.tcad.__main__" in err and "moscap2d" in err
    assert (root / PROVENANCE_NAME).read_bytes() == before
    assert tool.main([str(root), "--generator", tcad.TCAD_MAIN]) == 0
    assert (root / PROVENANCE_NAME).read_bytes() == _expected(root, tcad.TCAD_MAIN)


def test_main_writes_nothing_if_any_tree_refuses(tmp_path, capsys):
    """Every tree is checked before any is written: a refusal leaves all of them unchanged."""
    good = _old_scheme_tree(tmp_path, "results/tcad/moscap1d")
    bad = _old_scheme_tree(tmp_path, "results/tcad/moscap2d")
    prov = json.loads((bad / PROVENANCE_NAME).read_bytes())
    prov["gplugins_commit"] = "0" * 40
    io.write_json(bad / PROVENANCE_NAME, prov)
    before = {p: (p / PROVENANCE_NAME).read_bytes() for p in (good, bad)}
    assert tool.main([str(good), str(bad)]) == 2
    assert "gplugins_commit" in capsys.readouterr().err
    for p, b in before.items():
        assert (p / PROVENANCE_NAME).read_bytes() == b, p
    # an unknown tree name after a good one: nothing written either
    other = _old_scheme_tree(tmp_path, "elsewhere")
    assert tool.main([str(good), str(other)]) == 2
    assert (good / PROVENANCE_NAME).read_bytes() == before[good]


def test_restamp_resolves_writer_by_tree_path(tmp_path, capsys):
    """Charon plan Task B0: the writer comes from the tree's path relative to results/, never
    from its base name. A tree named like a DEVSIM tree in another root (results/tcad-charon/
    moscap1d), or outside results/, is not a registered tree and needs --generator."""
    assert tool.tree_key(tmp_path / "results" / "tcad" / "moscap1d") == "tcad/moscap1d"
    assert tool.tree_key(tmp_path / "results" / "tcad" / "moscap1d" / ".") == "tcad/moscap1d"
    assert tool.tree_key(tmp_path / "moscap1d") is None
    assert tool.tree_key(REPO / "results" / "tcad" / "meshconv", REPO / "results") == (
        "tcad/meshconv"
    )
    for rel in ("results/tcad-charon/moscap1d", "results/moscap1d", "moscap1d"):
        root = _old_scheme_tree(tmp_path, rel)
        before = (root / PROVENANCE_NAME).read_bytes()
        assert tool.main([str(root)]) == 2, rel
        assert "--generator" in capsys.readouterr().err
        assert (root / PROVENANCE_NAME).read_bytes() == before
    # every registered tree resolves to its registry writer
    for key, writer in tcad.TREE_GENERATORS.items():
        assert tool._writer(tmp_path / "results" / key, None) == writer, key
    # the committed trees resolve through the real results/ root
    for prov in sorted((REPO / "results").glob(f"tcad*/*/{PROVENANCE_NAME}")):
        key = tool.tree_key(prov.parent, REPO / "results")
        assert tcad.TREE_GENERATORS[key] == json.loads(prov.read_bytes())["generator"], key
