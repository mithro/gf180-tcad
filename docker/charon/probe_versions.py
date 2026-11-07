# SPDX-License-Identifier: Apache-2.0
"""Print the provenance of the gf180-tcad charon image as JSON (sorted keys, trailing newline).

Runs inside the image with the TCAD venv's Python (CI: ``docker run ... python3
probe_versions.py``; tests: tools/sandbox-run). Everything comes from the image itself:

- ``tcad_dev``: what docker/tcad-dev/probe_versions.py reports (the dev-HEAD TCAD image this one
  is built FROM; its own checks run too);
- ``tcad_dev_image_ref`` and ``charon_libs_image_ref``: the pinned images the build used
  (docker/TCAD_DEV_IMAGE and docker/CHARON_LIBS_IMAGE at build time);
- ``charon_build``, ``sources``, ``charon_mp_sha256``, ``compilers``, ``kokkos_backends`` and
  ``runtime_packages``: what docker/charon-libs/probe_versions.py reports under the same keys,
  read from the copied /opt/charon and this image's Debian packages;
- ``netcdf4_python``: the versions of the netCDF4 and cftime packages in the venv and of the
  netCDF-C and HDF5 libraries that the netCDF4 wheel carries.

No timestamps, hostnames or host paths.
"""

import hashlib
import importlib.util
import json
import os
import sys
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def netcdf4_python() -> dict[str, str]:
    import netCDF4

    if netCDF4.__version__ != version("netCDF4"):
        sys.exit(f"probe_versions: netCDF4 {netCDF4.__version__} != dist {version('netCDF4')}")
    return {
        "cftime": version("cftime"),
        "hdf5": netCDF4.__hdf5libversion__,
        "netCDF4": version("netCDF4"),
        "netcdf_c": netCDF4.__netcdf4libversion__,
    }


def probe() -> dict:
    tcad_dev = _load("gf180tcad_tcad_dev_probe", HERE.parent / "tcad-dev" / "probe_versions.py")
    libs = _load("gf180tcad_charon_libs_probe", HERE.parent / "charon-libs" / "probe_versions.py")
    return {
        "tcad_dev": tcad_dev.probe(),
        "tcad_dev_image_ref": os.environ["GF180TCAD_CHARON_TCAD_DEV_IMAGE"],
        "charon_libs_image_ref": os.environ["GF180TCAD_CHARON_LIBS_IMAGE"],
        "charon_build": libs._json(libs.SHARE / "charon-build.json"),
        "sources": libs._json(libs.SHARE / "SOURCES.json"),
        "charon_mp_sha256": hashlib.sha256(libs.CHARON_MP.read_bytes()).hexdigest(),
        "compilers": tcad_dev.elf_comment(libs.CHARON_MP),
        "kokkos_backends": libs.kokkos_backends(),
        "runtime_packages": libs.runtime_packages(),
        "netcdf4_python": netcdf4_python(),
    }


def main() -> None:
    sys.stdout.write(json.dumps(probe(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
