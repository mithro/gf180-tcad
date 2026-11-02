(explained-moscap)=

# The MOS capacitor

What is a {term}`MOS capacitor <MOSCAP>`, and why does this project simulate it before the transistor? This page
answers that for a reader who knows basic circuits and has read {doc}`oxide-and-poly`. It leaves
out why the capacitance changes with the gate voltage.

```{figure} /_generated/explained/moscap-cell-light.svg
:figclass: only-light
:alt: Cross-section of the transistor: the gate, the thin gate oxide and the tall body below them in colour, the source and the drain either side in grey, with dark contact bars on the gate, the source, the drain and the bottom of the body.

The 2D cell `w10p0_l0p70` of the {term}`nfet_05v0`. The 1D stack is the column under the
gate: the gate, the {term}`gate oxide` and the body, in colour. The source and the drain, muted,
are the parts the MOS capacitor leaves out. The oxide thickness and the body doping are fitted
to the {term}`SPICE` model. The junction depth is the {term}`model card`'s value. The gate and
body depths are project choices. The source and drain widths come from the cell's
{ref}`reduced mesh artefact <moscap2d-mesh-artefact>`. {{ x_fig_moscap_cell_scale }}
```

```{figure} /_generated/explained/moscap-cell-dark.svg
:figclass: only-dark
:alt: Cross-section of the transistor: the gate, the thin gate oxide and the tall body below them in colour, the source and the drain either side in grey, with dark contact bars on the gate, the source, the drain and the bottom of the body.

The 2D cell `w10p0_l0p70` of the {term}`nfet_05v0`. The 1D stack is the column under the
gate: the gate, the {term}`gate oxide` and the body, in colour. The source and the drain, muted,
are the parts the MOS capacitor leaves out. The oxide thickness and the body doping are fitted
to the {term}`SPICE` model. The junction depth is the {term}`model card`'s value. The gate and
body depths are project choices. The source and drain widths come from the cell's
{ref}`reduced mesh artefact <moscap2d-mesh-artefact>`. {{ x_fig_moscap_cell_scale }}
```

(explained-moscap-stack)=

## A transistor without its source and drain

MOS stands for metal, oxide and semiconductor, the three layers of the stack
({ref}`Sze and Ng, ch. 4 <lit-sze>`). Here the "metal" is the {term}`poly-silicon` gate, the
oxide is silicon dioxide and the semiconductor is the silicon body. The stack is the middle of a
transistor, with the source and the drain left out.

The gate and the body are the two plates of a capacitor, and the oxide is the insulator between
them ({ref}`Taur and Ning, ch. 4 <lit-taur>`). This repo's 1D
MOS capacitor is one column through that stack. It has a contact on the top of
the gate and one on the bottom of the body ({py:mod}`gf180tcad.tcad.moscap1d`).

(explained-moscap-cgg)=

## The gate capacitance

A capacitance is the charge a capacitor takes for each volt across it. The gate capacitance
{term}`Cgg` is that ratio for a small change of the gate voltage, with the body held at zero
volts ({ref}`Sze and Ng, ch. 4 <lit-sze>`). Its curve against the gate voltage is the
{term}`C–V` curve.

```{figure} /_generated/explained/moscap-cv-light.svg
:figclass: only-light
:alt: Gate capacitance against gate voltage: high and flat at both ends, a deep dip just above zero volts, with a solid line inside a grey band and a dashed line lying almost on top of the solid one.

The gate capacitance of the nfet_05v0 at `w10p0_l10p00`. The solid line is the {term}`PDK`'s
SPICE model at the {term}`typical corner`, and the grey band spans its {{ x_corner_count }}
{term}`corners <corner>`. The dashed line is
the simulated stack, with the oxide thickness, body doping and voltage shift fitted to the SPICE
model.
```

