# SPDX-License-Identifier: Apache-2.0
"""TCAD provenance: TCAD_GENERATORS and every committed tree root's provenance.json.

As for the SPICE reference (tests/test_reference.py, tests/test_results_provenance.py), each TCAD
entry point's hashed module list is tied to its own import graph (issue #34: one list per entry
point, so a change to code a tree's writer never imports leaves that tree's hash alone), each
committed tree root is tied to the entry point that writes it (TREE_GENERATORS), and each
committed ``results/tcad/<tree>/provenance.json`` must equal what that entry point would write
now. These need the plugin submodule checked out (``git submodule update --init``).
"""

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from gf180tcad import manifest, reference, sandbox, tcad
from gf180tcad.layout import PROVENANCE_NAME
from gf180tcad.tcad import calibration

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "results"
TCAD_RESULTS = RESULTS / "tcad"
# The TCAD entry points.
TCAD_MAIN = "gf180tcad.tcad.__main__"
CALIBRATE_MAIN = "gf180tcad.calibrate.__main__"
ROOTS = (TCAD_MAIN, CALIBRATE_MAIN)
# The entry point that writes each tree root (docs/reproduce/index.md, tcad-provenance).
WRITERS = {
    "moscap1d": TCAD_MAIN,
    "moscap2d": TCAD_MAIN,
    "meshconv": TCAD_MAIN,
    "calibration": CALIBRATE_MAIN,
    "validation": CALIBRATE_MAIN,
}
# The tree roots of the plan's results layout (Global Constraints, "Result files").
TREE_ROOTS = ("moscap1d", "moscap2d", "meshconv", "calibration", "validation")
REGENERATE = (
    "regenerate the tree for each device with `uv run --locked python -m ...`: "
    "moscap1d: `gf180tcad.tcad moscap --device <device> --dim 1 --params start` (and "
    "`--params calibrated`) `--out results/tcad/moscap1d`; "
    "moscap2d: `gf180tcad.tcad moscap --device <device> --dim 2 --params start --geometry <gid> "
    "--out results/tcad/moscap2d`, one 16 GiB job at a time (L = 2 um: `--method qs`, then "
    "`--method combine-qs`); "
    "meshconv: `gf180tcad.tcad meshconv --device <device> --dim 1|2 --jobs 1 --out "
    "results/tcad/meshconv`; "
    "calibration: `gf180tcad.calibrate run --device <device> --out results/tcad/calibration`; "
    "validation (after the calibration is committed): `gf180tcad.calibrate validate --device "
    "<device> --out results/tcad/validation`; then `make manifest`. A tree whose data are not "
    "regenerated is restamped with `uv run --locked python tools/restamp-tcad-provenance "
    "results/tcad/<tree>` and recorded on docs/reproduce/index.md (tcad-provenance)"
)


def _ast_import_closure(roots: tuple[str, ...]) -> set[str]:
    """gf180tcad modules imported (transitively, parents included) by ``roots``, from the AST."""
    src = sandbox.REPO_ROOT / "src"

    def file_of(name: str) -> Path | None:
        base = src.joinpath(*name.split("."))
        for f in (base / "__init__.py", base.with_suffix(".py")):
            if f.is_file():
                return f
        return None

    def with_parents(name: str) -> set[str]:
        parts = name.split(".")
        return {".".join(parts[:i]) for i in range(1, len(parts) + 1)}

    seen: set[str] = set()
    todo = list(roots)
    while todo:
        name = todo.pop()
        for m in with_parents(name) - seen:
            seen.add(m)
            tree = ast.parse(file_of(m).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                found = []
                if isinstance(node, ast.Import):
                    found = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    assert node.level == 0, f"{m}: relative import"
                    found = [node.module]
                    found += [f"{node.module}.{a.name}" for a in node.names]
                todo += [
                    f for f in found if f.split(".")[0] == "gf180tcad" and file_of(f) is not None
                ]
    return seen


def test_tcad_generators_are_the_two_entry_points():
    assert tuple(tcad.TCAD_GENERATORS) == ROOTS
    assert (tcad.TCAD_MAIN, tcad.CALIBRATE_MAIN) == ROOTS
    for entry, modules in tcad.TCAD_GENERATORS.items():
        assert entry in modules
        assert list(modules) == sorted(set(modules)), entry


def test_tree_generators_tie_each_tree_to_its_writer():
    assert tcad.TREE_GENERATORS == WRITERS
    assert set(tcad.TREE_GENERATORS) == set(TREE_ROOTS)


@pytest.mark.parametrize("entry", ROOTS)
def test_tcad_generator_modules_match_the_import_graph(entry):
    graph = _ast_import_closure((entry,))
    listed = set(tcad.TCAD_GENERATORS[entry])
    assert not graph - listed, f"imported by {entry} but not hashed: {sorted(graph - listed)}"
    assert not listed - graph, f"hashed for {entry} but not imported: {sorted(listed - graph)}"


@pytest.mark.parametrize("entry", ROOTS)
def test_tcad_generator_modules_match_what_python_loads(entry):
    code = (
        f"import sys, {entry}; "
        "print(' '.join(sorted(m for m in sys.modules if m.split('.')[0] == 'gf180tcad')))"
    )
    res = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=REPO
    )
    assert set(res.stdout.split()) == set(tcad.TCAD_GENERATORS[entry])


