(explained-oxide)=

# Gate oxide and poly-silicon

What are the {term}`gate oxide` and the {term}`poly-silicon` gate of this project's transistors,
and why do their thickness and doping matter? This page answers that for a reader who knows basic
circuits and has read {doc}`silicon-and-carriers`. It leaves out what the silicon under the oxide
does as the gate voltage changes.

```{figure} /_generated/explained/oxide-stack-light.svg
:figclass: only-light
:alt: Three stacked layers: a shaded gate on top, a thin shaded oxide below it and a tall muted body at the bottom, each labelled with its material, thickness and doping.

The layers of the {term}`nfet_05v0`: the gate and the {term}`gate oxide` shaded, the body
muted. The oxide thickness and the body doping are fitted to the {term}`SPICE` model. The gate
doping is the {term}`model card`'s value, and the gate and body depths are project choices.
{{ x_fig_oxide_stack_scale }}
```

```{figure} /_generated/explained/oxide-stack-dark.svg
:figclass: only-dark
:alt: Three stacked layers: a shaded gate on top, a thin shaded oxide below it and a tall muted body at the bottom, each labelled with its material, thickness and doping.

The layers of the {term}`nfet_05v0`: the gate and the {term}`gate oxide` shaded, the body
muted. The oxide thickness and the body doping are fitted to the {term}`SPICE` model. The gate
doping is the {term}`model card`'s value, and the gate and body depths are project choices.
{{ x_fig_oxide_stack_scale }}
```

(explained-oxide-capacitor)=

## A capacitor with silicon plates

The gate, the gate oxide and the body form a capacitor, with the gate and the body underneath
as its plates. The oxide between them is the insulator
({ref}`Taur and Ning, the chapter on MOS capacitors <lit-taur>`). A voltage on the gate draws
charge into the silicon under the oxide. That charge lets the gate switch the transistor
({ref}`Taur and Ning, the chapter on MOSFETs <lit-taur>`). This repo simulates the stack on its
own, without a source or drain, as a {term}`MOS capacitor <MOSCAP>`.

(explained-oxide-layer)=

## The oxide

The gate oxide is silicon dioxide, an insulator, and the model card gives its thickness in two
forms ({repo}`data/process/nfet_05v0.toml`). TOXE, the electrical thickness, is {{ x_toxe_nfet }}.
Most of the model's equations use it, the {term}`threshold voltage <Vt>` among them
({ref}`BSIM4 manual, §1.1 <lit-bsim4>`). TOXP, the physical thickness of the layer, is
{{ x_toxp_nfet }}. The model adds the depth of the charge to it when it computes the gate
capacitance ({ref}`BSIM4 manual, §1.1 <lit-bsim4>`).

The oxide's relative permittivity, {term}`EPSROX`, is {{ x_epsrox_nfet }}. At the same voltage,
a capacitor with this oxide holds that many times the charge of a vacuum gap as thick
({ref}`Sze and Ng, ch. 4 <lit-sze>`).

(explained-oxide-cox)=

## Oxide capacitance

A thinner oxide puts the plates closer, so the gate holds more charge for each volt. The
capacitance per area of the oxide alone is {term}`Cox`. Three quantities set it: the oxide's
permittivity $\varepsilon_{ox}$, that of vacuum $\varepsilon_0$, and the thickness $t_{ox}$
({ref}`Sze and Ng, ch. 4 <lit-sze>`).

$$
C_{ox} = \frac{\varepsilon_{ox} \, \varepsilon_0}{t_{ox}}
$$

With TOXE, Cox is {{ x_cox_toxe_nfet }}, an idealised example from the card's values. This
repo's calibration ({ref}`cv-agreement`) adjusts three parameters until the simulated gate
capacitance matches the SPICE model's. It sets the oxide to {{ x_t_ox_nfet_cal }}.

That thickness gives a Cox of {{ x_cox_nfet_cal }}, an idealised example from the calibrated
value. The calibration result
({repo}`nfet_05v0.result.json <results/tcad/calibration/nfet_05v0.result.json>`) records the
same {{ x_cox_check_nfet }}. The {term}`PDK` gives {{ x_cox_spec_min }} to {{ x_cox_spec_max }} in
the row `COX (Poly) 6V` of its
[gate oxide capacitance table](https://github.com/fossi-foundation/gf180mcu-pdk/blob/25ed9c64b64b8e1b93cc4d2d5cade4cd82383a9a/docs/analog/spice/elec_specs/tables_clear/5_General_Specification3.csv).
That row applies because the nfet_05v0 uses the {term}`nfet_06v0` model card and its oxide
({repo}`data/pdk_elec_spec.json`). The value lies inside the range.

(explained-poly)=

## The poly-silicon gate

The gate is poly-silicon, silicon made of many small crystals. The nfet's gate holds
{{ x_ngate_nfet }} of {term}`donors <donor>` ({term}`NGATE`), so it is n-type. The pfet's gate
holds {{ x_ngate_pfet }} of {term}`acceptors <acceptor>`, so it is p-type
({repo}`data/process/pfet_05v0.toml`).

Because the gate is silicon, the gate voltage can push the free carriers away from its lower
face, as it does in the body. That thin layer without free carriers is
{term}`poly depletion`. It adds a capacitance in series with Cox
({ref}`Sze and Ng, ch. 4 <lit-sze>`). Two capacitors in series hold less charge per volt than
either alone, so it lowers the gate's capacitance.

The simulated gate is {{ x_poly_nfet }} deep. That depth is a project choice, many times the
widest depleted layer, so the far side of the gate stays neutral silicon
({py:mod}`gf180tcad.tcad.moscap1d`).

(explained-oxide-differs)=

## Where this repo's results differ

The calibration fits the oxide thickness between TOXE and an upper bound. That bound is TOXP
plus an allowance of {{ x_delta_nfet }}, so {{ x_t_ox_upper_nfet }}. The fit ends at
{{ x_t_ox_nfet_cal }}, thicker than TOXE. The allowance stands for the depth at which the SPICE
model places the charge, a little below the oxide face. Poly depletion is not part of it,
because the simulated gate is poly-silicon and shows it directly
({doc}`/comparison/process-data`).

In the simple picture the capacitance tops out at Cox, but the simulated stack stays below it.
Its capacitance is {{ x_c_acc_nfet_cal }} at the most negative gate voltage
and {{ x_c_inv_nfet_cal }} at the most positive. At both ends the charge in the body sits a
little below the oxide face, which the {term}`effective oxide thickness` counts as extra oxide.
At the positive end the gate voltage also pushes {term}`electrons <electron>` away
from the gate's lower face. So poly depletion adds its series capacitance at that end only.

The 2D cell and its other differences are on {doc}`/limitations/moscap2d`, and every known gap
is on {doc}`/limitations/index`.
