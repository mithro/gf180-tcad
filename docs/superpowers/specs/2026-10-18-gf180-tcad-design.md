# gf180-tcad — Open-source TCAD validated against the GF180MCU PDK

Status: draft for review · Date: 2026-10-18, amended 2026-10-27 (§16) · Repo: `github.com/mithro/gf180-tcad` (my call)

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
- G2. Simulate an initial small set of 5 V devices with **DEVSIM** and **Charon** in parallel, cross-comparing their results job by job (§12.1).
- G3. Produce a golden SPICE dataset from the pinned PDK with ngspice (and Xyce as a second SPICE engine).
- G4. Compare TCAD vs SPICE with a documented, two-level agreement definition (§5), and document every mismatch with its probable cause (§6).
- G5. Run every simulation inside Docker under hard resource limits (§8).
- G6. Bit-identical reproducibility of every published result (§9).
- G7. Sphinx documentation on Read the Docs covering (a) reproduction, (b) current results, (c) comparison with the PDK, (d) limitations / in-progress / known shortcomings (§10), with 3D renders of every simulation process (§10.1) and an explainer section on how the parts of a semiconductor device work (§10.2).
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
- gdsfactory for structure generation. **Fix and extend the existing gplugins DEVSIM plugin** (currently raises `NotImplementedError` after a meshwell API change) in the fork `mithro/gplugins`, rather than writing a new plugin. Add a Charon backend there too ("plugins that add new TCAD simulators"; required since 2026-10-27, §12.1).
- Licence: everything developed is **Apache-2.0**. Using GPL (or other OSS) libraries in-process is fine (DMT-core, meshwell, Charon); so is running tools in containers.
- Containers built reproducibly by GitHub Actions and published to **ghcr.io** (under `ghcr.io/mithro/…`).
- Review (user decision): every PR is reviewed by independent review subagents; findings are fixed before merge; the user spot-checks but is not a merge blocker. PRs are opened only inside `mithro/*` repos. Since 2026-10-27, each PR also updates the status pages it affects (README Status, the docs index Status, the plan checkboxes, the limitations index, the affected results and comparison pages), and every review checks that it did; a PR whose docs lag is "needs fixes" (§16).
- Account actions: the builder may create `mithro/gf180-tcad`, forks under `mithro/`, and ghcr.io packages via the authenticated `gh` CLI; creating the Read the Docs project is handed to the user when Phase 0 needs it.
- Git: small logical commits; feature branches in worktrees; nothing committed directly to `main`; every change reviewed before merge; merges into `main` are real merge commits (`--no-ff`); no squash or rebase merges (rebasing a branch while working on it is fine). `main` = latest stable state.
- **Latest versions of everything** (tools, libraries, PDK, base images). An older version may be used only to confirm that something once worked (e.g. the gplugins DEVSIM plugin against the meshwell release it was written for); the item is then upgraded to the latest version and re-verified to give the right result. Each such "worked on old → verified on latest" step is recorded in the docs.
- **Use popular pre-built containers that already contain the PDK and tooling** rather than building toolchains from scratch: base images on IIC-OSIC-TOOLS (`hpretl/iic-osic-tools`, latest tag, pinned by digest), which ships gf180mcu, ngspice, Xyce, KLayout and gdsfactory. Project images on ghcr.io are thin layers on top (DEVSIM, forks, project code). Only tools absent from such images (Charon/Trilinos) get their own pinned build (§12.1).
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
- DEVSIM vs Charon on the identical mesh and identical models: ≤ 1 % on Id, ≤ 2 mV on Vt; every other metric by kind, ≤ 1 % for relative quantities and ≤ 2 mV for voltages (§12.1). (A larger difference is a *simulator* problem and blocks process conclusions.)

### 5.3 Corner bounds and spread of the physical inputs

Added 2026-10-27 at the user's request (§16); tracked in issue #57. For each device, the TCAD
gives not only one value of each physical input (doping levels, oxide and layer thicknesses,
gate length and width, overlap) but a lower and an upper bound, taken from the SPICE corners
the PDK ships, and the spread between them. The typical value matters; so does the variation
around it.

**What the PDK ships.** The model library `sm141064.ngspice` has five MOSFET corner sections,
selected with `.lib sm141064.ngspice <corner>`: `typical`, `ff`, `ss`, `fs` and `sf` (the
first letter is the nfet, the second the pfet: fast or slow). These are the five the SPICE
reference already runs (`gf180tcad.devices.CORNERS`). The library also has:
- a `statistical` section: Monte Carlo of the global (die-to-die and wafer-to-wafer) variation,
  switched on by `sw_stat_global = 1`;
- a mismatch wrapper per device (`fets_mm`, switched on by `sw_stat_mismatch = 1`): a random
  threshold-voltage offset per transistor that falls with the square root of its area. In the
  upstream file the 6 V nfet (`nmos_6p0`) wrapper has `par_vth` = 11.55 mV·µm, the pair-difference
  coefficient (the A_Vt of §5.2); one transistor's σ is 0.7071 · par_vth / √(area), with
  the wrapper's own length and width offsets;
- corner sections for other devices (`moscap_*`, `bjt_*`, `diode_*`, `res_*`, `mimcap_*`),
  with typical, ff and ss only. They are out of scope with those devices (§2).

The SPICE reference runs with both statistical switches at 0 (`design.ngspice`), so each corner
is one deterministic curve.

**What the 6 V corners change.** Each corner adds an offset to some BSIM4 inputs and multiplies
others by a factor, the same for every geometry. The values below were read from the upstream
model file (`google/globalfoundries-pdk-libs-gf180mcu_fd_pr` commit `9f992d5`,
`models/ngspice/sm141064.ngspice`, sha256 `73fc67d3…`, sections `.LIB ff` and `.LIB ss`). That
file is not the pinned one: the pinned PDK's copy (sha256 `69a7ab87…`, recorded in
`results/spice/provenance.json`) differs from it, and only the pinned copy has the
`nfet_05v0`/`pfet_05v0` wrappers. The first step of the implementing task re-reads every value
from the pinned copy and corrects these tables where they differ.

