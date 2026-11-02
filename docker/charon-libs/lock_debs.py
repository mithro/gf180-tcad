# SPDX-License-Identifier: Apache-2.0
"""Pin the Ubuntu .deb files the charon-libs build stage installs on top of the base image.

Run on the host (network, no Docker):
    uv run --locked python docker/charon-libs/lock_debs.py --tag MIRROR_TAG SNAPSHOT INSTALLED \
        OUT_JSON PACKAGE...

SNAPSHOT is a snapshot.ubuntu.com timestamp (for example 20261015T000000Z, the one
docker/tcad-dev/upstream.json uses for its GCC 14 packages). INSTALLED is the output of
``dpkg-query -W -f '${Package}\\t${Version}\\t${Status}\\n'`` run in the base image
(docker/IMAGE). The tool reads the noble, noble-updates and noble-security indexes (main and
universe, amd64) of that snapshot, resolves the Depends and Pre-Depends of every PACKAGE (not
Recommends or Suggests), and keeps what the base image does not already satisfy. A dependency
that the base image has installed at a version that does not satisfy the constraint is an error:
the build stage never upgrades a package of the base image. The tool reads no Breaks,
Conflicts or Replaces field: ``dpkg -i`` refuses a package that Breaks or Conflicts with an
installed one, but a package that Replaces files of a base image package is not detected.
OUT_JSON (upstream.json) keeps its other entries; its ``deb`` entries are replaced by one per resolved .deb (``url`` in the snapshot
pool, ``sha256`` from the index, ``install_order`` its place in dependency order, so that
``dpkg -i`` in that order sees each package after its dependencies).
"""

import json
import lzma
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SUITES = ("noble", "noble-updates", "noble-security")
COMPONENTS = ("main", "universe")
ARCH = "amd64"
MIRROR = "https://github.com/mithro/gf180-tcad/releases/download/gf180-tcad/inputs/{tag}/{file}"


# --- Debian version comparison (Debian Policy 5.6.12) ---------------------------------------
def _order(c: str) -> int:
    if c == "~":
        return -1
    if c.isdigit():
        return 0
    if c.isalpha():
        return ord(c)
    return ord(c) + 256


def _cmp_part(a: str, b: str) -> int:
    while a or b:
        na = re.match(r"^\D*", a).group(0)
        nb = re.match(r"^\D*", b).group(0)
        for i in range(max(len(na), len(nb))):
            ca = _order(na[i]) if i < len(na) else 0
            cb = _order(nb[i]) if i < len(nb) else 0
            if ca != cb:
                return -1 if ca < cb else 1
        a, b = a[len(na) :], b[len(nb) :]
        da = re.match(r"^\d*", a).group(0)
        db = re.match(r"^\d*", b).group(0)
        ia, ib = int(da or 0), int(db or 0)
        if ia != ib:
            return -1 if ia < ib else 1
        a, b = a[len(da) :], b[len(db) :]
    return 0


def _split(v: str) -> tuple[int, str, str]:
    # The epoch ends at the first colon; the upstream version may hold more colons.
    epoch, _, rest = v.partition(":") if ":" in v else ("0", "", v)
    upstream, _, rev = rest.rpartition("-") if "-" in rest else (rest, "", "0")
    return int(epoch or 0), upstream, rev


def vcmp(a: str, b: str) -> int:
    ea, ua, ra = _split(a)
    eb, ub, rb = _split(b)
    if ea != eb:
        return -1 if ea < eb else 1
    return _cmp_part(ua, ub) or _cmp_part(ra, rb)


def satisfies(version: str, op: str | None, want: str | None) -> bool:
    if op is None:
        return True
    c = vcmp(version, want)
    return {"<<": c < 0, "<=": c <= 0, "=": c == 0, ">=": c >= 0, ">>": c > 0}[op]


# --- indexes -----------------------------------------------------------------------------------
def parse_index(text: str) -> list[dict]:
    out = []
    for para in text.split("\n\n"):
        fields: dict[str, str] = {}
        key = None
        for line in para.splitlines():
            if line.startswith((" ", "\t")) and key:
                fields[key] += "\n" + line.strip()
            elif ":" in line:
                key, _, val = line.partition(":")
                fields[key] = val.strip()
        if "Package" in fields:
            out.append(fields)
    return out


def parse_relation(text: str) -> list[list[tuple[str, str | None, str | None]]]:
    """'a (>= 1) | b, c' -> [[(a, '>=', '1'), (b, None, None)], [(c, None, None)]]."""
    groups = []
    for group in filter(None, (g.strip() for g in text.split(","))):
        alts = []
        for alt in group.split("|"):
            m = re.match(
                r"^\s*([^\s(:]+)(?::\S+)?\s*(?:\(\s*(<<|<=|=|>=|>>)\s*([^)\s]+)\s*\))?", alt
            )
            alts.append((m.group(1), m.group(2), m.group(3)))
        groups.append(alts)
    return groups


