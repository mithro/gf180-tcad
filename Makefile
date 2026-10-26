# SPDX-License-Identifier: Apache-2.0
# Reproduce the published results. See docs/reproduce/index.md.

PYTHON ?= uv run --locked python
# SPICE jobs at once, each admitted at 4 GiB (8 -> 32 GiB): pass JOBS=4 on a host with less than
# 32 GiB of memory.
JOBS ?= 8
TCAD = $(PYTHON) -m gf180tcad.tcad
CALIBRATE = $(PYTHON) -m gf180tcad.calibrate
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
	tcad-meshconv tcad-start tcad-calibrate tcad-calibrated tcad-validate \
	cache-status cache-push

# Everything, in dependency order: the SPICE reference, then the TCAD trees (mesh convergence,
# start values, calibration, calibrated values, validation), then the manifest check. Hours:
# the 2D jobs (16 GiB each) run one at a time.
reproduce:
	$(MAKE) spice-reference
	$(MAKE) tcad-meshconv
	$(MAKE) tcad-start
	$(MAKE) tcad-calibrate
	$(MAKE) tcad-calibrated
	$(MAKE) tcad-validate
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

# 4. The calibrated values. 1D only: no 2D calibrated results are committed yet
# (docs/limitations/moscap2d.md).
tcad-calibrated:
	$(TCAD) moscap --device nfet_05v0 --dim 1 --params calibrated --out results/tcad/moscap1d
	$(TCAD) moscap --device pfet_05v0 --dim 1 --params calibrated --out results/tcad/moscap1d

# 5. The validation of the committed calibration (refuses unless it is committed and unchanged).
tcad-validate:
	$(CALIBRATE) validate --device nfet_05v0 --out results/tcad/validation
	$(CALIBRATE) validate --device pfet_05v0 --out results/tcad/validation

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
