(display-values)=

# Display values and their sources

The six values of {repo}`data/render/display.toml` draw the render band diagrams
({numref}`Figure %s of The render manifest <render-band-offsets>`). No simulation reads them. Public sources give different numbers
for each value. This page shows every number the sources give, the one the file takes, and what
the sources show about why the numbers differ.

The file {repo}`data/render/display-sources.toml` lists the numbers, and
{py:mod}`gf180tcad.display_sources` reads it. The test
{test}`tests/test_display_sources.py::test_the_display_file_takes_the_used_row_of_each_quantity`
holds the display file to the rows marked used.

## The numbers each source gives

Each table holds one quantity, one row per source. T is the temperature the source states, and
m* the density-of-states mass a density of states goes with. Basis is "listed" when the source
prints the number, and "computed" when it is this repo's arithmetic from the source's mass.
"Used" marks the row the display file takes.

```{include} /_generated/reproduce/display-sources.inc.md
```

(display-values-dos)=

## Densities of states and the effective mass

The effective density of states of a band follows from its density-of-states effective mass.
{math:numref}`eq-display-dos` gives it
({ref}`Ioffe archive <lit-ioffe>`).

$$
N = 2 \left( \frac{2 \pi m^* k_B T}{h^2} \right)^{3/2}
$$ (eq-display-dos)

where

- $N$ is the effective density of states of the band (the tables give it per cm³), in m⁻³;
- $\pi$ is the ratio of a circle's circumference to its diameter, dimensionless;
- $m^*$ is the density-of-states effective mass (quoted in free-electron masses $m_0$), in kg;
- $k_B$ is the Boltzmann constant, in J/K;
- $T$ is the temperature, in K;
- $h$ is the Planck constant, in J·s.

The sources use the same formula with different masses. {numref}`display-dos-masses` draws $N$
against $m^*$ at 300 K. Each source's number sits on the curve at its own mass, to the figures
the source prints. The test
{test}`tests/test_display_sources.py::test_each_density_of_states_is_the_formula_at_its_mass`
checks every row.

For {term}`electrons <electron>` the masses are close: 1.18 m₀ from Ioffe, 1.08 m₀ from the Colorado sheet and
1.09 m₀ from Green. For {term}`holes <hole>` they are not: Ioffe and the Colorado sheet give 0.81 m₀, Green
1.15 m₀. Wikipedia gives Green's hole mass as 0.59 m₀ at 4 K and 1.15 m₀ at 300 K. It states
that this mass changes by a factor of two in silicon between absolute zero and room temperature
({ref}`Wikipedia <lit-wikipedia-effective-mass>`). The file takes Green's 300 K masses, the
temperature of the display values.

```{figure} /_generated/reproduce/display-dos-masses-light.svg
:name: display-dos-masses
:figclass: only-light
:alt: A rising curve of density of states against mass. Six markers sit on it: three electron markers near the upper right, two hole markers lower left at the same mass, and one hole marker high on the curve.

The band-edge density of states against the density-of-states mass at 300 K, by
{math:numref}`eq-display-dos`, with each source's N_c (electrons) and N_v (holes) at the mass the
source gives, from {repo}`data/render/display-sources.toml`.
```

```{figure} /_generated/reproduce/display-dos-masses-dark.svg
:figclass: only-dark
:alt: A rising curve of density of states against mass. Six markers sit on it: three electron markers near the upper right, two hole markers lower left at the same mass, and one hole marker high on the curve.

The band-edge density of states against the density-of-states mass at 300 K, by
{math:numref}`eq-display-dos`, with each source's N_c (electrons) and N_v (holes) at the mass the
source gives, from {repo}`data/render/display-sources.toml`.
```

(display-values-gap)=

## Silicon's band gap

The Ioffe archive gives the {term}`band gap` of silicon as a function of temperature,
{math:numref}`eq-display-gap` ({ref}`Ioffe archive <lit-ioffe>`).

$$
E_g(T) = E_0 - \frac{\alpha T^2}{T + \beta}
$$ (eq-display-gap)

