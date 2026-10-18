<!-- SPDX-License-Identifier: Apache-2.0 -->
# Plugin history: the gplugins DEVSIM plugin once worked

This directory holds the inputs of a re-runnable record. The record shows that the
[gdsfactory gplugins](https://github.com/gdsfactory/gplugins) DEVSIM plugin worked at
gplugins v0.8.0 on its Sept-2023 stack, and that its import is broken at v1.4.2. The
gplugins sources come from the tags of [our fork](https://github.com/mithro/gplugins), the
`third_party/gplugins` submodule. The record itself is in
[`results/plugin-history/`](../../results/plugin-history), and the write-up is
[`docs/limitations/plugin-history.md`](../../docs/limitations/plugin-history.md).

| File | What it is |
|---|---|
| `checks_v080.py` | The check driver for v0.8.0. It runs in the v0.8.0 venv inside the sandbox. |
| `checks_v142.py` | The check driver for v1.4.2. It runs only the `import` check. |
| `harness.py` | Helpers shared by both drivers (standard library only): check recording, versions, currents and depletion width. |
| `v080.in` | The input of `v080.lock`. |
| `v080.lock` | The resolved, hashed v0.8.0 package set. It keeps the record re-runnable after PyPI yanks. |

## Rebuild a record

```sh
uv run --locked python -m gf180tcad.history --version v0.8.0 --out results/plugin-history
uv run --locked python -m gf180tcad.history --version v0.8.0 --mesh-scale 0.5 --out results/plugin-history
uv run --locked python -m gf180tcad.history --version v1.4.2 --out results/plugin-history
make manifest
```

Each command takes a few minutes. `--workdir DIR` keeps the scratch directory and its download
caches, so a second run is faster. The default is a new temporary directory, which is removed
on success. The sandbox refuses a workdir inside the repo, its git directories or `$HOME`.
The steps are in the docstring of `src/gf180tcad/history/__init__.py`:

1. sources from `git archive` of the tag;
2. an install step with network;
3. a check run with no network and `PDK` unset.

Everything runs in the base image (`docker/IMAGE`).

### The checks

| Check | v0.8.0 code it runs |
|---|---|
| `import` | `import gplugins.devsim` |
| `pin_test` | `PINWaveguide(core_width=500 nm, core_thickness=220 nm, slab_thickness=90 nm).ddsolver()`, from `test_pin_waveguide` |
| `ramp` | `ramp_voltage` of the PIN `left` contact to 0 and then −1 V, and of the PN slab `cathode` to 0.1 and then 0.2 V |
| `ddcomponent_mesh` | `DDComponent(...)` of the `get_solver.py` `__main__` block (the trimmed `straight_pn`) |
| `ddsolver` | `c.ddsolver()` on that PN slab |
| `refine` | `c.get_refined_mesh(...)`, exactly as in the block |

The PIN waveguide is solved, ramped and deleted before the PN slab is built. DEVSIM solves
every device it holds at the same time, and `DDComponent` switches on extended precision
globally, so this order gives each block the solver state it would have on its own.

`test_pin_waveguide` itself goes further than this record: it ramps to −5 V and then solves the
optical modes with tidy3d. Neither step is part of the record.

To run the `__main__` block outside a notebook, two changes are needed. The generic PDK is
activated first. The layer map is `gdsfactory.generic_tech.LAYER`, in place of the block's
`gf.tech.LayerMap()`.

`--mesh-scale R` multiplies every value in the PN slab's `resolutions` dict by R, both
`resolution` and `distance`. The PIN waveguide uses DEVSIM's own tensor mesh and ignores R.

### How `v080.lock` was made

The lock was compiled once, with uv 0.13.1 from `docker/tcad/build-requirements.lock`, in the
sandbox with network. The directory held `v080.in` and the `git archive` of v0.8.0 as
`./gplugins`. The command is in the lock's header:

```sh
uv pip compile --python-version 3.11.17 --python-platform x86_64-manylinux_2_28 \
  --generate-hashes --no-emit-package gplugins \
  --exclude-newer 2023-09-20T18:00:00Z --exclude-newer-package klayout=2024-04-01T00:00:00Z \
  v080.in -o v080.lock
```

- **`--exclude-newer`** is the v0.8.0 release time.
- **`--exclude-newer-package`** exempts klayout, because the last 0.28 wheels were uploaded in
  2024.
- **gplugins is left out of the lock.** Its source comes from the tag, and a `.pth` file puts
  it on `sys.path`, so nothing unhashed is installed.
- **The input also asks for `setuptools` and `wheel`.** Pinned to 2023, they are the hashed build
  constraints for the three sdist-only packages: antlr4-python3-runtime, flatdict and rectpack.
  flatdict 4.0.1 needs `pkg_resources`, which today's setuptools no longer has.

The v1.4.2 record needs no lock of its own. It uses `uv sync --frozen` with the `uv.lock` of the
tag.
