# SPDX-License-Identifier: Apache-2.0
"""The "once worked" record of the gdsfactory gplugins DEVSIM plugin.

``python -m gf180tcad.history --version v0.8.0|v1.4.2 [--mesh-scale R] --out DIR`` rebuilds one
record (``results/plugin-history/*.json``): gplugins v0.8.0 on its Sept-2023 stack, where the
plugin worked, or v1.4.2 on its frozen lock, where its import is broken. It runs on the host and
uses the base image (``docker/IMAGE``) through :func:`gf180tcad.sandbox.run`, in three steps:

1. **Sources**, on the host: ``git archive <tag>`` of the gplugins submodule into the workdir
   (the tag is fetched first if the clone lacks it, as shallow CI submodule clones do).
2. **Install**, in the sandbox *with* network: uv from ``docker/tcad/build-requirements.lock``
   (hashed), then for v0.8.0 CPython 3.11.17 and the hashed
   ``experiments/plugin-history/v080.lock`` (the gplugins source on ``sys.path`` through a
   ``.pth`` file), for v1.4.2 ``uv sync --frozen`` from the tag's own uv lock with the base
   Python 3.12. All state
   (caches, interpreters, venvs) lives in the workdir.
3. **Run**, in the sandbox with *no* network: the check driver
   ``experiments/plugin-history/checks_<v>.py``, with ``PDK`` unset.

The driver's raw JSON is re-written with :func:`gf180tcad.io.write_json` together with the tag,
its commit, the image and the network mode of the run. The record holds no timings and no host
paths. It is reproducible byte for byte on one host; it is not part of the GitHub-hosted
cross-check (the 2023 stack has no cross-host bit-identity guarantee).

The CLI is not ``python -m gf180tcad``: ``gf180tcad.__main__`` is a SPICE generator module.
"""

from __future__ import annotations

import argparse
import io as _stdio
import json
import math
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from gf180tcad import sandbox
from gf180tcad.io import write_json

_SUBMODULE = sandbox.REPO_ROOT / "third_party" / "gplugins"
_IMAGE_FILE = sandbox.REPO_ROOT / "docker" / "IMAGE"
_BUILD_LOCK = "docker/tcad/build-requirements.lock"  # relative to the repo (/work/src)

#: The CPython of the v0.8.0 venv (uv-managed; v0.8.0 predates Python 3.12 support).
V080_PYTHON = "3.11.17"
#: The sdist-only packages of v080.lock, built with its own setuptools/wheel as build constraints.
V080_SDISTS = ("antlr4-python3-runtime", "flatdict", "rectpack")


@dataclass(frozen=True)
class Version:
    """A gplugins version with a record: its fork tag and its check driver."""

    tag: str  #: the tag in the gplugins submodule
    driver: str  #: the check driver in experiments/plugin-history
    meshed: bool  #: whether the driver meshes, i.e. whether --mesh-scale applies


#: The versions with a record, by name (``--version``).
VERSIONS = {
    "v0.8.0": Version("v0.8.0", "checks_v080.py", meshed=True),
    "v1.4.2": Version("v1.4.2", "checks_v142.py", meshed=False),
}

_ENV = (
    "export HOME=/tmp/home UV_CACHE_DIR=/work/out/uvcache UV_PYTHON_INSTALL_DIR=/work/out/uvpython"
    " PIP_CACHE_DIR=/work/out/pipcache UV_NO_CONFIG=1 PIP_CONFIG_FILE=/dev/null"
    " PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1\n"
    "unset VIRTUAL_ENV PYTHONPATH\n"
)

_TOOLVENV = (
    "rm -rf toolvenv venv\n"
    "/usr/bin/python3 -m venv --without-pip toolvenv\n"
    "/usr/bin/python3 -m pip --python toolvenv/bin/python install --no-deps --only-binary=:all:"
    f" --require-hashes -r /work/src/{_BUILD_LOCK}\n"
    "uv=/work/out/toolvenv/bin/uv\n"
    '"$uv" --version\n'
)

_INSTALL = {
    "v0.8.0": (
        f'"$uv" python install --no-bin {V080_PYTHON}\n'
        f'"$uv" venv --managed-python --python {V080_PYTHON} venv\n'
        '"$uv" pip install --python venv/bin/python --require-hashes --no-deps'
        f" --only-binary=:all: --no-binary={','.join(V080_SDISTS)}"
        " --build-constraints /work/src/experiments/plugin-history/v080.lock"
        " -r /work/src/experiments/plugin-history/v080.lock\n"
        'site="$(venv/bin/python -c \'import sysconfig; print(sysconfig.get_paths()["purelib"])\')"\n'
        "printf '%s\\n' /work/out/gplugins > \"$site/gf180tcad-gplugins.pth\"\n"
    ),
    "v1.4.2": (
        "cd /work/out/gplugins\n"
        "UV_PROJECT_ENVIRONMENT=/work/out/venv UV_PYTHON_DOWNLOADS=never"
        ' "$uv" sync --frozen --python /usr/bin/python3'
        " --extra devsim --extra gmsh --extra tidy3d --extra dev\n"
    ),
}


def install_script(version: str) -> str:
    """The shell script of step 2 (network on), run in the workdir (``/work/out``)."""
    return "set -eux\ncd /work/out\n" + _ENV + _TOOLVENV + _INSTALL[version]


