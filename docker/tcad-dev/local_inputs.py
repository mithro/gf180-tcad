# SPDX-License-Identifier: Apache-2.0
"""Point the dev-HEAD TCAD image build at the inputs fetch_sources.py fetched (no index, no URL).

Runs in the build stage of docker/tcad-dev/Dockerfile with the base image's /usr/bin/python3:
    local_inputs.py python-mirror UPSTREAM_JSON SRC_DIR MIRROR_DIR
        moves the fetched CPython (upstream.json ``cpython``) to MIRROR_DIR/<release>/<file>, the
        layout ``uv python install --mirror file://MIRROR_DIR`` reads
        (https://docs.astral.sh/uv/reference/cli/#uv-python-install);
    local_inputs.py lock UPSTREAM_JSON LOCK SRC_DIR OUT
        writes LOCK to OUT with each ``name @ <upstream.json url>`` requirement (meshwell,
        gdsfactory, gf180mcu, gmsh) pointing at the fetched copy SRC_DIR/<file> instead. The
        ``--hash`` lines stay, so uv still checks the copy against the lock (the lock's hash of
        each is upstream.json's sha256: tests/test_tcad_dev_lock.py);
    local_inputs.py strip-uv-cache SITE_PACKAGES
        deletes each ``*.dist-info/uv_cache.json`` and its RECORD line. uv writes that file for
        a package installed from a local file (here: every package, fetched first): uv's own
        cache key, holding the file's timestamp, which no build can reproduce. It is not part of
        the package, and an install from a URL (as before the mirror) has none.
"""

import csv
import io
import json
import shutil
import sys
from pathlib import Path

URL_INSTALLED = ("meshwell", "gdsfactory", "gf180mcu", "gmsh")


def python_mirror(upstream: dict, src: Path, mirror: Path) -> None:
    e = upstream["cpython"]
    dest = mirror / e["release"]
    dest.mkdir(parents=True, exist_ok=True)
    shutil.move(src / e["file"], dest / e["file"])
    print(f"local_inputs: CPython at {dest / e['file']}", flush=True)


def lock(upstream: dict, text: str, src: Path) -> str:
    for name in URL_INSTALLED:
        old = f"{name} @ {upstream[name]['url']} "
        if text.count(old) != 1:
            sys.exit(f"local_inputs: {name}: {upstream[name]['url']} is not in the lock once")
        text = text.replace(old, f"{name} @ {(src / upstream[name]['file']).as_uri()} ")
    return text


# The keys of uv's cache-info file (uv 0.13.1); anything else is not stripped blindly.
UV_CACHE_KEYS = {"timestamp", "commit", "tags", "env", "directories"}


def strip_uv_cache(site: Path) -> None:
    n = 0
    for cache in sorted(site.glob("*.dist-info/uv_cache.json")):
        if set(json.loads(cache.read_text(encoding="utf-8"))) != UV_CACHE_KEYS:
            sys.exit(f"local_inputs: {cache}: not uv's cache-info file")
        record = cache.parent / "RECORD"
        name = f"{cache.parent.name}/uv_cache.json"
        rows = list(csv.reader(io.StringIO(record.read_text(encoding="utf-8"))))
        kept = [r for r in rows if r[0] != name]
        if len(kept) != len(rows) - 1:
            sys.exit(f"local_inputs: {record} does not list {name} once")
        out = io.StringIO()
        csv.writer(out, lineterminator="\n").writerows(kept)
        record.write_text(out.getvalue(), encoding="utf-8")
        cache.unlink()
        n += 1
    print(f"local_inputs: stripped uv_cache.json from {n} dist-infos", flush=True)


def main() -> None:
    cmd, *args = sys.argv[1:]
    if cmd == "strip-uv-cache" and len(args) == 1:
        strip_uv_cache(Path(args[0]))
        return
    upstream = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    if cmd == "python-mirror" and len(args) == 3:
        python_mirror(upstream, Path(args[1]), Path(args[2]))
    elif cmd == "lock" and len(args) == 4:
        text = lock(upstream, Path(args[1]).read_text(encoding="utf-8"), Path(args[2]))
        Path(args[3]).write_text(text, encoding="utf-8")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
