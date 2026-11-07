# SPDX-License-Identifier: Apache-2.0
# Reproduce the published results. See docs/reproduce/index.md.

PYTHON ?= uv run --locked python
# SPICE jobs at once, each admitted at 4 GiB (8 -> 32 GiB): pass JOBS=4 on a host with less than
# 32 GiB of memory.
JOBS ?= 8
TCAD = $(PYTHON) -m gf180tcad.tcad
CALIBRATE = $(PYTHON) -m gf180tcad.calibrate
CORNERS = $(PYTHON) -m gf180tcad.calibrate.corners
# Scratch directories of the split 2D jobs (--method qs, then combine-qs on the same directory);
# a cut-off job resumes from here when the target runs again.
TCAD_SCRATCH ?= tmp/reproduce-scratch
# The temporary tree root of reproduce-quick (never results/: tools/crosscheck-tcad-run refuses).
QUICK_OUT ?= tmp/reproduce-quick
TCAD_SUBSET = tests/crosscheck_tcad_subset.txt
# A checkout of the output cache repository (docs/reproduce/output-cache.md) for cache-push:
# git clone --depth 1 git@github.com:mithro/gf180-tcad-output-cache.git tmp/output-cache
OUTPUT_CACHE ?= tmp/output-cache

.PHONY: reproduce reproduce-quick manifest spice-reference \
	tcad-meshconv tcad-start tcad-calibrate tcad-calibrated tcad-validate tcad-meshes \
	tcad-corners \
	cache-status cache-push lint pre-push pre-push-docs readme-figures

# Everything, in dependency order: the SPICE reference, then the TCAD trees (mesh convergence,
# start values, calibration, calibrated values, validation, the reduced mesh artefacts of the
# calibrated 2D cells, corner fits), then the manifest check. Hours: the 2D jobs (16 GiB each)
# run one at a time, the 1D corner fits (2 GiB each) four at a time.
reproduce:
	$(MAKE) spice-reference
	$(MAKE) tcad-meshconv
	$(MAKE) tcad-start
	$(MAKE) tcad-calibrate
	$(MAKE) tcad-calibrated
	$(MAKE) tcad-validate
	$(MAKE) tcad-meshes
	$(MAKE) -j4 tcad-corners
	$(PYTHON) -m gf180tcad.manifest verify results/

# The SPICE reference (both engines, all corners) into results/spice.
spice-reference:
	$(PYTHON) -m gf180tcad spice-reference --engine both --jobs $(JOBS) --out results/spice

# 1. Mesh convergence: 1D (2 GiB per level job), then 2D one 16 GiB level job at a time.
tcad-meshconv:
	$(TCAD) meshconv --device nfet_05v0 --dim 1 --out results/tcad/meshconv
	$(TCAD) meshconv --device pfet_05v0 --dim 1 --out results/tcad/meshconv
	$(TCAD) meshconv --device nfet_05v0 --dim 2 --jobs 1 --out results/tcad/meshconv
	$(TCAD) meshconv --device pfet_05v0 --dim 2 --jobs 1 --out results/tcad/meshconv

# 2. The process files' start values: 1D, and the committed 2D cells. The L = 2 um cells have no
# AC sweep (gf180tcad.tcad.moscap2d.AC_INFEASIBLE): QS alone, then the job files from it.
tcad-start:
	$(TCAD) moscap --device nfet_05v0 --dim 1 --params start --out results/tcad/moscap1d
	$(TCAD) moscap --device pfet_05v0 --dim 1 --params start --out results/tcad/moscap1d
	$(TCAD) moscap --device nfet_05v0 --dim 2 --params start --geometry w10p0_l0p60 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device nfet_05v0 --dim 2 --params start --geometry w10p0_l2p00 \
		--method qs --resume $(TCAD_SCRATCH)/moscap2d-nfet_05v0-start-w10p0_l2p00 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device nfet_05v0 --dim 2 --params start --geometry w10p0_l2p00 \
		--method combine-qs --resume $(TCAD_SCRATCH)/moscap2d-nfet_05v0-start-w10p0_l2p00 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device pfet_05v0 --dim 2 --params start --geometry w10p0_l0p50 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device pfet_05v0 --dim 2 --params start --geometry w10p0_l2p00 \
		--method qs --resume $(TCAD_SCRATCH)/moscap2d-pfet_05v0-start-w10p0_l2p00 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device pfet_05v0 --dim 2 --params start --geometry w10p0_l2p00 \
		--method combine-qs --resume $(TCAD_SCRATCH)/moscap2d-pfet_05v0-start-w10p0_l2p00 \
		--out results/tcad/moscap2d

