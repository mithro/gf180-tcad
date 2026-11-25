# SPDX-License-Identifier: Apache-2.0
"""The Charon jobs of gf180-tcad: the MOS capacitor on the second TCAD backend.

The simulator is the Charon backend of the plugin fork, ``gplugins.devsim.backends.charon``,
run inside the pinned Charon image (:repo:`docker/CHARON_IMAGE`); the method and every setting
come from experiments B1 to B7 (:repo:`docs/limitations/charon.md`). Results go to their own tree,
:data:`TREE_ROOT`, with the DEVSIM result layout plus ``"backend": "charon"`` in every meta file
(:repo:`Charon plan, Task B <docs/superpowers/plans/2026-10-27-phase4-charon-backend.md>`).

This package is the entry point :data:`CHARON_MAIN` of the generator registry
(:repo:`src/gf180tcad/generators.json`). No DEVSIM entry point imports it, so a change here never
changes a DEVSIM tree's hash (``tests/tcad/test_tcad_provenance.py``).
"""

from __future__ import annotations

from pathlib import Path

from gf180tcad.sandbox import REPO_ROOT

#: The pin file of the Charon image.
CHARON_IMAGE_FILE = Path("docker") / "CHARON_IMAGE"

#: The image name of :data:`gf180tcad.tcad.IMAGES` that Charon jobs run in.
CHARON_IMAGE_NAME = "charon"

#: The root of the Charon result trees (``moscap1d`` and later ones), relative to the repo.
TREE_ROOT = Path("results") / "tcad-charon"

#: The entry point that writes :data:`TREE_ROOT`.
CHARON_MAIN = "gf180tcad.charon.__main__"

#: The backend name written into every Charon meta file.
BACKEND = "charon"


def charon_image(repo_root: Path | None = None) -> str:
    """The pinned Charon image reference (:data:`CHARON_IMAGE_FILE`)."""
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    return (root / CHARON_IMAGE_FILE).read_text(encoding="utf-8").strip()
