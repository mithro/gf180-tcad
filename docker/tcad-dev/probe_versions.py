# SPDX-License-Identifier: Apache-2.0
"""Print the provenance of the gf180-tcad dev-HEAD TCAD image as JSON (sorted keys, newline).

Runs inside the dev-HEAD TCAD image (via tools/sandbox-run --image "$(cat docker/TCAD_DEV_IMAGE)").
It reports every key of docker/tcad/probe_versions.py (same base image, same tools, versions read
from the installed packages), plus ``upstream``: the source manifest baked into the image
(docker/tcad-dev/upstream.json), after checking it against what the installed packages record:
the URL each was installed from (its PEP 610 direct_url.json) and the git revision gmsh reports.
No timestamps, hostnames or host paths.
"""

import importlib.util
import json
import os
import sys
from importlib.metadata import distribution, version
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = Path(sys.prefix) / "share" / "gf180tcad" / "upstream.json"
# Installed by uv from a URL (requirements.lock / gf180mcu.lock): name -> upstream.json key.
URL_INSTALLED = ("meshwell", "gdsfactory", "gf180mcu", "gmsh")


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


def check(upstream: dict) -> None:
    for name in URL_INSTALLED:
        got = _installed_url(name)
        if got != upstream[name]["url"]:
            sys.exit(f"probe_versions: {name} installed from {got}, not {upstream[name]['url']}")
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
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(saved)
    return {**_stable_probe(), "upstream": upstream}


def main() -> None:
    data = probe()
    sys.stdout.write(json.dumps(data, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
