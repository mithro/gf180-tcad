#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build Charon 2.2.0 together with its pinned Trilinos, Charon's own recipe (build_charon.py with
# upstream's opts files plus the project's, then make, make install), in
# docker/charon-libs/Dockerfile.
#   build-charon.sh prepare SRC_DIR TREE CONTEXT
#       unpack the fetched tarballs into TREE (TREE/tcad-charon with Trilinos inside it, as
#       Charon's ExtraRepositoriesList.cmake expects, and TREE/TriBITS), check the tarball's
#       opts files against upstream.json, and apply CONTEXT/patches/*.patch in name order
#   build-charon.sh build TREE BUILD_DIR PREFIX JOBS CONTEXT
#       configure (build_charon.py: the tarball's General.opts and Linux.opts, then
#       CONTEXT/opts/gf180.opts), make -j JOBS, make install into PREFIX, run the build-time
#       probe (the upstream nightly tests in PROBE_TESTS, all of which must run and pass) and
#       write PREFIX/share/gf180tcad/charon-build.json
#   build-charon.sh check-runtime PREFIX
#       every ELF file under PREFIX finds all its shared libraries (run in the final image)
# No mode uses the network. Timing and peak memory go to the build log only (GNU time), never
# into PREFIX, so the installed bytes do not depend on the host or on JOBS.
set -euo pipefail

# The build-time probe: upstream nightly tests, by their registered names (exact matches).
PROBE_TESTS=(
    Charon_charon_mp_pmoscap.nlp
    Charon_charon_mp.hb.loca-moscap-cv.ox
    Charon_charon_mp.hb.loca-moscap-cv.sub
    Charon_charon_mp_pndiode.nlp
)

prepare() {
    local src="$1" tree="$2" ctx="$3"
    mkdir -p "$tree/tcad-charon" "$tree/TriBITS"
    tar -xzf "$src/charon-distrib-v2_2.tar.gz" -C "$tree"
    mkdir -p "$tree/tcad-charon/Trilinos"
    tar -xzf "$src"/Trilinos-*.tar.gz -C "$tree/tcad-charon/Trilinos" --strip-components=1
    tar -xzf "$src"/TriBITS-*.tar.gz -C "$tree/TriBITS" --strip-components=1
    # The tarballs carry their authors' modes (some owner-only); everyone may read the tree.
    chmod -R a+rX,go-w "$tree"
    /usr/bin/python3 -I "$ctx/inputs.py" check-opts "$ctx/upstream.json" "$tree/tcad-charon"
    local p
    for p in "$ctx"/patches/*.patch; do
        echo "build-charon: applying ${p##*/}"
        patch -p1 --forward --batch -d "$tree/tcad-charon" < "$p"
    done
}

build() {
    local tree="$1" bld="$2" prefix="$3" jobs="$4" ctx="$5"
    local optdir="$tree/tcad-charon/scripts/build/all"
    mkdir -p "$bld"
    cd "$bld"
    # build_charon.py reads only a General.opts in the current directory when one exists, and
    # an opts file named after the host or $SNLSYSTEM when one exists: allow neither.
    [ ! -e General.opts ] || { echo "build-charon: $bld/General.opts exists" >&2; exit 1; }
    unset SNLSYSTEM
    /usr/bin/python3 -I "$ctx/inputs.py" check-opts "$ctx/upstream.json" "$tree/tcad-charon"
    export TRIBITS_BASE_DIR="$tree/TriBITS"
    echo "build-charon: configure $(date -u +%FT%TZ)"
    # gf180.opts sets the image's prefix /opt/charon; -r resets it to PREFIX, so that a
    # development build in tools/sandbox-run can install elsewhere (build_charon.py fails if the
    # option to reset is missing).
    /usr/bin/python3 "$optdir/build_charon.py" -c "$optdir" -f "$ctx/opts/gf180.opts" \
        -b release -r "CMAKE_INSTALL_PREFIX:$prefix" "$tree/tcad-charon"
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
    local t regex=""
    for t in "${PROBE_TESTS[@]}"; do
        regex+="${regex:+|}${t//./\\.}"
    done
    regex="^(${regex})\$"
    # Every probe test must be registered: ctest -N lists exactly as many as PROBE_TESTS names.
    local listed
    listed="$(ctest -N -L nightly -R "$regex" | sed -n 's/^Total Tests: //p')"
    if [ "$listed" != "${#PROBE_TESTS[@]}" ]; then
        echo "build-charon: $listed probe tests registered, want ${#PROBE_TESTS[@]}" >&2
        exit 1
    fi
    ctest -L nightly -R "$regex" --no-tests=error --output-on-failure
    install -d -m 0755 "$prefix/share/gf180tcad"
    /usr/bin/python3 -I "$ctx/inputs.py" record "$ctx/upstream.json" "$ctx" \
        "$prefix/share/gf180tcad/charon-build.json" "${PROBE_TESTS[@]}"
    echo "build-charon: done $(date -u +%FT%TZ)"
}

check_runtime() {
    local prefix="$1" f out bad=0
    [ -x "$prefix/bin/charon_mp.exe" ] || { echo "build-charon: no $prefix/bin/charon_mp.exe" >&2; exit 1; }
    while IFS= read -r -d '' f; do
        [ "$(head -c 4 "$f" | od -An -tx1 | tr -d ' \n')" = 7f454c46 ] || continue
        # A static or relocatable ELF file has no shared libraries to find.
        out="$(ldd "$f" 2>&1)" || {
            grep -q 'not a dynamic executable' <<<"$out" && continue
            echo "build-charon: ldd $f: $out" >&2; bad=1; continue
        }
        if grep -q 'not found' <<<"$out"; then
            echo "build-charon: $f: $(grep 'not found' <<<"$out" | tr -s ' \t\n' ' ')" >&2
            bad=1
        fi
    done < <(find "$prefix" -type f -print0)
    [ "$bad" = 0 ] || exit 1
    echo "build-charon: every ELF file under $prefix finds its shared libraries"
}

case "${1:-}" in
    prepare) shift; prepare "$@" ;;
    build) shift; build "$@" ;;
    check-runtime) shift; check_runtime "$@" ;;
    *) echo "usage: build-charon.sh prepare SRC TREE CONTEXT | build TREE BUILD PREFIX JOBS CONTEXT | check-runtime PREFIX" >&2
       exit 2 ;;
esac
