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
  component cross-section, [`DDComponent`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L43), meshed with {{ gmsh }}, and a PIN waveguide, [`PINWaveguide`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L101), on a
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

| Check | What runs |
|---|---|
| {repo}`import <experiments/plugin-history/checks_v080.py#L338>` | [`import gplugins.devsim`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/__init__.py) |
| {repo}`pin_test <experiments/plugin-history/checks_v080.py#L62>` | the PIN waveguide build and [`ddsolver()`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L385) |
| {repo}`ramp <experiments/plugin-history/checks_v080.py#L102>` ({repo}`PN part <experiments/plugin-history/checks_v080.py#L288>`) | [`ramp_voltage`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L420) of the PIN waveguide to 0 and −1 V, and (added) of the PN-slab cathode to 0.1 and 0.2 V |
| {repo}`ddcomponent_mesh <experiments/plugin-history/checks_v080.py#L187>` | the PN-slab `DDComponent(...)` |
| {repo}`ddsolver <experiments/plugin-history/checks_v080.py#L357>` | [`ddsolver()`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L204) on the PN slab (meshing with gmsh, then solving) |
| {repo}`refine <experiments/plugin-history/checks_v080.py#L304>` | [`get_refined_mesh`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L328) on the PN slab, as in the block |
| {repo}`refined_solve <experiments/plugin-history/checks_v080.py#L375>` | the block's last step, a second `DDComponent` solved with `global_meshsize_array`; recorded as not run, because it needs the output of `refine` |

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

