<!-- SPDX-License-Identifier: Apache-2.0 -->
# High-voltage junctions: breakdown voltage of well edges with edge terminations

This directory predicts the reverse breakdown voltage of gf180mcu well-to-substrate junction
edges. The structures are those of a test die of the
[evampire](https://github.com/mithro/evampire) project; [`structures.json`](structures.json) is
that project's structure list. Each structure is solved in DEVSIM on a 2D cross-section, as a
straight edge and as a round corner. The breakdown voltage is the bias at which the electron
ionisation integral along a field line reaches 1. The records are in
[`results/hv-junction/`](../../results/hv-junction), and the write-up is
[`docs/results/hv-junction.md`](../../docs/results/hv-junction.md).

| File | What it is |
|---|---|
| [`structures.json`](structures.json) | The drawn structures, exported by evampire's layout generator. |
| [`hvsite.py`](hvsite.py) | Turns one structure and one process assumption into the parameters of its cross-section. It holds the doping family. |
| [`predict.py`](predict.py) | Writes the case sets `main`, `family`, `rest` and `p5`. |
| [`cases.py`](cases.py) | The bare-edge and calibration sections that the check cases build on. |
| [`checks.py`](checks.py) | Writes the check cases, runs the 1D diodes and writes the diode record. |
| [`structure.py`](structure.py), [`dd.py`](dd.py) | The DEVSIM mesh, doping and drift-diffusion set-up. They run inside the sandbox. |
| [`sweep.py`](sweep.py) | The reverse sweep of one case. It runs inside the sandbox. |
| [`fieldline.py`](fieldline.py), [`ionize.py`](ionize.py) | The field-line trace and the ionisation integral (numpy and scipy only). |
| [`profile1d.py`](profile1d.py) | Sheet resistance and capacitance of a well profile, for the doping anchors. |
| [`diode1d.py`](diode1d.py) | Three abrupt 1D diodes. It runs inside the sandbox. |
| [`verify.py`](verify.py) | Reruns recorded cases and compares them with the records. |
| [`run.py`](run.py) | Runs one script through [`tools/sandbox-run`](../../tools/sandbox-run) (8 GiB, one CPU) and gives a run's pins. |
| [`batch.py`](batch.py) | Runs a case set, one container per case, and writes each case's pins. |
| [`record.py`](record.py) | Writes a record from a batch's run directories. |
| [`charon_mesh.py`](charon_mesh.py), [`charon_deck.py`](charon_deck.py), [`charon_run.py`](charon_run.py), [`charon_field.py`](charon_field.py) | The Charon cross-check: DEVSIM's nodes as an Exodus mesh, the decks, the sweep and its post-processing. |
| [`charon_batch.py`](charon_batch.py), [`charon_record.py`](charon_record.py) | Run named cases on Charon, and write their record. |
| [`charon_defaults.py`](charon_defaults.py), [`charon_diode_ref.py`](charon_diode_ref.py) | Development checks of the Charon set-up. No record holds their results. |
| [`fit.py`](fit.py) | Development script (scipy on the host) that fitted the deep parts of the doping family to the published capacitance models, the N-well with the deep P layer under it. No record holds its results. |

The tests are [`tests/test_hv_junction.py`](../../tests/test_hv_junction.py). The figures and
the page's numbers are in
[`src/gf180tcad/hvjunction_figures.py`](../../src/gf180tcad/hvjunction_figures.py).

## Rebuild a record

The work directory must be outside the repository, because the sandbox refuses the repository.
`batch.py` refuses a checkout with uncommitted changes under this directory,
[`docker/`](../../docker) or [`tools/`](../../tools). A case whose `result.json` exists is
skipped, so a cut-off batch resumes. Progress is in `<workdir>/batch.log`, one line per finished
case with an ETA; each case's log is `<workdir>/<case>/run.log`.

```sh
W=~/.cache/gf180-tcad/hv-junction

# main: every structure under AL, AD, BL, BD and BLq, the NAT structures under AnL and AnD
uv run --locked python experiments/hv-junction/predict.py $W/main-cases.json main
uv run --locked python experiments/hv-junction/batch.py $W/main $W/main-cases.json --jobs 40
uv run --locked python experiments/hv-junction/record.py $W/main $W/main-cases.json \
    results/hv-junction/main.json --allow-missing

# rest: the cases of main that the records named lack or hold with older parameters.
# Name every record written so far; write each round to a new record (rest, rest2, rest3 ...).
uv run --locked python experiments/hv-junction/predict.py $W/rest-cases.json rest \
    results/hv-junction/main.json results/hv-junction/rest.json \
    results/hv-junction/rest2.json results/hv-junction/rest3.json
uv run --locked python experiments/hv-junction/batch.py $W/rest $W/rest-cases.json --jobs 40
uv run --locked python experiments/hv-junction/record.py $W/rest $W/rest-cases.json \
    results/hv-junction/rest.json --allow-missing

# mem: cases that ran out of memory at 8 GiB, rerun with more (a case file of those cases)
uv run --locked python experiments/hv-junction/batch.py $W/mem $W/mem-cases.json --jobs 8 --mem 24g
uv run --locked python experiments/hv-junction/record.py $W/mem $W/mem-cases.json \
    results/hv-junction/mem.json --allow-missing
# gaps: cases of the main set that still had no breakdown value (a case file of those cases)
# sharp: the sharp-corner sections, which predict.py runs in 128-bit precision; take them
# from `predict.py OUT.json rest RECORD.json ...` (the cases whose parameters changed)

# family: the key structures under the lighter and heavier substrate and a higher oxide charge
uv run --locked python experiments/hv-junction/predict.py $W/family-cases.json family
uv run --locked python experiments/hv-junction/batch.py $W/family $W/family-cases.json --jobs 40
uv run --locked python experiments/hv-junction/record.py $W/family $W/family-cases.json \
    results/hv-junction/family.json --allow-missing

# p5: each ring-sense structure with its first ring held at 0 V
uv run --locked python experiments/hv-junction/predict.py $W/p5-cases.json p5
uv run --locked python experiments/hv-junction/batch.py $W/p5 $W/p5-cases.json --jobs 18
uv run --locked python experiments/hv-junction/record.py $W/p5 $W/p5-cases.json \
    results/hv-junction/p5.json --allow-missing

# checks: precision, bias step and mesh (eight cases), then the three 1D diodes
uv run --locked python experiments/hv-junction/checks.py cases $W/checks-cases.json
uv run --locked python experiments/hv-junction/batch.py $W/checks $W/checks-cases.json --jobs 8
uv run --locked python experiments/hv-junction/record.py $W/checks $W/checks-cases.json \
    results/hv-junction/checks.json
uv run --locked python experiments/hv-junction/checks.py diodes $W/diodes
uv run --locked python experiments/hv-junction/checks.py record $W/diodes \
    results/hv-junction/diodes.json

# charon: cases of main on Charon (16 GiB each), compared with the committed DEVSIM record
uv run --locked python experiments/hv-junction/charon_batch.py $W/charon2 $W/main-cases.json \
    'NP4|BL|edge' 'NT20|BD|edge'
uv run --locked python experiments/hv-junction/charon_record.py $W/charon2 \
    results/hv-junction/charon.json HEAD:results/hv-junction/main.json \
    'NP4|BL|edge' 'NT20|BD|edge'
```

After a record is added or replaced, or [`structures.json`](structures.json),
[`hvsite.py`](hvsite.py) or [`predict.py`](predict.py) changes:

```sh
uv run --locked --group docs python -m gf180tcad.hvjunction_figures tables
make manifest
uv run --locked pytest tests/test_hv_junction.py tests/test_manifest.py
uv run --locked --group docs sphinx-build -W -b html docs docs/_build
```

The first command rewrites the result tables of the docs page: one row per structure of
[`structures.json`](structures.json), one column per process. It changes the page only when
the structures or the processes changed. Every number of the page and every figure is read
from the records at docs build time, so nothing is typed by hand from a record. The tests pick
up each record that exists.

A record is the record of what ran at its commit. The page, the figures and the tests read a
case only when the record's `params_sha256` of that case is the hash of the parameters
[`predict.py`](predict.py) gives now. A case run with other parameters, and a case with no
result, prints as a dash. So a record made before a change of the structures or the process
never prints a superseded number, and the dashes show what a `rest` round has to cover.

The order of the prediction records is `main`, `rest`, `rest2`, `rest3`, `mem`, `gaps`, `sharp`, `rest5`, `ring128` (six multi-ring cases in 128-bit), `family`, `family3` (the family's sharp corners in 128-bit): a
case takes the row of the last of them that holds it. A further round needs its name added
to `PREDICTION_RECORDS` in
[`src/gf180tcad/hvjunction_figures.py`](../../src/gf180tcad/hvjunction_figures.py) and in
[`tests/test_hv_junction.py`](../../tests/test_hv_junction.py). The record `p5` is its own
set. Its cases carry the names of ordinary cases with other parameters, so it is never merged
with the others and has its own table. `charon-firstpass.json` holds six sections of the
first doping family, against the `main.json` of commit 1b6e59f.

## Check a rerun against the records

[`verify.py`](verify.py) reruns recorded cases in the sandbox and compares each with its row in
the last prediction record that holds it:

```sh
# named cases
uv run --locked python experiments/hv-junction/verify.py $W/verify 'NT20|BL|edge' 'NW0|BD|edge'
# eight cases drawn at random from those that take minutes (no rings, double precision)
uv run --locked python experiments/hv-junction/verify.py $W/verify --sample 8 --seed 1
```

It prints one line per case and exits 0 when every breakdown voltage agrees within `--tol`
(0.1 V unless given), 1 when one differs or a rerun fails, and 2 when a named case is not in
the records with its present parameters. A line reads:

```text
ok       NT20c|BD|corner (rest3): rerun 62.1643 V, record 62.1643 V, difference +0.0000 V; bias points equal
ok       DT20b|BL|edge (main): rerun 32.3078 V, record 32.3539 V, difference -0.0461 V; bias points differ
```

A case of a record made with the present sweep code reproduces exactly, with equal bias
points. The record `main` was run with an earlier voltage ramp. Its cases visit other bias
points, and the breakdown voltage, interpolated between them, differs by up to 0.07 V in the
nine cases tried. The sandbox test of [`tests/test_hv_junction.py`](../../tests/test_hv_junction.py)
(`pytest -m sandbox`) reruns one case to 1e-6 V. The same file's other tests check that every
number and table of the docs page is the records' own.

## Run times

The times are those of the first `main` batch (478 cases at commit 48c2657, a coarser mesh for
the abutting junctions than now). On this project's host (88 logical CPUs, 40 jobs at once) it
took 10.9 hours. A case took 8.2 minutes at the median (493 s), and nine in ten took under
22 minutes. The shortest took 2 minutes. The slow cases are the floating rings in bare
substrate (P-well assumption B): the eight slowest took 4.3 to 9.5 hours each (NR3W3, NR3M1,
NR4S, NR5_1p4 and NR5_2). The rerun case of the sandbox test, NW0 under B at the straight
edge, took 5 minutes.

Of the check cases, the 0.1 µm bare edge took 9 minutes and the 0.05 µm one 30 minutes in the
development runs. A 0.025 µm mesh took 2.2 hours and is not among the check cases.

## What is pinned

Each run's `pins.json` holds the commit, whether the checkout had uncommitted changes, the
image by digest ([`docker/TCAD_DEV_IMAGE`](../../docker/TCAD_DEV_IMAGE), and
[`docker/CHARON_IMAGE`](../../docker/CHARON_IMAGE) for a Charon run) and the sha256 of every
tracked file of this directory.

A record of [`record.py`](record.py) holds the image and the sha256 of the five modules a
sweep imports ([`dd.py`](dd.py), [`fieldline.py`](fieldline.py), [`ionize.py`](ionize.py),
[`structure.py`](structure.py), [`sweep.py`](sweep.py)), which every run must share. It also
lists every commit its runs were made at, so a batch restarted after an unrelated commit is
accepted. It refuses runs from a checkout with uncommitted changes. It holds the sha256 of
each case's parameters. A Charon record adds the Charon image, each case's commit and Charon
module hashes, and the commit, path and sha256 of the DEVSIM record it compares with. The
diode record of [`checks.py`](checks.py) holds one run's full pins.

The tests check a record's pins against the files at each of its commits, so those commits
must stay ancestors of the branch: never rebase a branch that holds a record.

Not pinned:

- the evampire commit that [`structures.json`](structures.json) was exported from; the file
  itself is hashed;
- the case file given to `batch.py`; a record holds each case's parameter hash, and the tests
  rebuild the case sets from `predict.py` and `checks.py`;
- the host and its CPU;
- a commit made while a batch runs. `batch.py` takes the pins when it starts and writes a
  warning line to `batch.log` if the checkout differs when it ends.

The development runs made before `run.py` wrote pins (the first bare edges, the calibration
sets of [`cases.py`](cases.py), the first Charon runs) are in no record. The check cases
replace them.
