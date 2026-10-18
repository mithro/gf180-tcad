# SPDX-License-Identifier: Apache-2.0
"""Download the non-PyPI sources of the dev-HEAD TCAD image and check their sha256.

Runs in the build stage of docker/tcad-dev/Dockerfile with the base image's /usr/bin/python3:
    fetch_sources.py UPSTREAM_JSON OUT_DIR NAME...
Each NAME is a key of upstream.json; its ``url`` is saved as OUT_DIR/NAME and must hash to its
``sha256``, or the build fails. Nothing is unpacked here.
"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path


def fetch(entry: dict, dest: Path) -> None:
    h = hashlib.sha256()
    with urllib.request.urlopen(entry["url"], timeout=300) as resp, dest.open("wb") as out:
        while chunk := resp.read(1 << 20):
            h.update(chunk)
            out.write(chunk)
    if h.hexdigest() != entry["sha256"]:
        sys.exit(f"fetch_sources: {entry['url']}: sha256 {h.hexdigest()} != {entry['sha256']}")


def main() -> None:
    manifest, out_dir, *names = sys.argv[1:]
    if not names:
        sys.exit("usage: fetch_sources.py UPSTREAM_JSON OUT_DIR NAME...")
    upstream = json.loads(Path(manifest).read_text(encoding="utf-8"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name in names:
        fetch(upstream[name], out / name)
        print(f"fetch_sources: {name} ok ({upstream[name]['sha256']})", flush=True)


if __name__ == "__main__":
    main()
