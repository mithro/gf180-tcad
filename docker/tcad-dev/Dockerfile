# SPDX-License-Identifier: Apache-2.0
# gf180-tcad dev-HEAD TCAD image: like docker/tcad/ (the stable baseline, PyPI releases), but with
# DEVSIM, meshwell, gdsfactory, gf180mcu and gmsh from their upstream development HEADs, pinned
# by commit and sha256 in upstream.json. The same pinned base image and the same CPython 3.13
# patch as the stable image; the venv has the same path, /opt/gf180tcad-tcad.
# Project code is NOT baked in; tools/sandbox-run mounts the repo at /work/src.
# Build with docker/tcad-dev/build, which passes BASE_IMAGE = docker/IMAGE (reproducible:
# SOURCE_DATE_EPOCH + rewrite-timestamp).
#
# Two stages: `build` fetches and checks every source, compiles DEVSIM (with a GCC 14 that
# exists only in this stage) and fills the venv; the image is the base plus a copy of the venv
# and of the uv-managed CPython, so no compiler, source tree or download is left in it.
ARG BASE_IMAGE

FROM ${BASE_IMAGE} AS build
ARG SOURCE_DATE_EPOCH
# Must equal the --python-version of the single locks (tests/test_tcad_dev_lock.py).
ARG TCAD_PYTHON=3.13.16
# hatch-vcs takes meshwell's version from git, which the source tarball lacks: the version it
# gives at the pinned commit (v2.5.2-2-gb6d5ccd52). Only meshwell uses setuptools-scm here.
ARG MESHWELL_VERSION=2.5.3.dev2+gb6d5ccd52
USER root
ENV HOME=/tmp/home PYTHONDONTWRITEBYTECODE=1 UV_NO_CONFIG=1 UV_CACHE_DIR=/opt/build/uv-cache \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python UV_LINK_MODE=copy
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# 1. Every non-PyPI source (DEVSIM and the submodules it builds with, the GCC 14 packages),
#    by URL, checked against upstream.json's sha256.
RUN --mount=type=bind,source=upstream.json,target=/run/gf180tcad/upstream.json \
    --mount=type=bind,source=fetch_sources.py,target=/run/gf180tcad/fetch_sources.py \
    set -eu \
 && mkdir -p "$HOME" \
 && /usr/bin/python3 -I /run/gf180tcad/fetch_sources.py /run/gf180tcad/upstream.json \
        /opt/build/src devsim symdiff umfpack_lgpl boost_config boost_math boost_multiprecision \
        cpp-14-x86-64-linux-gnu gcc-14-x86-64-linux-gnu g++-14-x86-64-linux-gnu \
        gfortran-14-x86-64-linux-gnu libgcc-14-dev libstdc++-14-dev libgfortran-14-dev \
 && cp /run/gf180tcad/upstream.json /opt/build/src/upstream.json

# 2. uv (hash-pinned, into a build venv), CPython $TCAD_PYTHON (uv checks it against the sha256 it
#    embeds for that version) and the empty venv.
RUN --mount=type=bind,source=build-requirements.lock,target=/run/gf180tcad/build-requirements.lock \
    set -eu \
 && /usr/bin/python3 -m venv --without-pip /opt/build/buildvenv \
 && /usr/bin/python3 -m pip --isolated --python /opt/build/buildvenv/bin/python install \
        --no-cache-dir --disable-pip-version-check --no-input --no-compile \
        --require-hashes --no-deps --only-binary=:all: \
        -r /run/gf180tcad/build-requirements.lock \
 && /opt/build/buildvenv/bin/uv python install --no-bin "$TCAD_PYTHON" \
 && /opt/build/buildvenv/bin/uv venv --managed-python --python "$TCAD_PYTHON" /opt/gf180tcad-tcad

# 3. DEVSIM from source (build-devsim.sh: upstream's x86_64 recipe), as a wheel.
RUN --mount=type=bind,source=build-devsim.sh,target=/run/gf180tcad/build-devsim.sh \
    --mount=type=bind,source=build-requirements.lock,target=/run/gf180tcad/build-requirements.lock \
    set -eu \
 && UV=/opt/build/buildvenv/bin/uv bash /run/gf180tcad/build-devsim.sh /opt/build/src \
        /opt/build/devsim /opt/build/wheels "/opt/gf180tcad-tcad/bin/python" \
        /run/gf180tcad/build-requirements.lock

