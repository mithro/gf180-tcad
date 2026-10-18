# Resource sandbox (stub)

Every simulator run goes through `tools/sandbox-run` (or `gf180tcad.sandbox.run`). It runs the
pinned image (`docker/IMAGE`) in a Docker container with: memory limit (swap = memory, default
16g), 8 CPUs, 4096 PIDs, `--network=none` (opt-in `--network bridge`), read-only root, 1 GiB
tmpfs `/tmp`, repo mounted read-only at `/work/src`, output dir at `/work/out`, host UID:GID,
and the cgroup parent `gf180-tcad.slice` (aggregate 128 GiB, no swap). OOM kills exit 137 and
raise `SandboxOOM`. Project code is not baked into the image: `PYTHONPATH=/work/src/src` runs it
from the mounted checkout with the image's `/opt/gf180tcad` venv.

The image (`ghcr.io/mithro/gf180-tcad-base`, `docker/base/`) is built reproducibly by
`docker/base/build` (pinned BuildKit, `SOURCE_DATE_EPOCH`, `rewrite-timestamp`); its config
digest is committed in `docker/base/IMAGE_ID` and CI rebuilds it from scratch to check that.
Tool and PDK provenance is in `docker/base/versions.json` (`docker/base/probe_versions.py`).

One-time host setup (needs sudo): `tools/sandbox-setup`.

Full documentation is added in a later task.
