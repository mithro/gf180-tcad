(cv-agreement)=

# C–V calibration of the TCAD MOS capacitor

This page shows how the simulated {term}`MOS capacitor <MOSCAP>` is fitted to the gate
capacitance of the {term}`PDK`'s {term}`SPICE` model. It then shows how well the fitted values
match at gate lengths not used in the fit.

It is the first use of the
{term}`calibrated parameter budget`. The 1D {term}`TCAD` MOS capacitor is fitted to the
{term}`Cgg`–Vg of the {term}`calibration targets <calibration target>`. It is then fixed and
checked at the {term}`held-out geometries <held-out geometry>`
({repo}`plan <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-12-calibrate-against-spice-cggvg>`).
The code is {py:mod}`gf180tcad.calibrate.cv`; the results are
{repo}`results/tcad/calibration` and {repo}`results/tcad/validation`.

## In plain language

The TCAD gate stack has three free numbers: how thick the oxide looks electrically, how
heavily the silicon under it is doped, and a small offset of the voltage at which the surface
turns from accumulation to depletion. They are adjusted, within limits fixed beforehand, until
the TCAD gate capacitance matches the {term}`PDK`'s SPICE model at three long, wide-to-short
gate lengths. Then they are fixed, and the TCAD is compared with SPICE at gate lengths it never
saw.

For the nfet the result is good. In 1D the fixed stack agrees with SPICE at every
geometry, the three it was fitted to and the three it never saw. The 2D check is
{term}`Disagree` at both calibrated cells (below).

For the pfet it is not. One stack cannot
follow the SPICE model's pfet curves. Their accumulation-to-depletion edge moves by more than
half a volt between the longest and the shortest gate. So the pfet is published as
{term}`Disagree` with the reasons below.

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

At {term}`Lmin` it is a large part of Cgg, so Lmin mostly tests the bookkeeping. For the
calibrated nfet in accumulation (u = −5 V) it is 3.97 of 14.36 fF. These values come from
{py:meth}`~gf180tcad.tcad.moscap1d.MoscapCV.area_scaled` on the committed calibrated 1D curve.

The targets are the {term}`TT` {{ ngspice }} {term}`cv` sweeps (1 MHz, Vds = 0) of the three
calibration geometries, W = 10 µm at L = 10 µm, 2 µm and Lmin. {{ Xyce }} has no {term}`C–V` analysis,
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
restarts, run in the {term}`dev-HEAD TCAD image`. The residuals are the relative Cgg error at every
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
  Each must be ≤ 50 mV. **This {term}`tolerance` is a proposal: no published standard exists.**
  **Interpretation of the plan:** the plan defines C_mid = (C_min + C_acc)/2 from SPICE's own curve
  and records C_min and C_acc of SPICE in `spice_regions`; here each curve, TCAD and SPICE,
  crosses its *own* C_mid, computed from its own minimum and accumulation value. That makes the
  ΔV a shift of the transition, independent of a plateau error (with SPICE's level, a 3 % plateau
  error alone would move the TCAD crossing);
- the **depletion error**, max |ΔC|/C for u_fb − 1 V < u < u_t + 1 V, is reported for every
  geometry but is not a pass/fail metric.

(cv-agreement-deviation)=

### Deviation from the design spec

The {repo}`design spec, section 5.2 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#52-technical-definition>`
sets Cgg ≤ 5 % in accumulation, depletion and inversion. Here the depletion-region 5 % is
replaced by the two ΔV crossings, deliberately. In the transition a relative-C metric measures
the slope of the curve, not whether TCAD and SPICE agree.

For the nfet W10/L10 at TT,
SPICE Cgg rises from 81.84 fF at u = 0.5 V to 143.75 fF at 0.7 V, and its slope reaches
0.513 fF/mV at 0.675 V. There C is 130.9 fF, interpolated between the 0.65 V and 0.7 V points.
So a curve shifted by only 13 mV (5 % of 130.9 fF over 0.513 fF/mV) already fails 5 %. On the
50 mV grid, with linear interpolation, the smallest whole-millivolt rigid shift that fails 5 %
at some bias is 15 mV.

