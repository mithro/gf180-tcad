# SPDX-License-Identifier: Apache-2.0
"""sha256 manifest of a results tree: lines ``<sha256>  <relpath>``, sorted by path."""

import argparse
import hashlib
import sys
from collections.abc import Iterable
from pathlib import Path

from gf180tcad.layout import ENVELOPE_NAME, PROVENANCE_NAME

# Regenerable 25-62 MB gmsh meshes are git-ignored (see docs/limitations/moscap2d.md); their
# sha256 is recorded as mesh_sha256 in each cv.meta.json instead.
_UNTRACKED_MESH_NAME = "mesh.msh"


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
        if p.is_dir() and p.name.startswith("."):
            # e.g. a .spice.staging-* or .spice.old-* left by an interrupted spice-reference
            raise ValueError(
                f"{rel}: dot-directory in a results tree (a leftover spice-reference staging "
                "or .old- directory?); remove it before updating or verifying the manifest"
            )
        if p.is_file() and p != skip and p.name != _UNTRACKED_MESH_NAME:
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
# Two kinds of subset (``kind``):
#
# - ``spice``: jobs ``<engine>/<corner>/<device>/<geometry_id>`` of the SPICE reference
#   (results/spice, manifest prefix ``spice/``), with one root ``provenance.json``. The tree's
#   root ``envelope.json`` is compared only when the subset is the whole reference (every job of
#   :func:`all_jobs`). It is the min/max over all five corners of each (engine, device,
#   geometry); a partial subset run lacks some corners, so it writes an envelope with those
#   entries left out, which can never equal the committed one, and it is excluded on both sides.
#   It is pure min/max selection of the metrics.json floats, which are compared.
# - ``tcad``: jobs ``<tree>/<device>/<params>`` of the TCAD MOS capacitor trees (results/tcad,
#   manifest prefix ``tcad/``), e.g. ``moscap1d/nfet_05v0/calibrated``. Each tree root has its
#   own ``provenance.json`` (gf180tcad.tcad.tree_provenance), required for every tree the jobs
#   name; there is no root provenance.json and no envelope.

ALL = "all"
KINDS = ("spice", "tcad")


def all_jobs() -> tuple[str, ...]:
    """Relpaths of every job of the full reference (engines x corners x devices x geometries)."""
    # imported here so that `manifest update` / `verify` do not load the generator
    from gf180tcad import reference
    from gf180tcad.devices import CORNERS, DEVICES

    plan = reference.plan_jobs(reference.ENGINES, CORNERS, tuple(DEVICES))
    return tuple(j.relpath.as_posix() for j in plan)


def tcad_axes() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """The TCAD job axes: trees (``moscap1d``, ``moscap2d``), devices and params
    (``start``, ``calibrated``), as the TCAD command line defines them."""
    # imported here so that `manifest update` / `verify` do not load the TCAD code
    from gf180tcad.tcad import RESULTS_IMAGE, process
    from gf180tcad.tcad.__main__ import PARAMS

    return tuple(sorted(RESULTS_IMAGE)), tuple(process.DEVICES), tuple(PARAMS)


def tcad_all_jobs() -> tuple[str, ...]:
    """Relpaths ``<tree>/<device>/<params>`` of every TCAD MOS capacitor job: every combination
    of :func:`tcad_axes`, in that order."""
    trees, devices, params = tcad_axes()
    return tuple(f"{t}/{d}/{p}" for t in trees for d in devices for p in params)


def full_jobs(kind: str) -> tuple[str, ...]:
    """Every job of ``kind``: :func:`all_jobs` (``spice``) or :func:`tcad_all_jobs` (``tcad``)."""
    if kind == "spice":
        return all_jobs()
    if kind == "tcad":
        return tcad_all_jobs()
    raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")


def _check_job(path: Path, n: int, line: str, kind: str) -> None:
    parts = line.split("/")
    if kind == "spice":
        if len(parts) != 4 or any(p in ("", ".", "..") for p in parts):
            raise ValueError(
                f"{path}:{n}: expected <engine>/<corner>/<device>/<geometry_id>, got {line!r}"
            )
        return
    trees, devices, params = tcad_axes()
    if (
        len(parts) != 3
        or parts[0] not in trees
        or parts[1] not in devices
        or parts[2] not in params
    ):
        raise ValueError(
            f"{path}:{n}: expected <tree>/<device>/<params> with <tree> in {trees}, <device> in "
            f"{devices} and <params> in {params}, got {line!r}"
        )


