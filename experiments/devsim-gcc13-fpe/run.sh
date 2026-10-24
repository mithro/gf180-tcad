#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Re-run the GCC 13.3 DEVSIM "Uncaught FPE" evidence (see README.md):
#   experiments/devsim-gcc13-fpe/run.sh WORKDIR
# WORKDIR must be a new or empty directory outside the repository (the sandbox refuses the repo).
# Needs Docker, the sandbox (tools/sandbox-setup) and network for the build and one PyPI download
# (made inside the sandbox, hash-checked by pip --require-hashes).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
WORK="${1:?usage: run.sh WORKDIR}"
mkdir -p "$WORK"
WORK="$(cd "$WORK" && pwd -P)"
# The last commit whose docker/tcad-dev built DEVSIM with the base image's GCC 13.3 (the next
# commit to touch docker/tcad-dev, b23db01, switched to GCC 14).
GCC13_COMMIT=80c8aaa
# The PyPI devsim 2.11.1 wheel of the stable image (its hash in docker/tcad/requirements.lock).
WHEEL=devsim-2.11.1-cp39-abi3-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl
WHEEL_SHA256=961abda549dffead751c55014882f88bace380b7a616248fca55b1af0bc745b1
TEST=gplugins/devsim/tests/test_stack1d.py::test_parallel_plate_charge
sbx() { "$REPO/tools/sandbox-run" --image "$1" --workdir "$WORK/fork" -- "${@:2}"; }

echo "== 1. build the GCC 13.3 image (docker/tcad-dev at $GCC13_COMMIT), --load"
git -C "$REPO" worktree add --detach "$WORK/src" "$GCC13_COMMIT"
GCC13_IMAGE="$("$WORK/src/docker/tcad-dev/build" --load)"
echo "GCC 13.3 image: $GCC13_IMAGE"

echo "== 2. the fork at the pinned submodule commit, from git archive"
PIN="$(git -C "$REPO" ls-tree HEAD third_party/gplugins | awk '{print $3}')"
mkdir -p "$WORK/fork"
git -C "$REPO/third_party/gplugins" archive "$PIN" | tar -x -C "$WORK/fork"
cp "$HERE/trap_fpe.py" "$WORK/fork/"

echo "== 3. the test in the GCC 13.3 image: expect it to fail with 'Uncaught FPE'"
if sbx "$GCC13_IMAGE" python3 -m pytest -p no:cacheprovider -q "$TEST" > "$WORK/step3.log" 2>&1; then
    echo "run.sh: the test passed with the GCC 13.3 build; the evidence did not reproduce" >&2
    exit 1
fi
grep -m1 "Uncaught FPE" "$WORK/step3.log"

echo "== 4. wheel swap: the PyPI devsim 2.11.1 wheel on PYTHONPATH, same image: expect a pass"
mkdir -p "$WORK/wheel"
printf 'devsim==2.11.1 --hash=sha256:%s\n' "$WHEEL_SHA256" > "$WORK/wheel/requirements.txt"
"$REPO/tools/sandbox-run" --network bridge --workdir "$WORK/wheel" -- \
    /usr/bin/python3 -m pip download --isolated --disable-pip-version-check --no-deps \
    --require-hashes --only-binary=:all: --python-version 3.13 \
    --platform manylinux_2_28_x86_64 -r /work/out/requirements.txt -d /work/out
echo "$WHEEL_SHA256  $WORK/wheel/$WHEEL" | sha256sum -c
mkdir -p "$WORK/fork/_pypidevsim"
python3 -m zipfile -e "$WORK/wheel/$WHEEL" "$WORK/fork/_pypidevsim"
sbx "$GCC13_IMAGE" sh -c "PYTHONPATH=/work/out/_pypidevsim:\$PYTHONPATH \
    python3 -m pytest -p no:cacheprovider -q $TEST"

echo "== 5. gdb trap in the GCC 13.3 image: expect SIGFPE in _Py_dg_dtoa under ObjectHolder::GetString"
sbx "$GCC13_IMAGE" gdb -q -batch -ex run -ex bt --args python3 /work/out/trap_fpe.py \
    > "$WORK/step5.log" 2>&1
grep -m1 "SIGFPE" "$WORK/step5.log"
grep -m1 "_Py_dg_dtoa" "$WORK/step5.log"
grep -m1 "ObjectHolder::GetString" "$WORK/step5.log"

echo "== 6. compiler swap: the pinned GCC 14 dev image: expect a pass and 'no trap'"
DEV_IMAGE="$(cat "$REPO/docker/TCAD_DEV_IMAGE")"
sbx "$DEV_IMAGE" python3 -m pytest -p no:cacheprovider -q "$TEST"
sbx "$DEV_IMAGE" gdb -q -batch -ex run --args python3 /work/out/trap_fpe.py > "$WORK/step6.log" 2>&1
grep -m1 "no trap" "$WORK/step6.log"

git -C "$REPO" worktree remove --force "$WORK/src"
