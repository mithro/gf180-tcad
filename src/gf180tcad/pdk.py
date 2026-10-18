# SPDX-License-Identifier: Apache-2.0
"""PDK provenance: locate the GF180MCU model files and check them against the recorded hashes.

``docker/base/versions.json`` records the sha256 of the SPICE model files in the pinned image
(written by ``docker/base/probe_versions.py``). Every SPICE run calls :func:`check_against` so it
fails if the models differ from the recorded ones.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VARIANT = "gf180mcuD"
_CHUNK = 1 << 20


class PdkMismatch(RuntimeError):
    """The PDK in use differs from the one recorded in versions.json."""


@dataclass(frozen=True)
class PdkInfo:
    root: Path
    variant: str
    open_pdks_commit: str
    ngspice_lib: Path
    ngspice_design: Path
    xyce_lib: Path
    xyce_design: Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def locate(pdk_root: Path | str | None = None, variant: str = DEFAULT_VARIANT) -> PdkInfo:
    """Find the model files under ``<pdk_root>/<variant>``; ``$PDK_ROOT`` if ``pdk_root`` is None.

    Raises RuntimeError if no root is given, FileNotFoundError (naming the path) if a model file
    or nodeinfo.json is missing. All returned paths are absolute.
    """
    if pdk_root is None:
        env = os.environ.get("PDK_ROOT")
        if not env:
            raise RuntimeError(
                "no PDK root: pass pdk_root or set the PDK_ROOT environment variable"
            )
        pdk_root = env
    root = Path(pdk_root).absolute()
    base = root / variant
    ngspice = base / "libs.tech" / "ngspice"
    xyce = base / "libs.tech" / "xyce"
    nodeinfo = base / ".config" / "nodeinfo.json"
    files = {
        "ngspice_lib": ngspice / "sm141064.ngspice",
        "ngspice_design": ngspice / "design.ngspice",
        "xyce_lib": xyce / "sm141064.xyce",
        "xyce_design": xyce / "design.xyce",
    }
    for path in (*files.values(), nodeinfo):
        if not path.is_file():
            raise FileNotFoundError(f"PDK file not found: {path}")
    # Same source as docker/base/probe_versions.py (keep the two in sync).
    commit = json.loads(nodeinfo.read_text(encoding="utf-8"))["commit"]["open_pdks"]
    return PdkInfo(root=root, variant=variant, open_pdks_commit=commit, **files)


def check_against(info: PdkInfo, versions: Path | str) -> None:
    """Raise PdkMismatch (listing every difference) unless ``info`` matches ``versions``.

    Compared: variant, open_pdks commit, and the sha256 of the ngspice lib, ngspice design file
    and Xyce lib. versions.json records no hash for the Xyce design file, so ``xyce_design`` is
    only located (it must exist, see :func:`locate`) and is NOT hash-checked. A key missing from
    versions.json is reported as a mismatch.
    """
    recorded = json.loads(Path(versions).read_text(encoding="utf-8"))
    actual = {
        "gf180mcu_variant": info.variant,
        "open_pdks_commit": info.open_pdks_commit,
        "sm141064_ngspice_sha256": _sha256(info.ngspice_lib),
        "design_ngspice_sha256": _sha256(info.ngspice_design),
        "sm141064_xyce_sha256": _sha256(info.xyce_lib),
    }
    problems = []
    for key, got in actual.items():
        if key not in recorded:
            problems.append(f"  {key}: missing from versions.json (actual {got!r})")
        elif recorded[key] != got:
            problems.append(f"  {key}: expected {recorded[key]!r}, actual {got!r}")
    if problems:
        raise PdkMismatch(f"PDK at {info.root} differs from {versions}:\n" + "\n".join(problems))
