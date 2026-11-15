# SPDX-License-Identifier: Apache-2.0
"""Digests of the result trees a TCAD tree is made from (issue #188).

A tree that reads other committed result trees (the calibration reads the SPICE reference, say)
records in its ``provenance.json``, per input tree, :func:`prefix_digest`: the sha256 of the
manifest lines (:mod:`gf180tcad.manifest`, ``<sha256>  <relpath>``) of that tree's files. A
regenerated input then shows as a digest that no longer matches :repo:`results/MANIFEST.sha256`.

Its own module, importing nothing of the package but :mod:`gf180tcad.layout`, because every
module a TCAD entry point imports is hashed into its ``generator_sha256``
(:func:`gf180tcad.tcad.generator_files`): importing :mod:`gf180tcad.manifest` would add the SPICE
reference code to every TCAD hash.
"""

import hashlib
from collections.abc import Mapping
from pathlib import Path

from gf180tcad.layout import PROVENANCE_NAME

# Regenerable 25-62 MB gmsh meshes are git-ignored and left out of the manifest (see
# docs/limitations/moscap2d.md); their sha256 is recorded as mesh_sha256 in each cv.meta.json.
UNTRACKED_MESH_NAME = "mesh.msh"


def _sorted(paths) -> list[str]:
    return sorted(paths, key=lambda s: s.encode("utf-8"))


def prefix_digest(entries: Mapping[str, str], prefix: str) -> dict:
    """The digest of the manifest ``entries`` (relpath to sha256) under ``prefix/``, less every
    ``provenance.json``: ``{"files": n, "sha256": h}``, ``h`` the sha256 of their manifest lines
    ``<sha256>  <relpath>\\n`` in manifest order.

    The provenance files are left out, so restamping an input tree (a code-only change, no data
    changed) does not move the digest. ValueError if no file is under ``prefix``."""
    rels = _sorted(
        r for r in entries if r.startswith(f"{prefix}/") and r.rpartition("/")[2] != PROVENANCE_NAME
    )
    if not rels:
        raise ValueError(f"no file under {prefix}/")
    lines = "".join(f"{entries[r]}  {r}\n" for r in rels)
    return {"files": len(rels), "sha256": hashlib.sha256(lines.encode("utf-8")).hexdigest()}


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_digest(results_root: Path, prefix: str) -> dict:
    """:func:`prefix_digest` of the files on disk under ``results_root/prefix``: every file the
    manifest of ``results_root`` lists there (no :data:`UNTRACKED_MESH_NAME`). ValueError for a
    symlink, NotADirectoryError for a missing tree."""
    root = Path(results_root) / prefix
    if not root.is_dir():
        raise NotADirectoryError(f"input tree is not an existing directory: {root}")
    entries = {}
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise ValueError(f"{p}: symlinks are not allowed in a results tree")
        if p.is_file() and p.name != UNTRACKED_MESH_NAME:
            entries[f"{prefix}/{p.relative_to(root).as_posix()}"] = _sha256(p)
    return prefix_digest(entries, prefix)