Offsets added to the card value:

| Input | BSIM4 parameter | Unit | nfet ff | nfet ss | pfet ff | pfet ss |
|---|---|---|---|---|---|---|
| Threshold voltage offset | VTH0 | V | −0.1298 | +0.1193 | +0.1245 | −0.1225 |
| Oxide thickness offset, nfet | TOXE, TOXP | nm | −1.0 | +1.0 | — | — |
| Oxide thickness offset, pfet | TOXE | nm | — | — | −1.0 | +1.0 |
| Gate length offset | XL | nm | −42 | +70 | −46.5 | +69 |
| Gate width offset | XW | nm | +50 | −50 | +50 | −50 |

Factors that multiply the card value:

| Input | BSIM4 parameters | nfet ff | nfet ss | pfet ff | pfet ss |
|---|---|---|---|---|---|
| Overlap capacitance | CGSO, CGDO, CGSL, CGDL | 0.90 | 1.10 | 0.90 | 1.10 |
| Saturation velocity | VSAT | 1.0846 | 0.899 | — | — |

The pfet VTH0 is negative, so a positive offset makes the pfet faster. The pfet card shifts
TOXE only, not TOXP. `fs` and `sf` scale the nfet `ff` and `ss` offsets by 0.67 (XL, XW, VSAT)
or 0.75 (VTH0, TOXE) and give the pfet its own values between those of `ff` and `ss`; their
overlap factors are 0.93 and 1.07 (nfet) and 1.07 and 0.93 (pfet). The `statistical` section gives each of the same inputs a Gaussian spread (for
the 6 V nfet, for example, a VTH0 term of 8 mV shared with the pfet plus 28 mV of its own, and
a TOXE term of 0.4 nm plus 0.13 nm, each at one standard deviation with `mc_skew = 3`).

**Requirement.**
- *Corner calibration.* Each device's process description is calibrated against each of the
  five corners, by the same procedure, the same tunables, the same geometries and the same
  parameter budget as the typical-corner calibration (§5.2), with the corner's SPICE curves as
  targets. The card values the fit does not tune are the corner's own: the area and overlap
  bookkeeping that turns a C per area into a Cgg (XL and XW in the capacitance length and width,
  the overlap and fringe terms CGSO, CGDO, CGSL, CGDL) uses that corner's card values as fixed
  inputs. Otherwise the corner's XL, XW and overlap shifts, several percent of the gate area at
  L = 1–2 µm, would be absorbed into the oxide and doping tunables. The bounds of a tunable
  follow the corner where the card shifts the same quantity: the oxide bounds move by the
  corner's TOXE offset and the flat-band bounds by its VTH0 offset; the doping bounds stay as at
  TT. A bound hit is reported, as at TT, and a minimum or maximum that sits on a bound is
  reported as that bound, not as a measured value. Anti-goal A1 applies: the corner fits never change the
  typical calibration, and each corner's validation uses the held-out geometries of §5.2
  against the same corner.
- *What is reported.* For every tunable physical input of the device: the typical value (the
  TT fit), the minimum and the maximum across the five corner fits, and which corner gave each.
  Where a distribution is available (the `statistical` section), also the mean, the standard
  deviation and the 2.5 % and 97.5 % percentiles over a fixed-seed Monte Carlo of the global
  variation (mismatch off), each sample's SPICE curve calibrated the same way, with that
  sample's own drawn XL, XW and overlap values in the bookkeeping (printed by ngspice for each
  seed and recorded with the sample). The number of
  samples and the seeds are fixed in the plan and recorded with the results.
- *Cross-check against the card.* Where the card states the shift of a physical quantity
  directly (TOXE ±1 nm, XL, XW), the spread of the TCAD-fitted quantity is compared with it
  and the difference is reported. A TCAD oxide spread far from ±1 nm says the fit is
  absorbing the corner shift into another tunable.
- *Where it is shown.* A table per device on the results pages and on the agreement pages
  (§10(b), §10(c)): one row per input, columns for the unit, the typical value, the minimum,
  the maximum, the corner of each, and the Monte Carlo statistics. The values live in committed
  result files with provenance (§9), never only on the page.
- *Phasing.* Phase 2 does it for the three 1D MOS capacitor tunables from the C–V curves
  (Phase 2 plan, Task 16). Phase 3 extends it to the MOSFET inputs that I–V curves constrain
  (gate length and width offsets, LDD and source/drain, overlap, velocity saturation).

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

- Every simulation (SPICE, meshing, DEVSIM, Charon) and every render (§10.1) runs in a container launched by one wrapper (`tools/sandbox-run`), never directly on the host.
- Per container: `--memory=X --memory-swap=X` (no swap), `--cpus`, `--pids-limit`, `--network=none` for simulation steps, non-root user, read-only image, results written only to a mounted output dir. Defaults (my call): 16 GiB / 8 CPUs per job.
- Aggregate cap: total memory across all concurrently running jobs ≤ a budget (default 128 GiB, mirroring `ws-layout.slice`). Enforced by putting containers under a dedicated cgroup slice (`--cgroup-parent`) if that can be configured on this host, otherwise by the job runner's admission control (jobs × per-job limit ≤ budget). The builder confirms which works here.
- OOM inside a container is a reported job failure (exit 137), never a host event.
- Thread counts pinned (`OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`) — needed for determinism (§9) as well as resource control.

### 8.1 Long runs: justified by what they tell us, managed so they cannot waste a day

Added 2026-10-27 at the user's request (§16). Machine time is cheap; a wrong number or a lost
day is not. So:
- **A run is justified by what it tells us**, never ruled out by its length alone. A 24-hour
  job is fine; a quick job whose answer nobody needs is not. Run time is a scheduling fact (it
  decides the order, and that 16 GiB jobs run one at a time on this host, §8), not a reason to
  leave a result out. A missing result whose only reason is "it takes too long" is not
  accepted: it is either run or the plan says what it would tell us and why that is not needed.
