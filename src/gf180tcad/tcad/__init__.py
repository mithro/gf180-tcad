# SPDX-License-Identifier: Apache-2.0
"""TCAD side of gf180-tcad: process descriptions, and (later tasks) the MOS capacitors.

Nothing here is a SPICE generator module (:data:`gf180tcad.reference.GENERATOR_MODULES`), so
changes to this package never touch ``results/spice/provenance.json``.
"""

from gf180tcad.sandbox import REPO_ROOT

# TODO(Task 9b): add provenance(), which writes each TCAD tree root's provenance.json. It
# hashes TCAD_GENERATOR_MODULES, which Task 9b defines here together with its import-graph test.

# The file pinning the TCAD image by digest (``docker/TCAD_IMAGE``).
TCAD_IMAGE_FILE = REPO_ROOT / "docker" / "TCAD_IMAGE"

# The TCAD image reference that TCAD jobs run in, read from :data:`TCAD_IMAGE_FILE`.
TCAD_IMAGE: str = TCAD_IMAGE_FILE.read_text(encoding="utf-8").strip()