A 15 mV shift is a small fraction of the {term}`corner` spread of the
crossings. For the nfet W10/L10 that spread is 252 mV (u_dep) and 249 mV (u_inv) wide (below). The deviation is
also listed on {ref}`the limitations page <limitations-spec-deviations>`.

(cv-agreement-windows)=

### Verdicts and the "Same process" windows

Each plateau and each crossing gets a {ref}`verdict <agreement-verdicts>`: {term}`Agree` within
the tolerance, else {term}`Same process` inside its window, else {term}`Disagree`; a geometry's
verdict is the worst of its four ({py:func}`~gf180tcad.calibrate.cv.verdicts`).

- A **plateau**'s window, at each plateau bias, is the {term}`combined range` of two intervals.
  One is the five-corner {term}`corner envelope` of Cgg
  ({py:func}`~gf180tcad.calibrate.cv.envelope_cv`, pure min/max of the committed cv.csv files).
  The other is the public 6 V {term}`Cox` spec, 1.8 / 2.3 / 2.8 fF/µm². Its source is the
  [GF180MCU PDK electrical specs, 5.3 Gate oxide capacitance](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/spice/elec_specs/elec_specs_5_3.html),
  rows "COX (Poly) 6V", entered in {repo}`data/pdk_elec_spec.json`. The spec is mapped to Cgg
  by the same bookkeeping as the model: Cox_min/max × LeffCV × WeffCV plus the parasitic term.
  In 2D the factor is the drawn W × L. {py:func}`gf180tcad.specwindow.window` forms the combined range and says which
  side sets it.
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
3 of 8 per device type. No value is within 1e-3 of a bound. The pfet `dv_fb_v`, +187.2 mV,
is the nearest: 13 mV inside the +200 mV bound (93.6 % of the way from 0 to it), not a bound hit by the
1e-3 rule but close to one.

{term}`nfet_05v0`:

| Parameter | Unit | Fitted | Lower bound | Upper bound |
|---|---|---|---|---|
| `t_ox_eff_nm` | nm | 16.050 | 15.2 | 16.95 |
| `n_ch_cm3` | cm⁻³ | 8.813e16 | 6.30e16 | 3.4e17 |
| `dv_fb_v` | mV | +98.7 | −200 | +200 |

{term}`pfet_05v0`:

| Parameter | Unit | Fitted | Lower bound | Upper bound |
|---|---|---|---|---|
| `t_ox_eff_nm` | nm | 15.721 | 15.6 | 16.39 |
| `n_ch_cm3` | cm⁻³ | 2.147e17 | 6.78e16 | 3.4e17 |
| `dv_fb_v` | mV | +187.2 | −200 | +200 |

How the optimiser stopped:

| Device | Stop criterion | Evaluations |
|---|---|---|
| {term}`nfet_05v0` | xtol reached | 15 |
| {term}`pfet_05v0` | ftol reached | 11 |

"Evaluations" is scipy's `nfev`, the residual evaluations of the optimiser's steps. It leaves
out the finite-difference Jacobians (`njev`: 8 for the nfet and 11 for the pfet, each 3
evaluations). So the 1D {{ DEVSIM }} sweeps number `nfev` + 3 × `njev`: 15 + 3 × 8 = 39 (nfet)
and 11 + 3 × 11 = 44 (pfet). The {term}`job`'s `progress.log` counts every one.

