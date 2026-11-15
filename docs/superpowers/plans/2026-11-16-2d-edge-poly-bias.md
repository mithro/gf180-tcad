# The 2D edge capacitance: a fitted poly length bias — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 2D plateau gap of [issue #189](https://github.com/mithro/gf180-tcad/issues/189). The calibrated 2D MOS capacitor cells have too little edge capacitance against the SPICE card. The fix adds one fitted structural parameter per device: a poly length bias δ at each gate end. Then every calibrated 2D cell, the validation and everything that records the calibration are rerun.

**Owner's decision** (2026-11-16, on #189): "Least-squares δ". Add one fitted 2D parameter per device, a poly length bias, fitted to both plateaus. Leave the residual tagged as a card artefact, and rerun all ten calibrated 2D cells.

**Evidence** (#189 and its comments; `docs/comparison/cv-agreement.md`, section "The 2D cells' edge capacitance", from PR #193):

- **The gap.** Over the W = 10 µm cells, Cgg per unit width is a line in L: `C_edge + C_area·L`. The 2D per-area term agrees with SPICE within 2.4 %. The 2D edge is low by 0.052 / 0.269 fF/µm (nfet, u = −5 / +5 V) and by 0.217 / 0.277 fF/µm (pfet).
- **The sensitivity study** (`experiments/edge-sensitivity/`, nfet W10/L0.6):
  - Contact plugs change nothing beyond re-meshing (−0.012 fF/µm).
  - A poly longer by δ at each end adds Cox·2δ on both plateaus, linear in δ (0.121 fF/µm for 30 nm).
  - Extensions (LDD) of any doping under the longer poly add the same on both plateaus. A light extension inverts at −5 V, because the adjacent p-body supplies holes. A heavy one barely depletes.
  - So the card's bias-dependent overlap (CGSL with CKAPPA) cannot be matched on both plateaus by any structure tried. The least-squares δ makes Cox·2δ the mean of the two gaps.
- **Budget.** The design spec (§5.2) allows 8 calibrated parameters per device type. A structural feature that no public source documents counts against it, and a residual that cannot otherwise be removed must justify it. The study is that justification. δ makes 4 of 8.

## Global Constraints

The Phase 2 Global Constraints apply unchanged (`docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md`). So do the restamp procedure of `docs/reproduce/index.md` (tcad-provenance), the owner's docs rules (spec §10.3: a marked figure for every described situation, equations with a `where` list, every file a link) and the no-shortcuts rule. Every task ends in a reviewed, merged PR that leaves `main` standing on its own.

## Task E1: commit the sensitivity study

- [x] `experiments/edge-sensitivity/variant.py` and `run.py`, with a `README.md`: what the harness changes, how to run it, and where results go.
- [x] A results record, `results/edge-sensitivity/<device>-<gid>.json` (outside `results/tcad/`, so the TCAD provenance checks do not cover it; the record pins its own inputs). It holds every variant's Cgg per unit width at ±5 V, the image, the plugin commit, the variant's parameters and its node count. A writer, `experiments/edge-sensitivity/record.py`, builds it from the run directories.
- [x] A sandbox test (marked `sandbox`, long) reruns the `base` and `bias30` variants of the nfet and compares them with the record. The base must also equal the committed cell's `cv.csv`.
- [x] A host test computes δ by least squares from the record and `comparison_figures.edge_split`: `2·δ·slope = mean of the two plateau gaps`, where `slope` is the measured Cgg gain per nm of δ. Pin it.
- [x] Docs: a section on `docs/limitations/moscap2d.md`, "What the 2D edge needs". It has a figure: per variant, the gain at −5 V against the gain at +5 V, with the target point. It explains the LDD finding in plain words and gives the fitted δ per device (nfet 40.2 nm, pfet 61.5 nm; misses ±0.109 and ±0.030 fF/µm). Update the limitations index and the #189 links.

## Task E2: δ as a tunable, at its start value

- [ ] `data/process/{nfet,pfet}_05v0.toml`: `[param.poly_bias_nm]`, role `tunable`, provenance `calibrated`, start 0 (`project choice`), bounds [0, 100] nm (`project choice`). Each note says the fit is 2D only (Task E3).
  - Also fix the `dv_fb_v` note's "about 40 mV" ([issue #96](https://github.com/mithro/gf180-tcad/issues/96)): state the 31 mV of `explain.idealised.degenerate_offset` with its inputs, or drop the number.
- [ ] `process.TUNABLES` gains `poly_bias_nm`. The 1D model ignores it (`moscap1d` never reads it), with a test that the 1D C–V is the same at any δ.
- [ ] `stack.build` widens the oxide, the poly and the gate electrode by δ at each end. The source/drain stays self-aligned to the widened poly. `CrossSection` keeps the drawn `l_um` for the normalisation and records `poly_l_um`, which `moscap2d.check_geometry` checks.
- [ ] The 1D calibration (`calibrate_cv`) fits the three 1D tunables. `poly_bias_nm` passes through it at its start value, and the calibration file records it with origin `start` until E3. Check how `calibration.read` handles the new name, and migrate the two committed calibration files with a recorded procedure (they gain `poly_bias_nm: 0`).
- [ ] At δ = 0 nothing computed changes. Restamp every tree. Rerun the `crosscheck-tcad` subset byte for byte, plus one calibrated 2D cell's first QS points, against the committed `cv.csv`. Record it.

## Task E3: fit δ and rerun

- [ ] `python -m gf180tcad.calibrate edge-fit --device D`: δ from the E1 record and the edge split of the committed calibrated cells at δ = 0, written into `results/tcad/calibration/<device>.json` with origin `calibrated-2d`. The test re-derives it.
- [ ] Rerun every calibrated 2D cell at the fitted δ, one 16 GiB job at a time: nfet W10/L0.6, W10/L0.7, W10/L1, W10/L2 (QS only) and W1.6/L0.7; pfet W10/L0.5, W10/L0.7, W10/L1, W10/L2 (QS only) and W1.6/L0.7. One PR per cell, or per pair, as the commit-early rule asks.
- [ ] After the last cell: rerun the 1D calibrated jobs (their provenance records the calibration's `param_sha256`), the validation, the corner fits (their provenance records the calibration) and the mesh artefacts. Update the manifest.
- [ ] Docs: the C–V page's 2D tables and the edge-capacitance section show the new values. The new residual at each plateau is tagged `spice-fit` (the card's bias-dependent overlap). Update the limitations pages, the README Status and the docs index Status.

## Task E4: check the depletion crossing

- [ ] With δ fitted, recompute the 2D-only depletion shift of [issue #108](https://github.com/mithro/gf180-tcad/issues/108) at every cell, and record whether the edge correction moved it. Update #108 and the page.
