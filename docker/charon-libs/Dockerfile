# SPDX-License-Identifier: Apache-2.0
# gf180-tcad charon-libs image: Charon 2.2.0 built together with the Trilinos and TriBITS commits
# its user manual pins (Table 2-1), from Sandia's official source tarball, with Charon's own
# recipe (build_charon.py + General.opts + Linux.opts) plus the project lines and patches in this
# directory. The result is the base image (docker/IMAGE) plus /opt/charon. Charon is
# GPL-3.0-or-later: README.md here states what that means for this image and where the
# corresponding source is. Build with docker/charon-libs/build.
#
# Stages: `deps` fetches every input of upstream.json (the only step with a network), checks
# each sha256, installs the pinned build-only .debs and unpacks and patches the sources;
# `build` configures, compiles and installs Charon and Trilinos into /opt/charon and runs the
# upstream nightly tests named in build-charon.sh as the build-time probe; the image copies
# /opt/charon onto the base image, so no compiler, -dev package or source tree is left in it.
ARG BASE_IMAGE

FROM ${BASE_IMAGE} AS deps
ARG SOURCE_DATE_EPOCH
USER root
ENV HOME=/tmp/home
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# 1. Every input, from the gf180-tcad input mirror first, then its original URL, sha256-checked.
RUN --mount=type=bind,source=upstream.json,target=/run/gf180tcad/upstream.json \
    --mount=type=bind,source=fetch_sources.py,target=/run/gf180tcad/fetch_sources.py \
    --mount=type=bind,source=inputs.py,target=/run/gf180tcad/inputs.py \
    set -eu \
 && mkdir -p "$HOME" \
 && read -ra names <<< "$(/usr/bin/python3 -I /run/gf180tcad/inputs.py names /run/gf180tcad/upstream.json)" \
 && /usr/bin/python3 -I /run/gf180tcad/fetch_sources.py /run/gf180tcad/upstream.json \
        /opt/build/src "${names[@]}"

# 2. The build-only packages (their dependencies first; none replaces a base image package),
#    then the sources unpacked and patched.
RUN --network=none \
    --mount=type=bind,source=upstream.json,target=/run/gf180tcad/ctx/upstream.json \
    --mount=type=bind,source=inputs.py,target=/run/gf180tcad/ctx/inputs.py \
    --mount=type=bind,source=build-charon.sh,target=/run/gf180tcad/ctx/build-charon.sh \
    --mount=type=bind,source=opts,target=/run/gf180tcad/ctx/opts \
    --mount=type=bind,source=patches,target=/run/gf180tcad/ctx/patches \
    set -eu \
 && mapfile -t debs < <(/usr/bin/python3 -I /run/gf180tcad/ctx/inputs.py debs \
        /run/gf180tcad/ctx/upstream.json /opt/build/src) \
 && dpkg -i "${debs[@]}" \
 && bash /run/gf180tcad/ctx/build-charon.sh prepare /opt/build/src /opt/build /run/gf180tcad/ctx \
 && rm -f /opt/build/src/*.deb

FROM deps AS build
ARG SOURCE_DATE_EPOCH
# Compile jobs; the installed bytes do not depend on it.
ARG JOBS=2

# 3. Configure, make, install, probe. Then the build record and the corresponding-source list.
RUN --network=none \
    --mount=type=bind,source=upstream.json,target=/run/gf180tcad/ctx/upstream.json \
    --mount=type=bind,source=inputs.py,target=/run/gf180tcad/ctx/inputs.py \
    --mount=type=bind,source=build-charon.sh,target=/run/gf180tcad/ctx/build-charon.sh \
    --mount=type=bind,source=opts,target=/run/gf180tcad/ctx/opts \
    --mount=type=bind,source=patches,target=/run/gf180tcad/ctx/patches \
    set -eu \
 && bash /run/gf180tcad/ctx/build-charon.sh build /opt/build /opt/build/build /opt/charon \
        "$JOBS" /run/gf180tcad/ctx \
 && install -d -m 0755 /opt/charon/share/gf180tcad /opt/charon/share/doc/charon \
 && /usr/bin/python3 -I /run/gf180tcad/ctx/inputs.py sources /run/gf180tcad/ctx/upstream.json \
        /run/gf180tcad/ctx /opt/charon/share/gf180tcad/SOURCES.json \
 && install -m 0644 /run/gf180tcad/ctx/upstream.json /opt/charon/share/gf180tcad/upstream.json \
 && cp -r /opt/build/tcad-charon/LICENSE/. /opt/charon/share/doc/charon/ \
 && chmod -R go-w,a+rX /opt/charon

FROM ${BASE_IMAGE}
ARG BASE_IMAGE
COPY --from=build /opt/charon /opt/charon
USER 1000:1000
ENV PATH=/opt/charon/bin:${PATH} \
    GF180TCAD_CHARON_BASE_IMAGE=${BASE_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/mithro/gf180-tcad/releases/tag/gf180-tcad/inputs/charon-20261102" \
      org.opencontainers.image.title="gf180-tcad-charon-libs" \
      org.opencontainers.image.description="gf180-tcad base image plus Charon 2.2.0 and Trilinos built from source in /opt/charon" \
      org.opencontainers.image.licenses="GPL-3.0-or-later AND BSD-3-Clause AND LGPL-2.1-or-later AND Apache-2.0" \
      org.opencontainers.image.base.name="${BASE_IMAGE}"

ENTRYPOINT []
CMD ["/bin/bash"]
