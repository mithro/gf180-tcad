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
on pull requests and on pushes to `main` (only when {repo}`docker/` or
{repo}`image.yml <.github/workflows/image.yml>` changes), and weekly and on manual dispatch (always):

1. build, and require the config digest to equal {repo}`docker/base/IMAGE_ID` and the
   manifest digest to equal {repo}`docker/IMAGE`;
2. run the provenance probe inside the pinned image, and require its output to
   equal {repo}`docker/base/versions.json`;
3. rebuild from scratch on a fresh runner (`--no-cache`), and require the
   result to equal the first build and the committed digests.

Pull requests push the tag `pr-<number>`; `main` pushes `latest` and `sha-<commit>`. Each
of these is pushed only after the checks above passed
([package versions](https://github.com/mithro/gf180-tcad/pkgs/container/gf180-tcad-base/versions)).
The build itself pushes only the staging tag `unverified`, which can point at an image that has
not passed the checks. The weekly and manual runs only rebuild and verify. Whether the results are the same bytes on
another computer is described in {ref}`cross-host-determinism`.

(tcad-image)=

## TCAD image

{term}`TCAD` {term}`jobs <job>` run in a second image,
[`ghcr.io/mithro/gf180-tcad-tcad`](https://github.com/mithro/gf180-tcad/pkgs/container/gf180-tcad-tcad),
built from {repo}`docker/tcad/` **on top of the pinned base image**: its `FROM` is the
reference in {repo}`docker/IMAGE` ({repo}`docker/tcad/build` passes it as `BASE_IMAGE`).
{term}`SPICE` jobs keep using the base image, so the committed {term}`SPICE reference <SPICE reference results>` does not depend
on it.

This is the {term}`stable TCAD image`, with the latest PyPI releases of the TCAD stack. The
{term}`dev-HEAD TCAD image` ({ref}`tcad-dev-image`) has the same structure with each project at its
upstream development HEAD; it is the stack of the final results, and this one is the baseline
for how things used to work and for debugging.

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

works like the base build ({ref}`image-rebuild`). Its `SOURCE_DATE_EPOCH` inputs are
{repo}`docker/tcad/Dockerfile`, the three lock files and {repo}`docker/IMAGE`: the base digest is the `FROM`, so it
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
   Until step 3, the TCAD checks fail ({repo}`docker/tcad/versions.json` names the old base, and its digests
   change), and so does `lint-test`.
2. Rebuild the TCAD image locally (twice, `--no-cache`) FROM the pushed base, and commit the new
   {repo}`docker/tcad/IMAGE_ID` and {repo}`docker/tcad/versions.json`.
3. CI pushes the TCAD image; commit {repo}`docker/TCAD_IMAGE` (its manifest digest).
4. Regenerate any TCAD results in the new image and commit them.
5. Merge only when every check is green.

On the first push of step 1, the TCAD entry can also fail to pull a base that the base entry has
not pushed (the two entries run in parallel). That failure is expected; it goes away on
the next push, or with a re-run of the failed job once the base is pushed. The from-scratch
rebuild of each entry runs even when the other entry failed.

(tcad-dev-image)=

## Dev-HEAD TCAD image

There are two TCAD images. They share the base image, the {{ Python }} 3.13 patch release and
the venv path, and differ only in where the TCAD stack comes from:

- the {term}`dev-HEAD TCAD image`,
  [`ghcr.io/mithro/gf180-tcad-tcad-dev`](https://github.com/mithro/gf180-tcad/pkgs/container/gf180-tcad-tcad-dev),
  pinned by {repo}`docker/TCAD_DEV_IMAGE` and built from {repo}`docker/tcad-dev/`, has
  {{ DEVSIM }}, {{ meshwell }}, {{ gdsfactory }}, the {{ gf180mcu_gdsfactory }} and {{ gmsh }} at
  their development HEADs (meshwell and gf180mcu from mithro forks of upstream HEAD, see
  {ref}`tcad-dev-forks`). **It is the stack of the final results;**
- the {term}`stable TCAD image` ({ref}`tcad-image`, {repo}`docker/TCAD_IMAGE`) has their latest
  [PyPI](https://pypi.org/) releases. It is kept as the baseline for "how it used to work" and for debugging: a
  difference between the two images is a change upstream, not in this project.

The 1D TCAD results are generated in the dev-HEAD image and the 2D results in the
stable image; see {ref}`tcad-results-image`.

**Sources, pinned by commit.** {repo}`docker/tcad-dev/upstream.json` records each project's
repository, default branch, the HEAD commit when the image was pinned and that commit's date
(for a fork also the upstream repository and the upstream commit the fork is based on), its
licence, the URL it is fetched from, its mirror URL and that file's sha256. The build fetches
every input at build time, inside the {{ Docker }} build, and fails if a hash differs
({ref}`tcad-dev-mirror`). GitHub
projects are the tarballs of exactly their commit (`codeload.github.com/<owner>/<repo>/tar.gz/<sha>`,
or `github.com/<owner>/<repo>/archive/<sha>.tar.gz`, which redirects there). The Python
dependencies that are not themselves dev HEADs come from a new lock resolved against the dev
packages' own requirements, as for the stable image ({repo}`docker/tcad-dev/pyproject.toml`,
{repo}`docker/tcad-dev/uv.lock`, exported with hashes to {repo}`docker/tcad-dev/requirements.lock`;
{{ uv }} records the sha256 of the URL sources too, so every sdist and wheel is hash-checked).
{repo}`tests/test_tcad_dev_lock.py` checks that the locks reproduce and agree with
{repo}`docker/tcad-dev/upstream.json` and {repo}`docker/tcad-dev/wheelhouse.json`.

- **DEVSIM** is compiled from source by {repo}`docker/tcad-dev/build-devsim.sh`, following
  DEVSIM's own x86_64 release recipe
  ([`scripts/build_manylinux_2_28.sh`](https://github.com/devsim/devsim/blob/ec9905bbfdfacaf66e0cae7f2d98748f9bb8aeb0/scripts/build_manylinux_2_28.sh)):
  extended precision with the quad-precision
  [`getrf`](https://github.com/devsim/devsim/tree/ec9905bbfdfacaf66e0cae7f2d98748f9bb8aeb0/external/getrf) (DEVSIM's copy of the
  [LAPACK](https://www.netlib.org/lapack/) routine, compiled at quad precision),
  [symdiff](https://github.com/devsim/symdiff) and
  [umfpack_lgpl](https://github.com/devsim/umfpack_lgpl) at the commits of DEVSIM's submodules,
  and BLAS/LAPACK loaded at run time from the base image's
  {repo}`DEVSIM_MATH_LIBS <docker/base/Dockerfile#L42>` (the system
  [OpenBLAS](https://www.openblas.net/)), as in the stable image. Upstream compiles its x86_64
  wheels with [GCC](https://gcc.gnu.org/) 14 (the
  [gcc-toolset-14](https://github.com/pypa/manylinux#manylinux_2_28-almalinux-8-based) of
  [manylinux_2_28](https://github.com/pypa/manylinux)); the base image has only GCC 13 and no
  Fortran compiler, which the quad-precision `getrf` needs. So Ubuntu 24.04's
  [GCC 14.2 packages](https://launchpad.net/ubuntu/noble/+source/gcc-14) (C, C++ and Fortran;
  the build whose run-time libraries the base image already has) are unpacked into a throwaway
  build stage only (from [snapshot.ubuntu.com](https://snapshot.ubuntu.com/), hash-pinned).
  With the base image's GCC 13.3 instead, the build works but the DEVSIM it makes raises
  "Uncaught FPE" errors in 13 tests of {{ gplugins_fork }} that pass with the
  [PyPI wheel](https://pypi.org/project/devsim/2.11.1/) and with this GCC 14 build. The
  root cause is not established:
  [`FE_INVALID`](https://pubs.opengroup.org/onlinepubs/9799919799/basedefs/fenv.h.html) is raised in
  [CPython](https://github.com/python/cpython)'s `_Py_dg_dtoa` (float to string, reached from
  DEVSIM's argument handling) and surfaced by DEVSIM's per-command FPE check
  ([`FPECheck`](https://github.com/devsim/devsim/blob/ec9905bbfdfacaf66e0cae7f2d98748f9bb8aeb0/src/utility/FPECheck.hh));
  the GCC 14 and PyPI builds do not take that path. The new build record shows the same
  `devsim_py3.so` (sha256 `32cd805c…b874`) as the first GCC 14 pin, built from the same commit.
  The re-runnable evidence (build, wheel swap, gdb trap, compiler swap) is
  {repo}`experiments/devsim-gcc13-fpe/`.
  The image itself is the
  base plus a copy of the venv and the uv-managed CPython: no compiler, source tree or download
  is left in it ({test}`tests/test_tcad_dev_image.py::test_tcad_dev_no_bytecode_and_no_compiler`).
  The build also writes DEVSIM's build record (the commit, the sha256 of `devsim_py3.so` and the
  compilers in its [ELF](https://refspecs.linuxfoundation.org/elf/gabi4+/ch4.sheader.html)
  `.comment` section); the probe checks the installed module against it and
  reports it as `devsim_build` in {repo}`docker/tcad-dev/versions.json`
  ({test}`tests/test_tcad_dev_image.py::test_tcad_dev_versions_json_devsim_build`). The wheel's
  own `VERSION` file names the commit too, but
  [DEVSIM's wheel recipe](https://github.com/devsim/devsim/blob/ec9905bbfdfacaf66e0cae7f2d98748f9bb8aeb0/dist/bdist_wheel/setup.py)
  does not package it.
- **meshwell**, **gdsfactory** and **gf180mcu** are built from their commit tarballs (meshwell
  and gf180mcu: of {{ meshwell_fork }} and {{ gf180mcu_fork }}). meshwell takes its version
  from git through [hatch-vcs](https://github.com/ofek/hatch-vcs), which a tarball cannot
  give, so the build passes the version hatch-vcs reports at that commit (counted from
  upstream's [`v2.5.2`](https://github.com/simbilod/meshwell/releases/tag/v2.5.2) tag).
- **gmsh** is the dated development snapshot wheel that gmsh publishes at a fixed URL
  ([gmsh.info/python-packages-dev](https://gmsh.info/python-packages-dev/gmsh/)); the wheel
  reports the git revision of [gmsh `master`](https://gitlab.onelab.info/gmsh/gmsh) it was built
  from, and {repo}`docker/tcad-dev/upstream.json` records that commit.

**Pins and provenance.** As for the stable image: {repo}`docker/TCAD_DEV_IMAGE` holds the
{term}`manifest digest`, {repo}`docker/tcad-dev/IMAGE_ID` the {term}`config digest` and
{repo}`docker/tcad-dev/versions.json` the output of {repo}`docker/tcad-dev/probe_versions.py`
run in the image. It has every key of the stable probe, plus `upstream`, the source list that the
image carries, after the probe has checked it against the URL each package was installed from
and the git revision gmsh reports, plus `devsim_build` (above). {repo}`tests/test_tcad_dev_image.py`
checks the image itself.
Run a command in it with

```
tools/sandbox-run --image "$(cat docker/TCAD_DEV_IMAGE)" --workdir DIR -- python3 ...
```

(tcad-dev-forks)=

### Forks, and why

When the image was first pinned (2026-10-19), three upstream problems kept the full flow from
running in it. They were recorded as {term}`strict expected failures <strict expected failure>`
and are now fixed. Each fix lives in a fork under
[github.com/mithro](https://github.com/mithro), on a `gf180/<topic>` branch merged into the
fork's `main` by pull request. Upstream is read only: no pull requests, issues or comments are
made there. Each fork keeps its upstream licence, says at the top of its README that it is a
fork and why, and runs CI on {{ GitHub_hosted_runner }}s with no secrets and no publishing
workflows.

Each fork, at its commit, and where it enters the flow are drawn in {numref}`image-forks`.

```{figure} /_generated/reproduce/image-forks-light.svg
:name: image-forks
:figclass: only-light
:alt: Boxes in two columns. Left, the three forks, each with its commit and, for two of them, the fix it carries. Right, the dev-HEAD TCAD image, which two forks enter, and the plugin submodule, which the third enters.

The forks at their commits (left) and where each enters the flow (right). The two that the
dev-HEAD image builds, with their fixes, come from {repo}`docker/tcad-dev/upstream.json`. The
plugin fork is the submodule of {repo}`.gitmodules`, at the commit that
{repo}`results/tcad/moscap1d/provenance.json` records.
```

```{figure} /_generated/reproduce/image-forks-dark.svg
:figclass: only-dark
:alt: Boxes in two columns. Left, the three forks, each with its commit and, for two of them, the fix it carries. Right, the dev-HEAD TCAD image, which two forks enter, and the plugin submodule, which the third enters.

The forks at their commits (left) and where each enters the flow (right). The two that the
dev-HEAD image builds, with their fixes, come from {repo}`docker/tcad-dev/upstream.json`. The
plugin fork is the submodule of {repo}`.gitmodules`, at the commit that
{repo}`results/tcad/moscap1d/provenance.json` records.
```

- **{{ gf180mcu_fork }}** (Apache-2.0), main
  [`9342e3e`](https://github.com/mithro/gf180mcu/commit/9342e3e1804e419ba4d3a252746fe688657a9b74)
  = upstream [`96b7324`](https://github.com/gdsfactory/gf180mcu/commit/96b7324d85df05704f68c1370c175627d0a88034)
  plus [mithro/gf180mcu#4](https://github.com/mithro/gf180mcu/pull/4).
  - **Problem.** gf180mcu did not import with gdsfactory's HEAD (10.0.0rc0). Its
    [`tech.py`](https://github.com/gdsfactory/gf180mcu/blob/96b7324d85df05704f68c1370c175627d0a88034/gf180mcu/tech.py)
    built every gdsfactory `CrossSection` at import, to learn its default name. From gdsfactory 10, the
    layer lookup that this needs activates the PDK named by `PDK=gf180mcu`, which is the
    half-imported module itself.
  - **Fix.** The `CrossSection` objects are now built on first use.
  - **Pin.** Relaxed to `gdsfactory>=9.45,<11`. gf180mcu is therefore an ordinary part of
    {repo}`docker/tcad-dev/uv.lock` and is no longer installed `--no-deps`.
  - **Checks in the fork.** The fork's own tests,
    [`tests/test_gf180tcad_gdsfactory10.py`](https://github.com/mithro/gf180mcu/blob/9342e3e1804e419ba4d3a252746fe688657a9b74/tests/test_gf180tcad_gdsfactory10.py) at `9342e3e`, run in its CI under
    gdsfactory 9.51.0 and 10.0.0rc0. They import gf180mcu in a fresh interpreter, with and
    without `PDK`, and compare `nfet`/`pfet(volt="5.0V")` with {term}`GDS` written by upstream
    `96b7324` under gdsfactory 9.51.0: identical bytes under 9.51.0, an empty XOR under 10.
  - **Check here.** {test}`tests/test_tcad_dev_image.py::test_tcad_dev_gf180mcu_pdk` imports
    gf180mcu in the dev image and checks that `PDK=gf180mcu` activates it.
- **{{ meshwell_fork }}** (GPL-3.0-or-later, as its
  [`CITATION.cff`](https://github.com/simbilod/meshwell/blob/b6d5ccd5293312e99c91686cd6f010ca7bda5e15/CITATION.cff)
  states), main
  [`4184d31`](https://github.com/mithro/meshwell/commit/4184d3138e80c3b0b365aee615a07adf7f9f8ac5)
  = upstream [`b6d5ccd`](https://github.com/simbilod/meshwell/commit/b6d5ccd5293312e99c91686cd6f010ca7bda5e15)
  plus [mithro/meshwell#1](https://github.com/mithro/meshwell/pull/1).
  - **Problem.** {{ meshio }} 5.3.5 could not read back meshwell's meshes. gmsh 5 writes
    [MSH](https://gmsh.info/doc/texinfo/gmsh.html#MSH-file-format) 4.2 by default (gmsh commit
    [`f3306764`](https://gitlab.onelab.info/gmsh/gmsh/-/commit/f3306764674df314a01200f02486230460cfd5d6)).
    MSH 4.2 adds a list of embedded entities to every `$Entities` record (gmsh
    [`51eba072`](https://gitlab.onelab.info/gmsh/gmsh/-/commit/51eba072c)). meshio's MSH 4.1
    reader ([`_gmsh41.py`](https://github.com/nschloe/meshio/blob/v5.3.5/src/meshio/gmsh/_gmsh41.py)
    at v5.3.5) does not expect that field, misreads the records that follow it, and fails with a
    `KeyError` on a curve tag. No entity is actually missing.
  - **Fix.** meshwell writes MSH 4.1, gmsh 4's default, unless the caller asks for another
    version. Its own meshio read-backs always use 4.1.
  - **Checks in the fork.** The fork's
    [`tests/test_gf180tcad_msh_readback.py`](https://github.com/mithro/meshwell/blob/4184d3138e80c3b0b365aee615a07adf7f9f8ac5/tests/test_gf180tcad_msh_readback.py) at `4184d31` runs in its CI under gmsh
    4.15.2 and the gmsh 5 snapshot. It checks that two 2D scenes (a square, and two layers with
    an interface) read back under gmsh 5 exactly as under gmsh 4.15.2: node count, every cell
    block, and the physical groups. Upstream's own suite, run locally, fails the same 27 tests
    (all missing generated references) under gmsh 4.15.2 and under gmsh 5, against 155 before
    the fix.
  - **Check here.** {test}`tests/test_tcad_dev_image.py::test_tcad_dev_meshwell_mesh_reads_back`
    reads meshwell's square back in the dev image and asserts its point count, cell blocks,
    `field_data` and `cell_sets`. These are the same values that
    {test}`tests/test_tcad_image.py::test_meshwell_mesh_reads_back` asserts in the stable image
    (gmsh 4.15.2), so the two images are compared.
- **{{ gplugins_fork }}** (MIT), [mithro/gplugins#10](https://github.com/mithro/gplugins/pull/10).
  - **Problem.** The fork's PN-slab test
    ([`test_mesh.py`](https://github.com/mithro/gplugins/blob/408d0af89c6691e78e03b4d7e75b6dcccc74ee99/gplugins/devsim/tests/test_mesh.py) at `408d0af`) checked that the v0.8.0-topology rib floats
    by requiring `boundary_jump_v > 0.05` V. That is the size of the rib's arbitrary offset,
    which only the mesh and the initial guess set: 0.118 V with gmsh 4.15.2 and 0.035 V with
    gmsh 5 at mesh ×1.
  - **Fix.** The test now checks the mesh-independent invariant. Between bias steps only the slab
    moves, so the signed core − slab jump at the rib's right bottom vertex changes by exactly the
    step of the contact potential difference (−0.1 V) and at the left one by 0. Both hold to
    1e-3 V at mesh ×1 and ×0.5; the fork test records them as measured to 1e-15 V
    ([`RIB_JUMP_TOL_V`](https://github.com/mithro/gplugins/blob/1c071d0565ef4917b48ff907b9426e879ccca7fc/gplugins/devsim/tests/test_mesh.py#L48)). This is a
    stronger check: it fails for a coupled rib.
  - **Check here.**
    {test}`tests/test_tcad_dev_image.py::test_tcad_dev_fork_pn_slab_currents_explained` runs
    that fork test in the dev image and requires it to pass. The fork test is the one that holds
    the invariant. It runs from a [`git archive`](https://git-scm.com/docs/git-archive) of the submodule pin,
    {repo}`third_party/gplugins <.gitmodules>` at
    [`0715c81`](https://github.com/mithro/gplugins/commit/0715c81c4439533512621a97358d9d779411ebf6),
    the commit the committed results are made with.

**The full flow runs in the current dev image** (2026-10-24, image {term}`config digest` `b4bae2b3…`,
{term}`manifest digest` `fe347528…`, with the submodule pinned at gplugins `1c071d0`):

- the 42 sandbox tests of {repo}`tests/tcad`, {repo}`tests/test_tcad_dev_image.py` and
  {repo}`tests/test_tcad_image.py` pass;
- the 1D {term}`MOS capacitor <MOSCAP>` and mesh-convergence results folders regenerated in the dev image
  are byte-identical to the committed {repo}`results/tcad/moscap1d` and
  {repo}`results/tcad/meshconv` results folders. Only their provenance files
({repo}`results/tcad/moscap1d/provenance.json`, {repo}`results/tcad/meshconv/provenance.json`), which name the
  image, differs;
- the drift guard, {test}`tests/tcad/test_moscap1d.py::test_stable_and_dev_images_agree`, passes:
  the stable and dev images give the same bytes.

The fork's own suite was last counted on the **previous** dev image (config `245963e5…`, on
2026-10-19), at gplugins `408d0af`: its `gplugins/devsim` and `gplugins/process` tests gave
131 passed in the dev image and 131 passed in the stable image. It was not recounted on the
current image at `1c071d0`; the PN-slab test of it runs in the sandbox tests above.

So no numeric drift was found against the stable image. DEVSIM's `devsim_py3.so` is also
byte-identical to the first GCC 14 pin's.

(tcad-results-image)=

### Which image makes which results

The final results come from upstream dev HEAD; the stable image is for testing how things used
to work, and for debugging. {py:data}`gf180tcad.tcad.RESULTS_IMAGE` names the image each result
kind is generated with, and it is the default of `python -m gf180tcad.tcad moscap` and
`meshconv` ({py:mod}`gf180tcad.tcad.__main__`); `--image dev|stable` picks the other one.

| results | image | why |
|---|---|---|
| 1D {term}`MOS capacitor <MOSCAP>`, {repo}`results/tcad/moscap1d` | dev HEAD, {repo}`docker/TCAD_DEV_IMAGE` | the stack of the final results |
| 1D {term}`mesh convergence`, {repo}`results/tcad/meshconv` (`moscap1d/`) | dev HEAD, {repo}`docker/TCAD_DEV_IMAGE` | the same |
| 2D MOS capacitor and its mesh convergence (`moscap2d/`) | stable, {repo}`docker/TCAD_IMAGE` | see below |

The same mapping, read from the code, is drawn in {numref}`results-images`.

```{figure} /_generated/reproduce/results-images-light.svg
:name: results-images
:figclass: only-light
:alt: Boxes in two columns. Left, the 1D and the 2D result kinds, each naming its results folder and its mesh-convergence folder. Right, the dev and the stable image, each naming its pin file. An arrow joins each kind to its image.

Each result kind of {py:data}`gf180tcad.tcad.RESULTS_IMAGE` with its results folders (left).
Right, the image that makes it, by its pin file in {repo}`src/gf180tcad/generators.json`.
```

```{figure} /_generated/reproduce/results-images-dark.svg
:figclass: only-dark
:alt: Boxes in two columns. Left, the 1D and the 2D result kinds, each naming its results folder and its mesh-convergence folder. Right, the dev and the stable image, each naming its pin file. An arrow joins each kind to its image.

Each result kind of {py:data}`gf180tcad.tcad.RESULTS_IMAGE` with its results folders (left).
Right, the image that makes it, by its pin file in {repo}`src/gf180tcad/generators.json`.
```

The top folder of each set of results holds a provenance file, such as
{repo}`results/tcad/moscap2d/provenance.json`. Under `images`, it records which image made each
result kind in it: the image's name, its reference and its probe record. That record is
{repo}`docker/tcad/versions.json` or {repo}`docker/tcad-dev/versions.json`. The mesh-convergence results folder holds
1D and 2D results, so it records one entry for each.

- **1D on dev HEAD.** The 1D results folders regenerate on the dev image byte-identical to the stable
  image's, data file for data file. Only {repo}`provenance.json <results/tcad/moscap1d/provenance.json>` differs. Two sandbox tests keep it
  so: {test}`tests/tcad/test_moscap1d.py::test_byte_identical` and
  {test}`tests/tcad/test_meshconv.py::test_meshconv_byte_identical` rerun the committed results folders in
  the dev image, and {test}`tests/tcad/test_moscap1d.py::test_stable_and_dev_images_agree`
  runs both 1D CLIs on both images and requires the same bytes. That last test is the drift
  guard between the two stacks.
- **2D on stable.** The selected 2D mesh comes from the 2D mesh convergence on the stable
  image, which has {{ gmsh }} 4.15.2. The dev image has gmsh 5 and no 2D mesh convergence (next
  item). The 2D results of
  {repo}`Task 11 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`
  are therefore made on the stable image, explicitly, as {numref}`results-images` shows.
- **No 2D mesh convergence on dev.** The 2D mesh convergence has not been rerun on the dev
  image ([issue #67](https://github.com/mithro/gf180-tcad/issues/67)).
- **Known gap.** The stable image's builder, {repo}`docker/tcad/build`, has the laxer
  builder check. Unlike {repo}`docker/tcad-dev/build`, it does not verify an existing builder's
  driver and BuildKit image before using it
  ([issue #81](https://github.com/mithro/gf180-tcad/issues/81)).

(tcad-dev-mirror)=

### The input mirror

Every file the build fetches is mirrored to mithro-owned storage, {{ input_mirror }}. That is a
[GitHub release](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
of this repository, tag `gf180-tcad/inputs/tcad-dev-20261019`, used only for build inputs and
published as a pre-release, so it is never the repository's "Latest" release (GitHub makes the
newest full release "Latest" whatever `--latest=false` says). It holds 164 files:

- every source tarball (DEVSIM and its submodules, gdsfactory, the two forks);
- the gmsh development wheel, whose dated snapshots on [gmsh.info](https://gmsh.info/) are not
  promised to stay;
- the seven GCC 14 `.deb`s;
- the [python-build-standalone](https://github.com/astral-sh/python-build-standalone) CPython;
- every [PyPI](https://pypi.org/) file the build installs.

{repo}`docker/tcad-dev/upstream.json` and {repo}`docker/tcad-dev/wheelhouse.json` (the PyPI files,
written by {repo}`docker/tcad-dev/wheelhouse.py`) record, for each file, both URLs and its
sha256. {repo}`docker/tcad-dev/fetch_sources.py` fetches the mirror first and falls back to the
original URL. The sha256 is checked either way, so a missing or altered mirror file can only
slow the build, never change it.

The build then installs from the fetched files alone. [pip](https://pip.pypa.io/en/stable/) and
{{ uv }} run with `--no-index --find-links`; CPython comes through
[`uv python install --mirror file://`](https://docs.astral.sh/uv/reference/cli/#uv-python-install);
and the URL
requirements are rewritten to the fetched copies by {repo}`docker/tcad-dev/local_inputs.py`,
keeping their lock hashes. So nothing reaches PyPI, gmsh.info or GitHub during the install
steps.

{test}`tests/test_tcad_dev_lock.py::test_every_input_has_a_mirror_url_and_a_sha256` checks that
every input has a mirror URL and a sha256.
{test}`tests/test_tcad_dev_lock.py::test_wheelhouse_is_exactly_the_locked_pypi_files` checks
that the wheelhouse is exactly one allowed file per locked pin.
{repo}`tests/test_tcad_dev_inputs.py` unit-tests the mirror-then-URL fallback and the
local-install rewrites.

**Policy.** Never replace or delete assets of an existing inputs release. New or changed files go
to a new dated tag, because older commits keep building from the old one.

### Rebuild and verify the dev-HEAD image

```
docker/tcad-dev/build --no-cache
```

({repo}`docker/tcad-dev/build`) works like {repo}`docker/tcad/build`. Its `SOURCE_DATE_EPOCH`
inputs are:

- {repo}`docker/tcad-dev/Dockerfile`;
- the two lock files, {repo}`docker/tcad-dev/requirements.lock` and
  {repo}`docker/tcad-dev/build-requirements.lock`;
- the two input lists, {repo}`docker/tcad-dev/upstream.json` and
  {repo}`docker/tcad-dev/wheelhouse.json`;
- the three build scripts, {repo}`docker/tcad-dev/fetch_sources.py`,
  {repo}`docker/tcad-dev/local_inputs.py` and {repo}`docker/tcad-dev/build-devsim.sh`;
- {repo}`docker/IMAGE`.

On a shared host, `GF180TCAD_BUILDER` (read by {repo}`docker/tcad-dev/build`) selects another
builder of the same {{ BuildKit }} image, for example one created with CPU and memory limits
([`docker buildx create`](https://docs.docker.com/reference/cli/docker/buildx/create/)
`--driver-opt cpuset-cpus=...,memory=...`). The image does not depend on the builder's limits. `--load` also loads the result into the local Docker image store (same
image ID), so it can be run before it is pushed. The `image` workflow builds, checks and
publishes it as its third matrix entry, `tcad-dev`, on {{ GitHub_hosted_runner }}s, exactly as
the other two. After the first push of a new package on the {{ ghcr }}, check that an
anonymous pull of {repo}`docker/TCAD_DEV_IMAGE` works; if it does not, make the package public
({ref}`as for the stable image <tcad-image>`).

The build script refuses a builder in which any node lacks the pinned {{ BuildKit }} image option.

### Moving to a newer dev HEAD

1. Read the new HEAD commits with [`git ls-remote`](https://git-scm.com/docs/git-ls-remote) (anonymous https; never through an API
   client), and their dates from a clone.
   For a fork, first merge the new upstream HEAD into the fork's `main` (by pull request in the
   fork), and pin the fork's merged `main`.
2. Update {repo}`docker/tcad-dev/upstream.json` (commit, date, the sha256 of the new tarball or
   wheel, its `file` and `mirror_url`; for a fork also `upstream_commit`), the URL sources in
   {repo}`docker/tcad-dev/pyproject.toml`, the meshwell version and
   [`exclude-newer`](https://docs.astral.sh/uv/reference/settings/#exclude-newer). Relock with the
   command in that file, re-run the recorded
   [`uv pip compile`](https://docs.astral.sh/uv/reference/cli/#uv-pip-compile) command of
   {repo}`docker/tcad-dev/build-requirements.lock`, and regenerate
   {repo}`docker/tcad-dev/wheelhouse.json` with {repo}`docker/tcad-dev/wheelhouse.py`.
3. Upload every file to a new mirror release, tag `gf180-tcad/inputs/tcad-dev-<YYYYMMDD>`
   ([`gh release create --prerelease`](https://cli.github.com/manual/gh_release_create), then
   [`gh release upload`](https://cli.github.com/manual/gh_release_upload), each with
   `--repo mithro/gf180-tcad`). Then check each asset's digest against the two input lists. Keep
   old mirror releases, because older commits build from them. The tag appears in six places,
   and {test}`tests/test_tcad_dev_lock.py::test_one_mirror_tag_everywhere` checks that they agree:
   - `MIRROR_TAG` in {repo}`docker/tcad-dev/wheelhouse.py`, which sets the tag (the test reads it
     from there);
   - every `mirror_url` in {repo}`docker/tcad-dev/upstream.json`;
   - every `mirror_url` in {repo}`docker/tcad-dev/wheelhouse.json` (regenerated);
   - `input_mirror` in {repo}`docs/conf.py`;
   - the docstring of {repo}`docker/tcad-dev/fetch_sources.py`;
   - the tag named in this page.
4. Rebuild twice (`--no-cache`), commit {repo}`docker/tcad-dev/IMAGE_ID` and
   {repo}`docker/tcad-dev/versions.json`, then {repo}`docker/TCAD_DEV_IMAGE` once CI has pushed it.

(charon-images)=

## Charon images

{{ Charon }} is the second TCAD simulator of {term}`Phase 4`. It is built from source in
{repo}`docker/charon-libs/`, with the [Charon user manual](https://www.sandia.gov/app/uploads/sites/106/2022/08/Charon_UserManual-v2_2.pdf)'s
own recipe. {repo}`docker/CHARON_LIBS_IMAGE` pins that image by digest. The `charon` image
adds its `/opt/charon` to the dev-HEAD TCAD image ({ref}`charon-image`). No TCAD job runs Charon.

```{figure} /_generated/reproduce/charon-stages-light.svg
:name: charon-stages
:figclass: only-light
:alt: Five boxes joined by arrows. The inputs box at the top feeds the deps stage, which feeds the build stage, which feeds the charon-libs image at the bottom. A base image box on the left feeds both the deps stage and the image.

How the charon-libs image is built, from the stages of {repo}`docker/charon-libs/Dockerfile`.
The inputs come from {repo}`docker/charon-libs/upstream.json`, and the base image is
{repo}`docker/IMAGE`. Only `/opt/charon` passes from the build stage into the image.
```

```{figure} /_generated/reproduce/charon-stages-dark.svg
:figclass: only-dark
:alt: Five boxes joined by arrows. The inputs box at the top feeds the deps stage, which feeds the build stage, which feeds the charon-libs image at the bottom. A base image box on the left feeds both the deps stage and the image.

How the charon-libs image is built, from the stages of {repo}`docker/charon-libs/Dockerfile`.
The inputs come from {repo}`docker/charon-libs/upstream.json`, and the base image is
{repo}`docker/IMAGE`. Only `/opt/charon` passes from the build stage into the image.
```

### What the build uses

{repo}`docker/charon-libs/upstream.json` pins every input by sha256:

- the Charon 2.2.0 source tarball from Sandia's [download page](https://charon.sandia.gov/charon-downloads/source-code/);
- {{ Trilinos }} and {{ TriBITS }} at the commits that Table 2-1 of the user manual names;
- the build-only Ubuntu packages, such as the OpenMPI, netCDF and Boost headers.

{repo}`docker/charon-libs/lock_debs.py` chooses those packages from one Ubuntu snapshot. It
stops when a package needs a different version of a package that the base image has. It also
stops when a package's Breaks, Conflicts or Replaces field names a package that the base image
has, at the installed version.

The build reads Charon's own `General.opts` and `Linux.opts` from the tarball and checks their
sha256. It then reads {repo}`docker/charon-libs/opts/gf180.opts`, which holds five project lines:

- no Dakota drivers and no debug build;
- the install prefix `/opt/charon`;
- the base image's OpenBLAS as the BLAS and LAPACK library.

### The input mirror

The [release `gf180-tcad/inputs/charon-20261102`](https://github.com/mithro/gf180-tcad/releases/tag/gf180-tcad/inputs/charon-20261102)
holds a copy of every input that {repo}`docker/charon-libs/upstream.json` names. Each entry
there records the mirror URL, the original URL and the sha256. The fetch script,
{repo}`docker/charon-libs/fetch_sources.py`, tries the mirror first and the original URL second,
and checks the sha256 either way. The policy of the dev-HEAD image's mirror applies: assets of a
release are never replaced, and changed files go to another dated tag.

### Patches

The build applies six patches from {repo}`docker/charon-libs/patches/`. The first sets
constants. Four let 2022 sources build with the base image's GCC 13, netCDF 4.9 and tools. The
last makes the build reproducible across hosts.

| Patch | What it changes | Licence |
|---|---|---|
| {repo}`0001 <docker/charon-libs/patches/0001-codata2018-constants.patch>` | Charon's `kb`, `q` and `eps0` | GPL-3.0-or-later |
| {repo}`0002 <docker/charon-libs/patches/0002-kokkos-include-cstdint.patch>` | Kokkos: adds `<cstdint>` | BSD-3-Clause |
| {repo}`0003 <docker/charon-libs/patches/0003-exodus-netcdf-szip-macro.patch>` | Exodus: skips a constant netCDF defines | BSD-3-Clause |
| {repo}`0004 <docker/charon-libs/patches/0004-teuchos-include-cstdint.patch>` | Teuchos: adds `<cstdint>` | BSD-3-Clause |
| {repo}`0005 <docker/charon-libs/patches/0005-interpreter-copy-without-rsync.patch>` | Charon's configure: copies without `rsync` | GPL-3.0-or-later |
| {repo}`0006 <docker/charon-libs/patches/0006-interpreter-sorted-listings.patch>` | Charon's interpreter generator: sorted file lists | GPL-3.0-or-later |

The constants patch sets three values to the CODATA 2018 values that the {{ DEVSIM }} jobs use:

- `kb`, the Boltzmann constant divided by the elementary charge, in eV/K;
- `q`, the elementary charge;
- `eps0`, the vacuum permittivity.

The five other patches change no computation:

- GCC 13 no longer includes `<cstdint>` through other standard headers, so two files lacked
  `uint32_t`.
- netCDF 4.9 defines `NC_SZIP_NN` as a macro with the value 32. An Exodus file declares a
  constant of that name and value, which no longer compiles.
- Charon's configure step copies its input-deck interpreter with `rsync`, which the base image
  lacks. The copy failed without stopping the build, and the build check then stopped on the
  missing interpreter. The patch copies with CMake's `file(COPY)` and the same three exclusions.
- The generator of that interpreter lists its input files in directory order, which differs
  between filesystems. The generated modules then differed between the project's host and a
  GitHub runner, and so did the image digest. The patch sorts the lists.

### Licence

Charon is licensed GPL-3.0-or-later. Each patch keeps the licence of the files it changes, as
the table above lists; {repo}`docker/charon-libs/README.md` names them. Every other file of the
project stays Apache-2.0.

### Build steps

{repo}`docker/charon-libs/build` works like {repo}`docker/tcad-dev/build`, with one more rule.
The Trilinos compile runs in a BuildKit builder limited to 16 GiB of memory with no swap.
The script creates that builder on first use. It refuses a builder unless every node's
running container has a memory limit of at most 16 GiB and no swap, as docker applied them.

The builder runs outside {term}`gf180-tcad.slice`, with that limit of its own. Docker's
buildx places a builder in a given {term}`cgroup` only when docker uses the cgroupfs driver,
and the project's host runs docker with {{ systemd }}.
[Issue #155](https://github.com/mithro/gf180-tcad/issues/155) holds the ways to place it in the slice.

{numref}`charon-stages` shows the three stages of {repo}`docker/charon-libs/Dockerfile`:

1. `deps` fetches every input, checks its sha256, installs the build packages and applies the
   patches. This is the only step with a network.
2. `build` runs Charon's [`build_charon.py`](https://charon.sandia.gov/charon-downloads/source-code/) through {repo}`docker/charon-libs/build-charon.sh`,
   then `make` and `make install`. Four upstream nightly tests then run as the build check, and
   every one must run and pass.
3. The image is the base image plus `/opt/charon`, with no compiler or source tree left in it.
   Every program and library in `/opt/charon` must find its shared libraries there.

The four tests of the build check are these, by their CTest names:

- `Charon_charon_mp_pmoscap.nlp`, a p-type MOS capacitor;
- `Charon_charon_mp.hb.loca-moscap-cv.ox` and `Charon_charon_mp.hb.loca-moscap-cv.sub`, two
  small-signal C-V {term}`sweeps <sweep>` of a MOS capacitor;
- `Charon_charon_mp_pndiode.nlp`, an abrupt {term}`pn junction`, as the deck
  [`pndiode.nlp.inp`](https://charon.sandia.gov/charon-downloads/source-code/) of the Charon
  tarball defines it.

The build writes two JSON records into `/opt/charon/share/gf180tcad/` in the image, both
produced by {repo}`docker/charon-libs/inputs.py`:

- the build record lists the inputs by sha256, the opts files, the patches and the tests of
  the build check;
- the source record lists the corresponding source by sha256.

{repo}`docker/charon-libs/probe_versions.py` reads both records, the compiler of
`charon_mp.exe` and the runtime packages, and its output is
{repo}`docker/charon-libs/versions.json`. Its `charon_build` and `sources` keys copy the two
records. {repo}`docker/charon-libs/IMAGE_ID` holds the config digest.

`--target deps --load` loads the first stage as a local image. A developer can then run the
compile in {repo}`tools/sandbox-run` and keep the build tree between attempts. `--jobs N` sets
the number of compile jobs.

(charon-mpi-sandbox)=

### One MPI process in the sandbox

```{figure} /_generated/reproduce/charon-mpi-light.svg
:name: charon-mpi
:figclass: only-light
:alt: A container box holds a process box with two thread boxes, main and progress. An arrow leads from the process to a /tmp box. A dashed box lists orted and the pmix files as not started.

`charon_mp.exe` in a container of {repo}`tools/sandbox-run`: one process with two threads, its
session directory under `/tmp`, and neither `orted` nor the PMIx files. {repo}`tests/test_charon_image.py`
checks each of these during a solve.
```

```{figure} /_generated/reproduce/charon-mpi-dark.svg
:figclass: only-dark
:alt: A container box holds a process box with two thread boxes, main and progress. An arrow leads from the process to a /tmp box. A dashed box lists orted and the pmix files as not started.

`charon_mp.exe` in a container of {repo}`tools/sandbox-run`: one process with two threads, its
session directory under `/tmp`, and neither `orted` nor the PMIx files. {repo}`tests/test_charon_image.py`
checks each of these during a solve.
```

Charon is an MPI program. Every TCAD job runs `charon_mp.exe` as one process, without
`mpirun`, under the rules of {repo}`tools/sandbox-run`: no network, and only `/tmp` writable.
Started that way, OpenMPI 4.1 forks a helper daemon, `orted`, and writes shared-memory files
under `/tmp`. {repo}`docker/charon-libs/Dockerfile` sets `OMPI_MCA_ess_singleton_isolated=1`,
which stops both. The solve then runs in one process with two threads, as {numref}`charon-mpi`
shows: the main thread, which computes, and OpenMPI's progress thread.

The Exodus output file holds the date, time and host of the run in its QA record. Two runs of
the same deck therefore differ in that record only. The text output `currents-loca.dat` is
byte-identical between runs. The image's `exodiff -absolute -tolerance 0` finds no difference
between the two Exodus files in any variable at any time step.

### Build cost

The pinned image was built twice from the same commit, with two compile jobs both times. One
build ran on a GitHub runner with 4 CPUs. The other ran on the project's host in the 16 GiB
builder, with other jobs sharing its 8 CPUs. Both gave the same digests. The record of both builds is in
[pull request #120](https://github.com/mithro/gf180-tcad/pull/120).

| Quantity | GitHub runner | Project's host |
|---|---|---|
| Wall time of the whole build (min) | 71 | 216 |
| Wall time of `make` (min) | 65 | 209 |

On the project's host the builder's memory peaked at 6.35 GB. In the pinned image, the files in
`/opt/charon` add up to 353 MB (`du -sb`). The manifest of the pin in {repo}`docker/CHARON_LIBS_IMAGE`
gives the layer it adds to the base image as 91.7 MB compressed.

### Checks on GitHub

```{figure} /_generated/reproduce/charon-ci-light.svg
:name: charon-ci
:figclass: only-light
:alt: Flow from the trigger to a gate on three paths. No leads to a skip box. Yes leads to the build, then three checks in a row, then the published tags.

The charon-libs entry of the build-push job in {repo}`.github/workflows/image.yml`. The checks run
in turn, and a failed check ends the job before any published tag.
```

```{figure} /_generated/reproduce/charon-ci-dark.svg
:figclass: only-dark
:alt: Flow from the trigger to a gate on three paths. No leads to a skip box. Yes leads to the build, then three checks in a row, then the published tags.

The charon-libs entry of the build-push job in {repo}`.github/workflows/image.yml`. The checks run
in turn, and a failed check ends the job before any published tag.
```

{repo}`.github/workflows/image.yml` builds this image only when it changes, as
{numref}`charon-ci` shows. Its build job runs on a pull request or a push that changes
{repo}`docker/charon-libs/`, {repo}`docker/IMAGE` or {repo}`docker/CHARON_LIBS_IMAGE`, and on a
manual run. It allows 350 minutes. The rebuild from scratch, which proves the digests
reproducible, runs on the weekly schedule and on a manual run. Every other pull request skips
both and passes.

The build pushes only the tag `unverified`. Three checks then compare the config digest with
{repo}`docker/charon-libs/IMAGE_ID`, the {term}`manifest digest` with {repo}`docker/CHARON_LIBS_IMAGE` and the
probe's output with {repo}`docker/charon-libs/versions.json`. The published tags come last.

{repo}`tests/test_charon_image.py` runs the image's checks. Its sandbox tests run the upstream
`pmoscap.nlp` and `loca_moscap_cv` decks in both pinned Charon images. The charon-libs image
installs them under `/opt/charon/share/gf180tcad/tests`. The image's `io_info` reads one time step in the
`pmoscap.nlp` output file.

(charon-image)=

### The charon image

The `charon` image is the one a Charon job runs in. It is the
{ref}`dev-HEAD TCAD image <tcad-dev-image>` with `/opt/charon` from the charon-libs image and the
{{ netCDF4 }} and {{ cftime }} packages added to its venv. One container then holds {{ Python }} 3.13,
the {{ DEVSIM }} stack, `netCDF4` and `charon_mp.exe`. {repo}`docker/charon/` holds the recipe, and
{repo}`docker/CHARON_IMAGE` pins it by digest.

```{figure} /_generated/reproduce/charon-layers-light.svg
:name: charon-layers
:figclass: only-light
:alt: A tall container box on the right holds four boxes stacked from the bottom: the dev-HEAD TCAD image, layer 1 /opt/charon, layer 2 netCDF4 and cftime, and the ENV. Two boxes on the left, the charon-libs image and the wheels stage, each have an arrow to the layer beside them.

The layers of the charon image, from {repo}`docker/charon/Dockerfile`. The dev-HEAD TCAD image
is the bottom of the stack. The charon-libs image gives layer 1 and the `wheels` stage gives
layer 2.
```

```{figure} /_generated/reproduce/charon-layers-dark.svg
:figclass: only-dark
:alt: A tall container box on the right holds four boxes stacked from the bottom: the dev-HEAD TCAD image, layer 1 /opt/charon, layer 2 netCDF4 and cftime, and the ENV. Two boxes on the left, the charon-libs image and the wheels stage, each have an arrow to the layer beside them.

The layers of the charon image, from {repo}`docker/charon/Dockerfile`. The dev-HEAD TCAD image
is the bottom of the stack. The charon-libs image gives layer 1 and the `wheels` stage gives
layer 2.
```

{numref}`charon-layers` shows the two layers the image adds:

1. Layer 1 copies `/opt/charon` byte for byte from the image that {repo}`docker/CHARON_LIBS_IMAGE`
   pins. Both images start from {repo}`docker/IMAGE`, so the runtime libraries are present. The
   build runs the `ldd` check of {repo}`docker/charon-libs/build-charon.sh` on every file.
2. Layer 2 installs the wheels that {repo}`docker/charon/requirements.lock` pins by sha256. The
   `wheels` stage downloads them, and the install runs with no network and no dependency
   resolution. `numpy` and `certifi`, the other requirements of `netCDF4`, come from the dev
   image's venv.

The image's ENV keeps the dev image's settings, `OMP_NUM_THREADS=1` among them. It adds:

- `PATH`: `/opt/charon/bin` first, then the dev image's `PATH`;
- `CHARON_EXECUTABLE_PATH=/opt/charon/bin` and `CHARON_EXECUTABLE=charon_mp.exe`;
- `OMPI_MCA_ess_singleton_isolated=1`, as in the charon-libs image ({ref}`charon-mpi-sandbox`);
- `PYTHON_CPU_COUNT=1`, the dev image's value, set again.

{repo}`docker/charon/probe_versions.py` writes {repo}`docker/charon/versions.json`. It holds the
dev image's probe, both pinned image references, the charon-libs keys and the versions below.

```{table} The Python packages the charon image adds, and the C libraries inside the netCDF4 wheel. Values from {repo}`docker/charon/versions.json`.
:name: charon-image-versions

| Component | Version |
|---|---|
| `netCDF4` | 1.7.5 |
| `cftime` | 1.6.6.1 |
| netCDF-C in the `netCDF4` wheel | 4.10.1 |
| HDF5 in the `netCDF4` wheel | 2.2.0 |
```

{repo}`docker/charon/build` works like {repo}`docker/charon-libs/build`, in the same 16 GiB
builder. Its build inputs are the files in {repo}`docker/charon/`, the two pin files and
{repo}`docker/charon-libs/build-charon.sh`.

The pinned image was built twice from the same commit, once on a GitHub runner and once on the
project's host. Both gave the same digests, as [pull request #164](https://github.com/mithro/gf180-tcad/pull/164)
records. The runner's time includes the push of the image, and the host's its load into the
local image store. The table gives the two build logs that the pull request records.

| Quantity | GitHub runner | Project's host |
|---|---|---|
| Wall time of the whole build (s) | 295 | 335 |
| Builder memory peak (GB) | — | 5.10 |

Workflow [run 42349097853](https://github.com/mithro/gf180-tcad/actions/runs/42349097853)
rebuilt both Charon images from scratch on a GitHub runner. Each rebuilt digest equals its pin, in
{repo}`docker/CHARON_IMAGE` and {repo}`docker/CHARON_LIBS_IMAGE`.

The manifest of the pin in {repo}`docker/CHARON_IMAGE` gives the two layers as 91.7 MB and
12.5 MB, compressed. They sit on top of the dev-HEAD TCAD image.

{repo}`.github/workflows/image.yml` builds the charon image whenever a pull request or a push
changes a file under {repo}`docker/`. The entry has no gate. It is {numref}`charon-ci` without
the gate box: the trigger leads to the build, then to the same three checks and published tags. Its rebuild from
scratch runs on every such change as well. The sandbox tests of
{repo}`tests/test_charon_image.py` also check the ENV above and read the `pmoscap.nlp` output
with `netCDF4`.
