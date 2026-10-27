# gf180-tcad

Open-source [TCAD](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-TCAD) for the GlobalFoundries
[GF180MCU](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-GF180MCU) process ([open PDK](https://github.com/fossi-foundation/gf180mcu-pdk)),
validated against the [PDK](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-PDK)'s own [SPICE](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-SPICE) models.

## What and why

This project builds a scriptable TCAD flow (structures from
[gdsfactory](https://gdsfactory.github.io/gdsfactory/) layouts, simulated with
[DEVSIM](https://devsim.org/), with [Charon](https://charon.sandia.gov/) planned in parallel for
cross-comparison) for
GF180MCU transistors, and measures, quantitatively, reproducibly and in public,
how closely it agrees with the PDK SPICE models.

The SPICE models are the [SPICE reference](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-SPICE-reference-results); the TCAD is the
suspect. Mismatches are documented with their probable cause rather than hidden. Only once the
TCAD has earned confidence will it be used to extend or create SPICE models.

## Status

[Phases 0 and 1](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-Phases-0-and-1) are complete: the foundations and the
SPICE reference dataset, which gives the same bytes on another computer
([check on another computer](https://gf180-tcad.readthedocs.io/en/latest/reproduce/index.html#cross-host-determinism)).
[Phase 2](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-Phase-2) (the first TCAD
work) is in progress. The first TCAD results are committed, for the 5 V
[`nfet_05v0`](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-nfet_05v0) and
[`pfet_05v0`](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-pfet_05v0) at the
uncalibrated start values:

- the 1D [MOS capacitor](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-MOSCAP)
  [C–V](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-CV) curves
  ([`results/tcad/moscap1d`](results/tcad/moscap1d)) and their
  [mesh convergence](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-mesh-convergence)
  ([`results/tcad/meshconv/moscap1d`](results/tcad/meshconv/moscap1d),
  [report](https://gf180-tcad.readthedocs.io/en/latest/limitations/mesh-convergence.html)), made on the
  [dev-HEAD TCAD image](#images);
- the 2D MOS capacitor cut from the PDK's [gdsfactory](https://gdsfactory.github.io/gdsfactory/)
  transistor cells ([`results/tcad/moscap2d`](results/tcad/moscap2d)), at the minimum gate length
  (0.60 µm nfet, 0.50 µm pfet) and at L = 2 µm, with its own mesh convergence
  ([`results/tcad/meshconv/moscap2d`](results/tcad/meshconv/moscap2d)), made on the
  [stable TCAD image](#images) for now. The L = 2 µm cell has no small-signal (AC) result, because the AC solve
  fails in the direct solver at that size, and the L = 10 µm cell is not run in 2D, because its
  equilibrium solve fails there too; see the
  [2D MOS capacitor page](https://gf180-tcad.readthedocs.io/en/latest/limitations/moscap2d.html).

The 1D MOS capacitor is calibrated against the SPICE
[Cgg](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-Cgg)–Vg
([plan](docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-12-calibrate-against-spice-cggvg),
[`results/tcad/calibration`](results/tcad/calibration),
[`results/tcad/validation`](results/tcad/validation),
[C–V calibration page](https://gf180-tcad.readthedocs.io/en/latest/comparison/cv-agreement.html)):
three tunables, 3 of the 8-parameter budget. In 1D the nfet agrees with SPICE at every geometry,
fitted and held out. The pfet is published as a disagreement: the SPICE pfet's depletion edge
moves by 0.57 V between L = 10 µm and the minimum length, which one length-independent 1D stack
cannot follow. The calibrated 1D curves are in
[`results/tcad/moscap1d`](results/tcad/moscap1d). Every committed TCAD result has generated
pages (TCAD-against-SPICE overlays, verdicts, mesh convergence), linked from the
[results page](https://gf180-tcad.readthedocs.io/en/latest/results/index.html), and
`make reproduce` includes the TCAD trees. It has not been run end to end, and its 2D files are
not expected to match yet
([Reproduce](https://gf180-tcad.readthedocs.io/en/latest/reproduce/index.html#one-command)); the
calibrated 1D [jobs](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-job) are cross-checked byte for byte on a
[GitHub-hosted runner](https://docs.github.com/en/actions/concepts/runners/github-hosted-runners)
([TCAD cross-check](https://gf180-tcad.readthedocs.io/en/latest/reproduce/index.html#cross-host-tcad)).
The 2D validation of the calibrated stack is in progress
([issue #35](https://github.com/mithro/gf180-tcad/issues/35)).

Planned, not built yet:
[DEVSIM](https://devsim.org/) and [Charon](https://charon.sandia.gov/) run in parallel on every
job and cross-compared
([Phase 4 plan](docs/superpowers/plans/2026-10-27-phase4-charon-backend.md),
[issue #44](https://github.com/mithro/gf180-tcad/issues/44); no Charon job has run yet), 3D
renders of the simulated processes
([renders plan](docs/superpowers/plans/2026-10-27-renders-pipeline.md),
[issue #43](https://github.com/mithro/gf180-tcad/issues/43)) and explainer pages on how the parts
of a semiconductor work ([issue #46](https://github.com/mithro/gf180-tcad/issues/46)).
The current limitations, including the deviations from the design spec, are listed on the
[limitations page](https://gf180-tcad.readthedocs.io/en/latest/limitations/index.html).

## Documentation

[![Documentation Status](https://readthedocs.org/projects/gf180-tcad/badge/?version=latest)](https://gf180-tcad.readthedocs.io/en/latest/)

The documentation is at [gf180-tcad.readthedocs.io](https://gf180-tcad.readthedocs.io/en/latest/). To regenerate the
SPICE reference and the TCAD results yourself, see [Reproduce](https://gf180-tcad.readthedocs.io/en/latest/reproduce/index.html); its
[cross-host determinism](https://gf180-tcad.readthedocs.io/en/latest/reproduce/index.html#cross-host-determinism) section says on which
hosts the results are byte-identical.

## Images

Every simulation runs in one of three reproducible images on the
[GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry),
each pinned by
[manifest digest](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-manifest-digest)
in a one-line file and built by
[`.github/workflows/image.yml`](.github/workflows/image.yml), which checks that a from-scratch
rebuild gives the same digests:

| Image | Pin file | Role |
|---|---|---|
| [`ghcr.io/mithro/gf180-tcad-base`](https://github.com/mithro/gf180-tcad/pkgs/container/gf180-tcad-base) | [`docker/IMAGE`](docker/IMAGE) | the SPICE reference |
| [`ghcr.io/mithro/gf180-tcad-tcad`](https://github.com/mithro/gf180-tcad/pkgs/container/gf180-tcad-tcad) | [`docker/TCAD_IMAGE`](docker/TCAD_IMAGE) | the [stable TCAD image](https://gf180-tcad.readthedocs.io/en/latest/reproduce/image.html#tcad-image) |
| [`ghcr.io/mithro/gf180-tcad-tcad-dev`](https://github.com/mithro/gf180-tcad/pkgs/container/gf180-tcad-tcad-dev) | [`docker/TCAD_DEV_IMAGE`](docker/TCAD_DEV_IMAGE) | the [dev-HEAD TCAD image](https://gf180-tcad.readthedocs.io/en/latest/reproduce/image.html#tcad-dev-image) |

What each holds:

- **base**: [IIC-OSIC-TOOLS](https://hub.docker.com/r/hpretl/iic-osic-tools) with the PDK,
  [ngspice](https://ngspice.sourceforge.io/) and [Xyce](https://xyce.sandia.gov/).
- **stable TCAD**: the TCAD stack at its latest releases.
- **dev-HEAD TCAD**: the TCAD stack at development HEAD (the newest commit), pinned by commit,
  with DEVSIM built from source.

The exact versions in each image are in its `versions.json`
([base](docker/base/versions.json), [stable](docker/tcad/versions.json),
[dev HEAD](docker/tcad-dev/versions.json)). The final results are to come from the dev-HEAD
image; the stable one is kept for checking how the released versions behave. Which results come
from which image today
is on the [image page](https://gf180-tcad.readthedocs.io/en/latest/reproduce/image.html#tcad-results-image).

## Development

Needs [uv](https://docs.astral.sh/uv/); the checks are [pytest](https://docs.pytest.org/) and
[ruff](https://docs.astral.sh/ruff/). Tests marked [`sandbox`](https://gf180-tcad.readthedocs.io/en/latest/glossary.html#term-sandbox) run simulators through
[`tools/sandbox-run`](tools/sandbox-run) and are excluded here.

```
uv sync --locked
uv run pytest -m "not sandbox"
uv run ruff check
uv run ruff format --check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution rules.

## Licence

[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0), see [LICENSE](LICENSE).
