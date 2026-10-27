# SPDX-License-Identifier: Apache-2.0
"""TCAD side of gf180-tcad: process descriptions, MOS capacitors and their provenance.

Nothing here is a SPICE generator module (:data:`gf180tcad.reference.GENERATOR_MODULES`), so
changes to this package never touch ``results/spice/provenance.json``.

**Provenance.** Each TCAD tree root (:repo:`results/tcad/moscap1d`, :repo:`results/tcad/moscap2d`,
:repo:`results/tcad/meshconv`, and the ``calibration`` and ``validation`` trees of Task 12 under
:repo:`results/tcad`) holds one
``provenance.json``, written from :func:`tree_provenance`. It holds, under ``images``, for each
result kind in the tree (``moscap1d``, ``moscap2d``) the TCAD image that made it: its name
(:data:`IMAGES`), reference and ``versions.json`` contents. It also holds the plugin
commit ``gplugins_commit``, the entry point that wrote the tree, ``generator``
(:data:`TREE_GENERATORS`), and that entry point's ``generator_sha256`` (:func:`generator_sha256`),
and, for a tree
with calibrated results (:func:`calibrated_devices`: calibrated job directories, and every device
with a validation result at the tree root), per device the sha256 of its calibration file
``results/tcad/calibration/<device>.json`` (:mod:`gf180tcad.tcad.calibration`, written by
:repo:`Task 12 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-12-calibrate-against-spice-cggvg>`) and the ``param_sha256`` of the
values applied (:func:`gf180tcad.tcad.calibration.param_sha256`). It holds no date.

**Images.** :data:`RESULTS_IMAGE` names the image each result kind is generated with: the 1D
results on the dev-HEAD image (:repo:`docker/TCAD_DEV_IMAGE`), the 2D results on the stable
image (:repo:`docker/TCAD_IMAGE`) for now. ``python -m gf180tcad.tcad`` takes ``--image`` to
pick the other one, for testing and debugging.

The plugin is the submodule `third_party/gplugins
<https://github.com/mithro/gplugins/tree/1c071d0565ef4917b48ff907b9426e879ccca7fc>`_, a checkout
of the gplugins fork. Its commit is read on the host with
``git -C third_party/gplugins rev-parse HEAD``
(inside the sandbox the repo is a read-only mount without git). It raises unless the
submodule's working tree is clean (``git status --porcelain`` is empty) and its commit equals
the gitlink recorded in ``HEAD`` (``git ls-tree HEAD third_party/gplugins``), so the hashed
plugin files are exactly the pinned commit's.

**One hash per entry point** (issue #34). ``generator_sha256`` covers the import closure of the
entry point that writes the tree (:data:`TCAD_GENERATORS`), not of both: a change to a module that
a tree's writer never imports (the calibration code, for the MOS capacitor and mesh-convergence
trees) leaves that tree's hash alone. The non-module inputs (:data:`TCAD_GENERATOR_EXTRA_FILES`,
the plugin's files and the process files) are the same for both entry points.

**The registry** (Charon plan Task B0). The entry points' module lists, the tree that each one
writes, the images and the calibration directories are data, in
:repo:`src/gf180tcad/generators.json` (:data:`REGISTRY_FILE`), read once at import into the dicts below. The file is not hashed: it
decides what is hashed, and a change to it either adds or removes a hashed file (visible in the
hash) or renames a tree (visible in the manifest). Adding an entry point, a tree or an image for
another backend is then a data row, and changes no committed tree's ``generator_sha256``.

Only the plugin's ``gplugins/devsim/`` files are hashed into ``generator_sha256``, less those an
entry point's ``plugin_excludes`` in the registry leave out (:data:`PLUGIN_EXCLUDES`: the Charon
backend's ``gplugins/devsim/backends/charon/`` for both DEVSIM entry points). The rest of
the plugin that the TCAD imports (``gplugins/__init__.py``, ``gplugins.common``,
``gplugins.meshwell``) is covered by ``gplugins_commit`` together with the clean-tree check, not
by the file hashes.
"""

import fnmatch
import hashlib
import json
import re
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

from gf180tcad.layout import PROVENANCE_NAME
from gf180tcad.sandbox import REPO_ROOT

# The file pinning the TCAD image by digest (``docker/TCAD_IMAGE``).
TCAD_IMAGE_FILE = REPO_ROOT / "docker" / "TCAD_IMAGE"

# The stable TCAD image reference (PyPI releases), read from :data:`TCAD_IMAGE_FILE`.
TCAD_IMAGE: str = TCAD_IMAGE_FILE.read_text(encoding="utf-8").strip()

