# Reproduce

How to rerun everything in this project. Every simulator invocation runs inside
a pinned container image through a resource-limited sandbox, so a result can be
regenerated on another machine and compared byte for byte.

Results are produced as files with fixed formatting (shortest round-trip
floats, `\n` line endings, `.` decimal separator, sorted JSON keys, UTF-8, no
timestamps, hostnames or absolute host paths), and the documentation will
be generated from those files, so the pages will never show numbers that cannot
be reproduced.

## One command: `make reproduce`

```sh
make reproduce
```

This regenerates the SPICE reference dataset for both engines (ngspice and
Xyce), all corners, both devices and every geometry into `results/spice`, then
runs `python -m gf180tcad.manifest verify results/`. It exits non-zero if any
job fails or if any file differs from, is missing from, or is not listed in
`results/MANIFEST.sha256`. On a clean checkout a successful run leaves
`git status` clean. It needs Docker, the sandbox (see {doc}`sandbox`) and the
pinned image (see {doc}`image`). The 120 jobs take about a minute with 8 jobs,
the default (`make reproduce JOBS=16` runs more at once).

After an intended change to the results, regenerate them and rewrite the
manifest with:

```sh
make manifest
```

## Running part of the reference

`make reproduce` is a wrapper around:

```sh
uv run --locked python -m gf180tcad spice-reference \
    [--engine ngspice|xyce|both] [--corner C ...] [--device D ...] \
    [--geometry G ...] [--jobs N] --out results/spice
```

`--corner` (`typical`, `ff`, `ss`, `fs`, `sf`), `--device` (`nfet_05v0`,
`pfet_05v0`) and `--geometry` (a geometry id such as `w10p0_l0p60`) can be
repeated; the default is all of them, and `--engine` defaults to `both`.
`--geometry` keeps, for each selected device, only the listed geometries that
device has; a geometry that no selected device has is an error. For example,
a single device at one corner:

```sh
uv run --locked python -m gf180tcad spice-reference --engine ngspice \
    --corner typical --device nfet_05v0 --out /tmp/nfet-typical
```

`--out` is *replaced* by the jobs that were run, so write a partial run to a
directory of its own, not to `results/spice`. It must not exist, be empty, or
be an earlier reference tree (one with a `provenance.json`); any other
directory is refused.

How it works:

- **One job** is one engine, corner, device and geometry. It runs entirely
  inside the pinned image as one sandbox container
  (`python -m gf180tcad spice-job ...`). The job checks the image's PDK
  against `docker/base/versions.json`, runs every sweep the engine supports,
  extracts the metrics and writes the CSV and JSON files. Every published
  number is computed and formatted by the image's Python and numpy, never by
  the host's.
- **The host** only schedules the jobs and copies their finished files byte
  for byte. Each job has its own scratch directory outside the repo (under
  `$TMPDIR`). It is deleted when the job succeeds, and kept and named in the
  report when the job fails.
- **No partial results.** The results are assembled in a staging directory
  and swapped into place only when every job succeeded. The swap is an atomic
  exchange, so `--out` is never missing, even if the process is killed. If
  any job fails or the run is interrupted (Ctrl-C), `--out` is left as it
  was, queued jobs are cancelled, the failures are listed and the command
  exits non-zero.
- **Memory admission.** `--jobs N` (default 8) is accepted only if
  N × 4 GiB, the per-job sandbox memory limit, fits the 128 GiB budget of
  `gf180-tcad.slice`, so at most 32.
- **Progress.** One line per finished job, with done/total, jobs per minute
  and the ETA, so a log file can be followed while it runs.

## Layout of `results/spice`

```text
results/spice/provenance.json
results/spice/<engine>/<corner>/<device>/<geometry_id>/<sweep>.csv
results/spice/<engine>/<corner>/<device>/<geometry_id>/metrics.json
```

- `<sweep>.csv` holds the simulated columns (`vd vg vb id ig ib`, or `vg cgg`
  for `cv`). Its `# key: value` header holds only engine, corner, device,
  geometry_id, w_um, l_um, sweep, temp_c and units.
- `metrics.json` holds the same identifying fields plus the extracted metrics
  (definitions in `gf180tcad.metrics`).
- **Xyce has no cv analysis.** Xyce directories therefore have no `cv.csv`,
  and their `metrics.json` has no `cgg_inv_ff` or `cgg_acc_ff`.
