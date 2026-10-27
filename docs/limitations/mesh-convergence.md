(mesh-convergence)=

# Mesh convergence of the TCAD MOS capacitors

The {repo}`design spec, section 5.2 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#52-technical-definition>`
requires that {term}`uniform refinement` of the mesh changes every metric by less than 1 %. The
mesh does matter: in an early prototype the depletion capacitance moved by 2 % between two meshes
(see the {repo}`Phase 2 plan <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-10-mesh-convergence-tooling>`), so convergence is checked, not assumed.
This page shows how much the simulated capacitance changes as the mesh is made finer, and which
mesh the results use.

## Method

{py:func}`gf180tcad.tcad.meshconv.converge` solves the {term}`TCAD` {term}`MOSCAP` at four
levels, the start {py:class}`~gf180tcad.tcad.mesh.MeshSpec` scaled by 1, 2^-0.5, 0.5 and 2^-1.5
({py:data}`gf180tcad.tcad.meshconv.LEVELS`; the 2D study runs the first three, see
{ref}`mesh-convergence-2d`). Each level multiplies every spacing by its factor
({py:meth}`~gf180tcad.tcad.mesh.MeshSpec.scaled`). In 1D it keeps the grading, which there only
caps the ratio of neighbouring spacings. In 2D it scales the grading's slope too, so that the
size at every point scales ({py:data}`gf180tcad.tcad.meshconv.REFINE_GRADING`,
{ref}`a uniform refinement must refine the grading <moscap2d-refine-grading>`). The solver's
relative-error limit, the {term}`QS <C–V>` step
({py:data}`~gf180tcad.tcad.moscap1d.DV_QS`) and the physical constants are the same at every
level. The report holds, per level, the curve, the node count and the largest relative change
against the next finer level at every bias. Per triple of neighbouring levels it holds the
{term}`observed order of convergence` at every bias and its median. It also holds the
{term}`Richardson extrapolation` of the three finest levels. The **selected level** is the
coarsest whose change against the next finer one is below 1 %
({py:data}`gf180tcad.tcad.meshconv.CRITERION`) at every bias. Every 1D result uses
it: the `moscap` command ({py:mod}`gf180tcad.tcad.__main__`) reads its mesh from the device's
`selected.json` ({py:data}`~gf180tcad.tcad.meshconv.SELECTED_NAME`) in
{repo}`results/tcad/meshconv/moscap1d`
({py:func}`gf180tcad.tcad.meshconv.selected_spec`).

The command is `python -m gf180tcad.tcad meshconv --device D --dim 1 --out results/tcad/meshconv`
({py:mod}`gf180tcad.tcad.__main__`). It runs each level as a separate {term}`sandbox` container in the
{term}`dev-HEAD TCAD image` ({repo}`docker/TCAD_DEV_IMAGE`; `--image stable` for the
{term}`stable TCAD image`, see {ref}`tcad-results-image`), under the same memory admission check as the
{term}`SPICE reference <SPICE reference results>` (concurrent containers × memory ≤ 128 GiB). The report is computed in the same image.
`--dim 2` runs the 2D MOS capacitor ({ref}`mesh-convergence-2d`).

**Oscillation and noise.** Per triple and bias the report also flags oscillatory convergence (the
change reverses sign between the levels, d12 · d23 < 0), where neither the order nor the
{term}`Richardson extrapolation` applies, and treats a level difference at or below a noise floor as
noise: the order is then undefined, not an arbitrary number. The floor is
{py:data}`~gf180tcad.tcad.meshconv.NOISE_K` = 1e4 times the solver's relative error limit times |C|
(1e-6 relative at 1e-10). A QS C is a 2 mV central difference of charges of up to C × 6 V, so its
noise is up to 6e3 × that limit; 1e4 rounds that up. The median order uses only defined,
monotone biases. In 1D no bias oscillates or falls below the floor.

## 1D result

The {term}`C–V` is the quasi-static curve on the 201 gate biases of the {term}`SPICE` {term}`cv` sweep,
with the start values of the {term}`process files <process file>`. The start spec is
{py:attr}`~gf180tcad.tcad.mesh.MeshSpec.DEFAULT_1D` (0.05 nm at both oxide interfaces, 20 nm
in the bulk, grading 1.1). "Max change" is the largest relative change against the next finer
level over all biases.

