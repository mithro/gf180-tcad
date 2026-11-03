(explained-calibration)=

# What the calibration changes

What does the calibration change, and what does it leave alone? This page answers that for the
{term}`nfet_05v0` and the {term}`pfet_05v0`, for a reader who has read {doc}`cv-curve`. It shows
the three fitted numbers, what stays fixed and their bounds over the {term}`corners <corner>`.
{numref}`fig-calibration-stack` shows the stack the fit changes.

```{figure} /_generated/explained/calibration-stack-light.svg
:figclass: only-light
:name: fig-calibration-stack
:alt: Three stacked layers: a muted gate on top, a thin shaded oxide below it and a tall shaded body at the bottom, each labelled with its material, thickness and doping.

The 1D stack of the nfet_05v0: the gate on top, the {term}`gate oxide` and the body. The fit
changes the two shaded layers. The oxide thickness and the body doping are fitted to the
{term}`SPICE` model. The gate doping is the {term}`model card`'s value, and the gate and body
depths are project choices. {{ x_fig_calibration_stack_scale }}
```

```{figure} /_generated/explained/calibration-stack-dark.svg
:figclass: only-dark
:alt: Three stacked layers: a muted gate on top, a thin shaded oxide below it and a tall shaded body at the bottom, each labelled with its material, thickness and doping.

The 1D stack of the nfet_05v0: the gate on top, the {term}`gate oxide` and the body. The fit
changes the two shaded layers. The oxide thickness and the body doping are fitted to the
{term}`SPICE` model. The gate doping is the {term}`model card`'s value, and the gate and body
depths are project choices. {{ x_fig_calibration_stack_scale }}
```

(explained-calibration-fitted)=

## Three numbers, each within limits

The calibration fits three numbers of the simulated stack: the oxide thickness, the body doping
and a shift of the gate voltage ({ref}`explained-cv-curve-fit`). The fit moves them until the
simulated {term}`C–V` curve comes closest to the SPICE one. Each number stays between two
limits, set before the fit. {numref}`fig-calibration-limits` shows each number within its limits.

```{figure} /_generated/explained/calibration-limits-light.svg
:figclass: only-light
:name: fig-calibration-limits
:alt: Three panels, one per fitted number: oxide thickness, body doping on a log axis and gate voltage shift. Each has a grey bar per transistor between two tick marks, an open circle at the start and a filled diamond at the fitted value.

Each fitted number of both transistors on its own axis. The bar runs between the two limits.
The open circle is the start value. The diamond is the value fitted to the SPICE model at the
{term}`typical corner`. The starts and limits are model-card values or project choices, as the
table in the next section says.
```

```{figure} /_generated/explained/calibration-limits-dark.svg
:figclass: only-dark
:alt: Three panels, one per fitted number: oxide thickness, body doping on a log axis and gate voltage shift. Each has a grey bar per transistor between two tick marks, an open circle at the start and a filled diamond at the fitted value.

Each fitted number of both transistors on its own axis. The bar runs between the two limits.
The open circle is the start value. The diamond is the value fitted to the SPICE model at the
{term}`typical corner`. The starts and limits are model-card values or project choices, as the
table in the next section says.
```

The nfet's numbers
({repo}`nfet_05v0.result.json <results/tcad/calibration/nfet_05v0.result.json>`):

{{ x_fit_table_nfet }}

The pfet's numbers
({repo}`pfet_05v0.result.json <results/tcad/calibration/pfet_05v0.result.json>`):

{{ x_fit_table_pfet }}

{{ x_bound_hits }}. A value on its limit would show the fit pressing against that limit
({ref}`cv-agreement`).

(explained-calibration-limits)=

## Where the starts and limits come from

The {term}`model card` is the {term}`PDK`'s SPICE description of the transistor. Each start and
limit of {numref}`fig-calibration-limits` is a model-card value, derived from one, or a project
choice. The {term}`process files <process file>` record which
({repo}`nfet_05v0.toml <data/process/nfet_05v0.toml>`,
{repo}`pfet_05v0.toml <data/process/pfet_05v0.toml>`; {ref}`the tunables <process-data-tunables>`).
The two transistors share this table:

{{ x_limit_kinds_table }}

- The oxide starts at its lower limit, the card's electrical oxide thickness. That is the
  thickness most of the model's equations use ({ref}`BSIM4.5.0 manual, §1.1 <lit-bsim4>`).
