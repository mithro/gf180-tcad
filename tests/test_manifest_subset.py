# SPDX-License-Identifier: Apache-2.0
"""``manifest verify-subset``: a regenerated subset tree against the committed manifest."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from gf180tcad import manifest, reference
from gf180tcad.devices import CORNERS, DEVICES

A = "ngspice/typical/nfet_05v0/w10p0_l0p60"
B = "xyce/typical/pfet_05v0/w10p0_l0p50"
C = "ngspice/ff/nfet_05v0/w10p0_l0p60"  # committed, but not in the subset


def _job(root, rel, tag):
    d = root / rel
    d.mkdir(parents=True)
    (d / "idvd.csv").write_bytes(f"# {tag}\n0.0,1.25e-05\n".encode())
    (d / "metrics.json").write_bytes(f'{{"tag": "{tag}"}}\n'.encode())


@pytest.fixture
def setup(tmp_path):
    """A committed results/ (manifest included), a subset file and a matching subset tree."""
    results = tmp_path / "results"
    spice = results / "spice"
    for rel in (A, B, C):
        _job(spice, rel, rel)
    (spice / "provenance.json").write_bytes(b'{"generator_sha256": "abc"}\n')
    (spice / "envelope.json").write_bytes(b'{"full": "envelope"}\n')
    (results / "tcad").mkdir()  # outside the prefix: never looked at
    (results / "tcad" / "x.csv").write_bytes(b"1\n")
    m = results / "MANIFEST.sha256"
    manifest.update(results, m)

    subset = tmp_path / "subset.txt"
    subset.write_text(f"# the cross-check subset\n\n{A}\n{B}\n")

    tree = tmp_path / "tree"
    for rel in (A, B):
        shutil.copytree(spice / rel, tree / rel)
    shutil.copyfile(spice / "provenance.json", tree / "provenance.json")
    # a subset run writes its own (incomplete) envelope, which must not be compared
    (tree / "envelope.json").write_bytes(b'{"partial": "envelope"}\n')
    return tree, m, subset


def _check(setup):
    tree, m, subset = setup
    return manifest.verify_subset(tree, m, "spice/", manifest.load_subset(subset))


def test_identical_subset_passes(setup):
    assert _check(setup) == []


def test_envelope_is_excluded(setup):
    tree = setup[0]
    (tree / "envelope.json").unlink()
    assert _check(setup) == []


def test_changed_byte_is_reported_without_tolerance(setup):
    tree = setup[0]
    f = tree / A / "idvd.csv"
    f.write_bytes(f.read_bytes().replace(b"1.25e-05", b"1.2500000000000001e-05"))
    assert _check(setup) == [(f"spice/{A}/idvd.csv", "changed")]


def test_missing_file_of_listed_job_is_reported(setup):
    tree = setup[0]
    (tree / B / "metrics.json").unlink()
    assert _check(setup) == [(f"spice/{B}/metrics.json", "missing")]


def test_missing_job_reports_every_file(setup):
    tree = setup[0]
    shutil.rmtree(tree / B)
    assert _check(setup) == [
        (f"spice/{B}/idvd.csv", "missing"),
        (f"spice/{B}/metrics.json", "missing"),
    ]


def test_file_not_in_manifest_is_reported(setup):
    tree = setup[0]
    (tree / A / "cv.csv").write_bytes(b"new\n")
    assert _check(setup) == [(f"spice/{A}/cv.csv", "not in manifest")]


def test_job_outside_subset_is_reported(setup):
    tree, m, _ = setup
    # identical to its committed bytes, but the subset did not ask for it
    shutil.copytree(m.parent / "spice" / C, tree / C)
    assert _check(setup) == [
        (f"spice/{C}/idvd.csv", "not in subset"),
        (f"spice/{C}/metrics.json", "not in subset"),
    ]


def test_provenance_must_match(setup):
    tree = setup[0]
    (tree / "provenance.json").write_bytes(b'{"generator_sha256": "abd"}\n')
    assert _check(setup) == [("spice/provenance.json", "changed")]
    (tree / "provenance.json").unlink()
    assert _check(setup) == [("spice/provenance.json", "missing")]


def test_listed_job_absent_from_manifest_is_reported(setup):
    subset = setup[2]
    subset.write_text(f"{A}\n{B}\nxyce/typical/nfet_05v0/w9p0_l0p60\n")
    assert _check(setup) == [("spice/xyce/typical/nfet_05v0/w9p0_l0p60/", "unknown job")]


def test_prefix_scopes_the_manifest(setup):
    tree, m, _ = setup
    # "tcad/x.csv" exists in the manifest but outside the prefix, so a tree file with
    # that name is not matched against it
    (tree / "tcad").mkdir()
    shutil.copyfile(m.parent / "tcad" / "x.csv", tree / "tcad" / "x.csv")
    assert _check(setup) == [("spice/tcad/x.csv", "not in subset")]


def test_prefix_must_end_with_slash(setup):
    tree, m, subset = setup
    with pytest.raises(ValueError, match="prefix"):
        manifest.verify_subset(tree, m, "spice", manifest.load_subset(subset))


def test_tree_must_be_directory(setup, tmp_path):
    _, m, subset = setup
    with pytest.raises(NotADirectoryError):
        manifest.verify_subset(tmp_path / "nope", m, "spice/", manifest.load_subset(subset))


def test_symlink_in_tree_rejected(setup, tmp_path):
    tree = setup[0]
    (tree / A / "link.csv").symlink_to(tmp_path / "subset.txt")
    with pytest.raises(ValueError, match="link"):
        _check(setup)


def test_missing_provenance_reported_even_if_manifest_lacks_it(setup):
    tree, m, _ = setup
    lines = m.read_bytes().decode().splitlines(keepends=True)
    m.write_bytes(
        "".join(ln for ln in lines if not ln.endswith("  spice/provenance.json\n")).encode()
    )
    (tree / "provenance.json").unlink()
    assert _check(setup) == [("spice/provenance.json", "missing")]


def _complete(setup):
    """The fixture's committed jobs A, B and C stand in for the full reference."""
    tree, m, _ = setup
    shutil.copytree(m.parent / "spice" / C, tree / C)
    shutil.copyfile(m.parent / "spice" / "envelope.json", tree / "envelope.json")
    return lambda: manifest.verify_subset(tree, m, "spice/", (A, B, C), full=(C, B, A))