# The file pinning the dev-HEAD TCAD image by digest (``docker/TCAD_DEV_IMAGE``).
TCAD_DEV_IMAGE_FILE = REPO_ROOT / "docker" / "TCAD_DEV_IMAGE"

# The dev-HEAD TCAD image reference, read from :data:`TCAD_DEV_IMAGE_FILE`.
TCAD_DEV_IMAGE: str = TCAD_DEV_IMAGE_FILE.read_text(encoding="utf-8").strip()

# The generator registry (Charon plan Task B0): data, read here, never hashed.
REGISTRY_FILE = Path(__file__).resolve().parents[1] / "generators.json"
_REGISTRY: dict = json.loads(REGISTRY_FILE.read_bytes())

# The TCAD images by name: the repo-relative pin file and versions.json of each (the registry's
# ``images``).
IMAGES: dict[str, tuple[Path, Path]] = {
    name: (Path(v["pin"]), Path(v["versions"])) for name, v in _REGISTRY["images"].items()
}

# The image each result kind is generated with by default. The final results come from upstream
# dev HEAD; the stable image is for testing how things used to work, and for debugging. 1D: the
# dev image (its 1D results are byte-identical to the stable image's: tests/tcad/test_moscap1d.py
# test_stable_and_dev_images_agree). 2D stays on the stable image, explicitly, for now: gmsh 5
# meshes the 2D cells differently, so 2D needs its own mesh convergence on the dev image first,
# planned before the Phase 2 exit (docs/reproduce/image.md, "Which image makes which results").
RESULTS_IMAGE = {"moscap1d": "dev", "moscap2d": "stable"}

# The two TCAD entry points: the MOS capacitor and mesh-convergence jobs, and the calibration.
TCAD_MAIN = "gf180tcad.tcad.__main__"
CALIBRATE_MAIN = "gf180tcad.calibrate.__main__"

# Per entry point, every gf180tcad module it imports (its import closure, shared modules
# included), sorted: the registry's ``entry_points``. The closure is the static one: every import
# statement counts, also one inside a function (calibrate.cv and meshconv import moscap2d and
# stack that way), so it is a superset of what one run loads. tests/tcad/test_tcad_provenance.py
# ties each list to that entry point's import graph; a task that adds a TCAD module extends the
# lists that import it in the same PR.
TCAD_GENERATORS: dict[str, tuple[str, ...]] = {
    entry: tuple(modules) for entry, modules in _REGISTRY["entry_points"].items()
}

# The entry point that writes each committed tree root, keyed by the root's path relative to
# results/ (``tcad/moscap1d``; the registry's ``trees``), and whose hash its provenance.json
# records. tools/restamp-tcad-provenance picks the generator from it.
TREE_GENERATORS: dict[str, str] = dict(_REGISTRY["trees"])

# Per entry point, the plugin files (fnmatch patterns relative to the submodule, ``*`` matching
# across ``/``) left out of its hash (the registry's ``plugin_excludes``).
PLUGIN_EXCLUDES: dict[str, tuple[str, ...]] = {
    entry: tuple(patterns) for entry, patterns in _REGISTRY["plugin_excludes"].items()
}

# Where each backend's calibrated values live (the registry's ``calibration_dirs``).
CALIBRATION_DIRS: dict[str, Path] = {
    backend: Path(d) for backend, d in _REGISTRY["calibration_dirs"].items()
}

if {TCAD_MAIN, CALIBRATE_MAIN} - set(TCAD_GENERATORS):
    raise KeyError(f"{REGISTRY_FILE} lacks the entry points {TCAD_MAIN} and {CALIBRATE_MAIN}")

# Non-module files hashed with them: the sandbox (thread environment, limits, mounts).
TCAD_GENERATOR_EXTRA_FILES = ("tools/sandbox-run",)

# The plugin submodule; the git-tracked files under its gplugins/devsim/ are hashed.
GPLUGINS_SUBMODULE = "third_party/gplugins"
GPLUGINS_HASHED_DIR = "gplugins/devsim"

# The process files.
PROCESS_GLOB = "data/process/*.toml"

# Where the calibrated DEVSIM values live (Task 12): results/tcad/calibration/<device>.json.
CALIBRATION_DIR = CALIBRATION_DIRS["devsim"]

# Where the validation of the calibrated values lives (Task 12): results/tcad/validation/<device>.json.
VALIDATION_DIR = Path("results") / "tcad" / "validation"


class ProvenanceError(RuntimeError):
    """The plugin submodule is not the clean, pinned commit, so no provenance is written."""


def _git(args: list[str], cwd: Path) -> str:
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise ProvenanceError(f"git {' '.join(args)} failed in {cwd}: {res.stderr.strip()}")
    return res.stdout