The `t_ox_eff_nm` upper bounds are TOXP plus the charge-centroid allowance Δ: 0.95 nm for the
nfet and 0.79 nm for the pfet, the maximum over both plateaus of the BSIM4 charge-thickness
centroid X_DC times {term}`EPSROX`/ε_si (X_DC = 2.841 nm and 2.361 nm at the plateau edges); the
calculation is on {doc}`process-data` ("The charge-centroid allowance Δ"). The fitted nfet oxide,
16.05 nm, is TOXP plus 0.05 nm; the pfet's, 15.72 nm, is TOXE plus 0.12 nm. With them the oxide's own
Cox is 2.151 and 2.197 fF/µm², and the 1D C per area at u = −5 / +5 V is 2.112 / 2.097 (nfet) and
2.149 / 2.089 fF/µm² (pfet): all inside the public 1.8–2.8 fF/µm² spec.

Per geometry, calibration and validation (held-out) together, the plateau errors, the
crossing shifts ΔV_dep and ΔV_inv, the depletion error (reported only) and the geometry's
verdict. The validation rows are {repo}`results/tcad/validation/nfet_05v0.json` and
{repo}`results/tcad/validation/pfet_05v0.json` (1D, fixed calibrated values). Accumulation and
inversion are the largest plateau errors and Depletion the depletion error, all as
|ΔCgg|/Cgg_SPICE.

**nfet_05v0**

Role and verdict:

| W (µm) | L (µm) | Role | Verdict |
|---|---|---|---|
| 10 | 10 | calibration | Agree |
| 10 | 2 | calibration | Agree |
| 10 | 1 | validation | Agree |
| 10 | 0.7 | validation | Agree |
| 10 | 0.6 | calibration | Agree |
| 1.6 | 0.7 | validation | Agree |

Plateau and depletion errors:

| W (µm) | L (µm) | Accumulation (%) | Inversion (%) | Depletion (%) |
|---|---|---|---|---|
| 10 | 10 | 0.67 | 0.63 | 12.9 |
| 10 | 2 | 0.59 | 0.57 | 6.7 |
| 10 | 1 | 0.83 | 0.50 | 7.8 |
| 10 | 0.7 | 0.75 | 0.44 | 6.4 |
| 10 | 0.6 | 0.85 | 0.41 | 5.4 |
| 1.6 | 0.7 | 0.75 | 0.44 | 5.9 |

Crossing shifts:

| W (µm) | L (µm) | ΔV_dep (mV) | ΔV_inv (mV) |
|---|---|---|---|
| 10 | 10 | +27.9 | +20.2 |
| 10 | 2 | +0.7 | -6.5 |
| 10 | 1 | -27.3 | -31.7 |
| 10 | 0.7 | -31.5 | -30.5 |
| 10 | 0.6 | -22.0 | -18.0 |
| 1.6 | 0.7 | -22.9 | -22.9 |

**pfet_05v0**

Role and verdict:

| W (µm) | L (µm) | Role | Verdict |
|---|---|---|---|
| 10 | 10 | calibration | Disagree |
| 10 | 2 | calibration | Same process |
| 10 | 1 | validation | Agree |
| 10 | 0.7 | validation | Same process |
| 10 | 0.5 | calibration | Disagree |
| 1.6 | 0.7 | validation | Same process |

Plateau and depletion errors:

| W (µm) | L (µm) | Accumulation (%) | Inversion (%) | Depletion (%) |
|---|---|---|---|---|
| 10 | 10 | 4.22 | 0.27 | 29.6 |
| 10 | 2 | 3.73 | 0.57 | 24.4 |
| 10 | 1 | 3.76 | 1.38 | 17.9 |
| 10 | 0.7 | 4.31 | 2.30 | 15.0 |
| 10 | 0.5 | 5.64 | 3.81 | 18.1 |
| 1.6 | 0.7 | 6.12 | 4.12 | 12.9 |

Crossing shifts:

| W (µm) | L (µm) | ΔV_dep (mV) | ΔV_inv (mV) |
|---|---|---|---|
| 10 | 10 | -218.1 | -11.5 |
| 10 | 2 | -128.3 | -4.2 |
| 10 | 1 | -0.2 | +8.0 |
| 10 | 0.7 | +123.8 | +19.9 |
| 10 | 0.5 | +308.6 | +40.7 |
| 1.6 | 0.7 | +131.8 | +31.8 |

