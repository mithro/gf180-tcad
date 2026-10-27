(explained-silicon)=

# Silicon, doping and carriers

What carries a current in silicon, and how many carriers are in the silicon of this project's
transistors? This page answers that for a reader who knows basic circuits and has not studied
semiconductor physics. It leaves out energy bands.

```{figure} /_generated/explained/silicon-doping-light.svg
:figclass: only-light
:alt: Log-scale densities against depth through gate, oxide and body; the body is shaded, with a high hole line and a low electron line.

Densities through the calibrated {term}`nfet_05v0` stack: the gate, the gate oxide and the
shaded body. {{ x_fig_silicon_doping_scale }}
```

```{figure} /_generated/explained/silicon-doping-dark.svg
:figclass: only-dark
:alt: Log-scale densities against depth through gate, oxide and body; the body is shaded, with a high hole line and a low electron line.

Densities through the calibrated {term}`nfet_05v0` stack: the gate, the gate oxide and the
shaded body. {{ x_fig_silicon_doping_scale }}
```

## Atoms and bonds

Silicon is a crystal in which each atom shares its four outer electrons with four neighbours
({ref}`Sze and Ng, ch. 1 <lit-sze>`). Each shared pair is a bond that holds the atoms together.
An electron held in a bond cannot move through the crystal. A perfect crystal with every
electron in a bond carries no current.

(explained-carriers)=

## Electrons and holes

Heat breaks a few bonds. Each break frees an {term}`electron`, which moves through the crystal
and carries a current. The broken bond is a {term}`hole`. A neighbouring bonded electron can
jump into it, so the hole moves too and acts as a positive charge. In pure silicon, electrons
and holes come in pairs, so their densities are equal: the {term}`intrinsic carrier density`
$n_i$.

The simulations of this repo use $n_i$ = {{ x_n_i_tcad }} at {{ x_t_tcad }}, from their
committed constants
({repo}`per_area.meta.json <results/tcad/moscap1d/nfet_05v0/calibrated/per_area.meta.json>`).
The dopings below are far higher, and they set how well the silicon conducts.

(explained-dopants)=

## Dopants

A {term}`dopant` is an atom of another element placed in the crystal. A {term}`donor` has one
more outer electron than silicon, and that spare electron is free to move. Donors make n-type
silicon. An {term}`acceptor` has one fewer, takes an electron from a bond and leaves a hole, so
acceptors make p-type silicon ({ref}`Sze and Ng, ch. 1 <lit-sze>`).

This repo's {term}`process file` for the {term}`nfet_05v0`
({repo}`data/process/nfet_05v0.toml`) gives the dopings. The body is p-type, with
{{ x_ndep_nfet }} of acceptors as the starting value, the {term}`model card` parameter NDEP. The calibration
fitted {{ x_n_ch_nfet_cal }}, this repo's committed value. The gate is n-type poly-silicon with
{{ x_ngate_nfet }} of donors ({term}`NGATE`). The source and drain are n-type too, peaking at
{{ x_sd_peak_nfet }} ({term}`NSD`).

The {term}`pfet_05v0` is the mirror image. Its body is the n-type well, with a calibrated
donor density of {{ x_n_ch_pfet_cal }}
({repo}`per_area.meta.json <results/tcad/moscap1d/pfet_05v0/calibrated/per_area.meta.json>`).

(explained-how-many)=

## How many carriers

In doped silicon one carrier outnumbers the other. The {term}`majority carrier` density equals
the doping, because each dopant gives one carrier. The {term}`minority carrier` density follows
from the mass-action law: the product of the two densities is fixed at $n_i^2$
({ref}`Sze and Ng, ch. 1 <lit-sze>`).

$$
n \, p = n_i^2
$$

In the nfet body the holes number {{ x_n_ch_nfet_cal }}. The mass-action law then leaves
{{ x_n_minority_nfet }} of electrons, an idealised example computed from the committed doping
and $n_i$. Adding acceptors raises the holes and lowers the electrons by the same factor.

(explained-silicon-differs)=

## Where this repo's results differ

The {term}`TCAD` counts carriers with {term}`Boltzmann statistics`, using the committed $n_i$.
That approximation holds while the doping is moderate and fails in very heavily doped silicon
({ref}`Sze and Ng, ch. 1 <lit-sze>`). The gate, at {{ x_ngate_nfet }}, is such a region.

In an idealised example, exact Fermi–Dirac statistics place the gate's electrons
{{ x_degenerate_offset_gate }} higher in energy than Boltzmann statistics do. The example uses
the textbook density of states {{ x_nc_si }} ({ref}`Sze and Ng, appendix G <lit-sze>`) and the
committed temperature.
The calibration's flat-band offset `dv_fb_v` absorbs this error with the other flat-band terms,
as its note in the process file states.

The body doping is one uniform value, fitted to the {term}`SPICE` {term}`C–V` curves
({ref}`cv-agreement`). The 2D cell and its other differences are on
{doc}`/limitations/moscap2d`, and every known gap is on {doc}`/limitations/index`.