- **A failure to converge or a solver error is a correctness problem**, recorded with what is
  known and an issue, never accepted as "infeasible" and dropped.
- **Every run longer than a few minutes is managed**, so that it never runs for a day and gives
  wrong values, or runs for a day and then fails on something that could have been checked at
  the start:
  - *checks first*: inputs, image, mesh and output directory are checked, and one bias point is
    solved, before the long part starts;
  - *progress log*: a line per completed step (bias point, level, sample) with the time and the
    peak memory, written to a log file, not only to the terminal;
  - *resume state*: the run saves its state after each completed step and continues from it
    after a restart; a resumed run records that it was resumed (as the 2D sweeps do with
    `resumed`);
  - *bounded retries*: a failed step is retried a fixed, small number of times with a recorded
    change (for example extended precision), then the run stops with an error that names the
    step;
  - *output checks that fail loudly*: each step's result is checked as it is written (finite,
    within physical limits, smooth against its neighbours where that is expected), and a failed
    check stops the run instead of writing a number;
  - *memory cap*: every run is in the sandbox with its memory limit (§8), so running out of
    memory is a reported failure of that job, never a host event, and the limit is never raised
    just to make a run pass.
- **Decisions taken on run time alone are revisited** (the list and their status are in §16).

## 9. Reproducibility ("bit-identical")

- Everything pinned: container images by digest; Python deps via a lock file with hashes; PDK by commit; forks (`mithro/gplugins`, any others) by commit; Charon/Trilinos by version and source hash.
- Images built in GitHub Actions as thin layers over the pinned IIC-OSIC-TOOLS digest, with reproducible-build settings (`SOURCE_DATE_EPOCH`, BuildKit timestamp rewriting, pip installs from a hashed lock file, no unpinned `apt-get`), pushed to `ghcr.io/mithro/gf180-tcad-*`. A CI job rebuilds and checks the digest matches. Upgrading to a newer upstream image is a deliberate, reviewed change that reruns the full comparison.
- Deterministic numerics: fixed thread counts (single-threaded linear solvers in the reference configuration), fixed mesh seeds, no wall-clock or hostname in outputs.
- Every result file has a SHA-256 recorded in a committed manifest. The full set is reproducible with one command (`make reproduce` or equivalent) inside the pinned images.
- **Where things run (user decision).** Simulations start **local** (this host, sandboxed per §8). **No self-hosted GitHub runners.** Once a simulation is working well and fits a GitHub-hosted runner's limits (time per job and memory), it is *also* run on **GitHub-hosted runners**, and CI fails on any hash difference against the committed manifest. This cross-check between local and GitHub-hosted results is the evidence for deterministic output across machines; at least a representative subset (SPICE reference + one MOSCAP + one 2D MOSFET bias sweep, coarse mesh if needed) must be cross-checked this way. Runs that do not fit those limits (fine meshes, 3D, Charon) stay local, with their hashes committed and the docs stating which results were cross-checked on GitHub and which only locally.
- **Restamps.** Updating a committed tree's `provenance.json` to a new generator hash without
  rerunning it (a restamp) is allowed only where the rerun is shown to give the same bytes, for
  example by rerunning a representative job and comparing hashes. Otherwise the tree is rerun.
- If some step proves non-deterministic despite this, that step is documented in (d) with the observed variation, and its outputs are compared numerically (with a stated tolerance) instead of by hash. This is a fallback, not the plan.

### 9.1 Output cache for large regenerable artefacts