| Check | v0.8.0 | v0.8.0, PN mesh × 0.5 | v1.4.2 |
|---|---|---|---|
| `import` | pass | pass | **fail**: [`ImportError`](https://docs.python.org/3/library/exceptions.html#ImportError) naming `fuse_polygons` |
| `pin_test` | pass | pass | not run |
| `ramp` | pass | pass | not run |
| `ddcomponent_mesh` | pass | pass | not run |
| `ddsolver` | pass | pass | not run |
| `refine` | **fail**: [`NameError`](https://docs.python.org/3/library/exceptions.html#NameError) | **fail**: `NameError` | not run |
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
  that block, it raises `NameError: name 'c' is not defined`.
- **v1.4.2 does not import.** The error is `ImportError: cannot import name 'fuse_polygons'
  from 'gplugins.gmsh'`, raised at [`gplugins/devsim/get_simulation.py:23`](https://github.com/mithro/gplugins/blob/f47ed3de80b99bafc960955b3d6925e947d4fc0f/gplugins/devsim/get_simulation.py#L23-L27).

(plugin-history-numbers)=

### Physical quantities

The {term}`depletion width` is the span of the nodes on one mesh row where both n and p are
below 1e-2 |[`NetDoping`](https://devsim.net/models.html#node-models)|.

| Quantity | v0.8.0 | v0.8.0, PN mesh × 0.5 |
|---|---|---|
| PIN depletion width at 0 V / −1 V (row nearest the rib's vertical centre) | 0.069 / 0.138 µm | the same |
| PN-slab NetDoping range | −1.1e+18 … 1.1e+18 cm⁻³ | −1.1e+18 … 1.1e+18 cm⁻³ |
| PN-slab Potential span over the silicon at equilibrium (recorded as `builtin_potential_v`; non-physical, see below) | 1.3613 V | 1.6267 V |
| PN-slab depletion width at equilibrium (bottom edge, y = 0) | 0.0386 µm (2 depleted nodes) | 0.0688 µm (8 depleted nodes) |
| PN-slab mesh nodes (sum over its four DEVSIM regions) | 3523 | 11326 |
| PN-slab anode − cathode contact potential at 0 / 0.1 / 0.2 V | 0.9587 / 0.8587 / 0.7587 V | 0.9587 / 0.8587 / 0.7587 V |
| PN-slab Potential span over the silicon at 0 / 0.1 / 0.2 V | 1.3613 / 1.3613 / 1.3613 V | 1.6267 / 1.6267 / 1.6267 V |
| PN-slab mesh physical groups (`msh_physical_groups`) | anode, cathode, core, slab90, slab90\_\_\_anode, slab90\_\_\_cathode: **no core\_\_\_slab90** | the same |
| PN-slab junction drop ψ(x_j − 0.2 µm) − ψ(x_j + 0.2 µm) at 0 / 0.1 / 0.2 V (bottom edge, x_j = 4.0 µm) | 0.83450 / 0.83450 / 0.83450 V | 0.83450 / 0.83450 / 0.83450 V |
| PN-slab Potential at the junction ψ(x_j), equilibrium | −0.47002 V | −0.67054 V |
| PN-slab rib/slab Potential jump at the rib's two bottom vertices, equilibrium (`boundary_jump_v`) | 0.46 V | 0.73 V |

The PN slab's mesh is unstructured and has no row at mid-height. Its bottom edge is the only
mesh row through the junction, which lies under the rib, so both silicon regions are used there.
The PN-slab depletion width is limited by the mesh. At full mesh it rests on 2 depleted nodes,
and at mesh × 0.5 on 8. The × 0.5 value is above an ideal abrupt-junction estimate of about
0.048 µm. So the re-verification compared it at mesh × 0.5, within about one element
({ref}`plugin-history-latest-pn`).

The rows from `msh_physical_groups` on are the record's **junction probe**
({repo}`pn_junction <experiments/plugin-history/checks_v080.py#L202>`, with
{repo}`junction_probe <experiments/plugin-history/harness.py#L145>` and
{repo}`msh2_physical_names <experiments/plugin-history/harness.py#L134>`). It uses the
definitions of the fork's latest-stack probe
([`_junction`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/tests/test_mesh.py#L248)): x_j is the metallurgical
junction on the bottom edge, ψ(x_j ∓ 0.2 µm) are the neutral n and p sides inside the rib, and
the jump is the larger Potential difference between the `core` and `slab90` nodes at the rib's
two bottom vertices. Each record also holds the Potential range of each silicon region at every
step (`potential_range_by_region`).

(plugin-history-junction)=

**The bias does not reach the junction, because the rib floats.** This was the record's
leading hypothesis, and the junction probe confirms it:
- **The mesh has no `core___slab90` group.** v0.8.0's mesher never tagged the boundary between
  the rib (`core`), which holds the whole pn junction, and the slab (`slab90`). So the DEVSIM
  device has no interface there, and the rib is a region with no path to either contact. The
  contacts are on the slab, so the bias moves the slab and the contact potentials only.
- **The junction drop never changes with bias.** It stays at 0.83450 V, the Boltzmann built-in
  potential V_t ln(N_A N_D / n_i²) = 0.834503 V of the rib's own 1e17 / 1e17 cm⁻³ junction
  (DEVSIM's `simple_physics` constants, 300 K).
- **The Potential is discontinuous at the rib's bottom vertices**, by 0.46 V at equilibrium (0.73 V at
  mesh × 0.5). The jump grows by the applied bias, because only the slab moves.
- **The rib's absolute Potential depends on the mesh** (ψ(x_j) is −0.47002 V at full mesh and
  −0.67054 V at × 0.5), because nothing fixes it. This explains the non-physical Potential
  span: it is the anode contact potential (+0.4793 V, the slab's maximum) minus the floating
  rib's minimum, 0.4793 + 0.8820 = 1.3613 V and 0.4793 + 1.1474 = 1.6267 V
  ({test}`tests/test_plugin_history.py::test_committed_v080_junction_probe`).

The anode − cathode contact potential still falls by exactly the 0.1 V step each time. At
equilibrium it matches the ideal built-in potential of the ±1.1e18 cm⁻³ contacts (≈ 0.957 V),
because it is set by the ohmic contact doping alone.

Why the old mesher dropped the boundary is plausible but not proven. v0.8.0's mesher tags an
interface only for line segments that two polygons share exactly, and the trapezoidal rib
(10° sidewall) and the slab cut evidently share none.

**All recorded currents are below the solver's current floor.**
- **PN slab:** below 1e-26 A/cm. The anode current is the same at both biases, and at half mesh
  size the cathode current changes sign.
- **PIN waveguide:** about 1e-15 A/cm, and nonzero at 0 V. Left + right is not 0 at either bias.

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

**It is not part of the GitHub-hosted cross-check** ({ref}`cross-host-determinism`). That
check covers only {repo}`results/spice`. The 2023 stack has {{ numpy }} 1.26 with its own
{term}`SIMD dispatch` and no cross-host bit-identity guarantee, so the record is reproducible on
one host only.

(plugin-history-latest)=

## Re-verified on latest

The plugin is fixed in {{ gplugins_fork }} and runs on the latest stack:
{{ DEVSIM }} 2.11.1, {{ meshwell }} 2.5.2, {{ gmsh }} 4.15.2, {{ gdsfactory }} 9.51.0 and
{{ Python }} 3.13, in the {term}`TCAD` image ({repo}`docker/TCAD_IMAGE`). gf180-tcad pins the
fork at [`400f842`](https://github.com/mithro/gplugins/commit/400f8423d7b0d1aac48eea1c0145342d0c1f766a) through the
{repo}`third_party/gplugins <.gitmodules>` submodule. All file links below are at that commit.

**Where the numbers come from.** Every latest-stack value in this section is one that the
linked fork tests assert or record. They ran in the fork's own CI, in the TCAD image, at the
pinned `400f842`, and their values are quoted here from those runs. This repository does not
measure them:
- its own tests check only that the submodule is pinned on the fork's main and that
  `import gplugins` resolves to the submodule in the TCAD image
  ({test}`tests/test_submodule.py::test_submodule_pinned_on_fork_main`,
  {test}`tests/test_submodule.py::test_plugin_imports_from_submodule`);
- its sandbox rebuild ({ref}`plugin-history-reproducibility`) recomputes only the v0.8.0 side,
  {repo}`results/plugin-history/v0.8.0.json` and {repo}`results/plugin-history/v0.8.0-mesh0p5.json`.

| Fork PR | What it changes | Merge commit |
|---|---|---|
| [mithro/gplugins#2](https://github.com/mithro/gplugins/pull/2) | `import gplugins.devsim` on the latest stack (lazy {{ tidy3d }} and pyvista imports, the pydantic `Extra` removal, the `get_refined_mesh` `NameError`, `delete_device`, silicon models only on regions with NetDoping) and a CI check in the TCAD image | [`4b0a07a`](https://github.com/mithro/gplugins/commit/4b0a07a78b5a282bb15cee230dc906aa17ee2529) |
| [mithro/gplugins#4](https://github.com/mithro/gplugins/pull/4) | [`create_2Duz_simulation`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/get_simulation.py#L41) meshes again, with meshwell 2.5 ([`mesh_xsection`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/meshing.py#L104), single-threaded, fixed seed, MSH 2.2); physical names from meshio's `field_data`, without which no interface was added | [`ddbf280`](https://github.com/mithro/gplugins/commit/ddbf280e001f83439bb67756544c0a5ad1a63528) |
| [mithro/gplugins#3](https://github.com/mithro/gplugins/pull/3) | analytic doping profiles ([`doping.py`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/doping.py)) | [`b519c87`](https://github.com/mithro/gplugins/commit/b519c87e79882baa71fb89bb77c2956b9ff56257) |
| [mithro/gplugins#5](https://github.com/mithro/gplugins/pull/5) | typed contacts, materials from cited constants and the 1D stack builder ([`stack1d.py`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/stack1d.py)) | [`400f842`](https://github.com/mithro/gplugins/commit/400f8423d7b0d1aac48eea1c0145342d0c1f766a) |

The PRs #2 and #4 are the port that this section re-verifies. #3 and #5 extend the plugin for
the MOS capacitors and do not change the paths below.

(plugin-history-latest-pin)=

### PIN waveguide: bit-identical

The PIN waveguide uses DEVSIM's own tensor mesh, so the port changes only its imports. On the
latest stack its depletion widths are **bit-identical** to v0.8.0's
([`test_pin_depletion_width_match_v080`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/test_devsim.py#L134)):

| Quantity | v0.8.0 (devsim 2.6.3, Python 3.11) | latest (devsim 2.11.1, Python 3.13) | difference |
|---|---|---|---|
| depletion width at 0 V | 0.06898074973467581 µm | 0.06898074973467581 µm | 0 |
| depletion width at −1 V | 0.13782918124914934 µm | 0.13782918124914934 µm | 0 |
| cut row y, depleted nodes at 0 / −1 V | 0.11027488009949704 µm, 51 / 82 | the same | 0 |

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

| Anchor | v0.8.0, × 1 / × 0.5 | latest, × 1 / × 0.5 | allowed difference | result |
|---|---|---|---|---|
| regions → material | Aluminum: anode, cathode; si: slab90, core | the same | exact | match |
| DEVSIM regions / contacts | anode, cathode, core, slab90 / anode, cathode | the same | exact | match |
| interfaces | slab90\_\_\_anode, slab90\_\_\_cathode | the same **plus core\_\_\_slab90** | exact | the fix, see below |
| anode − cathode at 0 V | 0.9586540658880733 / …742 V | within 8.9e-16 V of v0.8.0 (port self-difference 0) | 8.9e-16 V (4 {term}`ulp` of 1 V) | match |
| anode − cathode at 0.1 / 0.2 V | 0.85865 / 0.75865 V | the same, within the allowed difference | 8.9e-16 V | match |
| step per 0.1 V of bias | 0.1 V | 0.1 V | the same + 2 ulp | match |
| NetDoping range | ±1.1e18 cm⁻³ | ±1.1e18 cm⁻³ | exact | match |
| depletion width (bottom edge), compared at × 0.5 | 0.03863 / 0.06883 µm | 0.06000 / 0.06000 µm | 0.0302 µm (v0.8.0's self-difference); Δ = 0.0088 µm | match |
| the same, against the depletion approximation (0.06664 µm) | – | 0.06000 µm at × 0.5 | one bottom-edge node spacing, 0.0100 µm; Δ = 0.0066 µm | match |
| node count (reported, not asserted) | 3523 / 11326 | 3384 / 10424 | – | – |

The anode − cathode potential is a boundary-condition check, not a mesh check: it is the
ohmic-contact difference 2 V_t ln(1.1e18 / n_i), set by the contact doping alone, which is why
both self-differences are at the ulp level. The depletion width is a difference of two node
positions, so it is quantised to the node spacing; the port's × 1 = × 0.5 equality is a
coincidence of that.

(plugin-history-latest-junction)=

### PN slab: the bias now reaches the junction

The port meshes the rib/slab boundary, so its device has the `core___slab90` interface, and
the plugin adds it like every other `a___b` group of the mesh
([`get_simulation.py`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/get_simulation.py#L189)). This is the cause of
v0.8.0's "bias does not reach the junction" ({ref}`the junction probe <plugin-history-junction>`), now fixed. It is
an extra interface compared with v0.8.0, kept deliberately: dropping it would mean adding code
to reproduce a defect of the old mesher.

[`test_pn_slab_currents_explained`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/tests/test_mesh.py#L462) solves
the same mesh both ways on the latest stack (mesh × 1):

| Device | V_cathode | junction drop | rib/slab jump | I_anode / I_cathode |
|---|---|---|---|---|
| v0.8.0 topology (`core___slab90` left out of DEVSIM) | 0 / 0.1 / 0.2 V | 0.834504 V at every step | 0.118 V | below 1e-26 A/cm |
| as ported (every interface) | 0 V | 0.834504 V | 0 | below 1e-26 A/cm |
| | 0.1 V | 0.734504 V | 0 | −9.749e-15 / 9.749e-15 A/cm |
| | 0.2 V | 0.634504 V | 0 | −1.005e-13 / 1.005e-13 A/cm |

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
  ideality n = 0.1 V / (V_t ln(I2 / I1 − 1)) is **1.73**, within the [1, 2] the test asserts.

The v0.8.0 side of this comparison is the junction probe of the record
({ref}`plugin-history-numbers`), which {py:func}`python -m gf180tcad.history --version v0.8.0
<gf180tcad.history.main>` recomputes on the 2023 stack. The docstring of
[`test_pn_slab_currents_explained`](https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/gplugins/devsim/tests/test_mesh.py#L462) still
cites those numbers as measured ad hoc. Their committed source is
{repo}`experiments/plugin-history/checks_v080.py`, and the values are in
{repo}`results/plugin-history/v0.8.0.json` and {repo}`results/plugin-history/v0.8.0-mesh0p5.json`.
