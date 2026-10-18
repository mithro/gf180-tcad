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
pinned image (see {doc}`image`); 120 jobs take a few minutes with the default
8 concurrent jobs (`make reproduce JOBS=16` runs more at once).

After an intended change to the results, regenerate them and rewrite the
manifest with:

```sh
make manifest
```

## Running part of the reference

`make reproduce` is a wrapper around:

```sh
uv run python -m gf180tcad spice-reference \
    [--engine ngspice|xyce|both] [--corner C ...] [--device D ...] \
    [--jobs N] --out results/spice
```

`--corner` (`typical`, `ff`, `ss`, `fs`, `sf`) and `--device` (`nfet_05v0`,
`pfet_05v0`) can be repeated; the default is all of them, and `--engine`
defaults to `both`. For example, a single device at one corner:

```sh
uv run python -m gf180tcad spice-reference --engine ngspice \
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
  and swapped into place only when every job succeeded. If any job fails,
  `--out` is left as it was, the failures are listed and the command exits
  non-zero.
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
  of `src/gf180tcad/**/*.py`. There is deliberately no git commit and no date,
  so a regeneration on any machine gives the same bytes. Any change to the
  generator code changes `generator_sha256`, and so the reference has to be
  regenerated (and the manifest updated) together with such a change.

Generation never compares the two engines. Each engine's results are
published as they are; the ngspice/Xyce cross-check is a separate test,
described in {doc}`../limitations/engine-cross-check`.

```{toctree}
:maxdepth: 1

sandbox
image
```
