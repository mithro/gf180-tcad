(explained-parts)=

# The parts of a transistor

What are the gate, the source, the drain and the body of a {term}`GF180MCU` 5 V transistor,
and which does this repo simulate? This page answers that for a reader who knows basic circuits and has
read {doc}`silicon-and-carriers`. It names each part and leaves out how the transistor switches.

```{figure} /_generated/explained/parts-cell-light.svg
:figclass: only-light
:alt: Cross-section of the transistor: a gate on a thin oxide in the middle, a source on the left and a drain on the right at the surface, a large body below, contacts drawn as dark bars.

The 2D cell of the {term}`nfet_05v0` with {term}`geometry id` `w10p0_l0p70`, cut along the
gate's length. Blue parts are n-type and the orange body is p-type. The oxide thickness and the
body doping are fitted to the {term}`SPICE` model. The junction depth is the
{term}`model card`'s value. The gate and body depths and the source and drain width are
project choices. {{ x_fig_parts_cell_scale }}
```

```{figure} /_generated/explained/parts-cell-dark.svg
:figclass: only-dark
:alt: Cross-section of the transistor: a gate on a thin oxide in the middle, a source on the left and a drain on the right at the surface, a large body below, contacts drawn as dark bars.

The 2D cell of the {term}`nfet_05v0` with {term}`geometry id` `w10p0_l0p70`, cut along the
gate's length. Blue parts are n-type and the orange body is p-type. The oxide thickness and the
body doping are fitted to the {term}`SPICE` model. The junction depth is the
{term}`model card`'s value. The gate and body depths and the source and drain width are
project choices. {{ x_fig_parts_cell_scale }}
```

(explained-parts-gate)=

## The gate

The gate is the electrode on top, which takes the control voltage. That voltage controls the
channel, the thin layer of silicon under the gate where the current flows
({ref}`Taur and Ning, ch. 5 <lit-taur>`). The gate is a strip of
{term}`poly-silicon` that crosses the active area, the stretch of silicon that holds the
transistor. The {term}`PDK` draws the gate on its `Poly2` layer
([gate layer rules](https://github.com/google/gf180mcu-pdk/blob/de3240d7529a6970437ac3344820aaae7839f215/docs/physical_verification/design_manual/drm_07_08.rst))
and the active area on its `COMP` layer ({py:mod}`gf180tcad.tcad.stack`).

```{figure} images/gf180mcu-pmos-pair-plan-view.png
:alt: Two transistors seen from above, each a blue gate strip crossing a black-outlined active area with a contact square on either side, inside a yellow n-well. A legend row below names the layers: Nwell, COMP, Pplus, Nplus, SAB, Contact, Poly2 and Metal.

Two p-channel transistors, whose channel carries holes, seen from above. They are drawn as a
matched pair in the GF180MCU design manual ([§10.6.1](https://github.com/google/gf180mcu-pdk/blob/de3240d7529a6970437ac3344820aaae7839f215/docs/physical_verification/design_manual/drm_10_6_1.rst),
Apache License). G is the gate, S the source and D the drain.
```

The gate's length runs from source to drain, and its width runs along the strip. The
simulated cell in the first figure has a gate {{ x_l_cell }} long and {{ x_w_cell }} wide
({repo}`cv.meta.json <results/tcad/moscap2d/nfet_05v0/calibrated/w10p0_l0p70/cv.meta.json>`).
The cross-section cuts across the strip, so it shows the length; the width runs into the page.

(explained-parts-oxide)=

## The gate oxide

The {term}`gate oxide` is the insulating layer under the gate. In the simulated cell it is
{{ x_t_ox_cell }} thick. It is the thick oxide of the 5 V transistor. The PDK marks that oxide
with its {term}`Dualgate` layer ({py:mod}`gf180tcad.tcad.stack`). {doc}`oxide-and-poly` explains its
thickness and its capacitance.

(explained-parts-sd)=

## The source and the drain

The source and the drain ({term}`S/D`) are the regions either side of the gate. Carriers
enter the channel at the source and leave at the drain
({ref}`Taur and Ning, ch. 5 <lit-taur>`). In the nfet both are n-type, with up
to {{ x_sd_peak_nfet }} of {term}`donors <donor>` ({term}`NSD`). They reach {{ x_xj_nfet }} below the surface
({term}`XJ`), where they meet the body in a {term}`pn junction`
({doc}`pn-junction`).

(explained-parts-body)=

## The body and the wells

The body is the silicon around the source and the drain, the channel under the gate included.
In the nfet it is p-type. The design manual defines the LVPWELL layer for the body of the
n-channel transistors, whose channel carries electrons
([LVPWELL rules](https://github.com/google/gf180mcu-pdk/blob/de3240d7529a6970437ac3344820aaae7839f215/docs/physical_verification/design_manual/drm_07_04.rst)).

The {term}`pfet_05v0` is the mirror image, with a p-type source and drain in an
{term}`n-well` body. The plan-view drawing above shows that well in yellow
([Nwell rules](https://github.com/google/gf180mcu-pdk/blob/de3240d7529a6970437ac3344820aaae7839f215/docs/physical_verification/design_manual/drm_07_05.rst)).
This repo dopes each body uniformly ({py:mod}`gf180tcad.tcad.stack`). The doping is a value
fitted to the {term}`SPICE` model, {{ x_n_ch_nfet_cal }} for the nfet.

(explained-parts-contacts)=

## The contacts

Each part takes its voltage through a contact, drawn as a solid bar. The gate's sits on top, the
source's and the drain's at the surface, and the body's underneath. The simulated cell has four contacts, gate,
body, drain and source ({repo}`cv.meta.json <results/tcad/moscap2d/nfet_05v0/calibrated/w10p0_l0p70/cv.meta.json>`).
The simulator solves for the cell on a mesh, a grid of {{ x_node_count_cell }} points.

(explained-parts-ldd)=

## The lightly doped drain

A lightly doped drain ({term}`LDD`) is a part of the source and drain with less doping, under the
edge of the gate. The {term}`BSIM4` model gives the gate's overlap with it a capacitance of its
own, which changes with the gate voltage
({ref}`BSIM4 manual, §7.1 and §7.5.2 <lit-bsim4>`). The nfet's model card sets that
capacitance, CGDL, to {{ x_cgdl_nfet }} of gate width
({repo}`data/process/nfet_05v0.toml`).

(explained-parts-differs)=

## Where this repo's results differ

The simulated cell has no spacers, the insulating walls either side of the gate, and no LDD
({py:mod}`gf180tcad.tcad.stack`). The overlap capacitance of the LDD enters the 1D result, the
stack of layers on its own, from the model card instead
({py:func}`gf180tcad.tcad.moscap1d.parasitic_ff`). The cell also has no shallow trench isolation
({term}`STI`): its sides are boundaries that no current crosses.

The drawing's source and drain width is not to scale. The real contacts sit at the contact
openings of the PDK cell, not at the middle of each region. The 2D cell and its other differences
are on {doc}`/limitations/moscap2d`, and every known gap is on {doc}`/limitations/index`.
