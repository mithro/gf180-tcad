# SPDX-License-Identifier: Apache-2.0
# gf180-tcad charon image: the dev-HEAD TCAD image (docker/TCAD_DEV_IMAGE) plus /opt/charon, copied
# unchanged from the pinned charon-libs image (docker/CHARON_LIBS_IMAGE: Charon 2.2.0 and Trilinos
# built from source, docker/charon-libs/), plus the hash-locked netCDF4 and cftime wheels of
# requirements.lock in the TCAD venv. So one container holds Python 3.13 with the DEVSIM stack,
# netCDF4 and charon_mp.exe. Both images are FROM the same base image (docker/IMAGE), so the
# runtime libraries /opt/charon links against are already here; step 2 checks it.
# Charon is GPL-3.0-or-later: docker/charon-libs/README.md states what that means for the
# images and where the corresponding source is. Build with docker/charon/build.
#
# Stages: `wheels` downloads the locked wheels (the only step with a network; pip checks each
# sha256); the image copies /opt/charon and installs the wheels with --network=none.
ARG TCAD_DEV_IMAGE
ARG CHARON_LIBS_IMAGE

FROM ${CHARON_LIBS_IMAGE} AS charon-libs

FROM ${TCAD_DEV_IMAGE} AS wheels
USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# 1. The wheels of requirements.lock for the venv's interpreter (pip --python picks its tags):
#    hashes only, binary only, no dependencies resolved.
RUN --mount=type=bind,source=requirements.lock,target=/run/gf180tcad/requirements.lock \
    --mount=type=tmpfs,target=/tmp \
    set -eu \
 && export HOME=/tmp PIP_CONFIG_FILE=/dev/null \
 && /usr/bin/python3 -m pip --isolated --python /opt/gf180tcad-tcad/bin/python download \
        --no-cache-dir --disable-pip-version-check --no-input \
        --require-hashes --no-deps --only-binary=:all: \
        --dest /opt/build/wheels -r /run/gf180tcad/requirements.lock

FROM ${TCAD_DEV_IMAGE}
ARG TCAD_DEV_IMAGE
ARG CHARON_LIBS_IMAGE
COPY --from=charon-libs /opt/charon /opt/charon
USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# 2. The wheels into the TCAD venv from the downloaded files only (no index, no network), no
#    bytecode (.pyc files embed source mtimes). Then the imports, and the check that
#    charon_mp.exe and every library of /opt/charon load with this image's runtime libraries
#    (build-charon.sh check-runtime, from the charon-libs recipe: the named build context
#    `charon-libs-recipe` that docker/charon/build passes).
RUN --network=none \
    --mount=type=bind,source=requirements.lock,target=/run/gf180tcad/requirements.lock \
    --mount=type=bind,from=wheels,source=/opt/build/wheels,target=/run/gf180tcad/wheels \
    --mount=type=bind,from=charon-libs-recipe,source=build-charon.sh,target=/run/gf180tcad/build-charon.sh \
    --mount=type=tmpfs,target=/tmp \
    set -eu \
 && export HOME=/tmp PIP_CONFIG_FILE=/dev/null PYTHONDONTWRITEBYTECODE=1 \
 && /usr/bin/python3 -m pip --isolated --python /opt/gf180tcad-tcad/bin/python install \
        --no-cache-dir --disable-pip-version-check --no-input --no-compile \
        --require-hashes --no-deps --only-binary=:all: \
        --no-index --find-links /run/gf180tcad/wheels \
        -r /run/gf180tcad/requirements.lock \
 && /opt/gf180tcad-tcad/bin/python -c 'import netCDF4, cftime' \
 && test -z "$(find /opt/gf180tcad-tcad -name '*.pyc' -print -quit)" \
 && bash /run/gf180tcad/build-charon.sh check-runtime /opt/charon
USER 1000:1000
# PATH: Charon's tools first, then exactly the dev image's PATH (the TCAD venv, then the base
# image's). The rest of the dev image's ENV (OMP_NUM_THREADS=1 and the other thread variables,
# VIRTUAL_ENV, PDK, ...) is inherited; PYTHON_CPU_COUNT=1 is too, and is set again here so that
# this image does not depend on that. CHARON_EXECUTABLE_PATH and CHARON_EXECUTABLE name the
# solver for the Python backend. Experiment A3 (docker/charon-libs/Dockerfile): with
# OMPI_MCA_ess_singleton_isolated=1, charon_mp.exe runs as one MPI process without mpirun, forks
# no `orted` and writes no PMIx shared-memory files.
ENV PATH=/opt/charon/bin:${PATH} \
    CHARON_EXECUTABLE_PATH=/opt/charon/bin \
    CHARON_EXECUTABLE=charon_mp.exe \
    OMPI_MCA_ess_singleton_isolated=1 \
    PYTHON_CPU_COUNT=1 \
    GF180TCAD_CHARON_LIBS_IMAGE=${CHARON_LIBS_IMAGE} \
    GF180TCAD_CHARON_TCAD_DEV_IMAGE=${TCAD_DEV_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/mithro/gf180-tcad" \
      org.opencontainers.image.title="gf180-tcad-charon" \
      org.opencontainers.image.description="gf180-tcad dev-HEAD TCAD image plus Charon 2.2.0 and Trilinos in /opt/charon and netCDF4 in the TCAD venv" \
      org.opencontainers.image.licenses="GPL-3.0-or-later AND BSD-3-Clause AND LGPL-2.1-or-later AND Apache-2.0 AND MIT" \
      org.opencontainers.image.base.name="${TCAD_DEV_IMAGE}"

ENTRYPOINT []
CMD ["/bin/bash"]
