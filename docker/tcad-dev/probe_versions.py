# SPDX-License-Identifier: Apache-2.0
"""Print the provenance of the gf180-tcad dev-HEAD TCAD image as JSON (sorted keys, newline).

Runs inside the dev-HEAD TCAD image (via tools/sandbox-run --image "$(cat docker/TCAD_DEV_IMAGE)").
It reports every key of docker/tcad/probe_versions.py (same base image, same tools, versions read
from the installed packages), plus

- ``upstream``: the source manifest baked into the image (docker/tcad-dev/upstream.json), after
  checking it against what the installed packages record: the file each URL package was installed
  from (its PEP 610 direct_url.json, https://peps.python.org/pep-0610/: the build's
  sha256-checked copy of the manifest's URL), and the git revision gmsh reports;
- ``devsim_build``: DEVSIM's build record (docker/tcad-dev/build-devsim.sh), after checking that it
  is of the manifest's DEVSIM commit and that the installed extension module is the one it
  describes: the same sha256, and the compilers in its ELF ``.comment`` section.

No timestamps, hostnames or host paths.
"""

import hashlib
import importlib.util
import json
import os
import struct
import sys
from importlib.metadata import distribution, version
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = Path(sys.prefix) / "share" / "gf180tcad" / "upstream.json"
DEVSIM_BUILD = Path(sys.prefix) / "share" / "gf180tcad" / "devsim-build.json"
# Installed by uv from the fetched copy of an upstream.json URL (requirements.lock, rewritten by
# docker/tcad-dev/local_inputs.py): name -> upstream.json key.
URL_INSTALLED = ("meshwell", "gdsfactory", "gf180mcu", "gmsh")
FETCHED = Path("/opt/build/src")


def _stable_probe() -> dict[str, str]:
    path = HERE.parent / "tcad" / "probe_versions.py"
    spec = importlib.util.spec_from_file_location("gf180tcad_tcad_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.probe()


def _installed_url(name: str) -> str:
    text = distribution(name).read_text("direct_url.json")
    if text is None:
        sys.exit(f"probe_versions: {name} has no direct_url.json (not installed from a URL)")
    return json.loads(text)["url"]


def _gmsh_revision() -> str:
    import gmsh

    gmsh.initialize(readConfigFiles=False)
    try:
        return gmsh.option.getString("General.Version")
    finally:
        gmsh.finalize()


def elf_comment(path: Path) -> list[str]:
    """The sorted, distinct strings of an ELF64 little-endian file's ``.comment`` section."""
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x02\x01":
        sys.exit(f"probe_versions: {path} is not an ELF64 little-endian file")
    (shoff,) = struct.unpack_from("<Q", data, 0x28)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 0x3A)

    def section(i: int) -> tuple[int, int, int]:  # name offset, file offset, size
        name, _type, _flags, _addr, offset, size = struct.unpack_from(
            "<IIQQQQ", data, shoff + i * shentsize
        )
        return name, offset, size

    _, stroff, _ = section(shstrndx)
    for i in range(shnum):
        name, offset, size = section(i)
        if data[stroff + name : data.index(b"\0", stroff + name)] == b".comment":
            raw = data[offset : offset + size].split(b"\0")
            return sorted({s.decode() for s in raw if s})
    sys.exit(f"probe_versions: {path} has no .comment section")


def devsim_build(upstream: dict) -> dict:
    import devsim

    record = json.loads(DEVSIM_BUILD.read_text(encoding="utf-8"))
    if record["commit"] != upstream["devsim"]["commit"]:
        sys.exit(f"probe_versions: DEVSIM built from {record['commit']}, not the manifest's")
    so = Path(devsim.__file__).parent / "devsim_py3.so"
    sha = hashlib.sha256(so.read_bytes()).hexdigest()
    if sha != record["devsim_py3.so sha256"]:
        sys.exit(f"probe_versions: {so} (sha256 {sha}) is not the module DEVSIM's build recorded")
    if elf_comment(so) != record["compilers"]:
        sys.exit(f"probe_versions: {so}: .comment {elf_comment(so)} != {record['compilers']}")
    return record


def check(upstream: dict) -> None:
    for name in URL_INSTALLED:
        got = _installed_url(name)
        want = (FETCHED / upstream[name]["file"]).as_uri()
        if got != want:
            sys.exit(f"probe_versions: {name} installed from {got}, not {want}")
    rev = _gmsh_revision()
    if not rev.endswith("-git-" + upstream["gmsh"]["commit"][:9]):
        sys.exit(f"probe_versions: gmsh reports {rev}, not commit {upstream['gmsh']['commit']}")
    import devsim

    if devsim.__version__ != version("devsim"):
        sys.exit(f"probe_versions: devsim {devsim.__version__} != dist {version('devsim')}")


def probe() -> dict:
    upstream = json.loads(MANIFEST.read_text(encoding="utf-8"))
    # DEVSIM prints a banner on import and gmsh may log, both from C: send fd 1 to stderr meanwhile.
    sys.stdout.flush()
    saved = os.dup(1)
    os.dup2(2, 1)
    try:
        check(upstream)
        build = devsim_build(upstream)
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(saved)
    return {**_stable_probe(), "devsim_build": build, "upstream": upstream}


def main() -> None:
    data = probe()
    sys.stdout.write(json.dumps(data, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
