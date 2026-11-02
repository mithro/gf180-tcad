# SPDX-License-Identifier: Apache-2.0
"""docker/charon-libs's inputs, on the host with no network and no Docker.

- upstream.json pins every input (Charon 2.2.0 by the sha256 of Sandia's tarball, Trilinos and
  TriBITS by the commits Charon's user manual names, the build-only .debs of one Ubuntu snapshot
  in a dependency order);
- opts/gf180.opts is Charon's General.opts and Linux.opts byte for byte (their sha256s are
  recorded in upstream.json and checked against the tarball in the build) plus allow-listed
  project lines;
- every patch carries the GPL SPDX header, the file it patches and a reason, and is listed in the
  licence note;
- the helper scripts: the fetch script is the dev image's, the deb resolver compares Debian
  versions and resolves dependencies as dpkg would, the build script's SOURCE_DATE_EPOCH inputs
  cover every file the Dockerfile reads.
"""

import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LIBS = REPO / "docker" / "charon-libs"
UPSTREAM = json.loads((LIBS / "upstream.json").read_text(encoding="utf-8"))

CHARON_SHA256 = "2743f39fb14166091f1e38581f9d85379a7db178b4b2d4ce5c8411fdec727073"
TRILINOS_COMMIT = "81e9581a3c5f701d41e6828d0f0e5affcef5373a"
TRIBITS_COMMIT_PREFIX = "769f615fafb"
MIRROR = "https://github.com/mithro/gf180-tcad/releases/download/gf180-tcad/inputs/charon-"

# The project's lines of gf180.opts (option name -> value); anything else after the upstream
# copy fails the test.
PROJECT_LINES = {
    "tcad-charon_ENABLE_DAKOTA_DRIVERS:BOOL": "OFF",
    "Charon_ENABLE_DEBUG:BOOL": "OFF",
    "CMAKE_INSTALL_PREFIX:PATH": "/opt/charon",
    "TPL_BLAS_LIBRARIES:FILEPATH": "/usr/lib/x86_64-linux-gnu/openblas-pthread/libblas.so",
    "TPL_LAPACK_LIBRARIES:FILEPATH": "/usr/lib/x86_64-linux-gnu/openblas-pthread/liblapack.so",
}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"charon_libs_{name}", LIBS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inputs = _load("inputs")
lock_debs = _load("lock_debs")


def test_upstream_json_pins_every_input():
    for name, e in UPSTREAM.items():
        for key in ("url", "mirror_url", "sha256", "license", "role", "file", "kind"):
            assert e.get(key), f"{name}: no {key}"
        assert re.fullmatch(r"[0-9a-f]{64}", e["sha256"]), name
        assert e["mirror_url"].startswith(MIRROR), name
        assert e["url"].startswith("https://"), name
    assert UPSTREAM["charon"]["sha256"] == CHARON_SHA256
    assert UPSTREAM["charon"]["version"] == "2.2.0"
    assert UPSTREAM["trilinos"]["commit"] == TRILINOS_COMMIT
    assert UPSTREAM["trilinos"]["url"].endswith(TRILINOS_COMMIT)
    assert UPSTREAM["tribits"]["commit"].startswith(TRIBITS_COMMIT_PREFIX)
    assert UPSTREAM["tribits"]["url"].endswith(UPSTREAM["tribits"]["commit"])
    # One mirror release for every input.
    assert len({e["mirror_url"].rsplit("/", 1)[0] for e in UPSTREAM.values()}) == 1


def test_debs_come_from_one_snapshot_in_install_order():
    debs = {n: e for n, e in UPSTREAM.items() if e["kind"] == "deb"}
    assert {"libopenmpi-dev", "libnetcdf-dev", "libboost-dev", "libopenblas-dev"} <= set(debs)
    snapshots = {
        re.match(r"https://snapshot\.ubuntu\.com/ubuntu/(\d{8}T\d{6}Z)/pool/", e["url"]).group(1)
        for e in debs.values()
    }
    assert len(snapshots) == 1, snapshots
    assert sorted(e["install_order"] for e in debs.values()) == list(range(len(debs)))
    for name, e in debs.items():
        assert e["file"].startswith(f"{name}_{e['version'].split(':')[-1]}_"), name
        assert e["file"].endswith(("_amd64.deb", "_all.deb")), name
    assert inputs.debs(UPSTREAM)[0] == min(debs, key=lambda n: debs[n]["install_order"])


def test_inputs_names_lists_sources_then_debs():
    names = inputs.debs(UPSTREAM)
    assert set(names) == {n for n, e in UPSTREAM.items() if e["kind"] == "deb"}


def _opts_parts() -> tuple[list[str], list[str]]:
    lines = (LIBS / "opts" / "gf180.opts").read_text(encoding="utf-8").splitlines(keepends=True)
    at = inputs.opts_header_len(lines)
    assert at >= 1 and lines[0] == "# SPDX-License-Identifier: GPL-3.0-or-later\n"
    copies = []
    for want in UPSTREAM["charon"]["opts_files"].values():
        copies.append("".join(lines[at : at + want["lines"]]))
        at += want["lines"]
    return copies, lines[at:]


