# SPDX-License-Identifier: Apache-2.0
"""The output cache: a shared, regenerable store of large git-ignored result artefacts.

Some generated files are too large to commit here but slow to regenerate, for example the
25-62 MB gmsh mesh ``mesh.msh`` of each 2D job (docs/limitations/moscap2d.md). The committed
results name each one by its sha256 (``mesh_sha256`` in the ``cv.meta.json`` beside it). The
output cache is a separate plain git repository,
https://github.com/mithro/gf180-tcad-output-cache, holding those bytes under their
hash so that anyone can fetch them instead of rerunning the job:

    objects/sha256/<first 2 hex>/<sha256>.<ext>[.gz]    the file, gzip-compressed if configured
    index.json                                          sha256 -> paths, sizes, producing commit
    README.md                                           the contract (written by :func:`init`)

The key is the sha256 of the **uncompressed** file, so it is the hash the committed metadata
already names. Compression is deterministic (:func:`compress`: no file name, mtime 0). The cache
holds no provenance: ``results/MANIFEST.sha256`` and the ``provenance.json`` files of this
repository are the truth, and a file fetched from the cache is accepted only when its sha256 is
the one they name (:func:`pull` refuses anything else). Everything in the cache can be
regenerated from this repository, so the cache repository may be wiped and recreated at any time
(:func:`init`, then :func:`push`).

The configuration (which files are cacheable, the repository URLs, the per-object size cap that
keeps the cache free of git-LFS) is :data:`CONFIG_PATH`. The pure file logic (:func:`scan`,
:func:`compress`, :func:`verify`, the index) is separate from the few ``git`` calls
(:func:`init`, :func:`push`, :func:`open_cache`). This module is not imported by any generator
module, so using the cache changes no ``generator_sha256``.

Command line: ``tools/output-cache`` (or ``python -m gf180tcad.outcache``), see :func:`main` and
docs/reproduce/output-cache.md.
"""

import argparse
import contextlib
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]
# The committed configuration: cacheable artefacts, repository URLs, branch, size cap.
CONFIG_PATH = REPO_ROOT / "data" / "output-cache.json"
INDEX_NAME = "index.json"
README_NAME = "README.md"
ATTRIBUTES_NAME = ".gitattributes"
# Version of the index.json layout.
INDEX_FORMAT = 1
OBJECTS_DIR = "objects/sha256"
# How index paths name the primary repository's results tree.
RESULTS_PREFIX = "results/"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_GIT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
_CHUNK = 1 << 20
_COMPRESSIONS = {"gzip": ".gz", None: ""}


class HashMismatch(ValueError):
    """A cached object whose content does not hash to the sha256 it is stored under."""


@dataclass(frozen=True)
class Expected:
    """A cacheable file a committed meta names: its index ``path``, ``sha256`` and local file."""

    path: str
    sha256: str
    file: Path
    artefact: dict = field(repr=False)


@dataclass(frozen=True)
class Artefact:
    """A cacheable file present in the results tree, checked against the meta that names it."""

    path: str
    sha256: str
    file: Path
    size: int
    ext: str
    compression: str | None
    generator_sha256: str | None
    job: dict


@dataclass
class PushReport:
    """What :func:`push` did: ``added`` and already ``present`` artefacts, and those
    ``too_large`` (artefact, compressed size) to store."""

    added: list[Artefact] = field(default_factory=list)
    present: list[Artefact] = field(default_factory=list)
    too_large: list[tuple[Artefact, int]] = field(default_factory=list)
    committed: bool = False


@dataclass(frozen=True)
class Status:
    """A file the committed metas name: whether the cache has it and whether it is here."""

    path: str
    sha256: str
    in_cache: bool
    local: bool


# --- configuration, layout, index -------------------------------------------------------------


def load_config(path: Path | None = None) -> dict:
    """The output-cache configuration (:data:`CONFIG_PATH` by default)."""
    return json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))


