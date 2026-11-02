(explained-calibration)=

# What the calibration changes

What does the calibration change, and what does it leave alone? This page answers that for the
{term}`nfet_05v0` and the {term}`pfet_05v0`, for a reader who has read {doc}`cv-curve`. It shows
the three fitted numbers within their limits, what stays fixed and what the
{term}`corners <corner>` add.

```{figure} /_generated/explained/calibration-limits-light.svg
:figclass: only-light
:alt: Three panels, one per fitted number: oxide thickness, body doping on a log axis and gate voltage shift. Each has a grey bar per transistor between two tick marks, an open circle at the start and a green diamond at the fitted value.

Each fitted number of both transistors on its own axis. The bar runs between the two limits.
The open circle is the start value. The diamond is the value fitted to the {term}`SPICE` model
at the {term}`typical corner`. The starts and limits are model-card values or project choices,
as the second table says.
```

```{figure} /_generated/explained/calibration-limits-dark.svg
:figclass: only-dark
:alt: Three panels, one per fitted number: oxide thickness, body doping on a log axis and gate voltage shift. Each has a grey bar per transistor between two tick marks, an open circle at the start and a green diamond at the fitted value.

Each fitted number of both transistors on its own axis. The bar runs between the two limits.
The open circle is the start value. The diamond is the value fitted to the {term}`SPICE` model
at the {term}`typical corner`. The starts and limits are model-card values or project choices,
as the second table says.
```

(explained-calibration-fitted)=

## Three numbers, each within limits

The calibration fits three numbers of the simulated stack: the oxide thickness, the body doping
and a shift of the gate voltage ({ref}`explained-cv-curve-fit`). The fit moves them until the
simulated {term}`C–V` curve comes closest to the SPICE one. Each number stays between two
limits, set before the fit.

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
limit is a model-card value, derived from one, or a project choice
({ref}`the tunables <process-data-tunables>`). The two transistors share this table:

{{ x_limit_kinds_table }}

- The oxide starts at the card's electrical oxide thickness, its lower limit. The upper limit is
  the card's physical oxide thickness plus an allowance for charge that sits a little below the
  surface ({ref}`BSIM4 manual, ch. 7 <lit-bsim4>`).
- The body doping starts at the card's channel doping. Its lower limit is half the doping
  that the card's {term}`body effect` coefficient implies. Its upper limit is twice the start.
- The shift starts at zero, so the two dopings alone set the {term}`flat band`.

(explained-calibration-fixed)=

## What stays fixed

The fit changes nothing else. These stay as the model card gives them, or as this project chose
them ({repo}`nfet_05v0.toml <data/process/nfet_05v0.toml>`):

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
({ref}`the dip <explained-regions-dip>`). On a flat part it takes the relative error at each
voltage step. At a crossing it takes the voltage gap over the allowed gap, {{ x_dv_tol_l10 }}.

A {term}`least-squares fit` finds the three values that make the sum of these differences,
squared, smallest. Each evaluation solves the stack once and compares it at every fit gate length.
The search counted {{ x_nfev_nfet }} evaluations for the nfet and {{ x_nfev_pfet }} for the pfet.
The count leaves out the extra solves that measure how each number moves the curve
([scipy's `least_squares` manual](https://docs.scipy.org/doc/scipy-1.18.0/reference/generated/scipy.optimize.least_squares.html)).

(explained-calibration-corners)=

## What the corners give

The PDK's SPICE model has {{ x_corner_count }} {term}`corners <corner>`, the typical one among
them. This repo fits the typical corner alone, so this page shows no lower or upper bound of a
fitted number. Fits at the other corners give those bounds and the spread
(issues [#57](https://github.com/mithro/gf180-tcad/issues/57) and [#121](https://github.com/mithro/gf180-tcad/issues/121)).

The spread of the target itself is committed. Over the corners, the SPICE curve of the nfet at
`w10p0_l10p00` spans these values. Its flat parts in {term}`accumulation` and {term}`inversion`
come from {repo}`envelope.json <results/spice/envelope.json>`, the crossings from the nfet's
result file:

{{ x_corner_table }}

The flat parts follow the oxide, and the crossings follow the doping and the shift
({ref}`explained-cv-curve`). A simulated crossing that misses the allowed gap but lies inside
this spread is {term}`Same process` ({ref}`the windows <cv-agreement-windows>`).

(explained-calibration-differs)=

## Where this repo's results differ

The fit tunes {{ x_budget_used }} numbers of one 1D stack, the same for every gate length. Each
fit gate length gets its own {ref}`verdict <agreement-verdicts>`:

{{ x_fit_verdict_table }}

The pfet's whole fit is {{ x_verdict_pfet_1d }}. Its SPICE curve leaves {term}`accumulation` at a
gate voltage that moves with the gate length. One stack cannot follow that
({ref}`the pfet mismatch <cv-agreement-mismatch>`).

The 2D cells reuse the 1D fit unchanged. {{ x_two_d_disagree }}
([issue #108](https://github.com/mithro/gf180-tcad/issues/108)). The checks of each 2D cell are on
{ref}`cv-agreement-validation`.
