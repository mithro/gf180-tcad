# Base image

The simulators, the PDK and the pinned Python dependencies live in one
container image, `ghcr.io/mithro/gf180-tcad-base`, built from `docker/base/`. It
is based on the public IIC-OSIC-TOOLS image
(`hpretl/iic-osic-tools@sha256:306585de35d198e70ea58950f77147c86f56c698726a19afea9f1c83009557be`,
pinned by digest in `docker/base/Dockerfile`).

## How the image is pinned

Two files commit the identity of the image:

- `docker/IMAGE` holds the full reference with the **manifest digest**
  (`ghcr.io/mithro/gf180-tcad-base@sha256:...`). `tools/sandbox-run` reads it
  to choose the image to run, so a run always uses exactly that image.
- `docker/base/IMAGE_ID` holds the image **config digest** (the image ID, which
  covers the layer `diff_id`s).

Tool and PDK provenance is recorded in `docker/base/versions.json`, produced by
`docker/base/probe_versions.py` run inside the pinned image. The Python
dependencies installed in the image are hash-pinned in
`docker/base/requirements.lock` and `docker/base/build-requirements.lock`, which
are exact `uv export` outputs of `uv.lock` (a test checks that they stay in
sync).

## Rebuild and verify

The build is reproducible: it uses a pinned BuildKit (docker-container driver),
sets `SOURCE_DATE_EPOCH` to the commit time of the last change to the build
inputs (`Dockerfile` and the two lock files), turns on `rewrite-timestamp`,
disables provenance and SBOM attestations and builds for one platform
(`linux/amd64`).

```
docker/base/build --no-cache
```

prints the config digest on stdout. It must equal `docker/base/IMAGE_ID`. The
build refuses to run if the build inputs have uncommitted changes.

The `image` GitHub Actions workflow (`.github/workflows/image.yml`) checks this
on pull requests, on pushes to `main`, weekly, and on manual dispatch:

1. build, and require the config digest to equal `docker/base/IMAGE_ID` and the
   manifest digest to equal `docker/IMAGE`;
2. run the provenance probe inside the pinned image, and require its output to
   equal `docker/base/versions.json`;
3. rebuild from scratch on a fresh runner (`--no-cache`), and require the
   result to equal the first build and the committed digests.

Pull requests push the tag `pr-<number>`, `main` pushes `latest` and
`sha-<commit>`; the weekly and manual runs only rebuild and verify.
