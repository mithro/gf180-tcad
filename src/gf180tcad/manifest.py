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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m gf180tcad.manifest")
    ap.add_argument("command", choices=["update", "verify"])
    ap.add_argument("root", type=Path)
    ap.add_argument("--manifest", type=Path, default=None)
    args = ap.parse_args(argv)
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
