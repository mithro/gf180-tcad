# SPDX-License-Identifier: Apache-2.0
"""Helpers of docker/charon-libs/Dockerfile around upstream.json (base image /usr/bin/python3).

inputs.py names UPSTREAM_JSON
    every entry name, the debs in install order last (the fetch_sources.py arguments)
inputs.py debs UPSTREAM_JSON SRC_DIR
    the fetched .deb paths in install order (the dpkg -i arguments)
inputs.py check-opts UPSTREAM_JSON CHARON_DIR OPTS
    the Charon tarball's General.opts and Linux.opts hash to the sha256s recorded in
    upstream.json, and OPTS holds exactly those lines after its header (tests/
    test_charon_libs_inputs.py checks the rest of OPTS on the host)
inputs.py sources UPSTREAM_JSON CONTEXT_DIR OUT_JSON
    SOURCES.json: the Charon, Trilinos and TriBITS tarballs and every patch and opts file of
    the build context, each with its sha256 (the corresponding source of the GPL binaries)
"""

import hashlib
import json
import sys
from pathlib import Path

SOURCES = ("charon", "trilinos", "tribits")


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def debs(upstream: dict) -> list[str]:
    entries = [(e["install_order"], name) for name, e in upstream.items() if e["kind"] == "deb"]
    return [name for _, name in sorted(entries)]


def opts_header_len(lines: list[str]) -> int:
    """Number of leading lines of gf180.opts that are the project's own header comment."""
    n = 0
    while n < len(lines) and lines[n].startswith(
        ("# SPDX", "# gf180-tcad:", "# The next", "# (docker")
    ):
        n += 1
    return n


def check_opts(upstream: dict, charon_dir: Path, opts: Path) -> None:
    lines = opts.read_text(encoding="utf-8").splitlines(keepends=True)
    at = opts_header_len(lines)
    for rel, want in upstream["charon"]["opts_files"].items():
        real = hashlib.sha256((charon_dir / rel).read_bytes()).hexdigest()
        copy = "".join(lines[at : at + want["lines"]]).encode("utf-8")
        at += want["lines"]
        if real != want["sha256"] or hashlib.sha256(copy).hexdigest() != want["sha256"]:
            sys.exit(
                f"inputs: {rel}: tarball {real}, copy in {opts.name} differs or != {want['sha256']}"
            )
        print(f"inputs: {rel} ok ({real})")


def sources(upstream: dict, context: Path) -> dict:
    out = {}
    for name in SOURCES:
        e = upstream[name]
        out[e["file"]] = {"sha256": e["sha256"], "url": e["url"], "mirror_url": e["mirror_url"]}
    for sub in ("patches", "opts"):
        for f in sorted((context / sub).iterdir()):
            out[f"{sub}/{f.name}"] = {"sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
    return out


def main() -> None:
    a = sys.argv[1:]
    if a[:1] == ["names"] and len(a) == 2:
        up = _load(a[1])
        print(" ".join([n for n in sorted(up) if up[n]["kind"] != "deb"] + debs(up)))
    elif a[:1] == ["debs"] and len(a) == 3:
        up = _load(a[1])
        print("\n".join(str(Path(a[2]) / up[n]["file"]) for n in debs(up)))
    elif a[:1] == ["check-opts"] and len(a) == 4:
        check_opts(_load(a[1]), Path(a[2]), Path(a[3]))
    elif a[:1] == ["sources"] and len(a) == 4:
        text = json.dumps(sources(_load(a[1]), Path(a[2])), indent=2, sort_keys=True) + "\n"
        Path(a[3]).write_text(text, encoding="utf-8")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
