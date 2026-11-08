# SPDX-License-Identifier: Apache-2.0
"""The engine cross-check with the nfet card forced to BSIM4 4.6 (issue #161).

``docs/limitations/engine-cross-check.md`` explains why ngspice and Xyce differ for the nfet:
the PDK's nfet card declares BSIM4 ``version=4.5``, which ngspice evaluates as BSIM4 4.5 and
Xyce, whose oldest BSIM4 is 4.6.1, as 4.6.1. This module reruns each nfet geometry and sweep
with a patched copy of the image's ngspice library whose nfet card says ``version=4.6``. It
records three :func:`gf180tcad.spice.xyce.engine_diff` values per case in
:data:`~gf180tcad.engine46.RECORD`: stock ngspice against Xyce, patched ngspice against Xyce,
and stock against patched ngspice.

:data:`~gf180tcad.engine46.PATCH_SCRIPT` writes the patched copy inside the sandbox, so the
repository stays read-only. The copy differs from the PDK library in two ways: the nfet card's
``version=4.5`` becomes ``4.6``, and the library's nested ``.lib 'sm141064.spice'`` lines point
at the copy.

``python -m gf180tcad.engine46 record`` writes :data:`~gf180tcad.engine46.RECORD`; it runs three
small simulations per case in the sandbox, one at a time. ``tests/spice/test_xyce.py``
re-derives every case in the image and compares it with the record. No generator imports this
module, so it is outside every hashed closure.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import sys
import tempfile
from pathlib import Path

from gf180tcad import sandbox
from gf180tcad.devices import DEVICES, SWEEPS, Geometry, geometry_id
from gf180tcad.pdk import PdkInfo
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.spice.netlist import bias_plan, ngspice_netlist
from gf180tcad.spice.ngspice import run_ngspice, simulate
from gf180tcad.spice.xyce import engine_diff, simulate_xyce

#: The record :func:`~gf180tcad.engine46.record` writes and ``tests/spice/test_xyce.py`` checks.
RECORD = REPO_ROOT / "data" / "spice" / "engine-forced-bsim46.json"
#: The device whose card declares ``version=4.5`` (the pfet card declares 4.6).
DEVICE = DEVICES["nfet_05v0"]
#: The sweeps recorded: the two the engine cross-check fails on, and ``idvd``, which passes.
SWEEP_NAMES = ("idvg_lin", "idvg_sat", "idvd")
#: The corner and temperature of the engine cross-check.
CORNER, TEMP_C = "typical", 25.0
#: The BSIM4 version the patched nfet card declares (the PDK's card declares 4.5).
FORCED_VERSION = "4.6"
#: The working-directory subdirectory that holds the patched copy, passed to the ngspice
#: runner as an explicit input.
PATCHED_LIB_DIR = "lib"
#: The patched copy's path inside the sandbox.
PATCHED_LIB = f"/work/out/{PATCHED_LIB_DIR}/sm141064.ngspice"

#: Run in the sandbox: writes the patched copy to ``/work/out/sm141064.ngspice`` and prints
#: what it changed and the identity of the files it read, as JSON.
PATCH_SCRIPT = r"""
import hashlib, json, re
from gf180tcad import pdk
lib = pdk.locate().ngspice_lib
text = open(lib).read()
# every nested .lib target, in any form (indented, quoted or not), with its byte identity
targets = sorted(set(re.findall(r"(?im)^[ \t]*\.lib[ \t]+'?([^'\s]+)'?[ \t]+\S+", text)))
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
nested = {t: sha(lib.parent / t) for t in targets}
start = text.index("\n.lib nfet_06v0_t\n")
end = text.index("\n.endl nfet_06v0_t\n", start)
section, n_version = re.subn(r"(?m)^\+ version=4\.5$", "+ version=4.6", text[start:end])
text = text[:start] + section + text[end:]
n_nested = len(re.findall(r"(?i)sm141064\.spice", text))
text = re.sub(r"(?i)sm141064\.spice", "@PATCHED_LIB@", text)
open("/work/out/sm141064.ngspice", "w").write(text)
print(json.dumps({
    "version": n_version, "nested": n_nested, "left": text.lower().count("sm141064.spice"),
    "lib_sha": sha(lib), "nested_sha": nested, "mim_ngspice_sha": sha(lib.parent / "sm141064_mim.ngspice"),
}))
""".replace("@PATCHED_LIB@", PATCHED_LIB)

_PDK_SCRIPT = (
    "import dataclasses, json; from gf180tcad import pdk; info = pdk.locate(); "
    "pdk.check_against(info, '/work/src/docker/base/versions.json'); "
    "print(json.dumps({k: str(v) for k, v in dataclasses.asdict(info).items()}))"
)


def image_pdk(scratch: Path) -> PdkInfo:
    """The image's PDK, located and checked against ``docker/base/versions.json`` in the
    sandbox."""
    res = sandbox.run(["python3", "-c", _PDK_SCRIPT], out_dir=scratch)
    fields = json.loads(res.stdout.splitlines()[-1])
    return PdkInfo(
        **{k: (v if k in ("variant", "open_pdks_commit") else Path(v)) for k, v in fields.items()}
    )


def check_patch(info: dict) -> None:
    """ValueError unless :data:`~gf180tcad.engine46.PATCH_SCRIPT` changed what it should: both
    nfet_06v0 bins' ``version`` lines, every nested path, and no path back to the PDK's file;
    and unless each nested target is byte-identical to the file the netlist names, so the stock
    run evaluates the same text whichever copy ngspice resolves."""
    problems = []
    if info["version"] != 2:  # the two nfet_06v0 bins: L 0.6-0.7 and 0.7-50 um
        problems.append(f"version lines changed: {info['version']}")
    if info["nested"] <= 0 or info["left"] != 0:
        problems.append(f"nested paths: {info['nested']} changed, {info['left']} left")
    if set(info["nested_sha"]) != {"sm141064.spice", "sm141064_mim.spice"}:
        problems.append(f"nested targets: {sorted(info['nested_sha'])}")
    elif info["nested_sha"]["sm141064.spice"] != info["lib_sha"]:
        problems.append("sm141064.spice is not the library the netlist names")
    elif info["nested_sha"]["sm141064_mim.spice"] != info["mim_ngspice_sha"]:
        problems.append("sm141064_mim.spice is not the ngspice MIM library")
    if problems:
        raise ValueError("; ".join(problems))


def patch_lib(scratch: Path) -> tuple[Path, dict]:
    """``(path of the patched copy, what the patch changed)``, written in the sandbox under
    ``scratch`` and checked (:func:`~gf180tcad.engine46.check_patch`)."""
    res = sandbox.run(["python3", "-c", PATCH_SCRIPT], out_dir=scratch)
    info = json.loads(res.stdout.splitlines()[-1])
    check_patch(info)
    return scratch / "sm141064.ngspice", info


def case(g: Geometry, sweep_name: str, pdk: PdkInfo, lib: Path, scratch: Path) -> dict:
    """One geometry and sweep: stock ngspice, ngspice on the patched copy and Xyce, run in
    the sandbox under ``scratch``, and the three engine differences."""
    sweep = {s.name: s for s in SWEEPS}[sweep_name]
    for d in ("ng", "ng46", "xy"):
        (scratch / d).mkdir()
    (scratch / "ng46" / PATCHED_LIB_DIR).mkdir()
    shutil.copy(lib, scratch / "ng46" / PATCHED_LIB_DIR / "sm141064.ngspice")
    stock = simulate(DEVICE, g, sweep, CORNER, TEMP_C, pdk, scratch / "ng")
    pdk46 = dataclasses.replace(pdk, ngspice_lib=Path(PATCHED_LIB))
    text = ngspice_netlist(DEVICE, g, sweep, CORNER, TEMP_C, pdk46)
    ng46 = run_ngspice(text, scratch / "ng46", plan=bias_plan(DEVICE, sweep),
                       inputs=(PATCHED_LIB_DIR,))  # fmt: skip
    xy = simulate_xyce(DEVICE, g, sweep, CORNER, TEMP_C, pdk, scratch / "xy")
    return {
        "stock": engine_diff(stock, xy),
        "forced_4p6": engine_diff(ng46, xy),
        "stock_vs_forced": engine_diff(stock, ng46),
    }


def record(path: Path = RECORD) -> dict:
    """Run every geometry and sweep of :data:`~gf180tcad.engine46.DEVICE` and write the record
    to ``path``."""
    root = Path.home() / ".cache" / "gf180-tcad"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        scratch = Path(tmp)
        (scratch / "pdk").mkdir()
        (scratch / "lib").mkdir()
        pdk = image_pdk(scratch / "pdk")
        lib, info = patch_lib(scratch / "lib")
        cases = {}
        for g in DEVICE.geometries:
            gid = geometry_id(g)
            for sweep_name in SWEEP_NAMES:
                d = scratch / f"{gid}-{sweep_name}"
                d.mkdir()
                cases.setdefault(gid, {})[sweep_name] = case(g, sweep_name, pdk, lib, d)
                print(gid, sweep_name, cases[gid][sweep_name], flush=True)
    out = {
        "image": (REPO_ROOT / "docker" / "IMAGE").read_text(encoding="utf-8").strip(),
        "device": DEVICE.name,
        "corner": CORNER,
        "temp_c": TEMP_C,
        "pdk_ngspice_lib_sha256": info["lib_sha"],
        "cases": cases,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    if sys.argv[1:] != ["record"]:
        raise SystemExit("usage: python -m gf180tcad.engine46 record")
    record()
    print(f"wrote {RECORD.relative_to(REPO_ROOT)}")
