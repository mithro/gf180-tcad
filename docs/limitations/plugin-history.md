(plugin-history)=

# The gplugins DEVSIM plugin: it once worked

{term}`Phase 2` builds its {term}`TCAD` on the {{ DEVSIM }} plugin of {{ gplugins }}, the
{{ gdsfactory }} plugin collection. The plugin is broken on every recent gplugins release. The
project fixes it in {{ gplugins_fork }} rather than writing a new one, and old versions are used
only to prove that it once worked. This page is that proof. It is a committed record that
anyone can re-run: gplugins [v0.8.0](https://github.com/mithro/gplugins/tree/v0.8.0) on its own Sept-2023 stack, and the point where the
plugin broke, at [v1.4.2](https://github.com/mithro/gplugins/tree/v1.4.2). The port to the latest stack is checked against this record in
{ref}`plugin-history-latest`.

(plugin-history-timeline)=

## History of the plugin

All commits are linked in {{ gplugins_fork }}, which carries the upstream history unchanged.

- **Added**: [`a019e5a`](https://github.com/mithro/gplugins/commit/a019e5a8302858b38afde78740d3020b211248ad) ("add simulation",
  2023-08-01), first released in [v0.0.2](https://github.com/mithro/gplugins/tree/v0.0.2). It contains a {term}`drift-diffusion` solver on a
  component cross-section, [`DDComponent`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L43), meshed with {{ gmsh }}. It also contains a PIN (p-type, intrinsic, n-type) waveguide, [`PINWaveguide`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L101), on a
  {{ DEVSIM }} tensor mesh.
- **Last working release**: [v0.8.0](https://github.com/mithro/gplugins/tree/v0.8.0)
  ([`6245740`](https://github.com/mithro/gplugins/commit/624574ced6d9407306878c9fd00bede825640d94), 2023-09-20 17:57 UTC).
- **Import broken**: [`0ce7b30`](https://github.com/mithro/gplugins/commit/0ce7b30b81f128f81bc9b0b914700d84c2b4ed94) ("Consolidate gmsh
  plugin (#159)", 2023-09-20), first released in [v0.8.1](https://github.com/mithro/gplugins/tree/v0.8.1). It removed [`fuse_polygons`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/gmsh/parse_gds.py#L24) from
  [`gplugins.gmsh`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/gmsh/__init__.py), which [`get_simulation.py`](https://github.com/mithro/gplugins/blob/f47ed3de80b99bafc960955b3d6925e947d4fc0f/gplugins/devsim/get_simulation.py#L23-L27) still
  imports. From then on [`import gplugins.devsim`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/__init__.py) fails, and [v1.4.2](https://github.com/mithro/gplugins/tree/v1.4.2) still fails the same way.
- **Mesher removed**: [`017cede`](https://github.com/mithro/gplugins/commit/017cede91e322426144bd1cb5dc8ede78b830878) (2025-11-09),
  first released in [v2.0.0](https://github.com/mithro/gplugins/tree/v2.0.0), moved `gplugins.gmsh` to the new {{ meshwell }} API. [`create_2Duz_simulation`](https://github.com/mithro/gplugins/blob/208784df45f1db8b262f356ee2a67fa3808c3e1e/gplugins/devsim/get_simulation.py#L71),
  the mesher behind `DDComponent`, now raises [`NotImplementedError`](https://docs.python.org/3/library/exceptions.html#NotImplementedError) ("uz_xsection_mesh has been removed").

The PIN waveguide never needed gmsh. The path that broke is `DDComponent` with the mesher,
so the record below covers that path.

(plugin-history-record)=

## The record

{py:func}`python -m gf180tcad.history <gf180tcad.history.main>` ({py:mod}`gf180tcad.history`)
rebuilds one record, a JSON file in {repo}`results/plugin-history`. It has three steps, each in
the base image ({repo}`docker/IMAGE`), and the last two in the {term}`sandbox`:

1. The gplugins sources are taken from the fork's tag with
   [`git archive`](https://git-scm.com/docs/git-archive) (host).
2. The packages are installed, with network. For v0.8.0 this is {{ Python }} 3.11.17 and the
   hashed, resolved set {repo}`experiments/plugin-history/v080.lock`. The lock was compiled once
   with {{ uv }}, with [`--exclude-newer`](https://docs.astral.sh/uv/reference/cli/#uv-pip-compile--exclude-newer) set to the
   v0.8.0 release time, so it holds devsim 2.6.3, gdsfactory 7.6.1, meshwell 1.0.1 and
   gmsh 4.11.1. For v1.4.2 it is [`uv sync --frozen`](https://docs.astral.sh/uv/reference/cli/#uv-sync) from the tag's own uv
   lock file, with the base image's Python 3.12.
3. The fixed checks run, with no network and no {term}`PDK` preselected (the
   {repo}`PDK <docker/base/Dockerfile#L33>` environment
   variable is unset). They are {repo}`experiments/plugin-history/checks_v080.py` and
   {repo}`experiments/plugin-history/checks_v142.py`.

The commands and the lock recipe are in {repo}`experiments/plugin-history/README.md`.

The checks come from two blocks of the v0.8.0 source:

- **PIN waveguide.** The body of
  [`test_pin_waveguide`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/test_devsim.py#L4-L31): [`PINWaveguide`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L101) (500 nm × 220 nm
  core, 90 nm slab), [`ddsolver()`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L385), then [`ramp_voltage`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L420).
- **PN slab.** The [`__main__`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L412-L524) block of `get_solver.py`: a trimmed [`straight_pn`](https://github.com/gdsfactory/gdsfactory/blob/v7.6.1/gdsfactory/components/straight_pin.py#L90) as a [`DDComponent`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L43), [`ddsolver()`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L204) and
  [`get_refined_mesh`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L328). **The block solves only at equilibrium: it never calls `ramp_voltage`.** The PN-slab
  ramp to 0.1 and 0.2 V is an addition of this record. It uses [`ramp_voltage`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L243-L245)'s default contact,
  `cathode` (the contact on the p⁺⁺ side, so the bias is forward).

The checks, and what each one runs:

- {repo}`import <experiments/plugin-history/checks_v080.py#L338>`:
  [`import gplugins.devsim`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/__init__.py).
- {repo}`pin_test <experiments/plugin-history/checks_v080.py#L62>`: the PIN waveguide build and
  [`ddsolver()`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L385).
- {repo}`ramp <experiments/plugin-history/checks_v080.py#L102>`
  ({repo}`PN part <experiments/plugin-history/checks_v080.py#L288>`):
  [`ramp_voltage`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L420)
  of the PIN waveguide to 0 and −1 V. The added part ramps the PN-slab cathode to 0.1 and 0.2 V.
- {repo}`ddcomponent_mesh <experiments/plugin-history/checks_v080.py#L187>`: the PN-slab
  `DDComponent(...)`.
- {repo}`ddsolver <experiments/plugin-history/checks_v080.py#L357>`:
  [`ddsolver()`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L204)
  on the PN slab (meshing with gmsh, then solving).
- {repo}`refine <experiments/plugin-history/checks_v080.py#L304>`:
  [`get_refined_mesh`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L328)
  on the PN slab, as in the block.
- {repo}`refined_solve <experiments/plugin-history/checks_v080.py#L375>`: the block's last step,
  a second `DDComponent` solved with `global_meshsize_array`; recorded as not run, because it
  needs the output of `refine`.

(plugin-history-changes)=

### Changes from the v0.8.0 code

- **Generic PDK activated first.** [`get_layer_stack()`](https://github.com/gdsfactory/gdsfactory/blob/v7.6.1/gdsfactory/pdk.py#L758) in the block needs an active PDK.
- **Layer map.** gdsfactory 7.6.1 has no `gf.tech` module, so the block's
  [`gf.tech.LayerMap()`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L425) raises [`AttributeError`](https://docs.python.org/3/library/exceptions.html#AttributeError). The
  driver uses the generic layer map [`gdsfactory.generic_tech.LAYER`](https://github.com/gdsfactory/gdsfactory/blob/v7.6.1/gdsfactory/generic_tech/__init__.py#L13).
- **PIN before PN.** The PIN waveguide is solved, ramped and deleted before the PN slab is
  built. DEVSIM solves every device it holds at once, and `DDComponent` turns on extended
  precision globally, so this order gives each block the solver state it has on its own.
- **Dropped from [`test_pin_waveguide`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/test_devsim.py#L4-L31).** Its −5 V ramp and its {{ tidy3d }} mode solves
  ([`make_waveguide`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L485)).
- **Added.** The PN-slab ramp, and the physical quantities recorded around it (below).
- **Never reached.** The block's second solve on the refined mesh
  ([`get_solver.py:511-524`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L511-L524)), because `refine`
  raises before it.

(plugin-history-results)=

## Results

On this page, v0.8.0 × 0.5 is v0.8.0 with the PN mesh × 0.5.

| Check | v0.8.0 | v0.8.0 × 0.5 | v1.4.2 |
|---|---|---|---|
| `import` | pass | pass | **fail** |
| `pin_test` | pass | pass | not run |
| `ramp` | pass | pass | not run |
| `ddcomponent_mesh` | pass | pass | not run |
| `ddsolver` | pass | pass | not run |
| `refine` | **fail** | **fail** | not run |
| `refined_solve` | not run | not run | not run |

The records are {repo}`results/plugin-history/v0.8.0.json`,
{repo}`results/plugin-history/v0.8.0-mesh0p5.json` and
{repo}`results/plugin-history/v1.4.2.json`. Each one gives the resolved package versions and the
exact exception type, message and source line of every failed check.

- **v0.8.0 worked.** The PIN waveguide and the PN slab both mesh, solve and ramp.
- **`get_refined_mesh` was already broken at v0.8.0.** Its body reads `c`, the
  [variable of the `__main__` block](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L480), instead of
  [`self`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L328-L330)
  ([`get_solver.py:359`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L359)). Called from anywhere but
  that block, it raises a [`NameError`](https://docs.python.org/3/library/exceptions.html#NameError),
  `NameError: name 'c' is not defined`, in both v0.8.0 runs.
- **v1.4.2 does not import.** The error is an
  [`ImportError`](https://docs.python.org/3/library/exceptions.html#ImportError) naming
  `fuse_polygons`. Its message is `ImportError: cannot import name 'fuse_polygons'
  from 'gplugins.gmsh'`, raised at [`gplugins/devsim/get_simulation.py:23`](https://github.com/mithro/gplugins/blob/f47ed3de80b99bafc960955b3d6925e947d4fc0f/gplugins/devsim/get_simulation.py#L23-L27).

(plugin-history-numbers)=

### Physical quantities

The {term}`depletion width` is the span of the nodes on one mesh row where both n and p are
below 1e-2 |[`NetDoping`](https://devsim.net/models.html#node-models)|. The bias is the cathode
voltage of the ramp; "equilibrium" is the solve before the ramp.

**PIN waveguide**, depletion width (µm):

| Bias (V) | v0.8.0 | v0.8.0 × 0.5 |
|---|---|---|
| 0 | 0.069 | 0.069 |
| −1 | 0.138 | 0.138 |

**PN slab, mesh and equilibrium:**

| Quantity | v0.8.0 | v0.8.0 × 0.5 |
|---|---|---|
| NetDoping minimum (cm⁻³) | −1.1e+18 | −1.1e+18 |
| NetDoping maximum (cm⁻³) | 1.1e+18 | 1.1e+18 |
| mesh nodes | 3523 | 11326 |
| depletion width (µm) | 0.0386 | 0.0688 |
| depleted nodes | 2 | 8 |
| Potential span over the silicon (V) | 1.3613 | 1.6267 |
| Potential at the junction, ψ(x_j) (V) | −0.47002 | −0.67054 |
| rib/slab Potential jump (V) | 0.46 | 0.73 |

In the two ramp tables, "span" is the PN-slab Potential span over the silicon, "anode −
cathode" the anode − cathode contact potential and "drop" the junction drop, all in V.

**PN slab during the ramp, v0.8.0:**

| Bias (V) | Span | Anode − cathode | Drop |
|---|---|---|---|
| 0 | 1.3613 | 0.9587 | 0.83450 |
| 0.1 | 1.3613 | 0.8587 | 0.83450 |
| 0.2 | 1.3613 | 0.7587 | 0.83450 |

**PN slab during the ramp, v0.8.0 × 0.5:**

| Bias (V) | Span | Anode − cathode | Drop |
|---|---|---|---|
| 0 | 1.6267 | 0.9587 | 0.83450 |
| 0.1 | 1.6267 | 0.8587 | 0.83450 |
| 0.2 | 1.6267 | 0.7587 | 0.83450 |

What the quantities are:

- **PIN depletion width:** on the mesh row nearest the rib's vertical centre.
- **PN-slab mesh nodes:** the sum over its four DEVSIM regions.
- **PN-slab depletion width and depleted nodes:** on the bottom edge, y = 0.
- **PN-slab Potential span over the silicon:** recorded as `builtin_potential_v`; it is
  non-physical, see below.
- **PN-slab junction drop:** ψ(x_j − 0.2 µm) − ψ(x_j + 0.2 µm) on the bottom edge, with
  x_j = 4.0 µm.
- **PN-slab rib/slab Potential jump:** at the rib's two bottom vertices
  ({repo}`boundary_jump_v <experiments/plugin-history/harness.py#L182>`).
- **PN-slab mesh physical groups**
  ({repo}`msh_physical_groups <experiments/plugin-history/checks_v080.py#L281>`), the same at
  both meshes: anode, cathode, core, slab90, slab90\_\_\_anode, slab90\_\_\_cathode, and
  **no core\_\_\_slab90**.

The PN slab's mesh is unstructured and has no row at mid-height. Its bottom edge is the only
mesh row through the junction, which lies under the rib, so both silicon regions are used there.
The PN-slab depletion width is limited by the mesh. At full mesh it rests on 2 depleted nodes,
and at mesh × 0.5 on 8. So the re-verification compared it at mesh × 0.5
({ref}`plugin-history-latest-pn`).

The record's **junction probe** holds the mesh physical groups, the junction drop, ψ(x_j) and the
rib/slab jump. Its code is {repo}`pn_junction <experiments/plugin-history/checks_v080.py#L202>`, with
{repo}`junction_probe <experiments/plugin-history/harness.py#L145>` and
{repo}`msh2_physical_names <experiments/plugin-history/harness.py#L134>`. It uses the
definitions of the fork's latest-stack probe
([`_junction`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/tests/test_mesh.py#L248)): x_j is the metallurgical
junction on the bottom edge, ψ(x_j ∓ 0.2 µm) are the neutral n and p sides inside the rib, and
the jump is the larger Potential difference between the `core` and `slab90` nodes at the rib's
two bottom vertices. Each record also holds the Potential range of each silicon region at every
step (`potential_range_by_region`).

(plugin-history-junction)=

**The bias does not reach the junction, because the rib floats.** This was the record's
leading hypothesis, and the junction probe confirms it:
- **The mesh has no [`core___slab90`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/get_simulation.py#L189) group.** v0.8.0's mesher never tagged the boundary between
  the rib (`core`), which holds the whole pn junction, and the slab (`slab90`). So the DEVSIM
  device has no interface there, and the rib is a region with no path to either contact. The
  contacts are on the slab, so the bias moves the slab and the contact potentials only.
- **The junction drop never changes with bias.** It stays at 0.83450 V, the {term}`built-in potential`
  V_t ln(N_A N_D / n_i²) = 0.834503 V of the rib's own 1e17 / 1e17 cm⁻³ junction, with
  {term}`Boltzmann statistics` and the constants of DEVSIM's
  [`simple_physics`](https://github.com/devsim/devsim/blob/ec9905bbfdfacaf66e0cae7f2d98748f9bb8aeb0/python_packages/simple_physics.py)
  (300 K).
- **The Potential is discontinuous at the rib's bottom vertices**, by 0.46 V at equilibrium (0.73 V at
  mesh × 0.5). The jump grows by the applied bias, because only the slab moves.
- **The rib's absolute Potential depends on the mesh** (ψ(x_j) is −0.47002 V at full mesh and
  −0.67054 V at × 0.5), because nothing fixes it. This explains the non-physical Potential
  span: it is the anode contact potential (+0.4793 V, the slab's maximum) minus the floating
  rib's minimum, 0.4793 + 0.8820 = 1.3613 V and 0.4793 + 1.1474 = 1.6267 V
  ({test}`tests/test_plugin_history.py::test_committed_v080_junction_probe`).

The anode − cathode contact potential still falls by exactly the 0.1 V step each time. At
equilibrium it matches the ideal built-in potential of the ±1.1e18 cm⁻³ contacts (≈ 0.957 V),
because it is set by the doping of the {term}`ohmic contacts <ohmic contact>` alone.

The record shows that v0.8.0's mesh has no rib/slab boundary; why its mesher drops it is
open ([issue #79](https://github.com/mithro/gf180-tcad/issues/79)).

**All recorded currents are below the solver's current floor.**
- **PN slab:** below 1e-26 A/cm. The anode current is the same at both biases, and at half mesh
  size the cathode current changes sign.
- **PIN waveguide:** 1.0e-15 to 4.9e-15 A/cm in magnitude, and nonzero at 0 V. Left + right is not 0 at either bias.

The record keeps these values as v0.8.0 computed them. They are evidence that the solver ran,
not that its answer is right.

**What the re-verification compared.** The port to the latest stack was checked against
these quantities in {ref}`plugin-history-latest`:
- the depletion widths;
- the built-in potential (the equilibrium anode − cathode contact potential) and the NetDoping range;
- the region, contact and interface names;
- the node counts;
- whether the applied bias reaches the device.

It had to explain the currents, not match them, and it did
({ref}`plugin-history-latest-junction`).

(plugin-history-reproducibility)=

## Reproducibility

Two local runs give byte-identical records. The record holds no timings and no host paths
({test}`tests/test_plugin_history.py::test_history_json_has_no_timings_or_paths`). The
{test}`tests/test_plugin_history.py::test_v080_once_worked` and
{test}`tests/test_plugin_history.py::test_v142_import_broken` tests re-run the record in the
sandbox (`pytest -m sandbox`, {{ pytest }}) and compare it with the committed one. The record is
listed in the {term}`manifest`.

**It is not part of the check on another computer (a {{ GitHub_hosted_runner }})**
({ref}`cross-host-determinism`). That check covers only {repo}`results/spice`. The 2023 stack
has {{ numpy }} 1.26 with its own {term}`SIMD dispatch` and no guarantee of the same bytes on
another computer, so the record is reproducible on one host only.

(plugin-history-latest)=

## Re-verified on latest

The plugin is fixed in {{ gplugins_fork }} and runs on the latest stack:
{{ DEVSIM }} 2.11.1, {{ meshwell }} 2.5.2, {{ gmsh }} 4.15.2, {{ gdsfactory }} 9.51.0 and
{{ Python }} 3.13, in the {term}`stable TCAD image` ({repo}`docker/TCAD_IMAGE`). The re-verification
was made with gf180-tcad pinning the fork at [`400f842`](https://github.com/mithro/gplugins/commit/400f8423d7b0d1aac48eea1c0145342d0c1f766a) through the
{repo}`third_party/gplugins <.gitmodules>` submodule, and all file links below are at that commit.

The pin is [`0715c81`](https://github.com/mithro/gplugins/commit/0715c81c4439533512621a97358d9d779411ebf6).
It also includes {repo}`Task 8 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-8-fork-cv-solver-api>`,
the {term}`C–V` solver ([mithro/gplugins#6](https://github.com/mithro/gplugins/pull/6)),
and the fork pull requests [mithro/gplugins#9](https://github.com/mithro/gplugins/pull/9) to
[#12](https://github.com/mithro/gplugins/pull/12).

It ends with the backend seam of
{repo}`Task 15 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-15-required-first-step-of-spec-121-backend-seam-in-the-plugin>`,
[mithro/gplugins#13](https://github.com/mithro/gplugins/pull/13), whose merge commit is the pin.
The seam puts `device_description.py` and `results.py`, which import no simulator, in front of
the DEVSIM backend `backends/devsim.py` (formerly `get_solver.py`, which stays as an alias).
It changes no API that gf180-tcad uses and no result ({ref}`tcad-provenance`).
The file links in this section stay at the commits they name.

**Where the numbers come from.** Every latest-stack value in this section is one that the
linked fork tests assert or record. They ran in the fork's own continuous integration (CI), in the TCAD image, at the
pinned `400f842`. Their values are quoted here from those runs. This repository does not
measure them:
- its own tests check only that the submodule is pinned on the fork's main and that
  `import gplugins` resolves to the submodule in the TCAD image
  ({test}`tests/test_submodule.py::test_submodule_pinned_on_fork_main`,
  {test}`tests/test_submodule.py::test_plugin_imports_from_submodule`);
- its sandbox rebuild ({ref}`plugin-history-reproducibility`) recomputes only the v0.8.0 side,
  {repo}`results/plugin-history/v0.8.0.json` and {repo}`results/plugin-history/v0.8.0-mesh0p5.json`.

| Fork PR | Merge commit |
|---|---|
| [mithro/gplugins#2](https://github.com/mithro/gplugins/pull/2) | [`4b0a07a`](https://github.com/mithro/gplugins/commit/4b0a07a78b5a282bb15cee230dc906aa17ee2529) |
| [mithro/gplugins#4](https://github.com/mithro/gplugins/pull/4) | [`ddbf280`](https://github.com/mithro/gplugins/commit/ddbf280e001f83439bb67756544c0a5ad1a63528) |
| [mithro/gplugins#3](https://github.com/mithro/gplugins/pull/3) | [`b519c87`](https://github.com/mithro/gplugins/commit/b519c87e79882baa71fb89bb77c2956b9ff56257) |
| [mithro/gplugins#5](https://github.com/mithro/gplugins/pull/5) | [`400f842`](https://github.com/mithro/gplugins/commit/400f8423d7b0d1aac48eea1c0145342d0c1f766a) |
| [mithro/gplugins#6](https://github.com/mithro/gplugins/pull/6) | [`dddaa07`](https://github.com/mithro/gplugins/commit/dddaa071321c5177c8471312c565ad86d4b245d7) |

What each fork PR changes:

- **#2:** `import gplugins.devsim` works on the latest stack. Its changes are lazy {{ tidy3d }} and
  {{ pyvista }} imports and the removal of {{ pydantic }}'s deprecated
  [`Extra`](https://docs.pydantic.dev/latest/api/config/). They also cover the
  [`NameError`](https://docs.python.org/3/library/exceptions.html#NameError) of
  [`get_refined_mesh`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/get_solver.py#L631),
  [`delete_device`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/get_solver.py#L624),
  and silicon models only on regions with NetDoping. It also adds a {{ GitHub_Actions }} CI
  check in the TCAD image.
- **#4:** [`create_2Duz_simulation`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/get_simulation.py#L41)
  meshes again, with meshwell 2.5
  ([`mesh_xsection`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/meshing.py#L104),
  single-threaded, fixed seed, MSH 2.2). Physical names come from {{ meshio }}'s `field_data`,
  without which no interface was added.
- **#3:** analytic doping profiles
  ([`doping.py`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/doping.py)).
- **#5:** typed contacts, materials from cited constants and the 1D stack builder
  ([`stack1d.py`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/stack1d.py)).
- **#6:** the {term}`C–V` solver
  [`sweep_cv`](https://github.com/mithro/gplugins/blob/dddaa071321c5177c8471312c565ad86d4b245d7/gplugins/devsim/cv.py)
  ({repo}`Task 8 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-8-fork-cv-solver-api>`:
  quasi-static and small-signal AC,
  [`cv.py`](https://github.com/mithro/gplugins/blob/dddaa071321c5177c8471312c565ad86d4b245d7/gplugins/devsim/cv.py)),
  included since gf180-tcad pins
  [`dddaa07`](https://github.com/mithro/gplugins/commit/dddaa071321c5177c8471312c565ad86d4b245d7).
  It adds a module and changes none of the paths below.

The PRs #2 and #4 are the port that this section re-verifies. #3, #5 and #6 extend the plugin
for the {term}`MOS capacitors <MOSCAP>` of
{repo}`Phase 2 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md>` and do not change the paths below.

(plugin-history-latest-pin)=

### PIN waveguide: bit-identical

The PIN waveguide uses DEVSIM's own tensor mesh, so the port changes only its imports. On the
latest stack its depletion widths are **bit-identical** to v0.8.0's
([`test_pin_depletion_width_match_v080`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/test_devsim.py#L134)):

The v0.8.0 stack has devsim 2.6.3 and Python 3.11; the latest has devsim 2.11.1 and Python 3.13.
Each difference between them is 0:

| Quantity | v0.8.0 and latest |
|---|---|
| depletion width at 0 V (µm) | 0.06898074973467581 |
| depletion width at −1 V (µm) | 0.13782918124914934 |
| cut row y (µm) | 0.11027488009949704 |
| depleted nodes at 0 V | 51 |
| depleted nodes at −1 V | 82 |

The test allows 1e-6 relative; the measured difference is 0. The contact currents are
bit-identical too, and stay below the 1e-13 A/cm floor
([`test_pin_currents_below_floor`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/test_devsim.py#L144)). They are
still nonzero at 0 V and left + right ≠ 0, so they remain solver noise.

(plugin-history-latest-pn)=

### PN slab: the anchors

The PN slab is the one of {repo}`experiments/plugin-history/checks_v080.py`, ported to
gdsfactory 9 in the fork's
[`tests/test_mesh.py`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/tests/test_mesh.py) and meshed by meshwell, not
by v0.8.0's mesher. Each allowed difference is the larger of the two meshers' self-differences, mesh × 1
against × 0.5: v0.8.0's from {repo}`results/plugin-history/v0.8.0.json` and
{repo}`results/plugin-history/v0.8.0-mesh0p5.json`, the port's from the same `resolutions` at
both scales
([`test_pn_slab_physical_anchors_match_v080`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/tests/test_mesh.py#L366)).

The names, which must match exactly at both mesh scales:

| Anchor | v0.8.0 | latest |
|---|---|---|
| regions → material | Aluminum: anode, cathode; si: slab90, core | the same |
| DEVSIM regions / contacts | anode, cathode, core, slab90 / anode, cathode | the same |
| interfaces | slab90\_\_\_anode, slab90\_\_\_cathode | the same **plus core\_\_\_slab90** |

The regions and the contacts match. The interfaces differ by `core___slab90`, the fix (see below).

The numbers, at mesh × 1 and × 0.5. Every anchor matches within its allowed difference; the node
count is reported, not asserted. The v0.8.0 anode − cathode at 0 V is 0.9586540658880733 V at
× 1 and …742 at × 0.5. The other v0.8.0 values:

| Anchor | × 1 | × 0.5 |
|---|---|---|
| anode − cathode at 0.1 V (V) | 0.85865 | the same |
| anode − cathode at 0.2 V (V) | 0.75865 | the same |
| step per 0.1 V of bias (V) | 0.1 | 0.1 |
| NetDoping range (cm⁻³) | ±1.1e18 | ±1.1e18 |
| depletion width, bottom edge (µm) | 0.03863 | 0.06883 |
| depletion width against the {term}`depletion approximation` (µm) | not applicable | not applicable |
| node count | 3523 | 11326 |

The latest values:

| Anchor | × 1 | × 0.5 |
|---|---|---|
| anode − cathode at 0 V (V) | within 8.9e-16 of v0.8.0 | the same as × 1 |
| anode − cathode at 0.1 V (V) | within the allowed difference | the same |
| anode − cathode at 0.2 V (V) | within the allowed difference | the same |
| step per 0.1 V of bias (V) | 0.1 | 0.1 |
| NetDoping range (cm⁻³) | ±1.1e18 | ±1.1e18 |
| depletion width, bottom edge (µm) | 0.06000 | 0.06000 |
| depletion width against the depletion approximation (µm) | not applicable | 0.06000 |
| node count | 3384 | 10424 |

The allowed differences:

| Anchor | Allowed difference |
|---|---|
| anode − cathode at 0 V (V) | 8.9e-16 |
| anode − cathode at 0.1 V (V) | 8.9e-16 |
| anode − cathode at 0.2 V (V) | 8.9e-16 |
| step per 0.1 V of bias (V) | 8.9e-16 plus two {term}`ulp` |
| NetDoping range (cm⁻³) | exact |
| depletion width, bottom edge (µm) | 0.0302 |
| depletion width against the depletion approximation (µm) | 0.0100 |
| node count | not asserted |

- **anode − cathode:** the allowed difference, 8.9e-16 V, is 4 {term}`ulp` of 1 V. The port's
  self-difference (× 1 against × 0.5) is 0.
- **depletion width, bottom edge:** compared at × 0.5. The allowed difference is v0.8.0's
  self-difference, 0.0302 µm; the port differs from v0.8.0 by Δ = 0.0088 µm.
- **depletion width against the depletion approximation:** the approximation gives 0.06664 µm.
  The allowed difference is one bottom-edge node spacing, 0.0100 µm; Δ = 0.0066 µm at × 0.5.

The anode − cathode potential is a boundary-condition check, not a mesh check: it is the
ohmic-contact difference 2 V_t ln(1.1e18 / n_i), set by the contact doping alone, which is why
both self-differences are at the ulp level. The depletion width is a difference of two node
positions, so it is quantised to the node spacing; the port's × 1 = × 0.5 equality is a
coincidence of that.

(plugin-history-latest-junction)=

### PN slab: the bias now reaches the junction

The port meshes the rib/slab boundary, so its device has the [`core___slab90`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/get_simulation.py#L189) interface, and
the plugin adds it like every other `a___b` group of the mesh
([`get_simulation.py`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/get_simulation.py#L189)). This is the cause of
v0.8.0's "bias does not reach the junction" ({ref}`the junction probe <plugin-history-junction>`), now fixed. It is
an extra interface compared with v0.8.0, kept deliberately: dropping it would mean adding code
to reproduce a defect of the old mesher.

[`test_pn_slab_currents_explained`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/tests/test_mesh.py#L462) solves
the same mesh both ways on the latest stack (mesh × 1):

The cathode voltage steps through 0, 0.1 and 0.2 V; with `core___slab90` left out, the values
are the same at every step. "v0.8.0 topology" leaves `core___slab90` out of DEVSIM; "as ported"
uses every interface. The potentials:

| Device | V_cathode (V) | Junction drop (V) | Rib/slab jump (V) |
|---|---|---|---|
| v0.8.0 topology | every step | 0.834504 | 0.118 |
| as ported | 0 | 0.834504 | 0 |
| as ported | 0.1 | 0.734504 | 0 |
| as ported | 0.2 | 0.634504 | 0 |

The currents:

| Device | V_cathode (V) | I_anode (A/cm) | I_cathode (A/cm) |
|---|---|---|---|
| v0.8.0 topology | every step | below 1e-26 | below 1e-26 |
| as ported | 0 | below 1e-26 | below 1e-26 |
| as ported | 0.1 | −9.749e-15 | 9.749e-15 |
| as ported | 0.2 | −1.005e-13 | 1.005e-13 |

- **Leaving the interface out reproduces v0.8.0's signatures:** a constant junction drop at the
  rib's built-in potential, currents below the noise floor and a nonzero rib/slab jump. The
  floating rib's absolute Potential differs from v0.8.0's, because only the initial guess and
  the mesh set it, so only differences inside the rib are compared.
- **As ported, the bias reaches the junction.** The drop falls by exactly the applied 0.1 V per
  step, 0.8345 → 0.7345 → 0.6345 V (asserted within 1e-3 V), and the two regions agree at the
  bottom vertices (jump below 1e-6 V).
- **The forward current is conserved and grows like a diode's.** Anode = −cathode within 1e-6
  relative, and the current grows from 9.7e-15 to 1.0e-13 A/cm between 0.1 and 0.2 V. For
  I = I0 (exp(V / n V_t) − 1), I2 / I1 = exp(a) + 1 with a = 0.1 V / (n V_t), so the implied
  {term}`ideality factor` n = 0.1 V / (V_t ln(I2 / I1 − 1)) is **1.73**, within the [1, 2] the test asserts.

The v0.8.0 side of this comparison is the junction probe of the record
({ref}`plugin-history-numbers`), which {py:func}`python -m gf180tcad.history --version v0.8.0
<gf180tcad.history.main>` recomputes on the 2023 stack. The docstring of
[`test_pn_slab_currents_explained`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/tests/test_mesh.py#L462) still
cites those numbers as measured ad hoc. Their committed source is
{repo}`experiments/plugin-history/checks_v080.py`, and the values are in
{repo}`results/plugin-history/v0.8.0.json` and {repo}`results/plugin-history/v0.8.0-mesh0p5.json`.
