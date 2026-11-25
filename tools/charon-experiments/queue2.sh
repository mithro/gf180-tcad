#!/usr/bin/env bash
# queue2.sh : the SRH-lifetime variants of B2, the B4 rerun and the analyses (one container at a time).
set -uo pipefail
T="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${CX_OUT:?set CX_OUT to a directory outside the repo}"
"$T/sbx.sh" "$CX_OUT/b2tau" "$CX_OUT/b2tau/run2.log" -- env CX_VEND=5.0 python3 b2h.py tau_1e-15 tau_1e-13 tau_1e-14 tau_1e-15_step_5mV tau_1e-12_tol_1e-8
echo "b2tau exit=$?"
mkdir -p "$CX_OUT/b4"
"$T/sbx.sh" "$CX_OUT/b4" "$CX_OUT/b4/run2.log" -- python3 b4.py
echo "b4 exit=$?"
"$T/sbx.sh" "$CX_OUT/b1" "$CX_OUT/b1/an.log" -- python3 b1an.py
echo "b1an exit=$?"
for v in 1e-10 1e-8; do
    d="$CX_OUT/b2/nfet_05v0_calibrated_ni_klu2_$v"
    "$T/sbx.sh" "$d" "$d/an.log" -- env CX_VGMAX=0.35 python3 b2an.py nfet_05v0 calibrated "klu2_$v"
    echo "b2an $v exit=$?"
done
echo queue2-finished
