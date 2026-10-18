# Definition of agreement

The comparison is defined at two levels: a plain-language one for anyone, and a
technical one precise enough to be checked.

## In plain language

The {term}`TCAD` setup is **credible** for a device type when **one physically
plausible {term}`process description`** (the same doping, oxide, mobility and contact
parameters for every gate length and width) reproduces the {term}`PDK`'s typical-corner
({term}`TT`, 25 °C) {term}`SPICE` behaviour across all checked geometries and biases, within
the {ref}`tolerances below <tolerances>`, **including on characteristics that were not used to tune
it**. Every remaining mismatch is listed with a probable physical or modelling
cause.

(agreement-verdicts)=

Each device and each metric gets one of three verdicts:

| Verdict | Meaning |
|---|---|
| **{term}`Agree`** | Within the technical {term}`tolerance`. |
| **{term}`Same process`** | Outside the tolerance but inside the PDK's own min-max {term}`spec window` (for example ±120 mV in {term}`Vt`, ±20 % in {term}`Idsat`; see {doc}`pdk-spec-check`). The TCAD device is plausibly *a* GF180 device, not *the* typical one. |
| **{term}`Disagree`** | Outside the spec window: the TCAD is describing a different process. |

## Technical definition

(comparison-space)=

### Comparison space

- **Devices** (initial set): {term}`nfet_05v0` and {term}`pfet_05v0`. These are wrappers
  around the {term}`nfet_06v0` and {term}`pfet_06v0` {term}`BSIM4`
  {term}`cards <model card>` (in the {{ gf180mcu_models }}), differing only in the
  mismatch parameter, so one calibrated thick-oxide ({term}`Dualgate`) recipe serves
  both.
- **Geometries**, W/L in µm: 10/{term}`Lmin` (n: 0.6, p: 0.5), 10/0.7, 10/1, 10/2,
  10/10, plus a narrow 1.6/0.7, the geometry of the taped-out `nfet_06v0` and
  `pfet_06v0` test devices ({doc}`../limitations/silicon-validation`). The {term}`bin`
  boundary at L = 0.7 µm is deliberately included.
- **Bias**: Vgs and Vds from 0 to 5 V (mirrored for p); Vbs of 0, -1 and -2 V
  (mirrored for p). Temperature is 25 °C; -40 °C and 125 °C are a later
  extension.
- **SPICE**: TT {term}`corner`, {{ ngspice }} primary and {{ Xyce }} secondary. A disagreement
  between the two SPICE engines of more than 0.5 % flags a problem with the
  reference, not with the TCAD (the {term}`engine cross-check`; current status in
  {doc}`../limitations/engine-cross-check`).

(spice-reference-conditions)=

### SPICE reference conditions

The primary {term}`golden reference` uses the PDK device as a designer would
instantiate it from a schematic: the PDK's default instance parameters (AS, AD,
PS and PD computed by the PDK's standard formulas, default SA, SB, SCA and SCB,
nf = 1, m = 1). A secondary reference uses parameters extracted from the actual
{{ gdsfactory }} cell layout; the difference between the two is reported and
attributed to `stress`, `rsd` (see the {ref}`mismatch taxonomy <mismatch-taxonomy>`) or
well-proximity effects. Both are fixed before
any TCAD result is generated.

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
({{ gf180mcu_pdk_docs }}); (2) values in the public SPICE card (TOXE, TOXP, NDEP, NSD, NGATE,
XJ, LPE0, RDSW; see the {ref}`BSIM4 manual <lit-bsim4>`), used as starting points and bounds and never as fixed truths, because
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
spec and the {term}`corner envelope` (their {term}`hull`: the lowest lower bound and the
highest upper bound), and the page shows which one sets it (spec, envelope, or both);
otherwise the corner envelope is used. The corner envelope is the envelope of the TT,
{term}`FF`, {term}`SS <SS corner>`, {term}`FS` and {term}`SF` SPICE corners at the same
geometry and bias, so the reference dataset includes all five corners. It is published as
{repo}`results/spice/envelope.json` (see {doc}`pdk-spec-check`).

(tolerances)=

### Tolerances

Tolerances come from the {ref}`ITRS 2007 <lit-itrs>` Modeling and Simulation chapter, Table MS3,
unless marked *proposal*, which means no published standard exists.

