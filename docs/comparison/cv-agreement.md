(cv-agreement)=

# C–V calibration of the TCAD MOS capacitor

The first {term}`calibrated parameter budget` spent: the 1D {term}`TCAD`
{term}`MOS capacitor <MOSCAP>` fitted to the {term}`SPICE` {term}`Cgg`–Vg of the
{term}`calibration targets <calibration target>`, then frozen and checked at the
{term}`held-out geometries <held-out geometry>`
({repo}`Task 12 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-12-calibrate-against-spice-cggvg>`).
The code is {py:mod}`gf180tcad.calibrate.cv`; the results are
{repo}`results/tcad/calibration` and {repo}`results/tcad/validation`.

## In plain language

The TCAD gate stack has three free numbers: how thick the oxide looks electrically, how
heavily the silicon under it is doped, and a small offset of the voltage at which the surface
turns from accumulation to depletion. They are adjusted, within limits fixed beforehand, until
the TCAD gate capacitance matches the {term}`PDK`'s SPICE model at three long, wide-to-short
gate lengths. Then they are frozen, and the TCAD is compared with SPICE at gate lengths it never
saw. For the nfet the result is good: the frozen stack agrees with SPICE at every geometry, the three it was fitted to and the three it never saw. For the pfet it is not: one stack cannot follow the SPICE model's pfet curves, whose accumulation-to-depletion edge moves by more than half a volt between the longest and the shortest gate, so the pfet is published as {term}`Disagree` with the reasons below.

## What is fitted

Three {term}`process file` tunables, 3 of the 8 parameters of the
{ref}`parameter budget <parameter-budget>` of each device type. Their start values, bounds and
the sources of the bounds are those of {doc}`process-data` (read with
{py:func}`gf180tcad.tcad.process.load`); the calibration never redefines them and never writes the
process files.

- `t_ox_eff_nm`, the {term}`effective oxide thickness`, between TOXE and TOXP plus the
  charge-centroid allowance (it absorbs the quantum-mechanical dark space, which is not
  modelled: classical {term}`drift-diffusion` without a {term}`density-gradient` term);
- `n_ch_cm3`, the uniform body doping, between half the doping K1 implies and 2 × NDEP;
- `dv_fb_v`, a lumped flat-band offset of ±0.2 V, applied as a rigid gate-bias shift. It
  absorbs the {term}`Boltzmann statistics` of the degenerate gate, SPICE's empirical flat band
  and any interface charge.

The model is the 1D MOS capacitor ({py:func}`gf180tcad.tcad.moscap1d.simulate`) on its selected
mesh ({ref}`mesh-convergence`), with {term}`poly depletion` simulated in the poly-gate region at the
fixed {term}`NGATE`. Its C per area is turned into a gate capacitance of each geometry by the
fixed {term}`BSIM4` bookkeeping ({py:meth}`gf180tcad.tcad.moscap1d.MoscapCV.area_scaled`): the
capacitance area LeffCV × WeffCV ({term}`DLC`, {term}`DWC`) plus the overlap, fringe and
gate-bulk terms. That bookkeeping is reference-model data, fixed, and not part of the budget.
At {term}`Lmin` it is a large part of Cgg (about 4 of 14 fF in accumulation), so Lmin mostly tests
the bookkeeping.

The targets are the {term}`TT` {{ ngspice }} {term}`cv` sweeps (1 MHz, Vds = 0) of the three
calibration geometries, W = 10 µm at L = 10 µm, 2 µm and Lmin. {{ Xyce }} has no C–V analysis,
so the spec's 0.5 % {term}`engine cross-check` cannot apply to Cgg and ngspice is the only Cgg
reference.

**Guards.** {py:func}`~gf180tcad.calibrate.cv.calibrate_cv` raises
{py:class}`~gf180tcad.calibrate.cv.CalibrationLeak`, before anything is simulated, for a
geometry that is not a calibration geometry, a target that is not the TT ngspice cv sweep of
its geometry, and a parameter that is not a free tunable.
{py:func}`~gf180tcad.calibrate.cv.validate_cv` accepts only the result loaded from the committed
calibration file whose `param_sha256` matches it, and the `validate` command refuses to run
until that file is committed.

**Optimiser.** {{ scipy }} `least_squares` with `method="trf"`, `jac="2-point"`,
`diff_step=1e-4`, `ftol = xtol = gtol = 1e-10`, `max_nfev=200`, `x0` the start values and
`x_scale` the bound widths ({py:data}`~gf180tcad.calibrate.cv.LSQ`): deterministic, with no
restarts, run in the dev-HEAD TCAD image. The residuals are the relative Cgg error at every
plateau bias and ΔV_dep/50 mV and ΔV_inv/50 mV, at each calibration geometry. Two details of
scipy's finite differences: the start `t_ox_eff_nm` sits on its lower bound, which `trf` moves
inside by 1e-10 relative; and for a parameter at 0 (`dv_fb_v` at the start) scipy replaces the
relative step by its default absolute step, 1.49e-8 V, on the first Jacobian only. A value
within 1e-3 of a bound, relative to the bound width, is reported as a bound hit.

