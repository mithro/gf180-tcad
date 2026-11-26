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
| [`predict.py`](predict.py) | Writes the prediction case sets `main`, `supp`, `family` and `delta`. |
| [`cases.py`](cases.py) | The bare-edge and calibration sections that the check cases build on. |
| [`checks.py`](checks.py) | Writes the check cases, runs the 1D diodes and writes the diode record. |
| [`structure.py`](structure.py), [`dd.py`](dd.py) | The DEVSIM mesh, doping and drift-diffusion set-up. They run inside the sandbox. |
| [`sweep.py`](sweep.py) | The reverse sweep of one case. It runs inside the sandbox. |
| [`fieldline.py`](fieldline.py), [`ionize.py`](ionize.py) | The field-line trace and the ionisation integral (numpy and scipy only). |
| [`profile1d.py`](profile1d.py) | Sheet resistance and capacitance of a well profile, for the doping anchors. |
| [`diode1d.py`](diode1d.py) | Three abrupt 1D diodes. It runs inside the sandbox. |
| [`run.py`](run.py) | Runs one script through [`tools/sandbox-run`](../../tools/sandbox-run) (8 GiB, one CPU) and gives a run's pins. |
| [`batch.py`](batch.py) | Runs a case set, one container per case, and writes each case's pins. |
| [`record.py`](record.py) | Writes a record from a batch's run directories. |
| [`charon_mesh.py`](charon_mesh.py), [`charon_deck.py`](charon_deck.py), [`charon_run.py`](charon_run.py), [`charon_field.py`](charon_field.py) | The Charon cross-check: DEVSIM's nodes as an Exodus mesh, the decks, the sweep and its post-processing. |
| [`charon_batch.py`](charon_batch.py), [`charon_record.py`](charon_record.py) | Run named cases on Charon, and write their record. |
| [`charon_defaults.py`](charon_defaults.py), [`charon_diode_ref.py`](charon_diode_ref.py) | Development checks of the Charon set-up. No record holds their results. |

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

# main: every structure under A, Aq, B and Bq, the NAT structures under An
uv run --locked python experiments/hv-junction/predict.py $W/main-cases.json main
uv run --locked python experiments/hv-junction/batch.py $W/main $W/main-cases.json --jobs 40
uv run --locked python experiments/hv-junction/record.py $W/main $W/main-cases.json \
    results/hv-junction/main.json --allow-missing

# supp: the cases main left open, and the deep N-wells under A and Aq with the full sweep
uv run --locked python experiments/hv-junction/predict.py $W/supp-cases.json supp
uv run --locked python experiments/hv-junction/batch.py $W/supp $W/supp-cases.json --jobs 40
uv run --locked python experiments/hv-junction/record.py $W/supp $W/supp-cases.json \
    results/hv-junction/supp.json --allow-missing

# family: ten structures under the lighter, heavier and graded substrate and a higher charge
uv run --locked python experiments/hv-junction/predict.py $W/family-cases.json family
uv run --locked python experiments/hv-junction/batch.py $W/family $W/family-cases.json --jobs 40
uv run --locked python experiments/hv-junction/record.py $W/family $W/family-cases.json \
    results/hv-junction/family.json --allow-missing

# delta: every case whose parameters differ from the records named, or that they lack
uv run --locked python experiments/hv-junction/predict.py $W/delta-cases.json delta \
    results/hv-junction/main.json results/hv-junction/supp.json results/hv-junction/family.json
uv run --locked python experiments/hv-junction/batch.py $W/delta $W/delta-cases.json --jobs 40
uv run --locked python experiments/hv-junction/record.py $W/delta $W/delta-cases.json \
    results/hv-junction/delta.json --allow-missing

# checks: precision, bias step and mesh (eight cases), then the three 1D diodes
uv run --locked python experiments/hv-junction/checks.py cases $W/checks-cases.json
uv run --locked python experiments/hv-junction/batch.py $W/checks $W/checks-cases.json --jobs 8
uv run --locked python experiments/hv-junction/record.py $W/checks $W/checks-cases.json \
    results/hv-junction/checks.json
uv run --locked python experiments/hv-junction/checks.py diodes $W/diodes
uv run --locked python experiments/hv-junction/checks.py record $W/diodes \
    results/hv-junction/diodes.json

# charon: six cases of main on Charon (16 GiB each)
CASES='NT20|A|edge NT20|B|edge NW1p5|B|edge NM1_6|B|edge NR1_2|B|edge DT20|B|edge'
uv run --locked python experiments/hv-junction/charon_batch.py $W/charon $W/main-cases.json $CASES
uv run --locked python experiments/hv-junction/charon_record.py $W/charon $W/main-cases.json \
    results/hv-junction/charon.json $CASES
```

After a record is added or replaced:

```sh
make manifest
uv run --locked pytest tests/test_hv_junction.py tests/test_manifest.py
uv run --locked --group docs sphinx-build -W -b html docs docs/_build
```

Nothing on the docs page is typed by hand from a record. The page prints a dash for a value
whose record is not committed, and the value appears once the record is. The tests pick up
each record that exists.

A record is the record of what ran at its commit. A later change to
[`structures.json`](structures.json), [`hvsite.py`](hvsite.py) or [`predict.py`](predict.py)
leaves cases in it whose parameters are no longer the current ones. The `delta` set reruns
those. The page and the figures take each case from the last of `main`, `supp`, `family` and
`delta` that holds it, and read only the structures that are in
[`structures.json`](structures.json). The page counts the printed cases that still come from
superseded parameters; with a complete `delta` record the count is 0, and the tests then
require it.

The committed `main.json` was run at commit 48c2657. A rebuild of `main` from a later commit
holds the current parameters for every case, not the ones of that commit.

## Run times

On this project's host (88 logical CPUs, 40 jobs at once) the 478 cases of `main` took
10.9 hours. A case took 8.2 minutes at the median (493 s), and nine in ten took under
22 minutes. The shortest took 2 minutes. The slow cases are the floating rings in bare
substrate (assumption B): the eight slowest took 4.3 to 9.5 hours each (NR3W3, NR3M1, NR4S,
NR5_1p4 and NR5_2). The rerun case of the sandbox test, `NW0|B|edge`, took 5 minutes.

Of the check cases, the 0.1 µm bare edge took 9 minutes and the 0.05 µm one 30 minutes in the
development runs. A 0.025 µm mesh took 2.2 hours and is not among the check cases.

## What is pinned

Each run's `pins.json` holds the commit, whether the checkout had uncommitted changes, the
image by digest ([`docker/TCAD_DEV_IMAGE`](../../docker/TCAD_DEV_IMAGE), and
[`docker/CHARON_IMAGE`](../../docker/CHARON_IMAGE) for a Charon run) and the sha256 of every
tracked file of this directory. A record holds the pins once. [`record.py`](record.py),
[`charon_record.py`](charon_record.py) and [`checks.py`](checks.py) refuse runs whose pins
differ and runs from a checkout with uncommitted changes. A record also holds the sha256 of
each case's parameters.

The tests check a record's pins against the files at the record's own commit, so that commit
must stay an ancestor of the branch: never rebase a branch that holds a record.

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
