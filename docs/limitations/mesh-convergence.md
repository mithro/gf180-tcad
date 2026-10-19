(mesh-convergence)=

# Mesh convergence of the TCAD MOS capacitors

The {repo}`design spec, section 5.2 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#52-technical-definition>`
requires that {term}`uniform refinement` of the mesh changes every metric by less than 1 %. In the
spike, the depletion capacitance moved by 2 % between two meshes
({repo}`Task 10 of the Phase 2 plan <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-10-mesh-convergence-tooling>`), so this is checked, not assumed.

## Method

{py:func}`gf180tcad.tcad.meshconv.converge` solves the {term}`TCAD` {term}`MOSCAP` at four
levels, the start {py:class}`~gf180tcad.tcad.mesh.MeshSpec` scaled by 1, 2^-0.5, 0.5 and 2^-1.5
({py:data}`gf180tcad.tcad.meshconv.LEVELS`). Each level multiplies every spacing by its factor
and keeps the grading fixed ({py:meth}`~gf180tcad.tcad.mesh.MeshSpec.scaled`). The solver's
relative-error limit, the {term}`QS <C–V>` step
({py:data}`~gf180tcad.tcad.moscap1d.DV_QS`) and the physical constants are the same at every
level. The report holds, per level, the curve, the node count and the largest relative change
against the next finer level at every bias. Per triple of neighbouring levels it holds the
{term}`observed order of convergence` at every bias and its median. It also holds the
{term}`Richardson extrapolation` of the three finest levels. The **selected level** is the
coarsest whose change against the next finer one is below 1 %
({py:data}`gf180tcad.tcad.meshconv.CRITERION`) at every bias. From then on, every 1D result uses
it: the `moscap` command ({py:mod}`gf180tcad.tcad.__main__`) reads its mesh from the device's
`selected.json` ({py:data}`~gf180tcad.tcad.meshconv.SELECTED_NAME`) in
{repo}`results/tcad/meshconv/moscap1d`
({py:func}`gf180tcad.tcad.meshconv.selected_spec`).

The command is `python -m gf180tcad.tcad meshconv --device D --dim 1 --out results/tcad/meshconv`
({py:mod}`gf180tcad.tcad.__main__`). It runs each level as a separate {term}`sandbox` container in the
{{ DEVSIM }} image ({repo}`docker/TCAD_IMAGE`), under the same memory admission check as the
{term}`SPICE` reference (concurrent containers × memory ≤ 128 GiB). The report is computed in the same image.
`--dim 2` is refused until the 2D MOS capacitor of
{repo}`Task 11 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`
exists.

## 1D result

The {term}`C–V` is the quasi-static curve on the 201 gate biases of the SPICE {term}`cv` sweep,
with the start values of the {term}`process files <process file>`. The start spec is
{py:attr}`~gf180tcad.tcad.mesh.MeshSpec.DEFAULT_1D` (0.05 nm at both oxide interfaces, 20 nm
in the bulk, grading 1.1). "Max change" is the largest relative change against the next finer
level over all biases.

| Device | Level (scale) | Nodes | Max change | Median observed order |
|---|---|---|---|---|
| {term}`nfet_05v0` | 0 (1) | 668 | 3.7e-5 | 1.24 (levels 0–2) |
| | 1 (0.707) | 937 | 3.0e-5 | 2.05 (levels 1–3) |
| | 2 (0.5) | 1327 | 1.5e-5 | |
| | 3 (0.354) | 1877 | | |
| {term}`pfet_05v0` | 0 (1) | 676 | 3.8e-5 | 1.26 (levels 0–2) |
| | 1 (0.707) | 949 | 2.9e-5 | 2.08 (levels 1–3) |
| | 2 (0.5) | 1343 | 1.4e-5 | |
| | 3 (0.354) | 1900 | | |

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

So the spike's C/Cox = 1.0039 at −5 V (recorded in
{repo}`Task 11 of the Phase 2 plan <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`) is not physics of the stack. It comes from the 2D
structure, where
{repo}`Task 11 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`
diagnoses it.

## Limitations

- **1D only so far.** The 2D mesh convergence comes with
  {repo}`Task 11 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`.
- **Numbers from one image.** The results are from the TCAD image pinned in
  {repo}`docker/TCAD_IMAGE` and are regenerated when that image changes.