# 4. The venv: requirements.lock (wheels, except the sdists built here: meshwell and gdsfactory
#    at their pinned commits, and rectpack, sdist-only on PyPI; their build backends are the
#    hash-checked build constraints), gf180mcu --no-deps, then the DEVSIM wheel of step 3
#    --no-deps (it has no Python dependencies), with pip: uv would record the wheel file's
#    ctime in the dist-info (uv_cache.json, and so RECORD), which no build can fix. Hashes only,
#    no deps resolved, no bytecode. Then upstream.json, the provenance of the upstream sources
#    (docker/tcad-dev/probe_versions.py checks it against what the packages report), with a fixed
#    mode: a COPY from the build context would keep the checkout's mode, which follows the umask
#    of whoever checked it out (0664 here, 0644 on a GitHub runner).
RUN --mount=type=bind,source=requirements.lock,target=/run/gf180tcad/requirements.lock \
    --mount=type=bind,source=gf180mcu.lock,target=/run/gf180tcad/gf180mcu.lock \
    --mount=type=bind,source=upstream.json,target=/run/gf180tcad/upstream.json \
    --mount=type=bind,source=build-requirements.lock,target=/run/gf180tcad/build-requirements.lock \
    set -eu \
 && uv=/opt/build/buildvenv/bin/uv \
 && uvpip() { "$uv" pip install --python /opt/gf180tcad-tcad/bin/python --no-deps "$@"; } \
 && SETUPTOOLS_SCM_PRETEND_VERSION="$MESHWELL_VERSION" uvpip --require-hashes \
        --only-binary=:all: --no-binary=meshwell --no-binary=gdsfactory --no-binary=rectpack \
        --build-constraints /run/gf180tcad/build-requirements.lock \
        -r /run/gf180tcad/requirements.lock \
 && uvpip --require-hashes --only-binary=:all: --no-binary=gf180mcu \
        --build-constraints /run/gf180tcad/build-requirements.lock \
        -r /run/gf180tcad/gf180mcu.lock \
 && /usr/bin/python3 -m pip --isolated --python /opt/gf180tcad-tcad/bin/python install \
        --no-cache-dir --disable-pip-version-check --no-input --no-compile --no-deps \
        /opt/build/wheels/devsim-*.whl \
 && install -D -m 0644 /run/gf180tcad/upstream.json /opt/gf180tcad-tcad/share/gf180tcad/upstream.json \
 && site="$(/opt/gf180tcad-tcad/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" \
 && printf '%s\n' /work/src/third_party/gplugins > "$site/gf180tcad-gplugins.pth" \
 && test "$(/opt/gf180tcad-tcad/bin/python -c 'import platform; print(platform.python_version())')" = "$TCAD_PYTHON" \
 && test "$(/opt/gf180tcad-tcad/bin/python -c 'from importlib.metadata import version; print(version("meshwell"))')" = "$MESHWELL_VERSION" \
 && find /opt/uv-python -name '*.pyc' -delete \
 && find /opt/uv-python -name __pycache__ -type d -empty -delete \
 && chmod -R go-w /opt/uv-python /opt/gf180tcad-tcad \
 && test -z "$(find /opt/gf180tcad-tcad /opt/uv-python -name '*.pyc' -print -quit)"

FROM ${BASE_IMAGE}
ARG BASE_IMAGE
COPY --from=build /opt/uv-python /opt/uv-python
COPY --from=build /opt/gf180tcad-tcad /opt/gf180tcad-tcad
USER 1000:1000

# As docker/tcad/Dockerfile: the TCAD venv first, then exactly the base image's PATH; the rest of
# the base ENV (thread variables, DEVSIM_MATH_LIBS, OPENBLAS_CORETYPE, ...) is inherited.
ENV PATH=/opt/gf180tcad-tcad/bin:${PATH} \
    VIRTUAL_ENV=/opt/gf180tcad-tcad \
    PDK=gf180mcu \
    PYTHON_CPU_COUNT=1 \
    GF180TCAD_TCAD_BASE_IMAGE=${BASE_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/mithro/gf180-tcad" \
      org.opencontainers.image.title="gf180-tcad-tcad-dev" \
      org.opencontainers.image.description="gf180-tcad base image plus a Python 3.13 TCAD venv with DEVSIM, meshwell, gmsh, gdsfactory and gf180mcu from their upstream development HEADs" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.base.name="${BASE_IMAGE}"

ENTRYPOINT []
CMD ["/bin/bash"]
