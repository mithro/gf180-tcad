#!/usr/bin/env bash
# run_b2.sh DEV PARAMS REL ABS LIN [NI] : one B2 sweep set in its own directory, then analysis.
set -uo pipefail
E="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; OUT="${CX_OUT:?set CX_OUT to a directory outside the repo}"
dev=$1 params=$2 rel=$3 abs=$4 lin=$5 ni=${6:-ni}
d=$OUT/b2/${dev}_${params}_${ni}_${lin}_${rel}
rm -rf "$d"; mkdir -p "$d"
"$E/sbx.sh" "$d" "$d/run.log" -- env CX_REL=$rel CX_ABS=$abs CX_LIN=$lin python3 b2.py $dev $params $ni
rc=$?
echo "b2 exit=$rc" >> "$d/run.log"
if [ $rc -eq 0 ]; then
  "$E/sbx.sh" "$d" "$d/an.log" -- python3 b2an.py $dev $params $(basename $d)
  echo "an exit=$?" >> "$d/an.log"
fi
echo "done $d rc=$rc"