(cv-agreement-metric)=

## The agreement metric

All regions are in u = polarity × Vg (u = Vg for the nfet, −Vg for the pfet) and are set by the
SPICE TT curve of each geometry ({py:func}`~gf180tcad.calibrate.cv.regions`):

- u_fb is where SPICE C falls to 0.9 × C_acc, C_acc = C(u = −5 V); u_t is where SPICE C, rising
  from its minimum C_min, reaches (C_min + C_inv)/2, C_inv = C(u = +5 V);
- the **accumulation plateau** is u ≤ u_fb − 1 V and the **inversion plateau** u ≥ u_t + 1 V.
  On each, the maximum |ΔCgg|/Cgg_SPICE must be ≤ 5 % (the {ref}`tolerance <tolerances>` of
  the design spec);
- the **mid-capacitance crossings**: each curve, TCAD and SPICE, crosses its own level
  C_mid = (C_min + C_acc)/2 twice, once on the depletion side (u_dep, below the minimum) and
  once on the inversion side (u_inv, above it), linearly interpolated between grid points.
  ΔV_dep = u_dep(TCAD) − u_dep(SPICE) probes the flat band and the doping, ΔV_inv the threshold.
  Each must be ≤ 50 mV. **This tolerance is a proposal: no published standard exists.** Using each
  curve's own C_mid makes the ΔV a shift of the transition, independent of a plateau error;
- the **depletion error**, max |ΔC|/C for u_fb − 1 V < u < u_t + 1 V, is reported for every
  geometry but is not a pass/fail metric.

(cv-agreement-deviation)=

### Deviation from the design spec

The {repo}`design spec, section 5.2 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#52-technical-definition>`
sets Cgg ≤ 5 % in accumulation, depletion and inversion. Here the depletion-region 5 % is
replaced by the two ΔV crossings, deliberately. In the transition a relative-C metric measures
the slope of the curve, not whether TCAD and SPICE agree. For the nfet W10/L10 at TT,
SPICE Cgg rises from 81.84 fF at u = 0.5 V to 143.75 fF at 0.7 V, and its slope reaches
0.513 fF/mV at 0.675 V. There C is about 131 fF, so a curve shifted by only 13 mV (5 % of 131 fF
over 0.513 fF/mV) already fails 5 %; on the 50 mV grid, with linear interpolation, the
smallest whole-millivolt rigid shift that fails 5 % at some bias is 15 mV. A 15 mV shift is a
small fraction of the corner spread of the crossings (about ±125 mV, below). The deviation is
also listed on {ref}`the limitations page <limitations-spec-deviations>`.

(cv-agreement-windows)=

### Verdicts and the "Same process" windows

Each plateau and each crossing gets a {ref}`verdict <agreement-verdicts>`: {term}`Agree` within
the tolerance, else {term}`Same process` inside its window, else {term}`Disagree`; a geometry's
verdict is the worst of its four ({py:func}`~gf180tcad.calibrate.cv.verdicts`).

- A **plateau**'s window, at each plateau bias, is the {term}`hull` of the five-corner
  {term}`corner envelope` of Cgg ({py:func}`~gf180tcad.calibrate.cv.envelope_cv`, pure min/max
  of the committed cv.csv files) and the public 6 V {term}`Cox` spec, 1.8 / 2.3 / 2.8 fF/µm²
  ([GF180MCU PDK electrical specs, 5.3 Gate oxide capacitance](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/spice/elec_specs/elec_specs_5_3.html),
  rows "COX (Poly) 6V", entered in {repo}`data/pdk_elec_spec.json`), mapped to Cgg by the same
  bookkeeping as the model: Cox_min/max × LeffCV × WeffCV plus the parasitic term (in 2D: × the
  drawn W × L). {py:func}`gf180tcad.specwindow.window` forms the hull and says which side sets it.
  The plateau is "Same process" when the TCAD Cgg is inside the window at every plateau bias.
- A **crossing**'s window is the min–max of that crossing voltage over the five corners at the
  same geometry ({py:func}`~gf180tcad.calibrate.cv.crossing_window`); no spec publishes one.

The Cox spec is per area and has no geometry, so the SPICE {doc}`pdk-spec-check` lists it as
"TCAD only". The TCAD compares it with the 1D C per area on both plateaus and with the oxide's
own Cox (`cox_check` in the result files).

(cv-agreement-results)=

## Results

