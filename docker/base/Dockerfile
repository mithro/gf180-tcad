# SPDX-License-Identifier: Apache-2.0
# gf180-tcad base image: the pinned IIC-OSIC-TOOLS image plus a locked Python venv.
# Project code is NOT baked in; tools/sandbox-run mounts the repo at /work/src.
# Build with docker/base/build (reproducible: SOURCE_DATE_EPOCH + rewrite-timestamp).
ARG BASE_IMAGE=hpretl/iic-osic-tools@sha256:306585de35d198e70ea58950f77147c86f56c698726a19afea9f1c83009557be
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
ARG SOURCE_DATE_EPOCH

USER root
# Venv from the image's own /usr/bin/python3 (3.12.3): no pip inside it, no bytecode, hashes only,
# wheels only -- except rectpack (sdist-only on PyPI), built from its hashed sdist with the locked
# setuptools (installed first, then used via --no-build-isolation). Bytecode embeds source mtimes,
# so none may be written (the setuptools build would otherwise leave .pyc files).
RUN --mount=type=bind,source=requirements.lock,target=/run/gf180tcad/requirements.lock \
    --mount=type=bind,source=build-requirements.lock,target=/run/gf180tcad/build-requirements.lock \
    --mount=type=tmpfs,target=/tmp \
    export HOME=/tmp PIP_CONFIG_FILE=/dev/null PYTHONDONTWRITEBYTECODE=1 \
 && /usr/bin/python3 -m venv --without-pip /opt/gf180tcad \
 && pip() { /usr/bin/python3 -m pip --python /opt/gf180tcad/bin/python install \
        --no-cache-dir --disable-pip-version-check --no-input --no-compile \
        --require-hashes --no-deps --only-binary=:all: "$@"; } \
 && pip -r /run/gf180tcad/build-requirements.lock \
 && pip --no-build-isolation --no-binary=rectpack -r /run/gf180tcad/requirements.lock \
 && test -z "$(find /opt/gf180tcad -name '*.pyc' -print -quit)"
USER 1000:1000

ENV PATH=/opt/gf180tcad/bin:/foss/tools/ngspice/bin:/foss/tools/xyce/bin:/foss/tools/klayout:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    VIRTUAL_ENV=/opt/gf180tcad \
    PYTHONDONTWRITEBYTECODE=1 \
    PDK_ROOT=/foss/pdks \
    PDK=gf180mcuD \
    GF180TCAD_BASE_IMAGE=${BASE_IMAGE} \
    USER=gf180tcad \
    LOGNAME=gf180tcad \
    HOME=/tmp/home \
    TZ=UTC \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    DEVSIM_MATH_LIBS=libopenblas.so.0 \
    OPENBLAS_CORETYPE=Haswell

# DEVSIM dlopen()s BLAS/LAPACK: use the image's system OpenBLAS. OPENBLAS_CORETYPE pins the
# OpenBLAS kernel family (system and numpy/scipy wheels) so results do not depend on host CPU.

LABEL org.opencontainers.image.source="https://github.com/mithro/gf180-tcad" \
      org.opencontainers.image.title="gf180-tcad-base" \
      org.opencontainers.image.description="IIC-OSIC-TOOLS plus the locked gf180-tcad Python venv" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.base.name="${BASE_IMAGE}"

# The IIC entrypoint starts a VNC desktop; never run it.
ENTRYPOINT []
CMD ["/bin/bash"]
