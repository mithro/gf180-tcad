#!/usr/bin/env bash
# sbx.sh EXPDIR LOG -- CMD...   : run CMD in the charon image, workdir EXPDIR, one job at a time.
set -euo pipefail
D="$1"; LOG="$2"; shift 3
W="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
n=$(docker ps --format '{{.Names}} {{.Image}}' | grep -c "^gf180tcad-" || true)
echo "running containers: $n; $(systemctl show gf180-tcad.slice -p MemoryCurrent 2>&1)" >&2
docker ps --format '{{.Names}} {{.Image}}' >&2
if [ "$n" -ge 2 ]; then echo "two or more TCAD containers running; refusing" >&2; exit 75; fi
mkdir -p "$D"; cp "$W"/tools/charon-experiments/*.py "$D"/
set -o pipefail
~/github/mithro/gf180-tcad/tools/sandbox-run --mem 2g --cpus 1 --network none --image "$(cat $W/docker/CHARON_IMAGE)" --workdir "$D" -- "$@" > "$LOG" 2>&1