def test_complete_subset_compares_envelope(setup):
    check = _complete(setup)
    assert check() == []
    (setup[0] / "envelope.json").write_bytes(b'{"partial": "envelope"}\n')
    assert check() == [("spice/envelope.json", "changed")]
    (setup[0] / "envelope.json").unlink()
    assert check() == [("spice/envelope.json", "missing")]


def test_complete_subset_needs_committed_envelope(setup):
    check = _complete(setup)
    m = setup[1]
    lines = m.read_bytes().decode().splitlines(keepends=True)
    m.write_bytes(
        "".join(ln for ln in lines if not ln.endswith("  spice/envelope.json\n")).encode()
    )
    assert check() == [("spice/envelope.json", "not in manifest")]


def test_partial_subset_still_excludes_envelope(setup):
    tree, m, _ = setup
    (tree / "envelope.json").write_bytes(b"anything\n")
    # (A, B) is not every job of full, so the envelope is not compared
    assert manifest.verify_subset(tree, m, "spice/", (A, B), full=(A, B, C)) == []


def test_load_subset_all_expands_to_the_full_reference(tmp_path):
    p = tmp_path / "s.txt"
    p.write_text("# everything\nall\n")
    jobs = manifest.load_subset(p)
    assert jobs == manifest.all_jobs()
    plan = reference.plan_jobs(reference.ENGINES, CORNERS, tuple(DEVICES))
    assert jobs == tuple(j.relpath.as_posix() for j in plan)
    assert len(jobs) == 120


def test_load_subset_skips_comments_and_blanks(setup):
    assert manifest.load_subset(setup[2]) == (A, B)


