# The 2D edge capacitance: a fitted poly length bias — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 2D plateau gap of [issue #189](https://github.com/mithro/gf180-tcad/issues/189). The calibrated 2D MOS capacitor cells have too little edge capacitance against the SPICE card. The fix adds one fitted structural parameter per device: a poly length bias δ at each gate end. Then every calibrated 2D cell, the validation and everything that records the calibration are rerun.

**Owner's decision** (2026-11-16, on #189): "Least-squares δ". Add one fitted 2D parameter per device, a poly length bias, fitted to both plateaus. Leave the residual tagged as a card artefact, and rerun all ten calibrated 2D cells.

**Evidence** (#189 and its comments; `docs/comparison/cv-agreement.md`, section "The 2D cells' edge capacitance", from PR #193):

- **The gap.** Over the W = 10 µm cells, Cgg per unit width is a line in L: `C_edge + C_area·L`. The 2D per-area term agrees with SPICE within 2.4 %. The 2D edge is low by 0.052 / 0.269 fF/µm (nfet, u = −5 / +5 V) and by 0.217 / 0.277 fF/µm (pfet).
- **The sensitivity study** (`experiments/edge-sensitivity/`, nfet W10/L0.6):
  - Contact plugs change nothing beyond re-meshing (−0.012 fF/µm).
  - A poly longer by δ at each end adds Cox·2δ on both plateaus, linear in δ (0.121 fF/µm for 30 nm).
  - Extensions (LDD) of 1e18 to 2e19 cm⁻³ under a poly 65 nm longer, with a 100 nm spacer, add 0.274–0.285 fF/µm at −5 V and 0.256 at +5 V: more at −5 V, never more at +5 V. The mechanism (a light extension inverting at −5 V, a heavy one hardly depleting) is a reading of #189's comments, not on the page.
  - So the card's bias-dependent overlap (CGSL with CKAPPA) cannot be matched on both plateaus by any structure tried. The least-squares δ makes Cox·2δ the mean of the two gaps.
- **Budget.** The design spec (§5.2) allows 8 calibrated parameters per device type. A structural feature that no public source documents counts against it, and a residual that cannot otherwise be removed must justify it. The study is that justification. δ makes 4 of 8.

## Global Constraints

The Phase 2 Global Constraints apply unchanged (`docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md`). So do the restamp procedure of `docs/reproduce/index.md` (tcad-provenance), the owner's docs rules (spec §10.3: a marked figure for every described situation, equations with a `where` list, every file a link) and the no-shortcuts rule. Every task ends in a reviewed, merged PR that leaves `main` standing on its own.

## Task E1: commit the sensitivity study

- [x] `experiments/edge-sensitivity/variant.py` and `run.py`, with a `README.md`: what the harness changes, how to run it, and where results go.
- [x] A results record, `results/edge-sensitivity/<device>-<gid>.json` (outside `results/tcad/`, so the TCAD provenance checks do not cover it; the record pins its own inputs). It holds every variant's Cgg per unit width at ±5 V, the image, the plugin commit, the variant's parameters and its node count. A writer, `experiments/edge-sensitivity/record.py`, builds it from the run directories.
- [x] A sandbox test (marked `sandbox`, long) reruns the `base` and `bias30` variants of the nfet and compares them with the record. The base must also equal the committed cell's `cv.csv`.
- [x] A host test computes δ by least squares from the record and `comparison_figures.edge_split`: `2·δ·slope = mean of the two plateau gaps`, where `slope` is the measured Cgg gain per nm of δ. Pin it.
- [x] Docs: a section on `docs/limitations/moscap2d.md`, "What the 2D edge needs". It has a figure: per variant, the gain at −5 V against the gain at +5 V, with the target point. It gives each variant family's gain at both plateaus and gives the fitted δ per device (nfet 40.2 nm, pfet 61.5 nm; misses −0.109/+0.109 and −0.030/+0.030 fF/µm at −5 V/+5 V). Update the limitations index and the #189 links.

## Task E2: δ as a tunable, at its start value

Design as built (changed from the first draft, which put δ in `process.TUNABLES`): every 1D consumer (the 1D fit, the corner fits, the calibration file check, the explainer pages) iterates `TUNABLES`, and none of them reads δ. So δ has its own role and tuple, and the 1D calibration files stay as they are.

- [x] `data/process/{nfet,pfet}_05v0.toml`: `[param.poly_bias_nm]`, role `tunable-2d`, provenance `calibrated`, start 0 (`project choice`), bounds [0, 100] nm (`project choice`). The note says it is 2D only. The budget comment is 4 of 8.
  - [x] The `dv_fb_v` note ([issue #96](https://github.com/mithro/gf180-tcad/issues/96)) drops "about 40 mV" and names `gf180tcad.explain.idealised.degenerate_offset` (its N_c input is still under #88, so no number).
- [x] `process.TUNABLES_2D = ("poly_bias_nm",)`, role `tunable-2d` in `ROLES`; `process.load` requires exactly `TUNABLES` + `TUNABLES_2D` free, each with its own role. `TUNABLES` is unchanged. Test: the 1D C-V is the same at δ = 50 nm as at 0 (`tests/tcad/test_moscap1d.py::test_poly_bias_is_2d_only`, sandbox).
- [x] `stack.build` widens the oxide, the poly and the gate electrode by δ at each end; `gate_u` is the widened gate, so the source/drain stays self-aligned to it and `check_geometry` checks the widened gate. `l_um` stays drawn; `CrossSection.poly_l_um` is the meshed length. A δ that reaches a contact raises ValueError. Test: the dualgate driver case (sandbox).
- [x] At δ = 0 nothing computed changes. Every tree restamped (docs/reproduce/index.md record). Evidence: the `crosscheck-tcad` subset byte for byte, the 1D sandbox tests, the dualgate driver case and the nfet W10/L0.6 base variant equal to the E1 record. The other 2D driver cases pass. The L = 2 µm source/drain case, first run with a 2D job's memory, is a strict expected failure like Lmin's ([issue #203](https://github.com/mithro/gf180-tcad/issues/203)).

## Task E3: fit δ and rerun

### Design (added 2026-11-26, before E3 started)

**The problem.** δ is fitted from inputs that E3 itself replaces. The E1 records' `base` variant is the committed δ = 0 cell, and the fit's targets come from `comparison_figures.edge_split` over the committed δ = 0 calibrated cells. After the rerun both are gone:
- a live re-derivation of δ would see the fitted cells and give a different number, near 0;
- `tests/test_edge_sensitivity.py::test_record_base_is_the_committed_cell` would fail;
- `::test_record_pins_what_the_runs_used` requires the record's `generator_sha256` to equal today's. So every change to a generator file (E3's own code, or the #203 note in `data/process/pfet_05v0.toml`) makes the records stale and needs a rerun of all 12 variants, about 10 h of 16 GiB jobs. Under that rule E3 would rerun them at least twice.

**Decision: the fit is frozen when it is made.**
- `results/tcad/calibration/<device>.edge.json` holds:
  - δ, the slope, the two targets and the two residuals;
  - the sha256 of the E1 record it read;
  - the commit it was made at;
  - the edge split's inputs: per gate length, Cgg per unit width at u = −5 and +5 V of the SPICE curves and of the δ = 0 cells, with each cell's `cv.csv` sha256.
- The host test re-derives δ from the values in that file and the E1 record alone; it reads no live cell. The docs numbers of the fit come from that file.
- The E1 records become frozen inputs of the fit:
  - **Pins.** `test_record_pins_what_the_runs_used` checks each pin against the file at the record's own `commit` (`git show <commit>:<path>`), not against today's file, and checks that the record's sha256 is the one `<device>.edge.json` names.
  - **Reproduction.** The sandbox rerun test keeps checking that the harness still reproduces the record: it reruns `base` and `bias30` of the nfet at δ = 0 on today's code and compares them with the record. A new variant part, `delta0`, forces `poly_bias_nm` = 0, since `load_params(..., "calibrated")` applies the fitted δ after E3. A physics change still fails this test, and a restamp no longer forces a 10 h rerun.
  - **The base check.** `test_record_base_is_the_committed_cell` compares the `base` with the δ = 0 cell values frozen in `<device>.edge.json`, not with the live cell.
- **Check after the rerun (host, no new solve).** At each plateau, the edge gap that the live `edge_split` gives for the fitted cells equals the frozen residual. The tolerance comes from the record's linearity: `bias60` is twice `bias30` within 2 %, so the bound is 2 % of `slope × δ` plus the 2D mesh-selection tolerance of Cgg. The derivation goes in the test docstring.

**Issue #203 joins E3a.** E3a changes the generator files anyway, so the #203 changes share its one restamp:
- The pfet `sd_peak_cm3` note is corrected.
- A source/drain sensitivity harness `experiments/sd-sensitivity/` mirrors E1's `run.py` and `record.py` and writes `results/sd-sensitivity/pfet_05v0-<gid>.json`:
  - for the two pfet W = 10 µm cases of `tests/tcad/moscap2d_driver.py::case_sd`, L = 0.5 and 2 µm;
  - with peaks 5e19, 1e20 and 2e20 cm⁻³;
  - with the same pins, frozen to the commit the record was made at.
- `test_pfet_sd_doping_insensitive`, a 0.1 % bound that no length meets, is replaced by:
  - a host test that the numbers on `docs/limitations/moscap2d.md` are the record's, rounded;
  - the driver's sandbox cases comparing their rerun with the record.
- The records are made after the E3b cells, at the fitted δ, because they describe the committed cells.

**Order.**
1. **E3a, one PR:** the design, `edge-fit`, the frozen fit files, the pin semantics, `delta0`, the #203 harness and tests, the note fix, and the restamp of every tree. No 2D solve.
2. **E3b, one PR per pair of cells:** the 10 cells, one 16 GiB job at a time.
3. **E3c:** the two source/drain records, the validation, the mesh artefacts, the post-rerun check and the docs.

- [ ] `python -m gf180tcad.calibrate edge-fit --device D`: δ from the E1 record and the edge split of the committed calibrated cells at δ = 0, written to its own file, `results/tcad/calibration/<device>.edge.json` (so the 1D calibration's `param_sha256` and the 1D jobs stay as they are). `load_params(..., "calibrated")` applies it for 2D jobs; the 2D job meta records its sha256, and adds δ and its origin to `tunables` with `param_sha256` covering it (E2 leaves them out so the δ = 0 cells stay byte-identical). The test re-derives δ.
- [ ] Rerun every calibrated 2D cell at the fitted δ, one 16 GiB job at a time: nfet W10/L0.6, W10/L0.7, W10/L1, W10/L2 (QS only) and W1.6/L0.7; pfet W10/L0.5, W10/L0.7, W10/L1, W10/L2 (QS only) and W1.6/L0.7. One PR per cell, or per pair, as the commit-early rule asks.
- [ ] After the last cell: rerun the validation (it reads the 2D cells) and the reduced mesh artefacts. The 1D jobs, the 1D calibration and the corner fits do not read δ: restamp them. Update the manifest.
- [ ] Docs: the C–V page's 2D tables and the edge-capacitance section show the new values. The new residual at each plateau is tagged `spice-fit` (the card's bias-dependent overlap). Update the limitations pages, the README Status and the docs index Status.

## Task E4: check the depletion crossing

- [ ] With δ fitted, recompute the 2D-only depletion shift of [issue #108](https://github.com/mithro/gf180-tcad/issues/108) at every cell, and record whether the edge correction moved it. Update #108 and the page.
