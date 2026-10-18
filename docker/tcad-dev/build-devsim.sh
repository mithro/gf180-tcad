#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build the DEVSIM wheel from source, in the build stage of docker/tcad-dev/Dockerfile:
#   build-devsim.sh SRC_DIR WORK_DIR WHEEL_DIR PYTHON BUILD_CONSTRAINTS
# SRC_DIR holds the hash-checked downloads of fetch_sources.py (names from upstream.json).
#
# This follows DEVSIM's own x86_64 Linux release recipe, scripts/build_manylinux_2_28.sh at the
# pinned commit: DEVSIM_CONFIG=centos_6 (extended precision with the quad-precision getrf,
# MKL PARDISO loaded at run time if present, BLAS/LAPACK dlopen()ed from DEVSIM_MATH_LIBS),
# symdiff, getrf and umfpack_lgpl first, then DEVSIM, then dist/package_linux.sh and
# dist/bdist_wheel/setup.py. Differences, none of which changes the compiled code:
# - the submodules are the codeload tarballs of the gitlinks of the pinned commit (only those the
#   centos_6 configuration uses: symdiff, umfpack_lgpl and boostorg/{config,math,multiprecision};
#   eigen and superlu are not used by it);
# - package_linux.sh is re-done below with cp instead of rsync and without git (the tarball has
#   no .git; the VERSION file gets the pinned commit instead of `git rev-parse HEAD`);
# - no auditwheel repair: the wheel is installed only into this image, whose base provides the
#   shared libraries (libquadmath, libgfortran) that auditwheel would bundle;
# - the Python is the image's CPython 3.13 (upstream builds with 3.9; the wheel is abi3, cp39).
set -euo pipefail

UV="${UV:?set UV to the uv binary}"
SRC="${1:?}" WORK="${2:?}" WHEELS="${3:?}" PY="${4:?}" CONSTRAINTS="${5:?}"
UPSTREAM="$SRC/upstream.json"
commit() { "$PY" -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]]["commit"])' \
    "$UPSTREAM" "$1"; }

untar() {  # untar NAME DIR: a codeload tarball has one top-level directory
    mkdir -p "$2"
    tar -xzf "$SRC/$1" -C "$2" --strip-components=1 --no-same-owner
}
untar devsim "$WORK"
cd "$WORK"
untar symdiff external/symdiff
untar umfpack_lgpl external/umfpack_lgpl
untar boost_config external/boostorg/config
untar boost_math external/boostorg/math
untar boost_multiprecision external/boostorg/multiprecision

# gfortran 13 (the base image has gcc/g++ 13.3.0 of the same Ubuntu build, but no Fortran):
# unpacked into this throwaway build stage only.
dpkg-deb -x "$SRC/gfortran-13-x86-64-linux-gnu" /
dpkg-deb -x "$SRC/libgfortran-13-dev" /

export DEVSIM_CONFIG=centos_6 CMAKE=cmake CMAKE_CXX_FLAGS="" CC=gcc CXX=g++ \
    F77=/usr/bin/x86_64-linux-gnu-gfortran-13
PYTHON3_INCLUDE="$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["include"])')"
export PYTHON3_INCLUDE PYTHON3_ARCHIVE=""
# not nproc: it honours the base image's OMP_NUM_THREADS=1
JOBS="$(getconf _NPROCESSORS_ONLN)"
ARCH="$(uname -m)"
[ "$ARCH" = x86_64 ] || { echo "build-devsim: only x86_64 is supported, not $ARCH" >&2; exit 2; }

# scripts/build_manylinux_2_28.sh, x86_64 branch
(cd external/symdiff && bash ../symdiff_centos.sh && cd "linux_${ARCH}_release" && make -j"$JOBS")
(cd external/getrf && bash setup_centos6.sh && cd build && make -j"$JOBS")
(cd external/umfpack_lgpl && bash setup_centos6.sh && cd build && make -j"$JOBS")
bash scripts/setup_centos_6.sh
(cd "linux_${ARCH}_release" && make -j"$JOBS")

# dist/package_linux.sh (DIST_DIR=dist/devsim), with cp for rsync and the pinned commit for git
SRC_DIR="linux_${ARCH}_release/src/main"
DIST=dist/devsim
mkdir -p "$DIST/bin" "$DIST/lib/devsim" "$DIST/doc" "$DIST/examples/symdiff"
cp "$SRC_DIR/devsim_py3.so" dist/__init__.py "$DIST/lib/devsim/"
cp -a external/symdiff/lib/symdiff "$DIST/lib/"
cp doc/devsim.pdf external/symdiff/doc/symdiff.pdf "$DIST/doc/"
cp ./*.md NOTICE LICENSE "$DIST/"
cp -a examples testing "$DIST/"
cp -a python_packages umfpack "$DIST/lib/devsim/"
cp external/umfpack_lgpl/build/libumfpack_lgpl.so "$DIST/lib/devsim/umfpack/"
cp -a external/symdiff/examples/. "$DIST/examples/symdiff/"
printf 'Source available from:\nhttps://github.com/devsim/devsim\ncommit %s\n' \
    "$(commit devsim)" > "$DIST/VERSION"
cp dist/bdist_wheel/setup.* "$DIST/"

# the wheel (setup.py, py-limited-api cp39), its setuptools from the hash-checked constraints
"$UV" build --wheel --python "$PY" --out-dir "$WHEELS" \
    --build-constraints "$CONSTRAINTS" --require-hashes "$DIST"
