# Charon: what the experiments found

This page explains what {{ Charon }} 2.2 does with this project's 1D {term}`MOS capacitor <MOSCAP>`, and which
settings the Charon backend needs. It answers the open questions of the design spec's
{repo}`section 12.1 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#121-dual-backend-cross-comparison-devsim-and-charon>`
for the 1D MOS capacitor. Experiments B1 to B7 of the
{repo}`Charon plan, Task B <docs/superpowers/plans/2026-10-27-phase4-charon-backend.md#task-b-backendscharon-behind-the-task-15-seam>`
produced every number here. Their scripts are in {repo}`experiments/charon-backend/` and their
records in {repo}`results/charon-experiments/`.

(charon-strip)=
## The test structure

The experiments give Charon its mesh as an Exodus II file, written by
{repo}`cx.py <experiments/charon-backend/cx.py>`. They take the {{ lim_charon_nodes }} nodes of the
committed {{ DEVSIM }} {term}`job` of {term}`nfet_05v0` at the calibrated values
({repo}`its meta file <results/tcad/moscap1d/nfet_05v0/calibrated/per_area.meta.json>`). They
extrude the nodes into a strip one element wide, as {numref}`fig-charon-strip` shows near the
oxide. Node i of the description becomes nodes 2i and 2i + 1 of the strip, so no node moves.

```{figure} /_generated/limitations/charon-strip-light.svg
:name: fig-charon-strip
:figclass: only-light
:alt: Vertical lines at the node positions near the oxide, dense at both oxide faces, over three shaded blocks: poly on the left, oxide in the middle, body on the right.

The nfet strip near the oxide ({repo}`results/charon-experiments/cv.json`). Each vertical line is
a node pair at the same depth; the shading marks the element blocks `gate_poly`, `oxide` and
`body`. The side sets `gate` and `body_contact` are the strip's two far ends.
```

```{figure} /_generated/limitations/charon-strip-dark.svg
:figclass: only-dark
:alt: Vertical lines at the node positions near the oxide, dense at both oxide faces, over three shaded blocks: poly on the left, oxide in the middle, body on the right.

The nfet strip near the oxide ({repo}`results/charon-experiments/cv.json`). Each vertical line is
a node pair at the same depth; the shading marks the element blocks `gate_poly`, `oxide` and
`body`. The side sets `gate` and `body_contact` are the strip's two far ends.
```

The deck sets every constant of the project's table explicitly: permittivities, temperature,
intrinsic density, mobilities and SRH lifetimes. Both contacts are ohmic, the gate on the poly.
Charon's nodal `Doping` equals the description at every node of both devices. The largest
relative difference is {{ lim_charon_doping_rel }}
({repo}`probes.json <results/charon-experiments/probes.json>`, B5). {numref}`fig-charon-doping`
draws both. Charon's nodal intrinsic density is {{ lim_charon_ni }} cm⁻³, the project's value.

```{figure} /_generated/limitations/charon-doping-light.svg
:name: fig-charon-doping
:figclass: only-light
:alt: Two panels, nfet and pfet: the description's net doping as a step line over depth, high in the poly and lower in the body, with Charon's nodal values as circles on the line.

The magnitude of the net doping against depth from the gate end, nfet above and pfet below, at
the start and calibrated values. Lines: the description. Circles: Charon's nodal `Doping`
({repo}`results/charon-experiments/probes.json`, B5).
```

```{figure} /_generated/limitations/charon-doping-dark.svg
:figclass: only-dark
:alt: Two panels, nfet and pfet: the description's net doping as a step line over depth, high in the poly and lower in the body, with Charon's nodal values as circles on the line.

The magnitude of the net doping against depth from the gate end, nfet above and pfet below, at
the start and calibrated values. Lines: the description. Circles: Charon's nodal `Doping`
({repo}`results/charon-experiments/probes.json`, B5).
```

(charon-cv)=
## The quasi-static C–V

The gate {term}`sweep <sweep>` takes the device from {term}`accumulation` through {term}`depletion` into
{term}`inversion`. Charon solves zero-current {term}`drift-diffusion` at the gate biases
vg ± 1 mV, stepped by LOCA continuation. The C per area is the central difference of the gate charge,
{math:numref}`eq-charon-cv`:

