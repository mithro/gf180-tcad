# SPDX-License-Identifier: Apache-2.0
"""Helpers of docker/charon-libs/Dockerfile around upstream.json (base image /usr/bin/python3).

inputs.py names UPSTREAM_JSON
    every entry name, the debs in install order last (the fetch_sources.py arguments)
inputs.py debs UPSTREAM_JSON SRC_DIR
    the fetched .deb paths in install order (the dpkg -i arguments)
inputs.py check-opts UPSTREAM_JSON CHARON_DIR
    the Charon tarball's General.opts and Linux.opts hash to the sha256s recorded in
    upstream.json, and no other opts file of that directory would be read on this host
    (build_charon.py also reads <hostname>.opts there when one exists)
inputs.py sources UPSTREAM_JSON CONTEXT_DIR OUT_JSON
    SOURCES.json: the Charon, Trilinos and TriBITS tarballs, every patch and opts file of the
    build context and the build scripts, each with its sha256 (the corresponding source of the
    GPL binaries)
inputs.py record UPSTREAM_JSON CONTEXT_DIR OUT_JSON TEST...
    charon-build.json: the pinned inputs, the opts files and patches by sha256, the build type
    and the build-time probe tests, which all passed (the build stops otherwise)
"""

import hashlib
import json
import platform
import sys
from pathlib import Path

SOURCES = ("charon", "trilinos", "tribits")
# The files of docker/charon-libs/ that control the build (the Dockerfile mounts each of them
# into the build step, so SOURCES.json can hash them).
SCRIPTS = (
    "Dockerfile",
    "build",
    "build-charon.sh",
    "fetch_sources.py",
    "inputs.py",
    "upstream.json",
)


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def debs(upstream: dict) -> list[str]:
    entries = [(e["install_order"], name) for name, e in upstream.items() if e["kind"] == "deb"]
    return [name for _, name in sorted(entries)]


def names(upstream: dict) -> list[str]:
    """The sources in name order, then the debs in install order."""
    return [n for n in sorted(upstream) if upstream[n]["kind"] != "deb"] + debs(upstream)


def check_opts(upstream: dict, charon_dir: Path, hostname: str | None = None) -> None:
    opts_files = upstream["charon"]["opts_files"]
    for rel, want in opts_files.items():
        real = _sha256(charon_dir / rel)
        if real != want["sha256"]:
            sys.exit(f"inputs: {rel}: tarball has sha256 {real}, upstream.json {want['sha256']}")
        print(f"inputs: {rel} ok ({real})")
    host = (hostname or platform.uname()[1]).split(".")[0]
    for rel in opts_files:
        extra = charon_dir / Path(rel).parent / f"{host}.opts"
        if extra.exists():
            sys.exit(f"inputs: build_charon.py would also read {extra} on host {host!r}")


def sources(upstream: dict, context: Path) -> dict:
    out = {}
    for name in SOURCES:
        e = upstream[name]
        out[e["file"]] = {"sha256": e["sha256"], "url": e["url"], "mirror_url": e["mirror_url"]}
    for sub in ("patches", "opts"):
        for f in sorted((context / sub).iterdir()):
            out[f"{sub}/{f.name}"] = {"sha256": _sha256(f)}
    for name in SCRIPTS:
        out[name] = {"sha256": _sha256(context / name)}
    return out


def record(upstream: dict, context: Path, tests: list[str]) -> dict:
    if not tests:
        sys.exit("inputs: record needs the probe test names")
    c = upstream["charon"]
    opts = {rel: w["sha256"] for rel, w in c["opts_files"].items()}
    opts |= {f"opts/{f.name}": _sha256(f) for f in sorted((context / "opts").iterdir())}
    return {
        "charon": {"version": c["version"], "sha256": c["sha256"]},
        "trilinos": {k: upstream["trilinos"][k] for k in ("commit", "sha256")},
        "tribits": {k: upstream["tribits"][k] for k in ("commit", "sha256")},
        "build_type": "RELEASE",
        "opts": opts,
        "patches": {f.name: _sha256(f) for f in sorted((context / "patches").iterdir())},
        "probe": {"tests": sorted(tests), "result": "passed"},
    }


def _write(path: str, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    a = sys.argv[1:]
    if a[:1] == ["names"] and len(a) == 2:
        print(" ".join(names(_load(a[1]))))
    elif a[:1] == ["debs"] and len(a) == 3:
        up = _load(a[1])
        print("\n".join(str(Path(a[2]) / up[n]["file"]) for n in debs(up)))
    elif a[:1] == ["check-opts"] and len(a) == 3:
        check_opts(_load(a[1]), Path(a[2]))
    elif a[:1] == ["sources"] and len(a) == 4:
        _write(a[3], sources(_load(a[1]), Path(a[2])))
    elif a[:1] == ["record"] and len(a) >= 5:
        _write(a[3], record(_load(a[1]), Path(a[2]), a[4:]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
