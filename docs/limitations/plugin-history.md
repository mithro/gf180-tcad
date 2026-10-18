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
  first released in [v2.0.0](https://github.com/mithro/gplugins/tree/v2.0.0), moved `gplugins.gmsh` to the new {{ meshwell }} API. [`create_2Duz_simulation`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation.py#L32),
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
| {repo}`import <experiments/plugin-history/checks_v080.py#L288>` | [`import gplugins.devsim`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/__init__.py) |
| {repo}`pin_test <experiments/plugin-history/checks_v080.py#L55>` | the PIN waveguide build and [`ddsolver()`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L385) |
| {repo}`ramp <experiments/plugin-history/checks_v080.py#L95>` | [`ramp_voltage`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L420) of the PIN waveguide to 0 and −1 V, and (added) of the PN-slab cathode to 0.1 and 0.2 V |
| {repo}`ddcomponent_mesh <experiments/plugin-history/checks_v080.py#L180>` | the PN-slab `DDComponent(...)` |
| {repo}`ddsolver <experiments/plugin-history/checks_v080.py#L288>` | [`ddsolver()`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L204) on the PN slab (meshing with gmsh, then solving) |
| {repo}`refine <experiments/plugin-history/checks_v080.py#L269>` | [`get_refined_mesh`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L328) on the PN slab, as in the block |
| {repo}`refined_solve <experiments/plugin-history/checks_v080.py#L288>` | the block's last step, a second `DDComponent` solved with `global_meshsize_array`; recorded as not run, because it needs the output of `refine` |

(plugin-history-changes)=

### Changes from the v0.8.0 code

- **Generic PDK activated first.** `get_layer_stack()` in the block needs an active PDK.
- **Layer map.** gdsfactory 7.6.1 has no `gf.tech` module, so the block's
  [`gf.tech.LayerMap()`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L425) raises `AttributeError`. The
  driver uses the generic layer map `gdsfactory.generic_tech.LAYER`.
- **PIN before PN.** The PIN waveguide is solved, ramped and deleted before the PN slab is
  built. DEVSIM solves every device it holds at once, and `DDComponent` turns on extended
  precision globally, so this order gives each block the solver state it has on its own.
- **Dropped from [`test_pin_waveguide`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/test_devsim.py#L4-L31).** Its −5 V ramp and its tidy3d mode solves
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
| PN-slab NetDoping range | -1.1e+18 … 1.1e+18 cm⁻³ | -1.1e+18 … 1.1e+18 cm⁻³ |
| PN-slab built-in potential (max − min Potential over the silicon) | 1.3613 V | 1.6267 V |
| PN-slab depletion width at equilibrium (bottom edge, y = 0) | 0.0386 µm | 0.0688 µm |
| PN-slab mesh nodes (sum over its four DEVSIM regions) | 3523 | 11326 |
| PN-slab anode − cathode contact potential at 0 / 0.1 / 0.2 V | 0.9587 / 0.8587 / 0.7587 V | 0.9587 / 0.8587 / 0.7587 V |
| PN-slab Potential span over the silicon at 0 / 0.1 / 0.2 V | 1.3613 / 1.3613 / 1.3613 V | 1.6267 / 1.6267 / 1.6267 V |

The PN slab's mesh is unstructured and has no row at mid-height. Its bottom edge is the only
mesh row through the junction, which lies under the rib, so both silicon regions are used there.

**The applied bias reaches the contacts but not the junction.** The anode − cathode contact
potential falls by exactly the 0.1 V step each time. The Potential span over the silicon, which
should fall by the forward bias, does not change.
It is also larger than the equilibrium contact potential difference (the ideal built-in
potential between the ±1.1e18 cm⁻³ contacts), and it changes with the mesh, both signs of a
non-physical potential somewhere in the silicon.

**All recorded currents are below the solver's current floor.**
- **PN slab:** below 1e-26 A/cm. The anode current is the same at both biases, and at half mesh
  size the cathode current changes sign.
- **PIN waveguide:** about 1e-15 A/cm, and nonzero at 0 V. Left + right is not 0 at either bias.

The record keeps these values as v0.8.0 computed them. They are evidence that the solver ran,
not that its answer is right.

**What the re-verification compares.** The port to the latest stack
({ref}`plugin-history-latest`) compares these quantities:
- the depletion widths;
- the built-in potential and NetDoping range;
- the region, contact and interface names;
- the node counts;
- whether the applied bias reaches the device.

It must explain the currents; it does not have to match them.

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

To be filled in by the port of the plugin to the latest stack (devsim 2.11, meshwell 2.5,
gdsfactory 9) in {{ gplugins_fork }}. It recomputes the quantities above there, compares them
with this record and states the allowed difference.
