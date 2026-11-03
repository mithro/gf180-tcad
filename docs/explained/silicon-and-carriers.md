(explained-silicon)=

# Silicon, doping and carriers

What carries a current in silicon, and how many carriers are in the silicon of this project's
transistors? This page answers that for a reader who knows basic circuits and has not studied
semiconductor physics. It leaves out energy bands. The densities in {numref}`fig-silicon-doping`
are the numbers it explains.

```{figure} /_generated/explained/silicon-doping-light.svg
:figclass: only-light
:name: fig-silicon-doping
:alt: Log-scale densities against depth through gate, oxide and body; the body is shaded, with a high hole line and a low electron line.

Densities through the layers of the {term}`nfet_05v0`: the gate on top, the {term}`gate oxide`
and the shaded body below. The body doping and the oxide thickness are fitted to the
{term}`SPICE` model. The gate doping is the {term}`model card`'s value, and the layer depths
are project choices. {{ x_fig_silicon_doping_scale }}
```

```{figure} /_generated/explained/silicon-doping-dark.svg
:figclass: only-dark
:alt: Log-scale densities against depth through gate, oxide and body; the body is shaded, with a high hole line and a low electron line.

Densities through the layers of the {term}`nfet_05v0`: the gate on top, the {term}`gate oxide`
and the shaded body below. The body doping and the oxide thickness are fitted to the
{term}`SPICE` model. The gate doping is the {term}`model card`'s value, and the layer depths
are project choices. {{ x_fig_silicon_doping_scale }}
```

## Atoms and bonds

Silicon is a crystal in which each atom shares its four outer {term}`electrons <electron>` with
four neighbours ({ref}`Sze and Ng, ch. 1 <lit-sze>`). Each shared pair is a bond that holds the
atoms together. An electron held in a bond cannot move through the crystal. A perfect crystal
with every electron in a bond carries no current. The left panel of {numref}`fig-silicon-bonds`
draws such a crystal flat.

```{figure} /_generated/explained/silicon-bonds-light.svg
:figclass: only-light
:name: fig-silicon-bonds
:alt: Two panels of a three-by-three grid of silicon atoms, each joined to its four neighbours by a line carrying two dots. On the right one bond has lost a dot: an open circle sits there and a larger coloured dot lies in the gap beside it.

The bonds of silicon, drawn flat: each atom shares a pair of {term}`electrons <electron>` with
each of four neighbours. On the left is a perfect crystal. On the right one bond is broken: its
electron moves free and leaves a {term}`hole`. In the crystal the four neighbours sit in three
dimensions ({ref}`Sze and Ng, ch. 1 <lit-sze>`). Not to scale.
```

```{figure} /_generated/explained/silicon-bonds-dark.svg
:figclass: only-dark
:alt: Two panels of a three-by-three grid of silicon atoms, each joined to its four neighbours by a line carrying two dots. On the right one bond has lost a dot: an open circle sits there and a larger coloured dot lies in the gap beside it.

The bonds of silicon, drawn flat: each atom shares a pair of {term}`electrons <electron>` with
each of four neighbours. On the left is a perfect crystal. On the right one bond is broken: its
electron moves free and leaves a {term}`hole`. In the crystal the four neighbours sit in three
dimensions ({ref}`Sze and Ng, ch. 1 <lit-sze>`). Not to scale.
```

(explained-carriers)=

## Electrons and holes

Heat breaks a few bonds. Each break frees an electron, which moves through the crystal and
carries a current. The broken bond is a {term}`hole`, as the right panel of
{numref}`fig-silicon-bonds` shows. A neighbouring bonded electron can jump
into it, so the hole moves too and acts as a positive charge. In pure silicon, electrons and
holes come in pairs, so their densities are equal: the {term}`intrinsic carrier density` $n_i$.

The simulations of this repo use $n_i$ = {{ x_n_i_tcad }} at {{ x_t_tcad }}, from their
committed constants
({repo}`per_area.meta.json <results/tcad/moscap1d/nfet_05v0/calibrated/per_area.meta.json>`).
The dopings in the next section are far higher.

(explained-dopants)=

## Dopants

A {term}`dopant` is an atom of another element placed in the crystal. A {term}`donor` has one
more outer electron than silicon, and that spare electron is free to move. Donors make n-type
silicon. An {term}`acceptor` has one fewer, takes an electron from a bond and leaves a hole, so
acceptors make p-type silicon ({ref}`Sze and Ng, ch. 1 <lit-sze>`). Both are drawn in
{numref}`fig-silicon-dopants`.

