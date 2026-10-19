# SPDX-License-Identifier: Apache-2.0
"""Write docker/tcad-dev/wheelhouse.json: every PyPI file the dev-HEAD TCAD image build installs.

    uv run --no-project --with packaging python docker/tcad-dev/wheelhouse.py

(run from the repository root; needs network, reads PyPI's public JSON API,
https://docs.pypi.org/api/json/.) For every pinned
``name==version`` of requirements.lock and build-requirements.lock, PyPI lists the release's files;
the file chosen is the one with a hash the lock allows that the build's interpreter would install
first (packaging's tag order):

- requirements.lock: the venv's CPython 3.13 on the base image (glibc 2.39, x86_64);
- build-requirements.lock: the base image's /usr/bin/python3 (3.12, pip, ``--only-binary``) and
  the CPython 3.13 that runs the sdist builds (uv ``--build-constraints``), so the best wheel for
  each (the same file when it is pure Python).

A package without a compatible wheel (rectpack, sdist only) gets its sdist. The packages installed
from a URL (upstream.json) are not here. Each entry records the file's PyPI URL, its mirror URL
(the gf180-tcad input mirror, a GitHub release of mithro/gf180-tcad) and its sha256; the build
(fetch_sources.py) fetches the mirror first, falls back to PyPI and checks the sha256 either way,
then installs with ``--no-index --find-links``.
"""

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from packaging.markers import Marker
from packaging.tags import Tag, compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_sdist_filename, parse_wheel_filename

HERE = Path(__file__).resolve().parent
OUT = HERE / "wheelhouse.json"
# The mirror: release assets of mithro/gf180-tcad (docs/reproduce/image.md, "The input mirror";
# https://github.com/mithro/gf180-tcad/releases/tag/gf180-tcad/inputs/tcad-dev-20261019). The one
# place the tag is set: tests/test_tcad_dev_lock.py checks docs/conf.py, image.md, upstream.json
# and wheelhouse.json against it.
MIRROR_TAG = "gf180-tcad/inputs/tcad-dev-20261019"
MIRROR = f"https://github.com/mithro/gf180-tcad/releases/download/{MIRROR_TAG}/"
# glibc of the base image (Ubuntu 24.04): manylinux_2_39 down to manylinux_2_5, then linux.
PLATFORMS = [f"manylinux_2_{m}_x86_64" for m in range(39, 4, -1)] + [
    "manylinux2014_x86_64",
    "manylinux2010_x86_64",
    "manylinux1_x86_64",
    "linux_x86_64",
]
LOCKS = {
    "requirements.lock": [(3, 13)],
    "build-requirements.lock": [(3, 12), (3, 13)],
}


def tag_order(py: tuple[int, int]) -> list[Tag]:
    return [*cpython_tags(py, platforms=PLATFORMS), *compatible_tags(py, platforms=PLATFORMS)]


# The marker environment of the image's venv (CPython 3.13 on Linux x86_64).
ENVIRONMENT = {
    "implementation_name": "cpython",
    "implementation_version": "3.13.16",
    "os_name": "posix",
    "platform_machine": "x86_64",
    "platform_python_implementation": "CPython",
    "platform_system": "Linux",
    "python_full_version": "3.13.16",
    "python_version": "3.13",
    "sys_platform": "linux",
}


def pins(text: str) -> dict[str, tuple[str, set[str]]]:
    """``name -> (version, allowed sha256s)`` of every ``name==version`` requirement whose
    environment marker (if any) holds in the image."""
    out = {}
    for m in re.finditer(
        r"^([A-Za-z0-9_.-]+)==([^\s;]+)(?: ; ([^\\\n]+?))? \\\n((?:\s+--hash=sha256:[0-9a-f]{64}.*\n)+)",
        text,
        re.MULTILINE,
    ):
        if m.group(3) and not Marker(m.group(3)).evaluate(ENVIRONMENT):
            continue
        hashes = set(re.findall(r"[0-9a-f]{64}", m.group(4)))
        out[canonicalize_name(m.group(1))] = (m.group(2), hashes)
    return out


def mirror_name(filename: str) -> str:
    """The asset name GitHub gives an uploaded file (it turns ``~`` into ``.``)."""
    return filename.replace("~", ".")


def mirror_url(filename: str) -> str:
    return MIRROR + urllib.parse.quote(mirror_name(filename))


def choose(name: str, version: str, hashes: set[str], pythons: list[tuple[int, int]]) -> list[dict]:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as r:
        files = [f for f in json.load(r)["urls"] if f["digests"]["sha256"] in hashes]
    chosen = {}
    for py in pythons:
        order = {t: i for i, t in enumerate(tag_order(py))}
        best = None
        for f in files:
            if f["packagetype"] != "bdist_wheel":
                continue
            rank = min(
                (order[t] for t in parse_wheel_filename(f["filename"])[3] if t in order),
                default=None,
            )
            if rank is not None and (best is None or rank < best[0]):
                best = (rank, f)
        if best is None:
            sdists = [f for f in files if f["packagetype"] == "sdist"]
            if len(sdists) != 1:
                sys.exit(
                    f"wheelhouse: {name}=={version}: no wheel for {py} and {len(sdists)} sdists"
                )
            parse_sdist_filename(sdists[0]["filename"])
            best = (None, sdists[0])
        chosen[best[1]["filename"]] = best[1]
    return [
        {
            "filename": f["filename"],
            "package": name,
            "version": version,
            "sha256": f["digests"]["sha256"],
            "url": f["url"],
            "mirror_url": mirror_url(f["filename"]),
        }
        for f in chosen.values()
    ]


def main() -> None:
    entries: dict[str, dict] = {}
    for lock, pythons in LOCKS.items():
        for name, (version, hashes) in sorted(
            pins((HERE / lock).read_text(encoding="utf-8")).items()
        ):
            for e in choose(name, version, hashes, pythons):
                e = entries.setdefault(e.pop("filename"), e)
                e.setdefault("locks", [])
                if lock not in e["locks"]:
                    e["locks"].append(lock)
                print(f"wheelhouse: {lock}: {name}=={version}", flush=True)
    OUT.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wheelhouse: {len(entries)} files -> {OUT}")


if __name__ == "__main__":
    main()