- The oxide's upper limit is the physical oxide thickness plus an allowance for charge that sits
  a little below the surface. The physical thickness is that of the layer itself. For the nfet
  the limit is {{ x_toxp_nfet }} plus {{ x_delta_nfet }}, so {{ x_t_ox_upper_nfet }}
  ({ref}`BSIM4.5.0 manual, ch. 7 <lit-bsim4>`).
- The nfet card sets a physical oxide thickness. The pfet card sets none, so the {term}`BSIM4` default
  applies, equal to the electrical one ({ref}`BSIM4.5.0 manual, appendix A <lit-bsim4>`).
- The body doping starts at the card's channel doping. Its lower limit is half the doping
  that the card's {term}`body effect` coefficient implies. Its upper limit is twice the start.
  Both factors, the half and the twice, are project choices.
- The shift starts at zero, so the two dopings alone set the {term}`flat band`.

(explained-calibration-fixed)=

## What stays fixed

The fit changes nothing else. These stay as the model card gives them, or as this project chose
them. {numref}`fig-calibration-cell` shows the gate whose area they
scale to.

```{figure} /_generated/explained/moscap-cell-light.svg
:figclass: only-light
:name: fig-calibration-cell
:alt: Cross-section of the transistor: the gate, the thin gate oxide and the tall body below them in colour, the source and the drain either side in grey, with dark contact bars on the gate, the source, the drain and the bottom of the body.

The 2D cell `w10p0_l0p70` of the nfet_05v0. The 1D stack is the column under the gate, in
colour. The column gives a capacitance per area. Fixed card terms scale it to the
gate's whole length and width and add the overlap at the gate's ends. The fit compares this scaled
gate capacitance, in fF. The junction depth is the
model card's value. The gate and body depths and the source and drain width are project
choices. {{ x_fig_moscap_cell_scale }}
```

```{figure} /_generated/explained/moscap-cell-dark.svg
:figclass: only-dark
:alt: Cross-section of the transistor: the gate, the thin gate oxide and the tall body below them in colour, the source and the drain either side in grey, with dark contact bars on the gate, the source, the drain and the bottom of the body.

The 2D cell `w10p0_l0p70` of the nfet_05v0. The 1D stack is the column under the gate, in
colour. The column gives a capacitance per area. Fixed card terms scale it to the
gate's whole length and width and add the overlap at the gate's ends. The fit compares this scaled
gate capacitance, in fF. The junction depth is the
model card's value. The gate and body depths and the source and drain width are project
choices. {{ x_fig_moscap_cell_scale }}
```

- The gate doping ({term}`NGATE`), the oxide's permittivity ({term}`EPSROX`) and the
  temperature: model-card values.
- The terms that turn a capacitance per area into the gate's. These are the card's length and
  width offsets ({term}`DLC`, {term}`DWC`, {term}`XL`, {term}`XW`) and its overlap capacitances.
- The target: the SPICE curve at the typical corner, at {{ x_fit_length_count }} gate lengths.
  Other gate lengths are kept back to check the fit ({term}`held-out geometry`).
- The mesh and the voltage steps: project choices ({ref}`mesh-convergence`).

Each transistor's fit uses {{ x_budget_used }} of the {{ x_budget }} numbers its
{term}`parameter budget <calibrated parameter budget>` allows.

(explained-calibration-search)=

## How the fit searches

The fit compares the curves on their flat parts and at their halfway-level crossings
({ref}`the dip <explained-regions-dip>`). {numref}`fig-calibration-compare` marks both on the
nfet's longest gate.

```{figure} /_generated/explained/calibration-compare-light.svg
:figclass: only-light
:name: fig-calibration-compare
:alt: Gate capacitance against gate voltage: a solid and a dashed curve almost on top of each other, both ends shaded, and a ring with a diamond inside on each side of the dip.

What the fit compares on the nfet_05v0 at `w10p0_l10p00`. The solid line is the SPICE model at
the typical corner, the dashed line the simulated stack with its fitted values. The shading
marks the flat parts' voltage steps, read from
{repo}`nfet_05v0.result.json <results/tcad/calibration/nfet_05v0.result.json>`. The rings mark the SPICE
crossings and the diamonds the simulated ones.
```

```{figure} /_generated/explained/calibration-compare-dark.svg
:figclass: only-dark
:alt: Gate capacitance against gate voltage: a solid and a dashed curve almost on top of each other, both ends shaded, and a ring with a diamond inside on each side of the dip.

What the fit compares on the nfet_05v0 at `w10p0_l10p00`. The solid line is the SPICE model at
the typical corner, the dashed line the simulated stack with its fitted values. The shading
marks the flat parts' voltage steps, read from
{repo}`nfet_05v0.result.json <results/tcad/calibration/nfet_05v0.result.json>`. The rings mark the SPICE
crossings and the diamonds the simulated ones.
```

