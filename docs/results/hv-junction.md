# High-voltage junction terminations

The reverse {term}`breakdown voltage` of a well-to-substrate junction depends on what is drawn
at the well edge. The experiment {repo}`experiments/hv-junction` simulates that edge for the
structures of a test die of the [evampire](https://github.com/mithro/evampire) project. The
structure list is {repo}`experiments/hv-junction/structures.json`. Each structure is an {term}`N-well <n-well>`
or a {term}`deep N-well` in the P substrate, surrounded by one edge termination. The simulated
section of one structure is in {numref}`hvj-section-figure`.

The numbers here are predictions of a 2D model under stated process assumptions. Each
assumption is one typical process; no {term}`process corner <corner>` is simulated. No measured
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
AL. The well contact is swept; the substrate contact stays at 0 V. Each doped box is drawn down
to two standard deviations below its implant peak
({repo}`experiments/hv-junction/hvsite.py`).
```

```{figure} /_generated/hv-junction/section-dark.svg
:figclass: only-dark
:alt: Cross-section with depth downwards. An N-well on the left, a floating N-well ring, a P-well beyond the well edge, trench oxide at the surface, a Metal1 plate above, and two contacts.

The simulated section of an N-well with one floating ring and a Metal1 plate, under assumption
AL. The well contact is swept; the substrate contact stays at 0 V. Each doped box is drawn down
to two standard deviations below its implant peak
({repo}`experiments/hv-junction/hvsite.py`).
```

The script {repo}`experiments/hv-junction/hvsite.py` turns a drawn structure into this section.
The layer heights are those of the {term}`PDK`'s interconnect specification. The trench oxide is
0.32 µm thick and the dielectric under Metal1 is 0.86 µm thick
([dielectric table](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/layout/inter_specs/inter_specs_2_2.html)).
Poly2 is 0.2 µm thick and each metal 0.55 µm
([conductor table](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/layout/inter_specs/inter_specs_2_1.html)).
A Poly2 plate is meshed 10 nm above the trench oxide, so that the dielectric region surrounds
it.

A corner of the well is simulated as the same section in cylindrical coordinates. The axis is
the centre of the corner, and the well edge lies at the corner radius. A drawn radius under
1 µm is simulated at 1 µm.

Every well, ring and tap is a sum of implanted boxes. A box is a peak density times a depth
profile and a lateral profile, {math:numref}`eq-hvj-implant`:

$$
N(x,y)=N_0\,G(y)\,L(x)
$$ (eq-hvj-implant)

where

- $N$ is the {term}`dopant` density of one box, in cm⁻³;
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
- $p$ and $n$ are the {term}`hole` and {term}`electron` densities, in cm⁻³;
- $N_D$ and $N_A$ are the {term}`donor` and {term}`acceptor` densities of {math:numref}`eq-hvj-implant`, in cm⁻³.

A {term}`fixed oxide charge` is a sheet of positive charge on the silicon surface nodes. The
well contact and every plate tied to it
are then swept upwards together, one {term}`sweep` per case ({repo}`experiments/hv-junction/sweep.py`). The curves of
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
implant and a deeper light one. The substrate is uniform at 3.56e15 cm⁻³.

The deep N-well is one implant that peaks 2.55 µm below the surface. Under it lies a P layer
that peaks 4.36 µm down, the deep P layer. The deep N-well's published capacitance and
breakdown voltage need such a layer. The public data do not say whether it lies only under a
deep N-well or under the whole wafer, so both are simulated ({ref}`hvj-assumptions`).

The family is set against the published values of {numref}`tab-hvj-anchors`. The sheet
resistance and the capacitances are computed from the profiles by
{repo}`experiments/hv-junction/profile1d.py`, in the {term}`depletion approximation`. The breakdown
voltages are the simulated cases NT20 and DT20 under assumption AL.

~~~{table} The published anchors of the doping family and what the family gives.
:name: tab-hvj-anchors

| Quantity | Published | Family |
|---|---|---|
| N-well sheet resistance (Ω/sq) | 1000 | {{ hvj_nw_rs }} |
| N-well capacitance at 0 V (fF/µm²) | {{ hvj_nw_c0_model }} | {{ hvj_nw_c0 }} |
| N-well capacitance at 10 V (fF/µm²) | {{ hvj_nw_c10_model }} | {{ hvj_nw_c10 }} |
| Deep N-well capacitance at 0 V (fF/µm²) | {{ hvj_dnw_c0_model }} | {{ hvj_dnw_c0 }} |
| Deep N-well capacitance at 10 V (fF/µm²) | {{ hvj_dnw_c10_model }} | {{ hvj_dnw_c10 }} |
| N-well breakdown voltage (V) | 14 | {{ hvj_NT20_AL_edge }} |
| Deep N-well breakdown voltage (V) | 30.48 | {{ hvj_DT20_AL_edge }} |
~~~

The published sheet resistance runs from 800 to 1200 Ω/sq
([electrical specification 5.1](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/spice/elec_specs/elec_specs_5_1.html)).
The family's value is that of the well below the 0.32 µm of trench oxide. The published
capacitances are those of the diode models `diode_nw2ps_06v0`
([model file](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38461))
and `diode_dw2ps`
([model file](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38512)),
evaluated at the bias. The deep N-well model also gives the 30.48 V.

The published N-well breakdown voltage is 14 V typical and 10 V minimum
([electrical specification 5.5](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/spice/elec_specs/elec_specs_5_5.html)).
The family's abutting junction lies {{ hvj_abut_pct }} % above the typical value.

(hvj-assumptions)=

### P-well, deep P layer and oxide charge

The foundry generates the P-well (LVPWELL) from the drawn layers
([design manual 4.4](https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_04_4.html)).
The generation rule is unpublished, so each structure is simulated under several assumptions
about the {term}`generated P-well`. {numref}`hvj-section-figure` is drawn under assumption AL.
A process name joins one letter group for the P-well with one for the deep P layer:

- **A.** A P-well lies wherever no N-well, deep N-well or {term}`NAT` layer is. It abuts an
  N-well and stays 1.5 µm from a deep N-well
  ([rule LPW.11](https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_07_04.html)).
- **An.** As A, without the P-well strip between an N-well and a NAT layer. The NAT layer
  stays 0.5 µm from an N-well
  ([rule NAT.3](https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_10_05.html)).
- **B.** A P-well lies only where the layout draws one.
- **L.** The deep P layer lies only under a deep N-well.
- **D.** The deep P layer lies under the whole wafer.
- **q.** A fixed oxide charge of 1e11 cm⁻² lies on the silicon surface.

The main cases are AL, AD, BL, BD and BLq, and AnL and AnD for the NAT structures
({repo}`experiments/hv-junction/predict.py`). A case whose P-well abuts the N-well is not run
under D. The cases of the doping family add two suffixes:

- **lo and hi** set the substrate to 2e15 cm⁻³ or 5e15 cm⁻³.
- **q3** sets the fixed oxide charge to 3e11 cm⁻².

(hvj-checks)=

## Checks

### 1D diodes

An abrupt N⁺/P diode has a known answer. In the depletion approximation its field is a
triangle, the shape that the curves of {numref}`hvj-integral-figure` integrate over. The
integral {math:numref}`eq-hvj-integral` over that triangle reaches 1 at one junction potential.
The applied bias is that potential less the {term}`built-in potential`.
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
| abutting | 0.05 | 64-bit | 1 | {{ hvj_chk_abut_f0_05 }} |
| abutting | 0.03 | 64-bit | 1 | {{ hvj_chk_abut_f0_03 }} |
| abutting | 0.02 | 64-bit | 1 | {{ hvj_chk_abut_f0_02 }} |
~~~

The prediction cases use two meshes. A case whose P-well abuts the N-well under assumption A
has 0.03 µm at the drawn edges and 1.5 V steps. Every other case has 0.1 µm and 3 V steps.

The main record holds one section on both meshes. NT20 under AL and NW0 under BL are the same
abutting junction. It breaks down at {{ hvj_NT20_AL_edge }} V on the fine mesh and at
{{ hvj_NW0_BL_edge }} V on the coarse one. The coarse value differs by
{{ hvj_mesh_pair_pct }} %. The junctions of {numref}`tab-hvj-pwell` with a P-well within
1.5 µm carry that mesh error.

(hvj-results)=

## Results

A structure's name starts with N (N-well) or D (deep N-well). The letters after it name what
is drawn, and the number is its size in µm, with `p` for the decimal point. Each table gives
the breakdown voltage in volts. The column is the process assumption; `corner` marks the
cylindrical corner section, and the other columns are the straight edge. The records hold
more processes and shapes of each structure than the tables print.

A value written `> V` is a sweep whose integral stayed below 1 up to V, the highest bias
solved. The sweep ends at 60 V for a case with an abutting P-well and at 150 V otherwise.
Each value comes from a curve like those of {numref}`hvj-integral-figure`.

### Plain terminations

NT structures have a bare termination of the named length between the well and the substrate
tap. NC structures have a 20 µm termination and the named corner radius. Every other corner
has a radius of 8 µm. A drawn radius under 1 µm is simulated at 1 µm.

Three kinds of copy have the section of NT20. A name ending in `b` is a second copy, NT20L
has a wider lead, and NT20V lies in the 6 V gate-oxide area. The values are in
{numref}`tab-hvj-bare`, and the corner values are plotted against the radius in
{numref}`hvj-corners-figure`.

~~~{table} Breakdown voltage (V) of the plain terminations.
:name: tab-hvj-bare

| Structure | AL | BL | BL corner | BD |
|---|---|---|---|---|
| NC0 | {{ hvj_NC0_AL_edge }} | {{ hvj_NC0_BL_edge }} | {{ hvj_NC0_BL_corner }} | {{ hvj_NC0_BD_edge }} |
| NC15 | {{ hvj_NC15_AL_edge }} | {{ hvj_NC15_BL_edge }} | {{ hvj_NC15_BL_corner }} | {{ hvj_NC15_BD_edge }} |
| NT1 | {{ hvj_NT1_AL_edge }} | {{ hvj_NT1_BL_edge }} | {{ hvj_NT1_BL_corner }} | {{ hvj_NT1_BD_edge }} |
| NT10 | {{ hvj_NT10_AL_edge }} | {{ hvj_NT10_BL_edge }} | {{ hvj_NT10_BL_corner }} | {{ hvj_NT10_BD_edge }} |
| NT20 | {{ hvj_NT20_AL_edge }} | {{ hvj_NT20_BL_edge }} | {{ hvj_NT20_BL_corner }} | {{ hvj_NT20_BD_edge }} |
| NT20L | {{ hvj_NT20L_AL_edge }} | {{ hvj_NT20L_BL_edge }} | {{ hvj_NT20L_BL_corner }} | {{ hvj_NT20L_BD_edge }} |
| NT20V | {{ hvj_NT20V_AL_edge }} | {{ hvj_NT20V_BL_edge }} | {{ hvj_NT20V_BL_corner }} | {{ hvj_NT20V_BD_edge }} |
| NT20b | {{ hvj_NT20b_AL_edge }} | {{ hvj_NT20b_BL_edge }} | {{ hvj_NT20b_BL_corner }} | {{ hvj_NT20b_BD_edge }} |
| NT35 | {{ hvj_NT35_AL_edge }} | {{ hvj_NT35_BL_edge }} | {{ hvj_NT35_BL_corner }} | {{ hvj_NT35_BD_edge }} |
| NT5 | {{ hvj_NT5_AL_edge }} | {{ hvj_NT5_BL_edge }} | {{ hvj_NT5_BL_corner }} | {{ hvj_NT5_BD_edge }} |
~~~

```{figure} /_generated/hv-junction/corners-light.svg
:figclass: only-light
:name: hvj-corners-figure
:alt: Breakdown voltage against corner radius from 1 to 15 µm, for an N-well and a deep N-well, each with a horizontal line at its straight-edge value.

Breakdown voltage of the corner section against its radius, under assumption BL, for the plain
20 µm termination of an N-well and of a deep N-well. The horizontal lines are the straight
edges ({repo}`records <results/hv-junction>`).
```

```{figure} /_generated/hv-junction/corners-dark.svg
:figclass: only-dark
:alt: Breakdown voltage against corner radius from 1 to 15 µm, for an N-well and a deep N-well, each with a horizontal line at its straight-edge value.

Breakdown voltage of the corner section against its radius, under assumption BL, for the plain
20 µm termination of an N-well and of a deep N-well. The horizontal lines are the straight
edges ({repo}`records <results/hv-junction>`).
```

### Drawn P-well

NW structures draw a P-well at the named distance from the N-well edge. The values are in
{numref}`tab-hvj-pwell`. Assumption BL is plotted against the distance in
{numref}`hvj-pwell-figure`. Under assumption A the generated P-well abuts the N-well at every
distance.

~~~{table} Breakdown voltage (V) of the N-wells with a drawn P-well.
:name: tab-hvj-pwell

| Structure | AL | BL | BL corner | BD |
|---|---|---|---|---|
| NW0 | {{ hvj_NW0_AL_edge }} | {{ hvj_NW0_BL_edge }} | {{ hvj_NW0_BL_corner }} | {{ hvj_NW0_BD_edge }} |
| NW1p5 | {{ hvj_NW1p5_AL_edge }} | {{ hvj_NW1p5_BL_edge }} | {{ hvj_NW1p5_BL_corner }} | {{ hvj_NW1p5_BD_edge }} |
| NW3 | {{ hvj_NW3_AL_edge }} | {{ hvj_NW3_BL_edge }} | {{ hvj_NW3_BL_corner }} | {{ hvj_NW3_BD_edge }} |
| NW6 | {{ hvj_NW6_AL_edge }} | {{ hvj_NW6_BL_edge }} | {{ hvj_NW6_BL_corner }} | {{ hvj_NW6_BD_edge }} |
~~~

```{figure} /_generated/hv-junction/pwell-distance-light.svg
:figclass: only-light
:name: hvj-pwell-figure
:alt: Breakdown voltage against the drawn P-well distance from 0 to 6 µm, for the straight edge and the corner of an N-well and of a deep N-well.

Breakdown voltage against the distance of a drawn P-well from the well edge, under assumption
BL: the straight edge (solid) and the corner section (dashed) of an N-well and of a deep N-well
({repo}`records <results/hv-junction>`).
```

```{figure} /_generated/hv-junction/pwell-distance-dark.svg
:figclass: only-dark
:alt: Breakdown voltage against the drawn P-well distance from 0 to 6 µm, for the straight edge and the corner of an N-well and of a deep N-well.

Breakdown voltage against the distance of a drawn P-well from the well edge, under assumption
BL: the straight edge (solid) and the corner section (dashed) of an N-well and of a deep N-well
({repo}`records <results/hv-junction>`).
```

### NAT layer

NA structures draw a NAT layer at the named distance from the N-well edge, as far as the
substrate tap. Under assumption An no P-well lies beside the well, as on the right of
{numref}`hvj-section-figure` with the P-well removed. The values are in
{numref}`tab-hvj-nat`. The rows with M1, M2 or GM1 in the name also carry the plate of the
next section.

~~~{table} Breakdown voltage (V) of the N-wells with a NAT layer.
:name: tab-hvj-nat

| Structure | AL | AnL | AnL corner | AnD |
|---|---|---|---|---|
| NA0p6 | {{ hvj_NA0p6_AL_edge }} | {{ hvj_NA0p6_AnL_edge }} | {{ hvj_NA0p6_AnL_corner }} | {{ hvj_NA0p6_AnD_edge }} |
| NA0p6C0 | {{ hvj_NA0p6C0_AL_edge }} | {{ hvj_NA0p6C0_AnL_edge }} | {{ hvj_NA0p6C0_AnL_corner }} | {{ hvj_NA0p6C0_AnD_edge }} |
| NA0p6T10 | {{ hvj_NA0p6T10_AL_edge }} | {{ hvj_NA0p6T10_AnL_edge }} | {{ hvj_NA0p6T10_AnL_corner }} | {{ hvj_NA0p6T10_AnD_edge }} |
| NA0p6T35 | {{ hvj_NA0p6T35_AL_edge }} | {{ hvj_NA0p6T35_AnL_edge }} | {{ hvj_NA0p6T35_AnL_corner }} | {{ hvj_NA0p6T35_AnD_edge }} |
| NA0p6b | {{ hvj_NA0p6b_AL_edge }} | {{ hvj_NA0p6b_AnL_edge }} | {{ hvj_NA0p6b_AnL_corner }} | {{ hvj_NA0p6b_AnD_edge }} |
| NA2 | {{ hvj_NA2_AL_edge }} | {{ hvj_NA2_AnL_edge }} | {{ hvj_NA2_AnL_corner }} | {{ hvj_NA2_AnD_edge }} |
| NA4 | {{ hvj_NA4_AL_edge }} | {{ hvj_NA4_AnL_edge }} | {{ hvj_NA4_AnL_corner }} | {{ hvj_NA4_AnD_edge }} |
| NAGM1@g0 | {{ hvj_NAGM1_g0_AL_edge }} | {{ hvj_NAGM1_g0_AnL_edge }} | {{ hvj_NAGM1_g0_AnL_corner }} | {{ hvj_NAGM1_g0_AnD_edge }} |
| NAGM1@gw | {{ hvj_NAGM1_gw_AL_edge }} | {{ hvj_NAGM1_gw_AnL_edge }} | {{ hvj_NAGM1_gw_AnL_corner }} | {{ hvj_NAGM1_gw_AnD_edge }} |
| NAM1_10 | {{ hvj_NAM1_10_AL_edge }} | {{ hvj_NAM1_10_AnL_edge }} | {{ hvj_NAM1_10_AnL_corner }} | {{ hvj_NAM1_10_AnD_edge }} |
| NAM1_3 | {{ hvj_NAM1_3_AL_edge }} | {{ hvj_NAM1_3_AnL_edge }} | {{ hvj_NAM1_3_AnL_corner }} | {{ hvj_NAM1_3_AnD_edge }} |
| NAM1_6 | {{ hvj_NAM1_6_AL_edge }} | {{ hvj_NAM1_6_AnL_edge }} | {{ hvj_NAM1_6_AnL_corner }} | {{ hvj_NAM1_6_AnD_edge }} |
| NAM2_12 | {{ hvj_NAM2_12_AL_edge }} | {{ hvj_NAM2_12_AnL_edge }} | {{ hvj_NAM2_12_AnL_corner }} | {{ hvj_NAM2_12_AnD_edge }} |
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

| Structure | AL | BL | BL corner | BD |
|---|---|---|---|---|
| NGM1@g0 | {{ hvj_NGM1_g0_AL_edge }} | {{ hvj_NGM1_g0_BL_edge }} | {{ hvj_NGM1_g0_BL_corner }} | {{ hvj_NGM1_g0_BD_edge }} |
| NGM1@gw | {{ hvj_NGM1_gw_AL_edge }} | {{ hvj_NGM1_gw_BL_edge }} | {{ hvj_NGM1_gw_BL_corner }} | {{ hvj_NGM1_gw_BD_edge }} |
| NGP4@g0 | {{ hvj_NGP4_g0_AL_edge }} | {{ hvj_NGP4_g0_BL_edge }} | {{ hvj_NGP4_g0_BL_corner }} | {{ hvj_NGP4_g0_BD_edge }} |
| NGP4@gw | {{ hvj_NGP4_gw_AL_edge }} | {{ hvj_NGP4_gw_BL_edge }} | {{ hvj_NGP4_gw_BL_corner }} | {{ hvj_NGP4_gw_BD_edge }} |
| NM1_10 | {{ hvj_NM1_10_AL_edge }} | {{ hvj_NM1_10_BL_edge }} | {{ hvj_NM1_10_BL_corner }} | {{ hvj_NM1_10_BD_edge }} |
| NM1_3 | {{ hvj_NM1_3_AL_edge }} | {{ hvj_NM1_3_BL_edge }} | {{ hvj_NM1_3_BL_corner }} | {{ hvj_NM1_3_BD_edge }} |
| NM1_6 | {{ hvj_NM1_6_AL_edge }} | {{ hvj_NM1_6_BL_edge }} | {{ hvj_NM1_6_BL_corner }} | {{ hvj_NM1_6_BD_edge }} |
| NM2_12 | {{ hvj_NM2_12_AL_edge }} | {{ hvj_NM2_12_BL_edge }} | {{ hvj_NM2_12_BL_corner }} | {{ hvj_NM2_12_BD_edge }} |
| NM2_6 | {{ hvj_NM2_6_AL_edge }} | {{ hvj_NM2_6_BL_edge }} | {{ hvj_NM2_6_BL_corner }} | {{ hvj_NM2_6_BD_edge }} |
| NP1 | {{ hvj_NP1_AL_edge }} | {{ hvj_NP1_BL_edge }} | {{ hvj_NP1_BL_corner }} | {{ hvj_NP1_BD_edge }} |
| NP2 | {{ hvj_NP2_AL_edge }} | {{ hvj_NP2_BL_edge }} | {{ hvj_NP2_BL_corner }} | {{ hvj_NP2_BD_edge }} |
| NP4 | {{ hvj_NP4_AL_edge }} | {{ hvj_NP4_BL_edge }} | {{ hvj_NP4_BL_corner }} | {{ hvj_NP4_BD_edge }} |
| NPM12 | {{ hvj_NPM12_AL_edge }} | {{ hvj_NPM12_BL_edge }} | {{ hvj_NPM12_BL_corner }} | {{ hvj_NPM12_BD_edge }} |
~~~

```{figure} /_generated/hv-junction/plates-light.svg
:figclass: only-light
:name: hvj-plates-figure
:alt: Breakdown voltage against plate length from 0 to 12 µm, one pair of lines for each of Poly2, Metal1 and Metal2: the straight edge and the corner.

Breakdown voltage against the reach of one field plate beyond the N-well edge, under assumption
BL, by layer: the straight edge (solid) and the corner section (dashed). Length 0 is NT20
({repo}`records <results/hv-junction>`).
```

```{figure} /_generated/hv-junction/plates-dark.svg
:figclass: only-dark
:alt: Breakdown voltage against plate length from 0 to 12 µm, one pair of lines for each of Poly2, Metal1 and Metal2: the straight edge and the corner.

Breakdown voltage against the reach of one field plate beyond the N-well edge, under assumption
BL, by layer: the straight edge (solid) and the corner section (dashed). Length 0 is NT20
({repo}`records <results/hv-junction>`).
```

### Floating rings

NR structures surround the N-well with floating N-well rings. The digit after NR is the number
of rings. The values are in {numref}`tab-hvj-rings`. Assumption BL is plotted against the ring
count and against the gap of a single ring in {numref}`hvj-rings-figure`.

~~~{table} Breakdown voltage (V) of the N-wells with floating rings.
:name: tab-hvj-rings

| Structure | AL | BL | BL corner | BD |
|---|---|---|---|---|
| NR1S12 | {{ hvj_NR1S12_AL_edge }} | {{ hvj_NR1S12_BL_edge }} | {{ hvj_NR1S12_BL_corner }} | {{ hvj_NR1S12_BD_edge }} |
| NR1S2 | {{ hvj_NR1S2_AL_edge }} | {{ hvj_NR1S2_BL_edge }} | {{ hvj_NR1S2_BL_corner }} | {{ hvj_NR1S2_BD_edge }} |
| NR1S3 | {{ hvj_NR1S3_AL_edge }} | {{ hvj_NR1S3_BL_edge }} | {{ hvj_NR1S3_BL_corner }} | {{ hvj_NR1S3_BD_edge }} |
| NR1S5 | {{ hvj_NR1S5_AL_edge }} | {{ hvj_NR1S5_BL_edge }} | {{ hvj_NR1S5_BL_corner }} | {{ hvj_NR1S5_BD_edge }} |
| NR1S8 | {{ hvj_NR1S8_AL_edge }} | {{ hvj_NR1S8_BL_edge }} | {{ hvj_NR1S8_BL_corner }} | {{ hvj_NR1S8_BD_edge }} |
| NR1_1p4 | {{ hvj_NR1_1p4_AL_edge }} | {{ hvj_NR1_1p4_BL_edge }} | {{ hvj_NR1_1p4_BL_corner }} | {{ hvj_NR1_1p4_BD_edge }} |
| NR1_2 | {{ hvj_NR1_2_AL_edge }} | {{ hvj_NR1_2_BL_edge }} | {{ hvj_NR1_2_BL_corner }} | {{ hvj_NR1_2_BD_edge }} |
| NR1_3 | {{ hvj_NR1_3_AL_edge }} | {{ hvj_NR1_3_BL_edge }} | {{ hvj_NR1_3_BL_corner }} | {{ hvj_NR1_3_BD_edge }} |
| NR3M1 | {{ hvj_NR3M1_AL_edge }} | {{ hvj_NR3M1_BL_edge }} | {{ hvj_NR3M1_BL_corner }} | {{ hvj_NR3M1_BD_edge }} |
| NR3W1 | {{ hvj_NR3W1_AL_edge }} | {{ hvj_NR3W1_BL_edge }} | {{ hvj_NR3W1_BL_corner }} | {{ hvj_NR3W1_BD_edge }} |
| NR3W3 | {{ hvj_NR3W3_AL_edge }} | {{ hvj_NR3W3_BL_edge }} | {{ hvj_NR3W3_BL_corner }} | {{ hvj_NR3W3_BD_edge }} |
| NR3_1p5 | {{ hvj_NR3_1p5_AL_edge }} | {{ hvj_NR3_1p5_BL_edge }} | {{ hvj_NR3_1p5_BL_corner }} | {{ hvj_NR3_1p5_BD_edge }} |
| NR3_2 | {{ hvj_NR3_2_AL_edge }} | {{ hvj_NR3_2_BL_edge }} | {{ hvj_NR3_2_BL_corner }} | {{ hvj_NR3_2_BD_edge }} |
| NR4S | {{ hvj_NR4S_AL_edge }} | {{ hvj_NR4S_BL_edge }} | {{ hvj_NR4S_BL_corner }} | {{ hvj_NR4S_BD_edge }} |
| NR5_1p4 | {{ hvj_NR5_1p4_AL_edge }} | {{ hvj_NR5_1p4_BL_edge }} | {{ hvj_NR5_1p4_BL_corner }} | {{ hvj_NR5_1p4_BD_edge }} |
| NR5_2 | {{ hvj_NR5_2_AL_edge }} | {{ hvj_NR5_2_BL_edge }} | {{ hvj_NR5_2_BL_corner }} | {{ hvj_NR5_2_BD_edge }} |
~~~

```{figure} /_generated/hv-junction/rings-light.svg
:figclass: only-light
:name: hvj-rings-figure
:alt: Two panels of breakdown voltage for the straight edge and the corner: left against the number of floating rings, right against the gap of a single ring.

Breakdown voltage under assumption BL against the number of 2 µm wide floating rings whose
first gap is 2 µm (left), and against the gap of a single ring (right): the straight edge
(solid) and the corner section (dashed) ({repo}`records <results/hv-junction>`).
```

```{figure} /_generated/hv-junction/rings-dark.svg
:figclass: only-dark
:alt: Two panels of breakdown voltage for the straight edge and the corner: left against the number of floating rings, right against the gap of a single ring.

Breakdown voltage under assumption BL against the number of 2 µm wide floating rings whose
first gap is 2 µm (left), and against the gap of a single ring (right): the straight edge
(solid) and the corner section (dashed) ({repo}`records <results/hv-junction>`).
```

### Deep N-well

D structures repeat the terminations around a deep N-well: DT (termination length), DC
(corner radius), DW (drawn P-well), DM and DPM (plates), DGM (gated plate). DAo1 structures
draw a NAT layer that overlaps the deep N-well edge by 1 µm. The values are in
{numref}`tab-hvj-deep`. Their corner and P-well values are also in
{numref}`hvj-corners-figure` and {numref}`hvj-pwell-figure`.

~~~{table} Breakdown voltage (V) of the deep N-well structures.
:name: tab-hvj-deep

| Structure | AL | AD | BL | BD |
|---|---|---|---|---|
| DAo1 | {{ hvj_DAo1_AL_edge }} | {{ hvj_DAo1_AD_edge }} | {{ hvj_DAo1_BL_edge }} | {{ hvj_DAo1_BD_edge }} |
| DAo1C0 | {{ hvj_DAo1C0_AL_edge }} | {{ hvj_DAo1C0_AD_edge }} | {{ hvj_DAo1C0_BL_edge }} | {{ hvj_DAo1C0_BD_edge }} |
| DAo1M1_6 | {{ hvj_DAo1M1_6_AL_edge }} | {{ hvj_DAo1M1_6_AD_edge }} | {{ hvj_DAo1M1_6_BL_edge }} | {{ hvj_DAo1M1_6_BD_edge }} |
| DAo1T35 | {{ hvj_DAo1T35_AL_edge }} | {{ hvj_DAo1T35_AD_edge }} | {{ hvj_DAo1T35_BL_edge }} | {{ hvj_DAo1T35_BD_edge }} |
| DC0 | {{ hvj_DC0_AL_edge }} | {{ hvj_DC0_AD_edge }} | {{ hvj_DC0_BL_edge }} | {{ hvj_DC0_BD_edge }} |
| DGM1@g0 | {{ hvj_DGM1_g0_AL_edge }} | {{ hvj_DGM1_g0_AD_edge }} | {{ hvj_DGM1_g0_BL_edge }} | {{ hvj_DGM1_g0_BD_edge }} |
| DGM1@gw | {{ hvj_DGM1_gw_AL_edge }} | {{ hvj_DGM1_gw_AD_edge }} | {{ hvj_DGM1_gw_BL_edge }} | {{ hvj_DGM1_gw_BD_edge }} |
| DM1_10 | {{ hvj_DM1_10_AL_edge }} | {{ hvj_DM1_10_AD_edge }} | {{ hvj_DM1_10_BL_edge }} | {{ hvj_DM1_10_BD_edge }} |
| DM1_6 | {{ hvj_DM1_6_AL_edge }} | {{ hvj_DM1_6_AD_edge }} | {{ hvj_DM1_6_BL_edge }} | {{ hvj_DM1_6_BD_edge }} |
| DPM12 | {{ hvj_DPM12_AL_edge }} | {{ hvj_DPM12_AD_edge }} | {{ hvj_DPM12_BL_edge }} | {{ hvj_DPM12_BD_edge }} |
| DT10 | {{ hvj_DT10_AL_edge }} | {{ hvj_DT10_AD_edge }} | {{ hvj_DT10_BL_edge }} | {{ hvj_DT10_BD_edge }} |
| DT20 | {{ hvj_DT20_AL_edge }} | {{ hvj_DT20_AD_edge }} | {{ hvj_DT20_BL_edge }} | {{ hvj_DT20_BD_edge }} |
| DT20b | {{ hvj_DT20b_AL_edge }} | {{ hvj_DT20b_AD_edge }} | {{ hvj_DT20b_BL_edge }} | {{ hvj_DT20b_BD_edge }} |
| DT2p6 | {{ hvj_DT2p6_AL_edge }} | {{ hvj_DT2p6_AD_edge }} | {{ hvj_DT2p6_BL_edge }} | {{ hvj_DT2p6_BD_edge }} |
| DW1p5 | {{ hvj_DW1p5_AL_edge }} | {{ hvj_DW1p5_AD_edge }} | {{ hvj_DW1p5_BL_edge }} | {{ hvj_DW1p5_BD_edge }} |
~~~

### Doping family

Some structures are rerun under the family members of {ref}`hvj-assumptions`. The substrate
dopings are in {numref}`tab-hvj-family-l` and {numref}`tab-hvj-family-d`. The oxide charge and
the generated P-well are in {numref}`tab-hvj-family-other`. All hold the straight edge. The
spread along a row is the range that the unpublished doping leaves open, on the section of
{numref}`hvj-section-figure`.

~~~{table} Breakdown voltage (V) under the substrate dopings, deep P layer under deep N-well only.
:name: tab-hvj-family-l

| Structure | BLlo | BL | BLhi |
|---|---|---|---|
| NT20 | {{ hvj_NT20_BLlo_edge }} | {{ hvj_NT20_BL_edge }} | {{ hvj_NT20_BLhi_edge }} |
| NC0 | {{ hvj_NC0_BLlo_edge }} | {{ hvj_NC0_BL_edge }} | {{ hvj_NC0_BLhi_edge }} |
| NA0p6 | {{ hvj_NA0p6_BLlo_edge }} | {{ hvj_NA0p6_BL_edge }} | {{ hvj_NA0p6_BLhi_edge }} |
| NAM1_6 | {{ hvj_NAM1_6_BLlo_edge }} | {{ hvj_NAM1_6_BL_edge }} | {{ hvj_NAM1_6_BLhi_edge }} |
| NW3 | {{ hvj_NW3_BLlo_edge }} | {{ hvj_NW3_BL_edge }} | {{ hvj_NW3_BLhi_edge }} |
| NR3_2 | {{ hvj_NR3_2_BLlo_edge }} | {{ hvj_NR3_2_BL_edge }} | {{ hvj_NR3_2_BLhi_edge }} |
| NM1_6 | {{ hvj_NM1_6_BLlo_edge }} | {{ hvj_NM1_6_BL_edge }} | {{ hvj_NM1_6_BLhi_edge }} |
| NP2 | {{ hvj_NP2_BLlo_edge }} | {{ hvj_NP2_BL_edge }} | {{ hvj_NP2_BLhi_edge }} |
| DT20 | {{ hvj_DT20_BLlo_edge }} | {{ hvj_DT20_BL_edge }} | {{ hvj_DT20_BLhi_edge }} |
| DM1_6 | {{ hvj_DM1_6_BLlo_edge }} | {{ hvj_DM1_6_BL_edge }} | {{ hvj_DM1_6_BLhi_edge }} |
| DAo1 | {{ hvj_DAo1_BLlo_edge }} | {{ hvj_DAo1_BL_edge }} | {{ hvj_DAo1_BLhi_edge }} |
~~~

~~~{table} Breakdown voltage (V) under the substrate dopings, deep P layer under the whole wafer.
:name: tab-hvj-family-d

| Structure | BDlo | BD | BDhi |
|---|---|---|---|
| NT20 | {{ hvj_NT20_BDlo_edge }} | {{ hvj_NT20_BD_edge }} | {{ hvj_NT20_BDhi_edge }} |
| NC0 | {{ hvj_NC0_BDlo_edge }} | {{ hvj_NC0_BD_edge }} | {{ hvj_NC0_BDhi_edge }} |
| NA0p6 | {{ hvj_NA0p6_BDlo_edge }} | {{ hvj_NA0p6_BD_edge }} | {{ hvj_NA0p6_BDhi_edge }} |
| NAM1_6 | {{ hvj_NAM1_6_BDlo_edge }} | {{ hvj_NAM1_6_BD_edge }} | {{ hvj_NAM1_6_BDhi_edge }} |
| NW3 | {{ hvj_NW3_BDlo_edge }} | {{ hvj_NW3_BD_edge }} | {{ hvj_NW3_BDhi_edge }} |
| NR3_2 | {{ hvj_NR3_2_BDlo_edge }} | {{ hvj_NR3_2_BD_edge }} | {{ hvj_NR3_2_BDhi_edge }} |
| NM1_6 | {{ hvj_NM1_6_BDlo_edge }} | {{ hvj_NM1_6_BD_edge }} | {{ hvj_NM1_6_BDhi_edge }} |
| NP2 | {{ hvj_NP2_BDlo_edge }} | {{ hvj_NP2_BD_edge }} | {{ hvj_NP2_BDhi_edge }} |
| DT20 | {{ hvj_DT20_BDlo_edge }} | {{ hvj_DT20_BD_edge }} | {{ hvj_DT20_BDhi_edge }} |
| DM1_6 | {{ hvj_DM1_6_BDlo_edge }} | {{ hvj_DM1_6_BD_edge }} | {{ hvj_DM1_6_BDhi_edge }} |
| DAo1 | {{ hvj_DAo1_BDlo_edge }} | {{ hvj_DAo1_BD_edge }} | {{ hvj_DAo1_BDhi_edge }} |
~~~

~~~{table} Breakdown voltage (V) under the oxide charges and the generated P-well of the family.
:name: tab-hvj-family-other

| Structure | BLq | BLq3 | AL | ALhi |
|---|---|---|---|---|
| NT20 | {{ hvj_NT20_BLq_edge }} | {{ hvj_NT20_BLq3_edge }} | {{ hvj_NT20_AL_edge }} | {{ hvj_NT20_ALhi_edge }} |
| NC0 | {{ hvj_NC0_BLq_edge }} | {{ hvj_NC0_BLq3_edge }} | {{ hvj_NC0_AL_edge }} | {{ hvj_NC0_ALhi_edge }} |
| NA0p6 | {{ hvj_NA0p6_BLq_edge }} | {{ hvj_NA0p6_BLq3_edge }} | {{ hvj_NA0p6_AL_edge }} | {{ hvj_NA0p6_ALhi_edge }} |
| NAM1_6 | {{ hvj_NAM1_6_BLq_edge }} | {{ hvj_NAM1_6_BLq3_edge }} | {{ hvj_NAM1_6_AL_edge }} | {{ hvj_NAM1_6_ALhi_edge }} |
| NW3 | {{ hvj_NW3_BLq_edge }} | {{ hvj_NW3_BLq3_edge }} | {{ hvj_NW3_AL_edge }} | {{ hvj_NW3_ALhi_edge }} |
| NR3_2 | {{ hvj_NR3_2_BLq_edge }} | {{ hvj_NR3_2_BLq3_edge }} | {{ hvj_NR3_2_AL_edge }} | {{ hvj_NR3_2_ALhi_edge }} |
| NM1_6 | {{ hvj_NM1_6_BLq_edge }} | {{ hvj_NM1_6_BLq3_edge }} | {{ hvj_NM1_6_AL_edge }} | {{ hvj_NM1_6_ALhi_edge }} |
| NP2 | {{ hvj_NP2_BLq_edge }} | {{ hvj_NP2_BLq3_edge }} | {{ hvj_NP2_AL_edge }} | {{ hvj_NP2_ALhi_edge }} |
| DT20 | {{ hvj_DT20_BLq_edge }} | {{ hvj_DT20_BLq3_edge }} | {{ hvj_DT20_AL_edge }} | {{ hvj_DT20_ALhi_edge }} |
| DM1_6 | {{ hvj_DM1_6_BLq_edge }} | {{ hvj_DM1_6_BLq3_edge }} | {{ hvj_DM1_6_AL_edge }} | {{ hvj_DM1_6_ALhi_edge }} |
| DAo1 | {{ hvj_DAo1_BLq_edge }} | {{ hvj_DAo1_BLq3_edge }} | {{ hvj_DAo1_AL_edge }} | {{ hvj_DAo1_ALhi_edge }} |
~~~

(hvj-charon)=

## Charon cross-check

{{ Charon }} solves a case on {{ DEVSIM }}'s own nodes, written as a triangle mesh
({repo}`experiments/hv-junction/charon_mesh.py`). Its sweep includes impact ionisation in the
continuity equations, so its current rises at breakdown
({repo}`experiments/hv-junction/charon_run.py`). Three Charon values stand beside DEVSIM's
breakdown voltage:

- the bias at which the current is 100 times its low-bias trend;
- the bias at which the integral {math:numref}`eq-hvj-integral` reaches 1 on Charon's potential;
- the highest bias Charon solved.

Charon's control-volume scheme takes the hole coefficient's low-field values at every field
({repo}`experiments/hv-junction/charon_deck.py`). The electron coefficient is that of
{math:numref}`eq-hvj-alpha`. Each case's DEVSIM curve is of the kind in
{numref}`hvj-integral-figure`.

The six cases of {numref}`tab-hvj-charon-first` were run on an earlier member of the doping
family, under its process names A and B. They compare the two simulators on one section each.
Their values are not predictions of the present family
({repo}`record <results/hv-junction/charon-firstpass.json>`). The cases of
{numref}`tab-hvj-charon` are sections of the present family.

~~~{table} Breakdown voltage (V) on the earlier doping family: DEVSIM against Charon.
:name: tab-hvj-charon-first

| Case | DEVSIM | Charon current | Charon integral | Charon last bias |
|---|---|---|---|---|
| NT20, A | {{ hvj_c1_NT20_A_edge_devsim }} | {{ hvj_c1_NT20_A_edge_current }} | {{ hvj_c1_NT20_A_edge_integral }} | {{ hvj_c1_NT20_A_edge_last }} |
| NT20, B | {{ hvj_c1_NT20_B_edge_devsim }} | {{ hvj_c1_NT20_B_edge_current }} | {{ hvj_c1_NT20_B_edge_integral }} | {{ hvj_c1_NT20_B_edge_last }} |
| NW1p5, B | {{ hvj_c1_NW1p5_B_edge_devsim }} | {{ hvj_c1_NW1p5_B_edge_current }} | {{ hvj_c1_NW1p5_B_edge_integral }} | {{ hvj_c1_NW1p5_B_edge_last }} |
| NM1_6, B | {{ hvj_c1_NM1_6_B_edge_devsim }} | {{ hvj_c1_NM1_6_B_edge_current }} | {{ hvj_c1_NM1_6_B_edge_integral }} | {{ hvj_c1_NM1_6_B_edge_last }} |
| NR1_2, B | {{ hvj_c1_NR1_2_B_edge_devsim }} | {{ hvj_c1_NR1_2_B_edge_current }} | {{ hvj_c1_NR1_2_B_edge_integral }} | {{ hvj_c1_NR1_2_B_edge_last }} |
| DT20, B | {{ hvj_c1_DT20_B_edge_devsim }} | {{ hvj_c1_DT20_B_edge_current }} | {{ hvj_c1_DT20_B_edge_integral }} | {{ hvj_c1_DT20_B_edge_last }} |
~~~

A dash under Charon current is a sweep that stopped before its current reached 100 times the
trend.

~~~{table} Breakdown voltage (V) on the present doping family: DEVSIM against Charon.
:name: tab-hvj-charon

| Case | DEVSIM | Charon current | Charon integral | Charon last bias |
|---|---|---|---|---|
| NP4, BL | {{ hvj_c2_NP4_BL_edge_devsim }} | {{ hvj_c2_NP4_BL_edge_current }} | {{ hvj_c2_NP4_BL_edge_integral }} | {{ hvj_c2_NP4_BL_edge_last }} |
| NT20, BD | {{ hvj_c2_NT20_BD_edge_devsim }} | {{ hvj_c2_NT20_BD_edge_current }} | {{ hvj_c2_NT20_BD_edge_integral }} | {{ hvj_c2_NT20_BD_edge_last }} |
~~~

(hvj-limits)=

## Limits

- **2D sections.** Each value is one radial section. A corner is a smooth cylinder about one
  axis ({numref}`hvj-corners-figure`). A drawn corner with vertices concentrates the field
  more, so a corner value is an upper bound.
- **The criterion.** The integral reaching 1 marks the onset of avalanche on DEVSIM's
  potential. The solve carries no avalanche current, so it gives no current-voltage curve
  beyond that bias ({numref}`hvj-integral-figure`).
- **The absolute level.** The family's abutting junction lies {{ hvj_abut_pct }} % above the
  published typical value ({numref}`tab-hvj-anchors`). No correction is applied to any value.
- **The doping.** The wells are a family set against published values, not measured profiles.
  The deep P layer is inferred from the deep N-well's diode model, and its extent is an
  assumption ({ref}`hvj-assumptions`).
- **The floating rings.** A field line ends where the field falls under 2e3 V/cm, inside each
  ring. The integral is therefore taken gap by gap, and multiplication in one gap is not
  carried into the next ({numref}`hvj-rings-figure`).
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
differ. {repo}`experiments/hv-junction/README.md` gives the command of each record. The curves
of {numref}`hvj-integral-figure` are read from the main record.

- **main** ({repo}`main.json <results/hv-junction/main.json>`) holds every structure under
  the main assumptions. Of its cases, {{ hvj_n_main }} have the parameters of the present
  case set. The runs of that set left {{ hvj_n_main_missing }} cases without a result.
- **family** holds the doping family.
- **checks** and **diodes** hold the cases of {ref}`hvj-checks`.
- **charon-firstpass** and **charon** hold the cases of {ref}`hvj-charon`.

A case is printed only when its record row was run with the parameters that
{repo}`experiments/hv-junction/predict.py` gives at this commit. Any other case prints a dash.

The tests {repo}`tests/test_hv_junction.py` check each record's pins against the files at its
commit. They also check each number here against the records.
