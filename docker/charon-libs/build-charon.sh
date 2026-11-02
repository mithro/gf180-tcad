#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build Charon 2.2.0 together with its pinned Trilinos, Charon's own recipe (build_charon.py with
# an opts file, then make, make install), in docker/charon-libs/Dockerfile.
#   build-charon.sh prepare SRC_DIR TREE CONTEXT
#       unpack the fetched tarballs into TREE (TREE/tcad-charon with Trilinos inside it, as
#       Charon's ExtraRepositoriesList.cmake expects, and TREE/TriBITS), check the opts copy
#       against the tarball, and apply CONTEXT/patches/*.patch in name order
#   build-charon.sh build TREE BUILD_DIR PREFIX JOBS CONTEXT
#       configure (build_charon.py, CONTEXT/opts/gf180.opts as General.opts), make -j JOBS,
#       make install into PREFIX, run the build-time probe (the upstream nightly tests named in
#       PROBE_TESTS) and write PREFIX/share/gf180tcad/charon-build.json
# Neither mode uses the network. Timing and peak memory go to the build log only (GNU time),
# never into PREFIX, so the installed bytes do not depend on the host or on JOBS.
set -euo pipefail

PROBE_TESTS='pmoscap\.nlp$|loca-moscap-cv|pndiode'

prepare() {
    local src="$1" tree="$2" ctx="$3"
    mkdir -p "$tree/tcad-charon" "$tree/TriBITS"
    tar -xzf "$src/charon-distrib-v2_2.tar.gz" -C "$tree"
    mkdir -p "$tree/tcad-charon/Trilinos"
    tar -xzf "$src"/Trilinos-*.tar.gz -C "$tree/tcad-charon/Trilinos" --strip-components=1
    tar -xzf "$src"/TriBITS-*.tar.gz -C "$tree/TriBITS" --strip-components=1
    /usr/bin/python3 -I "$ctx/inputs.py" check-opts "$ctx/upstream.json" "$tree/tcad-charon" \
        "$ctx/opts/gf180.opts"
    local p
    for p in "$ctx"/patches/*.patch; do
        echo "build-charon: applying ${p##*/}"
        patch -p1 --forward --batch -d "$tree/tcad-charon" < "$p"
    done
}

build() {
    local tree="$1" bld="$2" prefix="$3" jobs="$4" ctx="$5"
    mkdir -p "$bld"
    cd "$bld"
    # A General.opts in the current directory is the only opts file build_charon.py reads.
    cp "$ctx/opts/gf180.opts" General.opts
    export TRIBITS_BASE_DIR="$tree/TriBITS"
    echo "build-charon: configure $(date -u +%FT%TZ)"
    /usr/bin/python3 "$tree/tcad-charon/scripts/build/all/build_charon.py" -b release \
        -r "CMAKE_INSTALL_PREFIX:$prefix" "$tree/tcad-charon"
    echo "build-charon: make -j$jobs $(date -u +%FT%TZ)"
    /usr/bin/time -v make -j"$jobs"
    echo "build-charon: make install $(date -u +%FT%TZ)"
    make install
    echo "build-charon: probe $(date -u +%FT%TZ)"
    # The upstream tests start 4 MPI ranks with mpiexec: as root in the build container, more
    # ranks than JOBS cores, shared memory only (no network, no ptrace single-copy).
    export OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 \
        OMPI_MCA_rmaps_base_oversubscribe=1 OMPI_MCA_btl=self,vader \
        OMPI_MCA_btl_vader_single_copy_mechanism=none
    ctest -R "$PROBE_TESTS" --output-on-failure
    echo "build-charon: done $(date -u +%FT%TZ)"
}

case "${1:-}" in
    prepare) shift; prepare "$@" ;;
    build) shift; build "$@" ;;
    *) echo "usage: build-charon.sh prepare SRC TREE CONTEXT | build TREE BUILD PREFIX JOBS CONTEXT" >&2
       exit 2 ;;
esac