A {term}`least-squares fit` finds the three values that make the cost
{math:numref}`eq-calibration-cost` smallest
({py:meth}`~gf180tcad.calibrate.cv.Metrics.residuals`):

$$
F=\tfrac{1}{2}\sum_{g}\Big[\sum_{V}r_C(V)^2+r_{\mathrm{dep}}^2+r_{\mathrm{inv}}^2\Big]
$$ (eq-calibration-cost)

where

- $F$ is the cost, dimensionless;
- $g$ is one of the fit's {{ x_fit_length_count }} gate lengths, in µm;
- $V$ is one voltage step of the two flat parts, in V;
- $r_C(V)$ is the relative error {math:numref}`eq-calibration-rc` at $V$, dimensionless;
- $r_{\mathrm{dep}}$ and $r_{\mathrm{inv}}$ are the scaled crossing gaps
  {math:numref}`eq-calibration-gap`, dimensionless.

Each relative error compares the simulated gate capacitance with the SPICE one:

$$
r_C(V)=\frac{C_{\mathrm{sim}}(V)-C_{\mathrm{SPICE}}(V)}{C_{\mathrm{SPICE}}(V)}
$$ (eq-calibration-rc)

where

- $r_C(V)$ is the relative error at $V$, dimensionless;
- $V$ is the gate voltage, in V;
- $C_{\mathrm{sim}}(V)$ is the simulated gate capacitance, in fF;
- $C_{\mathrm{SPICE}}(V)$ is the SPICE gate capacitance, in fF.

Each crossing gap is scaled by the allowed gap:

$$
r_{s}=\frac{\Delta V_{s}}{\Delta V_{\mathrm{tol}}},\quad s\in\{\mathrm{dep},\mathrm{inv}\}
$$ (eq-calibration-gap)

where

- $r_{s}$ is the scaled gap on side $s$, dimensionless;
- $s$ is the side of the dip, dep the falling one and inv the rising one, dimensionless;
- $\Delta V_{s}$ is the simulated minus the SPICE crossing voltage on side $s$, in V;
- $\Delta V_{\mathrm{tol}}$ is the allowed gap of {{ x_dv_tol_l10 }}, in mV.