$$
C(v_g) = \frac{Q(v_g + \Delta V) - Q(v_g - \Delta V)}{2\,\Delta V}
$$ (eq-charon-cv)

where

- $C$ is the gate capacitance per area, in F/cm²;
- $Q$ is the gate charge per area, the oxide's displacement flux at the poly face, in C/cm²;
- $v_g$ is the gate bias of the committed grid, in V;
- $\Delta V$ is the half step, 1 mV, as in the DEVSIM job, in V.

{numref}`fig-charon-cv` shows the result for both devices against the committed DEVSIM curves.
Charon agrees with DEVSIM at every one of the {{ lim_charon_points }} biases. The largest relative
difference is {{ lim_charon_nfet_devsim }} on the nfet and {{ lim_charon_pfet_devsim }} on the
pfet. Both are far inside the 1 % comparison {term}`tolerance`.

```{figure} /_generated/limitations/charon-cv-light.svg
:name: fig-charon-cv
:figclass: only-light
:alt: Top, the C-V of nfet and pfet, Charon points on DEVSIM lines. Bottom, log relative differences near 1e-5 against DEVSIM and near 1e-9 between Charon runs, far below a dashed 1 % line.

Top: the 1D {term}`C–V` of both devices at the calibrated values, Charon (points) on DEVSIM (lines),
against u = polarity × Vg ({repo}`results/charon-experiments/cv.json`). Bottom: Charon's relative
difference from DEVSIM, and from Charon's own reference run of each run that changes one setting.
The dashed line is the 1 % tolerance.
```

```{figure} /_generated/limitations/charon-cv-dark.svg
:figclass: only-dark
:alt: Top, the C-V of nfet and pfet, Charon points on DEVSIM lines. Bottom, log relative differences near 1e-5 against DEVSIM and near 1e-9 between Charon runs, far below a dashed 1 % line.

Top: the 1D C–V of both devices at the calibrated values, Charon (points) on DEVSIM (lines),
against u = polarity × Vg ({repo}`results/charon-experiments/cv.json`). Bottom: Charon's relative
difference from DEVSIM, and from Charon's own reference run of each run that changes one setting.
The dashed line is the 1 % tolerance.
```

The reference runs use SRH lifetimes of {{ lim_charon_ref_tau }} s, not the project's 1e-5 s.
With no current, the steady state is each region's equilibrium, whatever the lifetimes. The short
lifetimes tie n·p to n_i² at every node through the recombination term. That keeps the Newton
system of the zero-current state solvable at the onset of inversion.

In the bottom
panel of {numref}`fig-charon-cv`, a lifetime of 1e-14 s moves C by at most
{{ lim_charon_lifetime }} on the nfet. On the pfet it moves C by at most
{{ lim_charon_pfet_lifetime }}. The project's lifetime
moves it by at most {{ lim_charon_default_lifetime }} over the biases where it converges.

A ten times looser tolerance moves C by at most {{ lim_charon_tol9 }}, in the same panel. In the
reference runs, n·p equals n_i² within {{ lim_charon_np_ref }} at every node and state, so each
state is an equilibrium.

(charon-recombination)=
### The deviation from "same recombination"

The design spec's
{repo}`section 12.1 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#121-dual-backend-cross-comparison-devsim-and-charon>`
asks both backends for the same recombination. The quasi-static decks deviate: their lifetimes
are {{ lim_charon_ref_tau }} s. The deviation holds for zero-current sweeps only, where the result
does not depend on the lifetimes ({numref}`fig-charon-cv`).

A small-signal AC or
harmonic-balance deck keeps the project's lifetimes. There the lifetime sets how fast the
inversion charge follows the signal. A short one would turn a 1 MHz curve into the low-frequency
one.

(charon-tolerance)=
## The Newton tolerance

The experiments run at a WRMS tolerance of 1e-10 relative and 1e-12 absolute. The backend
writes 1e-9 and 1e-11 into its decks. Wherever both converge, they give the same C within
{{ lim_charon_b7_max }} relative. The top panel of {numref}`fig-charon-tolerance` shows this on
both devices and both parameter sets.

