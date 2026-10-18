(plugin-history)=

# The gplugins DEVSIM plugin: it once worked

{term}`Phase 2` builds its {term}`TCAD` on the {{ DEVSIM }} plugin of {{ gplugins }}, the
{{ gdsfactory }} plugin collection. The plugin is broken on every recent gplugins release. The
project fixes it in {{ gplugins_fork }} rather than writing a new one, and old versions are used
only to prove that it once worked. This page is that proof. It is a committed record that
anyone can re-run: gplugins v0.8.0 on its own Sept-2023 stack, and the point where the plugin
broke, at v1.4.2.

(plugin-history-timeline)=

## History of the plugin

All commits are linked in {{ gplugins_fork }}, which carries the upstream history unchanged.

- **Added**:
  [`a019e5a`](https://github.com/mithro/gplugins/commit/a019e5a8302858b38afde78740d3020b211248ad)
  ("add simulation", 2023-08-01), first released in v0.0.2. It contains a
  {term}`drift-diffusion` solver on a component cross-section, `DDComponent`, meshed with
  {{ gmsh }}, and a PIN waveguide, `PINWaveguide`, on a {{ DEVSIM }} tensor mesh.
- **Last working release: v0.8.0** ([`6245740`](https://github.com/mithro/gplugins/commit/624574ced6d9407306878c9fd00bede825640d94),
  2023-09-20 17:57 UTC).
- **Import broken**:
  [`0ce7b30`](https://github.com/mithro/gplugins/commit/0ce7b30b81f128f81bc9b0b914700d84c2b4ed94)
  ("Consolidate gmsh plugin (#159)", 2023-09-20), first released in v0.8.1. It removed
  `fuse_polygons` from `gplugins.gmsh`, which
  [`gplugins/devsim/get_simulation.py`](https://github.com/mithro/gplugins/blob/f47ed3de80b99bafc960955b3d6925e947d4fc0f/gplugins/devsim/get_simulation.py#L23-L27)
  still imports. From then on `import gplugins.devsim` fails, and v1.4.2 still fails the same
  way.
- **Mesher removed**:
  [`017cede`](https://github.com/mithro/gplugins/commit/017cede91e322426144bd1cb5dc8ede78b830878)
  (2025-11-09), first released in v2.0.0, moved `gplugins.gmsh` to the new {{ meshwell }} API.
  `create_2Duz_simulation`, the mesher behind `DDComponent`, now raises `NotImplementedError`
  ("uz_xsection_mesh has been removed").

The PIN waveguide never needed gmsh. The path that broke is `DDComponent` with the mesher,
so the record below covers that path.

(plugin-history-record)=

## The record

`python -m gf180tcad.history` ({py:mod}`gf180tcad.history`) rebuilds one record, a JSON file
in {repo}`results/plugin-history`. It has three steps, each in the base image
({repo}`docker/IMAGE`), and the last two in the {term}`sandbox`:

1. The gplugins sources are taken from the fork's tag with `git archive` (host).
2. The packages are installed, with network. For v0.8.0 this is CPython 3.11.17 and the hashed,
   resolved set {repo}`experiments/plugin-history/v080.lock`. The lock was compiled once with
   {{ uv }}, with `--exclude-newer` set to the v0.8.0 release time, so it holds devsim 2.6.3,
   gdsfactory 7.6.1, meshwell 1.0.1 and gmsh 4.11.1. For v1.4.2 it is `uv sync --frozen` from
   the tag's own uv lock file, with the base image's {{ Python }} 3.12.
3. The fixed checks run, with no network and no {term}`PDK` preselected (the `PDK` environment
   variable is unset). They are
   {repo}`experiments/plugin-history/checks_v080.py` and
   {repo}`experiments/plugin-history/checks_v142.py`.

The commands and the lock recipe are in {repo}`experiments/plugin-history/README.md`.

The checks are two blocks of the v0.8.0 source turned into named checks, with only the result
recording added:

- **PIN waveguide.** The body of
  [`test_pin_waveguide`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/test_devsim.py#L4-L31):
  `PINWaveguide` (500 nm × 220 nm core, 90 nm slab), `ddsolver()`, then `ramp_voltage`.
- **PN slab.** The `__main__` block of
  [`get_solver.py`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L412-L524):
  a trimmed `straight_pn` as a `DDComponent`.

| Check | What runs |
|---|---|
| `import` | `import gplugins.devsim` |
| `pin_test` | the PIN waveguide build and `ddsolver()` |
| `ramp` | `ramp_voltage`: the PIN waveguide to 0 and −1 V, the PN slab cathode to 0.1 and 0.2 V |
| `ddcomponent_mesh` | the PN slab `DDComponent(...)` |
| `ddsolver` | `ddsolver()` on the PN slab (meshing with gmsh, then solving) |
| `refine` | `get_refined_mesh(...)` on the PN slab, as in the block |

(plugin-history-results)=

## Results

| Check | v0.8.0 | v0.8.0, PN mesh × 0.5 | v1.4.2 |
|---|---|---|---|
| `import` | pass | pass | **fail**: `ImportError` naming `fuse_polygons` |
| `pin_test` | pass | pass | not run |
| `ramp` | pass | pass | not run |
| `ddcomponent_mesh` | pass | pass | not run |
| `ddsolver` | pass | pass | not run |
| `refine` | **fail**: `NameError` | **fail**: `NameError` | not run |

The records are {repo}`results/plugin-history/v0.8.0.json`,
{repo}`results/plugin-history/v0.8.0-mesh0p5.json` and
{repo}`results/plugin-history/v1.4.2.json`. Each one gives the resolved package versions and the
exact exception type, message and source line of every failed check.

- **v0.8.0 worked.** The PIN waveguide and the PN slab both mesh, solve and ramp. The
  depletion width of the PIN junction is measured on the mesh row nearest the rib's vertical
  centre, as the span of the nodes where both n and p are below 1e-2 |NetDoping|. It is
  0.069 µm at 0 V and 0.138 µm at −1 V. The PN slab has 3523 mesh nodes (the sum over its
  four DEVSIM regions).
- **`get_refined_mesh` was already broken at v0.8.0.** Its body uses `c`, the variable of the
  `__main__` block, instead of `self`
  ([`get_solver.py:359`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L359)).
  Called from anywhere else, it raises `NameError: name 'c' is not defined`.
- **v1.4.2 does not import.** The error is `ImportError: cannot import name 'fuse_polygons'
  from 'gplugins.gmsh'`, raised at `gplugins/devsim/get_simulation.py:23`.
- **Mesh × 0.5.** This is `--mesh-scale 0.5`, every value of the PN slab's `resolutions`
  halved. It gives 11326 nodes, and its PIN numbers are those of the full run, because
  the PIN waveguide uses DEVSIM's own mesh. It is the starting point of the allowance for mesh error
  that the re-verification on the latest stack uses.

**The PN slab carries no current.** Its contact currents at 0.1 and 0.2 V on the cathode
(the block names the contact on the p⁺⁺ side the cathode, so this is forward bias) are below 1e-26 A/cm in magnitude, which is numerical noise. The anode current is the same at both
biases, and at half mesh size the cathode current changes sign. A forward-biased junction should
carry a measurable current. The record keeps the values as v0.8.0 computed them. The
re-verification on the latest stack has to explain them, so these currents are evidence that
the solver ran, not that its answer is right.

(plugin-history-reproducibility)=

## Reproducibility

Two local runs give byte-identical records. The record holds no timings and no host paths
({test}`tests/test_plugin_history.py::test_history_json_has_no_timings_or_paths`). The
{test}`tests/test_plugin_history.py::test_v080_once_worked` and
{test}`tests/test_plugin_history.py::test_v142_import_broken` tests re-run the record in the
sandbox (`pytest -m sandbox`) and compare it with the committed one. The record is listed in the
{term}`manifest`.

**It is not part of the GitHub-hosted cross-check** ({ref}`cross-host-determinism`). That
check covers only {repo}`results/spice`. The 2023 stack has {{ numpy }} 1.26 with its own
{term}`SIMD dispatch` and
no cross-host bit-identity guarantee, so the record is reproducible on one host only.

(plugin-history-latest)=

## Re-verified on latest

To be filled in by the port of the plugin to the latest stack (devsim 2.11, meshwell 2.5,
gdsfactory 9) in {{ gplugins_fork }}: the same PIN and PN-slab numbers, recomputed there and
compared with this record, with the allowed difference stated.
