# Resource sandbox

Every simulator run goes through the {term}`sandbox` {repo}`tools/sandbox-run` (or the {{ Python }}
wrapper {py:func}`gf180tcad.sandbox.run`). Nothing is run directly on the host.

(sandbox-host-setup)=

## One-time host setup

{repo}`tools/sandbox-setup` (idempotent, needs `sudo`) installs the {{ systemd }}
[slice unit](https://www.freedesktop.org/software/systemd/man/latest/systemd.slice.html)
`/etc/systemd/system/gf180-tcad.slice` and reloads systemd. The {term}`slice` caps the
**aggregate** resources of all sandbox containers together
([resource control](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html)):

| Setting | Value | Meaning |
|---|---|---|
| [`MemoryMax`](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html#MemoryMax=bytes) | `128G` | all sandbox containers together, never more than 128 GiB |
| [`MemorySwapMax`](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html#MemorySwapMax=bytes) | `0` | the slice itself never swaps |
| [`TasksMax`](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html#TasksMax=N) | `32768` | all sandbox containers together, at most 32768 tasks |

(sandbox-per-run-limits)=

## Per-run limits

{repo}`tools/sandbox-run` takes

```sh
tools/sandbox-run [--mem 16g] [--cpus 8] [--pids 4096] [--image REF] --workdir DIR [--network none|bridge] -- CMD...
```

and starts `CMD` in a {{ Docker }} container ({{ docker_run }}) with these defaults:

| Limit | Default | Option |
|---|---|---|
| Memory | 16 GiB, no swap ([`--memory-swap`](https://docs.docker.com/reference/cli/docker/container/run/#memory) set equal to `--memory`) | `--mem` |
| CPUs | 8 | `--cpus` |
| Processes | 4096 | `--pids` |
| Network | [`--network=none`](https://docs.docker.com/reference/cli/docker/container/run/#network) (no network at all) | `--network bridge` to opt in |
| {term}`Cgroup <cgroup>` parent | [`gf180-tcad.slice`](https://docs.docker.com/reference/cli/docker/container/run/#cgroup-parent) | fixed |

Before starting the container, {repo}`tools/sandbox-run` refuses to run (exit 2) when

- the working directory is not allowed (see the list below);
- `gf180-tcad.slice` does not have the limits of {ref}`sandbox-host-setup`: it reads
  `systemctl show gf180-tcad.slice -p MemoryMax,MemorySwapMax,TasksMax` and requires exactly
  `MemoryMax=137438953472` (128 GiB), `MemorySwapMax=0` and `TasksMax=32768`. Without
  {repo}`tools/sandbox-setup`, Docker would create the slice on the fly with no limits at all.

Other properties of the container:

- all Linux [capabilities](https://man7.org/linux/man-pages/man7/capabilities.7.html) are
  dropped ([`--cap-drop ALL`](https://docs.docker.com/engine/containers/run/#runtime-privilege-and-linux-capabilities))
  and privilege escalation is off
  ([`--security-opt no-new-privileges`](https://docs.docker.com/reference/cli/docker/container/run/#security-opt));
- the root filesystem is [read-only](https://docs.docker.com/reference/cli/docker/container/run/#read-only),
  with a 1 GiB [`tmpfs`](https://docs.docker.com/reference/cli/docker/container/run/#tmpfs) at
  `/tmp`;
- the repository checkout is mounted read-only at `/work/src`
  ({py:data}`gf180tcad.sandbox.SOURCE_MOUNT`), and project
  code is run from it with `PYTHONPATH=/work/src/src`; it is not baked into the
  image;
- the working directory is mounted read-write at `/work/out`. It must exist and must not be
  the filesystem root, `$HOME` or an ancestor of it, the repository, a directory inside it, or
  an ancestor of it (a container able to write the repository's `.git`, for example its hooks,
  would escape the sandbox). Unrelated directories are fine: scratch directories under
  `$TMPDIR`, or sibling checkouts next to the repository;
- the process runs as the host user's UID and GID, with `HOME=/tmp/home`;
- `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` and `MKL_NUM_THREADS` are set to
  `1` for determinism;
- [`NPY_DISABLE_CPU_FEATURES`](https://numpy.org/doc/stable/reference/simd/build-options.html#runtime-dispatch)
  disables every {{ numpy }} {term}`SIMD dispatch` target, so every {term}`x86-64-v2` host
  runs the same baseline kernels and computes the same bits ({ref}`cross-host-determinism`);
- `GF180TCAD_IN_SANDBOX=1` ({py:data}`gf180tcad.sandbox.IN_SANDBOX_ENV`) marks the process as
  sandboxed; see {ref}`sandbox-direct-mode`;
- the image defaults to the one pinned in {repo}`docker/IMAGE` (see
  {doc}`image`); `--image` overrides it.

(sandbox-direct-mode)=

## Inside the sandbox: direct mode

Code that already runs in a sandbox container (a `spice-job` runs its simulators from there)
has no Docker, so {py:func}`gf180tcad.sandbox.run` then runs the command directly, in the
working directory, under the enclosing container's limits. The marker alone never enables
this: {py:func}`gf180tcad.sandbox.check_confined` must also prove the process is confined
(`/.dockerenv` exists, the {term}`cgroup` `memory.max` and `pids.max` are finite,
`/work/src` is mounted read-only, and no network interface but `lo` exists), else
{py:class}`~gf180tcad.sandbox.SandboxNotConfined` is raised and nothing runs. The working
directory follows the same rules as above ({py:func}`gf180tcad.sandbox.check_workdir`).

(sandbox-failure-behaviour)=

## Failure behaviour

The exit code is that of `CMD`. A {term}`job` that exceeds its memory limit is
{term}`OOM`-killed and the run exits with **137** ({py:data}`gf180tcad.sandbox.OOM_EXIT`),
which {py:func}`gf180tcad.sandbox.run` raises as {py:class}`~gf180tcad.sandbox.SandboxOOM`;
it is reported as a failure and other jobs are unaffected. Interrupting
{repo}`sandbox-run <tools/sandbox-run>` (SIGINT or SIGTERM) removes the container before
exiting.