def object_relpath(sha256: str, ext: str, compression: str | None) -> str:
    """Cache-relative POSIX path of the object of ``sha256`` (of the uncompressed file)."""
    if not _SHA256.fullmatch(sha256):
        raise ValueError(f"not a lowercase hex sha256: {sha256!r}")
    if compression not in _COMPRESSIONS:
        raise ValueError(f"unknown compression {compression!r}")
    return f"{OBJECTS_DIR}/{sha256[:2]}/{sha256}.{ext}{_COMPRESSIONS[compression]}"


def dump_index(index: dict) -> str:
    """``index.json`` text: two-space indent, sorted keys, final newline (deterministic)."""
    return json.dumps(index, indent=2, sort_keys=True) + "\n"


def load_index(cache: Path) -> dict:
    """The ``index.json`` of the cache checkout ``cache``."""
    index = json.loads((Path(cache) / INDEX_NAME).read_text(encoding="utf-8"))
    if index.get("format") != INDEX_FORMAT:
        raise ValueError(f"{INDEX_NAME}: format {index.get('format')!r}, not {INDEX_FORMAT}")
    return index


def readme_text(config: dict) -> str:
    """The cache repository's README.md: the contract, the commands and the repo settings."""
    primary, https, ssh = config["primary_repo"], config["repo_https"], config["repo_ssh"]
    slug = https.removeprefix("https://github.com/")
    branch = config["branch"]
    cap_mb = config["max_object_bytes"] / 1e6
    kinds = "\n".join(
        f"- `{a['pattern']}` ({a['description']}): named by `{a['hash_key']}` in the "
        f"`{a['meta']}` beside it; stored as `.{a['ext']}{_COMPRESSIONS[a['compression']]}`."
        for a in config["artefacts"]
    )
    return f"""\
# gf180-tcad output cache

A shared cache of large generated files of [{primary.removeprefix("https://github.com/")}]({primary})
that are kept out of that repository. This README is written by `tools/output-cache init` there;
do not edit it here.

## The contract

- **Everything here is regenerable** from {primary}: each file is a result of a job that
  repository describes and can rerun. Nothing here is original data.
- **This repository may be wiped and recreated at any time** (a new root commit, force-pushed).
  Clone it with `git clone --depth 1`, and **never depend on its history**: only the current
  tree of `{branch}` matters.
- **No provenance lives here.** The primary repository's `results/MANIFEST.sha256` and its
  `provenance.json` and `*.meta.json` files are the truth. This cache only holds bytes whose
  sha256 they name; a fetched file is used only if its sha256 matches (`tools/output-cache pull`
  checks and refuses a mismatch). `index.json` records where a file came from as a convenience.
- No git-LFS: every object is a plain git blob under {cap_mb:g} MB.

## Layout

- `objects/sha256/<first 2 hex>/<sha256>.<ext>[.gz]`: one file per sha256 of the
  **uncompressed** content. `.gz` objects are gzip-compressed deterministically (no file name,
  mtime 0) and must be decompressed before the hash is checked.
- `index.json`: sorted JSON, `objects` maps each sha256 to its `object` path, `ext`,
  `compression`, `size`, `compressed_size`, the results `paths` in the primary repository, the
  `generator_sha256` of its results tree, the `primary_commit` it was pushed from, the `date` and
  the `job`.

Cacheable files:

{kinds}

## Use (from a checkout of the primary repository)

```sh
tools/output-cache status                        # which named files the cache has
tools/output-cache pull results/<job dir>/mesh.msh   # fetch one, verified, into place
tools/output-cache pull <sha256> --out FILE
```

Add files after a run (needs write access; `--dry-run` first):

```sh
git clone --depth 1 {ssh} tmp/output-cache
tools/output-cache push --cache tmp/output-cache --results results --publish
```

Recreate from nothing (every listed file must be present locally):

```sh
tools/output-cache init tmp/output-cache-new
tools/output-cache push --cache tmp/output-cache-new --results results
git -C tmp/output-cache-new push --force origin {branch}
```

## Repository settings

The owner's standard settings, except where the contract needs otherwise:

- Wiki, projects and discussions disabled; merge commits only (no squash or rebase merges);
  delete head branches on merge; secret scanning and push protection enabled.
- **Force pushes to `{branch}` are allowed**, unlike the standard branch protection: a wipe is a
  force push of a new root commit. Deletion of `{branch}` stays disallowed.
- No `v0.0` tag and no tag ruleset: tags would pin history that may be discarded.
- No git-LFS (bandwidth quotas); objects stay under the size cap instead.

Repository: {https} (`{slug}`).
"""