# 3. The calibration against the TT ngspice Cgg-Vg (one 2 GiB job per device).
tcad-calibrate:
	$(CALIBRATE) run --device nfet_05v0 --out results/tcad/calibration
	$(CALIBRATE) run --device pfet_05v0 --out results/tcad/calibration

# 4. The calibrated values: 1D, and the committed calibrated 2D cells (issue #35; one 16 GiB
# job at a time, hours each; L = 10 um does not solve in 2D, docs/limitations/moscap2d.md).
tcad-calibrated:
	$(TCAD) moscap --device nfet_05v0 --dim 1 --params calibrated --out results/tcad/moscap1d
	$(TCAD) moscap --device pfet_05v0 --dim 1 --params calibrated --out results/tcad/moscap1d
	$(TCAD) moscap --device nfet_05v0 --dim 2 --params calibrated --geometry w10p0_l0p60 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device nfet_05v0 --dim 2 --params calibrated --geometry w10p0_l0p70 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device nfet_05v0 --dim 2 --params calibrated --geometry w10p0_l1p00 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device nfet_05v0 --dim 2 --params calibrated --geometry w10p0_l2p00 \
		--method qs --resume $(TCAD_SCRATCH)/moscap2d-nfet_05v0-calibrated-w10p0_l2p00 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device nfet_05v0 --dim 2 --params calibrated --geometry w10p0_l2p00 \
		--method combine-qs --resume $(TCAD_SCRATCH)/moscap2d-nfet_05v0-calibrated-w10p0_l2p00 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device nfet_05v0 --dim 2 --params calibrated --geometry w1p6_l0p70 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device pfet_05v0 --dim 2 --params calibrated --geometry w10p0_l0p50 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device pfet_05v0 --dim 2 --params calibrated --geometry w10p0_l0p70 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device pfet_05v0 --dim 2 --params calibrated --geometry w10p0_l1p00 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device pfet_05v0 --dim 2 --params calibrated --geometry w10p0_l2p00 \
		--method qs --resume $(TCAD_SCRATCH)/moscap2d-pfet_05v0-calibrated-w10p0_l2p00 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device pfet_05v0 --dim 2 --params calibrated --geometry w10p0_l2p00 \
		--method combine-qs --resume $(TCAD_SCRATCH)/moscap2d-pfet_05v0-calibrated-w10p0_l2p00 \
		--out results/tcad/moscap2d
	$(TCAD) moscap --device pfet_05v0 --dim 2 --params calibrated --geometry w1p6_l0p70 \
		--out results/tcad/moscap2d

# 5. The validation of the committed calibration (refuses unless it is committed and unchanged).
tcad-validate:
	$(CALIBRATE) validate --device nfet_05v0 --out results/tcad/validation
	$(CALIBRATE) validate --device pfet_05v0 --out results/tcad/validation

# 6. The reduced mesh artefact of each calibrated 2D cell (renders plan, Task R0): the full mesh
# pulled from the output cache by its mesh_sha256, cut in a 4 GiB sandbox, under a minute each.
tcad-meshes:
	$(PYTHON) -m gf180tcad.meshcut cut --job results/tcad/moscap2d/nfet_05v0/calibrated/w10p0_l0p60 \
		--out results/tcad/meshes/stable
	$(PYTHON) -m gf180tcad.meshcut cut --job results/tcad/moscap2d/nfet_05v0/calibrated/w10p0_l0p70 \
		--out results/tcad/meshes/stable
	$(PYTHON) -m gf180tcad.meshcut cut --job results/tcad/moscap2d/nfet_05v0/calibrated/w10p0_l1p00 \
		--out results/tcad/meshes/stable
	$(PYTHON) -m gf180tcad.meshcut cut --job results/tcad/moscap2d/nfet_05v0/calibrated/w10p0_l2p00 \
		--out results/tcad/meshes/stable
	$(PYTHON) -m gf180tcad.meshcut cut --job results/tcad/moscap2d/nfet_05v0/calibrated/w1p6_l0p70 \
		--out results/tcad/meshes/stable
	$(PYTHON) -m gf180tcad.meshcut cut --job results/tcad/moscap2d/pfet_05v0/calibrated/w10p0_l0p50 \
		--out results/tcad/meshes/stable
	$(PYTHON) -m gf180tcad.meshcut cut --job results/tcad/moscap2d/pfet_05v0/calibrated/w10p0_l0p70 \
		--out results/tcad/meshes/stable
	$(PYTHON) -m gf180tcad.meshcut cut --job results/tcad/moscap2d/pfet_05v0/calibrated/w10p0_l1p00 \
		--out results/tcad/meshes/stable
	$(PYTHON) -m gf180tcad.meshcut cut --job results/tcad/moscap2d/pfet_05v0/calibrated/w10p0_l2p00 \
		--out results/tcad/meshes/stable
	$(PYTHON) -m gf180tcad.meshcut cut --job results/tcad/moscap2d/pfet_05v0/calibrated/w1p6_l0p70 \
		--out results/tcad/meshes/stable