def test_opts_file_is_upstreams_plus_project_lines():
    opts_files = UPSTREAM["charon"]["opts_files"]
    assert list(opts_files) == ["scripts/build/all/General.opts", "scripts/build/all/Linux.opts"]
    copies, project = _opts_parts()
    for copy, want in zip(copies, opts_files.values(), strict=True):
        assert hashlib.sha256(copy.encode("utf-8")).hexdigest() == want["sha256"]
    seen = {}
    for line in project:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        assert key in PROJECT_LINES, f"project line not allow-listed: {line}"
        seen[key] = value
    assert seen == PROJECT_LINES


def test_patches_are_named_and_hashed():
    patches = sorted((LIBS / "patches").glob("*"))
    assert patches, "no patches"
    readme = (LIBS / "README.md").read_text(encoding="utf-8")
    for i, p in enumerate(patches, start=1):
        assert re.fullmatch(rf"{i:04d}-[a-z0-9-]+\.patch", p.name), p.name
        head = p.read_text(encoding="utf-8").splitlines()[:3]
        assert head[0] == "# SPDX-License-Identifier: GPL-3.0-or-later", p.name
        assert re.fullmatch(r"# Patches: tcad-charon/\S+ \(Charon 2\.2\.0\)\.", head[1]), p.name
        assert head[2].startswith("# Reason: ") and len(head[2]) > 20, p.name
        assert f"`{p.name}`" in readme, f"{p.name} missing from the licence note"
    # The build records each patch with its sha256 in SOURCES.json.
    src = inputs.sources(UPSTREAM, LIBS)
    for p in patches:
        assert src[f"patches/{p.name}"]["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert src["charon-distrib-v2_2.tar.gz"]["sha256"] == CHARON_SHA256


def test_constants_patch_sets_codata_2018():
    text = (LIBS / "patches" / "0001-codata2018-constants.patch").read_text(encoding="utf-8")
    added = [
        ln[1:].strip()
        for ln in text.splitlines()
        if ln.startswith("+") and not ln.startswith("+++")
    ]
    assert added == [
        "kb(1.380649e-23/1.602176634e-19),",
        "q(1.602176634e-19),",
        "eps0(8.8541878128e-12*0.01),",
    ]
    removed = [
        ln[1:].strip()
        for ln in text.splitlines()
        if ln.startswith("-") and not ln.startswith("---")
    ]
    assert removed == ["kb(8.617343e-05),", "q(1.602176487e-19),", "eps0(8.854187817e-12*0.01),"]


def test_fetch_sources_is_the_dev_image_copy():
    dev = (REPO / "docker" / "tcad-dev" / "fetch_sources.py").read_bytes()
    assert (LIBS / "fetch_sources.py").read_bytes() == dev


def test_build_inputs_cover_what_the_dockerfile_reads():
    build = (LIBS / "build").read_text(encoding="utf-8")
    block = re.search(r"^INPUTS=\((.*?)\)$", build, re.MULTILINE | re.DOTALL).group(1)
    listed = set(block.split())
    dockerfile = (LIBS / "Dockerfile").read_text(encoding="utf-8")
    sources = set(re.findall(r"source=([\w./-]+),", dockerfile))
    assert sources == {
        "upstream.json",
        "fetch_sources.py",
        "inputs.py",
        "build-charon.sh",
        "opts",
        "patches",
    }
    for s in sources:
        assert f"docker/charon-libs/{s}" in listed, s
    assert {"docker/charon-libs/Dockerfile", "docker/IMAGE"} <= listed


@pytest.mark.parametrize(
    ("a", "b", "want"),
    [
        ("1.0", "1.0", 0),
        ("1.0~rc1", "1.0", -1),
        ("1:1.0", "2.0", 1),
        ("2.1.12-stable-9ubuntu2.1", "2.1.12-stable-9ubuntu2.2", -1),
        ("13.3.0-6ubuntu2~24.04.1", "13.3.0-6ubuntu2", -1),
        ("1.83.0.1ubuntu2", "1.83.0-2.1ubuntu3.2", 1),
        ("1.0a", "1.0+", -1),
    ],
)
def test_debian_version_order(a, b, want):
    assert lock_debs.vcmp(a, b) == want
    assert lock_debs.vcmp(b, a) == -want


def _pkg(name, version, depends="", provides=""):
    return {
        "Package": name,
        "Version": version,
        "Depends": depends,
        "Provides": provides,
        "Filename": f"pool/main/x/{name}_{version}_amd64.deb",
        "SHA256": "0" * 64,
    }


def test_resolve_skips_installed_and_orders_dependencies():
    pkgs = {
        "a-dev": [_pkg("a-dev", "1", "liba (= 1), b-dev | c-dev, fortran-compiler")],
        "b-dev": [_pkg("b-dev", "2", "libb (>= 2)")],
        "libb": [_pkg("libb", "2"), _pkg("libb", "3")],
        "gfortran": [_pkg("gfortran", "1", provides="fortran-compiler")],
    }
    order = lock_debs.resolve(["a-dev"], pkgs, {"liba": "1"})
    assert [(p["Package"], p["Version"]) for p in order] == [
        ("libb", "3"),
        ("b-dev", "2"),
        ("gfortran", "1"),
        ("a-dev", "1"),
    ]


def test_resolve_refuses_to_replace_a_base_package():
    pkgs = {"a-dev": [_pkg("a-dev", "1", "liba (= 2)")], "liba": [_pkg("liba", "2")]}
    with pytest.raises(SystemExit, match="the base image has 1"):
        lock_debs.resolve(["a-dev"], pkgs, {"liba": "1"})
