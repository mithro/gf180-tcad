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

### Design (added 2026-11-26, before E3 started; revised after the design review on PR #209)

**The problem.** δ is fitted from inputs that E3 itself replaces: the E1 records' `base` variant (the committed δ = 0 cell) and `comparison_figures.edge_split` over the committed δ = 0 calibrated cells. After the rerun both are gone.
- A live re-derivation of δ would see the fitted cells and give a number near 0.
- `tests/test_edge_sensitivity.py` would fail in several places:
  - `test_record_base_is_the_committed_cell`;
  - `test_edge_fit_is_the_least_squares_bias` and `test_page_prints_the_fit`;
  - the pin comparisons, in `test_record_pins_what_the_runs_used` and in the sandbox rerun test.
- `data/process/*.toml` is part of every generator hash (`gf180tcad.tcad.PROCESS_GLOB`), and so is `gf180tcad.tcad.__main__`. So E3's code and the #203 note each make the records stale under today's pin rule: 12 variants, about 10 h of 16 GiB jobs, per change.

**Decision 1: the fit is frozen when it is made, in its own tree.**
- `uv run --locked python -m gf180tcad.calibrate.edge --device D --out results/tcad/edgefit` (its own registered entry point) writes `results/tcad/edgefit/<device>.json` and the tree's `provenance.json`. The file holds:
  - δ, the slope, the two targets and the two residuals;
  - the E1 record's sha256;
  - the commit the fit was made at. The command refuses a dirty checkout, as `run.py` does.
  - the inputs of the edge split. For each gate length it holds Cgg per unit width at u = −5 and +5 V, for the SPICE curve and for the δ = 0 cell, with each cell's `cv.csv` sha256.
- The line fit moves out of `comparison_figures` into a small module that both import. The `edge-fit` closure then holds no figure code.
- `edgefit` is its own tree. Its inputs are frozen in the file, so it has no live input tree and no cycle with `tcad/moscap2d`. `tcad/moscap2d` and `tcad/validation` record its sha256 in their calibration block. `tcad/corners` is untouched: `edgefit` sits outside `tcad/calibration`.
- **Host test of the fit.** It rebuilds the δ = 0 cells from `git show <fit commit>:<cv.csv path>`, checks each sha256 against the file, and calls `edge_split(tcad_root=tmp)`. It checks the SPICE values against the live `results/spice`, which E3 does not change. It then re-derives δ from those values and the record. lint-test clones with `fetch-depth: 0`.
- **Docs.** The docs substitutions read only the committed `edgefit` files and records, never `git show`, because the docs CI job is a shallow clone with no submodule.

**Decision 2: the E1 records become frozen inputs of the fit.**
- **Pins.** `test_record_pins_what_the_runs_used` changes:
  - `generator_sha256` is compared with `git show <commit>:results/tcad/moscap2d/provenance.json`;
  - `variant_py_sha256` is compared with the file at that commit;
  - the record's sha256 must be the one `edgefit` names;
  - `git merge-base --is-ancestor <commit> HEAD` must hold.
  A branch holding a pinned commit is never rebased; a merge from main is used instead. This rule goes in CONTRIBUTING.
- **`variant.py` builds from δ = 0 always.** The `base` it solves is the cross-section of `poly_bias_nm` = 0, and `bias<nm>` is measured from there. It cannot add δ twice, and the variant names keep their meaning.
- **Reproduction.** The sandbox rerun test reruns `base` and `bias30` of both records and compares Cgg with them. Of the pins it compares the image, the plugin commit and the calibration; the two hashes are checked at the record's commit, as above.
- **Evidence.** That rerun is required evidence of every restamp, recorded in `docs/reproduce/index.md` as E2's was, so drift in the physics is caught when it would be certified.
- `test_record_base_is_the_committed_cell` compares `base` with the δ = 0 cell from `git show <fit commit>:…/cv.csv`, as in the fit test.

**Decision 3: PR boundaries keep `main` standing on its own.**
- **E3a: code only.**
  - `load_params(..., "calibrated")` applies δ to a 2D job only when `results/tcad/edgefit/<device>.json` exists. E3a does not write it, so no committed cell changes and the restamp of every tree is honest: only the stamp moves. Evidence is as in E2: the crosscheck-tcad subset byte for byte, plus the `variant.py` reproduction.
  - The same PR adds the other δ-aware code, each piece dormant until the file exists:
    - the validation's `_two_d` check (each cell's δ and its `edgefit` sha256, next to the 1D `param_sha256`);
    - `meshcut/job.load_params` and `tunable_origins`;
    - `test_committed_2d_jobs_tie_to_today_s_parameters`;
    - `test_committed_validation`;
    - the explainer's gate drawing, from the meshed poly length;
    - the edge-fit command and its tests, run against a fixture tree.
  - The #203 note fix goes in here too. The `case_sd` change moves to E3c, which runs it.
  - The strict expected failures of `test_pfet_sd_doping_insensitive` stay until the source/drain records land.
- **E3b: one PR, pushed cell by cell, merged once.**
  - The first commit writes the two `edgefit` files from the δ = 0 cells on `main`.
  - Each of the 10 cells follows as its own results commit, pushed as it finishes, one 16 GiB job at a time.
  - Then, in the same PR: the validation, the recut mesh artefacts, `MANIFEST`, the post-rerun check and the docs.
  - Merging per cell pair would leave `main` with cells, validation and artefacts that disagree for days. The owner's "never hold finished results" rule is met by pushing each cell as it finishes; the PR is open from its first commit.
