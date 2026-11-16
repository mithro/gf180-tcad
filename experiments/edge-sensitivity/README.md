<!-- SPDX-License-Identifier: Apache-2.0 -->
# Edge sensitivity: what the 2D cross-section needs for the card's edge capacitance

This directory re-runs the study of
[issue #189](https://github.com/mithro/gf180-tcad/issues/189). Each run changes one feature of a
committed calibrated 2D MOS capacitor cell's cross-section. It solves the cell QS at its two
plateaus, u = −5 V and +5 V. The records are in
[`results/edge-sensitivity/`](../../results/edge-sensitivity), and the write-up is the section
"What the 2D edge needs" of [`docs/limitations/moscap2d.md`](../../docs/limitations/moscap2d.md).

| File | What it is |
|---|---|
| [`variant.py`](variant.py) | One variant's cross-section and QS solve. It runs inside the sandbox. Its docstring lists the variant names. |
| [`run.py`](run.py) | Runs variants one at a time through [`tools/sandbox-run`](../../tools/sandbox-run) (16 GiB, one CPU). It refuses uncommitted changes and writes each run's pins. |
| [`record.py`](record.py) | Writes one cell's record from the run directories. |

The tests are [`tests/test_edge_sensitivity.py`](../../tests/test_edge_sensitivity.py). The figure
and the least-squares poly length bias are in
[`src/gf180tcad/limitations_figures.py`](../../src/gf180tcad/limitations_figures.py).

## Rebuild a record

```sh
uv run --locked python experiments/edge-sensitivity/run.py \
    ~/.cache/gf180-tcad/edge-sens nfet_05v0 w10p0_l0p60 base plugs bias30 bias60 plugs+bias30 \
    bias65+ldd1e18+sp100 bias65+ldd5e18+sp100 \
    bias65+ldd5e18+ldddepth60+latr0.2+sp100 bias65+ldd2e19+ldddepth60+latr0.2+sp100
uv run --locked python experiments/edge-sensitivity/record.py \
    ~/.cache/gf180-tcad/edge-sens nfet_05v0 w10p0_l0p60 results/edge-sensitivity/nfet_05v0-w10p0_l0p60.json
uv run --locked python experiments/edge-sensitivity/run.py \
    ~/.cache/gf180-tcad/edge-sens pfet_05v0 w10p0_l0p50 base bias30 bias60
uv run --locked python experiments/edge-sensitivity/record.py \
    ~/.cache/gf180-tcad/edge-sens pfet_05v0 w10p0_l0p50 results/edge-sensitivity/pfet_05v0-w10p0_l0p50.json
make manifest
```

The work directory must be outside the repository, because the sandbox refuses the repository. A
variant whose `result.json` exists is skipped, so a cut-off run resumes. Each variant writes its log
to `<workdir>/<device>/<gid>/<variant>/variant.log`. On this project's host one variant takes about
50 minutes.

A record keeps, per variant, the gate biases, Cgg per unit width (fF/µm), the node count, the
meshed gate length and the variant's parameters. It also holds the pins every run shared. They are the
commit, the TCAD image and the gplugins commit. They also include the sha256 of
[`variant.py`](variant.py), the 2D writer's `generator_sha256`, and the calibration file and
values. [`record.py`](record.py) refuses runs whose pins differ.