| Device | Level | Scale | Nodes | Max change |
|---|---|---|---|---|
| {term}`nfet_05v0` | 0 | 1 | 668 | 3.7e-5 |
| nfet_05v0 | 1 | 0.707 | 937 | 3.0e-5 |
| nfet_05v0 | 2 | 0.5 | 1327 | 1.5e-5 |
| nfet_05v0 | 3 | 0.354 | 1877 | (finest) |
| {term}`pfet_05v0` | 0 | 1 | 676 | 3.8e-5 |
| pfet_05v0 | 1 | 0.707 | 949 | 2.9e-5 |
| pfet_05v0 | 2 | 0.5 | 1343 | 1.4e-5 |
| pfet_05v0 | 3 | 0.354 | 1900 | (finest) |

The median {term}`observed order of convergence` of each triple of neighbouring levels:

| Device | Coarsest level | Finest level | Median observed order |
|---|---|---|---|
| nfet_05v0 | 0 | 2 | 1.24 |
| nfet_05v0 | 1 | 3 | 2.05 |
| pfet_05v0 | 0 | 2 | 1.26 |
| pfet_05v0 | 1 | 3 | 2.08 |

- **The selected level is level 0, `DEFAULT_1D` itself, for both devices.** Its largest change
  is about 4e-5, 250 times below the 1 % criterion.
- **The three finest levels are second order.** Their observed order is 2.01 to 2.13 at every
  bias. The coarsest triple gives a median of about 1.25, because level 0 is not quite a uniform
  refinement of the others. Each layer is graded geometrically and then rescaled to fill its
  thickness exactly. At level 0, the 0.2 µm poly hits the grading cap of 1.1: the fewest
  intervals that grade from 20 nm to 0.05 nm overfill it, so its spacings are rescaled to about
  0.91 of nominal (0.0455 nm at the oxide instead of 0.05 nm). From level 1 on, every layer is
  limited by its length instead, and its spacings are within 1 % of nominal.
- **Against the exact reference.** {test}`tests/tcad/test_meshconv.py::test_converges_to_exact`
  runs the same four levels for the nfet stack on 21 gate biases and requires the finest level
  to be within 0.05 % of the exact {term}`Poisson–Boltzmann` curve
  ({py:func}`gf180tcad.tcad.analytic.lf_cv_uniform`) at every bias, with a median observed
  order between 1.5 and 2.5. The criterion is checked by
  {test}`tests/tcad/test_meshconv.py::test_selected_level_criterion`.
- **The oxide spacing `h_ox_nm` has no effect in 1D.** The 1D oxide spacing is the smaller of
  `h_ox_nm` and the spacing of its neighbour at each face. With `DEFAULT_1D` both neighbours are
  finer, so `h_ox_nm` is never used. This is exact: the oxide has no charge, so its potential is
  linear and any spacing resolves it.

## C/Cox in 1D

Classical accumulation and inversion layers add a capacitance in series with the
{term}`oxide capacitance <Cox>`, so C/Cox > 1 is impossible in 1D. The committed 1D results at
|Vg| = 5 V confirm it ({test}`tests/tcad/test_meshconv.py::test_1d_c_over_cox_below_one_at_5v`):

| Device | Cox (fF/µm²) | C/Cox at −5 V | C/Cox at +5 V |
|---|---|---|---|
| {term}`nfet_05v0` (15.2 nm) | 2.2718 | 0.98099 (accumulation) | 0.97302 (inversion) |
| {term}`pfet_05v0` (15.6 nm) | 2.2135 | 0.95135 (inversion) | 0.97915 (accumulation) |

So a C/Cox above 1 at −5 V, such as the 1.0039 of an early 2D prototype (see the
{repo}`Phase 2 plan <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`),
is not physics of the stack. It comes from the 2D structure ({ref}`moscap2d-artefact`).

(mesh-convergence-2d)=

## 2D result