def run_command(version: str, mesh_scale: float) -> list[str]:
    """The command of step 3 (network off): the check driver in the installed venv."""
    v = VERSIONS[version]
    args = ["--out", "/work/out/raw.json"]
    if v.meshed:
        args = ["--mesh-scale", repr(mesh_scale), *args]
    script = (
        "set -eu\nrm -rf /work/out/run /work/out/raw.json\nmkdir /work/out/run\ncd /work/out/run\n"
        "exec env -u PDK -u PYTHONPATH -u VIRTUAL_ENV PYTHONHASHSEED=0 /work/out/venv/bin/python"
        f' -s -P /work/src/experiments/plugin-history/{v.driver} "$@"\n'
    )
    return ["sh", "-c", script, "sh", *args]


def result_name(version: str, mesh_scale: float) -> str:
    """``<version>.json``, or ``<version>-mesh<R>.json`` (``.`` as ``p``) if R is not 1."""
    if mesh_scale == 1:
        return f"{version}.json"
    return f"{version}-mesh{repr(float(mesh_scale)).replace('.', 'p')}.json"


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(_SUBMODULE), *args], capture_output=True, check=check)


def tag_commit(tag: str) -> str:
    """The commit of ``tag`` in the gplugins submodule, fetching the tag if it is missing."""
    ref = f"refs/tags/{tag}^{{commit}}"
    res = _git("rev-parse", "-q", "--verify", ref, check=False)
    if res.returncode != 0:
        _git("fetch", "--depth", "1", "origin", "tag", tag)
        res = _git("rev-parse", "-q", "--verify", ref)
    return res.stdout.decode("ascii").strip()


def export_sources(tag: str, dest: Path) -> None:
    """``git archive <tag>`` of the submodule, extracted into ``dest`` (replaced)."""
    data = _git("archive", "--format=tar", tag).stdout
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=_stdio.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")


def image_ref() -> str:
    """The base image reference (the first line of ``docker/IMAGE``), which every step uses."""
    return _IMAGE_FILE.read_text(encoding="utf-8").splitlines()[0].strip()


def _sandbox(cmd: list[str], workdir: Path, log: Path, **kw) -> None:
    try:
        res = sandbox.run(cmd, out_dir=workdir, **kw)
    except sandbox.SandboxError as e:
        if e.result is not None:
            log.write_text(e.result.stdout + e.result.stderr, encoding="utf-8")
        raise
    log.write_text(res.stdout + res.stderr, encoding="utf-8")


def record(version: str, raw: dict, commit: str, mesh_scale: float) -> dict:
    """The committed record: the driver's raw result plus where and how it ran."""
    out = dict(raw)
    out.update(
        gplugins_tag=version,
        gplugins_commit=commit,
        image=image_ref(),
        network="none",
    )
    if VERSIONS[version].meshed:
        out["mesh_scale"] = float(mesh_scale)
    return out


def run(version: str, out_dir: Path, mesh_scale: float = 1.0, workdir: Path | None = None) -> Path:
    """Rebuild one record into ``out_dir``; returns its path. See the module docstring."""
    v = VERSIONS[version]
    if mesh_scale != 1 and not v.meshed:
        raise ValueError(f"{version} has no mesh; --mesh-scale does not apply")
    commit = tag_commit(v.tag)
    own = workdir is None
    wd = Path(tempfile.mkdtemp(prefix="gf180tcad-history-")) if own else Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    wd = wd.resolve()
    sandbox.check_workdir(wd)
    try:
        export_sources(v.tag, wd / "gplugins")
        print(f"[history] {version} ({commit}): install (network on) in {wd}", flush=True)
        _sandbox(["sh", "-c", install_script(version)], wd, wd / "install.log", network=True)
        print(f"[history] {version}: checks (network off)", flush=True)
        _sandbox(run_command(version, mesh_scale), wd, wd / "run.log", cpus=1)
        raw = json.loads((wd / "raw.json").read_bytes())
    except BaseException:
        print(f"[history] failed; logs kept in {wd}", file=sys.stderr, flush=True)
        raise
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / result_name(version, mesh_scale)
    write_json(path, record(version, raw, commit, mesh_scale))
    if own:
        shutil.rmtree(wd)
    return path


def _mesh_scale(text: str) -> float:
    value = float(text)
    if not (math.isfinite(value) and value > 0):
        raise argparse.ArgumentTypeError(f"--mesh-scale must be a finite number > 0, got {text}")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """The CLI arguments; ``--mesh-scale`` must be finite and > 0, and 1 for v1.4.2."""
    ap = argparse.ArgumentParser(
        prog="python -m gf180tcad.history",
        description="Rebuild a gplugins DEVSIM plugin-history record (results/plugin-history).",
    )
    ap.add_argument("--version", required=True, choices=sorted(VERSIONS))
    ap.add_argument(
        "--mesh-scale",
        type=_mesh_scale,
        default=1.0,
        help="multiply every value of the PN slab's resolutions dict (v0.8.0 only; default 1)",
    )
    ap.add_argument("--out", type=Path, required=True, help="directory for the record JSON")
    ap.add_argument(
        "--workdir",
        type=Path,
        default=None,
        help="scratch directory (kept; reuses its download caches). Default: a new temporary "
        "directory, removed on success. Never the repo, its git dirs or $HOME.",
    )
    args = ap.parse_args(argv)
    if args.mesh_scale != 1 and not VERSIONS[args.version].meshed:
        ap.error(f"--mesh-scale does not apply to {args.version} (it runs only the import check)")
    return args


def main(argv: list[str] | None = None) -> int:
    """``python -m gf180tcad.history``: rebuild one record (see the module docstring)."""
    args = parse_args(argv)
    path = run(args.version, args.out, args.mesh_scale, args.workdir)
    print(f"[history] wrote {path}")
    return 0
