(explained-bands)=

# Energy bands and the Fermi level

How does a band diagram show where the carriers are? This page answers that for a reader who knows
basic circuits and has read {doc}`silicon-and-carriers`. It draws the gate and the body each on
its own, and leaves out what happens where they meet.

```{figure} /_generated/explained/bands-stack-light.svg
:figclass: only-light
:alt: Three stacked layers: a shaded gate on top, a thin muted oxide below it and a tall shaded body at the bottom, each labelled with its material, thickness and doping.

The layers of the {term}`nfet_05v0`: the gate and the body shaded, the {term}`gate oxide`
muted. The oxide thickness and the body doping are fitted to the {term}`SPICE` model. The gate
doping is the {term}`model card`'s value, and the gate and body depths are project choices.
{{ x_fig_bands_stack_scale }}
```

```{figure} /_generated/explained/bands-stack-dark.svg
:figclass: only-dark
:alt: Three stacked layers: a shaded gate on top, a thin muted oxide below it and a tall shaded body at the bottom, each labelled with its material, thickness and doping.

The layers of the {term}`nfet_05v0`: the gate and the body shaded, the {term}`gate oxide`
muted. The oxide thickness and the body doping are fitted to the {term}`SPICE` model. The gate
doping is the {term}`model card`'s value, and the gate and body depths are project choices.
{{ x_fig_bands_stack_scale }}
```

(explained-bands-energy)=

## Two bands of energy

An {term}`electron` in a crystal can only have certain energies. The energies that matter here
fall into two ranges, called bands ({ref}`Sze and Ng, ch. 1 <lit-sze>`). The electrons held in the bonds between atoms
fill the lower range, the {term}`valence band`. The free electrons that move and carry current
have energies in the upper range, the {term}`conduction band`.

Between the two lies the {term}`band gap`, where no electron of a perfect crystal can be. Breaking
a bond lifts an electron across it. The empty place left in the valence band is a {term}`hole`
({ref}`Sze and Ng, ch. 1 <lit-sze>`).

Energies here are in electronvolts (eV), the energy an electron gains when it crosses one volt.
The band gap of silicon is {{ x_band_gap_si }}, a reference value at 300 K<!-- number-ok: cited temperature -->
({ref}`Ioffe archive <lit-ioffe>`). A kelvin (K) is a degree of temperature counted from absolute
zero.

(explained-bands-diagram)=

## The band diagram

A band diagram draws energy upwards. The lower edge of the conduction band and the upper edge of
the valence band are two lines, with the gap between them. Free electrons sit above the
upper line, and holes below the lower one.

```{figure} /_generated/explained/bands-flat-light.svg
:figclass: only-light
:alt: Two band diagrams side by side, the n-type gate and the p-type body, each with a shaded band on top and at the bottom; the dashed level is high in the gate and low in the body.

The bands of the nfet's gate and body, each on its own. The band edges come from the band gap, a
reference value. The gate doping is the {term}`model card`'s value, and the body doping is fitted
to the {term}`SPICE` model. The {term}`Fermi level`, dashed, is an idealised example computed from
those dopings and the simulations' $n_i$ and $V_t$.
```

```{figure} /_generated/explained/bands-flat-dark.svg
:figclass: only-dark
:alt: Two band diagrams side by side, the n-type gate and the p-type body, each with a shaded band on top and at the bottom; the dashed level is high in the gate and low in the body.

The bands of the nfet's gate and body, each on its own. The band edges come from the band gap, a
reference value. The gate doping is the {term}`model card`'s value, and the body doping is fitted
to the {term}`SPICE` model. The {term}`Fermi level`, dashed, is an idealised example computed from
those dopings and the simulations' $n_i$ and $V_t$.
```

The diagrams put zero at the middle of the gap. In pure silicon the Fermi level lies
close to that middle, the intrinsic level $E_i$ ({ref}`Sze and Ng, ch. 1 <lit-sze>`).

(explained-bands-fermi)=

## The Fermi level

The Fermi level is the energy at which a place for an electron is filled half of the time
({ref}`Sze and Ng, ch. 1 <lit-sze>`). Its height in the diagram shows which carrier dominates.
The nearer it lies to the conduction band, the more free electrons there are. The nearer it lies
to the valence band, the more holes there are.

{term}`Donors <donor>` raise it, and {term}`acceptors <acceptor>` lower it. The simulations
link it to the carrier densities with {term}`Boltzmann statistics`. That approximation holds while
the Fermi level stays several times a carrier's heat energy away from the band edges
({ref}`Sze and Ng, ch. 1 <lit-sze>`). Under it, the electron density $n$ sets the Fermi level's
height above the middle of the gap.

$$
E_F - E_i = q \, V_t \, \ln \frac{n}{n_i}
$$

Here $n_i$ is the {term}`intrinsic carrier density` and $q$ the charge of one electron. With the
thermal voltage $V_t$, the product $q V_t$ is the heat energy each carrier has. In eV, $q V_t$ is the same
number as $V_t$ in volts. The simulations of this repo use $V_t$ = {{ x_vt_tcad }}
({repo}`per_area.meta.json <results/tcad/moscap1d/nfet_05v0/calibrated/per_area.meta.json>`).

In the nfet's n-type gate, $n$ is the donor doping. The formula puts the Fermi level
{{ x_fermi_gate_nfet }} above the middle, an idealised example from the model card's gate doping.
In the p-type body, $n$ is the few electrons that the mass-action law leaves
({ref}`explained-how-many`). There the Fermi level is {{ x_fermi_body_nfet }} below the middle,
an idealised example from the calibrated body doping.

(explained-bands-differs)=

## Where this repo's results differ

The conduction band edge lies half the band gap above the middle. In the gate the formula puts the
Fermi level above that edge, as the diagram shows. There the Fermi level lies past the band
edge, where Boltzmann statistics fail ({ref}`Sze and Ng, ch. 1 <lit-sze>`).

The {term}`TCAD` still counts the gate's carriers with Boltzmann statistics. The size of that
error, and the calibration parameter that absorbs it, are on {doc}`/limitations/index`, in its
item on the poly gate.

The band gap of the diagrams is the reference value at 300 K<!-- number-ok: cited temperature -->.
The simulations run at {{ x_t_tcad }} and read the intrinsic carrier density, not a band gap
({py:class}`gf180tcad.tcad.process.Constants`).

The diagrams show each layer alone. Where the gate, the oxide and the body meet, the bands bend
({ref}`Sze and Ng, ch. 4 <lit-sze>`). This repo's {term}`MOS capacitor <MOSCAP>` simulations
compute that bending as the gate voltage changes ({py:mod}`gf180tcad.tcad.moscap1d`).
