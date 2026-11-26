# High-voltage junction terminations

The reverse {term}`breakdown voltage` of a well-to-substrate junction depends on what is drawn
at the well edge. The experiment {repo}`experiments/hv-junction` simulates that edge for the
structures of a test die of the [evampire](https://github.com/mithro/evampire) project. The
structure list is {repo}`experiments/hv-junction/structures.json`. Each structure is an N-well
or a {term}`deep N-well` in the P substrate, surrounded by one edge termination. The simulated
section of one structure is in {numref}`hvj-section-figure`.

The numbers here are predictions of a 2D model under stated process assumptions. No measured
breakdown voltage of these structures exists ({doc}`/limitations/silicon-validation`). The
{ref}`limits <hvj-limits>` list what the model leaves out.

(hvj-method)=

## Method

### Cross-section

{{ DEVSIM }} solves each structure on a 2D cross-section along a radius of the well
({repo}`experiments/hv-junction/structure.py`). The section has one silicon region, the trench
oxide ({term}`STI`), the dielectric above it and the conductor plates. Its left edge is a
symmetry plane 8 µm inside the well edge. The section of a structure with one
{term}`floating ring` and one {term}`field plate` is in {numref}`hvj-section-figure`.

```{figure} /_generated/hv-junction/section-light.svg
:figclass: only-light
:name: hvj-section-figure
:alt: Cross-section with depth downwards. An N-well on the left, a floating N-well ring, a P-well beyond the well edge, trench oxide at the surface, a Metal1 plate above, and two contacts.

The simulated section of an N-well with one floating ring and a Metal1 plate, under assumption
A. The well contact is swept; the substrate contact stays at 0 V. Each doped box is drawn down
to two standard deviations below its implant peak
({repo}`experiments/hv-junction/hvsite.py`).
```

```{figure} /_generated/hv-junction/section-dark.svg
:figclass: only-dark
:alt: Cross-section with depth downwards. An N-well on the left, a floating N-well ring, a P-well beyond the well edge, trench oxide at the surface, a Metal1 plate above, and two contacts.

The simulated section of an N-well with one floating ring and a Metal1 plate, under assumption
A. The well contact is swept; the substrate contact stays at 0 V. Each doped box is drawn down
to two standard deviations below its implant peak
({repo}`experiments/hv-junction/hvsite.py`).
```

The script {repo}`experiments/hv-junction/hvsite.py` turns a drawn structure into this section.
The layer heights are those of the PDK's interconnect specification. The trench oxide is
0.32 µm thick and the dielectric under Metal1 is 0.86 µm thick
([dielectric table](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/layout/inter_specs/inter_specs_2_2.html)).
Poly2 is 0.2 µm thick and each metal 0.55 µm
([conductor table](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/layout/inter_specs/inter_specs_2_1.html)).

A corner of the well is simulated as the same section in cylindrical coordinates. The axis is
the centre of the corner, and the well edge lies at the corner radius. A drawn radius under
2 µm is simulated at 2 µm.

Every well, ring and tap is a sum of implanted boxes. A box is a peak density times a depth
profile and a lateral profile, {math:numref}`eq-hvj-implant`:

$$
N(x,y)=N_0\,G(y)\,L(x)
$$ (eq-hvj-implant)

where

- $N$ is the dopant density of one box, in cm⁻³;
- $N_0$ is its peak density, in cm⁻³;
- $x$ and $y$ are the position along the surface and the depth, in µm;
- $G$ is the depth profile of {math:numref}`eq-hvj-depth`, dimensionless;
- $L$ is the lateral profile of {math:numref}`eq-hvj-lateral`, dimensionless.

$$
G(y)=\exp\frac{-(y-R_p)^2}{2\sigma_y^2}
$$ (eq-hvj-depth)

where

- $G$ is the depth profile, dimensionless;
- $y$ is the depth, in µm;
- $R_p$ is the depth of the peak, in µm;
- $\sigma_y$ is the vertical standard deviation, in µm.

$$
L(x)=\tfrac12[\operatorname{erfc}\frac{x-x_1}{\sqrt2\,\sigma_x}
-\operatorname{erfc}\frac{x-x_0}{\sqrt2\,\sigma_x}]
$$ (eq-hvj-lateral)

where

- $L$ is the lateral profile, dimensionless;
- $x$ is the position along the surface, in µm;
- $x_0$ and $x_1$ are the drawn edges of the box, in µm;
- $\sigma_x$ is the lateral standard deviation, in µm.

### Equations

The solve is {term}`drift-diffusion`: Poisson's equation {math:numref}`eq-hvj-poisson` with
the two carrier continuity equations
({repo}`experiments/hv-junction/dd.py`). The carriers have constant mobilities and
Shockley-Read-Hall recombination. The solve holds no impact-ionisation term.

$$
\nabla \cdot \left( \varepsilon \, \nabla \psi \right) = -q \left( p - n + N_D - N_A \right)
$$ (eq-hvj-poisson)

where

- $\varepsilon$ is the permittivity of the material, in F/cm;
- $\psi$ is the electrostatic potential, in V;
- $q$ is the elementary charge, in C;
- $p$ and $n$ are the hole and electron densities, in cm⁻³;
- $N_D$ and $N_A$ are the donor and acceptor densities of {math:numref}`eq-hvj-implant`, in cm⁻³.

A {term}`fixed oxide charge` is a sheet of positive charge on the silicon surface nodes. The
well contact and every plate tied to it
are then swept upwards together ({repo}`experiments/hv-junction/sweep.py`). The curves of
{numref}`hvj-integral-figure` are such sweeps.

### Breakdown criterion

The breakdown voltage is the bias at which the {term}`ionisation integral` reaches 1. After
each bias step the potential is traced along field lines through the high-field nodes
({repo}`experiments/hv-junction/fieldline.py`). The electron integral
{math:numref}`eq-hvj-integral` is taken along each line, and the largest counts
({repo}`experiments/hv-junction/ionize.py`).

$$
I_n=\int_0^W\alpha_n(s)\exp[-\int_0^s(\alpha_n-\alpha_p)\,\mathrm{d}s']\,\mathrm{d}s
$$ (eq-hvj-integral)

where

- $I_n$ is the electron ionisation integral, dimensionless;
- $s$ and $s'$ are arc lengths along the field line from its P end, in cm;
- $W$ is the length of the line inside the depleted silicon, in cm;
- $\alpha_n$ and $\alpha_p$ are the electron and hole ionisation coefficients of
  {math:numref}`eq-hvj-alpha`, in cm⁻¹.

$$
\alpha(E) = a \, \exp\!\left( -\frac{b}{E} \right)
$$ (eq-hvj-alpha)

where

- $\alpha$ is the ionisation coefficient of one carrier, in cm⁻¹;
- $E$ is the magnitude of the electric field, in V/cm;
- $a$ is the coefficient's prefactor, in cm⁻¹;
- $b$ is its critical field, in V/cm.

The values of $a$ and $b$ are those of van Overstraeten and de Man
({doi}`10.1016/0038-1101(70)90139-5`). For electrons $a$ = 7.03e5 cm⁻¹ and $b$ = 1.231e6 V/cm.
For holes they are 1.582e6 cm⁻¹ and 2.036e6 V/cm up to 4e5 V/cm. Above that field they are
6.71e5 cm⁻¹ and 1.693e6 V/cm.

The crossing of 1 is interpolated between two bias steps on the logarithm of the integral.
The integral of four cases against the bias is in {numref}`hvj-integral-figure`.

```{figure} /_generated/hv-junction/integral-light.svg
:figclass: only-light
:name: hvj-integral-figure
:alt: Four rising curves of the ionisation integral on a logarithmic axis against reverse bias. Each ends where it crosses a dashed line at 1.

The largest electron ionisation integral against the reverse bias of the well, for four cases
of the {repo}`main record <results/hv-junction/main.json>`. A case's name is its structure, its
process assumption and its shape. The dashed line at 1 defines the breakdown voltage.
```

```{figure} /_generated/hv-junction/integral-dark.svg
:figclass: only-dark
:alt: Four rising curves of the ionisation integral on a logarithmic axis against reverse bias. Each ends where it crosses a dashed line at 1.

The largest electron ionisation integral against the reverse bias of the well, for four cases
of the {repo}`main record <results/hv-junction/main.json>`. A case's name is its structure, its
process assumption and its shape. The dashed line at 1 defines the breakdown voltage.
```

(hvj-process)=

## Process assumptions

### Doping family

The PDK publishes no well doping profile. The wells of {numref}`hvj-section-figure` are
therefore one member of a family of profiles, `DEFAULT_PROCESS` of
{repo}`experiments/hv-junction/hvsite.py`. The N-well and the P-well are each a shallow heavy
implant and a deeper light one. The substrate is uniform at 3.5e15 cm⁻³.

The family is set against three published values, listed in {numref}`tab-hvj-anchors`. The
first two are computed from the N-well profile by
{repo}`experiments/hv-junction/profile1d.py`. The third is the simulated case NT20 under
assumption A.

~~~{table} The published anchors of the doping family and what the family gives.
:name: tab-hvj-anchors

| Quantity | Published | Family |
|---|---|---|
| N-well sheet resistance (Ω/sq) | 1000 | {{ hvj_nw_rs }} |
| N-well zero-bias capacitance (fF/µm²) | 0.149 | {{ hvj_nw_cj0 }} |
| N-well breakdown voltage (V) | 14 | {{ hvj_NT20_A_edge }} |
~~~

The published sheet resistance runs from 800 to 1200 Ω/sq
([electrical specification 5.1](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/spice/elec_specs/elec_specs_5_1.html)).
The capacitance is the `cjo` of the model `diode_nw2ps_06v0`
([model file](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38461));
the family lies {{ hvj_nw_cj0_pct }} % from it. The published breakdown voltage is 14 V
typical and 10 V minimum
([electrical specification 5.5](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/spice/elec_specs/elec_specs_5_5.html)).
The family's abutting junction lies {{ hvj_abut_pct }} % above the typical value.

The family does not reproduce the deep N-well diode model. That model, `diode_dw2ps`, has a
breakdown voltage of 30.48 V
([model file](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38512)).
The family's deep N-well values are in {numref}`tab-hvj-deep`.

### P-well and oxide charge

The foundry generates the P-well (LVPWELL) from the drawn layers
([design manual 4.4](https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_04_4.html)).
The generation rule is unpublished, so each structure is simulated under several assumptions
about the {term}`generated P-well`. {numref}`hvj-section-figure` is drawn under assumption A.

- **A.** A P-well lies wherever no N-well, deep N-well or {term}`NAT` layer is. It abuts an
  N-well and stays 1.5 µm from a deep N-well
  ([rule LPW.11](https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_07_04.html)).
- **An.** As A, without the P-well strip between an N-well and a NAT layer. The NAT layer
  stays 0.5 µm from an N-well
  ([rule NAT.3](https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_10_05.html)).
- **B.** A P-well lies only where the layout draws one.
- **Aq and Bq.** As A and B, with a fixed oxide charge of 1e11 cm⁻².

The cases of the doping family vary B and A
({repo}`experiments/hv-junction/predict.py`):

- **Blo, Bhi, Alo and Ahi** have a substrate of 2e15 cm⁻³ (lo) or 5e15 cm⁻³ (hi).
- **Bdp** adds acceptors that peak at 4e16 cm⁻³, 5 µm below the surface.
- **Bq3** has a fixed oxide charge of 3e11 cm⁻².

(hvj-checks)=

## Checks

### 1D diodes

An abrupt N⁺/P diode has a known answer. In the depletion approximation its field is a
triangle, the shape that the curves of {numref}`hvj-integral-figure` integrate over. The
integral {math:numref}`eq-hvj-integral` over that triangle reaches 1 at one junction potential.
The applied bias is that potential less the built-in potential.
{repo}`experiments/hv-junction/diode1d.py` solves the same diode in {{ DEVSIM }}. The two are
compared in {numref}`tab-hvj-diodes`.

~~~{table} Breakdown voltage of an abrupt diode: the triangular field and the 1D solve.
:name: tab-hvj-diodes

| P doping (cm⁻³) | Triangular field (V) | Built-in potential (V) | Applied bias (V) | 1D solve (V) |
|---|---|---|---|---|
| 1e15 | {{ hvj_diode_1e15_analytic }} | {{ hvj_diode_1e15_vbi }} | {{ hvj_diode_1e15_applied }} | {{ hvj_diode_1e15 }} |
| 1e16 | {{ hvj_diode_1e16_analytic }} | {{ hvj_diode_1e16_vbi }} | {{ hvj_diode_1e16_applied }} | {{ hvj_diode_1e16 }} |
| 1e17 | {{ hvj_diode_1e17_analytic }} | {{ hvj_diode_1e17_vbi }} | {{ hvj_diode_1e17_applied }} | {{ hvj_diode_1e17 }} |
~~~

A dash in a table of these pages marks a value whose record is not committed
({ref}`records <hvj-records>`).

### Precision, step and mesh

The check cases of {repo}`experiments/hv-junction/checks.py` repeat one section with one
setting changed. The bare cases are an N-well edge in uniform substrate. The abutting cases
are the section of {numref}`hvj-section-figure` without ring or plate. Their values are in
{numref}`tab-hvj-checks`.

~~~{table} Breakdown voltage of the check cases.
:name: tab-hvj-checks

| Section | Mesh at the edges (µm) | Floats | Bias step (V) | Breakdown (V) |
|---|---|---|---|---|
| bare | 0.1 | 128-bit | 2 | {{ hvj_chk_bare_f0_1_x128_v2 }} |
| bare | 0.1 | 64-bit | 2 | {{ hvj_chk_bare_f0_1_f64_v2 }} |
| bare | 0.1 | 64-bit | 4 | {{ hvj_chk_bare_f0_1_f64_v4 }} |
| bare | 0.1 | 64-bit | 5 | {{ hvj_chk_bare_f0_1_f64_v5 }} |
| bare | 0.05 | 64-bit | 4 | {{ hvj_chk_bare_f0_05_f64_v4 }} |
| abutting | 0.07 | 64-bit | 1 | {{ hvj_chk_abut_f0_07 }} |
| abutting | 0.05 | 64-bit | 1 | {{ hvj_chk_abut_f0_05 }} |
| abutting | 0.02 | 64-bit | 1 | {{ hvj_chk_abut_f0_02 }} |
~~~

The prediction cases use two meshes. A case whose P-well abuts the N-well under assumption A
has 0.07 µm at the drawn edges and 1.5 V steps. Every other case has 0.1 µm and 3 V steps.

The main record holds one section on both meshes. NT20 under A and NW0 under B are the same
abutting junction. It breaks down at {{ hvj_NT20_A_edge }} V on the fine mesh and at
{{ hvj_NW0_B_edge }} V on the coarse one. The coarse value is {{ hvj_mesh_pair_pct }} % higher. The junctions of
{numref}`tab-hvj-pwell` with a P-well within 1.5 µm carry that mesh error.

(hvj-results)=

## Results

A structure's name starts with N (N-well) or D (deep N-well). The letters after it name what
is drawn, and the number is its size in µm, with `p` for the decimal point. Each table gives
the breakdown voltage in volts. The column is the process assumption; `corner` marks the
cylindrical corner section, and the other columns are the straight edge.

A value written `> V` is a sweep whose integral stayed below 1 up to V, the highest bias
solved. The sweep ends at 60 V for a case with an abutting P-well and at 150 V otherwise.
Each value comes from a curve like those of {numref}`hvj-integral-figure`.

### Plain terminations

NT structures have a bare termination of the named length between the well and the substrate
tap. NC structures have a 20 µm termination and the named corner radius. Every other corner
has a radius of 8 µm. A name ending in `b` is a second copy of a structure, and NT20L is NT20
with a wider lead; their sections are the original's. The values are in
{numref}`tab-hvj-bare`, and the corner values are
plotted against the radius in {numref}`hvj-corners-figure`.

~~~{table} Breakdown voltage (V) of the plain terminations.
:name: tab-hvj-bare

| Structure | A | B | B corner | Bq | Bq corner |
|---|---|---|---|---|---|
| NC0 | {{ hvj_NC0_A_edge }} | {{ hvj_NC0_B_edge }} | {{ hvj_NC0_B_corner }} | {{ hvj_NC0_Bq_edge }} | {{ hvj_NC0_Bq_corner }} |
| NC15 | {{ hvj_NC15_A_edge }} | {{ hvj_NC15_B_edge }} | {{ hvj_NC15_B_corner }} | {{ hvj_NC15_Bq_edge }} | {{ hvj_NC15_Bq_corner }} |
| NT10 | {{ hvj_NT10_A_edge }} | {{ hvj_NT10_B_edge }} | {{ hvj_NT10_B_corner }} | {{ hvj_NT10_Bq_edge }} | {{ hvj_NT10_Bq_corner }} |
| NT20 | {{ hvj_NT20_A_edge }} | {{ hvj_NT20_B_edge }} | {{ hvj_NT20_B_corner }} | {{ hvj_NT20_Bq_edge }} | {{ hvj_NT20_Bq_corner }} |
| NT20L | {{ hvj_NT20L_A_edge }} | {{ hvj_NT20L_B_edge }} | {{ hvj_NT20L_B_corner }} | {{ hvj_NT20L_Bq_edge }} | {{ hvj_NT20L_Bq_corner }} |
| NT20b | {{ hvj_NT20b_A_edge }} | {{ hvj_NT20b_B_edge }} | {{ hvj_NT20b_B_corner }} | {{ hvj_NT20b_Bq_edge }} | {{ hvj_NT20b_Bq_corner }} |
| NT35 | {{ hvj_NT35_A_edge }} | {{ hvj_NT35_B_edge }} | {{ hvj_NT35_B_corner }} | {{ hvj_NT35_Bq_edge }} | {{ hvj_NT35_Bq_corner }} |
| NT5 | {{ hvj_NT5_A_edge }} | {{ hvj_NT5_B_edge }} | {{ hvj_NT5_B_corner }} | {{ hvj_NT5_Bq_edge }} | {{ hvj_NT5_Bq_corner }} |
~~~

```{figure} /_generated/hv-junction/corners-light.svg
:figclass: only-light
:name: hvj-corners-figure
:alt: Breakdown voltage against corner radius from 2 to 15 µm. The N-well corner rises with the radius towards its straight-edge line. The deep N-well lies higher.

Breakdown voltage of the corner section against its radius, under assumption B, for the plain
20 µm termination of an N-well and of a deep N-well. The horizontal lines are the straight
edges ({repo}`records <results/hv-junction>`).
```

```{figure} /_generated/hv-junction/corners-dark.svg
:figclass: only-dark
:alt: Breakdown voltage against corner radius from 2 to 15 µm. The N-well corner rises with the radius towards its straight-edge line. The deep N-well lies higher.

Breakdown voltage of the corner section against its radius, under assumption B, for the plain
20 µm termination of an N-well and of a deep N-well. The horizontal lines are the straight
edges ({repo}`records <results/hv-junction>`).
```

### Drawn P-well

NW structures draw a P-well at the named distance from the N-well edge. The values are in
{numref}`tab-hvj-pwell`. Assumption B is plotted against the distance in
{numref}`hvj-pwell-figure`. Under assumption A the generated P-well abuts the N-well at every distance.

~~~{table} Breakdown voltage (V) of the N-wells with a drawn P-well.
:name: tab-hvj-pwell

| Structure | A | B | B corner | Bq | Bq corner |
|---|---|---|---|---|---|
| NW0 | {{ hvj_NW0_A_edge }} | {{ hvj_NW0_B_edge }} | {{ hvj_NW0_B_corner }} | {{ hvj_NW0_Bq_edge }} | {{ hvj_NW0_Bq_corner }} |
| NW10 | {{ hvj_NW10_A_edge }} | {{ hvj_NW10_B_edge }} | {{ hvj_NW10_B_corner }} | {{ hvj_NW10_Bq_edge }} | {{ hvj_NW10_Bq_corner }} |
| NW1p5 | {{ hvj_NW1p5_A_edge }} | {{ hvj_NW1p5_B_edge }} | {{ hvj_NW1p5_B_corner }} | {{ hvj_NW1p5_Bq_edge }} | {{ hvj_NW1p5_Bq_corner }} |
| NW3 | {{ hvj_NW3_A_edge }} | {{ hvj_NW3_B_edge }} | {{ hvj_NW3_B_corner }} | {{ hvj_NW3_Bq_edge }} | {{ hvj_NW3_Bq_corner }} |
| NW6 | {{ hvj_NW6_A_edge }} | {{ hvj_NW6_B_edge }} | {{ hvj_NW6_B_corner }} | {{ hvj_NW6_Bq_edge }} | {{ hvj_NW6_Bq_corner }} |
~~~

```{figure} /_generated/hv-junction/pwell-distance-light.svg
:figclass: only-light
:name: hvj-pwell-figure
:alt: Breakdown voltage against the drawn P-well distance from 0 to 10 µm. Both wells rise with the distance and level off; the deep N-well lies higher.

Breakdown voltage against the distance of a drawn P-well from the well edge, under assumption
B: the straight edge (solid) and the corner section (dashed) of an N-well and of a deep N-well
({repo}`records <results/hv-junction>`).
```

```{figure} /_generated/hv-junction/pwell-distance-dark.svg
:figclass: only-dark
:alt: Breakdown voltage against the drawn P-well distance from 0 to 10 µm. Both wells rise with the distance and level off; the deep N-well lies higher.

Breakdown voltage against the distance of a drawn P-well from the well edge, under assumption
B: the straight edge (solid) and the corner section (dashed) of an N-well and of a deep N-well
({repo}`records <results/hv-junction>`).
```

### NAT layer

NA structures draw a NAT layer at the named distance from the N-well edge, as far as the
substrate tap. Under assumption An no P-well lies beside the well, as on the right of
{numref}`hvj-section-figure` with the P-well removed. The values are in
{numref}`tab-hvj-nat`. The rows with M1, M2 or GM1 in the name also carry the plate of the next section.

~~~{table} Breakdown voltage (V) of the N-wells with a NAT layer.
:name: tab-hvj-nat

| Structure | A | An | An corner | Bq | Bq corner |
|---|---|---|---|---|---|
| NA0p6 | {{ hvj_NA0p6_A_edge }} | {{ hvj_NA0p6_An_edge }} | {{ hvj_NA0p6_An_corner }} | {{ hvj_NA0p6_Bq_edge }} | {{ hvj_NA0p6_Bq_corner }} |
| NA0p6C0 | {{ hvj_NA0p6C0_A_edge }} | {{ hvj_NA0p6C0_An_edge }} | {{ hvj_NA0p6C0_An_corner }} | {{ hvj_NA0p6C0_Bq_edge }} | {{ hvj_NA0p6C0_Bq_corner }} |
| NA0p6T10 | {{ hvj_NA0p6T10_A_edge }} | {{ hvj_NA0p6T10_An_edge }} | {{ hvj_NA0p6T10_An_corner }} | {{ hvj_NA0p6T10_Bq_edge }} | {{ hvj_NA0p6T10_Bq_corner }} |
| NA0p6T35 | {{ hvj_NA0p6T35_A_edge }} | {{ hvj_NA0p6T35_An_edge }} | {{ hvj_NA0p6T35_An_corner }} | {{ hvj_NA0p6T35_Bq_edge }} | {{ hvj_NA0p6T35_Bq_corner }} |
| NA0p6b | {{ hvj_NA0p6b_A_edge }} | {{ hvj_NA0p6b_An_edge }} | {{ hvj_NA0p6b_An_corner }} | {{ hvj_NA0p6b_Bq_edge }} | {{ hvj_NA0p6b_Bq_corner }} |
| NA2 | {{ hvj_NA2_A_edge }} | {{ hvj_NA2_An_edge }} | {{ hvj_NA2_An_corner }} | {{ hvj_NA2_Bq_edge }} | {{ hvj_NA2_Bq_corner }} |
| NA4 | {{ hvj_NA4_A_edge }} | {{ hvj_NA4_An_edge }} | {{ hvj_NA4_An_corner }} | {{ hvj_NA4_Bq_edge }} | {{ hvj_NA4_Bq_corner }} |
| NAGM1@g0 | {{ hvj_NAGM1_g0_A_edge }} | {{ hvj_NAGM1_g0_An_edge }} | {{ hvj_NAGM1_g0_An_corner }} | {{ hvj_NAGM1_g0_Bq_edge }} | {{ hvj_NAGM1_g0_Bq_corner }} |
| NAGM1@gw | {{ hvj_NAGM1_gw_A_edge }} | {{ hvj_NAGM1_gw_An_edge }} | {{ hvj_NAGM1_gw_An_corner }} | {{ hvj_NAGM1_gw_Bq_edge }} | {{ hvj_NAGM1_gw_Bq_corner }} |
| NAM1_10 | {{ hvj_NAM1_10_A_edge }} | {{ hvj_NAM1_10_An_edge }} | {{ hvj_NAM1_10_An_corner }} | {{ hvj_NAM1_10_Bq_edge }} | {{ hvj_NAM1_10_Bq_corner }} |
| NAM1_3 | {{ hvj_NAM1_3_A_edge }} | {{ hvj_NAM1_3_An_edge }} | {{ hvj_NAM1_3_An_corner }} | {{ hvj_NAM1_3_Bq_edge }} | {{ hvj_NAM1_3_Bq_corner }} |
| NAM1_6 | {{ hvj_NAM1_6_A_edge }} | {{ hvj_NAM1_6_An_edge }} | {{ hvj_NAM1_6_An_corner }} | {{ hvj_NAM1_6_Bq_edge }} | {{ hvj_NAM1_6_Bq_corner }} |
| NAM2_12 | {{ hvj_NAM2_12_A_edge }} | {{ hvj_NAM2_12_An_edge }} | {{ hvj_NAM2_12_An_corner }} | {{ hvj_NAM2_12_Bq_edge }} | {{ hvj_NAM2_12_Bq_corner }} |
| NAM2_6 | {{ hvj_NAM2_6_A_edge }} | {{ hvj_NAM2_6_An_edge }} | {{ hvj_NAM2_6_An_corner }} | {{ hvj_NAM2_6_Bq_edge }} | {{ hvj_NAM2_6_Bq_corner }} |
~~~

### Field plates

NP, NM1 and NM2 structures carry one plate of Poly2, Metal1 or Metal2, tied to the well. The
number is the plate's reach beyond the well edge. NPM12 carries one plate on each of the three
layers.

A gated structure (NGM1, NGP4) has its plate on its own pad. The suffix `@g0` holds the plate at
0 V, and `@gw` ties it to the well. The values are in {numref}`tab-hvj-plates`. The single
plates are plotted against their length in {numref}`hvj-plates-figure`.

~~~{table} Breakdown voltage (V) of the N-wells with field plates.
:name: tab-hvj-plates

| Structure | A | B | B corner | Bq | Bq corner |
|---|---|---|---|---|---|
| NGM1@g0 | {{ hvj_NGM1_g0_A_edge }} | {{ hvj_NGM1_g0_B_edge }} | {{ hvj_NGM1_g0_B_corner }} | {{ hvj_NGM1_g0_Bq_edge }} | {{ hvj_NGM1_g0_Bq_corner }} |
| NGM1@gw | {{ hvj_NGM1_gw_A_edge }} | {{ hvj_NGM1_gw_B_edge }} | {{ hvj_NGM1_gw_B_corner }} | {{ hvj_NGM1_gw_Bq_edge }} | {{ hvj_NGM1_gw_Bq_corner }} |
| NGP4@g0 | {{ hvj_NGP4_g0_A_edge }} | {{ hvj_NGP4_g0_B_edge }} | {{ hvj_NGP4_g0_B_corner }} | {{ hvj_NGP4_g0_Bq_edge }} | {{ hvj_NGP4_g0_Bq_corner }} |
| NGP4@gw | {{ hvj_NGP4_gw_A_edge }} | {{ hvj_NGP4_gw_B_edge }} | {{ hvj_NGP4_gw_B_corner }} | {{ hvj_NGP4_gw_Bq_edge }} | {{ hvj_NGP4_gw_Bq_corner }} |
| NM1_10 | {{ hvj_NM1_10_A_edge }} | {{ hvj_NM1_10_B_edge }} | {{ hvj_NM1_10_B_corner }} | {{ hvj_NM1_10_Bq_edge }} | {{ hvj_NM1_10_Bq_corner }} |
| NM1_3 | {{ hvj_NM1_3_A_edge }} | {{ hvj_NM1_3_B_edge }} | {{ hvj_NM1_3_B_corner }} | {{ hvj_NM1_3_Bq_edge }} | {{ hvj_NM1_3_Bq_corner }} |
| NM1_6 | {{ hvj_NM1_6_A_edge }} | {{ hvj_NM1_6_B_edge }} | {{ hvj_NM1_6_B_corner }} | {{ hvj_NM1_6_Bq_edge }} | {{ hvj_NM1_6_Bq_corner }} |
| NM2_12 | {{ hvj_NM2_12_A_edge }} | {{ hvj_NM2_12_B_edge }} | {{ hvj_NM2_12_B_corner }} | {{ hvj_NM2_12_Bq_edge }} | {{ hvj_NM2_12_Bq_corner }} |
| NM2_6 | {{ hvj_NM2_6_A_edge }} | {{ hvj_NM2_6_B_edge }} | {{ hvj_NM2_6_B_corner }} | {{ hvj_NM2_6_Bq_edge }} | {{ hvj_NM2_6_Bq_corner }} |
| NP1 | {{ hvj_NP1_A_edge }} | {{ hvj_NP1_B_edge }} | {{ hvj_NP1_B_corner }} | {{ hvj_NP1_Bq_edge }} | {{ hvj_NP1_Bq_corner }} |
| NP2 | {{ hvj_NP2_A_edge }} | {{ hvj_NP2_B_edge }} | {{ hvj_NP2_B_corner }} | {{ hvj_NP2_Bq_edge }} | {{ hvj_NP2_Bq_corner }} |
| NP4 | {{ hvj_NP4_A_edge }} | {{ hvj_NP4_B_edge }} | {{ hvj_NP4_B_corner }} | {{ hvj_NP4_Bq_edge }} | {{ hvj_NP4_Bq_corner }} |
| NPM12 | {{ hvj_NPM12_A_edge }} | {{ hvj_NPM12_B_edge }} | {{ hvj_NPM12_B_corner }} | {{ hvj_NPM12_Bq_edge }} | {{ hvj_NPM12_Bq_corner }} |
~~~

```{figure} /_generated/hv-junction/plates-light.svg
:figclass: only-light
:name: hvj-plates-figure
:alt: Breakdown voltage against plate length from 0 to 12 µm for three layers. Metal1 rises highest, Metal2 less, and Poly2 rises at first and then falls.

Breakdown voltage against the reach of one field plate beyond the N-well edge, under assumption
B, by layer: the straight edge (solid) and the corner section (dashed). Length 0 is NT20
({repo}`records <results/hv-junction>`).
```

```{figure} /_generated/hv-junction/plates-dark.svg
:figclass: only-dark
:alt: Breakdown voltage against plate length from 0 to 12 µm for three layers. Metal1 rises highest, Metal2 less, and Poly2 rises at first and then falls.

Breakdown voltage against the reach of one field plate beyond the N-well edge, under assumption
B, by layer: the straight edge (solid) and the corner section (dashed). Length 0 is NT20
({repo}`records <results/hv-junction>`).
```

### Floating rings

NR structures surround the N-well with floating N-well rings. The digit after NR is the number
of rings. The values are in {numref}`tab-hvj-rings`. Assumption B is plotted against the ring
count and against the gap of a single ring in {numref}`hvj-rings-figure`.

~~~{table} Breakdown voltage (V) of the N-wells with floating rings.
:name: tab-hvj-rings

| Structure | A | B | B corner | Bq | Bq corner |
|---|---|---|---|---|---|
| NR1S2 | {{ hvj_NR1S2_A_edge }} | {{ hvj_NR1S2_B_edge }} | {{ hvj_NR1S2_B_corner }} | {{ hvj_NR1S2_Bq_edge }} | {{ hvj_NR1S2_Bq_corner }} |
| NR1S3 | {{ hvj_NR1S3_A_edge }} | {{ hvj_NR1S3_B_edge }} | {{ hvj_NR1S3_B_corner }} | {{ hvj_NR1S3_Bq_edge }} | {{ hvj_NR1S3_Bq_corner }} |
| NR1_1p4 | {{ hvj_NR1_1p4_A_edge }} | {{ hvj_NR1_1p4_B_edge }} | {{ hvj_NR1_1p4_B_corner }} | {{ hvj_NR1_1p4_Bq_edge }} | {{ hvj_NR1_1p4_Bq_corner }} |
| NR1_2 | {{ hvj_NR1_2_A_edge }} | {{ hvj_NR1_2_B_edge }} | {{ hvj_NR1_2_B_corner }} | {{ hvj_NR1_2_Bq_edge }} | {{ hvj_NR1_2_Bq_corner }} |
| NR1_3 | {{ hvj_NR1_3_A_edge }} | {{ hvj_NR1_3_B_edge }} | {{ hvj_NR1_3_B_corner }} | {{ hvj_NR1_3_Bq_edge }} | {{ hvj_NR1_3_Bq_corner }} |
| NR3M1 | {{ hvj_NR3M1_A_edge }} | {{ hvj_NR3M1_B_edge }} | {{ hvj_NR3M1_B_corner }} | {{ hvj_NR3M1_Bq_edge }} | {{ hvj_NR3M1_Bq_corner }} |
| NR3W1 | {{ hvj_NR3W1_A_edge }} | {{ hvj_NR3W1_B_edge }} | {{ hvj_NR3W1_B_corner }} | {{ hvj_NR3W1_Bq_edge }} | {{ hvj_NR3W1_Bq_corner }} |
| NR3W3 | {{ hvj_NR3W3_A_edge }} | {{ hvj_NR3W3_B_edge }} | {{ hvj_NR3W3_B_corner }} | {{ hvj_NR3W3_Bq_edge }} | {{ hvj_NR3W3_Bq_corner }} |
| NR3_1p5 | {{ hvj_NR3_1p5_A_edge }} | {{ hvj_NR3_1p5_B_edge }} | {{ hvj_NR3_1p5_B_corner }} | {{ hvj_NR3_1p5_Bq_edge }} | {{ hvj_NR3_1p5_Bq_corner }} |
| NR3_2 | {{ hvj_NR3_2_A_edge }} | {{ hvj_NR3_2_B_edge }} | {{ hvj_NR3_2_B_corner }} | {{ hvj_NR3_2_Bq_edge }} | {{ hvj_NR3_2_Bq_corner }} |
| NR4S | {{ hvj_NR4S_A_edge }} | {{ hvj_NR4S_B_edge }} | {{ hvj_NR4S_B_corner }} | {{ hvj_NR4S_Bq_edge }} | {{ hvj_NR4S_Bq_corner }} |
| NR5_1p4 | {{ hvj_NR5_1p4_A_edge }} | {{ hvj_NR5_1p4_B_edge }} | {{ hvj_NR5_1p4_B_corner }} | {{ hvj_NR5_1p4_Bq_edge }} | {{ hvj_NR5_1p4_Bq_corner }} |
| NR5_2 | {{ hvj_NR5_2_A_edge }} | {{ hvj_NR5_2_B_edge }} | {{ hvj_NR5_2_B_corner }} | {{ hvj_NR5_2_Bq_edge }} | {{ hvj_NR5_2_Bq_corner }} |
~~~

```{figure} /_generated/hv-junction/rings-light.svg
:figclass: only-light
:name: hvj-rings-figure
:alt: Two panels of breakdown voltage. Left, it rises with the number of rings. Right, against the gap of one ring, it is highest at the middle gap.

Breakdown voltage under assumption B against the number of 2 µm wide floating rings whose
first gap is 2 µm (left), and against the gap of a single ring (right): the straight edge
(solid) and the corner section (dashed) ({repo}`records <results/hv-junction>`).
```

```{figure} /_generated/hv-junction/rings-dark.svg
:figclass: only-dark
:alt: Two panels of breakdown voltage. Left, it rises with the number of rings. Right, against the gap of one ring, it is highest at the middle gap.

Breakdown voltage under assumption B against the number of 2 µm wide floating rings whose
first gap is 2 µm (left), and against the gap of a single ring (right): the straight edge
(solid) and the corner section (dashed) ({repo}`records <results/hv-junction>`).
```

### Deep N-well

D structures repeat the terminations around a deep N-well: DT (termination length), DC
(corner radius), DW (drawn P-well), DM and DPM (plates), DGM (gated plate). DAo1 structures
draw a NAT layer that overlaps the deep N-well edge by 1 µm. The values are in
{numref}`tab-hvj-deep`. Their corner and P-well values are also in {numref}`hvj-corners-figure` and
{numref}`hvj-pwell-figure`.

~~~{table} Breakdown voltage (V) of the deep N-well structures.
:name: tab-hvj-deep

| Structure | A | A corner | B | B corner | Bq |
|---|---|---|---|---|---|
| DAo1 | {{ hvj_DAo1_A_edge }} | {{ hvj_DAo1_A_corner }} | {{ hvj_DAo1_B_edge }} | {{ hvj_DAo1_B_corner }} | {{ hvj_DAo1_Bq_edge }} |
| DAo1C0 | {{ hvj_DAo1C0_A_edge }} | {{ hvj_DAo1C0_A_corner }} | {{ hvj_DAo1C0_B_edge }} | {{ hvj_DAo1C0_B_corner }} | {{ hvj_DAo1C0_Bq_edge }} |
| DAo1M1_6 | {{ hvj_DAo1M1_6_A_edge }} | {{ hvj_DAo1M1_6_A_corner }} | {{ hvj_DAo1M1_6_B_edge }} | {{ hvj_DAo1M1_6_B_corner }} | {{ hvj_DAo1M1_6_Bq_edge }} |
| DAo1T35 | {{ hvj_DAo1T35_A_edge }} | {{ hvj_DAo1T35_A_corner }} | {{ hvj_DAo1T35_B_edge }} | {{ hvj_DAo1T35_B_corner }} | {{ hvj_DAo1T35_Bq_edge }} |
| DC0 | {{ hvj_DC0_A_edge }} | {{ hvj_DC0_A_corner }} | {{ hvj_DC0_B_edge }} | {{ hvj_DC0_B_corner }} | {{ hvj_DC0_Bq_edge }} |
| DC15 | {{ hvj_DC15_A_edge }} | {{ hvj_DC15_A_corner }} | {{ hvj_DC15_B_edge }} | {{ hvj_DC15_B_corner }} | {{ hvj_DC15_Bq_edge }} |
| DGM1@g0 | {{ hvj_DGM1_g0_A_edge }} | {{ hvj_DGM1_g0_A_corner }} | {{ hvj_DGM1_g0_B_edge }} | {{ hvj_DGM1_g0_B_corner }} | {{ hvj_DGM1_g0_Bq_edge }} |
| DGM1@gw | {{ hvj_DGM1_gw_A_edge }} | {{ hvj_DGM1_gw_A_corner }} | {{ hvj_DGM1_gw_B_edge }} | {{ hvj_DGM1_gw_B_corner }} | {{ hvj_DGM1_gw_Bq_edge }} |
| DM1_10 | {{ hvj_DM1_10_A_edge }} | {{ hvj_DM1_10_A_corner }} | {{ hvj_DM1_10_B_edge }} | {{ hvj_DM1_10_B_corner }} | {{ hvj_DM1_10_Bq_edge }} |
| DM1_3 | {{ hvj_DM1_3_A_edge }} | {{ hvj_DM1_3_A_corner }} | {{ hvj_DM1_3_B_edge }} | {{ hvj_DM1_3_B_corner }} | {{ hvj_DM1_3_Bq_edge }} |
| DM1_6 | {{ hvj_DM1_6_A_edge }} | {{ hvj_DM1_6_A_corner }} | {{ hvj_DM1_6_B_edge }} | {{ hvj_DM1_6_B_corner }} | {{ hvj_DM1_6_Bq_edge }} |
| DPM12 | {{ hvj_DPM12_A_edge }} | {{ hvj_DPM12_A_corner }} | {{ hvj_DPM12_B_edge }} | {{ hvj_DPM12_B_corner }} | {{ hvj_DPM12_Bq_edge }} |
| DT10 | {{ hvj_DT10_A_edge }} | {{ hvj_DT10_A_corner }} | {{ hvj_DT10_B_edge }} | {{ hvj_DT10_B_corner }} | {{ hvj_DT10_Bq_edge }} |
| DT20 | {{ hvj_DT20_A_edge }} | {{ hvj_DT20_A_corner }} | {{ hvj_DT20_B_edge }} | {{ hvj_DT20_B_corner }} | {{ hvj_DT20_Bq_edge }} |
| DT20b | {{ hvj_DT20b_A_edge }} | {{ hvj_DT20b_A_corner }} | {{ hvj_DT20b_B_edge }} | {{ hvj_DT20b_B_corner }} | {{ hvj_DT20b_Bq_edge }} |
| DT2p6 | {{ hvj_DT2p6_A_edge }} | {{ hvj_DT2p6_A_corner }} | {{ hvj_DT2p6_B_edge }} | {{ hvj_DT2p6_B_corner }} | {{ hvj_DT2p6_Bq_edge }} |
| DT35 | {{ hvj_DT35_A_edge }} | {{ hvj_DT35_A_corner }} | {{ hvj_DT35_B_edge }} | {{ hvj_DT35_B_corner }} | {{ hvj_DT35_Bq_edge }} |
| DT5 | {{ hvj_DT5_A_edge }} | {{ hvj_DT5_A_corner }} | {{ hvj_DT5_B_edge }} | {{ hvj_DT5_B_corner }} | {{ hvj_DT5_Bq_edge }} |
| DW1p5 | {{ hvj_DW1p5_A_edge }} | {{ hvj_DW1p5_A_corner }} | {{ hvj_DW1p5_B_edge }} | {{ hvj_DW1p5_B_corner }} | {{ hvj_DW1p5_Bq_edge }} |
| DW3 | {{ hvj_DW3_A_edge }} | {{ hvj_DW3_A_corner }} | {{ hvj_DW3_B_edge }} | {{ hvj_DW3_B_corner }} | {{ hvj_DW3_Bq_edge }} |
| DW6 | {{ hvj_DW6_A_edge }} | {{ hvj_DW6_A_corner }} | {{ hvj_DW6_B_edge }} | {{ hvj_DW6_B_corner }} | {{ hvj_DW6_Bq_edge }} |
~~~

### Doping family

Ten structures are rerun under the family members of {ref}`hvj-process`. The members of
assumption B are in {numref}`tab-hvj-family-b`. Those of assumption A are in
{numref}`tab-hvj-family-a`. Both hold the straight edge. The spread along a row is the range that the
unpublished doping leaves open, on the section of {numref}`hvj-section-figure`.

~~~{table} Breakdown voltage (V) under the family members of assumption B.
:name: tab-hvj-family-b

| Structure | Blo | B | Bhi | Bdp | Bq3 |
|---|---|---|---|---|---|
| NT20 | {{ hvj_NT20_Blo_edge }} | {{ hvj_NT20_B_edge }} | {{ hvj_NT20_Bhi_edge }} | {{ hvj_NT20_Bdp_edge }} | {{ hvj_NT20_Bq3_edge }} |
| NC0 | {{ hvj_NC0_Blo_edge }} | {{ hvj_NC0_B_edge }} | {{ hvj_NC0_Bhi_edge }} | {{ hvj_NC0_Bdp_edge }} | {{ hvj_NC0_Bq3_edge }} |
| NA0p6 | {{ hvj_NA0p6_Blo_edge }} | {{ hvj_NA0p6_B_edge }} | {{ hvj_NA0p6_Bhi_edge }} | {{ hvj_NA0p6_Bdp_edge }} | {{ hvj_NA0p6_Bq3_edge }} |
| NAM1_6 | {{ hvj_NAM1_6_Blo_edge }} | {{ hvj_NAM1_6_B_edge }} | {{ hvj_NAM1_6_Bhi_edge }} | {{ hvj_NAM1_6_Bdp_edge }} | {{ hvj_NAM1_6_Bq3_edge }} |
| NW3 | {{ hvj_NW3_Blo_edge }} | {{ hvj_NW3_B_edge }} | {{ hvj_NW3_Bhi_edge }} | {{ hvj_NW3_Bdp_edge }} | {{ hvj_NW3_Bq3_edge }} |
| NR3_2 | {{ hvj_NR3_2_Blo_edge }} | {{ hvj_NR3_2_B_edge }} | {{ hvj_NR3_2_Bhi_edge }} | {{ hvj_NR3_2_Bdp_edge }} | {{ hvj_NR3_2_Bq3_edge }} |
| NM1_6 | {{ hvj_NM1_6_Blo_edge }} | {{ hvj_NM1_6_B_edge }} | {{ hvj_NM1_6_Bhi_edge }} | {{ hvj_NM1_6_Bdp_edge }} | {{ hvj_NM1_6_Bq3_edge }} |
| DT20 | {{ hvj_DT20_Blo_edge }} | {{ hvj_DT20_B_edge }} | {{ hvj_DT20_Bhi_edge }} | {{ hvj_DT20_Bdp_edge }} | {{ hvj_DT20_Bq3_edge }} |
| DM1_6 | {{ hvj_DM1_6_Blo_edge }} | {{ hvj_DM1_6_B_edge }} | {{ hvj_DM1_6_Bhi_edge }} | {{ hvj_DM1_6_Bdp_edge }} | {{ hvj_DM1_6_Bq3_edge }} |
| DAo1 | {{ hvj_DAo1_Blo_edge }} | {{ hvj_DAo1_B_edge }} | {{ hvj_DAo1_Bhi_edge }} | {{ hvj_DAo1_Bdp_edge }} | {{ hvj_DAo1_Bq3_edge }} |
~~~

~~~{table} Breakdown voltage (V) under the family members of assumption A.
:name: tab-hvj-family-a

| Structure | Alo | A | Ahi |
|---|---|---|---|
| NT20 | {{ hvj_NT20_Alo_edge }} | {{ hvj_NT20_A_edge }} | {{ hvj_NT20_Ahi_edge }} |
| NC0 | {{ hvj_NC0_Alo_edge }} | {{ hvj_NC0_A_edge }} | {{ hvj_NC0_Ahi_edge }} |
| NA0p6 | {{ hvj_NA0p6_Alo_edge }} | {{ hvj_NA0p6_A_edge }} | {{ hvj_NA0p6_Ahi_edge }} |
| NAM1_6 | {{ hvj_NAM1_6_Alo_edge }} | {{ hvj_NAM1_6_A_edge }} | {{ hvj_NAM1_6_Ahi_edge }} |
| NW3 | {{ hvj_NW3_Alo_edge }} | {{ hvj_NW3_A_edge }} | {{ hvj_NW3_Ahi_edge }} |
| NR3_2 | {{ hvj_NR3_2_Alo_edge }} | {{ hvj_NR3_2_A_edge }} | {{ hvj_NR3_2_Ahi_edge }} |
| NM1_6 | {{ hvj_NM1_6_Alo_edge }} | {{ hvj_NM1_6_A_edge }} | {{ hvj_NM1_6_Ahi_edge }} |
| DT20 | {{ hvj_DT20_Alo_edge }} | {{ hvj_DT20_A_edge }} | {{ hvj_DT20_Ahi_edge }} |
| DM1_6 | {{ hvj_DM1_6_Alo_edge }} | {{ hvj_DM1_6_A_edge }} | {{ hvj_DM1_6_Ahi_edge }} |
| DAo1 | {{ hvj_DAo1_Alo_edge }} | {{ hvj_DAo1_A_edge }} | {{ hvj_DAo1_Ahi_edge }} |
~~~

(hvj-charon)=

## Charon cross-check

{{ Charon }} solves six of the cases on {{ DEVSIM }}'s own nodes, written as a triangle mesh
({repo}`experiments/hv-junction/charon_mesh.py`). Its sweep includes impact ionisation in the
continuity equations, so its current rises at breakdown
({repo}`experiments/hv-junction/charon_run.py`). Three Charon values stand beside the DEVSIM
value of {ref}`hvj-results` in {numref}`tab-hvj-charon`:

- the bias at which the current is 100 times its low-bias trend;
- the bias at which the integral {math:numref}`eq-hvj-integral` reaches 1 on Charon's potential;
- the highest bias Charon solved.

Charon's control-volume scheme takes the hole coefficient's low-field values at every field
({repo}`experiments/hv-junction/charon_deck.py`). The electron coefficient is that of
{math:numref}`eq-hvj-alpha`. Each case's DEVSIM curve is of the kind in
{numref}`hvj-integral-figure`.

~~~{table} Breakdown voltage (V): DEVSIM's integral against three Charon values.
:name: tab-hvj-charon

| Case | DEVSIM | Charon current | Charon integral | Charon last bias |
|---|---|---|---|---|
| NT20, A | {{ hvj_NT20_A_edge }} | {{ hvj_NT20_A_edge_charon_current }} | {{ hvj_NT20_A_edge_charon_integral }} | {{ hvj_NT20_A_edge_charon_last }} |
| NT20, B | {{ hvj_NT20_B_edge }} | {{ hvj_NT20_B_edge_charon_current }} | {{ hvj_NT20_B_edge_charon_integral }} | {{ hvj_NT20_B_edge_charon_last }} |
| NW1p5, B | {{ hvj_NW1p5_B_edge }} | {{ hvj_NW1p5_B_edge_charon_current }} | {{ hvj_NW1p5_B_edge_charon_integral }} | {{ hvj_NW1p5_B_edge_charon_last }} |
| NM1_6, B | {{ hvj_NM1_6_B_edge }} | {{ hvj_NM1_6_B_edge_charon_current }} | {{ hvj_NM1_6_B_edge_charon_integral }} | {{ hvj_NM1_6_B_edge_charon_last }} |
| NR1_2, B | {{ hvj_NR1_2_B_edge }} | {{ hvj_NR1_2_B_edge_charon_current }} | {{ hvj_NR1_2_B_edge_charon_integral }} | {{ hvj_NR1_2_B_edge_charon_last }} |
| DT20, B | {{ hvj_DT20_B_edge }} | {{ hvj_DT20_B_edge_charon_current }} | {{ hvj_DT20_B_edge_charon_integral }} | {{ hvj_DT20_B_edge_charon_last }} |
~~~

(hvj-limits)=

## Limits

- **2D sections.** Each value is one radial section. A corner is a cylinder about one axis
  ({numref}`hvj-corners-figure`); the true corner of a rectangle with rings and plates is 3D.
- **The criterion.** The integral reaching 1 marks the onset of avalanche on DEVSIM's
  potential. The solve carries no avalanche current, so it gives no current-voltage curve
  beyond that bias ({numref}`hvj-integral-figure`).
- **The doping.** The wells are a family set against three published values
  ({numref}`tab-hvj-anchors`), not measured profiles. The family lies above the published
  N-well value and has no member at the deep N-well model's value.
- **The generated P-well.** Assumptions A and B differ by a factor of three or more at most
  N-well structures ({numref}`tab-hvj-bare`). Only silicon decides between them.
- **The mesh.** A junction with a P-well within 1.5 µm changes by {{ hvj_mesh_pair_pct }} %
  between the two prediction meshes ({ref}`hvj-checks`).
- **No silicon data.** No measurement of these structures exists
  ({doc}`/limitations/silicon-validation`).

(hvj-records)=

## Records

Every run goes through {repo}`tools/sandbox-run` with a pinned image
({repo}`experiments/hv-junction/run.py`). The records are under {repo}`results/hv-junction`.
Each holds the commit, the image and the sha256 of every file of the experiment that its runs
shared. The record writer {repo}`experiments/hv-junction/record.py` refuses runs whose pins
differ. {repo}`experiments/hv-junction/README.md` gives the command of each record. The curves of
{numref}`hvj-integral-figure` are read from the main record.

- **main** ({repo}`main.json <results/hv-junction/main.json>`) holds every structure under A,
  Aq, B and Bq. It also holds the NAT structures under An. It has {{ hvj_n_main }} cases, and
  {{ hvj_n_main_missing }} of its runs left no result.
- **supp** reruns those. It also reruns the deep N-wells under A and Aq to 150 V, with a corner
  section. In the main record their sweep ends at 60 V.
- **family** holds the doping family.
- **delta** reruns every case whose parameters the case set has changed since its run.
- **checks** and **diodes** hold the cases of {ref}`hvj-checks`.
- **charon** holds the cases of {ref}`hvj-charon`.

A case takes its value from the last of main, supp, family and delta that holds it. Of the
printed cases, {{ hvj_n_superseded }} come from a run with parameters that
{repo}`experiments/hv-junction/predict.py` has since changed.

The tests {repo}`tests/test_hv_junction.py` check each record's pins against the files at its
commit. They also check each number here against the records.
