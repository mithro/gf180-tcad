# SPDX-License-Identifier: Apache-2.0
"""sha256 manifest of a results tree: lines ``<sha256>  <relpath>``, sorted by path."""

import argparse
import hashlib
import sys
from pathlib import Path


def _digest(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan(root: Path, manifest: Path) -> dict[str, str]:
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"manifest root is not an existing directory: {root}")
    root = root.resolve()
    skip = Path(manifest).resolve()
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            raise ValueError(f"{rel}: symlinks are not allowed in a results tree")
        if p.is_file() and p != skip:
            out[rel] = _digest(p)
    return out


def _sorted(paths) -> list[str]:
    return sorted(paths, key=lambda s: s.encode("utf-8"))


def update(root: Path, manifest: Path) -> None:
    files = _scan(root, manifest)
    lines = [f"{files[r]}  {r}\n" for r in _sorted(files)]
    Path(manifest).write_bytes("".join(lines).encode("utf-8"))


def _load(manifest: Path) -> dict[str, str]:
    out = {}
    for line in Path(manifest).read_bytes().decode("utf-8").split("\n"):
        if line:
            digest, sep, rel = line.partition("  ")
            if not sep or len(digest) != 64:
                raise ValueError(f"{manifest}: malformed line {line!r}")
            if rel in out:
                raise ValueError(f"{manifest}: duplicate entry for {rel!r}")
            out[rel] = digest
    return out


def verify(root: Path, manifest: Path) -> list[str]:
    """Relative paths that are changed, missing or extra versus the manifest, sorted."""
    want, have = _load(manifest), _scan(root, manifest)
    bad = {r for r in want.keys() & have.keys() if want[r] != have[r]}
    bad |= want.keys() ^ have.keys()
    return _sorted(bad)


# --- subset check -------------------------------------------------------------------------------
#
# A subset run (some jobs of the reference, regenerated elsewhere, e.g. on a GitHub-hosted runner)
# is compared with the committed manifest byte for byte: sha256 equality, no tolerance.
#
# The tree's root ``envelope.json`` is excluded on both sides. It is the min/max over all five
# corners of each (engine, device, geometry); a subset run has only some corners, so it writes an
# envelope with those entries left out, which can never equal the committed one. The envelope is
# pure min/max selection of the metrics.json floats, so those, which are compared, determine it.

PROVENANCE = "provenance.json"
ENVELOPE = "envelope.json"


def load_subset(path: Path) -> tuple[str, ...]:
    """Job relpaths ``<engine>/<corner>/<device>/<geometry_id>``, one per line, in file order.

    ``#`` starts a comment line; blank lines are ignored. Raises ValueError on a malformed or
    duplicate line or an empty subset.
    """
    jobs: list[str] = []
    for n, raw in enumerate(Path(path).read_text(encoding="utf-8").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("/")
        if len(parts) != 4 or any(p in ("", ".", "..") for p in parts):
            raise ValueError(
                f"{path}:{n}: expected <engine>/<corner>/<device>/<geometry_id>, got {line!r}"
            )
        if line in jobs:
            raise ValueError(f"{path}:{n}: duplicate job {line!r}")
        jobs.append(line)
    if not jobs:
        raise ValueError(f"{path}: no jobs listed")
    return tuple(jobs)


def verify_subset(
    tree: Path, against: Path, prefix: str, jobs: tuple[str, ...]
) -> list[tuple[str, str]]:
    """``(manifest path, reason)`` for every difference of ``tree`` from ``against``, sorted.

    ``tree`` is a reference tree holding only ``jobs`` (relpaths under it); its files are
    compared with the manifest entries ``prefix + relpath``. Reasons:

    - ``changed``: listed in the manifest with a different sha256;
    - ``not in manifest``: a file of a listed job that the manifest does not have;
    - ``not in subset``: a file outside the listed jobs (other than provenance.json);
    - ``missing``: a manifest entry of a listed job, or provenance.json, absent from ``tree``;
    - ``unknown job``: a listed job with no entry in the manifest at all.

    ``envelope.json`` at the tree root is excluded (see the comment above).
    """
    if not prefix.endswith("/"):
        raise ValueError(f"prefix must end with '/', got {prefix!r}")
    have = _scan(tree, Path(against))
    have.pop(ENVELOPE, None)
    want = {r[len(prefix) :]: d for r, d in _load(against).items() if r.startswith(prefix)}

    def listed(rel: str) -> bool:
        return rel == PROVENANCE or any(rel.startswith(j + "/") for j in jobs)

    bad: list[tuple[str, str]] = []
    for rel, digest in have.items():
        if not listed(rel):
            bad.append((rel, "not in subset"))
        elif rel not in want:
            bad.append((rel, "not in manifest"))
        elif want[rel] != digest:
            bad.append((rel, "changed"))
    bad += [(rel, "missing") for rel in want if listed(rel) and rel not in have]
    bad += [(j + "/", "unknown job") for j in jobs if not any(r.startswith(j + "/") for r in want)]
    return sorted(((prefix + r, why) for r, why in bad), key=lambda t: t[0].encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m gf180tcad.manifest")
    ap.add_argument("command", choices=["update", "verify", "verify-subset"])
    ap.add_argument("root", type=Path)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--against", type=Path, help="verify-subset: the committed MANIFEST.sha256")
    ap.add_argument("--prefix", default="spice/", help="verify-subset: manifest path of the tree")
    ap.add_argument("--subset", type=Path, help="verify-subset: file listing the jobs")
    args = ap.parse_args(argv)
    if args.command == "verify-subset":
        if args.against is None or args.subset is None:
            ap.error("verify-subset needs --against and --subset")
        jobs = load_subset(args.subset)
        bad = verify_subset(args.root, args.against, args.prefix, jobs)
        for path, why in bad:
            print(f"{why}: {path}")
        if bad:
            print(f"{len(bad)} difference(s) from {args.against}", file=sys.stderr)
            return 1
        n = len(_scan(args.root, args.against)) - (args.root / ENVELOPE).is_file()
        print(
            f"identical: {n} files of {len(jobs)} jobs in {args.root} match {args.against} "
            f"under {args.prefix} (sha256; {ENVELOPE} excluded)"
        )
        return 0
    m = args.manifest or args.root / "MANIFEST.sha256"
    if args.command == "update":
        update(args.root, m)
        return 0
    bad = verify(args.root, m)
    for r in bad:
        print(r)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
