# SPDX-License-Identifier: Apache-2.0
"""The render manifest (:mod:`gf180tcad.render.manifest`), its readers
(:mod:`gf180tcad.quantity`) and the display-only constants (``data/render/display.toml``).

Every committed ``results/renders/**/*.render.json`` is re-read from its named sources. The
synthetic manifest under ``tests/fixtures/renders/`` is the positive control; the negative
controls change one thing in a copy of it and check that verification fails for that reason.
"""

import importlib.util
import json
import re
import shutil
import tomllib
from pathlib import Path

import pytest

from gf180tcad.render import manifest as rm

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path("tests") / "fixtures" / "renders"
FIXTURE_MANIFEST = FIXTURE / "r-test.render.json"
DISPLAY = ROOT / "data" / "render" / "display.toml"
LITERATURE = ROOT / "docs" / "limitations" / "literature.md"


def _committed_manifests() -> list[Path]:
    return sorted((ROOT / "results" / "renders").glob("**/*.render.json"))


def _copy_fixture(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / FIXTURE, tmp_path / FIXTURE)
    return tmp_path


def _load_maker():
    spec = importlib.util.spec_from_file_location(
        "make_fixture", ROOT / FIXTURE / "make_fixture.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- committed renders ------------------------------------------------------------------------


def test_every_entry_rereads_its_source():
    """Every committed manifest verifies against the files it names (none before task R3)."""
    problems = {}
    for path in _committed_manifests():
        m = rm.Manifest.load(path)
        found = m.verify(ROOT) + m.display_problems()
        if found:
            problems[path.relative_to(ROOT).as_posix()] = found
    assert not problems, problems


def test_display_entries_come_from_the_display_file():
    """A committed manifest takes its display-only values from data/render/display.toml only,
    and every entry read from that file has the role display. The fixture's own display file
    is the negative control."""
    assert rm.DISPLAY_SOURCE == "data/render/display.toml"
    assert (ROOT / rm.DISPLAY_SOURCE).is_file()
    m = rm.Manifest.load(ROOT / FIXTURE_MANIFEST)
    assert m.display_problems() == [
        (
            "e_g: role display read from tests/fixtures/renders/sources/display.toml, "
            "not data/render/display.toml"
        )
    ]
    m.quantities["e_g"].source = rm.DISPLAY_SOURCE
    assert m.display_problems() == []
    m.quantities["e_g"].role = "value"
    assert m.display_problems() == ["e_g: read from data/render/display.toml with role value"]


def test_exaggeration_strings_match_scales():
    """Every entry with scale != 1 has its exaggeration string, in the committed manifests and
    in the fixture; a manifest without it fails."""
    for path in [*_committed_manifests(), ROOT / FIXTURE_MANIFEST]:
        m = rm.Manifest.load(path)
        for name, q in m.quantities.items():
            if q.scale is not None and q.scale != 1:
                assert rm.exaggeration_text(q.label, q.scale) in m.exaggeration, (path, name)
    m = rm.Manifest.load(ROOT / FIXTURE_MANIFEST)
    m.exaggeration = [s for s in m.exaggeration if "oxide thickness" not in s]
    assert any("t_ox: no exaggeration string" in p for p in m.verify(ROOT))


def test_exaggeration_text():
    assert rm.exaggeration_text("oxide thickness", 40.0) == "oxide thickness ×40, not to scale"
    assert rm.exaggeration_text("depth", 0.25) == "depth ×0.25, not to scale"


# --- the positive control ---------------------------------------------------------------------


def test_fixture_verifies():
    m = rm.Manifest.load(ROOT / FIXTURE_MANIFEST)
    assert m.verify(ROOT) == []
    assert set(m.quantities) >= {"t_ox", "vg", "psi", "cv", "psi_at_0", "first_c", "e_g", "e_c"}


def test_fixture_is_the_builder_output(tmp_path):
    """The committed fixture manifest is what the builder writes from the fixture sources."""
    out = tmp_path / "rebuilt.render.json"
    _load_maker().build(ROOT).dump(out)
    assert out.read_bytes() == (ROOT / FIXTURE_MANIFEST).read_bytes()


def test_dump_load_round_trip(tmp_path):
    m = rm.Manifest.load(ROOT / FIXTURE_MANIFEST)
    out = tmp_path / "again.render.json"
    m.dump(out)
    assert out.read_bytes() == (ROOT / FIXTURE_MANIFEST).read_bytes()


# --- the negative controls --------------------------------------------------------------------


def test_missing_source_fails(tmp_path):
    root = _copy_fixture(tmp_path)
    (root / FIXTURE / "sources" / "stack.meta.json").unlink()
    problems = rm.Manifest.load(root / FIXTURE_MANIFEST).verify(root)
    assert any("t_ox: source missing" in p for p in problems), problems


def test_changed_value_fails(tmp_path):
    root = _copy_fixture(tmp_path)
    meta = root / FIXTURE / "sources" / "stack.meta.json"
    d = json.loads(meta.read_text(encoding="utf-8"))
    d["stack"]["t_ox_nm"] = 16.5
    meta.write_text(json.dumps(d), encoding="utf-8")
    problems = rm.Manifest.load(root / FIXTURE_MANIFEST).verify(root)
    assert any(p.startswith("t_ox: value 16.5 != recorded 16.4") for p in problems), problems


def test_changed_array_fails(tmp_path):
    root = _copy_fixture(tmp_path)
    csv = root / FIXTURE / "sources" / "curve.csv"
    csv.write_text(csv.read_text(encoding="utf-8").replace("0.3,", "0.31,"), encoding="utf-8")
    problems = rm.Manifest.load(root / FIXTURE_MANIFEST).verify(root)
    assert any(p.startswith("psi: value_sha256") for p in problems), problems
    # The derived band edge reads psi, so it fails too.
    assert any(p.startswith("e_c: value_sha256") for p in problems), problems


def test_input_hashes_current(tmp_path):
    """A source whose bytes changed fails even when the selected values did not."""
    root = _copy_fixture(tmp_path)
    csv = root / FIXTURE / "sources" / "curve.csv"
    csv.write_text("# an added comment line\n" + csv.read_text(encoding="utf-8"), encoding="utf-8")
    problems = rm.Manifest.load(root / FIXTURE_MANIFEST).verify(root)
    assert problems == [f"input {(FIXTURE / 'sources' / 'curve.csv').as_posix()}: sha256 changed"]


def test_source_not_in_inputs_fails():
    m = rm.Manifest.load(ROOT / FIXTURE_MANIFEST)
    del m.inputs[(FIXTURE / "sources" / "display.toml").as_posix()]
    assert any("e_g: source not listed in inputs" in p for p in m.verify(ROOT))


def test_derived_entries_reevaluate():
    """Each derived entry is recomputed from its inputs through gf180tcad.derive."""
    m = rm.Manifest.load(ROOT / FIXTURE_MANIFEST)
    assert m.quantities["e_c"].derived == "band_edge_ec"
    assert m.quantities["e_c_at_0"].value == pytest.approx(-0.1 + 1.12 / 2, abs=1e-15)
    m.quantities["e_c_at_0"].value = 0.47
    assert any(p.startswith("e_c_at_0: derived value") for p in m.verify(ROOT))


def test_derived_refuses_unknown_formula_and_input():
    d = json.loads((ROOT / FIXTURE_MANIFEST).read_text(encoding="utf-8"))
    d["quantities"]["e_c"]["derived"] = "invented_formula"
    with pytest.raises(ValueError, match="e_c: no formula 'invented_formula'"):
        rm.Manifest.from_dict(d)
    d = json.loads((ROOT / FIXTURE_MANIFEST).read_text(encoding="utf-8"))
    d["quantities"]["e_c"]["inputs"] = ["psi", "nowhere"]
    with pytest.raises(ValueError, match="e_c: input 'nowhere' is not a quantity"):
        rm.Manifest.from_dict(d)
    d = json.loads((ROOT / FIXTURE_MANIFEST).read_text(encoding="utf-8"))
    d["quantities"]["e_c"]["inputs"] = ["psi"]
    with pytest.raises(ValueError, match="e_c: band_edge_ec takes 2 inputs"):
        rm.Manifest.from_dict(d)


def test_derived_cycle_refused():
    d = json.loads((ROOT / FIXTURE_MANIFEST).read_text(encoding="utf-8"))
    d["quantities"]["e_c"]["inputs"] = ["e_c", "e_g"]
    with pytest.raises(ValueError, match="cycle"):
        rm.Manifest.from_dict(d)


def test_scale_required_on_geometry_and_axes():
    d = json.loads((ROOT / FIXTURE_MANIFEST).read_text(encoding="utf-8"))
    del d["quantities"]["t_ox"]["scale"]
    with pytest.raises(ValueError, match="t_ox: role 'geometry' needs a scale"):
        rm.Manifest.from_dict(d)
    d = json.loads((ROOT / FIXTURE_MANIFEST).read_text(encoding="utf-8"))
    del d["quantities"]["vg"]["scale"]
    with pytest.raises(ValueError, match="vg: role 'axis' needs a scale"):
        rm.Manifest.from_dict(d)
    d = json.loads((ROOT / FIXTURE_MANIFEST).read_text(encoding="utf-8"))
    del d["quantities"]["t_ox"]["label"]
    with pytest.raises(ValueError, match="t_ox: scale 40.0 needs a label"):
        rm.Manifest.from_dict(d)


def test_manifest_schema_closed():
    d = json.loads((ROOT / FIXTURE_MANIFEST).read_text(encoding="utf-8"))
    d["colour"] = "red"
    with pytest.raises(ValueError, match="unknown key"):
        rm.Manifest.from_dict(d)
    d = json.loads((ROOT / FIXTURE_MANIFEST).read_text(encoding="utf-8"))
    d["format"] = 2
    with pytest.raises(ValueError, match="format"):
        rm.Manifest.from_dict(d)
    d = json.loads((ROOT / FIXTURE_MANIFEST).read_text(encoding="utf-8"))
    d["quantities"]["t_ox"]["role"] = "decoration"
    with pytest.raises(ValueError, match="t_ox: role 'decoration'"):
        rm.Manifest.from_dict(d)
    d = json.loads((ROOT / FIXTURE_MANIFEST).read_text(encoding="utf-8"))
    d["quantities"]["t_ox"]["value_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="t_ox: exactly one of value and value_sha256"):
        rm.Manifest.from_dict(d)


# --- the display-only constants ---------------------------------------------------------------


def _anchors() -> set[str]:
    return set(
        re.findall(r"^\((lit-[a-z0-9-]+)\)=$", LITERATURE.read_text(encoding="utf-8"), re.MULTILINE)
    )


def test_display_constants_have_sources_and_note():
    d = tomllib.loads(DISPLAY.read_text(encoding="utf-8"))
    assert d["note"] == "display only: not an input to any simulation"
    anchors = _anchors()
    sections = {k: v for k, v in d.items() if isinstance(v, dict)}
    assert set(sections) == {"silicon", "sio2"}
    want = {
        "silicon": {"band_gap_ev", "nc_cm3", "nv_cm3"},
        "sio2": {"band_gap_ev", "conduction_offset_ev", "valence_offset_ev"},
    }
    for name, sec in sections.items():
        values = {k for k, v in sec.items() if isinstance(v, int | float)}
        assert values == want[name], name
        assert set(sec["sources"]) == values and set(sec["units"]) == values, name
        for key in values:
            cited = re.findall(r"\blit-[a-z0-9-]+\b", sec["sources"][key])
            assert cited and set(cited) <= anchors, (name, key, sec["sources"][key])
    assert d["silicon"]["band_gap_ev"] == 1.12


def test_display_offsets_add_up_to_the_oxide_gap():
    """E_g(SiO2) = E_g(Si) + both offsets, to the 0.1 eV the cited values carry."""
    d = tomllib.loads(DISPLAY.read_text(encoding="utf-8"))
    si, ox = d["silicon"], d["sio2"]
    total = si["band_gap_ev"] + ox["conduction_offset_ev"] + ox["valence_offset_ev"]
    assert total == pytest.approx(ox["band_gap_ev"], abs=0.1)


def test_display_mismatch_statement_matches_the_simulation():
    """The file states the band gap the simulation's n_i scaling implies: 2 * 6726 K * k_B/q."""
    from gf180tcad.tcad import process

    d = tomllib.loads(DISPLAY.read_text(encoding="utf-8"))
    src = (ROOT / "src" / "gf180tcad" / "tcad" / "process.py").read_text(encoding="utf-8")
    assert "math.exp(-6726.0 * (1 / t - 1 / 300.0))" in src
    c = process.CONSTANTS
    implied = 2 * 6726.0 * c.k_b_j_per_k / c.q_c
    assert f"{implied:.2f}" == "1.16"
    assert "E_g = 1.16 eV" in d["mismatch"] and "1.12 eV" in d["mismatch"]
    assert f"T = {c.t_k} K" in d["mismatch"]


@pytest.mark.parametrize(
    "bad", ["/etc/passwd", "../outside.json", "results/../../x.csv", "a\\b.csv", ""]
)
def test_paths_must_be_repo_relative(bad):
    """A source or an input outside the repo is refused, so every number traces to a repo file."""
    d = json.loads((ROOT / FIXTURE_MANIFEST).read_text(encoding="utf-8"))
    d["quantities"]["t_ox"]["source"] = bad
    with pytest.raises(ValueError, match="t_ox: .*repo-relative"):
        rm.Manifest.from_dict(d)
    d = json.loads((ROOT / FIXTURE_MANIFEST).read_text(encoding="utf-8"))
    d["inputs"][bad] = "0" * 64
    with pytest.raises(ValueError, match="repo-relative"):
        rm.Manifest.from_dict(d)