@pytest.mark.parametrize(
    "text",
    [
        "ngspice/typical/nfet_05v0\n",  # 3 components
        "ngspice/typical/nfet_05v0/w10p0_l0p60/idvd.csv\n",  # 5 components
        "/ngspice/typical/nfet_05v0/w10p0_l0p60\n",  # absolute
        "ngspice/../nfet_05v0/w10p0_l0p60\n",
        "ngspice/typical/nfet_05v0/w10p0_l0p60/\n",  # trailing slash
        f"{A}\n{A}\n",  # duplicate
        "# only comments\n",  # empty subset
        f"all\n{A}\n",  # "all" must be the only job line
        "all\nall\n",
    ],
)
def test_load_subset_rejects_bad_lines(tmp_path, text):
    p = tmp_path / "s.txt"
    p.write_text(text)
    with pytest.raises(ValueError):
        manifest.load_subset(p)


def _cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "gf180tcad.manifest", "verify-subset", *map(str, args)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_ok(setup):
    tree, m, subset = setup
    r = _cli(tree, "--against", m, "--prefix", "spice/", "--subset", subset)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "identical: 5 files of 2 jobs" in r.stdout and "envelope.json excluded" in r.stdout


def test_cli_prints_each_mismatch_and_fails(setup):
    tree, m, subset = setup
    (tree / A / "idvd.csv").write_bytes(b"x\n")
    (tree / B / "metrics.json").unlink()
    r = _cli(tree, "--against", m, "--prefix", "spice/", "--subset", subset)
    assert r.returncode == 1
    assert r.stdout.splitlines()[:2] == [
        f"changed: spice/{A}/idvd.csv",
        f"missing: spice/{B}/metrics.json",
    ]


def test_cli_requires_against_and_subset(setup):
    tree, m, subset = setup
    assert _cli(tree, "--subset", subset).returncode == 2
    assert _cli(tree, "--against", m).returncode == 2


# --- the real subset file and committed results -----------------------------------------------

REPO = Path(__file__).resolve().parents[1]
SUBSET = REPO / "tests" / "crosscheck_subset.txt"


def _crosscheck_args(subset):
    r = subprocess.run(
        [sys.executable, str(REPO / "tools" / "crosscheck-args"), str(subset)],
        check=True,
        capture_output=True,
        text=True,
    )
    a = reference.parse_args(["spice-reference", *r.stdout.splitlines(), "--out", "o"])
    return sorted(j.relpath.as_posix() for j in reference.plan_jobs(
        a.engines, a.corners, a.devices, a.geometries
    ))  # fmt: skip


def test_crosscheck_subset_is_the_full_reference():
    assert manifest.load_subset(SUBSET) == manifest.all_jobs()


def test_crosscheck_args_plan_exactly_the_listed_jobs(tmp_path):
    """tools/crosscheck-args (what the workflow passes to spice-reference) plans the subset."""
    assert _crosscheck_args(SUBSET) == sorted(manifest.load_subset(SUBSET))
    partial = tmp_path / "partial.txt"
    partial.write_text("\n".join(PARTIAL) + "\n")
    assert _crosscheck_args(partial) == sorted(PARTIAL)


# the original 8-job subset: nfet W10/Lmin 0.6, pfet W10/Lmin 0.5, both W1.6/L0.7, typical
PARTIAL = tuple(
    f"{e}/typical/{dg}"
    for e in ("ngspice", "xyce")
    for dg in ("nfet_05v0/w10p0_l0p60", "nfet_05v0/w1p6_l0p70",
               "pfet_05v0/w10p0_l0p50", "pfet_05v0/w1p6_l0p70")
)  # fmt: skip
SPICE = REPO / "results" / "spice"
COMMITTED = REPO / "results" / "MANIFEST.sha256"


def test_committed_partial_subset_verifies(tmp_path):
    """A partial copy of results/spice passes, with every sweep of each engine, no envelope."""
    tree = tmp_path / "tree"
    for j in PARTIAL:
        shutil.copytree(SPICE / j, tree / j)
        assert sorted(p.name for p in (tree / j).iterdir()) == list(
            reference.expected_files(j.split("/")[0])
        )
    shutil.copyfile(SPICE / "provenance.json", tree / "provenance.json")
    assert manifest.verify_subset(tree, COMMITTED, "spice/", PARTIAL) == []