- `provenance.json` holds the contents of `docker/base/versions.json`, the
  pinned image reference with its digest (`docker/IMAGE`) and
  `generator_sha256`. That is the sha256 over the sorted (path, sha256) pairs
  of the source files of the modules the generator imports, listed explicitly
  in `gf180tcad.reference.GENERATOR_MODULES` (a test checks the list against
  the import graph), plus `tools/sandbox-run`, which sets the container's
  thread environment and limits. There is deliberately no git commit and no date, so a
  regeneration on any machine gives the same bytes. A change to one of those
  files changes `generator_sha256`, so the reference has to be regenerated
  (and the manifest updated) together with such a change. Code elsewhere under
  `src/`, such as later TCAD modules, does not affect it.

Generation never compares the two engines. Each engine's results are
published as they are; the ngspice/Xyce cross-check is a separate test,
described in {doc}`../limitations/engine-cross-check`.

## Cross-host determinism

The committed reference is generated on the project's own machine, whose CPUs
are Intel Xeon Gold 6152. To show that the same bytes come out on a different
host, the
[`crosscheck` workflow](https://github.com/mithro/gf180-tcad/blob/main/.github/workflows/crosscheck.yml)
regenerates it on a GitHub-hosted runner (`ubuntu-latest`) and requires every
file to be byte-identical, by sha256, to `results/MANIFEST.sha256`. The
runner has a different CPU, kernel and Docker installation, and its CPU model
varies from run to run; so far the runs have landed on AMD EPYC 9V45 and AMD
EPYC 7763. There is no tolerance: a difference in the last digit of one float
fails it.

**Everything is cross-checked on GitHub-hosted runners.** The
[subset file](https://github.com/mithro/gf180-tcad/blob/main/tests/crosscheck_subset.txt)
holds the single line `all`, which stands for every job of the reference:
both engines, all five corners, both devices and all six geometries of each,
120 jobs. Each job includes every sweep its engine runs (`idvg_lin`,
`idvg_sat`, `idvd`, `ioff` and, for ngspice only, `cv`). The check covers
all 660 CSV and metrics files, the provenance file and the corner envelope.
Nothing is checked only locally.

The subset file can instead list jobs one per line, as
`<engine>/<corner>/<device>/<geometry_id>`, to cross-check part of the
reference. The corner envelope is then not compared, because it is the
min/max over all five corners and a partial run lacks some of them, so its
envelope always differs from the committed one. The envelope is computed only
by selecting from the metrics floats, and those are compared.

The workflow runs on pull requests that change the sources, tools, image
pin, results, project metadata, lock file, Makefile, subset file or the
workflow itself, and also weekly and on demand. Its steps are:

1. Free disk space and pull `docker/IMAGE` by its digest.
2. Install the sandbox slice with `sudo tools/sandbox-setup`. Then, while
   one container started by `tools/sandbox-run` is running, check that the
   container has the limits of a reference job (4 GiB memory, no swap, 1 CPU,
   256 PIDs) and that it runs inside `gf180-tcad.slice` with the slice's
   limits. The same `tools/sandbox-run` is used as locally; the sandbox is
   never disabled.
3. `tools/crosscheck-args` turns the subset file into `spice-reference`
   filters (`--engine`, `--corner`, `--device` and `--geometry`).
   The jobs then run with `--jobs 3` (3 × 4 GiB, 1 CPU each, on a 4-CPU,
   16 GiB runner) into a temporary `--out`. They are never written to
   `results/spice`, because `--out` is replaced by what was run.
4. `python -m gf180tcad.manifest verify-subset <out> --against
   results/MANIFEST.sha256 --prefix spice/ --subset tests/crosscheck_subset.txt`
   prints one line per difference, as `<reason>: spice/<path>`, and exits
   non-zero if there is any. The reasons are:
   - `changed`: different bytes.
   - `missing`: a committed file of a listed job was not produced, or the
     provenance file (always required) or, for the full reference, the
     envelope.
   - `not in manifest`: a produced file that was never committed.
   - `not in subset`: a produced job that is not listed.
   - `unknown job`: a listed job that has no committed files.

   On success it prints `identical: 662 files of 120 jobs ...`. The output is
   also shown in the run's summary.
5. On failure, an artefact named `crosscheck-differences` is uploaded. It
   holds the generated and committed copy of each differing file, a
   `diff -u` of each pair, the generator log, the runner and sandbox
   diagnostics, and the scratch directory of any job that failed.

`provenance.json` is compared. A change to the generator's sources changes
`generator_sha256`, so the cross-check fails until the reference has been
regenerated and the manifest updated, the same as `make reproduce`.

```{toctree}
:maxdepth: 1

sandbox
image
```
