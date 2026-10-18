# SPDX-License-Identifier: Apache-2.0
"""PDK provenance: locate the model files and check them against docker/base/versions.json."""

import hashlib
import json
from pathlib import Path

import pytest

from gf180tcad import pdk, sandbox

VARIANT = "gf180mcuD"
COMMIT = "a" * 40
FILES = {
    "ngspice_lib": "libs.tech/ngspice/sm141064.ngspice",
    "ngspice_design": "libs.tech/ngspice/design.ngspice",
    "xyce_lib": "libs.tech/xyce/sm141064.xyce",
    "xyce_design": "libs.tech/xyce/design.xyce",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def fake(tmp_path):
    """A fake PDK tree laid out like the real one, and a matching versions.json."""
    root = tmp_path / "pdks"
    base = root / VARIANT
    for rel in FILES.values():
        f = base / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(f"contents of {rel}\r\n".encode() + bytes(range(256)) * 300)
    (base / ".config").mkdir()
    (base / ".config" / "nodeinfo.json").write_text(
        json.dumps({"commit": {"open_pdks": COMMIT}}), encoding="utf-8"
    )
    versions = {
        "gf180mcu_variant": VARIANT,
        "open_pdks_commit": COMMIT,
        "sm141064_ngspice_sha256": _sha((base / FILES["ngspice_lib"]).read_bytes()),
        "design_ngspice_sha256": _sha((base / FILES["ngspice_design"]).read_bytes()),
        "sm141064_xyce_sha256": _sha((base / FILES["xyce_lib"]).read_bytes()),
    }
    vpath = tmp_path / "versions.json"
    vpath.write_text(json.dumps(versions), encoding="utf-8")
    return root, vpath, versions


def _write(vpath, versions):
    vpath.write_text(json.dumps(versions), encoding="utf-8")


def test_locate_resolves_paths(fake):
    root, _, _ = fake
    info = pdk.locate(root)
    assert info.root == root
    assert info.variant == VARIANT
    assert info.open_pdks_commit == COMMIT
    for attr, rel in FILES.items():
        assert getattr(info, attr) == root / VARIANT / rel
        assert getattr(info, attr).is_absolute()


def test_locate_makes_relative_root_absolute_and_ignores_cwd(fake, monkeypatch):
    root, _, _ = fake
    monkeypatch.chdir(root.parent)
    info = pdk.locate(Path("pdks"))
    assert info.ngspice_lib == root / VARIANT / FILES["ngspice_lib"]
    monkeypatch.chdir(root)  # a different cwd gives the same answer for an absolute root
    assert pdk.locate(root) == info


def test_locate_defaults_to_env(fake, monkeypatch):
    root, _, _ = fake
    monkeypatch.setenv("PDK_ROOT", str(root))
    assert pdk.locate() == pdk.locate(root)


def test_locate_without_root_or_env_fails(monkeypatch):
    monkeypatch.delenv("PDK_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="PDK_ROOT"):
        pdk.locate()


@pytest.mark.parametrize("attr", sorted(FILES))
def test_locate_missing_file_names_path(fake, attr):
    root, _, _ = fake
    target = root / VARIANT / FILES[attr]
    target.unlink()
    with pytest.raises(FileNotFoundError, match=str(target)):
        pdk.locate(root)


def test_check_against_matching_passes(fake):
    root, vpath, _ = fake
    pdk.check_against(pdk.locate(root), vpath)


def test_pdk_mismatch_is_runtime_error():
    assert issubclass(pdk.PdkMismatch, RuntimeError)


@pytest.mark.parametrize(
    "key", ["sm141064_ngspice_sha256", "design_ngspice_sha256", "sm141064_xyce_sha256"]
)
def test_hash_mismatch(fake, key):
    root, vpath, versions = fake
    versions[key] = "0" * 64
    _write(vpath, versions)
    with pytest.raises(pdk.PdkMismatch, match=key):
        pdk.check_against(pdk.locate(root), vpath)


def test_changed_file_bytes_detected(fake):
    root, vpath, _ = fake
    f = root / VARIANT / FILES["ngspice_lib"]
    f.write_bytes(f.read_bytes() + b" ")
    with pytest.raises(pdk.PdkMismatch, match="sm141064_ngspice_sha256"):
        pdk.check_against(pdk.locate(root), vpath)


def test_variant_mismatch(fake):
    root, vpath, versions = fake
    versions["gf180mcu_variant"] = "gf180mcuC"
    _write(vpath, versions)
    with pytest.raises(pdk.PdkMismatch, match="gf180mcu_variant"):
        pdk.check_against(pdk.locate(root), vpath)


def test_commit_mismatch(fake):
    root, vpath, versions = fake
    versions["open_pdks_commit"] = "b" * 40
    _write(vpath, versions)
    with pytest.raises(pdk.PdkMismatch, match="open_pdks_commit"):
        pdk.check_against(pdk.locate(root), vpath)


def test_missing_key_is_mismatch_not_keyerror(fake):
    root, vpath, versions = fake
    del versions["sm141064_xyce_sha256"]
    _write(vpath, versions)
    with pytest.raises(pdk.PdkMismatch, match="sm141064_xyce_sha256"):
        pdk.check_against(pdk.locate(root), vpath)


def test_all_mismatches_reported(fake):
    root, vpath, versions = fake
    versions["sm141064_ngspice_sha256"] = "1" * 64
    versions["design_ngspice_sha256"] = "2" * 64
    versions["gf180mcu_variant"] = "gf180mcuC"
    versions["open_pdks_commit"] = "b" * 40
    del versions["sm141064_xyce_sha256"]
    _write(vpath, versions)
    info = pdk.locate(root)
    with pytest.raises(pdk.PdkMismatch) as exc:
        pdk.check_against(info, vpath)
    msg = str(exc.value)
    for key in versions.keys() | {"sm141064_xyce_sha256"}:
        assert key in msg
    assert "1" * 64 in msg  # expected value
    assert _sha((root / VARIANT / FILES["ngspice_lib"]).read_bytes()) in msg  # actual value
    assert "b" * 40 in msg and COMMIT in msg
    assert "gf180mcuC" in msg


@pytest.mark.sandbox
def test_image_pdk_matches_versions_json(tmp_path):
    code = (
        "from gf180tcad import pdk; from pathlib import Path; "
        "pdk.check_against(pdk.locate(), Path('/work/src/docker/base/versions.json'))"
    )
    res = sandbox.run(["python", "-c", code], out_dir=tmp_path)
    assert res.returncode == 0
