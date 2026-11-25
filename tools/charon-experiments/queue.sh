#!/usr/bin/env bash
# queue.sh : run the Task B experiments one after another (one 2 GiB container at a time).
# CX_OUT must name a directory outside the repository; each experiment writes its own subdirectory.
set -uo pipefail
T="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${CX_OUT:?set CX_OUT to a directory outside the repo}"
export CX_VGMAX=0.35  # the drift-diffusion sweep does not converge into inversion (B2)
"$T/run_b2.sh" nfet_05v0 calibrated 1e-10 1e-12 klu2
"$T/run_b2.sh" nfet_05v0 calibrated 1e-11 1e-13 klu2
"$T/run_b2.sh" nfet_05v0 calibrated 1e-8 1e-10 klu2
for x in b5 b3 b4 b1; do
    mkdir -p "$CX_OUT/$x"
    "$T/sbx.sh" "$CX_OUT/$x" "$CX_OUT/$x/run.log" -- python3 "$x.py"
    echo "$x exit=$?" | tee -a "$CX_OUT/$x/run.log"
done
echo queue-finished
