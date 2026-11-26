<!-- SPDX-License-Identifier: Apache-2.0 -->
# Charon backend experiments B1 to B7

<!-- figure-ok: GitHub renders this README without the docs build; the strip and the 2D mesh are drawn on the linked Charon page -->

This directory runs experiments B1 to B7 of the
[Charon plan, Task B](../../docs/superpowers/plans/2026-10-27-phase4-charon-backend.md#task-b-backendscharon-behind-the-task-15-seam).
Each one runs the 1D MOS capacitor (and, for B1, a small 2D mesh) in the pinned
[Charon image](../../docker/CHARON_IMAGE) through [`tools/sandbox-run`](../../tools/sandbox-run).
The records are in [`results/charon-experiments/`](../../results/charon-experiments), and the
write-up is [`docs/limitations/charon.md`](../../docs/limitations/charon.md), whose figures draw
the strip and the 2D mesh.

| File | What it is |
|---|---|
| [`run.py`](run.py) | Runs the steps one at a time (2 GiB, one CPU, no network). It refuses uncommitted changes and writes each step's pins. |
| [`record.py`](record.py) | Writes the four records from the run directories. |
| [`cx.py`](cx.py) | The Exodus II writer, the strip mesh, the runner and the readers. |
| [`decks.py`](decks.py) | The interpreter decks of the MOS capacitor. |
| [`opts.py`](opts.py) | The solver tolerances and the KLU2 lines, from the environment. |
| [`b1.py`](b1.py), [`b1an.py`](b1an.py) | B1: TRI3 blocks on the strip and on a 2D mesh. |
| [`b2.py`](b2.py), [`b2an.py`](b2an.py) | B2, B6, B7: the C-V sweeps and their checks. |
| [`b2h.py`](b2h.py) | B2: the solver variants through the onset of inversion. |
| [`b2d.py`](b2d.py) | B2: solves started on the inversion side. |
| [`b2nlp.py`](b2nlp.py) | B2: the nonlinear-Poisson solve with a biased poly gate. |
| [`b3.py`](b3.py) | B3: Belos against Amesos2 KLU2. |
| [`b4.py`](b4.py) | B4: the harmonic-balance current columns on the poly-gate stack. |
| [`b4pp.py`](b4pp.py), [`b4mg.py`](b4mg.py) | B4: the same columns on an oxide-only parallel plate and on a metal-gate MOS capacitor. |
| [`b5.py`](b5.py) | B5: the nodal doping and the intrinsic density. |
| [`b7n.py`](b7n.py) | The Newton iterations of each failed solve, repeated with the linear system written ([issue #223](https://github.com/mithro/gf180-tcad/issues/223)). |
| [`traps.py`](traps.py) | The two decks that break the deck rules ([issue #224](https://github.com/mithro/gf180-tcad/issues/224)). |
| [`diag.py`](diag.py), [`ncdump.py`](ncdump.py) | Diagnostics: one solve's profiles, a netCDF header dump. |

## Rebuild the records

```sh
uv run --locked python experiments/charon-backend/run.py ~/.cache/gf180-tcad/charon-backend all
uv run --locked python experiments/charon-backend/record.py \
    ~/.cache/gf180-tcad/charon-backend results/charon-experiments
make manifest
```

The work directory must be outside the repository, because the sandbox refuses the repository.

A step whose [`done.json`](run.py) exists is skipped, so a cut-off run resumes. The records carry
the pins of the run. [`record.py`](record.py) only reads the run directories, so a later fix to it
rewrites the records from the same runs; the records carry its sha256 apart. Each step writes its
complete output to [`<workdir>/<step>/run.log`](run.py). The whole set takes about four and a half hours on this
project's host, one 2 GiB container at a time.