```{figure} /_generated/limitations/charon-tolerance-light.svg
:name: fig-charon-tolerance
:figclass: only-light
:alt: Top: four curves of the relative C change between the two tolerances, all near 1e-9 or below, with a dot on every point and triangles at the axis floor where the change is exactly zero. Bottom: one marker per pfet start setting at the last bias it converged at: filled at the grid end, hollow where the sweep then failed, a cross where the ramp from equilibrium then failed before the sweep began.

Top: the relative change of C from the reference tolerance (1e-10) to the backend's (1e-9), per
device and parameter set ({repo}`results/charon-experiments/cv.json`). Bottom: the pfet start
sweep under each setting, at the last bias it converged at
({repo}`results/charon-experiments/hard-range.json`). Filled: it reached the end of the grid.
Hollow: the sweep failed after that bias. Cross: the ramp up from equilibrium failed after that
bias, so the sweep never started. In the top panel the triangles at the floor mark
exactly zero changes.
```

```{figure} /_generated/limitations/charon-tolerance-dark.svg
:figclass: only-dark
:alt: Top: four curves of the relative C change between the two tolerances, all near 1e-9 or below, with a dot on every point and triangles at the axis floor where the change is exactly zero. Bottom: one marker per pfet start setting at the last bias it converged at: filled at the grid end, hollow where the sweep then failed, a cross where the ramp from equilibrium then failed before the sweep began.

Top: the relative change of C from the reference tolerance (1e-10) to the backend's (1e-9), per
device and parameter set ({repo}`results/charon-experiments/cv.json`). Bottom: the pfet start
sweep under each setting, at the last bias it converged at
({repo}`results/charon-experiments/hard-range.json`). Filled: it reached the end of the grid.
Hollow: the sweep failed after that bias. Cross: the ramp up from equilibrium failed after that
bias, so the sweep never started. In the top panel the triangles at the floor mark
exactly zero changes.
```

{numref}`tab-charon-tolerance-change` gives the largest change per case. The pfet start reference
fails on its way down from 5 V, as the next paragraph describes. A second reference run sweeps up
from −5 V and converges to {{ lim_charon_pfet_start_up_to }} V. Together they cover the
{{ lim_charon_pfet_start_points }} biases of that row, down to {{ lim_charon_pfet_start_from }} V
from above.

```{table} The largest relative change of C between the WRMS tolerances 1e-9 and 1e-10.
:name: tab-charon-tolerance-change

| Device | Parameter set | Largest relative change |
|---|---|---|
| nfet | calibrated | {{ lim_charon_b7_nfet_calibrated }} |
| nfet | start | {{ lim_charon_b7_nfet_start }} |
| pfet | calibrated | {{ lim_charon_b7_pfet_calibrated }} |
| pfet | start | {{ lim_charon_b7_pfet_start }} |
```

Below, "failed at" is the bias of a solve's failed step, and "last converged" the last bias
it converged at. At 1e-10 the pfet start sweep down from 5 V last converged
at {{ lim_charon_stall_last }} V. It failed at {{ lim_charon_stall_v }} V. Its last Newton step
leaves the residual at {{ lim_charon_stall_fnorm }}. The WRMS norm stays at
{{ lim_charon_stall_wrms }}, above its limit of 1, after {{ lim_charon_stall_iters }}
iterations, the most allowed.

The bottom panel of {numref}`fig-charon-tolerance` shows what changes the outcome. NOX's rescue off,
10 LOCA steps per grid step (5 mV each) and a lifetime of 1e-16 s fail at the same bias. Loosening either tolerance alone, the relative
to 1e-9 or the absolute to 1e-11, passes. Tightening both tolerances ten times, to 1e-11
relative and 1e-13 absolute, fails before the sweep. The ramp up from equilibrium last converged
at {{ lim_charon_stall_ramp_v }} V, so the sweep never starts.

