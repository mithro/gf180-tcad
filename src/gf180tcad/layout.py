# SPDX-License-Identifier: Apache-2.0
"""Names in the SPICE reference tree (``results/spice``), defined once for every module.

``<engine>/<corner>/<device>/<geometry_id>/`` holds one job's CSVs and :data:`METRICS_NAME`;
the tree root holds :data:`ENVELOPE_NAME` and :data:`PROVENANCE_NAME` (see
``docs/reproduce/index.md``, "Layout of results/spice"). Plain constants with no imports, so
that :mod:`gf180tcad.manifest` can use them without loading the generator.
"""

ENGINES = ("ngspice", "xyce")  # SPICE engines of the reference, primary first
METRICS_NAME = "metrics.json"  # per job: the extracted metrics
ENVELOPE_NAME = "envelope.json"  # tree root: per-metric min/max over the corners
PROVENANCE_NAME = "provenance.json"  # tree root: versions, image and generator_sha256
