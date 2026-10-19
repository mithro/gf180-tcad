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

This is the {term}`stable TCAD image`, with the latest PyPI releases of the TCAD stack. The
{term}`dev-HEAD TCAD image` ({ref}`tcad-dev-image`) has the same layout with each project at its
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

The 1D TCAD results are generated in the dev-HEAD image and the 2D results, for now, in the
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

- **{{ gf180mcu_fork }}** (Apache-2.0), main
  [`9342e3e`](https://github.com/mithro/gf180mcu/commit/9342e3e1804e419ba4d3a252746fe688657a9b74)
  = upstream [`96b7324`](https://github.com/gdsfactory/gf180mcu/commit/96b7324d85df05704f68c1370c175627d0a88034)
  plus [mithro/gf180mcu#4](https://github.com/mithro/gf180mcu/pull/4).
  - **Problem.** gf180mcu did not import with gdsfactory's HEAD (10.0.0rc0). Its
    [`tech.py`](https://github.com/gdsfactory/gf180mcu/blob/96b7324d85df05704f68c1370c175627d0a88034/gf180mcu/tech.py)
    built every cross-section at import, to learn its default name. From gdsfactory 10, the
    layer lookup that this needs activates the PDK named by `PDK=gf180mcu`, which is the
    half-imported module itself.
  - **Fix.** The cross-sections are now built on first use.
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
    1e-3 V at mesh ×1 and ×0.5 (measured to about 2e-15 V on both gmsh versions). This is a
    stronger check: it fails for a coupled rib.
  - **Check here.**
    {test}`tests/test_tcad_dev_image.py::test_tcad_dev_fork_pn_slab_currents_explained` runs
    that fork test in the dev image and requires it to pass. The fork test is the one that holds
    the invariant. It runs from a `git archive` of the submodule pin,
    {repo}`third_party/gplugins <.gitmodules>` at
    [`1c071d0`](https://github.com/mithro/gplugins/commit/1c071d0565ef4917b48ff907b9426e879ccca7fc),
    the commit the committed results are made with.

**The full flow runs in the dev image** (2026-10-19, image config `245963e5…`):

- every sandbox test of {repo}`tests/test_tcad_dev_image.py` passes;
- the fork's `gplugins/devsim` and `gplugins/process` tests at `408d0af` give 131 passed in the
  dev image and 131 passed in the stable image;
- the 1D {term}`MOS capacitor <MOSCAP>` and mesh-convergence trees regenerated in the dev image
  ({repo}`tests/tcad`) are byte-identical to the committed {repo}`results/tcad/moscap1d` and
  {repo}`results/tcad/meshconv` trees, except their `provenance.json`, which names the image.

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
| 2D MOS capacitor and its mesh convergence (`moscap2d/`) | stable, {repo}`docker/TCAD_IMAGE` | for now: see below |

Each tree root's `provenance.json` records, under `images`, which image made each result kind
in it: the image's name, its reference and its `versions.json`. The mesh-convergence tree holds
1D and 2D results, so it records one entry for each.

- **1D on dev HEAD.** The 1D trees regenerate on the dev image byte-identical to the stable
  image's, data file for data file; only `provenance.json` differs. Two sandbox tests keep it
  so: {test}`tests/tcad/test_moscap1d.py::test_byte_identical` and
  {test}`tests/tcad/test_meshconv.py::test_meshconv_byte_identical` rerun the committed trees in
  the dev image, and {test}`tests/tcad/test_moscap1d.py::test_stable_and_dev_images_agree`
  runs both 1D CLIs on both images and requires the same bytes. That last test is the drift
  guard between the two stacks.
- **2D on stable, for now.** {{ gmsh }} 5 (the dev image) meshes the 2D cells differently
  from gmsh 4.15.2 (the stable image), so a 2D result on dev needs its own mesh convergence on
  dev; the stable image's selected 2D mesh does not carry over. The 2D results of
  {repo}`Task 11 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`
  are therefore made on the stable image, explicitly.
- **Planned.** Before the {term}`Phase 2` exit, the 2D mesh convergence is rerun on the dev image and
  the 2D results are regenerated there; `RESULTS_IMAGE` then names dev for 2D as well.

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
