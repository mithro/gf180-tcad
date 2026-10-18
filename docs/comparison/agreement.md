# Definition of agreement

The comparison is defined at two levels: a plain-language one for anyone, and a
technical one precise enough to be checked.

## In plain language

The TCAD setup is **credible** for a device type when **one physically
plausible process description** (the same doping, oxide, mobility and contact
parameters for every gate length and width) reproduces the PDK's typical-corner
(TT, 25 °C) SPICE behaviour across all checked geometries and biases, within
the tolerances below, **including on characteristics that were not used to tune
it**. Every remaining mismatch is listed with a probable physical or modelling
cause.

Each device and each metric gets one of three verdicts:

| Verdict | Meaning |
|---|---|
| **Agree** | Within the technical tolerance. |
| **Same process** | Outside the tolerance but inside the PDK's own min-max spec window (for example ±120 mV in Vt, ±20 % in Idsat). The TCAD device is plausibly *a* GF180 device, not *the* typical one. |
| **Disagree** | Outside the spec window: the TCAD is describing a different process. |

## Technical definition

### Comparison space

- **Devices** (initial set): `nfet_05v0` and `pfet_05v0`. These are wrappers
  around the `nfet_06v0` and `pfet_06v0` BSIM4 cards, differing only in the
  mismatch parameter, so one calibrated thick-oxide (Dualgate) recipe serves
  both.
- **Geometries**, W/L in µm: 10/Lmin (n: 0.6, p: 0.5), 10/0.7, 10/1, 10/2,
  10/10, plus a narrow 1.6/0.7, the geometry of the taped-out `nfet_06v0` and
  `pfet_06v0` test devices ({doc}`../limitations/silicon-validation`). The bin
  boundary at L = 0.7 µm is deliberately included.
- **Bias**: Vgs and Vds from 0 to 5 V (mirrored for p); Vbs of 0, -1 and -2 V
  (mirrored for p). Temperature is 25 °C; -40 °C and 125 °C are a later
  extension.
- **SPICE**: TT corner, ngspice primary and Xyce secondary. A disagreement
  between the two SPICE engines of more than 0.5 % flags a problem with the
  reference, not with the TCAD.

### SPICE reference conditions

The primary golden reference uses the PDK device as a designer would
instantiate it from a schematic: the PDK's default instance parameters (AS, AD,
PS and PD computed by the PDK's standard formulas, default SA, SB, SCA and SCB,
nf = 1, m = 1). A secondary reference uses parameters extracted from the actual
gdsfactory cell layout; the difference between the two is reported and
attributed to `stress`, `rsd` or well-proximity effects. Both are fixed before
any TCAD result is generated.

### Calibration and validation are kept apart

To stop the TCAD from being tuned to the answer, the targets are split.

- **Calibration targets** (may be used to tune the process description):
  long-channel Cgg-Vg (oxide, well and channel doping, flat-band), long-channel
  Vt and body effect, Vt(L) roll-off, and subthreshold slope.
- **Validation targets** (must never be tuned on; they are the evidence): Idsat,
  linear Id at high Vgs, gm, gds (output conductance), Vt at the narrow width,
  DIBL, and all of the above at geometries not used in calibration.
- **Held-out geometries**, fixed before calibration: calibration may see W = 10
  µm at L = 10, 2 and Lmin. W = 10 µm at L = 0.7 and 1 µm and the narrow
  1.6/0.7 are held out for validation only. All metrics at held-out geometries
  are validation evidence, and Idsat, gm, gds and DIBL are validation at every
  geometry.

### Parameter sources and budget

Allowed sources, in order of preference: (1) the PDK's public documentation;
(2) values in the public SPICE card (TOXE, TOXP, NDEP, NSD, NGATE, XJ, LPE0,
RDSW), used as starting points and bounds and never as fixed truths, because
BSIM parameters are fitted rather than physical; (3) generic published
0.18 µm-class 5 V values with a citation.

Every value carries a provenance tag: `pdk-doc`, `spice-card`, `literature` or
`calibrated`. Each tunable parameter, its value, bounds, public source and the
target it was tuned against is recorded in a machine-readable process file and
rendered in these pages.

At most **8 calibrated parameters** are allowed per device type (n or p),
shared across all geometries. A structural feature that no public source
documents (for example a halo or pocket implant) counts against the budget and
must be justified by a calibration-target residual that cannot otherwise be
removed. If the calibration targets cannot reach tolerance within the budget,
calibration stops, the best fit is published with a "Disagree" or "Same
process" verdict, and the residual is analysed. The budget is not raised
silently.

