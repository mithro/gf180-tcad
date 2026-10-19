# SPDX-License-Identifier: Apache-2.0
"""TCAD side of gf180-tcad: process descriptions, MOS capacitors and their provenance.

Nothing here is a SPICE generator module (:data:`gf180tcad.reference.GENERATOR_MODULES`), so
changes to this package never touch ``results/spice/provenance.json``.

**Provenance.** Each TCAD tree root (:repo:`results/tcad/moscap1d`, and later ``moscap2d``,
``meshconv``, ``calibration`` and ``validation`` under :repo:`results/tcad`) holds one
``provenance.json``, written from :func:`tree_provenance`. It holds the TCAD image reference
(:repo:`docker/TCAD_IMAGE`), the contents of :repo:`docker/tcad/versions.json`, the plugin
commit ``gplugins_commit`` and ``generator_sha256`` (:func:`generator_sha256`), and, for a tree
with calibrated results, per device the sha256 of its calibration file
``results/tcad/calibration/<device>.json`` (:mod:`gf180tcad.tcad.calibration`, written by
:repo:`Task 12 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-12-calibrate-against-spice-cggvg>`) and the ``param_sha256`` of the
values applied (:func:`gf180tcad.tcad.calibration.param_sha256`). It holds no date.

The plugin is the submodule `third_party/gplugins
<https://github.com/mithro/gplugins/tree/dddaa071321c5177c8471312c565ad86d4b245d7>`_, a checkout
of the gplugins fork. Its commit is read on the host with
``git -C third_party/gplugins rev-parse HEAD``
(inside the sandbox the repo is a read-only mount without git). It raises unless the
submodule's working tree is clean (``git status --porcelain`` is empty) and its commit equals
the gitlink recorded in ``HEAD`` (``git ls-tree HEAD third_party/gplugins``), so the hashed
plugin files are exactly the pinned commit's.

Only the plugin's ``gplugins/devsim/`` files are hashed into ``generator_sha256``. The rest of
the plugin that the TCAD imports (``gplugins/__init__.py``, ``gplugins.common``,
``gplugins.meshwell``) is covered by ``gplugins_commit`` together with the clean-tree check, not
by the file hashes.
"""

import hashlib
import json
import re
import subprocess
from pathlib import Path

from gf180tcad.sandbox import REPO_ROOT

# The file pinning the TCAD image by digest (``docker/TCAD_IMAGE``).
TCAD_IMAGE_FILE = REPO_ROOT / "docker" / "TCAD_IMAGE"

# The TCAD image reference that TCAD jobs run in, read from :data:`TCAD_IMAGE_FILE`.
TCAD_IMAGE: str = TCAD_IMAGE_FILE.read_text(encoding="utf-8").strip()

# Every gf180tcad module the TCAD entry points import (gf180tcad.tcad.__main__ and, from Task
# 12, gf180tcad.calibrate.__main__), shared modules included. tests/tcad/test_tcad_provenance.py
# ties the list to the import graph; a task that adds a TCAD module extends it in the same PR.
TCAD_GENERATOR_MODULES = (
    "gf180tcad",
    "gf180tcad.devices",
    "gf180tcad.io",
    "gf180tcad.layout",
    "gf180tcad.sandbox",
    "gf180tcad.tcad",
    "gf180tcad.tcad.__main__",
    "gf180tcad.tcad.analytic",
    "gf180tcad.tcad.calibration",
    "gf180tcad.tcad.mesh",
    "gf180tcad.tcad.moscap1d",
    "gf180tcad.tcad.process",
)

# Non-module files hashed with them: the sandbox (thread environment, limits, mounts).
TCAD_GENERATOR_EXTRA_FILES = ("tools/sandbox-run",)

# The plugin submodule; the git-tracked files under its gplugins/devsim/ are hashed.
GPLUGINS_SUBMODULE = "third_party/gplugins"
GPLUGINS_HASHED_DIR = "gplugins/devsim"

# The process files.
PROCESS_GLOB = "data/process/*.toml"

# The TCAD image's tool versions.
TCAD_VERSIONS = Path("docker") / "tcad" / "versions.json"

# Where the calibrated values live (Task 12): results/tcad/calibration/<device>.json.
CALIBRATION_DIR = Path("results") / "tcad" / "calibration"


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


def generator_files(repo_root: Path | None = None) -> list[str]:
    """Repo-relative POSIX paths hashed by :func:`generator_sha256`, sorted by UTF-8 bytes.

    The files of :data:`TCAD_GENERATOR_MODULES` and :data:`TCAD_GENERATOR_EXTRA_FILES`, the
    git-tracked files under ``third_party/gplugins/gplugins/devsim/`` and the process files
    ``data/process/*.toml``. A missing one raises FileNotFoundError.
    """
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    files = []
    for name in TCAD_GENERATOR_MODULES:
        rel = module_relpath(name, root)
        if not (root / rel).is_file():
            raise FileNotFoundError(f"TCAD generator module {name} not found: {root / rel}")
        files.append(rel.as_posix())
    for rel in TCAD_GENERATOR_EXTRA_FILES:
        if not (root / rel).is_file():
            raise FileNotFoundError(f"TCAD generator file not found: {root / rel}")
        files.append(rel)
    tracked = _git(["ls-files", "-z", "--", GPLUGINS_HASHED_DIR], root / GPLUGINS_SUBMODULE)
    plugin = [f"{GPLUGINS_SUBMODULE}/{f}" for f in tracked.split("\0") if f]
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


def generator_sha256(repo_root: Path | None = None) -> str:
    """sha256 over the lines ``<file sha256>  <relpath>\\n`` of the :func:`generator_files`.

    It depends on file contents and repo-relative paths only, so it is the same in every clone.
    """
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    lines = [f"{_sha256(root / r)}  {r}\n" for r in generator_files(root)]
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def calibration_file(device: str, repo_root: Path | None = None) -> Path:
    """``results/tcad/calibration/<device>.json``, the calibrated values (Task 12)."""
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    return root / CALIBRATION_DIR / f"{device}.json"


def provenance(calibrated: tuple[str, ...] = (), repo_root: Path | None = None) -> dict:
    """The ``provenance.json`` of a tree root in which the ``calibrated`` devices used calibration.

    Raises :class:`ProvenanceError` if the plugin submodule is not clean and pinned, and
    FileNotFoundError if a calibrated device has no calibration file.
    """
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    out = {
        "generator_sha256": generator_sha256(root),
        "gplugins_commit": gplugins_commit(root),
        "image": (root / "docker" / "TCAD_IMAGE").read_text(encoding="utf-8").strip(),
        "versions": json.loads((root / TCAD_VERSIONS).read_text(encoding="utf-8")),
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
    """The devices with a ``<device>/calibrated`` job directory under ``tree_root``, sorted."""
    tree_root = Path(tree_root)
    return tuple(sorted(p.parent.name for p in tree_root.glob("*/calibrated") if p.is_dir()))


def tree_provenance(tree_root: Path, repo_root: Path | None = None) -> dict:
    """:func:`provenance` of the tree root ``tree_root``, from its calibrated job directories."""
    return provenance(calibrated_devices(tree_root), repo_root)
