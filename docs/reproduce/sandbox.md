# Resource sandbox

Every simulator run goes through `tools/sandbox-run` (or the Python wrapper
`gf180tcad.sandbox.run`). Nothing is run directly on the host.

(sandbox-host-setup)=

## One-time host setup

`tools/sandbox-setup` (idempotent, needs `sudo`) installs the systemd unit
`/etc/systemd/system/gf180-tcad.slice` and reloads systemd. The slice caps the
**aggregate** resources of all sandbox containers together:

| Setting | Value | Meaning |
|---|---|---|
| `MemoryMax` | `128G` | all sandbox containers together, never more than 128 GiB |
| `MemorySwapMax` | `0` | the slice itself never swaps |
| `TasksMax` | `32768` | all sandbox containers together, at most 32768 tasks |

(sandbox-per-run-limits)=

## Per-run limits

`tools/sandbox-run [--mem 16g] [--cpus 8] [--pids 4096] [--image REF] --workdir DIR [--network none|bridge] -- CMD...`
starts `CMD` in a Docker container with these defaults:

| Limit | Default | Option |
|---|---|---|
| Memory | 16 GiB, no swap (`--memory-swap` set equal to `--memory`) | `--mem` |
| CPUs | 8 | `--cpus` |
| Processes | 4096 | `--pids` |
| Network | `--network=none` (no network at all) | `--network bridge` to opt in |
| Cgroup parent | `gf180-tcad.slice` | fixed |

Other properties of the container:

- the root filesystem is read-only, with a 1 GiB `tmpfs` at `/tmp`;
- the repository checkout is mounted read-only at `/work/src`, and project
  code is run from it with `PYTHONPATH=/work/src/src`; it is not baked into the
  image;
- the working directory, which must exist and must not be the repository or
  inside it, is mounted read-write at `/work/out`;
- the process runs as the host user's UID and GID, with `HOME=/tmp/home`;
- `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` and `MKL_NUM_THREADS` are set to
  `1` for determinism;
- the image defaults to the one pinned in `docker/IMAGE` (see
  {doc}`image`); `--image` overrides it.

(sandbox-failure-behaviour)=

## Failure behaviour

The exit code is that of `CMD`. A job that exceeds its memory limit is
OOM-killed and the run exits with **137**, which `gf180tcad.sandbox.run`
raises as `SandboxOOM`; it is reported as a failure and other jobs are
unaffected. Interrupting `sandbox-run` (SIGINT or SIGTERM) removes the
container before exiting.