### The "Same process" window

Where the PDK publishes a spec min-max, the wider of the spec window and the
corner envelope is used, and which one is shown; otherwise the corner envelope
is used. The corner envelope is the envelope of the TT, FF, SS, FS and SF SPICE
corners at the same geometry and bias, so the reference dataset sweeps all five
corners.

### Tolerances

Tolerances come from the ITRS 2007 Modeling and Simulation chapter, Table MS3,
unless marked *proposal*, which means no published standard exists.

| Metric | Extraction | Tolerance |
|---|---|---|
| Vt_lin | max-gm extrapolation and constant-current (100 nA·W/L), Vds = 0.1 V | ≤ 10 mV (stretch 7 mV) |
| Vt roll-off, Vt(Lmin) - Vt(10 µm) | same | ≤ 10 mV |
| Body effect, ΔVt(Vbs = -2 V) | same | ≤ 10 mV |
| Idsat | Vgs = Vds = 5 V | ≤ 5 % (stretch 3 %) |
| Linear Id | Vds = 0.1 V, Vgs ≥ Vt + 0.5 V | ≤ 3 % |
| gm, gds, gm/Id | at Vgs = Vt + 150 mV and at Vgs = 5 V | ≤ 10 % |
| Subthreshold | RMS error of log10(Id) for Id > 1e-11 A/µm; SS | ≤ 0.05 decade RMS; SS ≤ 5 % (*proposal*) |
| Ioff | Vgs = 0, Vds = 5.5 V | ≤ 30 % |
| Cgg, Cgd | Cgg-Vg at Vds = 0 (accumulation, depletion, inversion); Cgd at Vds = 5 V | ≤ 5 % |
| Effective Rsd | 1/Id versus L extrapolation | ≤ 10 % |
| Isub (impact ionisation) | peak versus Vgs at Vds = 5 V | factor-of-2 band (*proposal*) |
| Gate leakage | - | not compared (the SPICE card has IGCMOD = 0) |

Metrics are also reported as an error divided by σ_mismatch, where
σ_Vt = A_Vt / √(WL) and the PDK's A_Vt is about 11.6 mV·µm, to give a physical
sense of scale.

### Numerical acceptance

These are prerequisites: no comparison counts unless they pass.

- **Mesh convergence**: a uniformly refined mesh changes every metric by less
  than 1 % (Vt by less than 1 mV).
- **Solver convergence**: relative update below 1e-10 on potential, documented
  per bias point. No bias point is silently skipped.
- **Gummel symmetry test** (McAndrew 2006, see {doc}`../limitations/literature`)
  is smooth through Vds = 0.
- **Charge conservation** in AC: Cgg = -(Cgd + Cgs + Cgb) within 0.1 %.
- **DEVSIM versus Charon** on the identical mesh and identical models: at most
  1 % on Id and 2 mV on Vt. A larger difference is a simulator problem and
  blocks process conclusions.

## Mismatch taxonomy

Every mismatch in the results pages is tagged with one or more causes, with an
estimated magnitude where possible. Each is documented at two depths: a
plain-language sentence, and a technical note with equations, magnitudes and
literature references.

| Tag | Cause | Expected signature |
|---|---|---|
| `doping` | Unknown channel, LDD, S/D and well profiles; analytic stand-ins | Vt, roll-off, body effect, Rsd |
| `oxide-qm` | TOXE ≠ TOXP: poly depletion and quantum dark space; classical drift-diffusion without density-gradient or a poly gate | ΔVt of about 10-30 mV, Cgg in inversion low or high |
| `mobility` | Model choice (Lombardi/CVT versus Philips/Klaassen), surface-roughness parameters | linear Id, gm peak |
| `velsat` | High-field saturation model (Caughey-Thomas) | Idsat, gds |
| `rsd` | Contact, silicide and LDD resistance (the card has RDSW 2175 Ω·µm) | high-Vgs Id, gm roll-off |
| `geometry-2d` | A 2D cross-section ignores STI narrow-width and corner effects | narrow-W Vt, W scaling |
| `stress` | STI/LOD stress is present in the silicon-fitted SPICE and absent in TCAD | mobility versus SA/SB |
| `spice-fit` | BSIM4 is empirical, binned (L bin at 0.7 µm) and fitted to silicon, so may be non-physical between bins | discontinuities, kinks at bin edges |
| `ii` | Impact-ionisation model and parameters at 5 V | Isub, gds at high Vds |
| `thermal` | Self-heating absent or present | Idsat at high power |
| `numerics` | Mesh and solver | fails the numerical acceptance checks above |
