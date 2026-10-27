(moscap2d)=

# The 2D MOS capacitor and the C/Cox > 1 artefact

The 2D {term}`MOSCAP` is the {{ gdsfactory }} cell `nfet(volt="5.0V")` or `pfet(volt="5.0V")`
of the {{ gf180mcu_gdsfactory }}, cut across its gate ({py:mod}`gf180tcad.tcad.stack`). The vertical stack
and the doping come from the {term}`process files <process file>`
({repo}`data/process`), because the {term}`PDK`'s {{ gdsfactory }} layer stack has no gate oxide and no
doping. {py:func}`gf180tcad.tcad.moscap2d.simulate` meshes the cross-section with the
{{ gplugins_fork }}'s single-threaded {{ meshwell }} path and solves it at every gate bias with {{ DEVSIM }}:
{term}`QS <C–V>` (the counterpart of the {term}`SPICE` {term}`Cgg` of {term}`BSIM4`
`capMod=2`) and 1 MHz AC with every non-gate contact's charge response.

## The structure

- **Thick oxide only.** The 5 V devices carry {term}`Dualgate` over the gate.
  {py:func}`~gf180tcad.tcad.stack.build` requires it and raises
  {py:class}`~gf180tcad.tcad.stack.DualgateMissing` otherwise
  ({test}`tests/tcad/test_moscap2d.py::test_dualgate_required`).
- **Cut.** Across the gate (along L) through the middle of the gate width, over the active area.
  The sides of the domain are zero-flux boundaries: the shallow trench isolation is not modelled.