def test_committed_full_tree_verifies_including_envelope(tmp_path):
    tree = tmp_path / "spice"
    shutil.copytree(SPICE, tree)
    jobs = manifest.all_jobs()
    assert manifest.verify_subset(tree, COMMITTED, "spice/", jobs) == []
    env = tree / "envelope.json"
    env.write_bytes(env.read_bytes().replace(b"0", b"1", 1))
    assert manifest.verify_subset(tree, COMMITTED, "spice/", jobs) == [
        ("spice/envelope.json", "changed")
    ]


def test_cli_complete_counts_and_compares_envelope(tmp_path):
    tree = tmp_path / "spice"
    shutil.copytree(SPICE, tree)
    r = _cli(tree, "--against", COMMITTED, "--prefix", "spice/", "--subset", SUBSET)
    assert r.returncode == 0, r.stdout + r.stderr
    n = sum(1 for p in tree.rglob("*") if p.is_file())
    assert f"identical: {n} files of 120 jobs" in r.stdout
    assert "envelope.json compared" in r.stdout and "excluded" not in r.stdout


# --- TCAD subsets (kind="tcad") ---------------------------------------------------------------
#
# TCAD jobs are <tree>/<device>/<params> under the manifest prefix tcad/; each tree named by the
# jobs has its own provenance.json, and there is no envelope.

T1N = "moscap1d/nfet_05v0/calibrated"
T1P = "moscap1d/pfet_05v0/calibrated"
T2N = "moscap2d/nfet_05v0/start"
TCAD_ALL = tuple(
    f"{t}/{d}/{p}"
    for t in ("moscap1d", "moscap2d")
    for d in ("nfet_05v0", "pfet_05v0")
    for p in ("start", "calibrated")
)


def _tcad_job(root, rel):
    d = root / rel
    if rel.startswith("moscap2d/"):
        d = d / "w10p0_l0p60"  # 2D job dirs hold one directory per geometry
    d.mkdir(parents=True)
    (d / "per_area.csv").write_bytes(f"# {rel}\n-5.0,1.25e-05\n".encode())
    (d / "per_area.meta.json").write_bytes(f'{{"job": "{rel}"}}\n'.encode())


@pytest.fixture
def tcad_setup(tmp_path):
    """A committed results/ with every TCAD job, per-tree provenance, and a 1D subset tree."""
    results = tmp_path / "results"
    tcad = results / "tcad"
    for rel in TCAD_ALL:
        _tcad_job(tcad, rel)
    for tree in ("moscap1d", "moscap2d", "meshconv", "calibration"):
        (tcad / tree).mkdir(exist_ok=True)
        (tcad / tree / "provenance.json").write_bytes(f'{{"tree": "{tree}"}}\n'.encode())
    (tcad / "calibration" / "nfet_05v0.json").write_bytes(b'{"x": 1}\n')
    _job(results / "spice", A, A)
    (results / "spice" / "provenance.json").write_bytes(b'{"generator_sha256": "abc"}\n')
    m = results / "MANIFEST.sha256"
    manifest.update(results, m)

    subset = tmp_path / "tcad_subset.txt"
    subset.write_text(f"# the TCAD cross-check subset\n\n{T1N}\n{T1P}\n")

    tree = tmp_path / "out"
    for rel in (T1N, T1P):
        shutil.copytree(tcad / rel, tree / rel)
    shutil.copyfile(tcad / "moscap1d" / "provenance.json", tree / "moscap1d" / "provenance.json")
    return tree, m, subset


def _tcad_check(tree, m, jobs):
    return manifest.verify_subset(
        tree, m, "tcad/", jobs, kind="tcad", full=manifest.tcad_all_jobs()
    )


