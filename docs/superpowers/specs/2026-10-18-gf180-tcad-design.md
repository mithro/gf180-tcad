# gf180-tcad — Open-source TCAD validated against the GF180MCU PDK

Status: draft for review · Date: 2026-10-18 · Repo: `github.com/mithro/gf180-tcad` (my call)

## 1. Intent

Build an open-source TCAD flow for GlobalFoundries GF180MCU transistors and
show — quantitatively, reproducibly, and in public — how closely it agrees with
the PDK's SPICE models.

**The SPICE models are the golden reference; the TCAD is the suspect.** The
point of this project is to earn (or fail to earn) confidence in the TCAD
setup. Only once that confidence exists will TCAD be used, in later work, to
improve or create SPICE models (e.g. for devices/variants the PDK does not
cover). That future use shapes this design: the flow must be scriptable,
parameterised by geometry and bias, and honest about what was *calibrated*
versus what was *predicted*.

## 2. Goals, non-goals, anti-goals

**Goals**
- G1. Generate device structures from gdsfactory layouts (gdsfactory `gf180mcu` PDK cells) and turn them into TCAD meshes and doping.
- G2. Simulate an initial small set of 5 V devices with **DEVSIM** (primary) and **Charon** (cross-check).
- G3. Produce a golden SPICE dataset from the pinned PDK with ngspice (and Xyce as a second SPICE engine).
- G4. Compare TCAD vs SPICE with a documented, two-level agreement definition (§5), and document every mismatch with its probable cause (§6).
- G5. Run every simulation inside Docker under hard resource limits (§8).
- G6. Bit-identical reproducibility of every published result (§9).
- G7. Sphinx documentation on Read the Docs covering (a) reproduction, (b) current results, (c) comparison with the PDK, (d) limitations / in-progress / known shortcomings (§10).
- G8. Identify taped-out wafer.space structures for future physical validation and pre-generate matching TCAD/SPICE predictions (§7).
- G9. Ground claims in the academic literature (§11).
- G10. Be structured so that adding the rest of the PDK's devices later is mechanical.

**Non-goals (this phase)**
- All PDK devices (3.3 V, LDMOS, BJTs, diodes, resistors, MIM, …) — later phases; architecture must allow them.
- Producing new or improved SPICE models.
- ESD / breakdown / snapback / reliability (TDDB, NBTI) — the 2022 spreadsheet's "Physical Effects" tab is a later phase.
- Process (implant/diffusion) simulation with a full process simulator — no suitable open-source one exists; analytic profiles are used instead.
- Measuring silicon.

