<!-- SPDX-License-Identifier: Apache-2.0 -->
# Plugin history: the gplugins DEVSIM plugin once worked

This directory holds the inputs of a re-runnable record. The record shows that the
[gdsfactory gplugins](https://github.com/gdsfactory/gplugins) DEVSIM plugin worked at
gplugins [v0.8.0](https://github.com/mithro/gplugins/tree/v0.8.0) on its Sept-2023 stack, and
that its import is broken at [v1.4.2](https://github.com/mithro/gplugins/tree/v1.4.2). The
gplugins sources come from the tags of [our fork](https://github.com/mithro/gplugins), the
[`third_party/gplugins`](../../.gitmodules) submodule. The record itself is in
[`results/plugin-history/`](../../results/plugin-history), and the write-up is
[`docs/limitations/plugin-history.md`](../../docs/limitations/plugin-history.md).

| File | What it is |
|---|---|
| [`checks_v080.py`](checks_v080.py) | The check driver for v0.8.0. It runs in the v0.8.0 venv inside the sandbox. |
| [`checks_v142.py`](checks_v142.py) | The check driver for v1.4.2. It runs only the `import` check. |
| [`harness.py`](harness.py) | Helpers shared by both drivers (standard library only): check recording, versions, currents, contact potentials and depletion width. |
| [`v080.in`](v080.in) | The input of `v080.lock`. |
| [`v080.lock`](v080.lock) | The resolved, hashed v0.8.0 package set. It keeps the record re-runnable after PyPI yanks. |

The tests are [`tests/test_plugin_history.py`](../../tests/test_plugin_history.py).

## Rebuild a record

```sh
uv run --locked python -m gf180tcad.history --version v0.8.0 --out results/plugin-history
uv run --locked python -m gf180tcad.history --version v0.8.0 --mesh-scale 0.5 --out results/plugin-history
uv run --locked python -m gf180tcad.history --version v1.4.2 --out results/plugin-history
make manifest
```

[uv](https://docs.astral.sh/uv/) runs the host side. Measured on this project's host with a
fresh workdir, install included, the runs take about:
- 76 s for v0.8.0;
- 85 s for v0.8.0 at mesh × 0.5;
- 34 s for v1.4.2.

`--workdir DIR` keeps the scratch directory and its download caches. The default is a new
temporary directory, which is removed on success. The sandbox refuses a workdir inside the repo,
its git directories or `$HOME`.

The steps are in the docstring of
[`src/gf180tcad/history/__init__.py`](../../src/gf180tcad/history/__init__.py):
1. sources from [`git archive`](https://git-scm.com/docs/git-archive) of the tag;
2. an install step with network;
3. a check run with no network and the `PDK` environment variable unset.

Everything runs in the base image ([`docker/IMAGE`](../../docker/IMAGE)).

To rebuild the records and compare them with the committed ones, run the sandbox tests with
[pytest](https://docs.pytest.org/):

```sh
uv run --locked pytest -m sandbox tests/test_plugin_history.py
```

### The checks

| Check | Code it runs |
|---|---|
| `import` | `import gplugins.devsim` |
| `pin_test` | [`PINWaveguide`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L101)`(core_width=500 nm, core_thickness=220 nm, slab_thickness=90 nm).ddsolver()`, from [`test_pin_waveguide`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/test_devsim.py#L4-L31) |
| `ramp` | [`ramp_voltage`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_simulation_xsection.py#L420) of the PIN `left` contact to 0 and then −1 V. **Added:** [`ramp_voltage`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L243-L245) of the PN slab on its default contact `cathode`, to 0.1 and then 0.2 V. |
| `ddcomponent_mesh` | [`DDComponent`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L43)`(...)` of the [`get_solver.py` `__main__` block](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L412-L524) (the trimmed `straight_pn`) |
| `ddsolver` | `c.ddsolver()` on that PN slab |
| `refine` | `c.get_refined_mesh(...)`, exactly as in the block |
| `refined_solve` | The block's second solve on the refined mesh. It is always recorded as not run, because it needs the result of `refine`. |

**The `__main__` block solves only at equilibrium.** It never calls `ramp_voltage`. The PN-slab
ramp, and the quantities recorded around it, are additions of this record. They are:
- the NetDoping range;
- the built-in potential;
- the depletion width on the bottom-edge mesh row;
- the anode and cathode contact-node potentials at each step;
- the silicon Potential span at each step.

The other changes from the v0.8.0 code:
- **PIN before PN.** The PIN waveguide is solved, ramped and deleted before the PN slab is
  built. DEVSIM solves every device it holds at the same time, and `DDComponent` switches on
  extended precision globally, so this order gives each block the solver state it would have on
  its own.
- **Dropped from `test_pin_waveguide`.** The test ramps to −5 V and then solves the optical modes
  with tidy3d. Neither step is part of the record.
- **Generic PDK activated first.** The block needs an active PDK.
- **Layer map.** It is `gdsfactory.generic_tech.LAYER`. gdsfactory 7.6.1 has no `gf.tech`
  module, so the block's [`gf.tech.LayerMap()`](https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/gplugins/devsim/get_solver.py#L425) raises
  `AttributeError`.

`--mesh-scale R` multiplies every value in the PN slab's `resolutions` dict by R, both
`resolution` and `distance`. The PIN waveguide uses DEVSIM's own tensor mesh and ignores R.

### How `v080.lock` was made

The lock was compiled once, with uv 0.13.1 from [`docker/tcad/build-requirements.lock`](../../docker/tcad/build-requirements.lock), in the
sandbox with network. The directory held `v080.in` and the `git archive` of v0.8.0 as
`./gplugins`. The command is in the lock's header:

```sh
uv pip compile --python-version 3.11.17 --python-platform x86_64-manylinux_2_28 \
  --generate-hashes --no-emit-package gplugins \
  --exclude-newer 2023-09-20T18:00:00Z --exclude-newer-package klayout=2024-04-01T00:00:00Z \
  v080.in -o v080.lock
```

- **[`--exclude-newer`](https://docs.astral.sh/uv/reference/cli/#uv-pip-compile--exclude-newer)** is the v0.8.0 release time.
- **`--exclude-newer-package`** exempts klayout, because the last 0.28 wheels were uploaded in
  2024.
- **gplugins is left out of the lock.** Its source comes from the tag, and a `.pth` file puts
  it on `sys.path`, so nothing unhashed is installed.
- **The input also asks for `setuptools` and `wheel`.** Pinned to 2023, they are the hashed build
  constraints for the three sdist-only packages: antlr4-python3-runtime, flatdict and rectpack.
  flatdict 4.0.1 needs `pkg_resources`, which today's setuptools no longer has.

The v1.4.2 record needs no lock of its own. It uses `uv sync --frozen` with the `uv.lock` of the
tag.
