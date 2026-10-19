# SPDX-License-Identifier: Apache-2.0
"""Point the dev-HEAD TCAD image build at the inputs fetch_sources.py fetched (no index, no URL).

Runs in the build stage of docker/tcad-dev/Dockerfile with the base image's /usr/bin/python3:
    local_inputs.py python-mirror UPSTREAM_JSON SRC_DIR MIRROR_DIR
        moves the fetched CPython (upstream.json ``cpython``) to MIRROR_DIR/<release>/<file>, the
        layout ``uv python install --mirror file://MIRROR_DIR`` reads;
    local_inputs.py lock UPSTREAM_JSON LOCK SRC_DIR OUT
        writes LOCK to OUT with each ``name @ <upstream.json url>`` requirement (meshwell,
        gdsfactory, gf180mcu, gmsh) pointing at the fetched copy SRC_DIR/<file> instead. The
        ``--hash`` lines stay, so uv still checks the copy against the lock (the lock's hash of
        each is upstream.json's sha256: tests/test_tcad_dev_lock.py).
"""

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


def main() -> None:
    cmd, *args = sys.argv[1:]
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
