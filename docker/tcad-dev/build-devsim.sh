#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build the DEVSIM wheel from source, in the build stage of docker/tcad-dev/Dockerfile:
#   build-devsim.sh SRC_DIR WORK_DIR WHEEL_DIR PYTHON BUILD_CONSTRAINTS WHEELHOUSE
# SRC_DIR holds the hash-checked downloads of fetch_sources.py (each upstream.json entry's
# ``file``), WHEELHOUSE those of wheelhouse.json (the build backend comes from there).
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
SRC="${1:?}" WORK="${2:?}" WHEELS="${3:?}" PY="${4:?}" CONSTRAINTS="${5:?}" WHEELHOUSE="${6:?}"
UPSTREAM="$SRC/upstream.json"
field() { "$PY" -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]][sys.argv[3]])' \
    "$UPSTREAM" "$1" "$2"; }
commit() { field "$1" commit; }
src_file() { echo "$SRC/$(field "$1" file)"; }  # where fetch_sources.py saved upstream.json's NAME

untar() {  # untar NAME DIR: a codeload tarball has one top-level directory
    mkdir -p "$2"
    tar -xzf "$(src_file "$1")" -C "$2" --strip-components=1 --no-same-owner
}
untar devsim "$WORK"
cd "$WORK"
untar symdiff external/symdiff
untar umfpack_lgpl external/umfpack_lgpl
untar boost_config external/boostorg/config
untar boost_math external/boostorg/math
untar boost_multiprecision external/boostorg/multiprecision

# GCC 14 (C, C++ and Fortran), unpacked into this throwaway build stage only. Upstream's x86_64
# wheels are built with GCC 14 (manylinux_2_28's gcc-toolset-14); the base image has only GCC 13
# and no Fortran. These are Ubuntu 24.04's GCC 14.2 packages, the build whose runtime
# (gcc-14-base, libstdc++6, libgfortran5, libquadmath0) the base image already has.
for deb in cpp-14-x86-64-linux-gnu gcc-14-x86-64-linux-gnu g++-14-x86-64-linux-gnu \
        gfortran-14-x86-64-linux-gnu libgcc-14-dev libstdc++-14-dev libgfortran-14-dev; do
    dpkg-deb -x "$(src_file "$deb")" /
done

export DEVSIM_CONFIG=centos_6 CMAKE=cmake CMAKE_CXX_FLAGS="" \
    CC=/usr/bin/x86_64-linux-gnu-gcc-14 CXX=/usr/bin/x86_64-linux-gnu-g++-14 \
    F77=/usr/bin/x86_64-linux-gnu-gfortran-14
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

# the wheel (setup.py, py-limited-api cp39), its setuptools from the hash-checked constraints,
# found in the fetched wheelhouse (no index)
"$UV" build --wheel --python "$PY" --out-dir "$WHEELS" --no-index --find-links "$WHEELHOUSE" \
    --build-constraints "$CONSTRAINTS" --require-hashes "$DIST"

# The build record (the wheel's VERSION file is not packaged: its data_files are the *.* files):
# the commit built, the sha256 of the extension module and the compilers that built it (the
# .comment section, one string per compiler). docker/tcad-dev/probe_versions.py checks the
# installed module against it and reports it in versions.json.
"$PY" - "$(commit devsim)" "$DIST/lib/devsim/devsim_py3.so" "$WHEELS/devsim-build.json" <<'PYEOF'
import hashlib, json, subprocess, sys
commit, so, out = sys.argv[1:]
comment = subprocess.run(["readelf", "-p", ".comment", so], capture_output=True, text=True,
                         check=True).stdout
strings = sorted({line.split("]", 1)[1].strip() for line in comment.splitlines() if "]" in line})
with open(so, "rb") as f:
    sha = hashlib.sha256(f.read()).hexdigest()
record = {"commit": commit, "compilers": strings, "devsim_py3.so sha256": sha}
with open(out, "w", encoding="utf-8") as f:
    f.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
PYEOF