where

- $E_g$ is the band gap of silicon, in eV;
- $T$ is the temperature, in K;
- $E_0$ is the band gap at 0 K, 1.17, in eV;
- $\alpha$ is a coefficient of the fit, 4.73×10⁻⁴, in eV/K;
- $\beta$ is a temperature of the fit, 636, in K.

At 300 K the formula gives 1.1245 eV (this repo's arithmetic). Ioffe lists 1.12 eV, the formula's value to two decimals,
and the Colorado sheet lists 1.124 eV. Wikipedia gives 1.14 eV at 302 K, where the formula gives
1.1240 eV (this repo's arithmetic). The two papers on the oxide give 1.1 eV and 1.2 eV, to one decimal. The file takes
Ioffe's 1.12 eV. {numref}`display-silicon-gap` draws the formula and the three numbers that state
a temperature.

```{figure} /_generated/reproduce/display-silicon-gap-light.svg
:name: display-silicon-gap
:figclass: only-light
:alt: A straight falling line of band gap against temperature from 250 to 350 K. At 300 K one marker sits just under the line and one on it; a third marker at 302 K sits well above the line.

Silicon's band gap against temperature by {math:numref}`eq-display-gap`, with the three sources
that give a temperature, from {repo}`data/render/display-sources.toml`.
```

```{figure} /_generated/reproduce/display-silicon-gap-dark.svg
:figclass: only-dark
:alt: A straight falling line of band gap against temperature from 250 to 350 K. At 300 K one marker sits just under the line and one on it; a third marker at 302 K sits well above the line.

Silicon's band gap against temperature by {math:numref}`eq-display-gap`, with the three sources
that give a temperature, from {repo}`data/render/display-sources.toml`.
```

(display-values-oxide)=

## The oxide's band gap and the band offsets

Alkauskas et al. give the measured band gap of SiO₂, 8.9 eV, and the measured Si/SiO₂ offsets.
These are 4.4 eV for the {term}`valence band` and 3.4 eV for the {term}`conduction band`
({ref}`Alkauskas et al. <lit-alkauskas>`). Their offsets are those of Himpsel et al. (1988) and
Keister et al. (1999).

With their silicon gap of 1.1 eV, the three add up: 1.1 + 4.4 + 3.4 = 8.9 eV
(this repo's arithmetic).

Shaltaf et al. give 8.9 eV for the oxide and 1.2 eV for silicon. Their offsets are 4.3 eV for
the valence band and 3.1 eV for the conduction band ({ref}`Shaltaf et al. <lit-shaltaf>`). Their
numbers do not add up: 1.2 + 4.3 + 3.1 = 8.6 eV (this repo's arithmetic). Wikipedia gives 9 eV for the oxide, from Vella et al. (2011)
({ref}`Wikipedia <lit-wikipedia-band-gap>`).

The file takes the three numbers of Alkauskas et al. A band diagram's oxide gap is then silicon's
gap plus both offsets. That is 1.12 + 3.4 + 4.4 = 8.92 eV (this repo's arithmetic). {numref}`display-oxide-sources` draws each
source's number.

```{figure} /_generated/reproduce/display-oxide-sources-light.svg
:name: display-oxide-sources
:figclass: only-light
:alt: Three stacked panels with one marker per source. Top, the oxide band gap: two markers at the left end, one at the right. Middle and bottom, the two offsets: one marker at each end of each panel.

The SiO₂ band gap and the two Si/SiO₂ band offsets that each source gives, one panel each, from
{repo}`data/render/display-sources.toml`. Each panel's axis spans its own numbers.
```

```{figure} /_generated/reproduce/display-oxide-sources-dark.svg
:figclass: only-dark
:alt: Three stacked panels with one marker per source. Top, the oxide band gap: two markers at the left end, one at the right. Middle and bottom, the two offsets: one marker at each end of each panel.

The SiO₂ band gap and the two Si/SiO₂ band offsets that each source gives, one panel each, from
{repo}`data/render/display-sources.toml`. Each panel's axis spans its own numbers.
```
