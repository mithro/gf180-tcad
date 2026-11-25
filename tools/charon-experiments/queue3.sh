#!/usr/bin/env bash
# queue3.sh : the full C-V grids with short SRH lifetimes (the lifetime-independence and noise
# checks of B2/B7), one container at a time.
set -uo pipefail
T="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${CX_OUT:?set CX_OUT to a directory outside the repo}"
export CX_VGMAX=
CX_TAU=1e-15 "$T/run_b2.sh" nfet_05v0 calibrated 1e-10 1e-12 klu2
CX_TAU=1e-14 "$T/run_b2.sh" nfet_05v0 calibrated 1e-10 1e-12 klu2
CX_TAU=1e-15 "$T/run_b2.sh" nfet_05v0 calibrated 1e-9 1e-11 klu2
CX_TAU=1e-15 "$T/run_b2.sh" pfet_05v0 calibrated 1e-10 1e-12 klu2
echo queue3-finished
