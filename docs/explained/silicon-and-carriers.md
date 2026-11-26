(explained-silicon)=

# Silicon, doping and carriers

What carries a current in silicon, and how many carriers are in the silicon of this project's
transistors? This page answers that for a reader who knows basic circuits and has not studied
semiconductor physics. It leaves out energy bands.

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
with every electron in a bond carries no current (left panel of {numref}`fig-silicon-bonds`).

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
That value starts from the room-temperature $n_i$ of
{ref}`Altermatt and co-authors <lit-altermatt>`, {{ x_n_i300_tcad }}.
The code ({py:attr}`~gf180tcad.tcad.process.Constants.n_i_cm3`) scales it to {{ x_t_tcad }}, citing
{ref}`Misiakos and Tsamakis <lit-misiakos>` for the temperature dependence.
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

Silicon holds {{ x_atom_density_si }} atoms, a textbook value
({ref}`Ioffe archive, basic parameters <lit-ioffe-basic>`). At the calibrated body doping, one
atom in {{ x_atoms_per_dopant_body }} is an acceptor, an idealised example of that ratio.

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

(explained-conduction)=

## How well doped silicon conducts

The mobility μ of a carrier says how fast it drifts per unit of electric field. The
resistivity of silicon whose majority carriers carry the current follows from it
({ref}`Wikipedia, Electron mobility <lit-wikipedia-mobility>`):

$$
\rho = \frac{1}{q N \mu}
$$ (eq-silicon-resistivity)

where

- $\rho$ is the resistivity, in Ω·cm;
- $q$ is the elementary charge, in C;
- $N$ is the majority carrier density, the doping, in cm⁻³;
- $\mu$ is the majority carrier mobility, in cm²/(V·s).

Mobility falls as the doping rises. The fit below gives the electron mobility of n-type
silicon at room temperature, for {{ x_n_min_fit }} of donors and up
({ref}`Wikipedia, Electron mobility <lit-wikipedia-mobility>`):

$$
\mu = \mu_0 + \frac{\mu_1}{1 + (N / N_{ref})^{\alpha}}
$$ (eq-silicon-mobility)

where

- $\mu$ is the electron mobility, in cm²/(V·s);
- $\mu_0$ is the fit's floor, {{ x_mu0_n_fit }} ({ref}`Wikipedia <lit-wikipedia-mobility>`), in cm²/(V·s);
- $\mu_1$ is the fit's step, {{ x_mu1_n_fit }}, in cm²/(V·s);
- $N$ is the donor density, in cm⁻³;
- $N_{ref}$ is the fit's reference density, {{ x_nref_n_fit }}, in cm⁻³;
- $\alpha$ is the fit's exponent, {{ x_alpha_n_fit }}, dimensionless.

At the nfet source and drain peak, {{ x_sd_peak_nfet }} of donors, the idealised fit gives
{{ x_mu_n_sd_nfet }}. The resistivity is then {{ x_rho_sd_nfet }}, an idealised example.

Pure silicon has n = p = $n_i$, and both carriers conduct.
{math:numref}`eq-silicon-intrinsic` gives its resistivity
({ref}`Wikipedia, Electron mobility <lit-wikipedia-mobility>`).

$$
\rho_i = \frac{1}{q n_i (\mu_n + \mu_p)}
$$ (eq-silicon-intrinsic)

where

- $\rho_i$ is the resistivity of pure silicon, in Ω·cm;
- $q$ is the elementary charge, in C;
- $n_i$ is the {term}`intrinsic carrier density`, in cm⁻³;
- $\mu_n$ is the electron mobility, at most {{ x_mu_n_max_si }} ({ref}`Wikipedia <lit-wikipedia-mobility>`), in cm²/(V·s);
- $\mu_p$ is the hole mobility, at most {{ x_mu_p_max_si }}, in cm²/(V·s).

With the committed $n_i$ and those largest mobilities, pure silicon has at least
{{ x_rho_intrinsic_min }}, an idealised example. The doped source and drain conduct far
better, so the doping, not $n_i$, sets how well the silicon conducts.
{numref}`fig-silicon-resistivity` draws both.

```{figure} /_generated/explained/silicon-resistivity-light.svg
:figclass: only-light
:name: fig-silicon-resistivity
:alt: Log-log plot of resistivity against donor density: a falling solid line from the lowest to the highest density, a dot at its end, and a flat dashed line far above it.

The resistivity of n-type silicon against its donor density, from
{math:numref}`eq-silicon-resistivity` and the mobility fit {math:numref}`eq-silicon-mobility`,
over the fit's range (solid). The dot is the nfet source and drain peak. The dashed line is
the smallest resistivity of pure silicon, {math:numref}`eq-silicon-intrinsic`. All are
idealised examples.
```

```{figure} /_generated/explained/silicon-resistivity-dark.svg
:figclass: only-dark
:alt: Log-log plot of resistivity against donor density: a falling solid line from the lowest to the highest density, a dot at its end, and a flat dashed line far above it.

The resistivity of n-type silicon against its donor density, from
{math:numref}`eq-silicon-resistivity` and the mobility fit {math:numref}`eq-silicon-mobility`,
over the fit's range (solid). The dot is the nfet source and drain peak. The dashed line is
the smallest resistivity of pure silicon, {math:numref}`eq-silicon-intrinsic`. All are
idealised examples.
```

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