def test_tcad_subset_parse(tmp_path):
    p = tmp_path / "s.txt"
    p.write_text(f"# comment\n\n{T1N}\n{T2N}\n")
    assert manifest.load_subset(p, kind="tcad") == (T1N, T2N)
    for text in (
        "moscap1d/nfet_05v0\n",  # 2 components
        "moscap1d/nfet_05v0/calibrated/w10p0_l0p60\n",  # 4 components
        "ngspice/typical/nfet_05v0/w10p0_l0p60\n",  # a SPICE job
        "moscap3d/nfet_05v0/start\n",  # unknown tree
        "meshconv/nfet_05v0/start\n",  # not a job tree
        "moscap1d/nfet_05v0/tuned\n",  # unknown params
        "moscap1d/nfet_33v0/start\n",  # unknown device
        "moscap1d/nfet_05v0/start/\n",  # trailing slash
        "/moscap1d/nfet_05v0/start\n",
        f"{T1N}\n{T1N}\n",  # duplicate
        "# only comments\n",
        f"all\n{T1N}\n",
    ):
        p.write_text(text)
        with pytest.raises(ValueError):
            manifest.load_subset(p, kind="tcad")
    p.write_text(f"{T1N}\n")
    with pytest.raises(ValueError, match="kind"):
        manifest.load_subset(p, kind="xyce")


def test_tcad_all_expands(tmp_path):
    p = tmp_path / "s.txt"
    p.write_text("# every TCAD job\nall\n")
    jobs = manifest.load_subset(p, kind="tcad")
    assert jobs == manifest.tcad_all_jobs()
    assert sorted(jobs) == sorted(TCAD_ALL) and len(set(jobs)) == 8
    assert not set(jobs) & set(manifest.all_jobs())


def test_tcad_verify_subset_detects_change(tcad_setup):
    tree, m, subset = tcad_setup
    jobs = manifest.load_subset(subset, kind="tcad")
    assert _tcad_check(tree, m, jobs) == []
    f = tree / T1P / "per_area.csv"
    f.write_bytes(f.read_bytes().replace(b"1.25e-05", b"1.2500000000000001e-05"))
    assert _tcad_check(tree, m, jobs) == [(f"tcad/{T1P}/per_area.csv", "changed")]
    (tree / T1N / "per_area.meta.json").unlink()
    (tree / T1N / "extra.csv").write_bytes(b"1\n")
    assert _tcad_check(tree, m, jobs) == [
        (f"tcad/{T1N}/extra.csv", "not in manifest"),
        (f"tcad/{T1N}/per_area.meta.json", "missing"),
        (f"tcad/{T1P}/per_area.csv", "changed"),
    ]


def test_tcad_verify_requires_tree_provenance(tcad_setup):
    tree, m, subset = tcad_setup
    jobs = manifest.load_subset(subset, kind="tcad")
    # no root provenance.json is required (the TCAD trees have one each)
    assert not (tree / "provenance.json").exists()
    assert _tcad_check(tree, m, jobs) == []
    (tree / "moscap1d" / "provenance.json").unlink()
    assert _tcad_check(tree, m, jobs) == [("tcad/moscap1d/provenance.json", "missing")]
    # a job of a second tree requires that tree's provenance too
    shutil.copytree(m.parent / "tcad" / T2N, tree / T2N)
    shutil.copyfile(
        m.parent / "tcad" / "moscap1d" / "provenance.json", tree / "moscap1d" / "provenance.json"
    )
    assert _tcad_check(tree, m, (*jobs, T2N)) == [("tcad/moscap2d/provenance.json", "missing")]
    p2 = tree / "moscap2d" / "provenance.json"
    p2.write_bytes(b'{"tree": "other"}\n')
    assert _tcad_check(tree, m, (*jobs, T2N)) == [("tcad/moscap2d/provenance.json", "changed")]
    # ... but not when its jobs are not listed; envelope.json is never special
    (tree / "envelope.json").write_bytes(b"{}\n")
    assert _tcad_check(tree, m, jobs) == [
        ("tcad/envelope.json", "not in subset"),
        (f"tcad/{T2N}/w10p0_l0p60/per_area.csv", "not in subset"),
        (f"tcad/{T2N}/w10p0_l0p60/per_area.meta.json", "not in subset"),
        ("tcad/moscap2d/provenance.json", "not in subset"),
    ]