The 2D study ({py:mod}`gf180tcad.tcad.moscap2d`, {doc}`moscap2d`) runs levels 0–2 from
{py:attr}`~gf180tcad.tcad.mesh.MeshSpec.DEFAULT_2D` on the {{ gdsfactory }} {term}`PDK` cell at
{term}`Lmin` with its source and drain ({py:data}`gf180tcad.tcad.meshconv.GEOMETRY_2D`), on the
201 biases of the SPICE {term}`cv` sweep. Lmin is the calibration geometry whose
{term}`C–V` the 2D structure (gate edges, overlap, fringe) shapes most; the selected spec is a
local spacing and applies to every 2D geometry. The 2D mesh is unstructured triangles from
{{ gmsh }}, which are isotropic, so the interfaces start at 0.5 nm, ten times the 1D spacing:
0.05 nm along a 10 µm interface would need tens of millions of nodes. The oxide spacing
matters in 2D, unlike in 1D, and starts at 1 nm ({ref}`moscap2d-artefact`).

**Level 3 is left out** ({py:data}`gf180tcad.tcad.meshconv.LEVELS_BY_DIM`,
{py:data}`gf180tcad.tcad.meshconv.EXCLUDED_2D`; the report records it as `excluded_levels`).
Meshing every level without solving gives its node count. With the refined grading, the node
count doubles per level:

| Lmin cell | W (µm) | L (µm) | Level 0 | Level 1 | Level 2 | Level 3 |
|---|---|---|---|---|---|---|
| nfet | 10 | 0.6 | 115,689 | 224,640 | 437,039 | 861,897 |
| pfet | 10 | 0.5 | 105,701 | 205,327 | 399,554 | 788,074 |

The estimated time of one QS sweep ({term}`job`) at each level:

| Lmin cell | Level 0 (h) | Level 1 (h) | Level 2 (h) | Level 3 (h) |
|---|---|---|---|---|
| nfet | 0.75 | 1.75 | 4.1 | 9.7 |
| pfet | 0.67 | 1.56 | 3.65 | 8.7 |

The times come from the measured cost of the first 2D study: s per bias = 3.25e-6 · nodes^1.278,
times the 201 biases, times 1.4 for the equilibrium set-up and the retried points. Level 3 has
not been attempted. Its mesh is as large as the 2D cell at L = 10 µm. That cell's equilibrium
{term}`drift-diffusion` solve fails in {{ DEVSIM }}'s direct solver ({ref}`moscap2d-l10`), an
open correctness problem ([issue #58](https://github.com/mithro/gf180-tcad/issues/58)). So
levels 0 and 1 are the candidates, each with a finer neighbour, and level 2 is only the finer
neighbour of level 1. The levels 0–2 give one triple, and so one observed order, which the
report gives with its oscillating and noise-floor biases.

The selection (the report's `levels` and `selected`, in {repo}`results/tcad/meshconv/moscap2d`; the
2D-equals-1D column is the largest relative difference of the extruded uniform stack's C per area
against 1D, {py:data}`~gf180tcad.tcad.meshconv.AGREEMENT_1D` = 0.5 %):

| Level | nfet: change to next level | nfet: against 1D | pfet: change to next level | pfet: against 1D |
|---|---|---|---|---|
| 0 | 0.256 % | 0.553 % | 0.170 % | 0.546 % |
| 1 | 0.092 % | 0.289 % | 0.076 % | 0.281 % |
| 2 | (finest) | 0.152 % | (finest) | 0.152 % |

Level 0 meets the 1 % convergence criterion but not the 0.5 % 2D-equals-1D one, so level 1 (scale
0.7071) is the coarsest level that meets both, for both devices. The selected level has 224,640
(nfet) and 205,327 (pfet) nodes. The nfet level-1 and level-2 sweeps each needed round-off
acceptances at the −0.6 V point ({ref}`moscap2d-solver`); the pfet needed none.

## Limitations

- **Numbers from one image per dimension.** The 1D results are from the dev-HEAD TCAD image
  pinned in {repo}`docker/TCAD_DEV_IMAGE` and are regenerated when that image changes. They are
  byte-identical to the stable image's ({repo}`docker/TCAD_IMAGE`), which
  {test}`tests/tcad/test_moscap1d.py::test_stable_and_dev_images_agree` checks. The 2D results
  are from the stable image: {{ gmsh }} 5 in the dev image meshes the 2D cells differently, so 2D
  needs its own mesh convergence there; see {ref}`tcad-results-image`.