- **E3c: the #203 source/drain records, its own PR after E3b.**
  - `tests/tcad/moscap2d_driver.py::case_sd` uses the calibrated values with the fitted δ, the committed cells' process. Today it uses the start values.
  - The harness `experiments/sd-sensitivity/` (`run.py`, `record.py`, `variant` as in E1) writes `results/sd-sensitivity/pfet_05v0-<gid>.json`, for L = 0.5 and 2 µm at 5e19, 1e20 and 2e20 cm⁻³.
  - `test_pfet_sd_doping_insensitive` becomes:
    - a host test that the numbers on `docs/limitations/moscap2d.md` and `docs/comparison/process-data.md`, including the 1/L scaling ratios, are the record's, rounded;
    - the driver's sandbox cases comparing their rerun with the record.
  - The strict expected failures go in this PR, not before.

**Decision 4: the check after the rerun (E3b, host).**
- **Per cell.** Fitted Cgg minus the frozen δ = 0 Cgg equals slope × δ at each plateau, within the per-cell tolerance. The tolerance is the mesh-selection criterion `meshconv.CRITERION` (1 % of Cgg) plus the quadratic-term bound of the record (0.0008 fF/µm at the fitted δ).
  - This also checks that the gain does not depend on L. The gain was measured at L0.6 and L0.5 only.
- **Per device.** The live `edge_split` gap at each plateau equals the frozen residual within Σ|wᵢ| × the per-cell tolerance + 2 % × slope × δ. Here wᵢ are the intercept's least-squares weights over the four lengths (Σ|wᵢ| ≈ 2.1). The numbers go in the test docstring and on the page.

**Decision 5: 2D mesh convergence at the fitted δ (E3b).** One 2D mesh-convergence run per device at its Lmin cell, at the fitted δ, recorded on `docs/limitations/mesh-convergence.md`. The selected level must still meet `CRITERION`; if it does not, E3b stops and the mesh is reselected.

**Docs named.**
- **E3b, the result pages:** `docs/comparison/cv-agreement.md` (the 2D tables and "The 2D cells' edge capacitance"), `docs/limitations/moscap2d.md` ("What the 2D edge needs", its numbers from `edgefit`), `docs/limitations/mesh-convergence.md`, the explained pages that draw the cell, and the results figures.
- **E3b, the status pages:** `docs/limitations/status.md`, the README and `docs/index.md` "Where it stands", and the limitations index.
- **E3a and E3b:** the restamp record in `docs/reproduce/index.md` and the plan checkboxes.
- **E3c:** `docs/comparison/process-data.md` and the source/drain section of `docs/limitations/moscap2d.md`.

E4 follows E3b.

- [x] **E3a** (code, dormant until the fit file exists): one reviewed PR.
  - [x] `gf180tcad.calibrate.edge`, its own entry point. The `tcad/edgefit` tree row is added in E3b, with the tree.
  - [x] `gf180tcad.tcad.edgefit`. `load_params_2d` and `meshcut` apply δ to calibrated 2D jobs when the file exists. A job's meta gets an `edge_fit` key (δ and the file's sha256) only then, so the δ = 0 cells keep their bytes.
  - [x] The 1D `param_sha256` stays the 1D calibration's. δ is recorded and checked separately, which deviates from the first draft's "δ in `tunables`".
  - [x] Deviation: `gf180tcad.calibrate.edge` computes the line fit itself and does not share a module with `comparison_figures`, so its closure holds no figure code. `tests/test_calibrate_edge.py` pins it equal to `limitations_figures.edge_fit` to 1e-12.
  - [x] The validation and the explainer: each 2D cell's `edge_fit` is checked against the committed fit (or none), and the cell's gate is drawn as meshed.
  - [x] `variant.py` from δ = 0, the record pin rules (record's own commit, ancestry, sandbox rerun of both records), the CONTRIBUTING no-rebase rule, and the #203 note.
  - [x] The restamp, with its evidence (docs/reproduce/index.md, "The poly length bias fit, dormant").
- [x] **E3b** (one PR, cell by cell, PR #214): the two `edgefit` files, then the 10 calibrated 2D cells at the fitted δ, one 16 GiB job at a time (W10 at each calibrated L and W1.6/L0.7, per device; the L2 cells QS only).
  - [x] Then the Lmin mesh-convergence check, the validation, the recut mesh artefacts, the post-rerun checks, `MANIFEST` and the docs. The residual at each plateau is tagged `spice-fit` (the card's bias-dependent overlap).
    - As built: the mesh-convergence check is a harness outside the hashed modules, `experiments/meshconv-fitted` (records in `results/meshconv-fitted/`), so no writer's hash moves and nothing is restamped. It reruns the study's three levels at the calibrated values and the fit; the 1D-agreement criterion is not rerun (the uniform stack has no gate end). The selected level 1 changes by 0.126 % (nfet) and 0.098 % (pfet) against level 2.
  - [x] The tests that need the committed fit: the host test of the fit from `git show <fit commit>:…/cv.csv` (each sha256 checked, then `edge_split(tcad_root=…)`), and `test_record_base_is_the_committed_cell` against the frozen δ = 0 cell instead of the live one.
  - [x] The registry: the `tcad/edgefit` tree row, and `tcad/edgefit` in the validation's input trees.
- [ ] **E3c** (#203): the source/drain harness and records at the fitted δ; the measured-value tests replace the 0.1 % bound; the pages' numbers from the records.

## Task E4: check the depletion crossing

- [ ] With δ fitted, recompute the 2D-only depletion shift of [issue #108](https://github.com/mithro/gf180-tcad/issues/108) at every cell, and record whether the edge correction moved it. Update #108 and the page.
