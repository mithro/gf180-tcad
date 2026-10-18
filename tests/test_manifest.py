# SPDX-License-Identifier: Apache-2.0
"""sha256 manifest of the results tree."""

import subprocess
import sys

import pytest

from gf180tcad import manifest


def _tree(root):
    (root / "sub").mkdir()
    (root / "b.csv").write_bytes(b"b\n")
    (root / "sub" / "a.json").write_bytes(b"{}\n")
    (root / "A.txt").write_bytes(b"A\n")


def test_manifest_format_sorted_and_excludes_self(tmp_path):
    _tree(tmp_path)
    m = tmp_path / "MANIFEST.sha256"
    manifest.update(tmp_path, m)
    manifest.update(tmp_path, m)  # idempotent; does not list itself
    lines = m.read_bytes().decode().splitlines()
    assert [ln.split("  ", 1)[1] for ln in lines] == ["A.txt", "b.csv", "sub/a.json"]
    assert all(len(ln.split("  ", 1)[0]) == 64 for ln in lines)
    assert m.read_bytes().endswith(b"\n") and b"\r" not in m.read_bytes()
    assert manifest.verify(tmp_path, m) == []


def test_manifest_detects_change_missing_extra(tmp_path):
    _tree(tmp_path)
    m = tmp_path / "MANIFEST.sha256"
    manifest.update(tmp_path, m)
    (tmp_path / "b.csv").write_bytes(b"changed\n")
    (tmp_path / "A.txt").unlink()
    (tmp_path / "sub" / "new.csv").write_bytes(b"x\n")
    assert manifest.verify(tmp_path, m) == ["A.txt", "b.csv", "sub/new.csv"]


def test_manifest_outside_root_and_empty(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    m = tmp_path / "M.sha256"
    manifest.update(root, m)
    assert m.read_bytes() == b""
    assert manifest.verify(root, m) == []
    (root / "x").write_bytes(b"1")
    assert manifest.verify(root, m) == ["x"]


def test_cli(tmp_path):
    _tree(tmp_path)
    run = lambda *a: subprocess.run(
        [sys.executable, "-m", "gf180tcad.manifest", *a],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run("update", str(tmp_path)).returncode == 0
    assert run("verify", str(tmp_path)).returncode == 0
    (tmp_path / "b.csv").write_bytes(b"zzz")
    r = run("verify", str(tmp_path))
    assert r.returncode != 0 and "b.csv" in r.stdout + r.stderr


def test_symlinks_rejected(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    (tmp_path / "outside").write_bytes(b"x")
    (root / "ok").write_bytes(b"1")
    m = tmp_path / "M.sha256"
    m.write_bytes(b"")
    (root / "link").symlink_to(tmp_path / "outside")
    for fn in (manifest.update, manifest.verify):
        with pytest.raises(ValueError, match="link"):
            fn(root, m)
    (root / "link").unlink()
    (root / "broken").symlink_to(tmp_path / "nonexistent")
    with pytest.raises(ValueError, match="broken"):
        manifest.update(root, m)
    (root / "broken").unlink()
    (root / "dlink").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="dlink"):
        manifest.update(root, m)


def test_root_must_be_directory(tmp_path):
    m = tmp_path / "M.sha256"
    m.write_bytes(b"")
    (tmp_path / "f").write_bytes(b"")
    for bad in (tmp_path / "missing", tmp_path / "f"):
        for fn in (manifest.update, manifest.verify):
            with pytest.raises(NotADirectoryError):
                fn(bad, m)


def test_duplicate_manifest_entry_rejected(tmp_path):
    (tmp_path / "a").write_bytes(b"1")
    m = tmp_path / "M.sha256"
    manifest.update(tmp_path, m)
    line = m.read_bytes()
    m.write_bytes(line + line)
    with pytest.raises(ValueError, match="duplicate"):
        manifest.verify(tmp_path, m)


@pytest.mark.parametrize("line", [b"nothex a\n", b"abc  a\n", b"0" * 64 + b" a\n"])
def test_malformed_manifest_line_rejected(tmp_path, line):
    m = tmp_path / "M.sha256"
    m.write_bytes(line)
    with pytest.raises(ValueError, match="malformed"):
        manifest.verify(tmp_path, m)