```{figure} /_generated/explained/moscap-cv-dark.svg
:figclass: only-dark
:alt: Gate capacitance against gate voltage: high and flat at both ends, a deep dip just above zero volts, with a solid line inside a grey band and a dashed line lying almost on top of the solid one.

The gate capacitance of the nfet_05v0 at `w10p0_l10p00`. The solid line is the {term}`PDK`'s
SPICE model at the {term}`typical corner`, and the grey band spans its {{ x_corner_count }}
{term}`corners <corner>`. The dashed line is
the simulated stack, with the oxide thickness, body doping and voltage shift fitted to the SPICE
model.
```

At both ends the curve is flat, and between them it dips ({ref}`the dip <explained-regions-dip>`). At the most negative gate voltage the SPICE model gives
{{ x_cgg_acc_l10 }} for this gate. At the most positive it gives {{ x_cgg_inv_l10 }}
({repo}`metrics.json <results/spice/ngspice/typical/nfet_05v0/w10p0_l10p00/metrics.json>`).
Under the gate, the ceiling is the {term}`oxide capacitance <Cox>` times the gate's area
({ref}`Sze and Ng, ch. 4 <lit-sze>`). The SPICE model adds the overlap capacitance to it
({ref}`explained-moscap-area`).

(explained-moscap-first)=

## Why this project simulates it first

The oxide is an insulator, so no current flows through the stack. The simulation solves it at
rest, with the body at zero volts ({py:mod}`gf180tcad.tcad.moscap1d`). Its capacitance is then
set by the oxide and by the doping of the gate and the body ({ref}`Sze and Ng, ch. 4 <lit-sze>`).

So the stack is where this repo fits the oxide thickness, the body doping and a shift of the
gate voltage. The fitted shift is {{ x_dv_fb_nfet_cal }} for the nfet
({repo}`nfet_05v0.json <results/tcad/calibration/nfet_05v0.json>`). The fit matches the
simulated gate capacitance to the SPICE model's at {{ x_fit_length_count }} gate lengths
({ref}`cv-agreement`). The fitted values are then held fixed and checked at gate
lengths the fit did not use.

(explained-moscap-area)=

## From one column to a whole gate

The 1D simulation gives the capacitance of one square micrometre of the stack. For capacitance,
the SPICE model uses its own effective length and width of the gate. It adds the capacitance
where the gate overlaps the source and the drain ({ref}`BSIM4 manual, §7.1 <lit-bsim4>`).

This repo multiplies the simulated capacitance per area by that effective area. It then adds the
same overlap terms, with the model card's values
({py:meth}`~gf180tcad.tcad.moscap1d.MoscapCV.area_scaled`). The dashed line in the figure is
that sum.

(explained-moscap-differs)=

## Where this repo's results differ

At `w10p0_l10p00` the simulated curve lies within {{ x_plateau_acc_l10 }} of the SPICE curve at
the most negative gate voltage. At the most positive it lies within {{ x_plateau_inv_l10 }}. The allowed error is
{{ x_plateau_tol_l10 }} ({repo}`nfet_05v0.result.json <results/tcad/calibration/nfet_05v0.result.json>`).

A verdict says whether the simulation matches the SPICE model: {term}`Agree`,
{term}`Same process` or {term}`Disagree` ({ref}`the verdicts <agreement-verdicts>`). Each check
of a curve gets a verdict ({ref}`the checks <cv-agreement-metric>`). A geometry's verdict is the
worst of them ({ref}`the verdict rule <cv-agreement-windows>`).

The 1D fit is {{ x_verdict_nfet_1d }} for the nfet and {{ x_verdict_pfet_1d }} for the
{term}`pfet_05v0` ({ref}`the pfet mismatch <cv-agreement-mismatch>`).

The 2D simulation of a whole cell uses the fitted stack of its transistor. The table lists every
2D cell with a verdict ({ref}`cv-agreement-validation`).

{{ x_two_d_table }}

{{ x_two_d_disagree }} ([issue #108](https://github.com/mithro/gf180-tcad/issues/108)). The halfway level is
defined with {ref}`the dip <explained-regions-dip>`. The 2D cell and its other
differences are on {doc}`/limitations/moscap2d`.