def test_tcad_full_passed_explicitly(tcad_setup):
    tree, m, subset = tcad_setup
    jobs = manifest.load_subset(subset, kind="tcad")
    # "complete" is never judged against the SPICE plan (the all_jobs() default)
    with pytest.raises(ValueError, match="full"):
        manifest.verify_subset(tree, m, "tcad/", jobs, kind="tcad")
    assert manifest.full_jobs("tcad") == manifest.tcad_all_jobs()
    assert manifest.full_jobs("spice") == manifest.all_jobs()
    r = _cli(tree, "--kind", "tcad", "--against", m, "--prefix", "tcad/", "--subset", subset)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "identical: 5 files of 2 jobs" in r.stdout and "partial subset" in r.stdout
    # every TCAD job is the complete TCAD set, whatever the SPICE plan holds
    full = tree.parent / "full"
    shutil.copytree(
        m.parent / "tcad", full, ignore=shutil.ignore_patterns("meshconv", "calibration")
    )
    (subset.parent / "all.txt").write_text("all\n")
    r = _cli(
        full, "--kind", "tcad", "--against", m, "--prefix", "tcad/", "--subset",
        subset.parent / "all.txt",
    )  # fmt: skip
    assert r.returncode == 0, r.stdout + r.stderr
    assert "identical: 18 files of 8 jobs" in r.stdout and "complete subset" in r.stdout


def test_spice_subset_unchanged(setup, tmp_path):
    tree, m, subset = setup
    assert manifest.load_subset(subset) == manifest.load_subset(subset, kind="spice") == (A, B)
    jobs = manifest.load_subset(subset)
    assert manifest.verify_subset(tree, m, "spice/", jobs, kind="spice") == []
    (tree / "provenance.json").unlink()
    assert manifest.verify_subset(tree, m, "spice/", jobs, kind="spice") == [
        ("spice/provenance.json", "missing")
    ]
    p = tmp_path / "t.txt"
    p.write_text(f"{T1N}\n")  # a TCAD job is not a SPICE job
    with pytest.raises(ValueError):
        manifest.load_subset(p)
    p.write_text("all\n")
    assert manifest.load_subset(p) == manifest.all_jobs()
    # the CLI defaults to --kind spice
    shutil.copyfile(m.parent / "spice" / "provenance.json", tree / "provenance.json")
    for extra in ((), ("--kind", "spice")):
        r = _cli(tree, *extra, "--against", m, "--prefix", "spice/", "--subset", subset)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "identical: 5 files of 2 jobs" in r.stdout and "envelope.json excluded" in r.stdout


TCAD_SUBSET = REPO / "tests" / "crosscheck_tcad_subset.txt"
TCAD = REPO / "results" / "tcad"


def test_crosscheck_tcad_subset_is_the_calibrated_1d_jobs():
    assert manifest.load_subset(TCAD_SUBSET, kind="tcad") == (
        "moscap1d/nfet_05v0/calibrated",
        "moscap1d/pfet_05v0/calibrated",
    )


def test_committed_tcad_subset_verifies(tmp_path):
    """A copy of the committed jobs of the TCAD subset, with their tree's provenance, passes."""
    jobs = manifest.load_subset(TCAD_SUBSET, kind="tcad")
    tree = tmp_path / "tcad"
    for j in jobs:
        shutil.copytree(TCAD / j, tree / j)
    for t in manifest.tcad_trees(jobs):
        shutil.copyfile(TCAD / t / "provenance.json", tree / t / "provenance.json")
    full = manifest.tcad_all_jobs()
    assert manifest.verify_subset(tree, COMMITTED, "tcad/", jobs, kind="tcad", full=full) == []
    r = _cli(
        tree, "--kind", "tcad", "--against", COMMITTED, "--prefix", "tcad/", "--subset",
        TCAD_SUBSET,
    )  # fmt: skip
    assert r.returncode == 0, r.stdout + r.stderr
    assert "identical: 5 files of 2 jobs" in r.stdout
    assert "partial subset; provenance moscap1d/provenance.json" in r.stdout