# 7. The corner fits (Task 16a): one 2 GiB job per device and corner, then the summary of each
# device. `make -j4 tcad-corners` runs four fits at once.
CORNER_FITS = $(foreach d,nfet_05v0 pfet_05v0,$(foreach c,ff ss fs sf,corner-fit-$(d)-$(c)))
tcad-corners: $(CORNER_FITS)
	$(CORNERS) summary --device nfet_05v0 --out results/tcad/corners
	$(CORNERS) summary --device pfet_05v0 --out results/tcad/corners

corner-fit-%:
	$(CORNERS) run --device $(word 1,$(subst -, ,$*)) --corner $(word 2,$(subst -, ,$*)) \
		--out results/tcad/corners

# The cross-checked TCAD subset only (as the crosscheck-tcad workflow job): its jobs into
# $(QUICK_OUT), then compared byte for byte with results/MANIFEST.sha256. Minutes.
reproduce-quick:
	$(PYTHON) tools/crosscheck-tcad-run $(TCAD_SUBSET) --clean --out $(QUICK_OUT)
	$(PYTHON) -m gf180tcad.manifest verify-subset $(QUICK_OUT) --kind tcad \
		--against results/MANIFEST.sha256 --prefix tcad/ --subset $(TCAD_SUBSET)

# Rewrite results/MANIFEST.sha256 from the files under results/.
manifest:
	$(PYTHON) -m gf180tcad.manifest update results/

# The output cache: which files the committed metas name (mesh.msh by mesh_sha256) are in it.
cache-status:
	$(PYTHON) tools/output-cache status --results results

# Add the cacheable files under results/ to $(OUTPUT_CACHE), commit there and push it (needs
# write access to the cache repository; run tools/output-cache push --dry-run first).
cache-push:
	$(PYTHON) tools/output-cache push --cache $(OUTPUT_CACHE) --results results --publish

# The README's committed figures (docs/images/readme/), drawn from the committed results by
# gf180tcad.docgen; tests/test_docgen.py fails when they are stale. Seconds.
readme-figures:
	$(PYTHON) -m gf180tcad.docgen readme-figures

# The lint steps of the CI lint-test job, exactly (.github/workflows/ci.yml runs this target).
# Seconds.
lint:
	uv run --locked ruff check
	uv run --locked ruff format --check

# What the pre-push hook (tools/git-hooks/pre-push, installed by tools/install-hooks) runs before
# every push: make lint, then the CI tests except the docs build, the generated pages and the
# calibration fits (PRE_PUSH_SLOW; pre-push-docs runs the first two, CI all three, so no file runs
# twice in one push; tests/test_makefile.py checks both lists). -rs lists the skips. The tests'
# scratch files go to PRE_PUSH_TMP, not the system temporary directory; it must be outside the
# repository (the sandbox and scratch-directory checks refuse workdirs inside it, so not tmp/), and
# one per checkout, since pytest empties its --basetemp when it starts and worktrees may push at
# once.
PRE_PUSH_TMP ?= $(HOME)/.cache/gf180-tcad/pre-push$(subst /,_,$(CURDIR))
PRE_PUSH_SLOW = tests/test_docgen.py tests/test_doc_links.py tests/test_calibrate_cv.py
pre-push: lint
	mkdir -p $(PRE_PUSH_TMP)
	uv run --locked pytest -m "not sandbox" -q -rs -p no:cacheprovider \
		--basetemp=$(PRE_PUSH_TMP)/pytest-pre-push tests $(addprefix --ignore=,$(PRE_PUSH_SLOW))

# The docs build (tests/test_doc_links.py: it builds the docs and checks their links) and the
# generated pages (tests/test_docgen.py: it runs docgen.generate on the committed and on synthetic
# result trees, issue #165). The hook runs them as well when a pushed commit changes docs/, src/,
# results/, README.md or CONTRIBUTING.md.
pre-push-docs:
	mkdir -p $(PRE_PUSH_TMP)
	uv run --locked pytest -m "not sandbox" -q -rs -p no:cacheprovider \
		--basetemp=$(PRE_PUSH_TMP)/pytest-pre-push-docs tests/test_doc_links.py tests/test_docgen.py