```{figure} /_generated/explained/silicon-dopants-light.svg
:figclass: only-light
:name: fig-silicon-dopants
:alt: Two panels of a three-by-three grid of atoms joined by lines carrying two dots each. On the left the centre atom is marked plus and a larger coloured dot lies near it; on the right the centre atom is marked minus and one bond nearby has an open circle in place of a dot.

A {term}`donor` (left) and an {term}`acceptor` (right) in silicon, drawn flat. The donor's
spare electron moves free, and the donor is left a positive ion. The acceptor takes an electron
from a bond, which leaves a {term}`hole`, and becomes a negative ion
({ref}`Sze and Ng, ch. 1 <lit-sze>`). Not to scale.
```

```{figure} /_generated/explained/silicon-dopants-dark.svg
:figclass: only-dark
:alt: Two panels of a three-by-three grid of atoms joined by lines carrying two dots each. On the left the centre atom is marked plus and a larger coloured dot lies near it; on the right the centre atom is marked minus and one bond nearby has an open circle in place of a dot.

A {term}`donor` (left) and an {term}`acceptor` (right) in silicon, drawn flat. The donor's
spare electron moves free, and the donor is left a positive ion. The acceptor takes an electron
from a bond, which leaves a {term}`hole`, and becomes a negative ion
({ref}`Sze and Ng, ch. 1 <lit-sze>`). Not to scale.
```

A transistor has five parts ({ref}`Taur and Ning, ch. 5 <lit-taur>`), drawn in
{numref}`Figure %s of The parts of a transistor <fig-parts-cell>`. The gate
is the top electrode, which takes the control voltage. The gate oxide insulates it from the
body, the silicon underneath. The source and drain ({term}`S/D`) are the regions at either end
of the gate, where the current enters and leaves the body.

This repo's {term}`process file` for the {term}`nfet_05v0`
({repo}`data/process/nfet_05v0.toml`) gives the dopings. The body is p-type, with
{{ x_ndep_nfet }} of acceptors in the {term}`model card` parameter NDEP. The gate is
{term}`poly-silicon` with {{ x_ngate_nfet }} of donors ({term}`NGATE`), so it is n-type. The
source and drain are n-type too, peaking at {{ x_sd_peak_nfet }} ({term}`NSD`).
The gate and body dopings are the solid lines of {numref}`fig-silicon-doping`.

This repo's calibration ({ref}`cv-agreement`) adjusts three parameters until the simulated
capacitance of the gate matches the {term}`SPICE` model's. The body doping is one of them. It
starts at NDEP and ends at {{ x_n_ch_nfet_cal }}, this repo's committed value.

The {term}`pfet_05v0` is the mirror image. Its body is the {term}`n-well`, with a calibrated
donor density of {{ x_n_ch_pfet_cal }}
({repo}`per_area.meta.json <results/tcad/moscap1d/pfet_05v0/calibrated/per_area.meta.json>`).

(explained-how-many)=

## How many carriers

In doped silicon one carrier outnumbers the other. The {term}`majority carrier` density equals
the doping, because each dopant gives one carrier. The {term}`minority carrier` density follows
from the mass-action law, {math:numref}`eq-silicon-mass-action`: the product of the two
densities is fixed ({ref}`Sze and Ng, ch. 1 <lit-sze>`).

$$
n \, p = n_i^2
$$ (eq-silicon-mass-action)

where

- $n$ is the electron density, in cm⁻³;
- $p$ is the hole density, in cm⁻³;
- $n_i$ is the {term}`intrinsic carrier density`, in cm⁻³.

In the nfet body the holes number {{ x_n_ch_nfet_cal }}. The mass-action law then leaves
{{ x_n_minority_nfet }} of electrons, an idealised example computed from the committed doping
and $n_i$. Adding acceptors raises the holes and lowers the electrons by the same factor. In
{numref}`fig-silicon-doping` the majority densities are solid and the minority ones dashed.

(explained-silicon-differs)=

## Where this repo's results differ

The {term}`TCAD` counts carriers with {term}`Boltzmann statistics`, the simple counting rule,
and the committed $n_i$ ({doc}`/limitations/index`). That rule holds at moderate doping and
fails in very heavily doped silicon ({ref}`Sze and Ng, ch. 1 <lit-sze>`). The gate of
{numref}`fig-silicon-doping`, at {{ x_ngate_nfet }}, is such a region.

The calibration absorbs that error in a shift of the gate voltage, one of its three parameters.
The shift also takes up other offsets, and the fit sets it to {{ x_dv_fb_nfet_cal }}. The note
on that parameter in {repo}`data/process/nfet_05v0.toml` says what it absorbs.

The body doping is one uniform value ({py:mod}`gf180tcad.tcad.stack`), fitted to the
{term}`C–V` curves of the SPICE model. The 2D cell and its other differences are on
{doc}`/limitations/moscap2d`, and every known gap is on {doc}`/limitations/index`.