Fitted values, from {repo}`results/tcad/calibration/nfet_05v0.json` and
{repo}`results/tcad/calibration/pfet_05v0.json`; the full results (residuals, regions,
windows) are beside them in {repo}`nfet_05v0.result.json <results/tcad/calibration/nfet_05v0.result.json>`
and {repo}`pfet_05v0.result.json <results/tcad/calibration/pfet_05v0.result.json>`. Budget used:
3 of 8 per device type. No value is within 1e-3 of a bound.

| Device | `t_ox_eff_nm` [bounds] | `n_ch_cm3` [bounds] | `dv_fb_v` [bounds] | Optimiser |
|---|---|---|---|---|
| {term}`nfet_05v0` | 16.050 [15.2, 16.95] | 8.813e16 [6.30e16, 3.4e17] | +98.7 mV [±200 mV] | xtol reached, 15 evaluations |
| {term}`pfet_05v0` | 15.721 [15.6, 16.39] | 2.147e17 [6.78e16, 3.4e17] | +187.2 mV [±200 mV] | ftol reached, 11 evaluations |

The `t_ox_eff_nm` upper bounds are TOXP plus the charge-centroid allowance Δ: 0.95 nm for the
nfet and 0.79 nm for the pfet, the maximum over both plateaus of the BSIM4 charge-thickness
centroid X_DC times EPSROX/ε_si (X_DC = 2.841 nm and 2.361 nm at the plateau edges); the
calculation is on {doc}`process-data` ("The charge-centroid allowance Δ"). The fitted nfet oxide,
16.05 nm, is TOXP plus 0.05 nm; the pfet's, 15.72 nm, is TOXE plus 0.12 nm. With them the oxide's own
Cox is 2.151 and 2.197 fF/µm², and the 1D C per area at u = −5 / +5 V is 2.112 / 2.097 (nfet) and
2.149 / 2.089 fF/µm² (pfet): all inside the public 1.8–2.8 fF/µm² spec.

Per geometry, calibration and validation (held-out) together, the plateau errors, the
crossing shifts ΔV_dep and ΔV_inv, the depletion error (reported only) and the geometry's
verdict. The validation rows are {repo}`results/tcad/validation/nfet_05v0.json` and
{repo}`results/tcad/validation/pfet_05v0.json` (1D, frozen values).

**nfet_05v0**

| W/L (µm) | Role | Accumulation | Inversion | ΔV_dep | ΔV_inv | Depletion | Verdict |
|---|---|---|---|---|---|---|---|
| 10/10 | calibration | 0.67 % | 0.63 % | +27.9 mV | +20.2 mV | 12.9 % | Agree |
| 10/2 | calibration | 0.59 % | 0.57 % | +0.7 mV | -6.5 mV | 6.7 % | Agree |
| 10/1 | validation | 0.83 % | 0.50 % | -27.3 mV | -31.7 mV | 7.8 % | Agree |
| 10/0.7 | validation | 0.75 % | 0.44 % | -31.5 mV | -30.5 mV | 6.4 % | Agree |
| 10/0.6 | calibration | 0.85 % | 0.41 % | -22.0 mV | -18.0 mV | 5.4 % | Agree |
| 1.6/0.7 | validation | 0.75 % | 0.44 % | -22.9 mV | -22.9 mV | 5.9 % | Agree |

**pfet_05v0**

| W/L (µm) | Role | Accumulation | Inversion | ΔV_dep | ΔV_inv | Depletion | Verdict |
|---|---|---|---|---|---|---|---|
| 10/10 | calibration | 4.22 % | 0.27 % | -218.1 mV | -11.5 mV | 29.6 % | Disagree |
| 10/2 | calibration | 3.73 % | 0.57 % | -128.3 mV | -4.2 mV | 24.4 % | Same process |
| 10/1 | validation | 3.76 % | 1.38 % | -0.2 mV | +8.0 mV | 17.9 % | Agree |
| 10/0.7 | validation | 4.31 % | 2.30 % | +123.8 mV | +19.9 mV | 15.0 % | Same process |
| 10/0.5 | calibration | 5.64 % | 3.81 % | +308.6 mV | +40.7 mV | 18.1 % | Disagree |
| 1.6/0.7 | validation | 6.12 % | 4.12 % | +131.8 mV | +31.8 mV | 12.9 % | Same process |

Every plateau window is set by the Cox spec side of the hull (`source` "spec" at every
plateau bias): the 1.8–2.8 fF/µm² spec is far wider than the corner envelope, so on the plateaus
"Same process" says only that the oxide is a plausible GF180 6 V oxide. The crossing windows are
the corners' own; for the nfet W10/L10 they are −0.870 to −0.618 V (u_dep) and +0.576 to
+0.825 V (u_inv).