**Anti-goals (would be failure even if it "works")**
- A1. "Matches SPICE" achieved by unconstrained curve-fitting: per-geometry tuned parameters, or tuning on the same metrics used to claim agreement.
- A2. Any NDA-derived process data (GF portal, sales kits, the maintainers' private inventory notes) entering the repo, docs, commit history or images. Every process number must cite a public source.
- A3. Results that cannot be regenerated bit-identically from a clean checkout.
- A4. Any interaction with upstream repositories (no PRs, issues, comments). Changes to third-party code live only in forks under `github.com/mithro/`.
- A5. A simulation able to push the host into OOM.
- A6. Hiding mismatches. Bad agreement, documented with a cause, is an acceptable result; undocumented good agreement is not.

## 3. Constraints (decided by the user)

- Open-source tools only.
- gdsfactory for structure generation. **Fix and extend the existing gplugins DEVSIM plugin** (currently raises `NotImplementedError` after a meshwell API change) in the fork `mithro/gplugins`, rather than writing a new plugin. Add a Charon backend there too if needed ("plugins that add new TCAD simulators").
- Licence: everything developed is **Apache-2.0**. Using GPL (or other OSS) libraries in-process is fine (DMT-core, meshwell, Charon); so is running tools in containers.
- Containers built reproducibly by GitHub Actions and published to **ghcr.io** (under `ghcr.io/mithro/…`).
- Review (user decision): every PR is reviewed by independent review subagents; findings are fixed before merge; the user spot-checks but is not a merge blocker. PRs are opened only inside `mithro/*` repos.
- Account actions: the builder may create `mithro/gf180-tcad`, forks under `mithro/`, and ghcr.io packages via the authenticated `gh` CLI; creating the Read the Docs project is handed to the user when Phase 0 needs it.
- Git: small logical commits; feature branches in worktrees; nothing committed directly to `main`; every change reviewed before merge; merges into `main` are real merge commits (`--no-ff`); no squash or rebase merges (rebasing a branch while working on it is fine). `main` = latest stable state.
- **Latest versions of everything** (tools, libraries, PDK, base images). An older version may be used only to confirm that something once worked (e.g. the gplugins DEVSIM plugin against the meshwell release it was written for); the item is then upgraded to the latest version and re-verified to give the right result. Each such "worked on old → verified on latest" step is recorded in the docs.
- **Use popular pre-built containers that already contain the PDK and tooling** rather than building toolchains from scratch: base images on IIC-OSIC-TOOLS (`hpretl/iic-osic-tools`, latest tag, pinned by digest), which ships gf180mcu, ngspice, Xyce, KLayout and gdsfactory. Project images on ghcr.io are thin layers on top (DEVSIM, forks, project code). Only tools absent from such images (Charon/Trilinos) get their own build, starting from an existing popular image where one exists.
- At most 2 concurrent subagents.
- Public-only data (A2). MPW-18H1 data was made public on 2026-10-18 (https://wafer.space/google-gf180mcu-mpw18h1/) and may be used like the other runs.

## 4. Starting facts (all public)

- **Reference PDK**: the latest gf180mcuD release as shipped in the pinned IIC-OSIC-TOOLS image (exact open_pdks commit recorded). Secondary check: open_pdks `d658698bd8bc` (what the wafer.space precheck image and runs 1/2 used), via Ciel; any model-card difference between the two is reported. SPICE library `libs.tech/ngspice/sm141064.ngspice`; BSIM4 v4.5 (level 54). The card facts below were read from the run-1/2 version and must be re-checked against the latest.
- **`nfet_05v0`/`pfet_05v0` are wrappers around the `nfet_06v0`/`pfet_06v0` BSIM4 cards**, differing only in the mismatch parameter. One calibrated thick-oxide (Dualgate) recipe therefore serves both.
- `nfet_06v0` card highlights: TOXE 15.2 nm, TOXP 16 nm, NDEP 1.7e17 cm⁻³, NGATE 1e20, NSD 1e20, XJ 0.15 µm, VTH0 0.673 V, K1 0.9, LPE0 163 nm, U0 0.0525 m²/Vs, VSAT 1.04e5 m/s, RDSW 2175 Ω·µm; IGCMOD = IGBMOD = 0 (no gate leakage); ALPHA0/BETA0 set (impact-ionisation substrate current on); two L bins (0.6–0.7, 0.7–50 µm). `pfet_06v0`: NDEP 1.7e17, NGATE 3.6e19, U0 0.0151, Lmin 0.5 µm.
- PDK electrical spec (public, gf180mcu-pdk.readthedocs.io): NE2 10/0.6 VT0 0.58/0.70/0.82 V, Idsat 400/500/600 µA/µm, Ioff ≤ 10 pA/µm, BVDSS ≥ 8.5 V; PE2 10/0.5 VT0 ≈ −0.83 V, Idsat ≈ −240 µA/µm (±~15%); 6 V Cox 1.8/2.3/2.8 fF/µm².
- **No measured device I-V/C-V data exists** for any wafer.space run 1/2 design (confirmed by the audit and bench sessions).
- **No published DEVSIM- or Charon-vs-BSIM comparison exists for any open PDK**, and no gf180mcu TCAD paper was found. This work is novel; documentation must carry that weight.

## 5. Definition of agreement

### 5.1 High-level definition (for anyone)

> The TCAD setup is **credible** for a device type when **one physically
> plausible process description** — the same doping, oxide, mobility and
> contact parameters for every gate length and width — reproduces the PDK's
> typical-corner (TT, 25 °C) SPICE behaviour across all checked geometries and
> biases, within the tolerances below, **including on characteristics that were
> not used to tune it**. Every remaining mismatch is listed with a probable
> physical or modelling cause.

Three verdict levels per device and per metric:
- **Agree** — within the technical tolerance (§5.2).
- **Same process** — outside tolerance but inside the PDK's own min–max spec window (e.g. ±120 mV Vt, ±20 % Idsat). The TCAD device is plausibly *a* GF180 device, not *the* typical one.
- **Disagree** — outside the spec window: TCAD is describing a different process.

### 5.2 Technical definition

**Comparison space.**
- Devices (initial set, my call): `nfet_05v0`, `pfet_05v0` (= 06v0 cards). Geometries W/L (µm): 10/Lmin (n: 0.6, p: 0.5), 10/0.7, 10/1, 10/2, 10/10, plus narrow **1.6/0.7** (the taped-out TRID `nfet_06v0`/`pfet_06v0` geometry, §7). Bin boundaries (L = 0.7) are deliberately included.
- Bias: Vgs, Vds 0 → 5 V (p: mirrored); Vbs 0, −1, −2 V (p: mirrored); T = 25 °C core, −40 and 125 °C as a later extension.
- SPICE: TT corner, ngspice primary, Xyce secondary; disagreement between the two SPICE engines > 0.5 % flags a reference problem, not a TCAD one.

**Calibration vs validation split (guards anti-goal A1).**
- *Calibration targets* (may be used to tune the process description): long-channel Cgg–Vg (oxide, well/channel doping, flat-band), long-channel Vt and body effect, Vt(L) roll-off, subthreshold slope.
- *Validation targets* (must never be tuned on; they are the evidence): Idsat, linear Id at high Vgs, gm, gds/output conductance, Vt at the narrow width, DIBL, all of the above at geometries not used in calibration.
- Each tunable parameter, its value, its bounds, its public source and which target it was tuned against is recorded in a machine-readable process file and rendered in the docs.
- *Parameter sources (my call).* Allowed, in order of preference: (1) PDK public docs (spec tables, layer/DRC rules — e.g. spacer, overlap, poly width); (2) values in the public SPICE card (TOXE/TOXP, NDEP, NSD, NGATE, XJ, LPE0, RDSW) used as **starting points and bounds**, never as fixed truths — BSIM parameters are fitted, not physical, and this is stated wherever used; (3) generic published 0.18 µm-class 5 V values with a citation. Every value carries a provenance tag: `pdk-doc`, `spice-card`, `literature`, or `calibrated`.
- *Free-parameter budget (my call).* At most **8 calibrated parameters per device type** (n or p), shared across all geometries, e.g. channel peak doping + depth, LDD dose + depth, S/D junction depth, effective oxide, surface-mobility scale, contact resistivity. Adding a structural feature not documented by any public source (e.g. halo/pocket) counts against the budget and must be justified by a calibration-target residual that cannot otherwise be removed. If calibration targets themselves cannot reach tolerance within the budget, calibration stops, the best fit is published with a "Disagree"/"Same process" verdict and the residual is analysed (§6); the budget is not raised silently.
- *Held-out geometries (my call, fixed before calibration).* Calibration may see W=10 at L = 10, 2 and Lmin (long-channel + roll-off endpoints). Held out for validation only: W=10 at L = 0.7 and 1, and the narrow 1.6/0.7. All metrics at held-out geometries are validation evidence; Idsat/gm/gds/DIBL are validation at every geometry.

**SPICE reference conditions (my call).** The primary golden reference uses the PDK device as a designer would instantiate it from a schematic: the PDK's default instance parameters (AS/AD/PS/PD computed by the PDK's standard formulas, default SA/SB/SCA/SCB, nf=1, m=1). A secondary reference uses parameters extracted from the actual gdsfactory cell layout; the difference between the two is reported and attributed to `stress`/`rsd`/well-proximity. Both are fixed before any TCAD result is generated.

**"Same process" window for metrics without a published spec (my call).** Taken from the PDK's own SPICE corners: the window is the envelope of TT/FF/SS/FS/SF at the same geometry and bias. Phase 1 therefore sweeps all five corners. Where the PDK publishes a spec min–max, the wider of the two windows is used and the choice is shown.

**Tolerances (ITRS 2007 Modeling & Simulation, Table MS3, unless marked).**

| Metric | Extraction | Tolerance |
|---|---|---|
| Vt_lin | max-gm extrapolation and constant-current (100 nA·W/L), Vds = 0.1 V | ≤ 10 mV (stretch 7 mV) |
| Vt roll-off Vt(Lmin) − Vt(10 µm) | same | ≤ 10 mV |
| Body effect ΔVt(Vbs = −2 V) | same | ≤ 10 mV |
| Idsat | Vgs = Vds = 5 V | ≤ 5 % (stretch 3 %) |
| Linear Id | Vds = 0.1 V, Vgs ≥ Vt + 0.5 V | ≤ 3 % |
| gm, gds, gm/Id | at Vgs = Vt + 150 mV and at Vgs = 5 V | ≤ 10 % |
| Subthreshold | RMS error of log10(Id) for Id > 1e-11 A/µm; SS | ≤ 0.05 dec RMS; SS ≤ 5 % *(proposal — no published standard)* |
| Ioff | Vgs = 0, Vds = 5.5 V | ≤ 30 % |
| Cgg, Cgd | Cgg–Vg at Vds = 0 (acc/dep/inv); Cgd at Vds = 5 V | ≤ 5 % |
| Effective Rsd | 1/Id vs L extrapolation | ≤ 10 % |
| Isub (impact ionisation) | peak vs Vgs at Vds = 5 V | factor-of-2 band *(proposal)* |
| Gate leakage | — | not compared (SPICE has IGCMOD = 0) |

Metrics are always reported also as error / σ_mismatch where σ_Vt = A_Vt/√(WL) (PDK A_Vt ≈ 11.6 mV·µm), giving a physical sense of scale.

**Numerical acceptance (prerequisite for any comparison).**
- Mesh convergence: a uniformly refined mesh changes every metric by < 1 % (Vt < 1 mV).
- Solver convergence: relative update < 1e-10 on potential, documented per bias point; no bias point silently skipped.
- Gummel symmetry test (McAndrew 2006) smooth through Vds = 0.
- Charge conservation in AC (Cgg = −(Cgd + Cgs + Cgb) within 0.1 %).
- DEVSIM vs Charon on the identical mesh and identical models: ≤ 1 % on Id, ≤ 2 mV on Vt. (A larger difference is a *simulator* problem and blocks process conclusions.)

## 6. Mismatch taxonomy (documented per result)

Every mismatch in the results pages is tagged with one or more causes, with an estimated magnitude where possible:

| Tag | Cause | Expected signature |
|---|---|---|
| `doping` | Unknown channel / LDD / S/D / well profiles; analytic stand-ins | Vt, roll-off, body effect, Rsd |
| `oxide-qm` | TOXE ≠ TOXP: poly depletion + quantum dark space; classical DD without density-gradient/poly gate | ΔVt ~10–30 mV, Cgg in inversion low/high |
| `mobility` | Model choice (Lombardi/CVT vs Philips/Klaassen), surface-roughness parameters | linear Id, gm peak |
| `velsat` | High-field saturation model (Caughey–Thomas) | Idsat, gds |
| `rsd` | Contact/silicide/LDD resistance (card RDSW 2175 Ω·µm) | high-Vgs Id, gm roll-off |
| `geometry-2d` | 2D cross-section ignores STI narrow-width / corner effects | narrow-W Vt, W scaling |
| `stress` | STI/LOD stress present in silicon-fitted SPICE, absent in TCAD | mobility vs SA/SB |
| `spice-fit` | BSIM4 is empirical, binned (L bin at 0.7 µm), fitted to silicon; may be non-physical between bins | discontinuities, kinks at bin edges |
| `ii` | Impact ionisation model/parameters at 5 V | Isub, gds at high Vds |
| `thermal` | Self-heating absent/present | Idsat at high power |
| `numerics` | Mesh/solver | fails §5.2 numerical checks |

Two documentation depths per mismatch: a plain-language sentence, and a technical note (with equations, magnitudes and literature references).

## 7. Physical validation (future silicon)

There is no measured data yet and no single-device `05v0` structure on runs 1/2. Since the 05v0 and 06v0 models are the same BSIM4 cards, the taped-out 06v0 devices are directly relevant. The repo will carry an inventory page and, for each structure, pre-computed TCAD and SPICE predictions at the exact drawn geometry so measured data can be dropped in later:

| Priority | Design (run) | Structures | Notes |
|---|---|---|---|
| 1 | TRID (ws-run1), CERN-OHL-W | single `nfet_06v0`/`pfet_06v0` W=1.6 L=0.7 with own G/D/S pads (bulk to rail); MIM equal-area/different-perimeter pair; 6 V diodes; charge-pumping pair | Datasheet says W=0.75; PCell and silicon say 1.6. Possible data behind CERN SSO. |
| 2 | 0000 / ASHES (ws-run2) | 2/1 µm 06v0 n/p FETs (×5 each), 03v3 FETs | **No licence** — reference only, do not redistribute; pad map undocumented. |
| 3 | T0P3 (ws-run2, TT GF0.3) | `tt_asw_5v0` analog switches (05v0, Ron vs V), 5 V mirror with Kelvin sense | Indirect 05v0 check. |
| 4 | CAB1 / CLON / DCO0 / 2975 | ring oscillators from 5 V 7-track cells (05v0 inv 0.82/0.60 n, 1.22/0.50 p) | Frequency vs SPICE/SDF — a circuit-level check. |
| 5 | ISHI (runs 1/2) | probe-padded inverters (05v0/06v0) | Verify Dualgate over each device: some "5 V" devices were built thin-oxide. |

Source pointers: the per-design summaries of the wafer.space run 1 and run 2 design archives, and the device-mix table derived from them; these are maintainer working files, not part of this repo. Layout access only through memory-limited wrappers around the layout viewer.

## 8. Execution sandbox

- Every simulation (SPICE, meshing, DEVSIM, Charon) runs in a container launched by one wrapper (`tools/sandbox-run`), never directly on the host.
- Per container: `--memory=X --memory-swap=X` (no swap), `--cpus`, `--pids-limit`, `--network=none` for simulation steps, non-root user, read-only image, results written only to a mounted output dir. Defaults (my call): 16 GiB / 8 CPUs per job.
- Aggregate cap: total memory across all concurrently running jobs ≤ a budget (default 128 GiB, mirroring `ws-layout.slice`). Enforced by putting containers under a dedicated cgroup slice (`--cgroup-parent`) if that can be configured on this host, otherwise by the job runner's admission control (jobs × per-job limit ≤ budget). The builder confirms which works here.
- OOM inside a container is a reported job failure (exit 137), never a host event.
- Thread counts pinned (`OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`) — needed for determinism (§9) as well as resource control.

## 9. Reproducibility ("bit-identical")

- Everything pinned: container images by digest; Python deps via a lock file with hashes; PDK by commit; forks (`mithro/gplugins`, any others) by commit; Charon/Trilinos by version and source hash.
- Images built in GitHub Actions as thin layers over the pinned IIC-OSIC-TOOLS digest, with reproducible-build settings (`SOURCE_DATE_EPOCH`, BuildKit timestamp rewriting, pip installs from a hashed lock file, no unpinned `apt-get`), pushed to `ghcr.io/mithro/gf180-tcad-*`. A CI job rebuilds and checks the digest matches. Upgrading to a newer upstream image is a deliberate, reviewed change that reruns the full comparison.
- Deterministic numerics: fixed thread counts (single-threaded linear solvers in the reference configuration), fixed mesh seeds, no wall-clock or hostname in outputs.
- Every result file has a SHA-256 recorded in a committed manifest. The full set is reproducible with one command (`make reproduce` or equivalent) inside the pinned images.
- **Where things run (user decision).** Simulations start **local** (this host, sandboxed per §8). **No self-hosted GitHub runners.** Once a simulation is working well and is cheap enough, it is *also* run on **GitHub-hosted runners**, and CI fails on any hash difference against the committed manifest. This cross-check between local and GitHub-hosted results is the evidence for deterministic output across machines; at least a representative subset (SPICE reference + one MOSCAP + one 2D MOSFET bias sweep, coarse mesh if needed) must be cross-checked this way. Expensive runs (fine meshes, 3D, Charon) stay local, with their hashes committed and the docs stating which results were cross-checked on GitHub and which only locally.
- If some step proves non-deterministic despite this, that step is documented in (d) with the observed variation, and its outputs are compared numerically (with a stated tolerance) instead of by hash. This is a fallback, not the plan.

## 10. Documentation (Sphinx → Read the Docs)

Sources in `docs/`; built in CI; published from `main` on Read the Docs. Sections map to the user's four requirements:
- (a) **Reproduce** — prerequisites, one-command reproduction, image digests, how hashes are checked, how to run a single device.
- (b) **Results** — auto-generated per device/geometry pages: I-V/C-V overlay plots (TCAD vs ngspice vs Xyce), extracted metrics table, verdict badges, mesh pictures, the process file in use.
- (c) **Comparison with the PDK** — the agreement definition (§5, both levels), a summary matrix (device × metric → Agree / Same process / Disagree), and per-mismatch explanations (§6) at both depths.
- (d) **Limitations & status** — known shortcomings, what's in progress, roadmap, assumptions and their public sources, the "no measured silicon yet" caveat, the silicon-validation inventory (§7), a literature page (§11).
Results pages are generated from the hashed result files, so the docs never show numbers that are not reproducible.

## 11. Literature (initial; [verify] items to be checked before citing)

- ITRS 2007 Modeling & Simulation, Table MS3 — tolerance numbers in §5.2.
- Tsividis & Suyama, JSSC 1994 [verify]; McAndrew, TED 2006 (Gummel symmetry) [verify] — model benchmark tests.
- BSIM4 manual (UC Berkeley) — TOXE/TOXP, NGATE, LPE0 meaning.
- Caughey & Thomas 1967; Masetti 1983; Lombardi 1988; Darwish (CVT) 1997 [verify]; Ancona & Iafrate 1989 (density-gradient) — physics models.
- Pelgrom 1989 [verify] — mismatch scale.
- Khalil/Selberherr 1995 [verify]; Lee/McIlrath/Antoniadis 1999 [verify] — inverse modelling of doping from I-V/C-V (the calibration method).
- Sanchez, DEVSIM, JOSS 2022; Charon User Manual v2.2 (SAND 2022); Hoekstra et al. SAND2007-7157; Bochev et al. 2013 [verify] — simulator references.
- SemiMod DMT-core (JOSS 2022) — tooling.

## 12. Architecture and reuse

- **This repo (`mithro/gf180-tcad`, Apache-2.0)**: device definitions, process description files, SPICE reference generation, metric extraction, comparison/verdicts, docs, sandbox, CI.
- **`mithro/gplugins` fork**: fix `gplugins.devsim` — first reproduce it working against the old meshwell/gdsfactory versions it was written for, then port to the latest meshwell, gdsfactory and DEVSIM and re-verify (meshing against latest meshwell; contacts; doping from layer stack + analytic profiles from `gplugins/process`); extend it for MOSFETs (gate stack, Dualgate oxide, LDD/S/D/well doping, body contact); add a Charon backend (gmsh → Exodus) if it fits the plugin's shape. Work done on fork branches, reviewed by PRs inside the fork (`gh pr create --repo mithro/gplugins`).
- **gdsfactory `gf180mcu` PDK package**: source of `nfet_05v0`/`pfet_05v0` cells; its LayerStack is illustrative only, so process-accurate vertical data comes from this repo's process file (forked only if a change is needed).
- **DMT-core (GPL-3, in-process OK)**: reuse for ngspice/Xyce sweep control and data handling, if it fits; otherwise borrow its patterns. SemiMod's `ihp_sg13g2_compact_models` is the template for the comparison/report pipeline. Hdev, OpenVAF: not used.
- **Charon**: latest Charon (v2.2 unless newer found) with the latest Trilinos it builds against; start from an existing popular image or conda package if a trustworthy one exists, otherwise our own reproducible image on ghcr.io.

## 13. Phases

Each phase ends with merged, reviewed work on `main`, published docs and passing reproducibility checks.

- **Phase 0 — Foundations.** Repo skeleton, Apache-2.0, sandbox wrapper with limits verified by a deliberate OOM test, base container images built reproducibly on GitHub → ghcr.io, Sphinx skeleton live on Read the Docs, CI (lint, tests, docs, hash check), contribution/review/merge rules written down.
- **Phase 1 — SPICE golden reference.** Pinned PDK; ngspice + Xyce sweeps for the device/geometry/bias matrix (§5.2); metric extraction library with tests; docs pages (b)/(c) showing SPICE-only results and spec-window checks (sanity: SPICE reproduces the PDK's own electrical spec table).
- **Phase 2 — gplugins DEVSIM fix + 1D/2D MOSCAP.** Fix the fork's plugin; MOS capacitor from gdsfactory geometry; mesh-convergence tooling; calibrate oxide and channel doping against SPICE Cgg–Vg.
- **Phase 3 — 2D MOSFET in DEVSIM.** Extend the plugin for MOSFETs; process description file with public sources; calibration on §5.2 calibration targets; validation on held-out targets; mismatch taxonomy filled in; full results/comparison docs.
- **Phase 4 — Charon cross-check.** Reproducible Charon image; Charon backend in the plugin; DEVSIM-vs-Charon numerical agreement; Charon-only physics (BGN, impact ionisation) used to explain mismatches.
- **Phase 5 — 3D and silicon-readiness.** 3D narrow-width (1.6/0.7) simulation; silicon-validation inventory and predictions at the exact TRID/ASHES/T0P3 geometries; temperature extension; roadmap for the rest of the PDK device list.

## 14. Calls I made (the user can override)

- Repo `github.com/mithro/gf180-tcad`; images `ghcr.io/mithro/gf180-tcad-*`.
- Initial device set and geometries (§5.2) — 05v0 n/p, including the TRID 1.6/0.7.
- Agreement thresholds from ITRS 2007; subthreshold and Isub tolerances are my proposals.
- Three-level verdict (Agree / Same process / Disagree).
- Resource defaults 16 GiB / 8 CPU per job, 128 GiB aggregate.
- DEVSIM first, Charon as cross-check; ngspice primary SPICE, Xyce secondary.
- MOSCAP before MOSFET.
- Parameter-source hierarchy, 8-parameter calibration budget, held-out geometries, SPICE reference instance parameters, corner-envelope "Same process" window (all §5.2).
- IIC-OSIC-TOOLS as the base container; latest gf180mcuD as primary reference, run-1/2 `d658698` as secondary.

## 15. Left to the builder

- Confirming IIC-OSIC-TOOLS is the right base (contents, size, licence) versus another popular PDK image.
- Whether DMT-core is imported or only its patterns borrowed.
- Mesh strategy (meshwell vs direct gmsh), solver settings, analytic profile forms.
- Docs theme, plotting library, CI provider details (GitHub Actions assumed).
- How the aggregate memory cap is enforced on this host (§8).
