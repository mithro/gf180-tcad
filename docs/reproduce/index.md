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
{repo}`third_party/gplugins <third_party>`, pinned to one commit on the fork's `main` (see
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

To have `git pull`, `git checkout` and `git switch` update the submodule checkout to the pinned
commit automatically, set
[`submodule.recurse`](https://git-scm.com/docs/git-config#Documentation/git-config.txt-submodulerecurse)
once per clone (worktrees share the setting); the first checkout of a new worktree still needs
`git submodule update --init`:

```sh
git config submodule.recurse true
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

This target of the {repo}`Makefile` regenerates every committed result in place, in dependency
order, and then runs `python -m gf180tcad.manifest verify results/` ({py:mod}`gf180tcad.manifest`).
Each step is a target of its own, which can also be run alone:

| target | runs | writes |
|---|---|---|
| `spice-reference` | `python -m gf180tcad spice-reference --engine both --jobs $(JOBS)`: the {term}`SPICE` reference for both engines ({{ ngspice }} and {{ Xyce }}), all {term}`corners <corner>`, both devices and every geometry | {repo}`results/spice` |
| `tcad-meshconv` | `python -m gf180tcad.tcad meshconv --dim 1` for both devices, then `--dim 2 --jobs 1` (one 16 GiB {term}`job` at a time) | {repo}`results/tcad/meshconv` |
| `tcad-start` | `python -m gf180tcad.tcad moscap --params start`: `--dim 1` for both devices, and `--dim 2` for each committed 2D cell; the L = 2 µm cells run `--method qs`, then `--method combine-qs` on the same `--resume` directory under `tmp/reproduce-scratch` (`TCAD_SCRATCH=`), so a cut-off job resumes when the target runs again | {repo}`results/tcad/moscap1d`, {repo}`results/tcad/moscap2d` |
| `tcad-calibrate` | `python -m gf180tcad.calibrate run` for both devices | {repo}`results/tcad/calibration` |
| `tcad-calibrated` | `python -m gf180tcad.tcad moscap --dim 1 --params calibrated` for both devices (no 2D calibrated results are committed) | {repo}`results/tcad/moscap1d` |
| `tcad-validate` | `python -m gf180tcad.calibrate validate` for both devices, which refuses unless the calibration files are committed and unchanged | {repo}`results/tcad/validation` |

It exits non-zero if any job fails or if any file differs from, is missing from, or is not
listed in the {term}`manifest`, {repo}`results/MANIFEST.sha256`. It needs {{ Docker }}, the sandbox
(see {doc}`sandbox`), the pinned images (see {doc}`image`) and the plugin submodule
({ref}`getting-the-source`), so clone with `--recurse-submodules`. The commands are those of the
{ref}`TCAD provenance table <tcad-provenance>`;
{test}`tests/test_makefile.py::test_reproduce_runs_in_dependency_order` and the other tests of
{repo}`tests/test_makefile.py` parse every command `make -n reproduce` prints with the argument
parser of the command line it calls, and compare the jobs with the committed job directories.

**The expected runtime is hours.** The 120 SPICE jobs take about a minute with 8 jobs, the
default (a host with less than 32 GiB of memory should pass `make reproduce JOBS=4`, because each job is
admitted at 4 GiB; `make reproduce JOBS=16` runs more at once, up to the
{ref}`memory admission <reproduce-how-it-works>` limit of 32). The 1D {term}`TCAD` jobs take
minutes. The 2D ones take hours: the 2D {term}`mesh convergence` and every 2D
{term}`MOS capacitor` job run one 16 GiB job at a time, hours each ({doc}`../limitations/moscap2d`),
so the host needs 16 GiB of memory free for the sandbox.

**Not yet run end to end, and the 2D files are not expected to match.** The TCAD half of
`make reproduce` has not been run in one go. Its 2D job files were made by older code, and the
L = 2 µm {term}`sweeps <sweep>` were resumed, so a fresh run differs from them; see {ref}`moscap2d-reproduce`.
So the final `manifest verify` of `make reproduce` is expected to exit non-zero until the 2D results are
regenerated and committed ([issue #35](https://github.com/mithro/gf180-tcad/issues/35)).
`make spice-reference` followed by `python -m gf180tcad.manifest verify results/` checks the SPICE
half alone.

(reproduce-quick)=

**`make reproduce-quick`** runs only the cross-checked TCAD subset,
{repo}`tests/crosscheck_tcad_subset.txt` (the two calibrated 1D MOS capacitor jobs), as the
{ref}`crosscheck-tcad job <cross-host-tcad>` does: {repo}`tools/crosscheck-tcad-run` writes the jobs
into `tmp/reproduce-quick` (`QUICK_OUT=`; a path under {repo}`results`, or inside the repository but outside `tmp/`, is refused), then
`python -m gf180tcad.manifest verify-subset tmp/reproduce-quick --kind tcad --prefix tcad/`
compares them byte for byte with the manifest. A TCAD subset `all` covers the `moscap1d` and `moscap2d` results folders only and reports `moscap2d/*/calibrated` as `unknown job` until issue [#35](https://github.com/mithro/gf180-tcad/issues/35) commits the 2D calibrated results. It takes about a minute; on 2026-10-26 it printed
`identical: 5 files of 2 jobs in tmp/reproduce-quick match results/MANIFEST.sha256 under tcad/`.

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
be an earlier reference results folder (one with a {repo}`provenance.json <results/spice/provenance.json>`, see {ref}`results-layout`); any
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

(tcad-provenance)=

## Provenance of the TCAD results

The top folder of each set of TCAD results holds one `provenance.json`
({py:func}`gf180tcad.tcad.tree_provenance`): the images that made it, the plugin commit, the
calibration applied (if any), the entry point that wrote the folder (`generator`) and a
{term}`generator_sha256`. The hash is **per results folder**
([issue #34](https://github.com/mithro/gf180-tcad/issues/34)): it covers the import closure of the entry point that writes the folder, one module list
per entry point in {py:data}`gf180tcad.tcad.TCAD_GENERATORS`, plus the inputs both entry points
share: the plugin's `gplugins/devsim` files, the {term}`process files <process file>` and
{repo}`tools/sandbox-run`. The closure is the static one, so an import inside a function counts
too ({test}`tests/tcad/test_tcad_provenance.py::test_tcad_generator_modules_match_the_import_graph`
runs once per entry point). {py:data}`gf180tcad.tcad.TREE_GENERATORS` ties each results folder
to its writer, and {test}`tests/tcad/test_tcad_provenance.py::test_committed_tcad_provenance_current`
requires every results folder to name its writer and to carry that writer's current hash. A
change to a module that a folder's writer never imports therefore leaves the folder's hash alone: the
calibration code ({py:mod}`gf180tcad.calibrate`, {py:mod}`gf180tcad.specwindow`) is not in the
closure of {py:mod}`gf180tcad.tcad.__main__`, and the job command line
({py:mod}`gf180tcad.tcad.__main__`) is not in the closure of
{py:mod}`gf180tcad.calibrate.__main__`. A change to a shared module (for example
{py:mod}`gf180tcad.tcad`, {py:mod}`gf180tcad.tcad.moscap1d`) or a shared input still changes
every hash. The results folders, their writers and the commands that regenerate them (then
`make manifest`):

| results folder | written by | regenerate |
|---|---|---|
| {repo}`results/tcad/moscap1d` | {py:mod}`gf180tcad.tcad.__main__` | `python -m gf180tcad.tcad moscap --device D --dim 1 --params start` (and `--params calibrated`) `--out results/tcad/moscap1d` |
| {repo}`results/tcad/moscap2d` | {py:mod}`gf180tcad.tcad.__main__` | `python -m gf180tcad.tcad moscap --device D --dim 2 --params start --geometry GID --out results/tcad/moscap2d` |
| {repo}`results/tcad/meshconv` | {py:mod}`gf180tcad.tcad.__main__` | `python -m gf180tcad.tcad meshconv --device D --dim 1` (and `--dim 2 --jobs 1`) `--out results/tcad/meshconv` |
| {repo}`results/tcad/calibration` | {py:mod}`gf180tcad.calibrate.__main__` | `python -m gf180tcad.calibrate run --device D --out results/tcad/calibration` |
| {repo}`results/tcad/validation` | {py:mod}`gf180tcad.calibrate.__main__` | `python -m gf180tcad.calibrate validate --device D --out results/tcad/validation` |

The 2D jobs run one 16 GiB job at a time, hours each; the L = 2 µm cells run `--method qs`,
then `--method combine-qs`. The validation is regenerated after the calibration is committed.

**Updating the provenance without a rerun.** When a change to a writer's closure cannot have
changed a results folder's data and the folder is not regenerated (the 2D jobs take hours), its
provenance can be updated to the current hash without a rerun:

```sh
uv run --locked python tools/restamp-tcad-provenance results/tcad/<tree>   # --dry-run first
make manifest
```

{repo}`tools/restamp-tcad-provenance` rewrites only `generator` and `generator_sha256`, the writer
taken from the folder's name, and refuses (exit 2, file unchanged) if anything else in the file
differs from what the writer would write now: the plugin commit, an image, the calibration
applied, or a `generator` naming the other entry point. Then the folder has to be regenerated.
Such an update claims that the data did not change; it does not show it. So every one is
recorded below, with the hash the folder had before.

**Results folders written under the old scheme.** Before [issue #34](https://github.com/mithro/gf180-tcad/issues/34) one hash covered both entry points, and
`provenance.json` had no `generator`. A results folder produced that way, for example on a branch that
was started before the per-folder hash and merges after it, fails
{test}`tests/tcad/test_tcad_provenance.py::test_committed_tcad_provenance_current`.
Bring it to the new scheme by rerunning its writer at the merged code, or by updating its
provenance as above (after rebasing onto the per-folder hash) and adding it to the record below.

**Provenance updated to the per-folder hash ([issue #34](https://github.com/mithro/gf180-tcad/issues/34)), not regenerated.** Every results folder's provenance was updated with
{repo}`tools/restamp-tcad-provenance` from the shared hash
`deecaa58fe64357d90ebc9aacf86e2607ece0fb65a1b2ceecf6f209eb4a0afde` to its writer's hash at that
change: {repo}`results/tcad/moscap1d`, {repo}`results/tcad/moscap2d` and
{repo}`results/tcad/meshconv` to `b30e8944b257734e1b6e481e987d441fda3cef7c0010ec97a53e428aa0b7f4d7`
({py:mod}`gf180tcad.tcad.__main__`), {repo}`results/tcad/calibration` and
{repo}`results/tcad/validation` to `5265e5fe223580d9efd878b9ebe33648b21f36dcdbf41ac8c7092f3ce9925950`
({py:mod}`gf180tcad.calibrate.__main__`). No data file changed. The code that change touched in
the closures is provenance bookkeeping only (the per-entry-point module lists and the
`generator` field in {py:mod}`gf180tcad.tcad`, and the `generator=` argument in both entry
points), nothing that computes a result. No results folder could be regenerated for it: the host's
container budget was taken by another task for hours. The two calibrated 1D jobs, with
{repo}`results/tcad/moscap1d/provenance.json`, are rerun and compared byte for byte by the
`crosscheck-tcad` workflow job ({ref}`cross-host-tcad`), which checks that restamp on every
change to the TCAD code; the other trees have no such check.

**Restamped without regeneration (Task 12).** Under the old scheme the hash covered both entry
points, so a change to a module that a tree's writer never imports still changed that tree's
hash. Task 12 added
{py:mod}`gf180tcad.calibrate` and {py:mod}`gf180tcad.specwindow` to the list, which the 2D MOS
capacitor job imports neither of. The 2D data were therefore **not** regenerated (hours per job):
{repo}`results/tcad/moscap2d/provenance.json <results/tcad/moscap2d/provenance.json>` was
rewritten from generator `8fd11fb03ced74d0fae78c4a84e9b8974d4beff5d8c75e1b41602657ec6d1326`, the
code that made the committed 2D results (Task 11), to the current hash. The same holds for the
whole {repo}`results/tcad/meshconv` folder: its `provenance.json` (1D and 2D) was rewritten, and
its 1D data were last regenerated in 690cf7b. The shared module {py:mod}`gf180tcad.tcad` also
changed since that generator, but only in provenance bookkeeping (the module list,
`VALIDATION_DIR`, `calibrated_devices`), not in anything that computes a result. The
calibration and the validation were rerun at the code they record and compared byte for
byte with the committed files; the 1D {term}`MOS capacitor` results folder is rerun and compared byte for byte
by the sandbox test {test}`tests/tcad/test_moscap1d.py::test_byte_identical`. The 1D
mesh-convergence data were rerun in the sandbox on 2026-10-26 and compared byte for byte with
the committed files by {test}`tests/tcad/test_meshconv.py::test_meshconv_byte_identical`
(passed; the sandbox session of two tests took 3 min 54 s). That test compares the folder's
`provenance.json` without its `moscap2d` image, which a 1D rerun cannot know
([issue #36](https://github.com/mithro/gf180-tcad/issues/36)); the 2D mesh-convergence results
had their provenance updated, not rerun, and have no such evidence. With the per-folder hash ([issue #34](https://github.com/mithro/gf180-tcad/issues/34)) such a
calibration-only change no longer touches these results folders.

(cross-host-determinism)=

## The same bytes on another computer

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

**The whole SPICE reference is cross-checked on GitHub-hosted runners.** The
{repo}`subset file <tests/crosscheck_subset.txt>` holds the single line `all`, which stands
for every job of the reference: both engines, all five corners, both devices and all six
geometries of each, 120 jobs. Each job includes every sweep its engine runs
({term}`idvg_lin`, {term}`idvg_sat`, {term}`idvd`, `ioff` and, for ngspice only, {term}`cv`).
The check covers all 660 CSV and metrics files, the {term}`provenance` file
({repo}`results/spice/provenance.json`) and the {term}`corner envelope`
({repo}`results/spice/envelope.json`).
Nothing of it is checked only locally. The TCAD results are
cross-checked in part ({ref}`cross-host-tcad`).

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
pins, results, project metadata, lock file, Makefile, either subset file, the plugin
submodule, the process files, the TCAD tests or the workflow itself, and also weekly and on
demand. The steps of its SPICE job, `crosscheck`, are:

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

(cross-host-tcad)=

### The TCAD cross-check: `crosscheck-tcad`

A second job of the same workflow, `crosscheck-tcad`, does the same for the {term}`TCAD`
results. It regenerates the jobs of {repo}`tests/crosscheck_tcad_subset.txt`, the calibrated
1D {term}`MOS capacitor` of both devices (`moscap1d/nfet_05v0/calibrated` and
`moscap1d/pfet_05v0/calibrated`), on a GitHub-hosted runner and requires every file to be
byte-identical to the manifest. The jobs rerun exactly the committed configuration: the selected
mesh, the SPICE `cv` gate biases and the committed calibrated values. Its steps are:

1. Free disk space, check out with `submodules: true` (the plugin is imported from
   {repo}`third_party/gplugins <third_party>`, and its commit is recorded in the results folder's provenance),
   and install the sandbox slice as above.
2. Pull, by {term}`digest <manifest digest>`, the image the jobs run in. That is the image of the
   1D results ({py:data}`gf180tcad.tcad.RESULTS_IMAGE`), the {term}`dev-HEAD TCAD image`
   {repo}`docker/TCAD_DEV_IMAGE`, which made the committed files; `tools/crosscheck-tcad-run
   --images` prints it.
3. {repo}`tools/crosscheck-tcad-run` runs each job as the host command that made it,
   `python -m gf180tcad.tcad moscap --device D --dim 1 --params calibrated --out <out>/moscap1d`
   (2 GiB, 1 CPU), one at a time, into a temporary results folder. It refuses an `--out` under
   {repo}`results`.
4. `python -m gf180tcad.manifest verify-subset <out> --kind tcad --against results/MANIFEST.sha256
   --prefix tcad/ --subset tests/crosscheck_tcad_subset.txt`. TCAD jobs are `<tree>/<device>/<params>`
   paths; each results folder the jobs name must have its own `provenance.json`, which is compared (it holds
   the calibration file's sha256 for both devices, which is why both are listed). There is no
   envelope. On success it prints `identical: 5 files of 2 jobs ...`. The first run passed on an AMD EPYC 7763
   ([run](https://github.com/mithro/gf180-tcad/actions/runs/40308867413), 2026-10-26).
5. On failure, the artefact `crosscheck-tcad-differences` holds the generated and committed copy
   of each differing file, their `diff -u`, the logs and the scratch directory of any failed job.

**Checked only locally.** The 1D start values, the calibration and validation, the mesh
convergence and the 2D results are not cross-checked on GitHub-hosted runners. The 2D jobs take
hours at 16 GiB each, more than the runner has. The 1D start-value and calibrated jobs are
rerun byte for byte locally by
{test}`tests/tcad/test_moscap1d.py::test_byte_identical`, and the 1D mesh convergence by
{test}`tests/tcad/test_meshconv.py::test_meshconv_byte_identical`; see {ref}`tcad-provenance`.

## Output cache

Large regenerable files that are not committed, such as the 2D meshes, are kept in a shared,
content-addressed cache repository: {repo}`tools/output-cache` `pull` fetches one and checks it against
the sha256 the committed results name. See {doc}`output-cache`.

```{toctree}
:maxdepth: 1

sandbox
image
output-cache
```
