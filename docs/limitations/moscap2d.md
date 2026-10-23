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

**The symptom.** In the {term}`Phase 2` research spike a 2D MOS capacitor gave C/Cox = 1.0039 at −5 V
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
| As first built (meshwell defaults, oxide spacing 2 nm) | **1.00126**, +2.07 % | 0.98765, +0.66 % |
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
spacing by r and kept the grading, as the 1D study does. The meshwell size field of the body
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
  refinement levels, Newton stalls there for 45 iterations. The plugin's `roundoff_accept` accepts
  such a solve only under narrow conditions (every potential update ≤ the 1e-12 V `abs_tol` and
  ≤ 32·eps·max|ψ| over the last 10 iterations, a plateau of the relative error, and a node
  with |ψ| small enough to explain it), after solving it again to that round-off state, because
  DEVSIM restores the previous solution of a solve it calls non-converged. Every accepted point is
  recorded. At the nfet level-1 point the accepted update is 1.6e-16 V (the bound 4.2e-15 V), the
  dielectric's smallest |ψ| is 2.7e-8 V, Cgg there is smooth against its neighbours (second
  difference 1.20e-3 C against 1.19e-3 on the level that needed no acceptance) and a ±0.1 mV
  nudge reproduces it within 5e-9.

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

(moscap2d-l10)=

## Not run: the 2D cell at L = 10 µm

The L = 10 µm cell is not simulated in 2D. At `DEFAULT_2D` it has about 2.0 million {term}`drift-diffusion`
unknowns, and the equilibrium drift-diffusion solve that sets up every 2D device fails inside
{{ DEVSIM }}'s direct solver (UMFPACK 5.1: "umfpack numeric failed"; the Poisson stage, 0.86 million
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
- **No 2D result at L = 10 µm** ({ref}`moscap2d-l10`).
- **The pfet source/drain peak is uncertain** and matters at Lmin ({ref}`moscap2d-sd`).