def load_indexes(snapshot: str) -> dict[str, list[dict]]:
    base = f"https://snapshot.ubuntu.com/ubuntu/{snapshot}"
    pkgs: dict[str, list[dict]] = {}
    for suite in SUITES:
        for comp in COMPONENTS:
            url = f"{base}/dists/{suite}/{comp}/binary-{ARCH}/Packages.xz"
            with urllib.request.urlopen(url, timeout=300) as resp:
                text = lzma.decompress(resp.read()).decode("utf-8")
            for p in parse_index(text):
                p["_base"] = base
                pkgs.setdefault(p["Package"], []).append(p)
    return pkgs


def load_installed(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[2] == "install ok installed":
            out[parts[0]] = parts[1]
    return out


def resolve(
    wanted: list[str], pkgs: dict[str, list[dict]], installed: dict[str, str]
) -> list[dict]:
    providers: dict[str, list[dict]] = {}
    for cands in pkgs.values():
        for p in cands:
            for name, _op, _v in (a for g in parse_relation(p.get("Provides", "")) for a in g):
                providers.setdefault(name, []).append(p)
    chosen: dict[str, dict] = {}
    order: list[dict] = []

    def best(name: str, op, want) -> dict | None:
        cands = [p for p in pkgs.get(name, []) if satisfies(p["Version"], op, want)]
        cands.sort(key=lambda p: _Key(p["Version"]), reverse=True)
        return cands[0] if cands else None

    def ok_installed(name: str, op, want) -> bool:
        return name in installed and satisfies(installed[name], op, want)

    def visit(p: dict, stack: tuple[str, ...]) -> None:
        name = p["Package"]
        if name in chosen:
            return
        chosen[name] = p
        rel = ", ".join(filter(None, (p.get("Pre-Depends", ""), p.get("Depends", ""))))
        for group in parse_relation(rel):
            if any(ok_installed(n, op, v) for n, op, v in group):
                continue
            if any(n in chosen and satisfies(chosen[n]["Version"], op, v) for n, op, v in group):
                continue
            if any(
                op is None
                and any(
                    q["Package"] in installed or q["Package"] in chosen
                    for q in providers.get(n, [])
                )
                for n, op, v in group
            ):
                continue
            pick = None
            for n, op, v in group:
                if n in installed:
                    sys.exit(
                        f"lock_debs: {name} needs {n} {op} {v}; the base image has {installed[n]}"
                    )
                pick = best(n, op, v)
                if pick is None and op is None and providers.get(n):
                    pick = min(providers[n], key=lambda q: q["Package"])
                if pick is not None:
                    break
            if pick is None:
                sys.exit(f"lock_debs: {name}: cannot satisfy {group} (via {' > '.join(stack)})")
            visit(pick, (*stack, pick["Package"]))
        order.append(p)

    for w in wanted:
        if w in installed:
            continue
        p = best(w, None, None)
        if p is None:
            sys.exit(f"lock_debs: no package {w}")
        visit(p, (w,))
    return order


class _Key:
    def __init__(self, v: str):
        self.v = v

    def __lt__(self, other: "_Key") -> bool:
        return vcmp(self.v, other.v) < 0


def entry(p: dict, tag: str, snapshot: str) -> dict:
    path = p["Filename"]
    file = path.rsplit("/", 1)[1]
    # GitHub release assets cannot hold '~' or '+' faithfully: the mirror name replaces '~'
    # with '.' as docker/tcad-dev/upstream.json does; '+' is percent-encoded in the URL.
    mirror_file = file.replace("~", ".")
    return {
        "file": urllib.parse.unquote(file),
        "kind": "deb",
        "license": f"Ubuntu package; licence in /usr/share/doc/{p['Package']}/copyright",
        "mirror_url": MIRROR.format(tag=tag, file=urllib.parse.quote(mirror_file)),
        "role": "charon-libs build stage only (Trilinos/Charon build dependency)",
        "sha256": p["SHA256"],
        "url": f"https://snapshot.ubuntu.com/ubuntu/{snapshot}/{urllib.parse.quote(path)}",
        "version": p["Version"],
    }


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 5 or args[0] != "--tag":
        sys.exit("usage: lock_debs.py --tag MIRROR_TAG SNAPSHOT INSTALLED OUT_JSON PACKAGE...")
    tag, snapshot, installed_path, out, wanted = (
        args[1],
        args[2],
        Path(args[3]),
        Path(args[4]),
        args[5:],
    )
    installed = load_installed(installed_path)
    order = resolve(wanted, load_indexes(snapshot), installed)
    result = {}
    if Path(out).exists():
        old = json.loads(Path(out).read_text(encoding="utf-8"))
        result = {k: v for k, v in old.items() if v.get("kind") != "deb"}
    for i, p in enumerate(order):
        result[p["Package"]] = entry(p, tag, snapshot) | {"install_order": i}
    Path(out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for p in order:
        print(f"{p['Package']} {p['Version']}")


if __name__ == "__main__":
    main()