Added 2026-10-27 at the user's request (§16). Large generated files that can be regenerated
and should stay out of the primary repo (the gmsh meshes `mesh.msh` of the 2D jobs, which are
also the full meshes that the §10.1 reduced mesh artefacts are cut from, and later other large
job outputs of the same kind) live in a separate repo,
[`mithro/gf180-tcad-output-cache`](https://github.com/mithro/gf180-tcad-output-cache), which
is a shared cache for everyone, not an archive.
- **Content-addressed.** Each file is stored under the sha256 that the primary repo already
  records for it (for example `mesh_sha256` in a 2D job's `cv.meta.json`). A fetched file is
  checked against that sha256 before use.
- **The primary repo is the only source of truth.** Its manifest (`results/MANIFEST.sha256`) and
  `provenance.json` files decide what a result is; the cache only saves regeneration time. A
  missing or wrong cache entry is regenerated in the sandbox, never trusted.
- **Disposable.** The cache may be wiped and rebuilt from the primary repo at any time, so
  nothing may depend on its history, its commit ids or its continued existence.
- **Never fetched by the docs build**, which stays offline and reads only the primary repo.
- Access goes through one tool, `tools/output-cache` (with `src/gf180tcad/outcache.py` and
  `data/output-cache.json`), specified and built separately.
- **Only reduction generators read the cache.** A generator that cuts a small committed
  artefact from a large one (the reduced mesh artefact of §10.1) fetches the large file by hash
  on the host, before its sandboxed `--network none` run (or regenerates it in the sandbox), and
  commits only the reduced artefact with provenance. Renders, tests, CI and the docs build read
  only committed files, never the cache.

## 10. Documentation (Sphinx → Read the Docs)

Sources in `docs/`; built in CI; published from `main` on Read the Docs. Sections map to the user's four requirements, plus the explainer section of §10.2:
- (a) **Reproduce** — prerequisites, one-command reproduction, image digests, how hashes are checked, how to run a single device.
- (b) **Results** — auto-generated per device/geometry pages: I-V/C-V overlay plots (TCAD vs ngspice vs Xyce), extracted metrics table, verdict badges, mesh pictures (drawn as part of the renders of §10.1), the process file in use, and the corner bounds and spread of each physical input (§5.3).
- (c) **Comparison with the PDK** — the agreement definition (§5, both levels), a summary matrix (device × metric → Agree / Same process / Disagree), per-mismatch explanations (§6) at both depths, and the corner bounds of the physical inputs next to the typical values (§5.3).
- (d) **Limitations & status** — known shortcomings, what's in progress, roadmap, assumptions and their public sources, the "no measured silicon yet" caveat, the silicon-validation inventory (§7), a literature page (§11).
Results pages are generated from the hashed result files, so the docs never show numbers that are not reproducible.

### 10.1 3D renders of the simulated processes

Added 2026-10-27 at the user's request (§16); tracked in issue #43. The documentation shows every simulation process
as a high-quality 3D render, so that a reader sees what is simulated and what happens during it
before reading a single plot. A render may simplify and exaggerate (not to scale, stretched
axes, omitted parts), but every quantity in it comes from the committed numbers.

**What is rendered.** One render per simulation process: a still image, plus a short animation
where the process is a sweep or a time or iteration evolution. Initial set:

| # | Process | Kind | Shows |
|---|---|---|---|
| R1 | 1D MOS capacitor C–V sweep | animation over Vg (+ poster still) | the gate/oxide/silicon stack, the band edges and Fermi levels bending through accumulation, depletion and inversion, the carrier and depletion charge, and a marker moving along the Cgg–Vg curve |
| R2 | 2D MOS capacitor cross-section | still (optional slow orbit) | the cross-section with its regions, mesh (near the gate) and net doping |
| R3 | Calibration loop | animation over optimiser iterations | which tunable moves (`t_ox_eff_nm`, `n_ch_cm3`, `dv_fb_v`), between which bounds, and what each step does to the TCAD curve against the SPICE target |
| R4 | SPICE reference sweeps | still per device (optional animation over geometry) | the I-V and C-V sweeps of §5.2 as surfaces over the bias plane, with the five-corner envelope |
| R5 | Mesh convergence | animation over refinement levels | the mesh refining and the curve difference to the next finer level shrinking below the 1 % criterion |
| R6 | Later phases | per phase | the 2D MOSFET bias sweeps (potential, carrier and current density), the 3D narrow-width device, and the devsim/Charon comparison (§12.1) side by side |

Each render has its own docs page (or section of the process's existing page) that states, in
words, **what is shown, what is to scale, and what is exaggerated and by how much**. The same
statement is drawn into the image (for example "oxide thickness ×40, not to scale").

**Based on the actual numbers.** Every geometric or physical quantity in a render (thicknesses,
lengths, doping, potentials, band energies, charges, capacitances, parameter values, mesh
nodes) is read from a committed result or process-data file. Nothing is invented, interpolated
by hand or typed into a render script.
- Each render has a **render manifest** next to the image (`<render>.render.json`). For every
  quantity it names the source file, the key inside it (JSON key path, or CSV column and row
  selector), the unit, the value used and the scale factor applied (1 when to scale). It also
  lists the derived quantities with the formula that derives them (for example a band edge
  from the potential and the band gap, with the band gap's own source).
- A render generator may derive a quantity from committed outputs when the derivation (its
  inputs and formula) is recorded in the manifest. A simulation job is extended to write a
  quantity, with provenance, only when it cannot be derived from committed outputs (for example
  the 1D potential and carrier profiles at each bias for R1, or the optimiser's iteration
  history for R3, neither of which is committed today).
- A test (`tests/test_renders.py`) re-reads every manifest entry from its named source and
  fails if a value differs, a source is missing, or a scale factor is not stated.

**Pipeline and provenance.**
- Renders are made by a committed, re-runnable generator under the repo (scene builders under
  `src/gf180tcad/render/`, Blender scripts under `render/blender/`, one shared style file for
  camera, lights, materials and palette). Step 1 reads the committed inputs and writes a scene
  description holding every number and scale factor; step 2 runs Blender on it; step 3 encodes
  animation frames. The Blender scripts take every quantity from the scene description and
  contain only styling.
- Blender (the user's suggestion; pinned once chosen): an official Blender release (latest at the time, version and archive
  sha256 recorded) in a thin project render image `ghcr.io/mithro/gf180-tcad-render`, built
  reproducibly like the other images (§9), with the video encoder pinned the same way. It runs
  only through `tools/sandbox-run`, with `--network none`, under the §8 limits, from committed
  inputs only (never from the §9.1 output cache). Seeds, sample counts and thread counts are
  fixed, so a rerun on the same host should give the same file; that is best effort and not
  tested, and render files are not part of the bit-identity rule of §9.
- The rendered files (PNG stills, WebM animations with a PNG poster frame) are committed under
  `results/renders/<process>/`, registered in `results/MANIFEST.sha256`, with a
  `provenance.json` per tree root as for the TCAD results: the sha256 of every input named in
  the manifests, the generator sha256 (scene builders, Blender scripts, style file), the render
  image reference and the Blender version.
- The docs build only embeds the committed files. It stays offline and deterministic: no
  Blender, no rendering and no video encoding at docs build time.
- **Size budget.** A still is at most 2 MB; an animation is at most 20 s and 6 MB; the whole
  `results/renders/` tree is at most 100 MB. A test enforces the three limits.
- **When to regenerate.** A render must be regenerated in the same PR whenever any input named
  in its manifest, or the generator, changes. The test above compares the recorded input and
  generator hashes with the current files and fails on a stale render, so a stale render cannot
  be merged. Bit-identity of renders is not assumed: renders are outside the GitHub-hosted
  hash cross-check (§9); what is checked is the manifest (values and input hashes), not the
  pixels.

**Quality bar ("good looking, high quality").**
- Resolution: stills 1920×1080 (16:9); animations 1920×1080 at 30 fps, VP9 WebM. Text in the
  image legible at the docs' content width.
- One lighting rig and one material library for every render: the same material and colour
  always means the same thing (silicon, oxide, poly, metal, mesh edges, electrons, holes), on a
  neutral background readable in the light and the dark docs theme. Any external asset (HDRI,
  font) is committed with its licence.
- Labels and legends in the image: region names, axis names with units, a scale bar, colour
  bars for every colour-mapped quantity, and the exaggeration statement. Each embedded image has
  alt text and a caption; the page text repeats what the image says, so nothing is only visual.
- Colour-blind-safe palette: Okabe–Ito for categories (regions, carriers, backends); a
  perceptually uniform map (cividis or viridis) for magnitudes; a diverging map centred on zero
  for signed quantities (net doping, potential). Colour is never the only cue.
- Consistent camera conventions across devices, so that pages compare: gate on top, substrate
  down, source left and drain right; x along the channel, y into the depth, z along the width;
  one fixed camera angle and framing per render kind, the same for nfet and pfet and for every
  geometry, with the same exaggeration factors where the geometry allows.
- Each render is reviewed against this list as part of its PR's review.

**Mesh pictures (§10(b), issue #39).** The mesh pictures of §10(b) are part of these renders
(R2, R5), drawn from a committed **reduced mesh artefact** with provenance, never from the full
mesh. The full 2D meshes (`mesh.msh`, 25–62 MB each) stay out of the primary repo, in the output
cache of §9.1, keyed by their `mesh_sha256`. The reduced artefact is
written in the TCAD image by a generator module from the job's own mesh, fetched from the
output cache by hash (`tools/output-cache`, on the host before the sandboxed run) or
regenerated: the node coordinates,
the triangle connectivity and the region of each element, restricted to a window around the
gate (or the mesher's own export of that window), at most 2 MB per job. It records the sha256
of the full mesh it came from, which must equal the committed `mesh_sha256` of that job
(`cv.meta.json`), so the picture is tied to the mesh that produced the results. The same
artefact feeds the 2D docs pages' flat mesh figure. Until it exists, the deviation stays on the
limitations page. If a fresh mesh-only run does not reproduce the committed `mesh_sha256` (the
committed 2D trees predate the current job format), the 2D job is rerun, so that the results
and the artefact come from one mesh.

**Phasing.** Render image first; then R1 and R2 (with the reduced mesh artefact and the 1D
profile files they need); then R3, R4 and R5; then the later phases' renders as those phases
produce results. Every 2D job whose mesh is neither in the cache nor reproduced with its
committed `mesh_sha256` is rerun, one 16 GiB job at a time (§8), managed as §8.1 requires (the
committed 2D trees predate the current job format, so this is likely for all of them).

### 10.2 How it works: explainer section

Added 2026-10-27 at the user's request (§16); tracked in issue #46. The docs gain a fifth,
reader-first section, `docs/explained/`: a general explanation of how the parts of a
semiconductor device work, grounded in this repo's real artefacts rather than in textbook
numbers.
- **Scope, in three tiers.**
  1. *Basics*: silicon, doping and carriers; the band diagram and the Fermi level; the pn
     junction and its depletion region; wells; source, drain and LDD; oxide and poly-silicon as
     materials. Grounded in the GF180MCU process data (`data/process/`) and the §10.1 renders.
  2. *The MOS capacitor*: oxide, accumulation, depletion, inversion, flat band, the C–V curve
     and what sets each part of it.
  3. *The MOSFET*, with the MOSFET phases: the channel, threshold voltage, body effect,
     short-channel effects (Vt roll-off, DIBL), saturation.

  Each concept is explained in plain language first, then with the equation and the literature
  reference already cited in §11 or the docs' literature page.
- **Grounded in the repo.** Every number and figure comes from committed inputs: the GF180MCU
  process data files (`data/process/`), the committed SPICE reference sweeps and extracted
  metrics (`results/spice/`), the TCAD results and calibration outcome (`results/tcad/`), and the
  3D renders of §10.1. Each explainer page names the committed files it draws from. No invented
  numbers; a deliberately idealised example (for example a textbook uniform-doping case) is
  labelled as such and computed by the docs generator from stated inputs.
- **Honest about the gap.** Each page links to the results and limitations pages of the same
  device and says where the simple picture and the simulated or SPICE reality differ (for
  example the pfet C–V disagreement of the 1D calibration, poly depletion, the quasi-static vs
  high-frequency curve).
- **Kept current by the same machinery.** The pages are built offline from committed inputs like
  the rest of the docs. A number enters a page by `docgen` substitution from its source file
  (preferred), or, when hand-written, is listed in `tests/test_doc_numbers.py` with its source.
  A test checks that every artefact an explainer page references exists, so a moved or
  regenerated result cannot leave a stale explanation.

### 10.3 How the documentation is written

Added 2026-10-27 at the user's request (§16). Work that is not documented and explained does
not count as done: if it cannot be explained in plain English, it is not understood yet. The
rules, with the tests that enforce the testable ones (`tests/test_doc_style.py`, added by the
docs style pass that follows this amendment):
- **Present state only.** A page says what is true now and what the reader needs to know now.
  What used to be true, what was changed and when, and how a result came about belong in the
  change log of this spec (§16), in the plans (`docs/superpowers/plans/`), in the reproduction
  record (`docs/reproduce/`) and on the plugin-history page, nowhere else. Test:
  `test_no_history_phrases` fails on narrative phrases ("previously", "no longer", "used to",
  "before PR", "until PR", "was changed") in pages outside those places, with an explicit
  per-line opt-out that gives the reason.
- **Plain English; no expert needed.** Each page starts with what it shows in plain words; an
  equation or a technical term comes after the plain statement and links to its definition.
  Every acronym is spelled out on its first use on each page (or links to the glossary there).
- **No invented terms.** Each glossary term is either standard in the field, with a reference
  (a textbook, a standard or the tool's manual), or a short plain-words description of a thing
  this repo does, named in ordinary words. A coined label is replaced by plain words. Code
  identifiers keep their names; the prose around them uses plain words. Tests:
  `test_glossary_definitions_short` (each glossary definition's first paragraph is at most 60
  words; the detail goes below it or on a linked page) and `test_every_term_is_defined` (every
  `{term}` role in the sources names a glossary entry; this repeats the Sphinx check without a
  build, so it runs in under a second).
- **Tables hold data.** One value per cell, units in the column header, numbers in columns of
  their own; no sentences and no multi-number cells. A table that mixes kinds is split. Long
  explanations go in the text below the table, or in a definition list or subsections with a
  short table of the bare facts. Test: `test_table_cells`, over the Markdown sources and the
  generated pages, fails on a cell of more than 8 words or with two or more numbers that carry
  units, with an explicit per-table opt-out marker that gives the reason.

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
- **`mithro/gplugins` fork**: fix `gplugins.devsim` — first reproduce it working against the old meshwell/gdsfactory versions it was written for, then port to the latest meshwell, gdsfactory and DEVSIM and re-verify (meshing against latest meshwell; contacts; doping from layer stack + analytic profiles from `gplugins/process`); extend it for MOSFETs (gate stack, Dualgate oxide, LDD/S/D/well doping, body contact); add a Charon backend (gmsh → Exodus) behind the backend seam (§12.1). Work done on fork branches, reviewed by PRs inside the fork (`gh pr create --repo mithro/gplugins`).
- **gdsfactory `gf180mcu` PDK package**: source of `nfet_05v0`/`pfet_05v0` cells; its LayerStack is illustrative only, so process-accurate vertical data comes from this repo's process file (forked only if a change is needed).
- **DMT-core (GPL-3, in-process OK)**: reuse for ngspice/Xyce sweep control and data handling, if it fits; otherwise borrow its patterns. SemiMod's `ihp_sg13g2_compact_models` is the template for the comparison/report pipeline. Hdev, OpenVAF: not used.
- **Charon**: latest Charon (v2.2 unless newer found) with the latest Trilinos it builds against; always our own reproducible, pinned image on ghcr.io (§12.1), which may be built from a trusted existing upstream recipe, image or conda package.

### 12.1 Dual-backend cross-comparison: devsim and Charon

Added 2026-10-27 at the user's request (§16); tracked in issue #44. DEVSIM and Charon run **in parallel** on every TCAD
job, not only as a late Phase 4 check, and their results are cross-compared job by job. Two
independent simulators agreeing on the same inputs is the evidence that a TCAD-vs-SPICE result
is a property of the device description, not of one simulator's discretisation, models or bugs.

**Same device description.** Both backends consume one backend-neutral device description:
mesh, regions and materials, contacts, doping, physical constants and models, and the bias
plan. It is produced once, through the backend seam of the Phase 2 plan, Task 15
(`device_description.py` plus `backends/devsim.py` in the `mithro/gplugins` fork), with a
`backends/charon.py` that translates it into Charon's mesh and input files. The physics is
pinned identically on both sides: the constants table of the Phase 2 plan (ε0, q, k_B, ε_si,
ε_ox, T, n_i), Boltzmann statistics, the same mobility, recombination and gate treatment. A
model one backend lacks is not approximated on the other; the job is marked as not comparable
for that model, and the reason is recorded.

**Committed results.**
- Each TCAD job's committed results carry both backends' outputs, in parallel per-backend
  trees with one `provenance.json` per tree root, as in Phase 2. The existing DEVSIM trees keep
  their paths; the exact layout is fixed in the plan.
- Each job also gets a **comparison file** (`compare.json`): per metric and per bias, the two
  values, the delta (absolute and relative), the tolerance applied and a pass/fail, in the
  style of `pdkdiff.compare`'s per-metric delta summary. It is computed inside one stated image,
  never by comparing numbers from different images bit-wise (Phase 2 Global Constraints).
- An agreement page in `docs/comparison/` (generated from the comparison files only) shows,
  per device and job, the overlay of both backends, the delta plots and the pass/fail matrix.

**What "agree" means.** No new numbers: the tolerances are the numerical-acceptance ones of
§5.2.
- The DEVSIM-vs-Charon line of §5.2 sets 1 % on Id and 2 mV on Vt, on the identical mesh and
  models. It is inherited unchanged and applied to every other metric by kind: relative
  quantities (currents, capacitances at each bias, plateau values, conductances) within
  **1 %**, the same value as the mesh-convergence criterion of §5.2 (`CRITERION = 0.01` in
  `src/gf180tcad/tcad/meshconv.py`); voltage quantities (Vt, flat band, the C–V crossing
  voltages) within **2 mV**.
- A relative tolerance is meaningless for quantities near zero (Id near Vds = 0, small
  capacitances). They need an absolute floor; its value is an open question (below), to be set
  from the solver-noise floor the mesh-convergence tooling already uses, not chosen freely.
- The normative values live in §5.2 and are rendered on `docs/comparison/agreement.md`
  (numerical acceptance). The code holds them once, in the comparison module, which imports the
  mesh-convergence criterion rather than repeating it; a test ties the module's values to the
  page.
- Each backend must first pass the §5.2 numerical acceptance on its own (mesh and solver
  convergence, charge conservation). A backend comparison on an unconverged result does not
  count.

**On disagreement.** A difference above tolerance is a simulator problem and blocks process
conclusions for that job (§5.2). Both results stay committed and shown; the disagreement is
recorded on the limitations page with its numbers and its probable cause (discretisation
scheme, model implementation, contact or boundary treatment, solver), tagged `numerics` in the
§6 taxonomy, and gets an issue. One backend is never silently picked, preferred or dropped, and
the tolerance is never loosened to make a job pass.

**Sandbox, provenance, reproduction.** Charon runs only in a sandbox image, like DEVSIM:
- a pinned Charon build (latest release and the Trilinos it builds against, by version and
  source sha256, §9), in its own reproducible image on ghcr.io, run through
  `tools/sandbox-run` with `--network none` and the §8 limits, single-rank and single-threaded
  in the reference configuration for determinism. The **Charon image is a prerequisite task**.
- Charon trees carry the same provenance as the DEVSIM trees (image reference, plugin commit,
  generator sha256, parameter sha256) and are registered in the manifest; `make reproduce`
  regenerates both backends.
- The SPICE reference stays the yardstick for both backends. Calibration (§5.2) and the
  TCAD-vs-SPICE verdicts are reported per backend, and the comparison runs on identical inputs
  (the start values, and the calibrated values of the backend that was calibrated), so a delta
  is a simulator difference and nothing else. Anti-goal A1 applies to each backend.

**Phasing.** First the backend seam (Phase 2 plan, Task 15, no Charon code; its submodule bump
keeps every committed TCAD result byte-identical); then the Charon
image; then the 1D MOS capacitor on Charon; then the 2D MOS capacitor; then each later device
on both backends from its first result. The cross-comparison pages appear with the first
Charon job. The detailed plan is a separate plan document.

**Open questions** (to be settled by the Charon image and plan work, and recorded on the
limitations page as they are answered):
- **Build cost.** Charon needs a large Trilinos build (Panzer and its dependencies): build
  time, image size, and whether a trustworthy existing image or package exists (§12) are
  unknown. Whether a single-rank, single-threaded build is bit-reproducible across hosts is
  also unknown; if not, Charon results are compared numerically, as §9's fallback allows.
- **Meshing and input format.** Charon reads Exodus II meshes and its own input files. Whether
  the backend can write Exodus from the gmsh/meshwell mesh without changing node positions
  (so that "the identical mesh" holds exactly), and how regions, contacts and the doping field
  map onto Charon's input, is not yet known.
- **Which physics models both support identically.** Overriding every constant (ε_si 11.7, the
  Altermatt n_i, T = 298.15 K), Boltzmann statistics in the degenerate poly gate, constant
  mobility and SRH with given lifetimes must be checked in Charon. The two discretisations
  differ (DEVSIM's finite-volume Scharfetter–Gummel; Charon's finite-element formulations), so
  their discretisation errors differ on the same mesh.
- **C–V method.** How Charon gives the quasi-static Cgg (dQ/dV from a DC sweep, or a
  small-signal AC solve) and whether it matches DEVSIM's method closely enough to compare
  within 1 %.
- **Absolute floor.** The absolute tolerance for near-zero quantities (see "What agree
  means"), and whether it can be taken from the mesh-convergence noise floor (`NOISE_K` times
  the solver tolerance in `meshconv.py`) for both backends.
- **Calibration.** Whether each backend is also calibrated independently (comparing the two
  calibrated parameter sets is a further check), in addition to running Charon on DEVSIM's
  calibrated values.
- **2D run time and memory on this host.** 2D DEVSIM jobs take hours at 16 GiB, one at a time,
  and Charon adds its own. This sets the order of the work, not whether a job runs (§8.1); the
  Charon plan measures it.

## 13. Phases

Each phase ends with merged, reviewed work on `main`, published docs and passing reproducibility checks.

- **Phase 0 — Foundations.** Repo skeleton, Apache-2.0, sandbox wrapper with limits verified by a deliberate OOM test, base container images built reproducibly on GitHub → ghcr.io, Sphinx skeleton live on Read the Docs, CI (lint, tests, docs, hash check), contribution/review/merge rules written down.
- **Phase 1 — SPICE golden reference.** Pinned PDK; ngspice + Xyce sweeps for the device/geometry/bias matrix (§5.2); metric extraction library with tests; docs pages (b)/(c) showing SPICE-only results and spec-window checks (sanity: SPICE reproduces the PDK's own electrical spec table).
- **Phase 2 — gplugins DEVSIM fix + 1D/2D MOSCAP.** Fix the fork's plugin; MOS capacitor from gdsfactory geometry; mesh-convergence tooling; calibrate oxide and channel doping against SPICE Cgg–Vg; corner bounds and spread of those inputs (§5.3).
- **Phase 3 — 2D MOSFET (DEVSIM and Charon, §12.1).** Extend the plugin for MOSFETs; process description file with public sources; calibration on §5.2 calibration targets; validation on held-out targets; mismatch taxonomy filled in; corner bounds and spread of the MOSFET inputs (§5.3); full results/comparison docs.
- **Phase 4 — Charon in parallel (amended 2026-10-27, §12.1).** No longer after Phase 3: it starts once the Phase 2 backend seam exists and runs alongside Phases 2–3. Reproducible Charon image; Charon backend in the plugin; the 1D, then 2D MOS capacitor on Charon, then every later device on both backends; per-job DEVSIM-vs-Charon comparison files and agreement page; Charon-only physics (BGN, impact ionisation) used to explain mismatches. Phases 2 and 3 can close without Charon results for their devices; Phase 4 closes when every device has results from both backends and the comparison page.
- **Phase 5 — 3D and silicon-readiness.** 3D narrow-width (1.6/0.7) simulation; silicon-validation inventory and predictions at the exact TRID/ASHES/T0P3 geometries; temperature extension; roadmap for the rest of the PDK device list.

## 14. Calls I made (the user can override)

- Repo `github.com/mithro/gf180-tcad`; images `ghcr.io/mithro/gf180-tcad-*`.
- Initial device set and geometries (§5.2) — 05v0 n/p, including the TRID 1.6/0.7.
- Agreement thresholds from ITRS 2007; subthreshold and Isub tolerances are my proposals.
- Three-level verdict (Agree / Same process / Disagree).
- Resource defaults 16 GiB / 8 CPU per job, 128 GiB aggregate.
- DEVSIM first, Charon as cross-check; ngspice primary SPICE, Xyce secondary. *(Superseded 2026-10-27 by the user: DEVSIM and Charon run in parallel and are cross-compared, §12.1.)*
- MOSCAP before MOSFET.
- Parameter-source hierarchy, 8-parameter calibration budget, held-out geometries, SPICE reference instance parameters, corner-envelope "Same process" window (all §5.2).
- Corner spread statistics (§5.3): min and max across the five corners, plus the mean, standard deviation and 2.5 % / 97.5 % percentiles of a fixed-seed Monte Carlo of the global variation.
- IIC-OSIC-TOOLS as the base container; latest gf180mcuD as primary reference, run-1/2 `d658698` as secondary.

## 15. Left to the builder

- Confirming IIC-OSIC-TOOLS is the right base (contents, size, licence) versus another popular PDK image.
- Whether DMT-core is imported or only its patterns borrowed.
- Mesh strategy (meshwell vs direct gmsh), solver settings, analytic profile forms.
- Docs theme, plotting library, CI provider details (GitHub Actions assumed).
- How the aggregate memory cap is enforced on this host (§8).

## 16. Change log

Amendments after the 2026-10-18 draft, newest last. Each quotes the user's request verbatim, so
that the intent survives later rewording of the sections it changed.

- **2026-10-27: 3D renders of the simulated processes.** New §10.1; §10(b) mesh pictures now
  come from it (settling issue #39 by requirement; the issue stays open until the artefact and
  the picture exist). The user's words:
  > "Add to the spec that we should include good looking, high quality 3d renders (probably
  > using blender 3d) of all various simulation processes in the documentation which allows a
  > person to see and understand what is being simulated and what is happening. These renders
  > can simplify or exadurate the real world results (making diagrams not to scale, etc) but
  > should still be based on the actual numbers."
- **2026-10-27: devsim and Charon in parallel.** New §12.1; G2, the §5.2 DEVSIM-vs-Charon
  line, Phase 4 (§13) and the §14 call changed to match. The user's words:
  > "We should also be using devsim and charon in parallel and cross comparing their results."
- **2026-10-27: output cache for large regenerable files.** New §9.1; §10.1 and the #39
  resolution take the full meshes from it. The user's words:
  > "Around #39 -- Let's create a seperate gf180-tcad-output-cache repo for large generated
  > files that should be kept out of the primary repo and can be regenerated. This repo should
  > be able to be regenerated fresh at any time and is effectively just a shared cache for
  > everyone."
- **2026-10-27: explainer section.** New §10.2. The user's words:
  > "Add to the spec that there should be a section of the documentation which is designed to
  > be a general explaination how the various parts of semiconductors work using the
  > references / assets from the repo to ground things in the real world."
- **2026-10-27: docs updated with every PR.** §3 (the Review constraint) and `CONTRIBUTING.md` (PR
  checklist) changed: the author updates the affected status pages in the same PR, and every
  review checks it. The user's words (11:45 and 11:50 ACDT):
  > "Make sure that the documentatoin is getting updated as work is done. It is currently out
  > of date."
  >
  > "Make sure that as part of every review it also checks if the docs have been correctly
  > updated at the same time."
- **2026-10-27 12:15 ACDT: six directives after reading the documentation.** The user's words,
  in the order given:
  1. > "Just because something takes a long time to run, doesn't mean it is worth doing. CPU
     > time is pretty cheap. Its fine to run a 24 hour job if it is correctly managed so that
     > it doesn't run 24 hours and produce rubbish or incorrect values, takes 24 hours and just
     > gives an error, etc."
  2. > "We want TCAD simulations to be able to provide upper and lower bound values for things
     > like doping level, material thickness and shape, etc all based on the corners that spice
     > provides."
  3. > "The medium / average value is important but so is the variance -- we want to understand
     > the upper and lower bounds on things."
  4. > "The work doesn't exist unless it has been properly documented and explained (you don't
     > understand something unless you can explain it in plain english). It should not explain
     > historic / old stuff -- it should explain what the person needs to know right now.
     > Historic state is for historians."
  5. > "Make sure to not make up jargon or terminology that doesn't exist. Use short plain
     > descriptions and link to the more detailed explaination if needed. Nothing should
     > require you to be an expert to understand things."
  6. > "There are a huge number of tables which mash data which should be in columns into
     > textual descriptions embedded in cells. Tables with long text or multiple numbers in an
     > individual cell are huge red flags the table is not formatted correctly."

  What changed: directive 1 is new §8.1; §9 (what runs on GitHub-hosted runners), §10.1
  (phasing) and §12.1 (the open question on 2D run time) lost their cost reasoning. Directives
  2 and 3 are new §5.3, with Task 16 in the Phase 2 plan and a Phase 3 item (§13); issue #57.
  Directives 4 to 6 are new §10.3, enforced by `tests/test_doc_style.py`.

  Decisions that had been taken on run time, and their status under §8.1:
  - *Renders plan: no 2D rerun only to get mesh pictures.* Already changed before these
    directives: the renders plan follows §10.1, which reruns every 2D job whose mesh cannot be
    reproduced (`docs/superpowers/plans/2026-10-27-renders-pipeline.md`, Task R0). No further
    change.
  - *The 2D MOS capacitor at L = 10 µm is not run* (`docs/limitations/moscap2d.md`): its
    equilibrium drift-diffusion solve fails in UMFPACK. Reopened as a correctness problem,
    issue #58.
  - *The 2D MOS capacitor at L = 2 µm has no AC result*: the small-signal solve fails in
    UMFPACK. Reopened as a correctness problem, issue #59.
  - *Level 3 of the 2D mesh-convergence study is left out*, for an estimated 9.7 h of QS
    ("over the 8 h job rule", `gf180tcad.tcad.meshconv.EXCLUDED_2D`) and for the L = 10 µm
    solver failure. There is no 8-hour rule any more; the run-time half of the reason is
    withdrawn. The level stays out until #58 is solved, since it is expected to fail the same
    way (the same size; not yet attempted, and #58 includes running it); the
    recorded reason is reworded when the 2D study is next rerun (it is part of the committed
    report, so changing it restamps that tree).
  - *Provenance restamped instead of rerun* (Task 12 and issue #34, the 2D trees and the 2D mesh
    convergence): replaced by the reruns of #35, which regenerate the 2D trees with today's
    code. The restamp rule is now in §9.
  - *`make reproduce` not run end to end, because the 2D jobs take hours*: to be run, managed
    per §8.1, once #35's 2D reruns are in.
  - *GitHub-hosted cross-check only where a run is "cheap enough"* (§9): reworded to the
    runners' actual limits (time per job and memory), which a run must fit; anything that does
    not fit is cross-checked locally and the docs say so, as before.
