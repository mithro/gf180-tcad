# Reproduce

How to rerun everything in this project. Every simulator invocation runs inside
a {doc}`pinned container image <image>` through a resource-limited {term}`sandbox`
({doc}`sandbox`), so a result can be
regenerated on another machine and compared byte for byte.

Results are produced as files with fixed formatting (shortest round-trip
floats, `\n` line endings, `.` decimal separator, sorted JSON keys, UTF-8, no
timestamps, hostnames or absolute host paths), and the documentation will
be generated from those files, so the pages will never show numbers that cannot
be reproduced.

(getting-the-source)=

## Getting the source, with its submodule

The {term}`TCAD` code uses the {{ DEVSIM }} plugin of {{ gplugins }} from {{ gplugins_fork }}. The fork
is a [git submodule](https://git-scm.com/book/en/v2/Git-Tools-Submodules),
{repo}`third_party/gplugins`, pinned to one commit on the fork's `main` (see
{repo}`.gitmodules`). Clone with
[`git clone --recurse-submodules`](https://git-scm.com/docs/git-clone) so that it is checked out:

```sh
git clone --recurse-submodules https://github.com/mithro/gf180-tcad.git
```

In a clone made without it, and in **every** new
[worktree](https://git-scm.com/docs/git-worktree) (each worktree has its own submodule
checkout, which `git worktree add` leaves empty), run
[`git submodule update --init`](https://git-scm.com/docs/git-submodule) once, and again
whenever a pull of `main` moves the submodule pin:

```sh
git submodule update --init
```

The {term}`SPICE` reference ({ref}`one-command`) does not need the submodule. The TCAD image
({doc}`image`) does not install gplugins: it imports it from the submodule, which
{repo}`tools/sandbox-run` mounts read-only with the rest of the repository at `/work/src`.
Without the checkout, `import gplugins` fails there;
{test}`tests/test_submodule.py::test_plugin_imports_from_submodule` checks that it comes from the
submodule, and {test}`tests/test_submodule.py::test_submodule_pinned_on_fork_main` that the pin
is a commit on the fork's `main`.

(one-command)=

## One command: `make reproduce`

```sh
make reproduce
```

This target of the {repo}`Makefile` regenerates the {term}`SPICE` reference dataset for both
engines ({{ ngspice }} and {{ Xyce }}), all {term}`corners <corner>`, both devices and every
geometry into {repo}`results/spice`, then runs `python -m gf180tcad.manifest verify results/`
({py:mod}`gf180tcad.manifest`). It exits non-zero if any {term}`job` fails or if any file
differs from, is missing from, or is not listed in the {term}`manifest`,
{repo}`results/MANIFEST.sha256`. On a clean checkout a successful run leaves
`git status` clean. It needs {{ Docker }}, the sandbox (see {doc}`sandbox`) and the
pinned image (see {doc}`image`). The 120 jobs take about a minute with 8 jobs,
the default (`make reproduce JOBS=16` runs more at once, up to the
{ref}`memory admission <reproduce-how-it-works>` limit of 32).

After an intended change to the results, regenerate them and rewrite the
manifest with:

```sh
make manifest
```

(partial-reference)=

## Running part of the reference

`make reproduce` is a wrapper around the {{ uv }}-run command line of the package
({repo}`src/gf180tcad/__main__.py`, {py:mod}`gf180tcad.reference`):

```sh
uv run --locked python -m gf180tcad spice-reference \
    [--engine ngspice|xyce|both] [--corner C ...] [--device D ...] \
    [--geometry G ...] [--jobs N] --out results/spice
```

`--corner` ({term}`corner`: `typical`, `ff`, `ss`, `fs`, `sf`, that is {term}`TT`, {term}`FF`,
{term}`SS <SS corner>`, {term}`FS` and {term}`SF`), `--device`
({term}`nfet_05v0`, {term}`pfet_05v0`) and `--geometry` (a {term}`geometry id` such as
`w10p0_l0p60`) can be
repeated; the default is all of them, and `--engine` defaults to `both`.
`--geometry` keeps, for each selected device, only the listed geometries that
device has; a geometry that no selected device has is an error. For example,
a single device at one corner:

```sh
uv run --locked python -m gf180tcad spice-reference --engine ngspice \
    --corner typical --device nfet_05v0 --out /tmp/nfet-typical
```

`--out` is *replaced* by the jobs that were run, so write a partial run to a
directory of its own, not to {repo}`results/spice`: a filtered run whose `--out` resolves to
the committed {repo}`results/spice` is refused before any job starts
({py:func}`gf180tcad.reference.check_committed_out`). `--out` must not exist, be empty, or
be an earlier reference tree (one with a {repo}`provenance.json <results/spice/provenance.json>`, see {ref}`results-layout`); any
other
directory is refused.

(reproduce-how-it-works)=

How it works:

- **One job** is one engine, corner, device and geometry. It runs entirely
  inside the pinned image as one sandbox container
  (`python -m gf180tcad spice-job ...`). The job checks the image's {term}`PDK`
  against {repo}`docker/base/versions.json`, runs every {term}`sweep` the engine supports,
  extracts the metrics and writes the CSV and JSON files. Every published
  number is computed and formatted by the image's {{ Python }} and {{ numpy }}, never by
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
  {term}`gf180-tcad.slice` ({ref}`sandbox-host-setup`), so at most 32
  ({py:func}`gf180tcad.reference.check_admission`).
- **Progress.** One line per finished job, with done/total, jobs per minute
  and the ETA, so a log file can be followed while it runs.

(results-layout)=

## Layout of {repo}`results/spice`

```text
results/spice/provenance.json
results/spice/<engine>/<corner>/<device>/<geometry_id>/<sweep>.csv
results/spice/<engine>/<corner>/<device>/<geometry_id>/metrics.json
```

Browse it: {repo}`results/spice`.

- `<sweep>.csv` holds the simulated columns (`vd vg vb id ig ib`, or `vg cgg`
  for `cv`). Its `# key: value` header holds only engine, corner, device,
  {term}`geometry_id`, w_um, l_um, sweep, temp_c and units.
- `metrics.json` holds the same identifying fields plus the extracted metrics
  (definitions in {py:mod}`gf180tcad.metrics`).
- **Xyce has no cv analysis.** Xyce directories therefore have no `cv.csv`,
  and their `metrics.json` has no {term}`cgg_inv_ff` or {term}`cgg_acc_ff`.
- {repo}`provenance.json <results/spice/provenance.json>` ({term}`provenance`) holds the
  contents of {repo}`docker/base/versions.json`, the pinned image reference with its
  {term}`digest <manifest digest>` ({repo}`docker/IMAGE`) and
  {term}`generator_sha256`. That is the sha256 over the sorted (path, sha256) pairs
  of the source files of the modules the generator imports, listed explicitly
  in {py:data}`gf180tcad.reference.GENERATOR_MODULES` (a test,
  {test}`tests/test_reference.py::test_generator_modules_match_the_import_graph`, checks the
  list against the import graph), plus {repo}`tools/sandbox-run`, which sets the container's
  thread environment and limits. There is deliberately no git commit and no date, so a
  regeneration on any machine gives the same bytes. A change to one of those
  files changes `generator_sha256`, so the reference has to be regenerated
  (and the manifest updated) together with such a change. Code elsewhere under
  {repo}`src/`, such as later {term}`TCAD` modules, does not affect it.

Generation never compares the two engines. Each engine's results are
published as they are; the ngspice/Xyce cross-check is a separate test
({test}`tests/spice/test_xyce.py::test_engines_agree`), described in
{doc}`../limitations/engine-cross-check`.

(cross-host-determinism)=

## Cross-host determinism

The committed reference is generated on the project's own machine, whose CPUs
are Intel Xeon Gold 6152. To show that the same bytes come out on a different
host, the `crosscheck` {{ GitHub_Actions }} workflow
({repo}`.github/workflows/crosscheck.yml`) regenerates it on a {{ GitHub_hosted_runner }}
(`ubuntu-latest`) and requires every file to be byte-identical, by sha256, to the
{term}`manifest` {repo}`results/MANIFEST.sha256`. The
runner has a different CPU, kernel and Docker installation, and its CPU model
varies from run to run. The full reference has passed on an AMD EPYC 7763; the only
pass on an AMD EPYC 9V45 was an earlier 8-job subset, before the numpy fix below. There is no {term}`tolerance`: a difference in the last digit of one float
fails it.

**Everything is cross-checked on GitHub-hosted runners.** The
{repo}`subset file <tests/crosscheck_subset.txt>` holds the single line `all`, which stands
for every job of the reference: both engines, all five corners, both devices and all six
geometries of each, 120 jobs. Each job includes every sweep its engine runs
({term}`idvg_lin`, {term}`idvg_sat`, {term}`idvd`, `ioff` and, for ngspice only, {term}`cv`).
The check covers all 660 CSV and metrics files, the {term}`provenance` file
({repo}`results/spice/provenance.json`) and the {term}`corner envelope`
({repo}`results/spice/envelope.json`).
Nothing is checked only locally.

**What we found and fixed.** The first full cross-check
([run](https://github.com/mithro/gf180-tcad/actions/runs/39115902279), on an
AMD EPYC 7763) failed. Every raw simulator CSV was identical, but five
`metrics.json` files differed in the last digits: {term}`Vt`, {term}`subthreshold slope` and
the {term}`DIBL` derived from them. The cause was numpy's run-time {term}`SIMD dispatch`.
numpy picks a kernel for each operation by CPU feature level, and its
`log10` kernels for AVX-512 and for AVX2 differ by one {term}`ulp` on some inputs.
The local Xeon and an earlier EPYC 9V45 runner both have AVX-512; the
EPYC 7763 has only AVX2. The sandbox ({repo}`tools/sandbox-run`) now pins numpy to its
baseline ({term}`x86-64-v2`) kernels by disabling every dispatch target with
[`NPY_DISABLE_CPU_FEATURES`](https://numpy.org/doc/stable/reference/simd/build-options.html#runtime-dispatch),
so all such hosts compute the same bits. The
reference was regenerated: no CSV changed, and the largest change to a
published metric was 5.7e-15 relative (51 ulp, in a DIBL value). Commits
[1731912](https://github.com/mithro/gf180-tcad/commit/1731912) (the fix) and
[6205cb9](https://github.com/mithro/gf180-tcad/commit/6205cb9) (the
regenerated results); the cross-check then passed on an AMD EPYC 7763
([run](https://github.com/mithro/gf180-tcad/actions/runs/39116857613)). A
sandbox test ({repo}`tests/sandbox/test_numpy_dispatch.py`) checks that numpy reports no
dispatch target enabled in the container, and that the baseline results equal those with only the AVX-512
targets disabled; the workflow checks the former on the runner too.

The subset file can instead list jobs one per line, as
`<engine>/<corner>/<device>/<geometry_id>`, to cross-check part of the
reference. The corner envelope is then not compared, because it is the
min/max over all five corners and a partial run lacks some of them, so its
envelope always differs from the committed one. The envelope is computed only
by selecting from the metrics floats, and those are compared.

The workflow runs on pull requests that change the sources, tools, image
pin, results, project metadata, lock file, Makefile, subset file or the
workflow itself, and also weekly and on demand. Its steps are:

1. Free disk space and pull {repo}`docker/IMAGE` by its {term}`digest <manifest digest>`.
2. Install the sandbox {term}`slice` with `sudo tools/sandbox-setup`
   ({repo}`tools/sandbox-setup`, {ref}`sandbox-host-setup`). Then, while
   one container started by {repo}`tools/sandbox-run` is running, check that the
   container has the limits of a reference job (4 GiB memory, no swap, 1 CPU,
   256 PIDs) and that it runs inside `gf180-tcad.slice` with the slice's
   limits. The same {repo}`tools/sandbox-run` is used as locally; the sandbox is
   never disabled.
3. {repo}`tools/crosscheck-args` turns the subset file into `spice-reference`
   filters (`--engine`, `--corner`, `--device` and `--geometry`).
   The jobs then run with `--jobs 3` (3 × 4 GiB, 1 CPU each, on a 4-CPU,
   16 GiB runner) into a temporary `--out`. They are never written to
   {repo}`results/spice`, because `--out` is replaced by what was run.
4. `python -m gf180tcad.manifest verify-subset <out> --against
   results/MANIFEST.sha256 --prefix spice/ --subset tests/crosscheck_subset.txt`
   ({py:func}`gf180tcad.manifest.verify_subset`) prints one line per difference, as `<reason>: spice/<path>`, and exits
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
5. On failure, an [artefact](https://docs.github.com/en/actions/tutorials/store-and-share-data)
   named `crosscheck-differences` is uploaded. It
   holds the generated and committed copy of each differing file, a
   `diff -u` of each pair, the generator log, the runner and sandbox
   diagnostics, and the scratch directory of any job that failed.

{repo}`provenance.json <results/spice/provenance.json>` is compared. A change to the
generator's sources changes {term}`generator_sha256`, so the cross-check fails until the reference has been
regenerated and the manifest updated, the same as `make reproduce`.

```{toctree}
:maxdepth: 1

sandbox
image
```