def load_subset(path: Path, kind: str = "spice") -> tuple[str, ...]:
    """Job relpaths of the ``kind`` subset file ``path``, one per line, in file order.

    ``spice`` jobs are ``<engine>/<corner>/<device>/<geometry_id>``; ``tcad`` jobs are
    ``<tree>/<device>/<params>`` (:func:`tcad_axes`). ``#`` starts a comment line; blank lines
    are ignored. A single job line ``all`` stands for :func:`full_jobs` of ``kind``. Raises
    ValueError on an unknown kind, a malformed or duplicate line, ``all`` together with other job
    lines, or an empty subset.
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    jobs: list[str] = []
    for n, raw in enumerate(Path(path).read_text(encoding="utf-8").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == ALL or ALL in jobs:
            if jobs:
                raise ValueError(f"{path}:{n}: {ALL!r} must be the only job line")
            jobs.append(line)
            continue
        _check_job(path, n, line, kind)
        if line in jobs:
            raise ValueError(f"{path}:{n}: duplicate job {line!r}")
        jobs.append(line)
    if not jobs:
        raise ValueError(f"{path}: no jobs listed")
    return full_jobs(kind) if jobs == [ALL] else tuple(jobs)


def tcad_trees(jobs: Iterable[str]) -> tuple[str, ...]:
    """The tree roots (``moscap1d``, ``moscap2d``) that the TCAD ``jobs`` name, sorted."""
    return tuple(sorted({j.split("/")[0] for j in jobs}))


def verify_subset(
    tree: Path,
    against: Path,
    prefix: str,
    jobs: tuple[str, ...],
    *,
    full: Iterable[str] | None = None,
    kind: str = "spice",
) -> list[tuple[str, str]]:
    """``(manifest path, reason)`` for every difference of ``tree`` from ``against``, sorted.

    ``tree`` is a results tree holding only ``jobs`` (relpaths under it); its files are
    compared with the manifest entries ``prefix + relpath``. Reasons:

    - ``changed``: listed in the manifest with a different sha256;
    - ``not in manifest``: a file of a listed job that the manifest does not have;
    - ``not in subset``: a file outside the listed jobs (other than the provenance files);
    - ``missing``: a manifest entry of a listed job absent from ``tree``; also the provenance
      files (always required) and, for a complete ``spice`` subset, envelope.json;
    - ``unknown job``: a listed job with no entry in the manifest at all.

    ``kind="spice"``: the provenance file is the root ``provenance.json``, and the root
    ``envelope.json`` is compared only if ``jobs`` is every job of ``full`` (default: the full
    reference, :func:`all_jobs`), and excluded otherwise (see the comment above).

    ``kind="tcad"``: the provenance files are ``<tree>/provenance.json`` of every tree named by
    ``jobs`` (:func:`tcad_trees`), in place of a root one; envelope.json is never special.
    ``full`` must be passed (:func:`tcad_all_jobs`), so that "complete" is never judged against
    the SPICE plan; ValueError otherwise.
    """
    if not prefix.endswith("/"):
        raise ValueError(f"prefix must end with '/', got {prefix!r}")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    if kind == "tcad":
        if full is None:
            raise ValueError("kind='tcad' needs full=tcad_all_jobs() passed explicitly")
        roots = {f"{t}/{PROVENANCE_NAME}" for t in tcad_trees(jobs)}
    else:
        complete = set(jobs) == set(all_jobs() if full is None else full)
        roots = {PROVENANCE_NAME, ENVELOPE_NAME} if complete else {PROVENANCE_NAME}
    have = _scan(tree, Path(against))
    if kind == "spice" and ENVELOPE_NAME not in roots:
        have.pop(ENVELOPE_NAME, None)
    want = {r[len(prefix) :]: d for r, d in _load(against).items() if r.startswith(prefix)}

    def listed(rel: str) -> bool:
        return rel in roots or any(rel.startswith(j + "/") for j in jobs)

    bad: list[tuple[str, str]] = []
    for rel, digest in have.items():
        if not listed(rel):
            bad.append((rel, "not in subset"))
        elif rel not in want:
            bad.append((rel, "not in manifest"))
        elif want[rel] != digest:
            bad.append((rel, "changed"))
    required = {rel for rel in want if listed(rel)} | roots
    bad += [(rel, "missing") for rel in sorted(required) if rel not in have]
    bad += [(j + "/", "unknown job") for j in jobs if not any(r.startswith(j + "/") for r in want)]
    return sorted(((prefix + r, why) for r, why in bad), key=lambda t: t[0].encode("utf-8"))


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m gf180tcad.manifest")
    ap.add_argument("command", choices=["update", "verify", "verify-subset"])
    ap.add_argument("root", type=Path)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--against", type=Path, help="verify-subset: the committed MANIFEST.sha256")
    ap.add_argument("--prefix", default="spice/", help="verify-subset: manifest path of the tree")
    ap.add_argument("--subset", type=Path, help="verify-subset: file listing the jobs")
    ap.add_argument(
        "--kind", choices=KINDS, default="spice",
        help="verify-subset: spice (<engine>/<corner>/<device>/<geometry_id> jobs, the "
        "default) or tcad (<tree>/<device>/<params> jobs, with --prefix tcad/)",
    )  # fmt: skip
    return ap


def _verify_subset_main(args: argparse.Namespace) -> int:
    jobs = load_subset(args.subset, kind=args.kind)
    full = full_jobs(args.kind)
    bad = verify_subset(args.root, args.against, args.prefix, jobs, full=full, kind=args.kind)
    for path, why in bad:
        print(f"{why}: {path}")
    if bad:
        print(f"{len(bad)} difference(s) from {args.against}", file=sys.stderr)
        return 1
    complete = set(jobs) == set(full)
    n = len(_scan(args.root, args.against))
    if args.kind == "tcad":
        trees = ", ".join(f"{t}/{PROVENANCE_NAME}" for t in tcad_trees(jobs))
        what = f"{'complete' if complete else 'partial'} subset; provenance {trees}"
    else:
        if not complete:
            n -= (args.root / ENVELOPE_NAME).is_file()
        envelope = "compared (complete subset)" if complete else "excluded (partial subset)"
        what = f"{ENVELOPE_NAME} {envelope}"
    print(
        f"identical: {n} files of {len(jobs)} jobs in {args.root} match {args.against} "
        f"under {args.prefix} (sha256; {what})"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = _parser()
    args = ap.parse_args(argv)
    if args.command == "verify-subset":
        if args.against is None or args.subset is None:
            ap.error("verify-subset needs --against and --subset")
        return _verify_subset_main(args)
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
