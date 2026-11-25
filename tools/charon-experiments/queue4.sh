#!/usr/bin/env bash
# queue4.sh : B4 at a looser HB tolerance, the 2D TRI3 mesh in um, after queue3.
set -uo pipefail
T="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${CX_OUT:?set CX_OUT to a directory outside the repo}"
mkdir -p "$CX_OUT/b4_1e-8" "$CX_OUT/b1_2d"
"$T/sbx.sh" "$CX_OUT/b4_1e-8" "$CX_OUT/b4_1e-8/run.log" -- env CX_REL=1e-8 CX_ABS=1e-10 python3 b4.py
echo "b4 exit=$?"
"$T/sbx.sh" "$CX_OUT/b1_2d" "$CX_OUT/b1_2d/run.log" -- bash -c 'python3 b1.py --only2d && python3 b1an.py'
echo "b1_2d exit=$?"
echo queue4-finished