**The geometries that dominate.** For the nfet no geometry dominates: the largest residuals
are the L = 10 µm crossings (+28 and +20 mV) and the Lmin accumulation plateau (0.85 %). For the
pfet the depletion-side crossings dominate the cost (31.85 of the final 32.38; each ΔV enters
as ΔV/50 mV): Lmin (+309 mV) and L = 10 µm (−218 mV), pulling in opposite directions.

(cv-agreement-mismatch)=

## Mismatch analysis (pfet)

{ref}`Mismatch taxonomy <mismatch-taxonomy>` tags: `spice-fit` and `doping`.

- *Plain language.* In the SPICE model the pfet's accumulation-to-depletion edge moves with
  gate length: on the TT curves it is at u_dep = −0.590 V for L = 10 µm, −0.688 V for 2 µm,
  −0.827 V for 1 µm, −0.961 V for 0.7 µm and −1.160 V for Lmin (0.5 µm), a spread of 0.57 V. The
  nfet's moves by 41 mV (−0.719 to −0.760 V). The 1D TCAD stack has one flat band for every
  length, so its own crossing moves only through the length-independent overlap terms
  (−0.808 V at L = 10 µm to −0.851 V at Lmin). The best compromise misses the long and the short
  gate in opposite directions, and agrees near L = 1 µm (ΔV_dep −0.2 mV).
- *Technical note.* The corner windows do not cover the spread either: at L = 10 µm the
  five corners span −0.718 to −0.464 V and the TCAD crossing is −0.808 V; at Lmin they span −1.360
  to −0.949 V and the TCAD is at −0.851 V. A length-dependent flat band in the C–V of a
  {term}`BSIM4` card is a property of the fitted model (`spice-fit`): in `capMod=2` the C–V flat
  band is computed from the threshold-voltage model, so the card's length dependence of Vt
  carries into Cgg. This is a hypothesis, not checked here against the card's equations term by
  term. Physically, a length-dependent flat band and depletion edge in a real pfet points at
  a non-uniform channel (`doping`): pockets or a lateral well profile, which a uniform 1D body
  cannot represent and which would cost parameters of the budget in a 2D stack
  ({ref}`parameter budget <parameter-budget>`). The other pfet residuals are smaller: the
  accumulation plateau is 3.7–6.1 % low at every length (the fit trades it against the
  crossings), and the inversion plateau and crossing agree everywhere.
- The budget is not raised: the best fit is published as it is, with its verdicts.

(cv-agreement-validation)=

## Validation

The validation ({py:func}`~gf180tcad.calibrate.cv.validate_cv`) ran after the calibration was
committed, on the committed file; it records the calibration file's sha256 and `param_sha256`.
Results at 1.6/0.7 are tagged in advance with the causes `geometry-2d` and `spice-fit`, and at
Lmin with `spice-fit`.

- **1D, held-out geometries** (W10/L0.7, W10/L1, W1.6/L0.7): the rows marked "validation" above.
  nfet: {term}`Agree` at all three. pfet: {term}`Agree` at L = 1 µm and {term}`Same process` at
  L = 0.7 µm and 1.6/0.7, both from the depletion-side crossing (+124 and +132 mV, inside the
  corner window) and, at 1.6/0.7, the accumulation plateau (6.12 %).
- **2D: not run yet.** The 2D check uses the calibrated 2D results,
  `python -m gf180tcad.tcad moscap --device D --dim 2 --params calibrated --geometry GID
  --out results/tcad/moscap2d` (the same `moscap2d.simulate` with source and drain, QS, on the
  selected 2D mesh and the SPICE grid; one job at a time, 16 GiB each). None exists: a 2D job
  takes hours, the L = 2 µm cell has no AC and the L = 10 µm cell does not solve in 2D
  ({doc}`/limitations/moscap2d`). The validation files list every geometry under `two_d` with
  status "not run"; rerunning `python -m gf180tcad.calibrate validate` after the 2D jobs fills
  them in. This deviates from the plan in one respect: the plan has
  {py:func}`~gf180tcad.calibrate.cv.validate_cv` call `moscap2d.simulate` itself; it reads the
  committed calibrated 2D results instead, so the multi-hour 2D sweeps run once, through the
  resumable 2D job, and serve both the result tree and the validation.

## Reproduce

```
uv run --locked python -m gf180tcad.calibrate run --device nfet_05v0 --out results/tcad/calibration
uv run --locked python -m gf180tcad.calibrate validate --device nfet_05v0 --out results/tcad/validation
```

and the same for `pfet_05v0`. Each `run` is one sandbox job of 1 CPU and 2 GiB (about 20 minutes
here); two runs give byte-identical files. The result-file schema: `<device>.json` is the
calibration file of {py:mod}`gf180tcad.tcad.calibration`, unchanged, so that `--params calibrated`
reads it; everything else is in `<device>.result.json`, which records the first file's sha256.
