# SPDX-License-Identifier: Apache-2.0
# gf180-tcad TCAD image: the pinned gf180-tcad base image plus a uv-managed CPython 3.13 venv with
# the TCAD stack (meshwell >= 2.4 needs Python 3.13; the base venv is 3.12).
# Project code is NOT baked in; tools/sandbox-run mounts the repo at /work/src.
# Build with docker/tcad/build, which passes BASE_IMAGE = docker/IMAGE (reproducible:
# SOURCE_DATE_EPOCH + rewrite-timestamp).
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
ARG SOURCE_DATE_EPOCH
# Must equal the --python-version of the single locks (tests/test_tcad_lock.py).
ARG TCAD_PYTHON=3.13.16

USER root
# 1. uv, hash-pinned, into a throwaway build venv on the tmpfs (the base venv has no pip and the
#    base image has no uv).
# 2. CPython $TCAD_PYTHON, pinned exactly; uv verifies the download against the sha256 it embeds
#    for that version.
# 3. The venv: requirements.lock (wheels only, except rectpack, which is sdist-only on PyPI and is
#    built with the hash-pinned setuptools from build-requirements.lock as build constraint), then
#    gf180mcu --no-deps (it pins gdsfactory~=9.40; the image has 9.51).
# Hashes only, no deps resolved, no bytecode (.pyc files embed source mtimes; the few .pyc files
# shipped in the CPython archive are stale after extraction, so they are deleted).
RUN --mount=type=bind,source=requirements.lock,target=/run/gf180tcad/requirements.lock \
    --mount=type=bind,source=gf180mcu.lock,target=/run/gf180tcad/gf180mcu.lock \
    --mount=type=bind,source=build-requirements.lock,target=/run/gf180tcad/build-requirements.lock \
    --mount=type=tmpfs,target=/tmp \
    set -eu \
 && export HOME=/tmp PIP_CONFIG_FILE=/dev/null PYTHONDONTWRITEBYTECODE=1 \
        UV_NO_CONFIG=1 UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_INSTALL_DIR=/opt/uv-python \
        UV_LINK_MODE=copy \
 && /usr/bin/python3 -m venv --without-pip /tmp/buildvenv \
 && /usr/bin/python3 -m pip --python /tmp/buildvenv/bin/python install \
        --no-cache-dir --disable-pip-version-check --no-input --no-compile \
        --require-hashes --no-deps --only-binary=:all: \
        -r /run/gf180tcad/build-requirements.lock \
 && uv=/tmp/buildvenv/bin/uv \
 && "$uv" python install --no-bin "$TCAD_PYTHON" \
 && "$uv" venv --managed-python --python "$TCAD_PYTHON" /opt/gf180tcad-tcad \
 && uvpip() { "$uv" pip install --python /opt/gf180tcad-tcad/bin/python \
        --require-hashes --no-deps --only-binary=:all: "$@"; } \
 && uvpip --no-binary=rectpack --build-constraints /run/gf180tcad/build-requirements.lock \
        -r /run/gf180tcad/requirements.lock \
 && uvpip -r /run/gf180tcad/gf180mcu.lock \
 && site="$(/opt/gf180tcad-tcad/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" \
 && printf '%s\n' /work/src/third_party/gplugins > "$site/gf180tcad-gplugins.pth" \
 && test "$(/opt/gf180tcad-tcad/bin/python -c 'import platform; print(platform.python_version())')" = "$TCAD_PYTHON" \
 && find /opt/uv-python -name '*.pyc' -delete \
 && find /opt/uv-python -name __pycache__ -type d -empty -delete \
 && chmod -R go-w /opt/uv-python \
 && test -z "$(find /opt/gf180tcad-tcad /opt/uv-python -name '*.pyc' -print -quit)"
USER 1000:1000

# PATH: the TCAD venv first, then exactly the base image's PATH (expanded from it, so there is one
# definition, in docker/base/Dockerfile; test_tcad_environment pins the result).
# The rest of the base ENV (thread variables, DEVSIM_MATH_LIBS, OPENBLAS_CORETYPE,
# PYTHONDONTWRITEBYTECODE, PDK_ROOT, ...) is inherited.
# PDK: gdsfactory imports $PDK as a module and activates it (the base value gf180mcuD is the
# open_pdks variant, not a Python module). PYTHON_CPU_COUNT: Python 3.13 os.cpu_count() returns
# it, so meshwell's import-time n_threads=cpu_count() defaults (and so gmsh) are single-threaded.
ENV PATH=/opt/gf180tcad-tcad/bin:${PATH} \
    VIRTUAL_ENV=/opt/gf180tcad-tcad \
    PDK=gf180mcu \
    PYTHON_CPU_COUNT=1 \
    GF180TCAD_TCAD_BASE_IMAGE=${BASE_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/mithro/gf180-tcad" \
      org.opencontainers.image.title="gf180-tcad-tcad" \
      org.opencontainers.image.description="gf180-tcad base image plus a Python 3.13 TCAD venv (DEVSIM, meshwell, gmsh, gdsfactory, gf180mcu)" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.base.name="${BASE_IMAGE}"

ENTRYPOINT []
CMD ["/bin/bash"]
