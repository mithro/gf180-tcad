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

Charon has no 1D mode and reads only Exodus II meshes. The experiments take the 686 nodes of the
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
the project's 8.265841554853887e9 cm⁻³ exactly.

(charon-cv)=
## The quasi-static C–V

Charon solves zero-current {term}`drift-diffusion` at the gate biases vg ± 1 mV, stepped by LOCA
continuation. The C per area is the central difference of the gate charge,
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
Charon agrees with DEVSIM at every one of the 201 biases. The largest relative difference is
3.0e-5 on the nfet and 5.4e-5 on the pfet, far inside the 1 % comparison {term}`tolerance`.

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

The reference runs use SRH lifetimes of 1e-15 s, not the project's 1e-5 s. With no current, the
steady state is each region's equilibrium, whatever the lifetimes. The short lifetimes only let
the {term}`inversion` charge appear quickly during the Newton solve. In the bottom panel of
{numref}`fig-charon-cv`, another lifetime moves C by at most 1.1e-9.

A ten times looser tolerance moves C by at most 1.0e-9, in the same panel. In the reference runs,
n·p equals n_i² within 2e-6 at every node and state, so each state is an equilibrium.

(charon-hard-range)=
## Where the default settings stop

With the project's lifetimes, the nfet {term}`sweep` stops at the onset of inversion. That is a device
bias of 0.35 V. {numref}`fig-charon-hard-range` shows the last bias each solver setting reached,
sweeping up from 0 V. Looser tolerances, another concentration scaling, 5 mV steps and the FEM
discretisation all stop between 0.05 V and 0.45 V. Only lifetimes of 1e-14 s or shorter reach
5 V.

```{figure} /_generated/limitations/charon-hard-range-light.svg
:name: fig-charon-hard-range
:figclass: only-light
:alt: One marker per solver setting at the last converged bias: most hollow markers sit between 0.1 and 0.5 V, filled markers for the shortest lifetimes sit at 5 V, crosses at 0 V.

The last converged device bias of each solver setting, sweeping the nfet strip up from 0 V
({repo}`results/charon-experiments/hard-range.json`). Filled: the sweep reached 5 V. Hollow: it
stopped. Crosses: the equilibrium solve itself failed.
```

```{figure} /_generated/limitations/charon-hard-range-dark.svg
:figclass: only-dark
:alt: One marker per solver setting at the last converged bias: most hollow markers sit between 0.1 and 0.5 V, filled markers for the shortest lifetimes sit at 5 V, crosses at 0 V.

The last converged device bias of each solver setting, sweeping the nfet strip up from 0 V
({repo}`results/charon-experiments/hard-range.json`). Filled: the sweep reached 5 V. Hollow: it
stopped. Crosses: the equilibrium solve itself failed.
```

At the stop the residual stays near 2e-6 while the Newton update does not shrink. Charon 2.2
computes in double precision only; DEVSIM's quasi-static sweep uses its 128-bit solver for the same
range. Solves started on the inversion side fail too, at every bias from 0.5 V to 5 V.

## What else the experiments settled

{numref}`tab-charon-other-answers` lists the other questions, all asked of the strip of
{numref}`fig-charon-strip` or a 2D mesh of the same stack. The answers come from
{repo}`probes.json <results/charon-experiments/probes.json>` and
{repo}`hard-range.json <results/charon-experiments/hard-range.json>` and
{repo}`harmonic-balance.json <results/charon-experiments/harmonic-balance.json>`.

```{table} The other questions of Task B and what the experiments found.
:name: tab-charon-other-answers

| Experiment | Question | Answer | Measured | Quantity |
|---|---|---|---|---|
| B1 | Does Charon read TRI3 blocks? | Yes | 2.6e-4 | C at 0 V of a 2D {{ gmsh }} mesh, relative to DEVSIM's 1D |
| B2 | Does the nonlinear-Poisson solve honour a biased poly gate? | No | 0 | Its C, fF/µm²: the bias drops inside the poly |
| B3 | Does Belos GMRES converge on the sweep? | No | not applicable | Amesos2 KLU2 converges instead |
| B4 | Do the cosine current columns give C on a parallel plate? | Yes | 2.1e-9 | Relative error of C |
| B4 | Do they give C with the ohmic poly gate? | No | 0.20 | Ratio to the QS C in accumulation ([issue #213](https://github.com/mithro/gf180-tcad/issues/213)) |
| B6 | Is the oxide flux a conservative gate charge? | Yes | 8.2e-13 | Relative mismatch with the poly and body charges |
| B7 | Does a ten times looser tolerance move C? | No | 1.3e-9 | Largest relative change of C |
| B7 | Does a ten times tighter tolerance converge? | No | 1e-11 | The WRMS tolerance that fails in depletion |
```

## Deck rules the backend follows

Four behaviours of Charon 2.2 fail silently, so the backend guards each one. The side sets
and blocks they name are those of {numref}`fig-charon-strip`:

- A side set named like an element block aborts the run with MPI error 14 and no message. The
  backend names the side sets after the contacts, distinct from the regions.
- A uniform doping block counts only when named `Function1`, `Function2` and so on. Any other name
  passes the interpreter and leaves the doping at zero.
- The tpetra block offers no direct solver. Three `Direct input` lines rooted at
  `Charon->Solution Control` select Amesos2 KLU2.
- The plugin writes its gmsh file in cm, and Charon reads µm. The 2D writer scales by 1e4.
