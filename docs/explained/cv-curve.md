(explained-cv-curve)=

# What sets each part of the C–V curve

Which part of the stack sets each part of the {term}`C–V` curve? This page answers that for the
{term}`nfet_05v0`, for a reader who has read {doc}`accumulation-depletion-inversion`. It shows
how the fit moves the simulated curve onto the {term}`SPICE` one.

```{figure} /_generated/explained/cv-parts-light.svg
:figclass: only-light
:alt: Gate capacitance against gate voltage: a solid line, a dashed line almost on top of it, and a dotted line with higher flat ends and a shallower dip. Labels name the oxide thickness at both flat ends, the body doping at the dip and a voltage shift with a two-headed arrow on the falling side.

The gate capacitance of the nfet_05v0 at `w10p0_l10p00`. The solid line is the SPICE model at
the {term}`typical corner`. The dotted line is the simulated stack at the start values, and the
dashed line at the fitted ones. The start oxide thickness and body doping are the
{term}`model card`'s values. The start shift and the gate doping's role are described below. The
places of the labels and the length of the arrow are drawing choices.
```

```{figure} /_generated/explained/cv-parts-dark.svg
:figclass: only-dark
:alt: Gate capacitance against gate voltage: a solid line, a dashed line almost on top of it, and a dotted line with higher flat ends and a shallower dip. Labels name the oxide thickness at both flat ends, the body doping at the dip and a voltage shift with a two-headed arrow on the falling side.

The gate capacitance of the nfet_05v0 at `w10p0_l10p00`. The solid line is the SPICE model at
the {term}`typical corner`. The dotted line is the simulated stack at the start values, and the
dashed line at the fitted ones. The start oxide thickness and body doping are the
{term}`model card`'s values. The start shift and the gate doping's role are described below. The
places of the labels and the length of the arrow are drawing choices.
```

(explained-cv-curve-fit)=

## Three numbers to fit

The simulated stack has three free numbers: the oxide thickness, the body doping and a shift of
the gate voltage ({ref}`cv-agreement`). The fit searches for the values that bring the simulated
curve closest to the SPICE one. It starts from the values below and stays within limits set
beforehand ({doc}`/comparison/process-data`).

| Parameter | Start | Fitted |
|---|---|---|
| Oxide thickness | {{ x_t_ox_nfet_start }} | {{ x_t_ox_nfet_cal }} |
| Body doping | {{ x_n_ch_nfet_start }} | {{ x_n_ch_nfet_cal }} |
| Gate voltage shift | {{ x_dv_fb_nfet_start }} | {{ x_dv_fb_nfet_cal }} |

The start thickness and doping are the model card's own. The start shift is a project choice
({repo}`nfet_05v0.toml <data/process/nfet_05v0.toml>`). The fit compares the curves at
{{ x_fit_length_count }} gate lengths. It compares their flat parts, and where each curve crosses
its own halfway level ({ref}`the dip <explained-regions-dip>`).

The {term}`pfet_05v0`'s curve is the mirror image, with the signs of the gate voltages reversed
({ref}`explained-regions-three`).

(explained-cv-curve-flat)=

## The flat parts: the oxide

At both ends a layer of carriers sits right under the oxide. So the oxide alone sets the
capacitance there ({ref}`Sze and Ng, ch. 4 <lit-sze>`). The {term}`oxide capacitance <Cox>` per
area is the oxide's permittivity over its thickness, so a thicker oxide lowers both flat parts.

As idealised examples from the thickness alone, the oxide gives {{ x_cox_toxe_nfet }} at the start and
{{ x_cox_nfet_cal }} when fitted. The start curve's flat parts lie above the SPICE ones, and the
fit thickens the oxide to bring them down.

The gate is silicon too, n-type at the model card's doping. At the positive end the gate voltage
pushes its {term}`electrons <electron>` away from the oxide. That {term}`poly depletion` lowers
the {term}`inversion` flat part a little ({ref}`explained-poly`).

(explained-cv-curve-dip)=

## The dip: the body doping

In {term}`depletion` the gate pushes the {term}`holes <hole>` away from the surface. It leaves a
layer without free carriers, whose capacitance is in series with the oxide's
({ref}`explained-regions-three`). For the same bending of the bands, a lighter doping leaves a
deeper layer, with a lower capacitance ({ref}`Sze and Ng, ch. 4 <lit-sze>`). So a lighter body
doping deepens the dip.

The fit lowers the body doping from {{ x_n_ch_nfet_start }} to {{ x_n_ch_nfet_cal }}. The start
curve's dip is shallower than the SPICE one, and the fitted curve's dip meets it.

The doping also moves the start of inversion. The {term}`threshold voltage` rises with the body
doping, because the gate must deplete a layer holding more {term}`acceptors <acceptor>` first
({ref}`Sze and Ng, ch. 4 <lit-sze>`).

(explained-cv-curve-shift)=

## The position: the voltage shift

The gate and body dopings set the gate voltage of {term}`flat band`, where the curve starts to
fall ({ref}`explained-regions-bands`). The fitted shift stands for what those dopings leave out
({ref}`cv-agreement`). One part is the gate's error from counting its carriers with
{term}`Boltzmann statistics`. The others are the SPICE model's own flat band and any charge at
the oxide face.

The simulation solves the stack at the gate voltage minus the shift
({repo}`per_area.meta.json <results/tcad/moscap1d/nfet_05v0/calibrated/per_area.meta.json>`).
So the nfet's whole curve slides to more positive gate voltages by {{ x_dv_fb_nfet_cal }}, with
its shape unchanged. At its true length that shift is too short to see in the figure, so the
arrow shows only its direction.

(explained-cv-curve-differs)=

## Where this repo's results differ

At `w10p0_l10p00` the fitted flat parts lie within {{ x_plateau_acc_l10 }} and
{{ x_plateau_inv_l10 }} of the SPICE curve. The allowed error is {{ x_plateau_tol_l10 }}. The
halfway-level crossings differ by {{ x_dv_dep_l10 }} on the falling side and {{ x_dv_inv_l10 }} on
the rising side, simulated minus SPICE. The allowed difference is {{ x_dv_tol_l10 }}
({repo}`nfet_05v0.result.json <results/tcad/calibration/nfet_05v0.result.json>`).

Between the flat parts the two curves differ by up to {{ x_depletion_l10 }}. The simulation
solves the stack at rest at each gate voltage, the {term}`quasi-static` curve
({py:mod}`gf180tcad.tcad.moscap1d`). The SPICE curve comes from the equations of
{term}`BSIM4`'s capacitance model instead ({ref}`BSIM4 manual, ch. 7 <lit-bsim4>`). Where the
curve is steep, a small shift gives a large relative error, so the checks leave the dip out
({ref}`the deviation <cv-agreement-deviation>`).

The 1D fit is {{ x_verdict_nfet_1d }} for the nfet and {{ x_verdict_pfet_1d }} for the pfet
({ref}`the pfet mismatch <cv-agreement-mismatch>`). The pfet's SPICE curve leaves accumulation
at a gate voltage that moves with the gate length. One simulated stack has one flat band for
every length.

{{ x_two_d_disagree }} ([issue #108](https://github.com/mithro/gf180-tcad/issues/108)). The
checks of each 2D cell are on {ref}`cv-agreement-validation`.
