# SPDX-License-Identifier: Apache-2.0
"""Print the provenance of the gf180-tcad charon-libs image as JSON (sorted keys, trailing newline).

Runs inside the image (CI: ``docker run ... python3 probe_versions.py``; tests: tools/sandbox-run).
Everything comes from the image itself:

- ``base``: what docker/base/probe_versions.py reports (the base image this one is built FROM);
- ``base_image_ref``: the pinned base image the build was FROM (docker/IMAGE at build time);
- ``charon_build``: the build record /opt/charon/share/gf180tcad/charon-build.json (the inputs
  by sha256, the opts files, the patches and the build-time probe tests, which all passed);
- ``sources``: /opt/charon/share/gf180tcad/SOURCES.json, the corresponding source by sha256;
- ``charon_mp_sha256`` and ``compilers`` (the ELF ``.comment`` strings of charon_mp.exe);
- ``kokkos_backends``: the Kokkos execution spaces enabled in the installed KokkosCore_config.h;
- ``runtime_packages``: the base image's Debian packages that /opt/charon links against
  (OpenMPI, netCDF, HDF5, Boost, OpenBLAS), name -> version.

No timestamps, hostnames or host paths.
"""

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREFIX = Path("/opt/charon")
SHARE = PREFIX / "share" / "gf180tcad"
CHARON_MP = PREFIX / "bin" / "charon_mp.exe"
# The Kokkos execution spaces KokkosCore_config.h can enable.
KOKKOS_SPACES = ("SERIAL", "OPENMP", "THREADS", "CUDA", "HIP", "SYCL", "OPENMPTARGET", "HPX")
# Runtime packages of the base image that the Charon build links against.
RUNTIME_PACKAGES = re.compile(
    r"^(libopenmpi\d+t64|openmpi-bin|libnetcdf\d+t64|libhdf5-\d+[-\w]*t64|"
    r"libboost-(program-options|system)\d[.\d]*|libopenblas0-pthread|liblapack3)$"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def kokkos_backends() -> list[str]:
    (config,) = PREFIX.glob("include/**/KokkosCore_config.h")
    text = config.read_text(encoding="utf-8")
    on = [
        s.title()
        for s in KOKKOS_SPACES
        if re.search(rf"^#define KOKKOS_ENABLE_{s}\b", text, re.MULTILINE)
    ]
    return on


def runtime_packages() -> dict[str, str]:
    res = subprocess.run(
        ["dpkg-query", "-W", "-f", "${Package} ${Version}\\n"],
        capture_output=True,
        text=True,
        check=True,
    )
    pkgs = dict(line.split(" ", 1) for line in res.stdout.splitlines() if line)
    out = {name: v for name, v in pkgs.items() if RUNTIME_PACKAGES.match(name.split(":")[0])}
    if not out:
        sys.exit("probe_versions: none of the runtime packages is installed")
    return out


def probe() -> dict:
    tcad_dev = _load("gf180tcad_tcad_dev_probe", HERE.parent / "tcad-dev" / "probe_versions.py")
    base = _load("gf180tcad_base_probe", HERE.parent / "base" / "probe_versions.py")
    return {
        "base": base.probe(),
        "base_image_ref": os.environ["GF180TCAD_CHARON_BASE_IMAGE"],
        "charon_build": _json(SHARE / "charon-build.json"),
        "sources": _json(SHARE / "SOURCES.json"),
        "charon_mp_sha256": hashlib.sha256(CHARON_MP.read_bytes()).hexdigest(),
        "compilers": tcad_dev.elf_comment(CHARON_MP),
        "kokkos_backends": kokkos_backends(),
        "runtime_packages": runtime_packages(),
    }


def main() -> None:
    sys.stdout.write(json.dumps(probe(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
