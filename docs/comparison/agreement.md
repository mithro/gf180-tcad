# Definition of agreement

This page says when the simulated devices count as matching the {term}`PDK`'s {term}`SPICE` models. The
comparison is defined at two levels: a plain-language one for anyone, and a technical one
precise enough to be checked.

## In plain language

The {term}`TCAD` setup is **credible** for a device type when **one {term}`process description`**
reproduces the {term}`PDK`'s {term}`SPICE` behaviour. The process description is built from public
sources ({ref}`parameter-budget`), with the same doping, oxide, mobility and contact parameters
for every gate length and width. It must match the {term}`typical corner <TT>`
(TT, 25 °C) across all checked geometries and biases, within the
{ref}`tolerances below <tolerances>`. That holds **including on characteristics that were not
used to tune it**. Every remaining mismatch is listed with its
physical or modelling cause and the evidence that shows it.

(agreement-verdicts)=

Each device and each metric gets one of three verdicts:

- **{term}`Agree`**: within the technical {term}`tolerance`.
- **{term}`Same process`**: outside the tolerance but inside the
  {term}`"Same process" window`, the {term}`combined range` of the PDK's own min-max
  {term}`spec window` and the {term}`corner envelope`. Examples of
  spec windows are ±120 mV in {term}`Vt` and ±20 % in {term}`Idsat` ({doc}`pdk-spec-check`).
  The TCAD device is then inside the range the PDK specifies, not at its typical point.
- **{term}`Disagree`**: outside the "Same process" window; the TCAD is describing a different
  process.

## Technical definition

(comparison-space)=

### Comparison space

- **Devices**: {term}`nfet_05v0` and {term}`pfet_05v0`. These are wrappers
  around the {term}`nfet_06v0` and {term}`pfet_06v0` {term}`BSIM4`
  {term}`cards <model card>` (in the {{ gf180mcu_models }}), differing only in the
  mismatch parameter, so one calibrated thick-oxide ({term}`Dualgate`) recipe serves
  both.
- **Geometries**, W/L in µm: 10/{term}`Lmin` (n: 0.6, p: 0.5), 10/0.7, 10/1, 10/2,
  10/10, plus a narrow 1.6/0.7, the geometry of the taped-out `nfet_06v0` and
  `pfet_06v0` test devices ({doc}`../limitations/silicon-validation`). The {term}`bin`
  boundary at L = 0.7 µm is deliberately included.