- **Source and drain.** A Gaussian of peak `sd_peak_cm3` at the surface that falls to the body
  doping at the junction depth {term}`XJ`, with a lateral straggle equal to the vertical one (a
  project choice, {py:data}`~gf180tcad.tcad.stack.LATERAL_STRAGGLE_RATIO`) under the poly edge.
  The nfet peak is the {term}`model card`'s {term}`NSD`, 1e20 cm⁻³. The pfet card's NSD (6e16 cm⁻³) is no source/drain
  doping, so the pfet peak, 1e20 cm⁻³, is a `literature` value: Plummer, Deal and Griffin,
  *Silicon VLSI Technology* (Prentice Hall, 2000, [ISBN 0-13-085037-3](https://openlibrary.org/isbn/0130850373)), chapter 2, the CMOS
  flow's p⁺ source/drain implant.
- **Dielectric.** An oxide (the spacer and inter-layer dielectric) fills the domain above the
  silicon outside the gate, so the gate's outer fringe reaches the silicon, as it does on
  silicon and in {term}`BSIM4`'s CF.
- **Contacts.** The gate on top of the poly, the body under the whole body, and the source and
  drain at the cell's contact openings, each its own equation-free electrode, so every other
  outer boundary is zero-flux.
- **Normalisation.** The C per area divides the per-width Cgg by the drawn gate length. {term}`DLC`
  and the BSIM4 parasitics are never applied in 2D: the cross-section has its own overlap and
  fringe.

(moscap2d-artefact)=

## The C/Cox > 1 artefact

**The symptom.** In the {term}`Phase 2` research spike a 2D MOS capacitor gave C/{term}`Cox` = 1.0039 at −5 V
with a 15.2 nm oxide, and 0.9909 with the same structure at 16 nm
({repo}`Task 11 of the Phase 2 plan <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`).
In 1D, C/Cox > 1 is impossible and does not occur ({ref}`mesh-convergence`). The diagnosis below
uses the simplest 2D structure that must equal 1D: the nfet stack extruded over 1 µm, with a gate
over the whole domain, no source or drain and zero-flux sides
({py:func}`gf180tcad.tcad.stack.uniform`). Every number is the QS C/Cox at −5 V
(accumulation) and the 2D/1D ratio minus 1 at the worst of five biases (−5, −1, 0.65, +2, +5 V);
the 1D reference is the converged 1D stack, C/Cox = 0.98099. Interfaces at 0.5 nm, grading 1.2.

| Step | Oxide 15.2 nm: C/Cox, worst 2D/1D − 1 | Oxide 16 nm: C/Cox, worst 2D/1D − 1 |
|---|---|---|
| As first built ({{ meshwell }} defaults, oxide spacing 2 nm) | **1.00126**, +2.07 % | 0.98765, +0.66 % |
| Distance-field sampling cap lifted | 0.99989, +1.93 % | 0.98623, +0.55 % |
| Vertex grid 1e-6 µm (the fix) | 0.98666, +0.58 % | 0.98623, +0.55 % (unchanged: on the grid) |

**The cause: meshwell rounds every vertex to 1 nm.** {{ meshwell }}'s `PolySurface` snaps each
vertex to its `point_tolerance`, which defaults to 1e-3 µm, and the plugin's cross-section path
left it at the default. A 15.2 nm oxide was meshed **15.0 nm** thick (its nodes span
y = 0 to 0.015 µm): {term}`Cox` 1.3 % too large, which turns the 1D C/Cox of 0.981 into 1.0013 (and, in
the spike, into 1.0039). A 16 nm oxide lies on the 1 nm grid, so it was meshed exactly, which is
why the two thicknesses disagreed by about 1.3 %. The fix passes a `point_tolerance` through
the plugin's 2D path ({{ gplugins_fork }} [PR #8](https://github.com/mithro/gplugins/pull/8)); the 2D MOS capacitor
uses 1e-6 µm ({py:data}`gf180tcad.tcad.stack.POINT_TOLERANCE_UM`), so a 15.2 nm oxide is
meshed 15.2 nm thick, and any calibrated thickness within 1e-4 relative. Every 2D run now checks
the meshed geometry against the stack, the oxide, the poly, the body and every electrode, and
raises {py:class}`~gf180tcad.tcad.moscap2d.GeometryError` if it differs
({py:func}`~gf180tcad.tcad.moscap2d.check_geometry`). The source/drain profile is an analytic
function of the node position, and the lateral positions come from the layout (on its own 1 nm
grid), so no other part of the 2D path depends on the vertex grid.

**A smaller cause: meshwell's distance-field sampling.** {{ meshwell }} samples each curve of a
threshold size field at no more than 100 points, so on a 1 µm interface the 0.5 nm size
applied only near samples 10 nm apart: the interface spacing was up to 2.0 nm (mean 0.9 nm). The
cap is lifted ({py:attr}`MeshSpec.MAX_SAMPLING <gf180tcad.tcad.mesh.MeshSpec.MAX_SAMPLING>`); the
interface spacing is then 0.51 nm everywhere. This is worth 0.14 % at 15.2 nm.

**What it is not.** The plan named four candidates; each was measured:

- *Contact-charge discretisation where the oxide meets the contact.* The poly gate's contact is
  0.2 µm away from the oxide, and the gate charge is the gate contact's charge plus the poly's
  space charge. On the same structure meshed by {{ DEVSIM }}'s own tensor mesher at 0.05 nm,
  2D equals 1D to **2.1e-5** at every bias and the charges balance exactly. With source and drain,
  1 MHz AC gives Cgg = Σ Cxg over the body, source and drain to 2e-11. Not a cause.
- *Side boundaries.* L = 2 µm gives the same C per area as L = 1 µm (−5 V: 0.99988 against
  0.99989 Cox, before the vertex fix). Not a cause.
- *Statistics.* Boltzmann in the accumulation layer and the degenerate poly. The 1D stack has the
  same statistics and stays below 1 (0.98099), and the tensor-meshed 2D stack equals it. Not a
  cause.
- *Normalisation area.* The meshed gate length is the drawn one; the problem was the
  thickness the area is multiplied by, Cox(15.2 nm) against a 15.0 nm mesh: the vertex grid
  above.

**The remainder after the fix is discretisation, and it is below the criteria.** With the geometry
exact, the 2D stack is still +0.44 % to +0.58 % above 1D at 0.5 nm. The tensor mesh at the same
0.5 nm interface spacing is +0.07 % to +0.28 %, the 1D-like spacing error; the rest comes from the
coarse triangles in the oxide, whose discrete capacitance is too large when the oxide spacing is
coarser than at its interfaces:

| Oxide spacing (vertex grid as first built) | worst 2D/1D − 1 at −5 V | minus the 1.3 % vertex-grid error |
|---|---|---|
| 2 nm | +1.93 % | +0.62 % |
| 1 nm | +1.72 % | +0.41 % |
| 0.5 nm | +1.64 % | +0.33 % |

So the 2D start mesh ({py:attr}`MeshSpec.DEFAULT_2D <gf180tcad.tcad.mesh.MeshSpec.DEFAULT_2D>`) has a
1 nm oxide spacing. Both parts fall under {term}`uniform refinement`, so the 2D mesh-convergence
study sees them ({ref}`mesh-convergence-2d`).

(moscap2d-agreement)=

**The 2D-equals-1D criterion selects the mesh.** The extruded stack at `DEFAULT_2D` itself, the
coarsest level, is within 0.38 % of 1D on both plateaus but +0.55 % at the minimum of the
{term}`C–V` (nfet +0.5 V, pfet −0.5 V), where the depletion region sets C. A bisection on the
uniform nfet stack (worst 2D/1D − 1 over −5, 0, +0.5, +1, +5 V) shows that the grading of the
body mesh through the depletion region sets it, not the oxide or the bulk spacing:

| Variant of `DEFAULT_2D` | Nodes | Worst 2D/1D − 1 |
|---|---|---|
| as it is (0.5 nm interfaces, 1 nm oxide, 100 nm bulk, grading 1.2) | 101k | +0.55 % |
| bulk spacing 50 nm | 101k | +0.48 % |
| oxide spacing 0.5 nm | 147k | +0.57 % |
| every spacing × 0.707 (the next refinement level) | 154k | +0.45 % |
| grading 1.1 | 171k | +0.32 % |

The design spec requires both mesh convergence (less than 1 % on refinement) and, here, 2D = 1D
within 0.5 % ({test}`tests/tcad/test_moscap2d.py::test_2d_equals_1d_without_sd`), so the 2D
mesh-convergence study selects the coarsest level that meets both
({py:data}`gf180tcad.tcad.meshconv.AGREEMENT_1D`, {py:func}`gf180tcad.tcad.meshconv.agreement_1d`).
Its `selected.json` and report record both criteria and the level each chooses
({ref}`mesh-convergence-2d`). C/Cox ≤ 1 at ±5 V holds at the selected level
({test}`tests/tcad/test_moscap2d.py::test_c_over_cox_le_1`).

(moscap2d-refine-grading)=

**A uniform refinement in 2D must refine the grading too.** The first 2D study scaled every
spacing by r and kept the grading, as the 1D study does. The {{ meshwell }} size field of the body
grows linearly from the interface, size(d) = h_min + (grading − 1)·d up to the bulk spacing
({py:meth}`MeshSpec.to_resolution_specs <gf180tcad.tcad.mesh.MeshSpec.to_resolution_specs>`),
so with the grading held fixed, beyond a few nm (the depletion region) every level had the
same size. Only the interfaces were refined. The 2D/1D agreement then converged on the
plateaus but not at the C–V minimum, and at the finest level it got worse. Here is the
uniform nfet stack, 2D/1D − 1 by level (the first study's results were not committed):

| Gate bias | Level 0 (101k nodes) | Level 1 (154k) | Level 2 (239k) | Level 3 (381k) |
|---|---|---|---|---|
| −5 V (accumulation) | +0.38 % | +0.25 % | +0.18 % | +0.09 % |
| 0 V | +0.52 % | +0.45 % | +0.40 % | +0.46 % |
| +0.5 V (C–V minimum) | +0.55 % | +0.44 % | +0.40 % | +0.48 % |
| +1 V (onset of inversion) | −0.05 % | −0.22 % | −0.21 % | −0.41 % |
| +5 V (inversion) | +0.25 % | +0.18 % | +0.15 % | +0.08 % |
| worst of 21 biases | 0.553 % | 0.463 % | 0.398 % | 0.483 % |

The pfet's worst values were 0.546, 0.518, 0.446 and 0.734 %. A uniform refinement scales the
size at every point, size_r(d) = r·size(d), so the slope scales as well:
grading' = 1 + (grading − 1)·r. {py:meth}`MeshSpec.scaled <gf180tcad.tcad.mesh.MeshSpec.scaled>`
does this with `refine_grading=True`, and the 2D study uses it
({py:data}`gf180tcad.tcad.meshconv.REFINE_GRADING`). 1D keeps the grading, since there it only
caps the ratio of neighbouring spacings.

(moscap2d-solver)=

## Two solver findings of the 2D sweep

- **Double precision and its fallback.** The QS {term}`sweep` runs in double precision (about twice as
  fast). In extended precision the result is the same within the QS noise; the plugin retries a
  solve that fails in double precision in extended precision at the same {term}`tolerances <tolerance>`
  (`precision_fallback`), and the 2D results record every such point (`extended_fallback`).
- **A relative criterion that is unreachable at a potential near 0 V.** {{ DEVSIM }}'s relative error is
  |update| / (|ψ| + 1e-10 V) per node, summed over the equations and regions of the device
  (`src/Equation/Equation.cc`, `src/Geometry/Region.cc` and `Device.cc` of DEVSIM 2.11.1). Where the
  potential passes through 0 V in the charge-free dielectric next to the gate, the 1e-10 criterion
  asks for an update below about 1e-20 V, beyond the round-off of the linear solve (1.6–1.7e-16 V,
  in double and extended precision alike). At the nfet's −0.6 V point, on three of the four
  refinement levels, {term}`Newton's method <Newton iteration>` stalls there for 45 iterations. The plugin's `roundoff_accept` accepts
  such a solve only under narrow conditions (every potential update ≤ the 1e-12 V `abs_tol` and
  ≤ 32·eps·max|ψ| over the last 10 iterations, a plateau of the relative error, and a node
  with |ψ| small enough to explain it), after solving it again to that round-off state, because
  DEVSIM restores the previous solution of a solve it calls non-converged. Every accepted point is
  recorded. At the nfet level-1 point the accepted update is 1.6e-16 V (the bound 4.2e-15 V), the
  dielectric's smallest |ψ| is 2.7e-8 V, Cgg there is smooth against its neighbours (second
  difference 1.20e-3 C against 1.19e-3 on the level that needed no acceptance). A ±0.1 mV
  nudge of the gate bias reproduces it within 5e-9, but that check was run on the identical
  {py:mod}`meshconv <gf180tcad.tcad.meshconv>` level-1 {term}`job`, not on the production tree. The
  production run's acceptances were checked by the second difference alone. The two
  {py:mod}`meshconv <gf180tcad.tcad.meshconv>` level-2 acceptances (at −0.601 V and −0.599 V)
  are unchecked.

(moscap2d-sd)=

## The source/drain peak matters at Lmin

The pfet source/drain peak, `sd_peak_cm3` = 1e20 cm⁻³, is a `literature` value, not a card value.
With the junction depth {term}`XJ` fixed, the peak also sets the straggle (44.5, 42.0 and 39.9 nm
for 5e19, 1e20 and 2e20 cm⁻³), and so how far the p⁺ edge reaches under the gate: fixing XJ is a
modelling choice that couples the two. At the pfet {term}`Lmin` (0.5 µm) a factor of two in the
peak moves Cgg by −1.52 % / +1.25 % at worst (depletion), −0.56 % / +0.50 % in accumulation and
−0.03 % / +0.03 % in inversion; the effect is at the gate edges, so it falls as about 1/L. So the
2D Lmin depletion Cgg carries about ±1.5 % from this value, which belongs in the uncertainty list of the
calibration and comparison
({repo}`Task 12 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-12-calibrate-against-spice-cggvg>`,
{repo}`Task 13a <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-13a-tcad-results-and-docs-pages>`).
{test}`tests/tcad/test_moscap2d.py::test_pfet_sd_doping_insensitive` keeps the 0.1 % bound: it is a
{term}`strict expected failure` at Lmin (on the sensitivity assertion only) and asserted at L = 2 µm.

(moscap2d-l2)=

## The L = 2 µm cell: QS only, resumed, with a memory growth that is not fixed

- **QS only.** The L = 2 µm cell (501k nodes for the nfet) has no AC result (no `cgx.csv`). Its AC
  sweep needs the {term}`drift-diffusion` small-signal solve, and that fails in {{ DEVSIM }}'s direct
  solver ({term}`UMFPACK` 5.1, "umfpack numeric failed") at this size, as the L = 10 µm cell's equilibrium
  solve does ({ref}`moscap2d-l10`). The {term}`job` files record it (`ac` is
  {py:data}`~gf180tcad.tcad.moscap2d.AC_INFEASIBLE`, `ac_points` is 0).
- **Resumed after out-of-memory restarts.** The L = 2 µm QS sweeps ran under a memory cap and were
  restarted by the service manager after being killed; each restart resumed from the last saved
  point ({py:func}`~gf180tcad.tcad.moscap2d.resume_count`; `resumed` in the job files: 4 restarts for each
  device, after points 57, 97, 136 and 173 for the nfet and 34, 73, 113 and 162 for the pfet).
  The hand-off between points is the saved state, so a resumed sweep agrees with an uninterrupted
  one within 1e-12 (the solver tolerance) but is not byte-identical to it. The restart counts were
  backfilled from the progress logs, since the runs predate the record.
- **The per-point memory growth is unresolved.** The nfet L = 2 µm sweep grew by about 180 MB per
  point. It is flat on the uniform stack (101k nodes, 30 biases: 1321 to 1331 MB) and in repeated
  sweeps, so it is not in the per-point path as such; it appears on the source/drain cells. Two
  hypotheses are open: something only the source/drain cell has (four contacts, the inter-layer
  dielectric region), or memory-allocator fragmentation at large node counts. This is an open
  follow-up, not a fix: the resume mechanism works around it.

(moscap2d-reproduce)=

## `make reproduce` does not yet reproduce the 2D files

`make reproduce` ({ref}`one-command`) reruns the committed 2D cells with today's code, but the
committed 2D {term}`job` files cannot come out byte for byte:

- **Older job files.** The Lmin cells (`w10p0_l0p60`, `w10p0_l0p50`) were written by the
  Task 11 code. Their `cv.meta.json` has no `ac` and no `resumed` entry; the current job writes
  both (`"ac": "computed"`, `"resumed": {}`).
- **Resumed sweeps.** The L = 2 µm cells were resumed four times each
  ({ref}`moscap2d-l2`): `resumed` records
  `{"qs": 4}`, and a resumed sweep is not byte-identical to an uninterrupted one.
- **Restamped, not rerun.** The 2D mesh convergence and the 2D {term}`provenance` were restamped to the
  current generator without a rerun ({ref}`tcad-provenance`), twice: in Task 12 and to the
  per-tree hash of [issue #34](https://github.com/mithro/gf180-tcad/issues/34). So nothing shows that today's code gives their bytes.

So a full `make reproduce` is expected to report at least the four 2D `cv.meta.json` files in
`manifest verify`, and the L = 2 µm `cv.csv` too (a resumed sweep agrees with an uninterrupted one
only within the solver tolerance), until the 2D results are regenerated and committed. It has not been run end to end: the 2D jobs take hours at 16 GiB
each, one at a time. All the 1D results are reproduced byte for byte locally, and the calibrated 1D
results on GitHub-hosted runners ({ref}`cross-host-tcad`).

(moscap2d-meshes)=

## The meshes are not committed

Each {term}`job` under {repo}`results/tcad/moscap2d` has a 25–62 MB `mesh.msh` ({{ gmsh }} MSH 2.2). They are
git-ignored (`results/**/mesh.msh`) and left out of the {py:mod}`manifest <gf180tcad.manifest>`;
the job's `cv.meta.json` records the sha256 of the mesh as `mesh_sha256`. The mesh is a function of
the committed cell geometry and the committed
{repo}`selected.json <results/tcad/meshconv/moscap2d/nfet_05v0/selected.json>` of the
{ref}`mesh-convergence study <mesh-convergence>` (nfet; the pfet's is beside it), so it regenerates
byte for byte. Run this in the {term}`TCAD` image (here the nfet at Lmin; for the pfet use the device
{repo}`pfet_05v0 <data/process/pfet_05v0.toml>` and its geometries `w10p0_l0p50` and `w10p0_l2p00`,
for the nfet L = 2 µm the geometry `w10p0_l2p00`):

```
python3 -c "
from gf180tcad.tcad import __main__ as cli, meshconv, moscap2d, stack
device, gid = 'nfet_05v0', 'w10p0_l0p60'
proc, _ = cli.load_params(device, 'start')
xs = stack.build(proc, stack.cell(device, cli.geometry_of(device, gid)), with_sd=True)
dd = moscap2d.build_device(xs, meshconv.selected_spec(device, 2), mesh_file='mesh.msh')
dd.delete_device()
"
```

Its `sha256sum mesh.msh` must equal the `mesh_sha256` in `cv.meta.json`
({repo}`tests/tcad/test_moscap2d.py` checks a regenerated mesh placed beside the job's files). A full
rerun of a job with `python -m gf180tcad.tcad moscap --device nfet_05v0 --dim 2 --params start
--geometry w10p0_l0p60 --out <tree root>` writes the mesh too, and the
{py:func}`~gf180tcad.tcad.moscap2d.simulate` it runs takes hours.

**Output cache.** Instead of regenerating it, a mesh is to be fetched from the shared
{ref}`output cache <output-cache>` ({repo}`tools/output-cache`), keyed by its `mesh_sha256`.
None of the four committed start-value 2D jobs' meshes is in the cache (nor on any disk), so none can be
fetched yet: `tools/output-cache status` reports all four as absent. The first cached mesh
belongs to the calibrated {term}`Lmin` nfet cell of
[issue #35](https://github.com/mithro/gf180-tcad/issues/35). Once a mesh is in the cache,
`tools/output-cache pull results/tcad/moscap2d/<device>/<params>/<geometry>/mesh.msh` writes it
into place only if its sha256 matches. The cache is regenerable and holds no provenance; the
committed `cv.meta.json` stays the truth.

(moscap2d-calibrated)=

## The calibrated 2D cells

The calibrated 2D jobs ({ref}`cv-agreement-validation`, [issue #35](https://github.com/mithro/gf180-tcad/issues/35)) run the committed
cells with `--params calibrated`, one 16 GiB {term}`job` at a time. The committed cells:

| Cell | Nodes | QS sweep (min) | AC sweep (min) | Job total (min) |
|---|---|---|---|---|
| nfet `w10p0_l0p60` | 225964 | 102 | 86 | 189 |
| nfet `w10p0_l0p70` | 245515 | 112 | 97 | 210 |

| Cell | Peak memory (GiB) | Attempts |
|---|---|---|
| nfet `w10p0_l0p60` | 7.8 | 1 |
| nfet `w10p0_l0p70` | 5.9 | 1 |

The sweep times are the last `elapsed` of each sweep's progress log, meshing included. QS has
201 points and AC 21. The job total is the wall time of the host command.
The peak memory is the {term}`cgroup` `memory.peak` of the job's container, sampled every 15 s.
The run record, with the exit code and the image, is on {ref}`tcad-provenance`.

No job had a
round-off acceptance or an extended-precision fallback; each meshed oxide is 16.05 nm, the
calibrated value. The meshes are not committed ({ref}`moscap2d-meshes`); the output cache
({doc}`/reproduce/output-cache`) holds them under their `mesh_sha256`. The `--resume` scratch
directory of these jobs is outside the checkout, because the {term}`sandbox` refuses one
inside it ([issue #55](https://github.com/mithro/gf180-tcad/issues/55)).

**W1.6/L0.7 adds no 2D information.** The 2D cut has no width dependence.
The function {py:func}`~gf180tcad.tcad.stack.build` cuts the cell along L, through the middle of the gate
width. It keeps only the intervals of the active area, the gate and the contacts
on that line. The width enters only as `w_um`, which scales `cgg_total`.

W1.6/L0.7 therefore gives the per-width solve of W10/L0.7 when the PDK cell has the same
intervals on that line. The observed mesh identity is in [issue #77](https://github.com/mithro/gf180-tcad/issues/77). A W-series at fixed L then
tests the area scaling and the parasitic model, not the 2D solve.

The W1.6/L0.7 comparison follows from the committed W10/L0.7 cell. Its `cgg_per_um`
({repo}`cv.csv <results/tcad/moscap2d/nfet_05v0/calibrated/w10p0_l0p70/cv.csv>`) times 1.6 µm
is compared with the {term}`TT` {{ ngspice }} target of W1.6/L0.7 by
{py:func}`~gf180tcad.calibrate.cv.compare`. The result is {term}`Disagree`
({test}`tests/test_calibrate_cv.py::test_w1p6_l0p70_two_d_from_the_w10_l0p70_cell`):

| Check | Value | Verdict |
|---|---|---|
| Accumulation plateau, worst difference (%) | 7.6 | {term}`Same process` |
| Inversion plateau, worst difference (%) | 13.8 | Same process |
| Depletion crossing shift (mV) | −194 | Disagree |
| Inversion crossing shift (mV) | −33 | {term}`Agree` |

The W1.6/L0.7 2D job itself is "not run" ([issue #35](https://github.com/mithro/gf180-tcad/issues/35)).

(moscap2d-l10)=

## Not run: the 2D cell at L = 10 µm

The L = 10 µm cell is not simulated in 2D. At `DEFAULT_2D` it has about 2.0 million {term}`drift-diffusion`
unknowns, and the equilibrium drift-diffusion solve that sets up every 2D device fails inside
{{ DEVSIM }}'s direct solver ({term}`UMFPACK` 5.1: "umfpack numeric failed"; the {term}`Poisson stage`, 0.86 million
unknowns, still solves). A QS sweep of its 201 biases alone would take an estimated 7–8 hours from
the measured rates. Its long-channel C per area is covered by the 2D-equals-1D check and by the 1D
MOS capacitor. Later options are an iterative solver or a symmetric half domain.

## C/Cox > 1 that is physics: the fringe

Per drawn area, the PDK cell's C/Cox does exceed 1, and should. At the nfet {term}`Lmin`
(0.6 µm) without source or drain, C/Cox at −5 V and +5 V is 1.108 and 1.092 with the spacer
and inter-layer dielectric, and 0.987 and 0.977 when that dielectric is replaced by zero-flux
boundaries. The difference, about 0.12 Cox, is the outer fringe from the poly sidewalls to the
silicon outside the gate: BSIM4's CF of 0.0727 fF/µm per side would add
2 × 0.0727 / (0.6 µm × 2.272 fF/µm²) = 0.107 Cox. With source and drain, their doping that
reaches under the gate edges adds the overlap, and C/Cox per drawn area is 1.071 (accumulation) and
1.090 (inversion) at Lmin. {test}`tests/tcad/test_moscap2d.py::test_c_over_cox_le_1` therefore
checks C/Cox ≤ 1 where the gate oxide is the only path, and the fringe is reported, not tested.

## Limitations

- **The shallow trench isolation, spacers and {term}`LDD` are not modelled.** The domain ends at the
  active area with zero-flux sides; the spacer and inter-layer dielectric is one oxide.
- **The source/drain lateral straggle is a project choice** (equal to the vertical one). Its
  effect on the overlap capacitance is visible at Lmin.
- **The remaining discretisation bias** of the triangle mesh (a few 0.1 %) is below the 1 %
  mesh-convergence criterion and the 0.5 % 2D-equals-1D check, and far below the 5 %
  agreement criterion ({ref}`mesh-convergence-2d`).
- **No 2D result at L = 10 µm** ({ref}`moscap2d-l10`), and **no AC result at L = 2 µm**
  ({ref}`moscap2d-l2`).
- **Calibrated 2D results only at the nfet W10/L0.6 and W10/L0.7** ({ref}`moscap2d-calibrated`, [issue #35](https://github.com/mithro/gf180-tcad/issues/35)).
- **The pfet source/drain peak is uncertain** and matters at Lmin ({ref}`moscap2d-sd`).