def gplugins_commit(repo_root: Path | None = None) -> str:
    """The plugin submodule's commit; raises :class:`ProvenanceError` unless clean and pinned."""
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    sub = root / GPLUGINS_SUBMODULE
    head = _git(["rev-parse", "HEAD"], sub).strip()
    dirty = _git(["status", "--porcelain"], sub)
    if dirty:
        raise ProvenanceError(f"{GPLUGINS_SUBMODULE} has local changes:\n{dirty}")
    tree = _git(["ls-tree", "HEAD", GPLUGINS_SUBMODULE], root)
    m = re.fullmatch(rf"160000 commit ([0-9a-f]{{40}})\t{re.escape(GPLUGINS_SUBMODULE)}\n", tree)
    if not m:
        raise ProvenanceError(f"{GPLUGINS_SUBMODULE} is not a gitlink in HEAD: {tree!r}")
    if m.group(1) != head:
        raise ProvenanceError(
            f"{GPLUGINS_SUBMODULE} is checked out at {head}, but HEAD pins {m.group(1)}; run "
            "`git submodule update --init`"
        )
    return head


def module_relpath(name: str, repo_root: Path | None = None) -> Path:
    """Repo-relative source file of module ``name`` (``__init__.py`` for a package)."""
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    base = Path("src", *name.split("."))
    init = base / "__init__.py"
    return init if (root / init).is_file() else base.with_suffix(".py")


def generator_files(generator: str, repo_root: Path | None = None) -> list[str]:
    """Repo-relative POSIX paths hashed by :func:`generator_sha256` for the entry point
    ``generator``, sorted by UTF-8 bytes.

    The files of its modules (:data:`TCAD_GENERATORS`, KeyError for another entry point), of
    :data:`TCAD_GENERATOR_EXTRA_FILES`, the git-tracked files under
    ``third_party/gplugins/gplugins/devsim/`` less the entry point's :data:`PLUGIN_EXCLUDES`, and
    the process files ``data/process/*.toml``. A missing one raises FileNotFoundError.
    """
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    files = []
    for name in TCAD_GENERATORS[generator]:
        rel = module_relpath(name, root)
        if not (root / rel).is_file():
            raise FileNotFoundError(f"TCAD generator module {name} not found: {root / rel}")
        files.append(rel.as_posix())
    for rel in TCAD_GENERATOR_EXTRA_FILES:
        if not (root / rel).is_file():
            raise FileNotFoundError(f"TCAD generator file not found: {root / rel}")
        files.append(rel)
    tracked = _git(["ls-files", "-z", "--", GPLUGINS_HASHED_DIR], root / GPLUGINS_SUBMODULE)
    excludes = PLUGIN_EXCLUDES.get(generator, ())
    plugin = [
        f"{GPLUGINS_SUBMODULE}/{f}"
        for f in tracked.split("\0")
        if f and not any(fnmatch.fnmatchcase(f, pat) for pat in excludes)
    ]
    if not plugin:
        raise FileNotFoundError(f"no tracked files in {GPLUGINS_SUBMODULE}/{GPLUGINS_HASHED_DIR}")
    files += plugin
    process = [p.relative_to(root).as_posix() for p in root.glob(PROCESS_GLOB)]
    if not process:
        raise FileNotFoundError(f"no process files {PROCESS_GLOB} in {root}")
    files += process
    return sorted(files, key=lambda s: s.encode())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generator_sha256(generator: str, repo_root: Path | None = None) -> str:
    """sha256 over the lines ``<file sha256>  <relpath>\\n`` of the :func:`generator_files` of
    the entry point ``generator`` (:data:`TCAD_GENERATORS`).

    It depends on file contents and repo-relative paths only, so it is the same in every clone.
    """
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    lines = [f"{_sha256(root / r)}  {r}\n" for r in generator_files(generator, root)]
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def calibration_file(
    device: str, repo_root: Path | None = None, *, backend: str = "devsim"
) -> Path:
    """``<calibration dir>/<device>.json``, the calibrated values of ``backend`` (Task 12;
    :data:`CALIBRATION_DIRS`, KeyError for another backend): for DEVSIM
    ``results/tcad/calibration/<device>.json``."""
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    return root / CALIBRATION_DIRS[backend] / f"{device}.json"


def image_ref(name: str, repo_root: Path | None = None) -> str:
    """The pinned reference of the TCAD image ``name`` (:data:`IMAGES`); KeyError if unknown."""
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    return (root / IMAGES[name][0]).read_text(encoding="utf-8").strip()