def test_the_tcad_entry_point_does_not_hash_the_calibration_code():
    """The point of issue #34: the MOS capacitor and mesh-convergence trees do not depend on the
    calibration-only modules, and the calibration trees do not depend on the CLI of the jobs."""
    tcad_main = set(tcad.TCAD_GENERATORS[TCAD_MAIN])
    calibrate_main = set(tcad.TCAD_GENERATORS[CALIBRATE_MAIN])
    assert {"gf180tcad.calibrate", "gf180tcad.calibrate.cv", "gf180tcad.specwindow"} <= (
        calibrate_main - tcad_main
    )
    assert TCAD_MAIN not in calibrate_main and CALIBRATE_MAIN not in tcad_main


def test_spice_provenance_untouched_by_tcad():
    """No TCAD module is a SPICE generator module, and the reverse holds for the TCAD-only ones."""
    every = {m for modules in tcad.TCAD_GENERATORS.values() for m in modules}
    tcad_only = {m for m in every if m.startswith("gf180tcad.tcad")}
    assert not tcad_only & set(reference.GENERATOR_MODULES)


@pytest.mark.parametrize("entry", ROOTS)
def test_generator_files_cover_plugin_process_and_sandbox(entry):
    files = tcad.generator_files(entry)
    assert "tools/sandbox-run" in files
    assert "data/process/nfet_05v0.toml" in files and "data/process/pfet_05v0.toml" in files
    assert "third_party/gplugins/gplugins/devsim/cv.py" in files
    assert "third_party/gplugins/gplugins/devsim/stack1d.py" in files
    assert "src/gf180tcad/tcad/moscap1d.py" in files
    assert files == sorted(files, key=lambda s: s.encode())
    assert not any("__pycache__" in f for f in files)
    modules = {tcad.module_relpath(m).as_posix() for m in tcad.TCAD_GENERATORS[entry]}
    assert {f for f in files if f.startswith("src/")} == modules


def test_generator_files_per_entry_point():
    tcad_files = set(tcad.generator_files(TCAD_MAIN))
    calibrate_files = set(tcad.generator_files(CALIBRATE_MAIN))
    assert "src/gf180tcad/tcad/__main__.py" in tcad_files - calibrate_files
    assert "src/gf180tcad/calibrate/cv.py" in calibrate_files - tcad_files
    assert "src/gf180tcad/specwindow.py" in calibrate_files - tcad_files
    # the shared non-module inputs are the same for both
    shared = {f for f in tcad_files if not f.startswith("src/")}
    assert shared == {f for f in calibrate_files if not f.startswith("src/")}
    with pytest.raises(KeyError):
        tcad.generator_files("gf180tcad.__main__")


def test_generator_sha256_per_entry_point(monkeypatch):
    """Deterministic, different per entry point, and a change to a calibration-only file changes
    the calibration entry point's hash only (a change to a shared file changes both)."""
    before = {e: tcad.generator_sha256(e) for e in ROOTS}
    assert before == {e: tcad.generator_sha256(e) for e in ROOTS}
    assert len(set(before.values())) == 2 and all(len(h) == 64 for h in before.values())
    real = tcad._sha256

    def changed(path):
        return "0" * 64 if path.as_posix().endswith(target) else real(path)

    monkeypatch.setattr(tcad, "_sha256", changed)
    target = "src/gf180tcad/calibrate/cv.py"
    assert tcad.generator_sha256(TCAD_MAIN) == before[TCAD_MAIN]
    assert tcad.generator_sha256(CALIBRATE_MAIN) != before[CALIBRATE_MAIN]
    target = "src/gf180tcad/tcad/__main__.py"
    assert tcad.generator_sha256(TCAD_MAIN) != before[TCAD_MAIN]
    assert tcad.generator_sha256(CALIBRATE_MAIN) == before[CALIBRATE_MAIN]
    for target in ("tools/sandbox-run", "data/process/nfet_05v0.toml", "src/gf180tcad/io.py"):
        for e in ROOTS:
            assert tcad.generator_sha256(e) != before[e], (target, e)


