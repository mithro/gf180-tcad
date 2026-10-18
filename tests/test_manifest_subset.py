# SPDX-License-Identifier: Apache-2.0
"""``manifest verify-subset``: a regenerated subset tree against the committed manifest."""

import shutil
import subprocess
import sys

import pytest

from gf180tcad import manifest

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
    assert "identical" in r.stdout and "5 files" in r.stdout and "2 jobs" in r.stdout


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
