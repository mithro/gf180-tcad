<!-- SPDX-License-Identifier: Apache-2.0 -->
# Mesh convergence at the fitted poly length bias

This directory reruns the 2D mesh-convergence study at the Lmin cells with the fitted poly length
bias, as plan Task E3, Decision 5 asks
([`docs/superpowers/plans/2026-11-16-2d-edge-poly-bias.md`](../../docs/superpowers/plans/2026-11-16-2d-edge-poly-bias.md)).
The committed study in [`results/tcad/meshconv`](../../results/tcad/meshconv) runs at the start
values with the poly as drawn. The record of this rerun is in
[`results/meshconv-fitted/`](../../results/meshconv-fitted), and the write-up is the section
"At the fitted poly length bias" of
[`docs/limitations/mesh-convergence.md`](../../docs/limitations/mesh-convergence.md).

| File | What it is |
|---|---|
| [`level.py`](level.py) | One refinement level's QS sweep, with the calibrated values and the committed fit. It runs inside the sandbox and saves each point, so a cut-off job resumes. |
| [`run.py`](run.py) | Runs levels one at a time through [`tools/sandbox-run`](../../tools/sandbox-run) (16 GiB, one CPU). It refuses uncommitted changes and writes each level's pins. |
| [`record.py`](record.py) | Writes one device's record from the level directories. |

## Rebuild a record

```sh
uv run --locked python experiments/meshconv-fitted/run.py ~/.cache/gf180-tcad/meshconv-fitted nfet_05v0 1 2 0
uv run --locked python experiments/meshconv-fitted/record.py \
    ~/.cache/gf180-tcad/meshconv-fitted nfet_05v0 results/meshconv-fitted/nfet_05v0.json
make manifest
```

and the same for `pfet_05v0`. Run one 16 GiB level at a time and nothing else beside it. The work
directory must be outside the repository, because the sandbox refuses the repository. A level
with a finished result is skipped. A level that was cut off, for example at its memory limit,
resumes at its last saved point when the same command runs again. Each level keeps its log and
its progress beside its result in the work directory.

Run [`run.py`](run.py) from a checkout that stays at one commit for the whole run. A detached
worktree does that. A level's pins hold the commit, and a run whose checkout changed is refused.
That commit must stay on `main`'s history.

A record holds the report of `gf180tcad.tcad.meshconv.converge` over the three levels. It also
holds the plan's check: the selected level's largest change against the next finer
level, and whether it is below the 1 % criterion. And it compares that level's capacitance with
the committed calibrated cell of the same geometry, on the same mesh. The study's second
criterion is the uniform stack's agreement with 1D. That stack has no gate end, so the poly
length bias does not enter it, and it is not rerun.
