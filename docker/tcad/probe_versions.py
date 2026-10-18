# SPDX-License-Identifier: Apache-2.0
"""Print the provenance of the gf180-tcad TCAD image as JSON (sorted keys, trailing newline).

Runs inside the TCAD image (via tools/sandbox-run --image "$(cat docker/TCAD_IMAGE)"). It reports
every key of docker/base/probe_versions.py, now for the TCAD venv (``python`` is the 3.13 patch),
plus the TCAD stack. In this image ``$PDK`` is the gdsfactory PDK module (gf180mcu), so the
open_pdks facts are read from ``$PDK_ROOT/gf180mcuD`` directly, never via ``$PDK``.
Versions come from the tools themselves. No timestamps, hostnames or host paths.
"""

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

VARIANT = "gf180mcuD"


def _tool_output(*cmd: str) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout + res.stderr


def _match(pattern: str, text: str, what: str) -> str:
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        sys.exit(f"probe_versions: cannot parse {what} version from:\n{text}")
    return m.group(1)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe() -> dict[str, str]:
    pdk_root = Path(os.environ["PDK_ROOT"])
    pdk = pdk_root / VARIANT
    nodeinfo = json.loads((pdk / ".config" / "nodeinfo.json").read_text(encoding="utf-8"))
    xyce_caps = _tool_output("Xyce", "-capabilities")
    return {
        # The IIC-OSIC-TOOLS image under the base image (inherited ENV) ...
        "base_image": os.environ["GF180TCAD_BASE_IMAGE"],
        # ... and the gf180-tcad base image this image is built FROM (docker/IMAGE).
        "base_image_ref": os.environ["GF180TCAD_TCAD_BASE_IMAGE"],
        "python": platform.python_version(),
        # The uv-managed CPython the venv is based on.
        "tcad_python": str(Path(sys._base_executable).resolve()),
        "ngspice": _match(r"\bngspice-(\S+)", _tool_output("ngspice", "--version"), "ngspice"),
        "xyce": _match(r"^Xyce Release (\S+)", _tool_output("Xyce", "-v"), "Xyce"),
        # The IIC Xyce is an MPI build; we always run it as one process without mpirun.
        "xyce_parallel": (
            "mpi-capable, run single-process" if "Parallel with MPI" in xyce_caps else "serial"
        ),
        "klayout": _match(r"^KLayout (\S+)", _tool_output("klayout", "-b", "-v"), "KLayout"),
        "klayout_python": version("klayout"),
        "gdsfactory": version("gdsfactory"),
        "devsim": version("devsim"),
        "meshwell": version("meshwell"),
        "gmsh": version("gmsh"),
        "gf180mcu": version("gf180mcu"),
        "scipy": version("scipy"),
        "numpy": version("numpy"),
        "pdk_root": str(pdk_root),
        "gf180mcu_variant": VARIANT,
        "open_pdks_commit": nodeinfo["commit"]["open_pdks"],
        "sm141064_ngspice_sha256": _sha256(pdk / "libs.tech" / "ngspice" / "sm141064.ngspice"),
        "design_ngspice_sha256": _sha256(pdk / "libs.tech" / "ngspice" / "design.ngspice"),
        "sm141064_xyce_sha256": _sha256(pdk / "libs.tech" / "xyce" / "sm141064.xyce"),
    }


def main() -> None:
    sys.stdout.write(json.dumps(probe(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