So a smaller step does not pass the stall, and a looser tolerance does. At 1e-11 the nfet
calibrated ramp, with the project's lifetimes, runs down from 0 V towards
{{ lim_charon_tight_ramp_to }} V. It last converged at {{ lim_charon_tight_ramp_v }} V. Both are
device biases, vg − dv_fb, with dv_fb = {{ lim_charon_nfet_dv_fb }} V.

The backend's 1e-9 passes on all four cases and gives the same C as 1e-10 within
{{ lim_charon_b7_max }}. That is far below Charon's difference from DEVSIM,
{{ lim_charon_pfet_start_devsim }} for the pfet start case.

(charon-newton)=
### Why Newton stops

The `newton-*` steps of {repo}`run.py <experiments/charon-backend/run.py>` sweep the start
values of both devices, at both lifetimes and both tolerances, one factor at a time. Where a
sweep fails, {repo}`b7n.py <experiments/charon-backend/b7n.py>` repeats the failed Newton solve
at 1e-10 and at 1e-11. Its `write linear system is on` line makes Charon write the Jacobian J,
the iterate and the residual after every iteration.

Charon cannot report a condition number. Amesos2's KLU2 adapter
([`Amesos2_KLU2_def.hpp`](https://github.com/trilinos/Trilinos/blob/81e9581a3c5f701d41e6828d0f0e5affcef5373a/packages/amesos2/src/Amesos2_KLU2_def.hpp)) calls neither of KLU's
estimators, `KLU_condest` and `KLU_rcond`
([`klu2_diagnostics.hpp`](https://github.com/trilinos/Trilinos/blob/81e9581a3c5f701d41e6828d0f0e5affcef5373a/packages/amesos2/src/KLU2/Source/klu2_diagnostics.hpp)). So
{repo}`b7n.py <experiments/charon-backend/b7n.py>` computes the condition number from the
written J. J's LU factors solve for every column of J⁻¹.

NOX's convergence test asks the WRMS norm of the update to fall below 1,
{math:numref}`eq-charon-wrms`
([`NOX_StatusTest_NormWRMS.H`](https://github.com/trilinos/Trilinos/blob/81e9581a3c5f701d41e6828d0f0e5affcef5373a/packages/nox/src/NOX_StatusTest_NormWRMS.H)):

$$
\|\delta x\|_{\mathrm{WRMS}} = \sqrt{\frac{1}{N} \sum_{i=1}^{N} \left( \frac{\delta x_i}{r\,|x_i| + a} \right)^2}
$$ (eq-charon-wrms)

where

- $\|\delta x\|_{\mathrm{WRMS}}$ is the WRMS norm of the update, dimensionless;
- $N$ is the number of unknowns, dimensionless;
- $i$ numbers the unknowns, dimensionless;
- $\delta x_i$ is the update of unknown $i$ in one Newton iteration, dimensionless;
- $x_i$ is unknown $i$ before that update, in Charon's scaled units, dimensionless;
- $r$ is the relative tolerance, dimensionless;
- $a$ is the absolute tolerance, dimensionless.

Charon's scaled units divide the potential by {{ lim_charon_newton_v0 }} V and the densities by
{{ lim_charon_newton_c0 }} cm⁻³. Two round-off scales test the candidate limits,
{math:numref}`eq-charon-floors`:

$$
f_x = \big\|\varepsilon\,|x|\big\|_{\mathrm{WRMS}}, \qquad
s_F = \big\|\varepsilon\,|J|\,|x|\big\|_2
$$ (eq-charon-floors)

where

- $f_x$ is floor_x, the WRMS norm of an update of $\varepsilon |x_i|$ in every unknown,
  dimensionless;
- $\varepsilon$ is the spacing of double-precision numbers at 1, 2⁻⁵², dimensionless;
- $x$ is the vector of the unknowns $x_i$, dimensionless;
- $J$ is the Jacobian of the scaled residual, dimensionless;
- $|x|$ and $|J|$ hold the magnitudes of the entries, dimensionless;
- $s_F$ is the round-off scale of the residual, dimensionless.

The condition number measures how far J magnifies such round-off,
{math:numref}`eq-charon-cond`:

$$
\kappa_1(A) = \|A\|_1\,\|A^{-1}\|_1, \qquad A = J \ \text{or}\ A = D^{-1} J
$$ (eq-charon-cond)

where

- $\kappa_1(A)$ is the 1-norm condition number of the matrix $A$, dimensionless;
- $J$ is the Jacobian, as in {math:numref}`eq-charon-floors`, dimensionless;
- $D$ is the diagonal matrix of the row sums of $|J|$, dimensionless.

$s_F$ takes the terms of each residual row to have the size of the matching entry of
$|J|\,|x|$.

{numref}`fig-charon-newton` shows every failed solve. NOX takes the full Newton step at every
iteration, so the line search plays no part. The round-off of the unknowns is not the limit.
Its floor_x is at most {{ lim_charon_newton_floor_x }} at 1e-10 and
{{ lim_charon_newton_floor_x_tight }} at 1e-11.

```{figure} /_generated/limitations/charon-newton-light.svg
:name: fig-charon-newton
:figclass: only-light
:alt: Top, the WRMS norm per Newton iteration of seven failed solves, falling to a plateau near 1 or staying far above it. Below, one row per solve: the smallest WRMS norms beside a much smaller round-off floor; the last residual beside its round-off scale; two condition numbers on a log axis beside a dotted line at 1/eps.

Top: the WRMS norm per Newton iteration of each failed solve, repeated at 1e-10; nfet blue,
pfet orange, dashed with the project's lifetime, circles for the sweeps at 1e-10 and squares
at 1e-11. Below, one row per solve, named by device, lifetime, sweep tolerance and failed bias:
the smallest WRMS norm at both tolerances and floor_x; the last residual and its round-off
scale; the condition numbers of J and D⁻¹J
({repo}`results/charon-experiments/hard-range.json`, `newton`).
```

```{figure} /_generated/limitations/charon-newton-dark.svg
:figclass: only-dark
:alt: Top, the WRMS norm per Newton iteration of seven failed solves, falling to a plateau near 1 or staying far above it. Below, one row per solve: the smallest WRMS norms beside a much smaller round-off floor; the last residual beside its round-off scale; two condition numbers on a log axis beside a dotted line at 1/eps.

Top: the WRMS norm per Newton iteration of each failed solve, repeated at 1e-10; nfet blue,
pfet orange, dashed with the project's lifetime, circles for the sweeps at 1e-10 and squares
at 1e-11. Below, one row per solve, named by device, lifetime, sweep tolerance and failed bias:
the smallest WRMS norm at both tolerances and floor_x; the last residual and its round-off
scale; the condition numbers of J and D⁻¹J
({repo}`results/charon-experiments/hard-range.json`, `newton`).
```

The residual is at its round-off scale. At the last iteration its 2-norm is
{{ lim_charon_newton_res_lo }} to {{ lim_charon_newton_res_hi }} times $s_F$. Each further
update is $J^{-1}$ applied to that residual, so its size follows J's conditioning. At the last
iteration $\kappa_1(D^{-1}J)$ is {{ lim_charon_newton_cond_lo }} to
{{ lim_charon_newton_cond_hi }}.

The tolerance does not change the iterates. Both repeats take the same updates for as long as
both run. At each such iteration the WRMS norm at 1e-11 is ten times the one at 1e-10.

Each failure of a 1e-11 sweep converges when repeated at 1e-10, with a WRMS norm of at most
{{ lim_charon_newton_conv_hi }}. The failures of the 1e-10 sweeps stay above 1 at both
tolerances. At 1e-11 every sweep fails. The nfet with the project's lifetime fails at
equilibrium, the others at device biases of {{ lim_charon_newton_tight_v }} V.

The lifetime and the doping act differently on the two devices. At 1e-10 the pfet sweep fails at
{{ lim_charon_newton_pfet_v }} V with either lifetime. Its WRMS norm stalls at
{{ lim_charon_newton_pfet_floor }} at most. The nfet sweep reaches the end of its grid with
1e-15 s.

With the project's lifetime the nfet sweep fails at {{ lim_charon_newton_nfet_v }} V. There
$\kappa_1(D^{-1}J)$ is {{ lim_charon_newton_nfet_cond }}, above $1/\varepsilon$. Its WRMS
norm stays above {{ lim_charon_newton_nfet_floor }}.

(charon-hard-range)=
## Where the default settings fail

With the project's lifetimes, the nfet sweep fails at the onset of inversion, a device bias of
{{ lim_charon_fail_v }} V.

{numref}`fig-charon-hard-range` shows the last bias each solver setting reached, sweeping up from
0 V. Five kinds of setting last converged between {{ lim_charon_stop_lo }} V and
{{ lim_charon_stop_hi }} V.
They are looser tolerances, another concentration scaling, 5 mV steps, no SRH and the FEM
discretisation. Lifetimes of 1e-12 s and 1e-13 s
last converged at {{ lim_charon_tau_stop }} V. Only lifetimes of 1e-14 s or shorter reach 5 V.

```{figure} /_generated/limitations/charon-hard-range-light.svg
:name: fig-charon-hard-range
:figclass: only-light
:alt: One marker per solver setting at the last converged bias: hollow markers for the settings that failed, filled markers for the shortest lifetimes at the end of the sweep, crosses at 0 V for failed equilibria.

The last converged device bias of each solver setting, sweeping the nfet strip up from 0 V
({repo}`results/charon-experiments/hard-range.json`). Filled: the sweep reached 5 V. Hollow: it
failed after that bias. Crosses: the equilibrium solve itself failed.
```

```{figure} /_generated/limitations/charon-hard-range-dark.svg
:figclass: only-dark
:alt: One marker per solver setting at the last converged bias: hollow markers for the settings that failed, filled markers for the shortest lifetimes at the end of the sweep, crosses at 0 V for failed equilibria.

The last converged device bias of each solver setting, sweeping the nfet strip up from 0 V
({repo}`results/charon-experiments/hard-range.json`). Filled: the sweep reached 5 V. Hollow: it
failed after that bias. Crosses: the equilibrium solve itself failed.
```

The reference setting fails with a residual of {{ lim_charon_ref_fnorm }} after its last Newton
iteration. Its WRMS norm is {{ lim_charon_ref_wrms }}, above the limit of 1.
Solves started on the inversion side fail too, at {{ lim_charon_inv_biases }} V.

(charon-structures)=
## The other test structures

Three experiments use structures other than the strip of {numref}`fig-charon-strip`, all drawn in
{numref}`fig-charon-structures`. The parallel plate is the strip's oxide alone between two
contacts, `top` and `bottom`. The metal-gate stack is its oxide and body with a work-function gate on the oxide. The
2D mesh is a {{ gmsh }} triangle mesh of the uniform stack.

```{figure} /_generated/limitations/charon-structures-light.svg
:name: fig-charon-structures
:figclass: only-light
:alt: Three panels: the oxide-only strip's node lines between two contacts, the oxide and body strip with its gate contact on the oxide, and a triangle mesh of poly, oxide and body.

The structures of experiments B4 and B1 ({repo}`results/charon-experiments/harmonic-balance.json`,
{repo}`results/charon-experiments/probes.json`). Top: the B4 parallel plate, node lines of the
oxide strip. Middle: the B4 metal-gate stack, oxide and body. Bottom: the B1 2D mesh, its triangles
shaded by block, with the contact sides marked.
```

```{figure} /_generated/limitations/charon-structures-dark.svg
:figclass: only-dark
:alt: Three panels: the oxide-only strip's node lines between two contacts, the oxide and body strip with its gate contact on the oxide, and a triangle mesh of poly, oxide and body.

The structures of experiments B4 and B1 ({repo}`results/charon-experiments/harmonic-balance.json`,
{repo}`results/charon-experiments/probes.json`). Top: the B4 parallel plate, node lines of the
oxide strip. Middle: the B4 metal-gate stack, oxide and body. Bottom: the B1 2D mesh, its triangles
shaded by block, with the contact sides marked.
```

## What else the experiments settled

{numref}`tab-charon-other-answers` lists the other questions. B1 uses the 2D mesh and B4 the
parallel plate and metal-gate stack of {numref}`fig-charon-structures`; the others use the strip.
The answers come from {repo}`probes.json <results/charon-experiments/probes.json>`,
{repo}`hard-range.json <results/charon-experiments/hard-range.json>` and
{repo}`harmonic-balance.json <results/charon-experiments/harmonic-balance.json>`.
{numref}`fig-charon-checks` draws the B2, B3, B6 and B7 answers.

The nonlinear-Poisson solve converges at {{ lim_charon_nlp_ok }} V, where C is
{{ lim_charon_nlp_c }}. At {{ lim_charon_nlp_bad }} V Newton's first update overshoots and the
residual turns NaN. Charon then aborts with MPI error 14.

```{figure} /_generated/limitations/charon-checks-light.svg
:name: fig-charon-checks
:figclass: only-light
:alt: Four panels: each linear solver's sweep as a bar; the nonlinear-Poisson C as circles at two biases, DEVSIM's C there as squares, and dotted lines at the biases where Newton diverged; the charge-check mismatches per state, with a triangle at the floor where one is exactly zero; the C change a hundred times looser on a log axis, a dot on every point, triangles at its floor where it is exactly zero, and one dashed line at the last bias the ramp from equilibrium of the ten times tighter nfet study converged at.

Top to bottom: B3, each linear solver's sweep from its start to where it last converged. B2, the
nonlinear-Poisson C (circles) and DEVSIM's C at the same bias (squares); a dotted line, "Newton
diverged, no C", at each bias where the solve diverged. B6, the oxide-flux spread and the poly
and body charge mismatches per state, nfet solid and pfet dashed, triangles at the floor where
one is exactly zero. B7, the nfet C change a
hundred times looser with the project's lifetimes, triangles where it is exactly zero, and a
dashed line at the last bias the ramp from equilibrium of the ten times tighter study of the
same case converged at; its sweep never began
({repo}`results/charon-experiments/probes.json`, {repo}`results/charon-experiments/hard-range.json`,
{repo}`results/charon-experiments/cv.json`).
```

```{figure} /_generated/limitations/charon-checks-dark.svg
:figclass: only-dark
:alt: Four panels: each linear solver's sweep as a bar; the nonlinear-Poisson C as circles at two biases, DEVSIM's C there as squares, and dotted lines at the biases where Newton diverged; the charge-check mismatches per state, with a triangle at the floor where one is exactly zero; the C change a hundred times looser on a log axis, a dot on every point, triangles at its floor where it is exactly zero, and one dashed line at the last bias the ramp from equilibrium of the ten times tighter nfet study converged at.

Top to bottom: B3, each linear solver's sweep from its start to where it last converged. B2, the
nonlinear-Poisson C (circles) and DEVSIM's C at the same bias (squares); a dotted line, "Newton
diverged, no C", at each bias where the solve diverged. B6, the oxide-flux spread and the poly
and body charge mismatches per state, nfet solid and pfet dashed, triangles at the floor where
one is exactly zero. B7, the nfet C change a
hundred times looser with the project's lifetimes, triangles where it is exactly zero, and a
dashed line at the last bias the ramp from equilibrium of the ten times tighter study of the
same case converged at; its sweep never began
({repo}`results/charon-experiments/probes.json`, {repo}`results/charon-experiments/hard-range.json`,
{repo}`results/charon-experiments/cv.json`).
```

```{table} The other questions of Task B and what the experiments found.
:name: tab-charon-other-answers

| Question | Answer | Measured |
|---|---|---|
| B1: does Charon read TRI3 blocks? (C of the 2D mesh at 0 V, relative to DEVSIM's 1D) | Yes | {{ lim_charon_tri3_2d }} |
| B1: does the strip split into TRI3 match the QUAD4 strip on the same nodes? (largest relative C difference, [issue #215](https://github.com/mithro/gf180-tcad/issues/215)) | No | {{ lim_charon_tri3_strip }} |
| B2: does the nonlinear-Poisson solve honour a biased poly gate? (its C where it converges, fF/µm²) | No | {{ lim_charon_nlp_c }} |
| B3: does Belos GMRES converge on the sweep? (the last bias it converged at, V; Amesos2 KLU2 reaches the end) | No | {{ lim_charon_belos_stop }} |
| B4: do the cosine current columns give C on the parallel plate? (relative error) | Yes | {{ lim_charon_pp }} |
| B4: do they give C on the metal-gate stack in depletion? (relative to the QS C) | Yes | {{ lim_charon_mg }} |
| B4: do they give C with the ohmic poly gate in accumulation? (ratio to the QS C, [issue #213](https://github.com/mithro/gf180-tcad/issues/213)) | No | {{ lim_charon_hb_acc }} |
| B4: do they give C with the ohmic poly gate in depletion? (ratio to the QS C, [issue #213](https://github.com/mithro/gf180-tcad/issues/213)) | No | {{ lim_charon_hb_depl }} |
| B6: is the oxide flux a conservative gate charge? (mismatch with the poly and body charges) | Yes | {{ lim_charon_b6 }} |
| B7: does a hundred times looser tolerance, 1e-8, move C with the project's lifetimes? (largest relative change) | No | {{ lim_charon_tol8 }} |
| B7: does a ten times tighter tolerance converge? (the WRMS tolerance) | No | {{ lim_charon_tight }} |
```

## Deck rules the backend follows

The experiment scripts and the backend follow four rules in their decks; the cm-to-µm one
applies to the 2D mesh only. The side sets and
blocks they name are those of {numref}`fig-charon-strip`:

- The body's side set is named `body_contact`, never `body`, the name of its element block.
  Each script renames it, as {repo}`b2.py <experiments/charon-backend/b2.py>` does. With the
  side set named `body`, `charon_mp.exe` exits with code {{ lim_charon_trap_side_exit }} while
  it reads the mesh. Its log ends in "Error: Different entity rank has already been set on Part".
- Each uniform doping block is named `Function1`, `Function2` and so on
  ({repo}`decks.py <experiments/charon-backend/decks.py>`). With that naming the nodal doping
  matches the description (B5, {numref}`fig-charon-doping`). A body block named `BodyDoping`
  passes the interpreter, and Charon completes. The body's nodal doping is then
  {{ lim_charon_trap_body_doping }} cm⁻³ ({numref}`fig-charon-traps`).
- The 2D mesh's coordinates are scaled from the plugin's cm to µm, by 1e4
  ({repo}`b1.py <experiments/charon-backend/b1.py>`). The scaled mesh gives C within
  {{ lim_charon_tri3_2d }} of DEVSIM's 1D (B1).
- Three `Direct input` lines rooted at `Charon->Solution Control` select Amesos2 KLU2
  ({repo}`opts.py <experiments/charon-backend/opts.py>`; B3, {numref}`fig-charon-checks`). The
  backend also turns NOX's "Rescue Bad Newton Solve" off.

The step `probe-deck-traps` of {repo}`run.py <experiments/charon-backend/run.py>` breaks the
first two rules on the nfet strip with {repo}`traps.py <experiments/charon-backend/traps.py>`
({repo}`probes.json <results/charon-experiments/probes.json>`, `deck_traps`).

```{figure} /_generated/limitations/charon-traps-light.svg
:name: fig-charon-traps
:figclass: only-light
:alt: Two panels over depth. Top, the poly: description line and Charon's nodal circles on it, at the same constant value. Bottom, the body: the description line at a negative constant, Charon's circles all on zero.

The net doping of the nfet strip's deck whose body doping block is named `BodyDoping`, poly
above and body below. Line: the description. Circles: Charon's nodal `Doping`
({repo}`results/charon-experiments/probes.json`, `deck_traps`).
```

```{figure} /_generated/limitations/charon-traps-dark.svg
:figclass: only-dark
:alt: Two panels over depth. Top, the poly: description line and Charon's nodal circles on it, at the same constant value. Bottom, the body: the description line at a negative constant, Charon's circles all on zero.

The net doping of the nfet strip's deck whose body doping block is named `BodyDoping`, poly
above and body below. Line: the description. Circles: Charon's nodal `Doping`
({repo}`results/charon-experiments/probes.json`, `deck_traps`).
```
