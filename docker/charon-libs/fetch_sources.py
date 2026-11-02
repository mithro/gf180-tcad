# SPDX-License-Identifier: Apache-2.0
"""Download the build inputs of the dev-HEAD TCAD image and check their sha256.

Runs in the build stage of docker/tcad-dev/Dockerfile with the base image's /usr/bin/python3:
    fetch_sources.py UPSTREAM_JSON OUT_DIR NAME...         (entries of upstream.json)
    fetch_sources.py --wheelhouse WHEELHOUSE_JSON OUT_DIR  (every file of wheelhouse.json)
Each entry is saved as OUT_DIR/<its ``file``> (upstream.json) or OUT_DIR/<its key> (wheelhouse.json,
the PyPI file name). It is fetched from its ``mirror_url`` (gf180-tcad's input mirror, a GitHub
release of mithro/gf180-tcad,
https://github.com/mithro/gf180-tcad/releases/tag/gf180-tcad/inputs/tcad-dev-20261019) first,
then from its original ``url``; either way the bytes must hash to its ``sha256``, or the build
fails. A download error is retried (ATTEMPTS per URL); a wrong sha256 goes straight to the next
URL. Nothing is unpacked here.
"""

import hashlib
import http.client
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ATTEMPTS = 2  # per URL


def _download(url: str, dest: Path) -> str:
    h = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=300) as resp, dest.open("wb") as out:
        while chunk := resp.read(1 << 20):
            h.update(chunk)
            out.write(chunk)
    return h.hexdigest()


def fetch(entry: dict, dest: Path) -> str:
    """Save ``entry`` to ``dest``; return which URL it came from. Exits on failure."""
    errors = []
    for which in ("mirror_url", "url"):
        for _ in range(ATTEMPTS):
            try:
                got = _download(entry[which], dest)
            except (OSError, http.client.HTTPException) as e:
                # OSError: URLError, HTTPError, timeouts, resets; HTTPException: a truncated or
                # malformed response (IncompleteRead, RemoteDisconnected is both). Retried.
                errors.append(f"{entry[which]}: {e!r}")
                continue
            if got == entry["sha256"]:
                return which
            # A wrong hash is not retried: the same URL serves the same bytes. Next URL.
            errors.append(f"{entry[which]}: sha256 {got} != {entry['sha256']}")
            break
    dest.unlink(missing_ok=True)
    sys.exit(f"fetch_sources: {dest.name}: every URL failed:\n  " + "\n  ".join(errors))


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["--wheelhouse"] and len(args) == 3:
        entries = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        jobs = {name: (e, name) for name, e in entries.items()}
        out = Path(args[2])
    elif len(args) >= 3 and not args[0].startswith("-"):
        upstream = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        jobs = {name: (upstream[name], upstream[name]["file"]) for name in args[2:]}
        out = Path(args[1])
    else:
        sys.exit(
            "usage: fetch_sources.py UPSTREAM_JSON OUT_DIR NAME...\n"
            "       fetch_sources.py --wheelhouse WHEELHOUSE_JSON OUT_DIR"
        )
    out.mkdir(parents=True, exist_ok=True)

    def one(name: str) -> str:
        entry, file = jobs[name]
        which = fetch(entry, out / file)
        return f"fetch_sources: {name} ok from {which} ({entry['sha256']})"

    # A few downloads at a time; the files and their checks do not depend on the order.
    with ThreadPoolExecutor(max_workers=8) as pool:
        for line in pool.map(one, sorted(jobs)):
            print(line, flush=True)


if __name__ == "__main__":
    main()
