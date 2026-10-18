# SPDX-License-Identifier: Apache-2.0
"""Print the provenance of the gf180-tcad base image as JSON (sorted keys, trailing newline).

Runs inside the image (via tools/sandbox-run). Versions come from the tools themselves, never from
/foss/pdks/versions.txt (which is stale). No timestamps, hostnames or host paths.
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
    variant = os.environ["PDK"]
    if variant != VARIANT:
        sys.exit(f"probe_versions: PDK={variant!r}, expected {VARIANT!r}")
    pdk = pdk_root / variant
    nodeinfo = json.loads((pdk / ".config" / "nodeinfo.json").read_text(encoding="utf-8"))
    xyce_caps = _tool_output("Xyce", "-capabilities")
    return {
        "base_image": os.environ["GF180TCAD_BASE_IMAGE"],
        "python": platform.python_version(),
        "ngspice": _match(r"\bngspice-(\S+)", _tool_output("ngspice", "--version"), "ngspice"),
        "xyce": _match(r"^Xyce Release (\S+)", _tool_output("Xyce", "-v"), "Xyce"),
        # The IIC Xyce is an MPI build; we always run it as one process without mpirun.
        "xyce_parallel": (
            "mpi-capable, run single-process" if "Parallel with MPI" in xyce_caps else "serial"
        ),
        # The KLayout CLI from the base image (/foss/tools/klayout) ...
        "klayout": _match(r"^KLayout (\S+)", _tool_output("klayout", "-b", "-v"), "KLayout"),
        # ... and the klayout Python module in the venv (a gdsfactory dependency).
        "klayout_python": version("klayout"),
        "gdsfactory": version("gdsfactory"),
        "devsim": version("devsim"),
        "pdk_root": str(pdk_root),
        "gf180mcu_variant": variant,
        "open_pdks_commit": nodeinfo["commit"]["open_pdks"],
        "sm141064_ngspice_sha256": _sha256(pdk / "libs.tech" / "ngspice" / "sm141064.ngspice"),
        "design_ngspice_sha256": _sha256(pdk / "libs.tech" / "ngspice" / "design.ngspice"),
        "sm141064_xyce_sha256": _sha256(pdk / "libs.tech" / "xyce" / "sm141064.xyce"),
    }


def main() -> None:
    sys.stdout.write(json.dumps(probe(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