def image_versions(name: str, repo_root: Path | None = None) -> dict:
    """The ``versions.json`` of the TCAD image ``name`` (:data:`IMAGES`)."""
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    return json.loads((root / IMAGES[name][1]).read_text(encoding="utf-8"))


def provenance(
    calibrated: tuple[str, ...] = (),
    repo_root: Path | None = None,
    *,
    images: Mapping[str, str],
    generator: str,
) -> dict:
    """The ``provenance.json`` of a tree root in which the ``calibrated`` devices used calibration.

    ``images`` maps each result kind of the tree (``moscap1d``, ``moscap2d``) to the name of the
    image that made it; ``generator`` is the entry point writing the tree (:data:`TCAD_MAIN` or
    :data:`CALIBRATE_MAIN`, KeyError for another). Raises :class:`ProvenanceError` if the plugin
    submodule is not clean and pinned, and FileNotFoundError if a calibrated device has no
    calibration file.
    """
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    out = {
        "generator": generator,
        "generator_sha256": generator_sha256(generator, root),
        "gplugins_commit": gplugins_commit(root),
        "images": {
            kind: {
                "name": name,
                "ref": image_ref(name, root),
                "versions": image_versions(name, root),
            }
            for kind, name in sorted(images.items())
        },
    }
    if calibrated:
        from gf180tcad.tcad import calibration

        out["calibration"] = {
            d: {
                "file_sha256": calibration.sha256_file(calibration_file(d, root)),
                "param_sha256": calibration.param_sha256(
                    calibration.read(calibration_file(d, root), d)
                ),
            }
            for d in sorted(set(calibrated))
        }
    return out


def calibrated_devices(tree_root: Path) -> tuple[str, ...]:
    """The devices whose results under ``tree_root`` used calibrated values, sorted: those with a
    ``<device>/calibrated`` job directory, and those with a validation result ``<device>.json``
    at the tree root (as in :data:`VALIDATION_DIR`), recognised by its content: it records the
    ``calibration_file_sha256`` of the calibration it applied. The decision never depends on the
    tree's directory name, so a validation written to any ``--out`` gets the same provenance."""
    from gf180tcad.tcad.process import DEVICES

    tree_root = Path(tree_root)
    found = {p.parent.name for p in tree_root.glob("*/calibrated") if p.is_dir()}
    for p in tree_root.glob("*.json"):
        if p.stem in DEVICES:
            data = json.loads(p.read_bytes())
            if isinstance(data, dict) and "calibration_file_sha256" in data:
                found.add(p.stem)
    return tuple(sorted(found))


def tree_provenance(
    tree_root: Path,
    images: Mapping[str, str],
    repo_root: Path | None = None,
    *,
    generator: str,
) -> dict:
    """:func:`provenance` of the tree root ``tree_root``, from its calibrated job directories,
    with ``images`` (result kind to image name), written by the entry point ``generator``."""
    return provenance(calibrated_devices(tree_root), repo_root, images=images, generator=generator)


def recorded_images(tree_root: Path) -> dict[str, str]:
    """The image names ``tree_root/provenance.json`` records for the result kinds that are
    subtrees of ``tree_root`` (``moscap1d/``, ``moscap2d/``: the mesh-convergence tree); empty
    if there is no such file or entry."""
    path = Path(tree_root) / PROVENANCE_NAME
    if not path.is_file():
        return {}
    recorded = json.loads(path.read_bytes()).get("images", {})
    return {k: v["name"] for k, v in recorded.items() if (Path(tree_root) / k).is_dir()}


def check_same_image(tree_root: Path, kind: str, image: str, others: Iterable[Path]) -> None:
    """Refuse a run on ``image`` that would leave one result kind made by two images.

    ``tree_root/provenance.json`` records one image for each result kind ``kind``. If it records
    another image than ``image`` and any of the ``others`` (the kind's other job directories,
    which the run leaves as they are) exists, the tree's provenance would claim one image for
    files from two. Delete the other job directories first (the whole kind is then regenerated, one
    job directory at a time, with ``--image``), or use the recorded image.

    Raises:
        ValueError: naming the recorded image, the requested image and the directories kept.
    """
    path = Path(tree_root) / PROVENANCE_NAME
    if not path.is_file():
        return
    recorded = json.loads(path.read_bytes()).get("images", {}).get(kind, {}).get("name")
    kept = sorted(p.as_posix() for p in others if Path(p).exists())
    if recorded is not None and recorded != image and kept:
        raise ValueError(
            f"{path} records {kind} results made on the {recorded!r} image, but this run uses "
            f"{image!r}, and would keep {', '.join(kept)} from the {recorded!r} image. Delete those "
            f"directories to regenerate the whole {kind} kind with --image {image}, or use "
            f"--image {recorded}."
        )