ATTRIBUTES_TEXT = "objects/** binary\n"


def _write_static(cache: Path, config: dict) -> None:
    (cache / README_NAME).write_text(readme_text(config), encoding="utf-8", newline="\n")
    (cache / ATTRIBUTES_NAME).write_text(ATTRIBUTES_TEXT, encoding="utf-8", newline="\n")


# --- file logic -------------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """sha256 hex digest of the file at ``path``, read in chunks."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def compress(src: Path, dst: Path) -> None:
    """gzip ``src`` into ``dst`` deterministically: level 9, no file name, mtime 0."""
    with (
        Path(src).open("rb") as fin,
        Path(dst).open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as gz,
    ):
        shutil.copyfileobj(fin, gz, _CHUNK)


def _open_object(path: Path, compression: str | None):
    return gzip.open(path, "rb") if compression == "gzip" else Path(path).open("rb")


def _content_digest(path: Path, compression: str | None) -> tuple[str, int]:
    h, n = hashlib.sha256(), 0
    with _open_object(path, compression) as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def extract(obj: Path, compression: str | None, sha256: str, dest: Path) -> None:
    """Write the content of the cached ``obj`` to ``dest`` if it hashes to ``sha256``.

    It is written beside ``dest`` first and moved into place only after the check, so a
    mismatch (:class:`HashMismatch`) leaves nothing behind.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(f".{dest.name}.partial-{os.getpid()}")
    h = hashlib.sha256()
    try:
        with _open_object(obj, compression) as fin, part.open("wb") as fout:
            for chunk in iter(lambda: fin.read(_CHUNK), b""):
                h.update(chunk)
                fout.write(chunk)
        if h.hexdigest() != sha256:
            raise HashMismatch(f"{obj}: content hashes to {h.hexdigest()}, not {sha256}")
        os.replace(part, dest)
    finally:
        part.unlink(missing_ok=True)


def _meta_pattern(artefact: dict) -> str:
    return (PurePosixPath(artefact["pattern"]).parent / artefact["meta"]).as_posix()


def expected(results: Path, config: dict | None = None) -> list[Expected]:
    """The cacheable files the metas under ``results`` name, sorted by path."""
    cfg = config or load_config()
    results = Path(results)
    out = []
    for art in cfg["artefacts"]:
        name = PurePosixPath(art["pattern"]).name
        for meta in sorted(results.glob(_meta_pattern(art))):
            data = json.loads(meta.read_text(encoding="utf-8"))
            if art["hash_key"] not in data:
                continue
            file = meta.parent / name
            rel = file.relative_to(results).as_posix()
            out.append(Expected(RESULTS_PREFIX + rel, data[art["hash_key"]], file, art))
    return sorted(out, key=lambda e: e.path)


def _generator_sha256(file: Path, results: Path) -> str | None:
    """``generator_sha256`` of the nearest ``provenance.json`` above ``file`` within ``results``."""
    d = file.parent
    while True:
        prov = d / "provenance.json"
        if prov.is_file():
            return json.loads(prov.read_text(encoding="utf-8")).get("generator_sha256")
        if d == results or d == d.parent:
            return None
        d = d.parent


def scan(results: Path, config: dict | None = None) -> list[Artefact]:
    """The cacheable files present under ``results``, each checked against its meta.

    A file that does not hash to the sha256 its meta names (a stale mesh), or that no meta names,
    raises ValueError: only the bytes the committed results name may enter the cache.
    """
    cfg = config or load_config()
    results = Path(results)
    named = {e.file: e for e in expected(results, cfg)}
    out = []
    for art in cfg["artefacts"]:
        for file in sorted(results.glob(art["pattern"])):
            rel = file.relative_to(results).as_posix()
            e = named.get(file)
            if e is None:
                raise ValueError(f"{rel}: no {art['meta']} beside it names its sha256")
            actual = sha256_file(file)
            if actual != e.sha256:
                raise ValueError(
                    f"{rel}: sha256 {actual}, but its {art['meta']} names "
                    f"{art['hash_key']} {e.sha256} (a stale file? regenerate or remove it)"
                )
            meta = json.loads((file.parent / art["meta"]).read_text(encoding="utf-8"))
            job = {k: meta[k] for k in art.get("job_keys", ()) if k in meta}
            job["dir"] = file.parent.relative_to(results).as_posix()
            out.append(
                Artefact(
                    path=e.path,
                    sha256=actual,
                    file=file,
                    size=file.stat().st_size,
                    ext=art["ext"],
                    compression=art["compression"],
                    generator_sha256=_generator_sha256(file, results),
                    job=job,
                )
            )
    return sorted(out, key=lambda a: a.path)


def add_objects(
    cache: Path,
    artefacts: list[Artefact],
    *,
    commit: str,
    date: str,
    config: dict | None = None,
    dry_run: bool = False,
) -> PushReport:
    """Store the missing ``artefacts`` in the checkout ``cache`` and update its index (no git).

    An object whose compressed size exceeds ``max_object_bytes`` is left out (``too_large``).
    ``dry_run`` reports what would be added and writes nothing.
    """
    cfg = config or load_config()
    cache = Path(cache)
    cap = cfg["max_object_bytes"]
    index = load_index(cache)
    objects = index["objects"]
    rep = PushReport()
    for a in artefacts:
        entry = objects.get(a.sha256)
        if entry is not None:
            rep.present.append(a)
            if not dry_run and a.path not in entry["paths"]:
                entry["paths"] = sorted({*entry["paths"], a.path})
            continue
        if dry_run:
            rep.added.append(a)
            continue
        rel = object_relpath(a.sha256, a.ext, a.compression)
        dest = cache / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".partial")
        try:
            if a.compression == "gzip":
                compress(a.file, part)
            else:
                shutil.copyfile(a.file, part)
            csize = part.stat().st_size
            if csize > cap:
                rep.too_large.append((a, csize))
                continue
            os.replace(part, dest)
        finally:
            part.unlink(missing_ok=True)
            with contextlib.suppress(OSError):
                dest.parent.rmdir()  # only if it stayed empty
        objects[a.sha256] = {
            "compressed_size": csize,
            "compression": a.compression,
            "date": date,
            "ext": a.ext,
            "generator_sha256": a.generator_sha256,
            "job": a.job,
            "object": rel,
            "paths": [a.path],
            "primary_commit": commit,
            "size": a.size,
        }
        rep.added.append(a)
    if not dry_run:
        (cache / INDEX_NAME).write_text(dump_index(index), encoding="utf-8", newline="\n")
        _write_static(cache, cfg)
    return rep


def verify(cache: Path, config: dict | None = None) -> list[str]:
    """Problems of the checkout ``cache`` (empty when consistent).

    Every indexed object exists at its layout path with its recorded sizes and content hash, and
    under the size cap; every file under ``objects/`` is indexed; ``index.json``, README.md and
    .gitattributes are exactly what this module writes.
    """
    cfg = config or load_config()
    cache = Path(cache)
    try:
        index = load_index(cache)
    except (OSError, ValueError) as e:
        return [f"{INDEX_NAME}: {e}"]
    problems = []
    if (cache / INDEX_NAME).read_text(encoding="utf-8") != dump_index(index):
        problems.append(f"{INDEX_NAME}: not in canonical form (sorted keys, two-space indent)")
    for name, text in ((README_NAME, readme_text(cfg)), (ATTRIBUTES_NAME, ATTRIBUTES_TEXT)):
        p = cache / name
        if not p.is_file() or p.read_text(encoding="utf-8") != text:
            problems.append(f"{name}: missing or not the generated text (run push to rewrite)")
    listed = set()
    for sha, e in sorted(index["objects"].items()):
        try:
            rel = object_relpath(sha, e["ext"], e["compression"])
        except (KeyError, ValueError) as err:
            problems.append(f"{sha}: bad index entry ({err})")
            continue
        listed.add(rel)
        if e.get("object") != rel:
            problems.append(f"{sha}: object path {e.get('object')!r}, expected {rel}")
        obj = cache / rel
        if not obj.is_file():
            problems.append(f"{sha}: object {rel} missing")
            continue
        csize = obj.stat().st_size
        if csize != e.get("compressed_size"):
            problems.append(f"{sha}: {rel} is {csize} bytes, index says {e.get('compressed_size')}")
        if csize > cfg["max_object_bytes"]:
            problems.append(f"{sha}: {rel} is over the {cfg['max_object_bytes']} byte cap")
        try:
            actual, size = _content_digest(obj, e["compression"])
        except (OSError, EOFError, gzip.BadGzipFile) as err:
            problems.append(f"{sha}: {rel} cannot be read ({err})")
            continue
        if actual != sha:
            problems.append(f"{sha}: {rel} content hashes to {actual}")
        elif size != e.get("size"):
            problems.append(f"{sha}: content is {size} bytes, index says {e.get('size')}")
    root = cache / OBJECTS_DIR
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(cache).as_posix()
            if p.is_file() and rel not in listed:
                problems.append(f"{rel}: not in {INDEX_NAME}")
    return problems


# --- git --------------------------------------------------------------------------------------


def _git(args: list[str], cwd: Path) -> str:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_VARS}
    r = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed ({r.returncode}): {r.stderr.strip()}")
    return r.stdout


def init(cache: Path, *, remote: str | None = None, config: dict | None = None) -> None:
    """Create a cache checkout at ``cache`` (absent or empty): README.md, an empty index.json,
    .gitattributes, one commit on the configured branch, ``origin`` = ``remote`` (default the
    configured SSH URL). The files are the same every time, so the whole cache repository can
    be recreated from nothing."""
    cfg = config or load_config()
    cache = Path(cache)
    if cache.exists() and any(cache.iterdir()):
        raise ValueError(f"{cache} is not empty")
    cache.mkdir(parents=True, exist_ok=True)
    (cache / INDEX_NAME).write_text(
        dump_index({"format": INDEX_FORMAT, "objects": {}}), encoding="utf-8", newline="\n"
    )
    _write_static(cache, cfg)
    _git(["init", "-q", "-b", cfg["branch"]], cache)
    _git(["remote", "add", "origin", remote or cfg["repo_ssh"]], cache)
    _git(["add", INDEX_NAME, README_NAME, ATTRIBUTES_NAME], cache)
    _git(["commit", "-q", "-m", "Initialise the output cache (README.md, empty index.json)"], cache)


def _primary_commit(results: Path) -> tuple[str, str]:
    """``(commit, committer date YYYY-MM-DD)`` of HEAD of the repository holding ``results``."""
    out = _git(["log", "-1", "--format=%H %cs", "HEAD"], Path(results))
    commit, date = out.split()
    return commit, date


def push(
    cache: Path,
    results: Path,
    *,
    commit: str | None = None,
    date: str | None = None,
    dry_run: bool = False,
    publish: bool = False,
    config: dict | None = None,
) -> PushReport:
    """Add the cacheable files under ``results`` to the checkout ``cache`` and commit there.

    ``commit`` and ``date`` default to HEAD of the primary repository holding ``results``. The
    commit message names that commit. ``publish`` then pushes the branch to ``origin``.
    """
    cfg = config or load_config()
    cache, results = Path(cache), Path(results)
    arts = scan(results, cfg)
    if commit is None or date is None:
        c, d = _primary_commit(results)
        commit, date = commit or c, date or d
    rep = add_objects(cache, arts, commit=commit, date=date, config=cfg, dry_run=dry_run)
    if dry_run:
        return rep
    _git(["add", "-A"], cache)
    if _git(["status", "--porcelain"], cache).strip():
        body = "\n".join(f"{a.sha256}  {a.path}" for a in rep.added)
        msg = (
            f"Add {len(rep.added)} object(s) from {cfg['primary_repo']} at {commit}\n\n"
            f"primary commit: {commit}\n{body}\n"
        )
        _git(["commit", "-q", "-m", msg], cache)
        rep.committed = True
    if publish:
        _git(["push", "-q", "origin", f"HEAD:{cfg['branch']}"], cache)
    return rep


@contextlib.contextmanager
def open_cache(
    spec: str, scratch: Path | None = None, branch: str = "main"
) -> Iterator[tuple[Path, Callable[[list[str]], None]]]:
    """``(checkout, fetch)`` of the cache ``spec``: a checkout directory, used as it is, or a
    git URL or bare repository, cloned shallow and blobless into a temporary directory under
    ``scratch`` (default the repository's ``tmp/``) and removed afterwards. ``fetch(paths)``
    makes those cache-relative paths present in the checkout (only they are downloaded)."""
    local = Path(spec)
    if local.is_dir() and (local / INDEX_NAME).is_file():
        yield local, lambda paths: None
        return
    url = local.resolve().as_uri() if local.exists() else spec
    scratch = Path(scratch) if scratch is not None else REPO_ROOT / "tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="output-cache-", dir=scratch))
    try:
        d = tmp / "cache"
        _git(
            ["clone", "-q", "--depth", "1", "--filter=blob:none", "--no-checkout",
             "--branch", branch, url, str(d)],
            tmp,
        )  # fmt: skip

        def fetch(paths: list[str]) -> None:
            _git(["checkout", "-q", "HEAD", "--", *paths], d)

        fetch([INDEX_NAME])
        yield d, fetch
    finally:
        shutil.rmtree(tmp)


def _resolve_target(target: str, results: Path, cfg: dict) -> tuple[str, Path | None]:
    if _SHA256.fullmatch(target):
        return target, None
    p = Path(target).resolve()
    for e in expected(results, cfg):
        if e.file.resolve() == p:
            return e.sha256, Path(target)
    raise ValueError(f"{target}: not a sha256, nor a file a meta under {results} names")


def pull(
    spec: str,
    target: str,
    *,
    results: Path,
    out: Path | None = None,
    scratch: Path | None = None,
    force: bool = False,
    config: dict | None = None,
) -> Path:
    """Fetch the object named by ``target`` from the cache ``spec`` and write it, verified.

    ``target`` is a sha256, or the path of a cacheable file under ``results`` whose meta names
    its sha256 (written there). ``out`` overrides the destination; for a sha256 the default is
    the first results path the index records. A destination that exists with other content is
    refused (FileExistsError) unless ``force``; content that does not hash to the sha256 is
    refused (:class:`HashMismatch`). Returns the destination.
    """
    cfg = config or load_config()
    results = Path(results)
    sha, dest = _resolve_target(target, results, cfg)
    with open_cache(spec, scratch, cfg["branch"]) as (d, fetch):
        objects = load_index(d)["objects"]
        if sha not in objects:
            raise KeyError(f"{sha} is not in the output cache {spec}")
        e = objects[sha]
        if out is not None:
            dest = Path(out)
        elif dest is None:
            dest = results / e["paths"][0].removeprefix(RESULTS_PREFIX)
        if dest.exists():
            if sha256_file(dest) == sha:
                return dest
            if not force:
                raise FileExistsError(f"{dest} exists with other content (pass --force)")
        rel = object_relpath(sha, e["ext"], e["compression"])
        fetch([rel])
        extract(d / rel, e["compression"], sha, dest)
    return dest


def status(
    spec: str, results: Path, *, scratch: Path | None = None, config: dict | None = None
) -> list[Status]:
    """For each cacheable file the metas under ``results`` name: in the cache ``spec``, here."""
    cfg = config or load_config()
    with open_cache(spec, scratch, cfg["branch"]) as (d, _):
        objects = load_index(d)["objects"]
    return [
        Status(e.path, e.sha256, e.sha256 in objects, e.file.is_file())
        for e in expected(results, cfg)
    ]


# --- command line -----------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tools/output-cache", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init", help="create an empty cache checkout")
    p.add_argument("dir", type=Path)
    p.add_argument("--remote", default=None, help="origin URL (default: the configured SSH URL)")
    p = sub.add_parser("push", help="add the cacheable files of a results tree and commit")
    p.add_argument("--cache", type=Path, required=True, help="cache checkout")
    p.add_argument("--results", type=Path, default=Path("results"))
    p.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    p.add_argument("--publish", action="store_true", help="then git push to origin")
    p = sub.add_parser("pull", help="fetch one object, verified, into place")
    p.add_argument("target", help="sha256, or the results path of a cacheable file")
    p.add_argument("--cache", default=None, help="checkout dir or URL (default: the HTTPS URL)")
    p.add_argument("--results", type=Path, default=Path("results"))
    p.add_argument("--out", type=Path, default=None, help="destination file")
    p.add_argument("--force", action="store_true", help="overwrite a different existing file")
    p.add_argument("--scratch", type=Path, default=None, help="where clones go (default tmp/)")
    p = sub.add_parser("verify", help="check a cache checkout")
    p.add_argument("--cache", type=Path, required=True)
    p = sub.add_parser("status", help="which named files the cache has")
    p.add_argument("--cache", default=None, help="checkout dir or URL (default: the HTTPS URL)")
    p.add_argument("--results", type=Path, default=Path("results"))
    p.add_argument("--scratch", type=Path, default=None, help="where clones go (default tmp/)")
    return ap


def _run(a: argparse.Namespace, cfg: dict) -> int:
    if a.command == "init":
        init(a.dir, remote=a.remote, config=cfg)
        print(f"initialised {a.dir} (origin {a.remote or cfg['repo_ssh']})")
        return 0
    if a.command == "push":
        rep = push(a.cache, a.results, dry_run=a.dry_run, publish=a.publish, config=cfg)
        for x in rep.added:
            if a.dry_run:
                print(f"would add {x.sha256}  {x.path} ({x.size} bytes)")
            else:
                print(f"added {x.sha256}  {x.path} ({x.size} bytes)")
        for x in rep.present:
            print(f"present {x.sha256}  {x.path}")
        for x, csize in rep.too_large:
            print(
                f"too large {x.sha256}  {x.path}: {csize} bytes compressed, cap "
                f"{cfg['max_object_bytes']}",
                file=sys.stderr,
            )
        if not a.dry_run:
            print("committed" if rep.committed else "nothing to commit")
            if a.publish:
                print(f"pushed to origin {cfg['branch']}")
        return 1 if rep.too_large else 0
    if a.command == "pull":
        dest = pull(
            a.cache or cfg["repo_https"], a.target, results=a.results, out=a.out,
            scratch=a.scratch, force=a.force, config=cfg,
        )  # fmt: skip
        print(f"wrote {dest} (sha256 verified)")
        return 0
    if a.command == "verify":
        problems = verify(a.cache, cfg)
        for p in problems:
            print(p)
        if problems:
            return 1
        n = len(load_index(a.cache)["objects"])
        print(f"ok: {n} object(s)")
        return 0
    rows = status(a.cache or cfg["repo_https"], a.results, scratch=a.scratch, config=cfg)
    for s in rows:
        where = "in cache " if s.in_cache else "MISSING  "
        print(f"{where} {'local' if s.local else 'absent'}  {s.sha256}  {s.path}")
    print(f"{sum(s.in_cache for s in rows)} of {len(rows)} named file(s) are in the cache")
    return 0


def main(argv: list[str] | None = None) -> int:
    """``tools/output-cache {init,push,pull,verify,status}``; 0 on success, 1 on a failure."""
    a = _parser().parse_args(argv)
    try:
        return _run(a, load_config())
    except (ValueError, KeyError, FileExistsError, RuntimeError, OSError) as e:
        print(f"output-cache: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