@pytest.mark.parametrize("entry", ROOTS)
def test_provenance_names_its_generator(entry):
    prov = tcad.provenance(images={"moscap1d": "dev"}, generator=entry)
    assert prov["generator"] == entry
    assert prov["generator_sha256"] == tcad.generator_sha256(entry)
    with pytest.raises(KeyError):
        tcad.provenance(images={"moscap1d": "dev"}, generator="gf180tcad.__main__")
    with pytest.raises(TypeError):
        tcad.provenance(images={"moscap1d": "dev"})  # the generator is never implied


def test_provenance_contents():
    prov = tcad.provenance(images={"moscap1d": "dev", "moscap2d": "stable"}, generator=TCAD_MAIN)
    assert set(prov) == {"generator", "generator_sha256", "gplugins_commit", "images"}
    assert prov["images"] == {
        "moscap1d": {
            "name": "dev",
            "ref": tcad.TCAD_DEV_IMAGE,
            "versions": json.loads((REPO / "docker/tcad-dev/versions.json").read_bytes()),
        },
        "moscap2d": {
            "name": "stable",
            "ref": tcad.TCAD_IMAGE,
            "versions": json.loads((REPO / "docker/tcad/versions.json").read_bytes()),
        },
    }
    res = subprocess.run(
        ["git", "-C", "third_party/gplugins", "rev-parse", "HEAD"],
        cwd=REPO, capture_output=True, text=True, check=True,
    )  # fmt: skip
    assert prov["gplugins_commit"] == res.stdout.strip()
    # no run date and no host path; the versions are the committed versions.json files (the
    # dev image's records its upstream sources' commit dates, which are inputs, not run dates)
    text = json.dumps({k: v for k, v in prov.items() if k != "images"}).lower()
    assert "date" not in text and str(REPO).lower() not in text
    assert str(REPO).lower() not in json.dumps(prov).lower()


def test_provenance_records_calibration(tmp_path, monkeypatch):
    values = {"t_ox_eff_nm": 15.9, "n_ch_cm3": 2.0e17, "dv_fb_v": 0.05}
    calib = tmp_path / "nfet_05v0.json"
    calibration.write(calib, "nfet_05v0", values)
    monkeypatch.setattr(tcad, "calibration_file", lambda d, root=None: tmp_path / f"{d}.json")
    prov = tcad.provenance(("nfet_05v0",), images={"moscap1d": "dev"}, generator=CALIBRATE_MAIN)
    assert prov["calibration"] == {
        "nfet_05v0": {
            "file_sha256": hashlib.sha256(calib.read_bytes()).hexdigest(),
            "param_sha256": calibration.param_sha256(values),
        }
    }
    tree = tmp_path / "tree"
    (tree / "nfet_05v0" / "calibrated").mkdir(parents=True)
    (tree / "pfet_05v0" / "start").mkdir(parents=True)
    assert tcad.calibrated_devices(tree) == ("nfet_05v0",)
    # a validation tree: every device validated there used its calibration, recognised by the
    # validation result's content (it records the calibration file's sha256), whatever the
    # tree's directory is called
    validated = json.dumps({"calibration_file_sha256": "0" * 64, "device": "pfet_05v0"})
    for name in ("validation", "elsewhere"):
        val = tmp_path / name
        val.mkdir()
        (val / "pfet_05v0.json").write_text(validated, encoding="utf-8")
        for other in ("provenance.json", "notes.json"):
            (val / other).write_text(validated, encoding="utf-8")
        (val / "nfet_05v0.json").write_text("{}", encoding="utf-8")
        assert tcad.calibrated_devices(val) == ("pfet_05v0",), name
    # the calibration tree itself was computed from the start values: its <device>.json is a
    # calibration file (schema, device, values); the sha256 is only in <device>.result.json
    cal = tmp_path / "calibration"
    cal.mkdir()
    calibration.write(cal / "pfet_05v0.json", "pfet_05v0", values)
    (cal / "pfet_05v0.result.json").write_text(validated, encoding="utf-8")
    assert tcad.calibrated_devices(cal) == ()


