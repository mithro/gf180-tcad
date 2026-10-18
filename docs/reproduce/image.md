# Base image

The simulators, the {term}`PDK` and the pinned {{ Python }} dependencies live in one
container image,
[`ghcr.io/mithro/gf180-tcad-base`](https://github.com/mithro/gf180-tcad/pkgs/container/gf180-tcad-base)
on the {{ ghcr }}, built from {repo}`docker/base/`. It is based on the public
{{ IIC_OSIC_TOOLS }} image
([`hpretl/iic-osic-tools`](https://hub.docker.com/r/hpretl/iic-osic-tools)`@sha256:306585de35d198e70ea58950f77147c86f56c698726a19afea9f1c83009557be`,
pinned by digest in {repo}`docker/base/Dockerfile`).

(image-pinning)=

## How the image is pinned

Two files commit the identity of the image:

- {repo}`docker/IMAGE` holds the full reference with the **{term}`manifest digest`**
  (`ghcr.io/mithro/gf180-tcad-base@sha256:...`). {repo}`tools/sandbox-run` reads it
  to choose the image to run, so a run always uses exactly that image.
- {repo}`docker/base/IMAGE_ID` holds the image **{term}`config digest`** (the image ID, which
  covers the layer [`diff_id`s](https://github.com/opencontainers/image-spec/blob/main/config.md)).

Tool and PDK {term}`provenance` is recorded in {repo}`docker/base/versions.json`, produced by
{repo}`docker/base/probe_versions.py` run inside the pinned image. The Python
dependencies installed in the image are hash-pinned in
{repo}`docker/base/requirements.lock` and {repo}`docker/base/build-requirements.lock`, which
are exact [`uv export`](https://docs.astral.sh/uv/reference/cli/#uv-export) outputs of
{repo}`uv.lock` ({test}`tests/test_requirements_lock.py::test_requirements_lock_in_sync_with_uv_lock`
checks that they stay in sync).

(image-rebuild)=

## Rebuild and verify

The build is reproducible: it uses a pinned {{ BuildKit }}
([docker-container driver](https://docs.docker.com/build/builders/drivers/docker-container/)),
sets [`SOURCE_DATE_EPOCH`](https://reproducible-builds.org/docs/source-date-epoch/) to the
commit time of the last change to the build inputs ({repo}`~docker/base/Dockerfile` and the two
lock files), turns on
[`rewrite-timestamp`](https://docs.docker.com/build/exporters/image-registry/), disables
[provenance and SBOM attestations](https://docs.docker.com/build/metadata/attestations/) and
builds for one platform (`linux/amd64`).

```
docker/base/build --no-cache
```

({repo}`docker/base/build`) prints the config digest on stdout. It must equal
{repo}`docker/base/IMAGE_ID`. The build refuses to run if the build inputs have uncommitted changes.

The `image` {{ GitHub_Actions }} workflow ({repo}`.github/workflows/image.yml`) checks this
on pull requests and on pushes to `main` (only when `docker/**` or
`image.yml` changes), and weekly and on manual dispatch (always):

1. build, and require the config digest to equal {repo}`docker/base/IMAGE_ID` and the
   manifest digest to equal {repo}`docker/IMAGE`;
2. run the provenance probe inside the pinned image, and require its output to
   equal {repo}`docker/base/versions.json`;
3. rebuild from scratch on a fresh runner (`--no-cache`), and require the
   result to equal the first build and the committed digests.

Pull requests push the tag `pr-<number>`, `main` pushes `latest` and
`sha-<commit>`, each only after the checks above passed (the build itself pushes only the
staging tag `unverified`, which can point at an unverified image) ([package versions](https://github.com/mithro/gf180-tcad/pkgs/container/gf180-tcad-base/versions));
the weekly and manual runs only rebuild and verify. Cross-host byte-identity of the results
is described in {ref}`cross-host-determinism`.

(tcad-image)=

## TCAD image

{term}`TCAD` {term}`jobs <job>` run in a second image,
[`ghcr.io/mithro/gf180-tcad-tcad`](https://github.com/mithro/gf180-tcad/pkgs/container/gf180-tcad-tcad),
built from {repo}`docker/tcad/` **on top of the pinned base image**: its `FROM` is the
reference in {repo}`docker/IMAGE` ({repo}`docker/tcad/build` passes it as `BASE_IMAGE`).
{term}`SPICE` jobs keep using the base image, so the committed SPICE reference does not depend
on it.

It adds a {{ uv }}-managed {{ Python }} 3.13, pinned to an exact patch release (uv checks the
download against the sha256 it embeds for that version), and a venv at `/opt/gf180tcad-tcad`,
first on `PATH`. The venv holds {{ DEVSIM }}, {{ meshwell }}, {{ gmsh }}, {{ gdsfactory }}, the
{{ gf180mcu_gdsfactory }}, {{ scipy }}, {{ pytest }} and the runtime dependencies of
{{ gplugins }}. Python 3.13 is needed because meshwell ≥ 2.4 requires it; the base venv is 3.12.

- **gplugins is not installed.** A `gf180tcad-gplugins.pth` file in the venv puts
  `/work/src/third_party/gplugins` (the submodule of {{ gplugins_fork }}, mounted read-only with the
  repository) on
  `sys.path`. A pure-code plugin change therefore needs no image rebuild; a plugin change that
  adds a dependency does.
- **Environment.** `PDK=gf180mcu`: gdsfactory imports `$PDK` as a module and activates it, so
  the base value (`gf180mcuD`, the {{ open_pdks }} variant) would break it. The open_pdks files
  are still read from `$PDK_ROOT/gf180mcuD`. `PYTHON_CPU_COUNT=1` makes `os.cpu_count()` return 1,
  so meshwell's `n_threads=cpu_count()` defaults keep gmsh single-threaded. The rest of the
  environment (thread variables, `DEVSIM_MATH_LIBS`, `OPENBLAS_CORETYPE`, …) is inherited from
  the base image. {repo}`tools/sandbox-run` also sets the thread variables
  (`OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`) on every run, and it is the
  only source of `NPY_DISABLE_CPU_FEATURES` ({{ numpy }}'s baseline kernels): neither image sets it, so
  a plain `docker run` of the image does not get it.
- **Locks.** The package set is a non-package uv project, {repo}`docker/tcad/pyproject.toml`,
  with its own {repo}`docker/tcad/uv.lock` (which records `exclude-newer`).
  {repo}`docker/tcad/requirements.lock` is its hashed export,
  `uv export --project docker/tcad --frozen --offline --no-emit-project --format requirements-txt --hashes`
  (`--frozen --offline` reads only the lock, so it needs neither Python 3.13 nor the network;
  {repo}`tests/test_tcad_lock.py` runs exactly this command, and it ignores the command line that
  uv echoes into the file's header).
  The gf180mcu package pins `gdsfactory~=9.40`, so it is installed `--no-deps` from its own
  lock, {repo}`docker/tcad/gf180mcu.lock`. uv, and setuptools (the hash-checked build constraint
  for the sdist-only `rectpack`), come from {repo}`docker/tcad/build-requirements.lock`. Both are
  [`uv pip compile`](https://docs.astral.sh/uv/reference/cli/#uv-pip-compile) `--no-deps`
  `--generate-hashes` outputs whose header records the whole command, including
  `--exclude-newer`, so re-running it reproduces them. {repo}`tests/test_tcad_lock.py` checks all
  three, and that numpy equals the base lock's numpy.
- **Pins and provenance.** {repo}`docker/TCAD_IMAGE` holds the reference with the {term}`manifest digest`,
  {repo}`docker/tcad/IMAGE_ID` the config digest and {repo}`docker/tcad/versions.json` the output
  of {repo}`docker/tcad/probe_versions.py` run in the image. {repo}`tests/test_tcad_image.py`
  checks the image itself (its tests run in the {term}`sandbox`).

Run a command in it with

```
tools/sandbox-run --image "$(cat docker/TCAD_IMAGE)" --workdir DIR -- python3 ...
```

or {py:func}`gf180tcad.sandbox.run` with `image=`.

### Rebuild and verify the TCAD image

```
docker/tcad/build --no-cache
```

works like the base build ({ref}`image-rebuild`). Its `SOURCE_DATE_EPOCH` inputs are the
Dockerfile, the three lock files and {repo}`docker/IMAGE`: the base digest is the `FROM`, so it
dates the build. The `image` workflow is a matrix over `{base, tcad}`. Each image has its own
build, `IMAGE_ID`, pinned-manifest and versions-probe checks and its own from-scratch rebuild
job. The TCAD entry pulls the public base image by digest, so scheduled runs need no login.

### Package visibility

New packages on the {{ ghcr }} are private. After the first push of a new package, make it
public, so that the fork CI and the GitHub cross-check can pull it without credentials: on the
package page, choose *Package settings → Change visibility → Public* (see
[configuring a package's visibility](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility)).
Then check the pull with no registry credentials:

```
DOCKER_CONFIG="$(mktemp -d)" docker pull "$(cat docker/TCAD_IMAGE)"
```

### Changing the base image

The TCAD image, its digests and every TCAD result depend on {repo}`docker/IMAGE`, so a change of
the base image updates both images in **one** pull request:

1. Change the base, rebuild it locally twice, and commit the new {repo}`docker/base/IMAGE_ID`,
   {repo}`docker/base/versions.json` and the predicted {repo}`docker/IMAGE`; CI pushes the base.
   Until step 3, the TCAD checks fail (its `versions.json` names the old base, and its digests
   change), and so does `lint-test`.
2. Rebuild the TCAD image locally (twice, `--no-cache`) FROM the pushed base, and commit the new
   {repo}`docker/tcad/IMAGE_ID` and {repo}`docker/tcad/versions.json`.
3. CI pushes the TCAD image; commit {repo}`docker/TCAD_IMAGE` (its manifest digest).
4. Regenerate any TCAD results in the new image and commit them.
5. Merge only when every check is green.

On the first push of step 1, the TCAD entry can also fail to pull a base that the base entry has
not pushed yet (the two entries run in parallel). That failure is expected; it goes away on
the next push, or with a re-run of the failed job once the base is pushed. The from-scratch
rebuild of each entry runs even when the other entry failed.
