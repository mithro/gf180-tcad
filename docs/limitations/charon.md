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

Charon has no 1D mode and reads only Exodus II meshes. The experiments take the {{ lim_charon_nodes }} nodes of the
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
Charon's nodal `Doping` equals the description at every node of both devices
({repo}`probes.json <results/charon-experiments/probes.json>`, B5). Its intrinsic density equals
the project's {{ lim_charon_ni }} cm⁻³ exactly.

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
pfet, far inside the 1 % comparison {term}`tolerance`.

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
lifetimes only let the inversion charge appear quickly during the Newton solve. In the bottom
panel of {numref}`fig-charon-cv`, a lifetime of 1e-14 s moves C by at most
{{ lim_charon_lifetime }} (nfet) and {{ lim_charon_pfet_lifetime }} (pfet). The project's lifetime
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
does not depend on the lifetimes ({numref}`fig-charon-cv`). A small-signal AC or
harmonic-balance deck keeps the project's lifetimes: there the lifetime sets how fast the
inversion charge follows the signal, so a short one would turn a 1 MHz curve into the
low-frequency one.

(charon-hard-range)=
## Where the default settings stop

With the project's lifetimes, the nfet sweep fails at the onset of inversion, a device bias of
{{ lim_charon_fail_v }} V.

{numref}`fig-charon-hard-range` shows the last bias each solver setting reached, sweeping up from
0 V. Looser tolerances, another concentration scaling, 5 mV steps and the FEM discretisation stop
between {{ lim_charon_stop_lo }} V and {{ lim_charon_stop_hi }} V. Lifetimes of 1e-12 s and 1e-13 s
stop at {{ lim_charon_tau_stop }} V. Only lifetimes of 1e-14 s or shorter reach 5 V.

```{figure} /_generated/limitations/charon-hard-range-light.svg
:name: fig-charon-hard-range
:figclass: only-light
:alt: One marker per solver setting at the last converged bias: hollow markers between 0.05 and 0.45 V, filled markers for the shortest lifetimes at 5 V, crosses at 0 V.

The last converged device bias of each solver setting, sweeping the nfet strip up from 0 V
({repo}`results/charon-experiments/hard-range.json`). Filled: the sweep reached 5 V. Hollow: it
stopped. Crosses: the equilibrium solve itself failed.
```

```{figure} /_generated/limitations/charon-hard-range-dark.svg
:figclass: only-dark
:alt: One marker per solver setting at the last converged bias: hollow markers between 0.05 and 0.45 V, filled markers for the shortest lifetimes at 5 V, crosses at 0 V.

The last converged device bias of each solver setting, sweeping the nfet strip up from 0 V
({repo}`results/charon-experiments/hard-range.json`). Filled: the sweep reached 5 V. Hollow: it
stopped. Crosses: the equilibrium solve itself failed.
```

At the stop of the reference setting, the last Newton iteration leaves the residual at
{{ lim_charon_ref_fnorm }} and the WRMS norm at {{ lim_charon_ref_wrms }}, above its limit of 1.
Solves started on the inversion side fail too, at {{ lim_charon_inv_biases }} V.

(charon-structures)=
## The other test structures

Three experiments use structures other than the strip of {numref}`fig-charon-strip`, all drawn in
{numref}`fig-charon-structures`. The parallel plate is the strip's oxide alone between two
contacts, `top` and `bottom`. The metal-gate stack is its oxide and body with a work-function gate on the oxide. The
2D mesh is a gmsh triangle mesh of the uniform stack.

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

```{table} The other questions of Task B and what the experiments found.
:name: tab-charon-other-answers

| Question | Answer | Measured |
|---|---|---|
| B1: does Charon read TRI3 blocks? (C of the 2D mesh at 0 V, relative to DEVSIM's 1D) | Yes | {{ lim_charon_tri3_2d }} |
| B1: does the strip split into TRI3 match the QUAD4 strip on the same nodes? (largest relative C difference, [issue #215](https://github.com/mithro/gf180-tcad/issues/215)) | No | {{ lim_charon_tri3_strip }} |
| B2: does the nonlinear-Poisson solve honour a biased poly gate? (its C, fF/µm²) | No | 0 |
| B3: does Belos GMRES converge on the sweep? (Amesos2 KLU2 does) | No | not applicable |
| B4: do the cosine current columns give C on the parallel plate? (relative error) | Yes | {{ lim_charon_pp }} |
| B4: do they give C on the metal-gate stack in depletion? (relative to the QS C) | Yes | {{ lim_charon_mg }} |
| B4: do they give C with the ohmic poly gate in accumulation? (ratio to the QS C, [issue #213](https://github.com/mithro/gf180-tcad/issues/213)) | No | {{ lim_charon_hb_acc }} |
| B4: do they give C with the ohmic poly gate in depletion? (ratio to the QS C, [issue #213](https://github.com/mithro/gf180-tcad/issues/213)) | No | {{ lim_charon_hb_depl }} |
| B6: is the oxide flux a conservative gate charge? (mismatch with the poly and body charges) | Yes | {{ lim_charon_b6 }} |
| B7: does a ten times looser tolerance move C? (largest relative change) | No | {{ lim_charon_tol8 }} |
| B7: does a ten times tighter tolerance converge? (the WRMS tolerance) | No | {{ lim_charon_tight }} |
```

## Deck rules the backend follows

Charon 2.2 needs four things in a deck, and the experiment scripts set each one. Three of them
fail silently when missing. The side sets and blocks they name are those of
{numref}`fig-charon-strip`:

- A side set named like an element block aborts the run with MPI error 14 and no message. The
  scripts name the body's side set `body_contact`.
- A uniform doping block counts only when named `Function1`, `Function2` and so on. Any other name
  passes the interpreter and leaves the doping at zero.
- The plugin writes its gmsh file in cm, and Charon reads µm. The 2D experiment scales by 1e4.
- The tpetra block offers no direct solver. Three `Direct input` lines rooted at
  `Charon->Solution Control` select Amesos2 KLU2. NOX's "Rescue Bad Newton Solve" is on by
  default and would let a Newton step use an unconverged linear solve; the backend turns it off.
