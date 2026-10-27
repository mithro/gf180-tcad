(explained-oxide)=

# Gate oxide and poly-silicon

What are the {term}`gate oxide` and the {term}`poly-silicon` gate of this project's transistors,
and why do their thickness and doping matter? This page answers that for a reader who knows basic
circuits and has read {doc}`silicon-and-carriers`. It leaves out what the silicon under the oxide
does as the gate voltage changes.

```{figure} /_generated/explained/oxide-stack-light.svg
:figclass: only-light
:alt: Three stacked layers: a shaded gate on top, a thin shaded oxide below it and a tall muted body at the bottom, each labelled with its material, thickness and doping.

The layers of the {term}`nfet_05v0`, with the values this repo fits to the {term}`SPICE` model:
the gate and the {term}`gate oxide` shaded, the body muted. {{ x_fig_oxide_stack_scale }}
```

```{figure} /_generated/explained/oxide-stack-dark.svg
:figclass: only-dark
:alt: Three stacked layers: a shaded gate on top, a thin shaded oxide below it and a tall muted body at the bottom, each labelled with its material, thickness and doping.

The layers of the {term}`nfet_05v0`, with the values this repo fits to the {term}`SPICE` model:
the gate and the {term}`gate oxide` shaded, the body muted. {{ x_fig_oxide_stack_scale }}
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

The gate oxide is silicon dioxide, an insulator. The {term}`model card` gives its thickness in
two forms ({ref}`BSIM4 manual <lit-bsim4>`). TOXE, the electrical thickness, is
{{ x_toxe_nfet }}. TOXP, the physical thickness, is {{ x_toxp_nfet }}
({repo}`data/process/nfet_05v0.toml`).

The oxide's relative permittivity, {term}`EPSROX`, is {{ x_epsrox_nfet }}. A capacitor with
this oxide between its plates holds that many times the charge of a vacuum gap of the same
thickness.

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
same {{ x_cox_check_nfet }}. It also records the range the {term}`PDK` specifies, with its
source. That range is {{ x_cox_spec_min }} to {{ x_cox_spec_max }}, and the value lies inside it.

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
Its capacitance per area is {{ x_c_acc_nfet_cal }} and {{ x_c_inv_nfet_cal }} at the two ends of
the gate-voltage range. The oxide alone gives {{ x_cox_check_nfet }}, in the same calibration
result. The charge in the silicon sits a little below the oxide face, and poly depletion adds
its series capacitance. The {term}`effective oxide thickness` lumps both in with the oxide.

The 2D cell and its other differences are on {doc}`/limitations/moscap2d`, and every known gap
is on {doc}`/limitations/index`.
