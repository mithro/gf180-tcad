# SPDX-License-Identifier: Apache-2.0
"""The committed SPICE reference must match the generator that is checked in.

A change to a generator source file (``reference.GENERATOR_MODULES`` plus
``tools/sandbox-run``), to ``docker/IMAGE`` or to ``docker/base/versions.json`` changes
``provenance.json``. These tests fail fast in the cheap CI job instead of only in the
GitHub-hosted cross-check (or in ``make reproduce``).
"""

import hashlib
import json
from pathlib import Path

from gf180tcad import manifest, reference

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "results"
PROVENANCE = RESULTS / "spice" / "provenance.json"
REGENERATE = (
    "regenerate the reference and the manifest in this change: `make reproduce` fails until "
    "you run `uv run --locked python -m gf180tcad spice-reference --engine both "
    "--out results/spice` and then `make manifest` (see docs/reproduce/index.md)"
)


def test_committed_generator_sha256_is_current():
    committed = json.loads(PROVENANCE.read_bytes())["generator_sha256"]
    current = reference.generator_sha256()
    assert committed == current, (
        f"results/spice/provenance.json has generator_sha256 {committed}, but the generator "
        f"sources now hash to {current}; {REGENERATE}"
    )


def test_committed_provenance_is_current():
    committed = json.loads(PROVENANCE.read_bytes())
    current = reference.provenance()
    assert committed == current, (
        f"results/spice/provenance.json differs from what the generator would write "
        f"({sorted(k for k in current if committed.get(k) != current[k])}); {REGENERATE}"
    )


def test_manifest_entry_of_provenance_is_current():
    entries = manifest._load(RESULTS / "MANIFEST.sha256")
    digest = hashlib.sha256(PROVENANCE.read_bytes()).hexdigest()
    assert entries["spice/provenance.json"] == digest, (
        "results/MANIFEST.sha256 does not match results/spice/provenance.json; run `make manifest`"
    )