Each evaluation solves the stack once and compares it at every fit gate length. The search
counted {{ x_nfev_nfet }} evaluations for the nfet and {{ x_nfev_pfet }} for the pfet. The count
leaves out the extra solves that measure how each number moves the curve
([scipy's `least_squares` manual](https://docs.scipy.org/doc/scipy-1.18.0/reference/generated/scipy.optimize.least_squares.html)).

(explained-calibration-corners)=

## What the corners give

The SPICE reference runs {{ x_corner_count }} {term}`corners <corner>`, the typical one among
them. A corner fit repeats the calibration against one other corner's SPICE curves. It takes that
corner's model-card offsets of the gate area, the overlaps, the oxide and the threshold as fixed
inputs ({ref}`reproduce-corners`). Over the {{ x_corner_count }} fits, each fitted number gets a
lowest and a highest value. The spread is the highest minus the lowest.
{numref}`fig-calibration-bounds` shows them.

```{figure} /_generated/explained/corner-bounds-light.svg
:figclass: only-light
:name: fig-calibration-bounds
:alt: Three panels, one per fitted number: oxide thickness, body doping on a log axis and gate voltage shift. Each has a grey bar per transistor from its lowest to its highest value, four triangles for the corner fits and a filled diamond at the typical fit.

Each fitted number of both transistors over the corners. The grey bar runs from the lowest to the
highest value. The triangles are the fits at the four other corners, ff and ss in colour. The
diamond is the typical fit. Read from the corner summaries
({repo}`nfet_05v0 <results/tcad/corners/nfet_05v0/summary.json>`,
{repo}`pfet_05v0 <results/tcad/corners/pfet_05v0/summary.json>`).
```

```{figure} /_generated/explained/corner-bounds-dark.svg
:figclass: only-dark
:alt: Three panels, one per fitted number: oxide thickness, body doping on a log axis and gate voltage shift. Each has a grey bar per transistor from its lowest to its highest value, four triangles for the corner fits and a filled diamond at the typical fit.

Each fitted number of both transistors over the corners. The grey bar runs from the lowest to the
highest value. The triangles are the fits at the four other corners, ff and ss in colour. The
diamond is the typical fit. Read from the corner summaries
({repo}`nfet_05v0 <results/tcad/corners/nfet_05v0/summary.json>`,
{repo}`pfet_05v0 <results/tcad/corners/pfet_05v0/summary.json>`).
```

The nfet's bounds and spread
({repo}`summary.json <results/tcad/corners/nfet_05v0/summary.json>`):

{{ x_corner_bounds_table_nfet }}

The pfet's bounds and spread
({repo}`summary.json <results/tcad/corners/pfet_05v0/summary.json>`):

{{ x_corner_bounds_table_pfet }}

The corner of each lowest and highest value:

{{ x_corner_extremes_table }}

{{ x_corner_bound_hits }}. What the corner fits leave out is on {doc}`/limitations/corners`.

The spread of the target itself is committed. {numref}`fig-calibration-corners` shows it as the
grey band round the typical SPICE curve.

```{figure} /_generated/explained/moscap-cv-light.svg
:figclass: only-light
:name: fig-calibration-corners
:alt: Gate capacitance against gate voltage: high and flat at both ends, a deep dip a little above zero volts, with a solid line inside a grey band and a dashed line lying almost on top of the solid one.

The gate capacitance of the nfet_05v0 at `w10p0_l10p00`. The solid line is the SPICE model at
the typical corner, and the grey band spans its {{ x_corner_count }} corners. The dashed line
is the simulated stack, with the oxide thickness, body doping and voltage shift fitted to the
typical corner.
```

```{figure} /_generated/explained/moscap-cv-dark.svg
:figclass: only-dark
:alt: Gate capacitance against gate voltage: high and flat at both ends, a deep dip a little above zero volts, with a solid line inside a grey band and a dashed line lying almost on top of the solid one.

The gate capacitance of the nfet_05v0 at `w10p0_l10p00`. The solid line is the SPICE model at
the typical corner, and the grey band spans its {{ x_corner_count }} corners. The dashed line
is the simulated stack, with the oxide thickness, body doping and voltage shift fitted to the
typical corner.
```

Over the corners, the curve's flat parts in {term}`accumulation` and {term}`inversion` and its
crossings span these values. The flat parts come from
{repo}`envelope.json <results/spice/envelope.json>`, the crossings from
{repo}`nfet_05v0.result.json <results/tcad/calibration/nfet_05v0.result.json>`:

{{ x_corner_table }}

The flat parts follow the oxide, and the crossings follow the doping and the shift
({ref}`explained-cv-curve`). A simulated crossing that misses the allowed gap but lies inside
this spread is {term}`Same process` ({ref}`the windows <cv-agreement-windows>`).

(explained-calibration-differs)=

## Where this repo's results differ

The fit tunes {{ x_budget_used }} numbers of one 1D stack, the same for every gate length. Each
fit gate length gets its own {ref}`verdict <agreement-verdicts>`:

{{ x_fit_verdict_table }}

The pfet's whole fit is {{ x_verdict_pfet_1d_term }}. {numref}`fig-calibration-pfet` shows the pfet
at its shortest and longest fit gates.

```{figure} /_generated/explained/calibration-pfet-light.svg
:figclass: only-light
:name: fig-calibration-pfet
:alt: Two panels of gate capacitance against gate voltage, for the pfet's shortest and longest fit gates, each with a solid line in a grey band and a dashed line.

The gate capacitance of the pfet_05v0 at its shortest and longest fit gates, against the true
gate voltage. The solid line is the SPICE model at the typical corner, inside the band of all
its corners. The dashed line is the simulated stack with the values fitted to the typical corner.
The dotted lines mark where the SPICE curve leaves accumulation at each length, and the arrow
gives the shift between them.
```

```{figure} /_generated/explained/calibration-pfet-dark.svg
:figclass: only-dark
:alt: Two panels of gate capacitance against gate voltage, for the pfet's shortest and longest fit gates, each with a solid line in a grey band and a dashed line.

The gate capacitance of the pfet_05v0 at its shortest and longest fit gates, against the true
gate voltage. The solid line is the SPICE model at the typical corner, inside the band of all
its corners. The dashed line is the simulated stack with the values fitted to the typical corner.
The dotted lines mark where the SPICE curve leaves accumulation at each length, and the arrow
gives the shift between them.
```

The pfet's SPICE curve leaves accumulation at a gate voltage that moves with the gate length.
One stack has one flat band for every length, so it cannot follow that
({ref}`the pfet mismatch <cv-agreement-mismatch>`).

The 2D cells reuse the 1D fit unchanged. {{ x_two_d_disagree }}
([issue #108](https://github.com/mithro/gf180-tcad/issues/108)). The checks of each 2D cell are on
{ref}`cv-agreement-validation`.
