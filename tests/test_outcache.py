# SPDX-License-Identifier: Apache-2.0
"""The output cache (:mod:`gf180tcad.outcache`) against local git repositories only.

A synthetic results tree has 2D job directories with a ``mesh.msh`` and the ``cv.meta.json``
naming its sha256; the cache is a checkout made by ``init`` whose ``origin`` is a bare repository
in ``tmp_path``. No network, no simulator.
"""

import gzip
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from gf180tcad import outcache

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "output-cache"
GIT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
JOB_A = "tcad/moscap2d/nfet_05v0/start/w10p0_l0p60"
JOB_B = "tcad/moscap2d/pfet_05v0/start/w10p0_l0p50"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
DATE = "2026-10-27"


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    for k in GIT_VARS:
        monkeypatch.delenv(k, raising=False)
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "t")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "t@example.invalid")


def _git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _mesh_bytes(tag: str, lines: int = 2000) -> bytes:
    body = "".join(f"{i} {i * 0.5:.6f} {tag} 0\n" for i in range(lines))
    return f"$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n{body}$EndNodes\n".encode()


def _job(results: Path, rel: str, mesh: bytes, *, meta_hash: str | None = None) -> Path:
    d = results / rel
    d.mkdir(parents=True, exist_ok=True)
    (d / "mesh.msh").write_bytes(mesh)
    device, params = rel.split("/")[2], rel.split("/")[3]
    meta = {
        "device": device,
        "dim": 2,
        "params": params,
        "mesh_sha256": meta_hash or hashlib.sha256(mesh).hexdigest(),
    }
    (d / "cv.meta.json").write_text(json.dumps(meta, sort_keys=True, indent=2) + "\n", "utf-8")
    return d / "mesh.msh"


@pytest.fixture
def results(tmp_path):
    """A results tree with two 2D jobs and the tree root's provenance.json."""
    r = tmp_path / "primary" / "results"
    _job(r, JOB_A, _mesh_bytes("a"))
    _job(r, JOB_B, _mesh_bytes("b"))
    (r / "tcad" / "moscap2d" / "provenance.json").write_text(
        '{\n  "generator_sha256": "feedface"\n}\n', "utf-8"
    )
    return r


@pytest.fixture
def bare(tmp_path):
    b = tmp_path / "cache.git"
    _git("init", "-q", "--bare", "-b", "main", str(b), cwd=tmp_path)
    return b


@pytest.fixture
def cache(tmp_path, bare):
    c = tmp_path / "cache"
    outcache.init(c, remote=str(bare))
    return c


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- configuration and layout ---------------------------------------------------------------


def test_committed_config():
    cfg = outcache.load_config()
    assert cfg["repo_ssh"] == "git@github.com:mithro/gf180-tcad-output-cache.git"
    assert cfg["repo_https"] == "https://github.com/mithro/gf180-tcad-output-cache"
    assert cfg["max_object_bytes"] <= 95_000_000
    (mesh,) = cfg["artefacts"]
    assert (mesh["pattern"], mesh["meta"], mesh["hash_key"]) == (
        "tcad/**/mesh.msh",
        "cv.meta.json",
        "mesh_sha256",
    )
    text = outcache.CONFIG_PATH.read_text("utf-8")
    assert text == json.dumps(cfg, indent=2, sort_keys=True) + "\n"


def test_object_relpath():
    h = "4b835acdae86b72c116c0ca69952cd62a10cac2e583374a80669372e086bec04"
    assert outcache.object_relpath(h, "msh", "gzip") == f"objects/sha256/4b/{h}.msh.gz"
    assert outcache.object_relpath(h, "bin", None) == f"objects/sha256/4b/{h}.bin"
    with pytest.raises(ValueError):
        outcache.object_relpath("xyz", "msh", "gzip")


# --- deterministic compression --------------------------------------------------------------


def test_compression_is_deterministic(tmp_path):
    src = tmp_path / "mesh.msh"
    src.write_bytes(_mesh_bytes("x"))
    a, b = tmp_path / "a.gz", tmp_path / "b.gz"
    outcache.compress(src, a)
    os.utime(src, (0, 1_000_000_000))  # a different mtime must not reach the header
    outcache.compress(src, b)
    assert a.read_bytes() == b.read_bytes()
    raw = a.read_bytes()
    assert raw[4:8] == b"\0\0\0\0"  # MTIME 0
    assert not raw[3] & 0x08  # no FNAME
    assert gzip.decompress(raw) == src.read_bytes()
    assert len(raw) < src.stat().st_size