Every plateau window is set by the Cox spec side of the combined range (`source` "spec" at every
plateau bias). The 1.8–2.8 fF/µm² spec is far wider than the corner envelope. So on the plateaus
"Same process" says only that the C per area is inside the PDK's 6 V oxide-capacitance spec. The crossing windows are
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
  {term}`BSIM4` {term}`card` is a property of the fitted model (`spice-fit`): in `capMod=2` the C–V flat
  band is computed from the threshold-voltage model, so the card's length dependence of {term}`Vt`
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
committed, on the committed file. It records that file's sha256 and `param_sha256`. This order
is the evidence that the held-out geometries were not in the fit.
Results at 1.6/0.7 are tagged in advance with the causes `geometry-2d` and `spice-fit`, and at
Lmin with `spice-fit`.

- **1D, held-out geometries** (W10/L0.7, W10/L1, W1.6/L0.7): the rows marked "validation" above.
  nfet: {term}`Agree` at all three. pfet: {term}`Agree` at L = 1 µm and {term}`Same process` at
  L = 0.7 µm and 1.6/0.7, both from the depletion-side crossing (+124 and +132 mV, inside the
  corner window) and, at 1.6/0.7, the accumulation plateau (6.12 %).

**2D: {term}`Disagree` at the two shortest nfet cells.** The
{repo}`nfet validation file <results/tcad/validation/nfet_05v0.json>` compares each calibrated 2D
cell with the TT ngspice Cgg. W10/L1 and W10/L2 are {term}`Same process`. The
{repo}`pfet validation file <results/tcad/validation/pfet_05v0.json>` does the same for the pfet cells.

