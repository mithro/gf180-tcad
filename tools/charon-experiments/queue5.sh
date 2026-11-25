#!/usr/bin/env bash
# queue5.sh : the full grid through inversion with LOCA sub-steps (5 per grid step) and with the
# constant predictor, short lifetimes (B2), after queue4.
set -uo pipefail
T="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${CX_OUT:?set CX_OUT to a directory outside the repo}"
export CX_VGMAX=
CX_TAU=1e-15 CX_SUB=5 "$T/run_b2.sh" nfet_05v0 calibrated 1e-10 1e-12 klu2
CX_TAU=1e-14 CX_SUB=5 "$T/run_b2.sh" nfet_05v0 calibrated 1e-10 1e-12 klu2
CX_TAU=1e-15 CX_PRED=constant "$T/run_b2.sh" nfet_05v0 calibrated 1e-10 1e-12 klu2
echo queue5-finished