- **Bias**: Vgs and Vds from 0 to 5 V (mirrored for p); Vbs of 0, -1 and -2 V
  (mirrored for p). Temperature is 25 °C; −40 °C and 125 °C are on the
  {doc}`roadmap </roadmap>` ([issue #71](https://github.com/mithro/gf180-tcad/issues/71)).
- **SPICE**: TT {term}`corner`, {{ ngspice }} primary and {{ Xyce }} secondary. A disagreement
  between the two SPICE engines of more than 0.5 % flags a problem with the
  reference, not with the TCAD (the {term}`engine cross-check`; current status in
  {doc}`../limitations/engine-cross-check`).

(spice-reference-conditions)=

### SPICE reference conditions

The primary {term}`SPICE reference <SPICE reference results>` uses the PDK device as a designer would
instantiate it from a schematic, with the PDK's default instance parameters:

- AS, AD, PS and PD, the source and drain areas and perimeters, computed by the PDK's standard
  formulas;
- SA, SB, SCA and SCB, the default layout distances used by the stress and well-proximity models;
- nf = 1 and m = 1.

It is the only reference built.

(secondary-reference)=

**The layout-extracted secondary reference is not built.** The
{repo}`design spec, section 5.2 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#52-technical-definition>`
also asks for a secondary reference with instance parameters extracted from the
{{ gdsfactory }} cell layout. The difference between the two is to be reported and attributed to
`stress`, `rsd` (see the {ref}`mismatch taxonomy <mismatch-taxonomy>`) or well-proximity
effects. Its absence is a recorded deviation from the spec ({ref}`limitations-spec-deviations`).
It is a {term}`Phase 3 entry gate`: it must exist, fixed, before any MOSFET TCAD result is
generated. It is on the {doc}`roadmap </roadmap>`
([issue #69](https://github.com/mithro/gf180-tcad/issues/69)).

(calibration-validation)=

### Calibration and validation are kept apart

To stop the TCAD from being tuned to the answer, the targets are split.

- **{term}`Calibration targets <calibration target>`** (may be used to tune the process
  description): long-channel {term}`Cgg`-Vg (oxide, well and channel doping, flat-band),
  long-channel Vt and {term}`body effect`, {term}`Vt(L) roll-off <Vt roll-off>`, and
  {term}`subthreshold slope`.
- **{term}`Validation targets <validation target>`** (must never be tuned on; they are the
  evidence): Idsat, {term}`linear Id` at high Vgs, {term}`gm`, {term}`gds` (output conductance),
  Vt at the narrow width, {term}`DIBL`, and all of the above at geometries not used in
  calibration.
- **{term}`Held-out geometries <held-out geometry>`**, fixed before calibration: calibration may see W = 10
  µm at L = 10, 2 and Lmin. W = 10 µm at L = 0.7 and 1 µm and the narrow
  1.6/0.7 are held out for validation only. All metrics at held-out geometries
  are validation evidence, and Idsat, gm, gds and DIBL are validation at every
  geometry.

(parameter-budget)=

### Parameter sources and budget

Allowed sources, in order of preference: (1) the PDK's public documentation
({{ gf180mcu_pdk_docs }}); (2) values in the public SPICE card (TOXE, TOXP, NDEP, {term}`NSD`, {term}`NGATE`,
{term}`XJ`, LPE0, RDSW; see the {ref}`BSIM4 manual <lit-bsim4>`), used as starting points and bounds and never as fixed truths, because
{term}`BSIM` parameters are fitted rather than physical; (3) generic published
0.18 µm-class 5 V values with a citation.

Every value carries a {term}`provenance tag`: `pdk-doc`, `spice-card`, `literature` or
`calibrated`. Each tunable parameter, its value, bounds, public source and the
target it was tuned against is recorded in a machine-readable process file and
rendered in these pages.

At most **8 {term}`calibrated parameters <calibrated parameter budget>`** are allowed per device type (n or p),
shared across all geometries. A structural feature that no public source
documents (for example a halo or pocket implant) counts against the budget and
must be justified by a calibration-target residual that cannot otherwise be
removed. If the calibration targets cannot reach tolerance within the budget,
calibration stops, the best fit is published with a {term}`Disagree` or {term}`Same process`
verdict, and the residual is analysed. The budget is not raised
silently.

(same-process-window)=

### The "Same process" window

Where the PDK publishes a spec min-max, the window covers both the published
spec and the {term}`corner envelope` (their {term}`combined range`: the lowest lower bound and the
highest upper bound), and the page shows which one sets it (spec, envelope, or both);
otherwise the corner envelope is used. The corner envelope is the envelope of the TT,
{term}`FF`, {term}`SS <SS corner>`, {term}`FS` and {term}`SF` SPICE corners at the same
geometry and bias, so the reference dataset includes all five corners. It is published as
{repo}`results/spice/envelope.json` (see {doc}`pdk-spec-check`).

(tolerances)=

### Tolerances

Tolerances come from Table MS3 of the Modeling and Simulation chapter of the
{ref}`ITRS 2007 <lit-itrs>` (International Technology Roadmap for Semiconductors). A tolerance
marked *proposal* has no published standard. Each tolerance is the largest allowed difference between
the TCAD and the SPICE value; the stretch goal is a tighter one to aim for.

Threshold voltages are extracted by {term}`max-gm extrapolation <max-gm Vt>` and by
{term}`constant current <constant-current Vt>` (100 nA·W/L), both at Vds = 0.1 V
({py:mod}`gf180tcad.metrics`):

| Metric | Tolerance (mV) | Stretch (mV) |
|---|---|---|
| Vt_lin | 10 | 7 |
| Vt roll-off, Vt(Lmin) - Vt(10 µm) | 10 | none |
| Body effect, ΔVt(Vbs = -2 V) | 10 | none |

Currents, conductances and capacitances are compared as a relative error. In this table "none"
means that the design spec sets no bias or no stretch goal for that metric:

| Metric | Vgs (V) | Vds (V) | Tolerance (%) | Stretch (%) |
|---|---|---|---|---|
| Idsat | 5 | 5 | 5 | 3 |
| Linear Id | ≥ Vt + 0.5 | 0.1 | 3 | none |
| gm, gds, gm/Id | Vt + 0.15 | none | 10 | none |
| gm, gds, gm/Id | 5 | none | 10 | none |
| {term}`Ioff` | 0 | 5.5 | 30 | none |
| Cgg | swept | 0 | 5 | none |
| Cgd | none | 5 | 5 | none |
| Effective {term}`Rsd` | none | none | 10 | none |

The Cgg-Vg {term}`sweep` covers accumulation, depletion and inversion. The effective Rsd is
extracted from 1/Id versus L.

The other metrics:

- **Subthreshold** (*proposal*): the root-mean-square (RMS) error of log10(Id), for
  Id > 1e-11 A/µm, at most 0.05 decade; the {term}`SS <subthreshold slope>` within 5 %.
- **Isub (impact ionisation)** (*proposal*): the peak versus Vgs at Vds = 5 V, within a factor
  of 2 either way.
- **Gate leakage**: not compared (the SPICE {term}`card <model card>` has IGCMOD = 0).

(metrics-not-yet-extracted)=

**Not extracted, or defined differently.** The SPICE reference
({py:mod}`gf180tcad.metrics`, keys of `metrics.json`) does not cover the whole table. That is a
recorded deviation from the design spec ({ref}`limitations-spec-deviations`). Extracting these
is a {term}`Phase 3 entry gate`
([issue #70](https://github.com/mithro/gf180-tcad/issues/70)):

- *Not extracted:* gm and gds at Vgs = Vt + 0.15 V, gm/Id, Cgd at Vds = 5 V, Cgg in
  depletion and the effective Rsd. Nor are Isub, the Vt roll-off Vt(Lmin) - Vt(10 µm) and the
  RMS error of log10(Id). Of Cgg only inversion ({term}`cgg_inv_ff`) and accumulation
  ({term}`cgg_acc_ff`) are extracted. Each geometry's Vt is published, the roll-off difference is
  not.
- *Definition differs:* the body effect ({term}`body_effect_v`) uses the
  {term}`constant-current Vt` only, not also the {term}`max-gm Vt`. The peak gm,
  {term}`gm_peak_s`, is taken on {term}`idvg_lin`. The table asks for gm at Vgs = Vt + 0.15 V and
  at Vgs = 5 V.

Metrics are also reported as an error divided by {term}`σ_mismatch`, to give a physical sense
of scale. For the Vt difference of a pair, σ_ΔVt = A_Vt / √(W·L), with the effective W and L
({ref}`Pelgrom 1989 <lit-pelgrom>`). The PDK's A_Vt is 11.55 mV·µm. The value is the
`par_vth = 0.01155` (V·µm) of the
[`nfet_05v0` subcircuit](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L46950-L46963) in the
PDK's ngspice model card (provenance tag `spice-card`). The card draws each device's Vt shift
with σ = 0.7071 · par_vth / √(W_eff · L_eff). Here W_eff = W + 0.5 µm and L_eff = L − 0.4 µm,
in µm. So par_vth is A_Vt in the Pelgrom convention for the Vt difference of a pair.

(numerical-acceptance)=

### Numerical acceptance

These are prerequisites: no comparison counts unless they pass.

- **{term}`Mesh convergence <mesh convergence>`**: a uniformly refined mesh changes every metric by less
  than 1 % (Vt by less than 1 mV).
- **Solver convergence**: relative update below 1e-10 on potential, documented
  per bias point. No bias point is silently skipped.
- **{term}`Gummel symmetry test`** ({ref}`McAndrew 2006 <lit-mcandrew>`)
  is smooth through Vds = 0.
- **Charge conservation** in the small-signal (AC) solution: Cgg = -(Cgd + Cgs + Cgb) within 0.1 %.
- **{{ DEVSIM }} versus {{ Charon }}** on the identical mesh and identical models: at most
  1 % on Id and 2 mV on Vt. Every other metric is held by kind: 1 % for relative quantities
  (the same value as the {term}`mesh convergence` criterion) and 2 mV for voltages. A larger difference is a
  simulator problem and blocks process conclusions. No {{ Charon }} {term}`job` has run, so this check
  has no result. Running both backends on every {term}`TCAD` job
  ({repo}`design spec, section 12.1 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#121-dual-backend-cross-comparison-devsim-and-charon>`)
  is on the {doc}`roadmap </roadmap>` ([issue #44](https://github.com/mithro/gf180-tcad/issues/44)).

(mismatch-taxonomy)=

## Mismatch taxonomy

Every mismatch in the {doc}`results pages </results/index>` is tagged with one or more causes, with an
estimated magnitude where possible. Each is documented at two depths: a
plain-language sentence, and a technical note with equations, magnitudes and
literature references.

The tags and the metrics each one is expected to show up in:

| Tag | Expected signature |
|---|---|
| `doping` | Vt, roll-off, body effect, Rsd |
| `oxide-qm` | ΔVt, Cgg in inversion low or high |
| `mobility` | linear Id, gm peak |
| `velsat` | Idsat, gds |
| `rsd` | high-Vgs Id, gm roll-off |
| `geometry-2d` | narrow-W Vt, W scaling |
| `stress` | mobility versus SA/SB |
| `spice-fit` | discontinuities, kinks at bin edges |
| `ii` | Isub, gds at high Vds |
| `thermal` | Idsat at high power |
| `numerics` | fails the {ref}`numerical acceptance checks <numerical-acceptance>` |

The cause behind each tag, in three groups. The process and structure of the device:

- `doping`: the channel, {term}`LDD`, {term}`S/D` and well profiles are unknown, and analytic
  stand-ins replace them.
- `rsd`: the contact, silicide and LDD resistance (the card has RDSW 2175 Ω·µm).
- `geometry-2d`: a 2D cross-section ignores {term}`STI` narrow-width and corner effects.
- `stress`: STI/{term}`LOD` stress is present in the silicon-fitted SPICE and absent in the TCAD.

The physical models of the TCAD:

- `oxide-qm`: TOXE ≠ TOXP, from {term}`poly depletion` and the quantum dark space; classical
  {term}`drift-diffusion` without {term}`density-gradient` ({ref}`Ancona and Iafrate <lit-ancona>`)
  or a poly gate misses both. The size of the expected ΔVt has no source
  ([issue #73](https://github.com/mithro/gf180-tcad/issues/73)).
- `mobility`: the mobility model choice ({ref}`Lombardi <lit-lombardi>`/{ref}`CVT <lit-darwish>`
  versus {ref}`Philips/Klaassen <lit-klaassen>`) and the surface-roughness parameters.
- `velsat`: the high-field velocity saturation model ({ref}`Caughey-Thomas <lit-caughey>`).
- `ii`: the impact-ionisation model and its parameters at 5 V.
- `thermal`: self-heating absent or present.

The SPICE model and the numerics:

- `spice-fit`: {term}`BSIM4` is empirical, {term}`binned` (L bin at 0.7 µm) and fitted to
  silicon, so it may be non-physical between bins.
- `numerics`: the mesh and the solver.