| Metric | Extraction | Tolerance |
|---|---|---|
| Vt_lin | {term}`max-gm extrapolation <max-gm Vt>` and {term}`constant-current <constant-current Vt>` (100 nA·W/L), Vds = 0.1 V ({py:mod}`gf180tcad.metrics`) | ≤ 10 mV (stretch 7 mV) |
| Vt roll-off, Vt(Lmin) - Vt(10 µm) | same | ≤ 10 mV |
| Body effect, ΔVt(Vbs = -2 V) | same | ≤ 10 mV |
| Idsat | Vgs = Vds = 5 V | ≤ 5 % (stretch 3 %) |
| Linear Id | Vds = 0.1 V, Vgs ≥ Vt + 0.5 V | ≤ 3 % |
| gm, gds, gm/Id | at Vgs = Vt + 150 mV and at Vgs = 5 V | ≤ 10 % |
| Subthreshold | RMS error of log10(Id) for Id > 1e-11 A/µm; {term}`SS <subthreshold slope>` | ≤ 0.05 decade RMS; SS ≤ 5 % (*proposal*) |
| {term}`Ioff` | Vgs = 0, Vds = 5.5 V | ≤ 30 % |
| Cgg, Cgd | Cgg-Vg at Vds = 0 (accumulation, depletion, inversion); Cgd at Vds = 5 V | ≤ 5 % |
| Effective {term}`Rsd` | 1/Id versus L extrapolation | ≤ 10 % |
| Isub (impact ionisation) | peak versus Vgs at Vds = 5 V | factor-of-2 band (*proposal*) |
| Gate leakage | - | not compared (the SPICE {term}`card <model card>` has IGCMOD = 0) |

Metrics are also reported as an error divided by {term}`σ_mismatch`, where
σ_Vt = A_Vt / √(WL) ({ref}`Pelgrom 1989 <lit-pelgrom>`) and the PDK's A_Vt is about 11.6 mV·µm, to give a physical
sense of scale. The value is the `par_vth = 0.01155` (V·µm) of the
[`nfet_05v0` subcircuit](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L46950-L46963) in the
PDK's ngspice model card (provenance tag `spice-card`). The card draws each device's Vt shift
with σ = 0.7071 · par_vth / √(W_eff · L_eff), with W_eff = W + 0.5 µm and L_eff = L − 0.4 µm in
µm, so par_vth is A_Vt in the Pelgrom convention for the Vt difference of a pair.

(numerical-acceptance)=

### Numerical acceptance

These are prerequisites: no comparison counts unless they pass.

- **Mesh convergence**: a uniformly refined mesh changes every metric by less
  than 1 % (Vt by less than 1 mV).
- **Solver convergence**: relative update below 1e-10 on potential, documented
  per bias point. No bias point is silently skipped.
- **{term}`Gummel symmetry test`** ({ref}`McAndrew 2006 <lit-mcandrew>`)
  is smooth through Vds = 0.
- **Charge conservation** in AC: Cgg = -(Cgd + Cgs + Cgb) within 0.1 %.
- **{{ DEVSIM }} versus {{ Charon }}** on the identical mesh and identical models: at most
  1 % on Id and 2 mV on Vt. A larger difference is a simulator problem and
  blocks process conclusions.

(mismatch-taxonomy)=

## Mismatch taxonomy

Every mismatch in the {doc}`results pages </results/index>` is tagged with one or more causes, with an
estimated magnitude where possible. Each is documented at two depths: a
plain-language sentence, and a technical note with equations, magnitudes and
literature references.

| Tag | Cause | Expected signature |
|---|---|---|
| `doping` | Unknown channel, {term}`LDD`, {term}`S/D` and well profiles; analytic stand-ins | Vt, roll-off, body effect, Rsd |
| `oxide-qm` | TOXE ≠ TOXP: poly depletion and quantum dark space; classical {term}`drift-diffusion` without {term}`density-gradient` ({ref}`Ancona and Iafrate <lit-ancona>`) or a poly gate | ΔVt of about 10-30 mV, Cgg in inversion low or high |
| `mobility` | Model choice ({ref}`Lombardi <lit-lombardi>`/{ref}`CVT <lit-darwish>` versus {ref}`Philips/Klaassen <lit-klaassen>`), surface-roughness parameters | linear Id, gm peak |
| `velsat` | High-field saturation model ({ref}`Caughey-Thomas <lit-caughey>`) | Idsat, gds |
| `rsd` | Contact, silicide and LDD resistance (the card has RDSW 2175 Ω·µm) | high-Vgs Id, gm roll-off |
| `geometry-2d` | A 2D cross-section ignores {term}`STI` narrow-width and corner effects | narrow-W Vt, W scaling |
| `stress` | STI/{term}`LOD` stress is present in the silicon-fitted SPICE and absent in TCAD | mobility versus SA/SB |
| `spice-fit` | BSIM4 is empirical, {term}`binned` (L bin at 0.7 µm) and fitted to silicon, so may be non-physical between bins | discontinuities, kinks at bin edges |
| `ii` | Impact-ionisation model and parameters at 5 V | Isub, gds at high Vds |
| `thermal` | Self-heating absent or present | Idsat at high power |
| `numerics` | Mesh and solver | fails the {ref}`numerical acceptance checks <numerical-acceptance>` above |
