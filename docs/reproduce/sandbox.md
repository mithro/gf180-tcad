# Resource sandbox (stub)

Every simulator run goes through `tools/sandbox-run` (or `gf180tcad.sandbox.run`). It runs the
pinned image (`docker/IMAGE`) in a Docker container with: memory limit (swap = memory, default
16g), 8 CPUs, 4096 PIDs, `--network=none` (opt-in `--network bridge`), read-only root, 1 GiB
tmpfs `/tmp`, repo mounted read-only at `/work/src`, output dir at `/work/out`, host UID:GID,
and the cgroup parent `gf180-tcad.slice` (aggregate 128 GiB, no swap). OOM kills exit 137 and
raise `SandboxOOM`.

One-time host setup (needs sudo): `tools/sandbox-setup`.

Full documentation is added in a later task.