@pytest.mark.parametrize(
    ("outputs", "match"),
    [
        ({"status --porcelain": " M gplugins/devsim/cv.py\n"}, "local changes"),
        (
            {
                "ls-tree HEAD third_party/gplugins": "160000 commit "
                + "b" * 40
                + "\tthird_party/gplugins\n"
            },
            "pins",
        ),
        ({"ls-tree HEAD third_party/gplugins": ""}, "not a gitlink"),
    ],
)
def test_provenance_refuses_a_dirty_or_unpinned_plugin(monkeypatch, outputs, match):
    def fake_git(args, cwd):
        key = " ".join(args)
        if key in outputs:
            return outputs[key]
        if key == "rev-parse HEAD":
            return "a" * 40 + "\n"
        if key == "status --porcelain":
            return ""
        if key.startswith("ls-tree"):
            return "160000 commit " + "a" * 40 + "\tthird_party/gplugins\n"
        raise AssertionError(key)

    monkeypatch.setattr(tcad, "_git", fake_git)
    with pytest.raises(tcad.ProvenanceError, match=match):
        tcad.gplugins_commit()


def _committed_tree_roots() -> list[Path]:
    return sorted(p.parent for p in TCAD_RESULTS.glob(f"*/{PROVENANCE_NAME}"))


def test_committed_tree_roots_are_known():
    roots = _committed_tree_roots()
    assert roots, "no committed TCAD tree root"
    assert {p.name for p in roots} <= set(TREE_ROOTS)
    for p in TCAD_RESULTS.iterdir():
        assert p.name in TREE_ROOTS, f"results/tcad/{p.name} is not a tree root of the layout"


# The calibration and validation trees are computed with the 1D model (Task 12).
MODEL_KINDS = {"calibration": ["moscap1d"], "validation": ["moscap1d"]}


def _result_kinds(root: Path) -> list[str]:
    """The result kinds (``moscap1d``, ``moscap2d``) a committed tree root holds: itself,
    (meshconv) its ``moscap<n>d`` subtrees, or (calibration, validation) the 1D model's."""
    if root.name in tcad.RESULTS_IMAGE:
        return [root.name]
    if root.name in MODEL_KINDS:
        return MODEL_KINDS[root.name]
    return sorted(p.name for p in root.iterdir() if p.is_dir() and p.name in tcad.RESULTS_IMAGE)


def test_committed_results_come_from_the_results_image():
    """Each committed result kind was made by its image of RESULTS_IMAGE: 1D on dev HEAD, 2D on
    the stable image (docs/reproduce/image.md, "Which image makes which results")."""
    for root in _committed_tree_roots():
        committed = json.loads((root / PROVENANCE_NAME).read_bytes())
        kinds = _result_kinds(root)
        assert kinds, root
        assert {k: v["name"] for k, v in committed["images"].items()} == {
            k: tcad.RESULTS_IMAGE[k] for k in kinds
        }, f"{root.relative_to(REPO)}: {REGENERATE}"


def test_committed_tcad_provenance_current():
    for root in _committed_tree_roots():
        committed = json.loads((root / PROVENANCE_NAME).read_bytes())
        assert committed.get("generator") == WRITERS[root.name], (
            f"{root.relative_to(REPO)}/provenance.json names generator "
            f"{committed.get('generator')!r}, not its writer {WRITERS[root.name]}; {REGENERATE}"
        )
        current = tcad.tree_provenance(
            root,
            {k: tcad.RESULTS_IMAGE[k] for k in _result_kinds(root)},
            generator=WRITERS[root.name],
        )
        assert committed == current, (
            f"{root.relative_to(REPO)}/provenance.json differs from what the generator would "
            f"write ({sorted(k for k in current if committed.get(k) != current[k])}); {REGENERATE}"
        )


def test_manifest_covers_the_tcad_results():
    entries = manifest._load(RESULTS / "MANIFEST.sha256")
    for p in TCAD_RESULTS.rglob("*"):
        if p.is_file() and p.name != "mesh.msh":  # git-ignored; its sha256 is in cv.meta.json
            rel = p.relative_to(RESULTS).as_posix()
            assert entries.get(rel) == hashlib.sha256(p.read_bytes()).hexdigest(), (
                f"results/MANIFEST.sha256 does not match results/{rel}; run `make manifest`"
            )
