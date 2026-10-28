(explained-junction)=

# The pn junction and its depletion region

Why does a region without free carriers form where n-type silicon meets p-type silicon? This
page answers that for a reader who knows basic circuits and has read {doc}`silicon-and-carriers`.
It covers the junction at rest, with no voltage applied, and leaves out the current through it.

```{figure} /_generated/explained/junction-cell-light.svg
:figclass: only-light
:alt: Cross-section of the transistor with gate, oxide, source, drain and body muted; the lower and inner edges of the source and drain are drawn as a bold line labelled junction.

The 2D cell `w10p0_l0p70` of the {term}`nfet_05v0`, with the junctions
of the source and the drain drawn bold. The oxide thickness and the body doping are fitted to
the {term}`SPICE` model, and the junction depth is the {term}`model card`'s value. The gate and
body depths and the source and drain width are project choices. {{ x_fig_junction_cell_scale }}
```

```{figure} /_generated/explained/junction-cell-dark.svg
:figclass: only-dark
:alt: Cross-section of the transistor with gate, oxide, source, drain and body muted; the lower and inner edges of the source and drain are drawn as a bold line labelled junction.

The 2D cell `w10p0_l0p70` of the {term}`nfet_05v0`, with the junctions
of the source and the drain drawn bold. The oxide thickness and the body doping are fitted to
the {term}`SPICE` model, and the junction depth is the {term}`model card`'s value. The gate and
body depths and the source and drain width are project choices. {{ x_fig_junction_cell_scale }}
```

(explained-junction-meet)=

## Where n-type meets p-type

The source and the drain of the nfet are n-type silicon, rich in free
{term}`electrons <electron>`. The body around them is p-type, rich in {term}`holes <hole>`.
The boundary between the two is a {term}`pn junction`
({ref}`Sze and Ng, ch. 2 <lit-sze>`).

The source and drain hold up to {{ x_sd_peak_nfet }} of {term}`donors <donor>`
({term}`NSD`). The body holds {{ x_n_ch_nfet_cal }} of {term}`acceptors <acceptor>`, this
repo's calibrated value. The junction lies {{ x_xj_nfet }} below the silicon surface
({term}`XJ`, {repo}`data/process/nfet_05v0.toml`).

(explained-junction-depletion)=

## The depletion region

Carriers spread from where they are crowded to where they are scarce. Electrons from the n side
cross the boundary and fill holes on the p side, and holes cross the other way
({ref}`Sze and Ng, ch. 2 <lit-sze>`).

Each carrier that leaves uncovers the {term}`dopant` atom it came from. That atom becomes an ion, an atom
with a net charge: positive on the n side, negative on the p side. The ions cannot move, so a
layer of fixed charge forms on each side, with no free carriers in it. That layer is the
depletion region.

The two layers of charge set up an electric field, which pushes the carriers back. The carriers
stop crossing when the push of the field balances their spread
({ref}`Sze and Ng, ch. 2 <lit-sze>`).

(explained-junction-vbi)=

## The built-in potential

The field adds up to a voltage across the depletion region, the {term}`built-in potential`
$V_{bi}$. It grows with the doping on both sides ({ref}`Sze and Ng, ch. 2 <lit-sze>`).

$$
V_{bi} = V_t \, \ln \frac{N_A \, N_D}{n_i^2}
$$

Here $N_A$ and $N_D$ are the acceptor and donor densities and $n_i$ is the
{term}`intrinsic carrier density`. The thermal voltage $V_t$ is {{ x_vt_tcad }}. For an
idealised abrupt junction between the card's source peak and the calibrated body doping,
$V_{bi}$ is {{ x_vbi_nfet }}.

(explained-junction-width)=

## How wide the region is

The {term}`depletion approximation` treats the region as fully emptied of carriers and the rest
as neutral. It gives the width $W$ of the region, with $\varepsilon_{si}$ the permittivity of
silicon and $q$ the charge of one electron ({ref}`Sze and Ng, ch. 2 <lit-sze>`).

$$
W = \sqrt{\frac{2 \, \varepsilon_{si} \, V_{bi}}{q} \left( \frac{1}{N_A} + \frac{1}{N_D} \right)}
$$

For the same idealised junction, $W$ is {{ x_w_dep_nfet }}. Both sides carry the same total
charge. So the region reaches far into the lightly doped side and barely into the heavily doped
one ({ref}`Sze and Ng, ch. 2 <lit-sze>`). Here it lies almost all in the body.

```{figure} /_generated/explained/junction-panels-light.svg
:figclass: only-light
:alt: Three panels against distance from the junction, negative in the source and positive in the body: a tall thin donor spike at the junction and a low acceptor step, a triangular field and a potential that falls to zero at the depletion edge.

The charge, the field and the potential of the idealised abrupt junction. Negative distances lie
in the source and positive ones in the body. The source doping is
the model card's peak value, and the body doping is fitted to the {term}`SPICE` model. The curves
are an idealised example computed from them in the depletion approximation.
```

```{figure} /_generated/explained/junction-panels-dark.svg
:figclass: only-dark
:alt: Three panels against distance from the junction, negative in the source and positive in the body: a tall thin donor spike at the junction and a low acceptor step, a triangular field and a potential that falls to zero at the depletion edge.

The charge, the field and the potential of the idealised abrupt junction. Negative distances lie
in the source and positive ones in the body. The source doping is
the model card's peak value, and the body doping is fitted to the {term}`SPICE` model. The curves
are an idealised example computed from them in the depletion approximation.
```

(explained-junction-differs)=

## Where this repo's results differ

The 2D cell's source and drain are not a step. Their doping peaks at the surface and falls to the
body's at the junction depth, as a Gaussian. It also spreads sideways under the gate edge
({py:mod}`gf180tcad.tcad.stack`). Near the junction the n side is therefore lightly doped too.
The textbook treats such a profile as a graded junction ({ref}`Sze and Ng, ch. 2 <lit-sze>`).

The {term}`TCAD` solves for the carrier densities everywhere and assumes no depletion
approximation. It varies only the gate voltage. The source, the drain and the body stay at
ground, so the junctions stay at rest ({py:mod}`gf180tcad.tcad.moscap2d`). The 2D cell and its other differences are on
{doc}`/limitations/moscap2d`, and every known gap is on {doc}`/limitations/index`.
