# SPDX-License-Identifier: Apache-2.0
# Reproduce the published results. See docs/reproduce/index.md.

PYTHON ?= uv run --locked python
JOBS ?= 8

.PHONY: reproduce manifest

# Regenerate the SPICE reference (both engines, all corners) and check it against the manifest.
reproduce:
	$(PYTHON) -m gf180tcad spice-reference --engine both --jobs $(JOBS) --out results/spice
	$(PYTHON) -m gf180tcad.manifest verify results/

# Rewrite results/MANIFEST.sha256 from the files under results/.
manifest:
	$(PYTHON) -m gf180tcad.manifest update results/
