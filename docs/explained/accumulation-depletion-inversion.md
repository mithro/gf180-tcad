(explained-regions)=

# Accumulation, depletion and inversion

What happens under the gate as the gate voltage moves from negative to positive? This page answers that for the
{term}`MOS capacitor <MOSCAP>` of the {term}`nfet_05v0`, for a reader who has read {doc}`mos-capacitor`. It names
the three regions of the {term}`C–V` curve and shows the energy bands in each.

```{figure} /_generated/explained/cv-regions-light.svg
:figclass: only-light
:alt: Gate capacitance against gate voltage in three shaded bands: high and flat at the left in orange, a dip in grey, and high and flat again at the right in blue, with a solid and a dashed line almost on top of each other.

The gate capacitance of the nfet_05v0 at `w10p0_l10p00`. The solid line is the {term}`SPICE`
model at the {term}`typical corner`. The dashed line is the simulated stack, with the oxide
thickness, body doping and voltage shift fitted to the SPICE model. The shading edges are this
repo's marks on the SPICE curve ({py:func}`~gf180tcad.calibrate.cv.regions`).
```

```{figure} /_generated/explained/cv-regions-dark.svg
:figclass: only-dark
:alt: Gate capacitance against gate voltage in three shaded bands: high and flat at the left in orange, a dip in grey, and high and flat again at the right in blue, with a solid and a dashed line almost on top of each other.

The gate capacitance of the nfet_05v0 at `w10p0_l10p00`. The solid line is the {term}`SPICE`
model at the {term}`typical corner`. The dashed line is the simulated stack, with the oxide
thickness, body doping and voltage shift fitted to the SPICE model. The shading edges are this
repo's marks on the SPICE curve ({py:func}`~gf180tcad.calibrate.cv.regions`).
```

(explained-regions-three)=

## Three regions and flat band

The body of the nfet is p-type: its free carriers are {term}`holes <hole>`. The gate voltage
decides which carriers gather at the surface of the body, under the oxide
({ref}`Sze and Ng, ch. 4 <lit-sze>`; {ref}`Taur and Ning, ch. 4 <lit-taur>`).

- {term}`Accumulation`: a negative gate draws extra holes to the surface. They form a thin layer
  right under the oxide, so the capacitance is close to the oxide's.
- {term}`Flat band`: at one gate voltage the body holds no charge at its surface.
- {term}`Depletion`: above flat band, the gate pushes the holes away. It leaves a layer without
  free carriers, holding the fixed charge of the {term}`acceptors <acceptor>`.
- {term}`Inversion`: further up, the gate draws {term}`electrons <electron>` to the surface.
  There they outnumber the holes, and the surface turns n-type.

The depleted layer acts as a second capacitor, in series with the oxide: the gate charge must
reach across both. So the gate capacitance falls in depletion. In inversion the electrons sit
right under the oxide again, and the curve climbs back ({ref}`Sze and Ng, ch. 4 <lit-sze>`).

The {term}`pfet_05v0` has an n-type body, the {term}`n-well`. There electrons and holes swap
roles, and the gate voltages change sign.

(explained-regions-dip)=

## The dip and where the regions start

Between its two flat parts the SPICE curve dips to a minimum of {{ x_c_min_l10 }} at
{{ x_u_min_l10 }} ({repo}`nfet_05v0.result.json <results/tcad/calibration/nfet_05v0.result.json>`).
This repo marks the regions on that curve ({py:func}`~gf180tcad.calibrate.cv.regions`).

- Accumulation ends at {{ x_u_fb_l10 }}, where the curve has fallen a set fraction below its
  flat part ({py:data}`~gf180tcad.calibrate.cv.FB_FRACTION`).
- Inversion starts at {{ x_u_t_l10 }}, where the curve has climbed halfway from the minimum back
  to its other flat part.

The halfway level lies midway between the minimum and the accumulation flat part. The checks of
{ref}`cv-agreement-metric` compare where each curve crosses it, on either side of the dip. On
the falling side, the SPICE curve crosses at {{ x_u_dep_spice_l10 }} and the simulated one at
{{ x_u_dep_tcad_l10 }}. On the rising side, they cross at {{ x_u_inv_spice_l10 }} and
{{ x_u_inv_tcad_l10 }}.

(explained-regions-bands)=

## The bands in each region

A band diagram shows the energies an electron can have against the depth into the body
({doc}`bands-and-fermi-level`). The {term}`Fermi level`, the energy filled half of the time,
stays flat, because no current flows ({ref}`Sze and Ng, ch. 4 <lit-sze>`).

```{figure} /_generated/explained/band-regimes-light.svg
:figclass: only-light
:alt: Four band diagrams against depth below the oxide: flat bands in accumulation with holes at the surface, flat bands at flat band, bands bending down near the surface in depletion, and bending further in inversion with electrons at the surface.

The bands of the nfet's body in an idealised stack, in the {term}`depletion approximation`.
The body doping is fitted to the SPICE model. The {term}`band gap` is a textbook value. The
intrinsic density and the thermal voltage are the simulation's constants.
```

```{figure} /_generated/explained/band-regimes-dark.svg
:figclass: only-dark
:alt: Four band diagrams against depth below the oxide: flat bands in accumulation with holes at the surface, flat bands at flat band, bands bending down near the surface in depletion, and bending further in inversion with electrons at the surface.

The bands of the nfet's body in an idealised stack, in the {term}`depletion approximation`.
The body doping is fitted to the SPICE model. The {term}`band gap` is a textbook value. The
intrinsic density and the thermal voltage are the simulation's constants.
```

A positive gate bends the bands down at the surface. The depletion panel is drawn where the
middle of the gap at the surface meets the Fermi level. There electrons and holes are equally
few ({ref}`Sze and Ng, ch. 4 <lit-sze>`).

In the inversion panel the bending is twice that: the surface is as n-type as the body is
p-type. That is the textbook start of strong inversion ({ref}`Sze and Ng, ch. 4 <lit-sze>`).
In this approximation the bands stay flat in accumulation, and the holes form a thin sheet at
the surface.

For this idealised stack, with no charge in the oxide, the textbook formulas put flat band at
{{ x_v_fb_nfet }}. They put the {term}`threshold voltage`, the start of strong inversion, at
{{ x_v_t_nfet }}, also an idealised value. The inputs are the {term}`model card`'s gate doping
and the fitted body doping and oxide thickness.

(explained-regions-differs)=

## Where this repo's results differ

The panels use the depletion approximation. The simulation solves the charge and the bending
together, with {term}`Boltzmann statistics` ({py:mod}`gf180tcad.tcad.moscap1d`). Its depleted
layer then has a smooth edge, and its bands bend in accumulation too
({ref}`Sze and Ng, ch. 4 <lit-sze>`).

The idealised voltages are not the marks of the figure. The marks are read off the SPICE
curve. The idealised voltages come from formulas, without the fitted shift of
{{ x_dv_fb_nfet_cal }}.

Each crossing check is {term}`Agree` when the two crossings lie within {{ x_dv_tol_l10 }}
of each other. Here the falling side is {{ x_verdict_dv_dep_l10 }} and the rising side
{{ x_verdict_dv_inv_l10 }} ({ref}`the checks <cv-agreement-metric>`). The pfet's 1D fit is
{{ x_verdict_pfet_1d }} ({ref}`the pfet mismatch <cv-agreement-mismatch>`).

{{ x_two_d_disagree }} ([issue #108](https://github.com/mithro/gf180-tcad/issues/108)). The
checks of each 2D cell are on {ref}`cv-agreement-validation`.