# --- init -----------------------------------------------------------------------------------


def _tree(d: Path) -> dict[str, bytes]:
    return {
        p.relative_to(d).as_posix(): p.read_bytes()
        for p in sorted(d.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(d).parts
    }


def test_init_is_byte_identical_twice(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    outcache.init(a, remote="unused-a")
    outcache.init(b, remote="unused-b")
    ta, tb = _tree(a), _tree(b)
    assert ta == tb
    assert set(ta) == {"README.md", "index.json", ".gitattributes"}
    assert json.loads(ta["index.json"]) == {"format": 1, "objects": {}}
    readme = ta["README.md"].decode()
    for phrase in (
        "regenerable",
        "--depth 1",
        "wiped",
        "mithro/gf180-tcad",
        "MANIFEST.sha256",
        "never depend on its history",
    ):
        assert phrase in readme, phrase
    assert _git("log", "--format=%s", cwd=a).strip()
    assert _git("remote", "get-url", "origin", cwd=a).strip() == "unused-a"


def test_init_refuses_a_non_empty_directory(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / "x").write_text("x", "utf-8")
    with pytest.raises(ValueError, match="not empty"):
        outcache.init(d, remote="r")


# --- scan, push ------------------------------------------------------------------------------


def test_scan_finds_the_meshes(results):
    arts = outcache.scan(results)
    assert [a.path for a in arts] == [f"results/{JOB_A}/mesh.msh", f"results/{JOB_B}/mesh.msh"]
    a = arts[0]
    assert a.sha256 == _sha(results / JOB_A / "mesh.msh")
    assert a.generator_sha256 == "feedface"
    assert a.job == {"device": "nfet_05v0", "dim": 2, "dir": JOB_A, "params": "start"}


def test_scan_refuses_a_mesh_its_meta_does_not_name(results):
    _job(results, JOB_A, _mesh_bytes("a"), meta_hash="0" * 64)
    with pytest.raises(ValueError, match="mesh_sha256"):
        outcache.scan(results)


def test_push_round_trip_through_a_bare_repo(results, cache, bare, tmp_path):
    rep = outcache.push(cache, results, commit=COMMIT, date=DATE, publish=True)
    assert len(rep.added) == 2 and not rep.present and not rep.too_large
    assert outcache.verify(cache) == []
    # A second push adds nothing and makes no commit.
    head = _git("rev-parse", "HEAD", cwd=cache)
    rep2 = outcache.push(cache, results, commit=COMMIT, date=DATE, publish=True)
    assert not rep2.added and len(rep2.present) == 2
    assert _git("rev-parse", "HEAD", cwd=cache) == head
    assert COMMIT in _git("log", "-1", "--format=%B", cwd=bare)

    # Pull by results path, from the bare repository (a clone, as from GitHub).
    mesh = results / JOB_A / "mesh.msh"
    want = mesh.read_bytes()
    mesh.unlink()
    outcache.pull(str(bare), str(mesh), results=results, scratch=tmp_path / "scratch")
    assert mesh.read_bytes() == want
    # Pull by hash into an explicit file.
    out = tmp_path / "by-hash.msh"
    h = _sha(results / JOB_B / "mesh.msh")
    outcache.pull(str(cache), h, results=results, out=out, scratch=tmp_path / "scratch")
    assert _sha(out) == h
    assert not any((tmp_path / "scratch").iterdir())  # clones removed


def test_push_dry_run_writes_nothing(results, cache):
    before = _tree(cache)
    head = _git("rev-parse", "HEAD", cwd=cache)
    rep = outcache.push(cache, results, commit=COMMIT, date=DATE, dry_run=True)
    assert len(rep.added) == 2
    assert _tree(cache) == before
    assert _git("rev-parse", "HEAD", cwd=cache) == head


def test_index_is_deterministic(results, tmp_path):
    texts = []
    for name in ("c1", "c2"):
        c = tmp_path / name
        outcache.init(c, remote="r")
        outcache.push(c, results, commit=COMMIT, date=DATE)
        texts.append((c / "index.json").read_bytes())
        assert _tree(c).keys() == _tree(tmp_path / "c1").keys()
    assert texts[0] == texts[1]
    index = json.loads(texts[0])
    entry = index["objects"][_sha(results / JOB_A / "mesh.msh")]
    assert entry["paths"] == [f"results/{JOB_A}/mesh.msh"]
    assert entry["primary_commit"] == COMMIT and entry["date"] == DATE
    assert entry["generator_sha256"] == "feedface"
    assert entry["size"] == (results / JOB_A / "mesh.msh").stat().st_size
    assert entry["compressed_size"] == (tmp_path / "c1" / entry["object"]).stat().st_size
    assert texts[0].decode() == json.dumps(index, indent=2, sort_keys=True) + "\n"


def test_same_mesh_at_two_paths_is_one_object(results, cache):
    _job(results, "tcad/moscap2d/nfet_05v0/calibrated/w10p0_l0p60", _mesh_bytes("a"))
    outcache.push(cache, results, commit=COMMIT, date=DATE)
    index = json.loads((cache / "index.json").read_text("utf-8"))
    assert len(index["objects"]) == 2
    entry = index["objects"][_sha(results / JOB_A / "mesh.msh")]
    other = "results/tcad/moscap2d/nfet_05v0/calibrated/w10p0_l0p60/mesh.msh"
    assert entry["paths"] == sorted([f"results/{JOB_A}/mesh.msh", other])


def test_size_cap(results, cache):
    cfg = dict(outcache.load_config(), max_object_bytes=100)
    rep = outcache.push(cache, results, commit=COMMIT, date=DATE, config=cfg)
    assert len(rep.too_large) == 2 and not rep.added
    assert json.loads((cache / "index.json").read_text("utf-8"))["objects"] == {}
    assert not [p for p in cache.rglob("*") if ".git" not in p.parts and p.suffix == ".gz"]


# --- pull refusals, verify --------------------------------------------------------------------


def test_pull_refuses_a_hash_mismatch(results, cache, tmp_path):
    outcache.push(cache, results, commit=COMMIT, date=DATE)
    h = _sha(results / JOB_A / "mesh.msh")
    obj = cache / outcache.object_relpath(h, "msh", "gzip")
    obj.write_bytes(gzip.compress(b"tampered\n", mtime=0))
    out = tmp_path / "x.msh"
    with pytest.raises(outcache.HashMismatch):
        outcache.pull(str(cache), h, results=results, out=out, scratch=tmp_path / "s")
    assert not out.exists()
    assert not [p for p in tmp_path.iterdir() if p.name.startswith("x.msh")]
    problems = outcache.verify(cache)
    assert any(h in p for p in problems), problems


def test_pull_refuses_to_overwrite_a_different_file(results, cache, tmp_path):
    outcache.push(cache, results, commit=COMMIT, date=DATE)
    h = _sha(results / JOB_A / "mesh.msh")
    out = tmp_path / "x.msh"
    out.write_bytes(b"something else\n")
    with pytest.raises(FileExistsError):
        outcache.pull(str(cache), h, results=results, out=out, scratch=tmp_path / "s")
    assert out.read_bytes() == b"something else\n"


def test_pull_of_an_unknown_hash(results, cache, tmp_path):
    with pytest.raises(KeyError):
        outcache.pull(str(cache), "f" * 64, results=results, out=tmp_path / "o", scratch=tmp_path)


def test_verify_finds_an_unindexed_object_and_a_missing_one(results, cache):
    outcache.push(cache, results, commit=COMMIT, date=DATE)
    h = _sha(results / JOB_A / "mesh.msh")
    obj = cache / outcache.object_relpath(h, "msh", "gzip")
    stray = obj.with_name("f" * 64 + ".msh.gz")
    stray.write_bytes(obj.read_bytes())
    obj.unlink()
    problems = outcache.verify(cache)
    assert any("missing" in p and h in p for p in problems), problems
    assert any("not in index.json" in p for p in problems), problems


# --- status -----------------------------------------------------------------------------------


def test_status(results, cache, tmp_path):
    outcache.push(cache, results, commit=COMMIT, date=DATE)
    # A third job whose mesh only its meta names (not here, not in the cache).
    d = results / "tcad/moscap2d/pfet_05v0/start/w10p0_l2p00"
    d.mkdir(parents=True)
    (d / "cv.meta.json").write_text(json.dumps({"mesh_sha256": "e" * 64}) + "\n", "utf-8")
    st = {s.path: s for s in outcache.status(str(cache), results, scratch=tmp_path / "s")}
    assert set(st) == {
        f"results/{JOB_A}/mesh.msh",
        f"results/{JOB_B}/mesh.msh",
        "results/tcad/moscap2d/pfet_05v0/start/w10p0_l2p00/mesh.msh",
    }
    assert st[f"results/{JOB_A}/mesh.msh"].in_cache
    assert st[f"results/{JOB_A}/mesh.msh"].local
    missing = st["results/tcad/moscap2d/pfet_05v0/start/w10p0_l2p00/mesh.msh"]
    assert (missing.sha256, missing.in_cache, missing.local) == ("e" * 64, False, False)


def test_status_of_the_committed_results_names_every_mesh_sha256():
    metas = sorted((REPO / "results").glob("tcad/**/cv.meta.json"))
    named = {
        json.loads(m.read_text("utf-8"))["mesh_sha256"]
        for m in metas
        if "mesh_sha256" in json.loads(m.read_text("utf-8"))
    }
    assert named
    assert {e.sha256 for e in outcache.expected(REPO / "results")} == named


# --- the command line -------------------------------------------------------------------------


def _run_tool(*args, cwd):
    return subprocess.run(
        [sys.executable, str(TOOL), *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def test_tool_round_trip(results, bare, tmp_path):
    primary = results.parent
    _git("init", "-q", "-b", "main", cwd=primary)
    _git("add", "-A", cwd=primary)
    _git("commit", "-q", "-m", "results", cwd=primary)
    commit = _git("rev-parse", "HEAD", cwd=primary).strip()
    c = tmp_path / "cachedir"
    r = _run_tool("init", str(c), "--remote", str(bare), cwd=primary)
    assert r.returncode == 0, r.stderr
    r = _run_tool("push", "--cache", str(c), "--results", str(results), "--dry-run", cwd=primary)
    assert r.returncode == 0, r.stderr
    assert "would add" in r.stdout
    r = _run_tool("push", "--cache", str(c), "--results", str(results), "--publish", cwd=primary)
    assert r.returncode == 0, r.stderr
    assert r.stdout.count("added") >= 2
    assert commit in _git("log", "-1", "--format=%B", cwd=bare)
    r = _run_tool("verify", "--cache", str(c), cwd=primary)
    assert r.returncode == 0, r.stdout + r.stderr
    scratch = ["--scratch", str(tmp_path / "scratch")]
    r = _run_tool("status", "--cache", str(bare), "--results", str(results), *scratch, cwd=primary)
    assert r.returncode == 0, r.stderr
    assert "missing" not in r.stdout
    mesh = results / JOB_B / "mesh.msh"
    want = mesh.read_bytes()
    mesh.unlink()
    r = _run_tool(
        "pull", "--cache", str(bare), str(mesh), "--results", str(results), *scratch, cwd=primary
    )
    assert r.returncode == 0, r.stderr
    assert mesh.read_bytes() == want


def test_tool_verify_fails_on_a_bad_object(results, cache, tmp_path):
    outcache.push(cache, results, commit=COMMIT, date=DATE)
    h = _sha(results / JOB_A / "mesh.msh")
    (cache / outcache.object_relpath(h, "msh", "gzip")).write_bytes(gzip.compress(b"x", mtime=0))
    r = _run_tool("verify", "--cache", str(cache), cwd=tmp_path)
    assert r.returncode == 1
    assert h in r.stdout + r.stderr


def test_tool_is_a_thin_wrapper():
    loader = importlib.machinery.SourceFileLoader("output_cache_tool", str(TOOL))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    assert mod.main is outcache.main
    assert os.access(TOOL, os.X_OK)


def test_outcache_is_not_a_generator_module():
    from gf180tcad import reference, tcad

    assert tcad.TCAD_GENERATORS  # every TCAD entry point's own list (issue #34)
    for entry, modules in tcad.TCAD_GENERATORS.items():
        assert "gf180tcad.outcache" not in modules, entry
        files = tcad.generator_files(entry)
        assert "data/output-cache.json" not in files, entry
        assert "src/gf180tcad/outcache.py" not in files, entry
    assert "gf180tcad.outcache" not in reference.GENERATOR_MODULES
    assert not any("outcache" in f or "output-cache" in f for f in tcad.TCAD_GENERATOR_EXTRA_FILES)


# --- review fixes (PR #49) --------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "results/../../escaped.txt",
        "/etc/escaped.txt",
        "results//x.msh",
        "results/",
        "elsewhere/x.msh",
        "results/a/../../x.msh",
    ],
)
def test_pull_refuses_an_index_path_outside_results(results, cache, tmp_path, bad):
    outcache.push(cache, results, commit=COMMIT, date=DATE)
    h = _sha(results / JOB_A / "mesh.msh")
    index = json.loads((cache / "index.json").read_text("utf-8"))
    index["objects"][h]["paths"] = [bad]
    (cache / "index.json").write_text(outcache.dump_index(index), "utf-8")
    (results / JOB_A / "mesh.msh").unlink()
    with pytest.raises(ValueError, match="index path"):
        outcache.pull(str(cache), h, results=results, scratch=tmp_path / "s")
    assert not list(tmp_path.rglob("escaped.txt"))


def test_push_refuses_a_cache_that_is_not_its_own_repository(results, cache, tmp_path):
    outer = tmp_path / "outer"
    outer.mkdir()
    _git("init", "-q", "-b", "main", cwd=outer)
    (outer / "unrelated.txt").write_text("unrelated\n", "utf-8")
    inner = outer / "cache"
    inner.mkdir()
    for name in ("index.json", "README.md", ".gitattributes"):
        (inner / name).write_bytes((cache / name).read_bytes())
    with pytest.raises(ValueError, match="not the root of its own git repository"):
        outcache.push(inner, results, commit=COMMIT, date=DATE)
    assert _git("status", "--porcelain", cwd=outer).startswith("??")  # nothing staged
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=outer, capture_output=True, text=True, check=False
    )
    assert r.returncode != 0  # no commit was made


@pytest.mark.parametrize("ext", ["", "../x", "MSH", "msh/..", "a..b", ".msh"])
def test_object_relpath_refuses_a_bad_ext(ext):
    with pytest.raises(ValueError, match="ext"):
        outcache.object_relpath("a" * 64, ext, "gzip")
    assert outcache.object_relpath("a" * 64, "tar.gz", None).endswith(".tar.gz")


def test_an_uninitialised_cache_is_reported_clearly(results, tmp_path, bare):
    empty = tmp_path / "empty-clone"
    empty.mkdir()
    with pytest.raises(ValueError, match="not initialised.*init.*--remote"):
        outcache.push(empty, results, commit=COMMIT, date=DATE)
    with pytest.raises(ValueError, match="not initialised.*init.*--remote"):
        outcache.status(str(bare), results, scratch=tmp_path / "s")
    r = _run_tool("status", "--cache", str(bare), "--results", str(results),
                  "--scratch", str(tmp_path / "s"), cwd=tmp_path)  # fmt: skip
    assert r.returncode == 1 and "not initialised" in r.stderr and "Traceback" not in r.stderr


def test_readme_documents_the_first_population():
    text = outcache.readme_text(outcache.load_config())
    assert (
        "init tmp/output-cache --remote git@github.com:mithro/gf180-tcad-output-cache.git" in text
    )
    doc = (REPO / "docs" / "reproduce" / "output-cache.md").read_text("utf-8")
    assert "--remote git@github.com:mithro/gf180-tcad-output-cache.git" in doc


def test_push_restores_an_indexed_object_that_is_missing(results, cache):
    outcache.push(cache, results, commit=COMMIT, date=DATE)
    h = _sha(results / JOB_A / "mesh.msh")
    obj = cache / outcache.object_relpath(h, "msh", "gzip")
    obj.unlink()
    rep = outcache.push(cache, results, commit=COMMIT, date=DATE)
    assert [a.sha256 for a in rep.added] == [h]
    assert obj.is_file() and outcache.verify(cache) == []