A cell is one 2D {term}`job` with source and drain, QS, on the selected 2D mesh and the SPICE
grid ({ref}`moscap2d-calibrated`). The committed nfet cells are W10/L0.6, W10/L0.7,
W10/L1 and W10/L2. The pfet cells are W10/L0.5 and W10/L0.7. The other geometries are "not run" ([issue #35](https://github.com/mithro/gf180-tcad/issues/35)).

A plateau row is its worst difference from SPICE. At W10/L0.6, a calibration geometry of the 1D fit:

| Check | 2D | Verdict |
|---|---|---|
| Accumulation plateau (%) | 8.8 | {term}`Same process` |
| Inversion plateau (%) | 15.6 | Same process |
| Depletion crossing shift (mV) | −240 | Disagree |
| Inversion crossing shift (mV) | −49 | {term}`Agree` |

At W10/L0.7:

| Check | 2D | Verdict |
|---|---|---|
| Accumulation plateau (%) | 7.6 | Same process |
| Inversion plateau (%) | 13.8 | Same process |
| Depletion crossing shift (mV) | −202 | Disagree |
| Inversion crossing shift (mV) | −41 | Agree |

At W10/L1:

| Check | 2D | Verdict |
|---|---|---|
| Accumulation plateau (%) | 5.7 | Same process |
| Inversion plateau (%) | 10.3 | Same process |
| Depletion crossing shift (mV) | −131 | Same process |
| Inversion crossing shift (mV) | −27 | Agree |

W10/L2 is a calibration geometry of the 1D fit, run with QS only ({ref}`moscap2d-l2`).
The 1D fit is {term}`Agree` on all four checks there, so this cell is no held-out evidence.
It tests the 2D cross-section's own edge, overlap and fringe capacitance at a fitted geometry.
Its plateau gap belongs to [issue #77](https://github.com/mithro/gf180-tcad/issues/77), not to the fit. At W10/L2:

| Check | 2D | Verdict |
|---|---|---|
| Accumulation plateau (%) | 3.0 | Agree |
| Inversion plateau (%) | 5.5 | Same process |
| Depletion crossing shift (mV) | −45 | Agree |
| Inversion crossing shift (mV) | +1 | Agree |

The 2D Cgg lies below SPICE on both plateaus, by more on the inversion side. At W10/L0.6 it
is 14.12 fF at +5 V
({repo}`cv.csv <results/tcad/moscap2d/nfet_05v0/calibrated/w10p0_l0p60/cv.csv>`). The
SPICE inversion level there is 16.70 fF (`spice_regions` in the validation file). The gap
shrinks as the gate gets longer. Why the 2D Cgg is low is open ([issue #77](https://github.com/mithro/gf180-tcad/issues/77)).

**The pfet cell, W10/L0.5.** It is a calibration geometry, and the 1D fit is {term}`Disagree` there,
on the depletion crossing ({repo}`pfet calibration file <results/tcad/calibration/pfet_05v0.result.json>`).
So the 2D cell is no held-out evidence. Every 2D check is Same process:

| Check | 2D | Verdict |
|---|---|---|
| Accumulation plateau (%) | 17.6 | Same process |
| Inversion plateau (%) | 17.8 | Same process |
| Depletion crossing shift (mV) | −105 | Same process |
| Inversion crossing shift (mV) | −58 | Same process |

The plateaus are Same process because the window takes in the public 1.8–2.8 fF/µm² Cox spec.
Over the 5 µm² gate it starts at 9.0 fF, below the SPICE corners. It ends at 14.76 fF on the
accumulation side and 15.38 fF on the inversion side (`window` in the validation file).

The cell gives 11.93 fF at +5 V and 11.94 fF at −5 V
({repo}`cv.csv <results/tcad/moscap2d/pfet_05v0/calibrated/w10p0_l0p50/cv.csv>`). SPICE gives 14.26 and 14.53 fF.
The start-value 2D cell already gives 12.03 fF
({repo}`cv.csv <results/tcad/moscap2d/pfet_05v0/start/w10p0_l0p50/cv.csv>`), so the gap comes before the calibration.

**The pfet cell, W10/L0.7.** It is a {term}`held-out geometry`; the 1D validation there is {term}`Same process`,
on the depletion crossing. The 2D cell is Same process:

| Check | 2D | Verdict |
|---|---|---|
| Accumulation plateau (%) | 13.7 | Same process |
| Inversion plateau (%) | 13.0 | Same process |
| Depletion crossing shift (mV) | −117 | Same process |
| Inversion crossing shift (mV) | −6 | Agree |

The plateau window is the Cox spec over the 7 µm² gate, 12.6 to 19.6 fF.
The cell gives 16.23 fF at +5 V and 16.12 fF at −5 V
({repo}`cv.csv <results/tcad/moscap2d/pfet_05v0/calibrated/w10p0_l0p70/cv.csv>`). SPICE gives 18.52 fF on both plateaus.
The gap is smaller than at W10/L0.5, as it is for the nfet.

L = 10 µm does not solve in 2D ({doc}`/limitations/moscap2d`). This deviates from the plan
in one respect. The plan has {py:func}`~gf180tcad.calibrate.cv.validate_cv` call
`moscap2d.simulate` itself. It reads the committed calibrated 2D results instead, so each
multi-hour 2D sweep runs once and serves both the results folder and the validation.

## Reproduce

```
uv run --locked python -m gf180tcad.calibrate run --device nfet_05v0 --out results/tcad/calibration
uv run --locked python -m gf180tcad.calibrate validate --device nfet_05v0 --out results/tcad/validation
```

and the same for `pfet_05v0`. Each `run` is one {term}`sandbox` job of 1 CPU and 2 GiB. A second
run gives byte-identical files
({test}`tests/test_calibrate_cv.py::test_calibration_reproduces_the_committed_files`). The result-file schema: `<device>.json` is the
calibration file of {py:mod}`gf180tcad.tcad.calibration`, unchanged, so that `--params calibrated`
reads it; everything else is in `<device>.result.json`, which records the first file's sha256.
