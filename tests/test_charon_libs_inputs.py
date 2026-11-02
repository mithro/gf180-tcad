# SPDX-License-Identifier: Apache-2.0
"""docker/charon-libs's inputs, on the host with no network and no Docker.

- upstream.json pins every input (Charon 2.2.0 by the sha256 of Sandia's tarball, Trilinos and
  TriBITS by the commits Charon's user manual names, the build-only .debs of one Ubuntu snapshot
  in a dependency order);
- opts/gf180.opts holds only allow-listed project lines (the build reads Charon's own
  General.opts and Linux.opts from the tarball, whose sha256s upstream.json records and the
  build checks);
- every patch carries the GPL SPDX header, the file it patches and a reason, and is listed in the
  licence note;
- the helper scripts: the fetch script is the dev image's, the deb resolver compares Debian
  versions and resolves dependencies as dpkg would, the build script's SOURCE_DATE_EPOCH inputs
  cover every file the Dockerfile reads, and the build script refuses a builder without a
  memory limit.
"""

import hashlib
import importlib.util
import json
import os
import re
import subprocess
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
    names = inputs.names(UPSTREAM)
    sources = sorted(n for n, e in UPSTREAM.items() if e["kind"] != "deb")
    assert sources == ["charon", "tribits", "trilinos"]
    assert names == sources + inputs.debs(UPSTREAM)
    assert set(inputs.debs(UPSTREAM)) == {n for n, e in UPSTREAM.items() if e["kind"] == "deb"}


def test_opts_file_is_upstreams_plus_project_lines():
    """gf180.opts holds the allow-listed project lines and nothing of Charon's: the build reads
    General.opts and Linux.opts from the tarball (build_charon.py -c) before it (-f), and checks
    them against the sha256s recorded here."""
    opts_files = UPSTREAM["charon"]["opts_files"]
    assert list(opts_files) == ["scripts/build/all/General.opts", "scripts/build/all/Linux.opts"]
    for want in opts_files.values():
        assert re.fullmatch(r"[0-9a-f]{64}", want["sha256"])
    lines = (LIBS / "opts" / "gf180.opts").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# SPDX-License-Identifier: Apache-2.0"
    seen = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        assert key in PROJECT_LINES, f"project line not allow-listed: {line}"
        assert key not in seen, f"repeated: {key}"
        seen[key] = value
    assert seen == PROJECT_LINES
    build = (LIBS / "build-charon.sh").read_text(encoding="utf-8")
    assert '-c "$optdir" -f "$ctx/opts/gf180.opts"' in build


def _fake_charon(tmp_path: Path) -> tuple[dict, Path]:
    """A tarball tree with its own General.opts and Linux.opts, and an upstream.json for it."""
    d = tmp_path / "tcad-charon" / "scripts" / "build" / "all"
    d.mkdir(parents=True)
    (d / "General.opts").write_text("A:BOOL=ON\n", encoding="utf-8")
    (d / "Linux.opts").write_text("B:BOOL=ON\n", encoding="utf-8")
    up = {
        "charon": {
            "opts_files": {
                f"scripts/build/all/{n}": {
                    "sha256": hashlib.sha256((d / n).read_bytes()).hexdigest()
                }
                for n in ("General.opts", "Linux.opts")
            }
        }
    }
    return up, tmp_path / "tcad-charon"


@pytest.mark.parametrize("name", ["General.opts", "Linux.opts"])
def test_check_opts_refuses_a_changed_upstream_opts_file(tmp_path, capsys, name):
    up, charon = _fake_charon(tmp_path)
    inputs.check_opts(up, charon, hostname="buildkitsandbox")
    assert capsys.readouterr().out.count(" ok (") == 2
    f = charon / "scripts" / "build" / "all" / name
    f.write_bytes(f.read_bytes().replace(b"ON", b"OF"))
    with pytest.raises(SystemExit, match=f"{name}: tarball has sha256"):
        inputs.check_opts(up, charon, hostname="buildkitsandbox")


def test_check_opts_refuses_a_host_opts_file(tmp_path):
    """build_charon.py -c also reads <hostname>.opts from that directory when one exists."""
    up, charon = _fake_charon(tmp_path)
    (charon / "scripts" / "build" / "all" / "chama.opts").write_text("C=1\n", encoding="utf-8")
    inputs.check_opts(up, charon, hostname="buildkitsandbox")
    with pytest.raises(SystemExit, match="would also read"):
        inputs.check_opts(up, charon, hostname="chama.example")


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


def test_sources_json_lists_the_build_scripts():
    """GPL corresponding source includes the scripts that control the build."""
    src = inputs.sources(UPSTREAM, LIBS)
    for name in ("Dockerfile", "build", "build-charon.sh", "fetch_sources.py", "inputs.py"):
        assert src[name]["sha256"] == hashlib.sha256((LIBS / name).read_bytes()).hexdigest()
    assert src["opts/gf180.opts"]["sha256"]


def test_build_record_names_the_inputs_and_the_probe():
    build = (LIBS / "build-charon.sh").read_text(encoding="utf-8")
    block = re.search(r"^PROBE_TESTS=\((.*?)\)$", build, re.MULTILINE | re.DOTALL).group(1)
    tests = block.split()
    assert tests == [
        "Charon_charon_mp_pmoscap.nlp",
        "Charon_charon_mp.hb.loca-moscap-cv.ox",
        "Charon_charon_mp.hb.loca-moscap-cv.sub",
        "Charon_charon_mp_pndiode.nlp",
    ]
    assert "--no-tests=error" in build
    rec = inputs.record(UPSTREAM, LIBS, tests)
    assert rec["charon"] == {"version": "2.2.0", "sha256": CHARON_SHA256}
    assert rec["trilinos"]["commit"] == TRILINOS_COMMIT
    assert rec["probe"] == {"tests": sorted(tests), "result": "passed"}
    assert set(rec["opts"]) == {*UPSTREAM["charon"]["opts_files"], "opts/gf180.opts"}
    assert set(rec["patches"]) == {p.name for p in (LIBS / "patches").iterdir()}
    with pytest.raises(SystemExit):
        inputs.record(UPSTREAM, LIBS, [])


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
        "Dockerfile",
        "build",
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
    # SOURCES.json hashes every build script, so each is mounted into the build step.
    for name in inputs.SCRIPTS:
        assert name in sources, name


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
        ("1:2.0:1-1", "1:2.0:0-1", 1),
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


# --- docker/charon-libs/build: the memory-limited builder ------------------------------------

BUILD = LIBS / "build"
_BUILD_TEXT = BUILD.read_text(encoding="utf-8")
BUILDKIT_IMAGE = re.search(r'^BUILDKIT_IMAGE="([^"]+)"$', _BUILD_TEXT, re.MULTILINE).group(1)
DEFAULT_BUILDER = re.search(r'BUILDER="\$\{GF180TCAD_BUILDER:-([^}]+)\}"', _BUILD_TEXT).group(1)

# A ``docker`` stand-in: logs every call; ``buildx inspect`` prints $FAKE_STATE/inspect.txt (or
# fails if there is none), ``buildx create`` writes it from its own --driver-opt options, and
# ``buildx build`` fails (these tests stop before or at the build).
_FAKE_DOCKER = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_STATE/calls.log"
case "$1 $2" in
    "buildx inspect") [ -f "$FAKE_STATE/inspect.txt" ] || exit 1; cat "$FAKE_STATE/inspect.txt" ;;
    "buildx create")
        shift 2; opts=""
        while [ $# -gt 0 ]; do
            case "$1" in
                --driver-opt) k="${2%%=*}"; opts+=" $k=\"${2#*=}\""; shift 2 ;;
                *) shift ;;
            esac
        done
        printf 'Name: x\nDriver:        docker-container\n\nNodes:\nDriver Options:      %s\n' \
            "$opts" > "$FAKE_STATE/inspect.txt" ;;
    *) exit 3 ;;
esac
"""


def _inspect(opts: str) -> str:
    return (
        "Name:          b\nDriver:        docker-container\n\nNodes:\nName:                  b0\n"
        f"Driver Options:        {opts}\nStatus:                stopped\n"
    )


def _run_build(tmp_path, inspect: str | None):
    bindir, state = tmp_path / "bin", tmp_path / "state"
    bindir.mkdir()
    state.mkdir()
    docker = bindir / "docker"
    docker.write_text(_FAKE_DOCKER, encoding="utf-8")
    docker.chmod(0o755)
    if inspect is not None:
        (state / "inspect.txt").write_text(inspect, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "GF180TCAD_BUILDER"}
    env |= {"PATH": f"{bindir}:{env['PATH']}", "FAKE_STATE": str(state)}
    res = subprocess.run([str(BUILD)], capture_output=True, text=True, env=env, check=False)
    calls = (state / "calls.log").read_text(encoding="utf-8").splitlines()
    return res, calls


_SLICE = 'cgroup-parent="gf180-tcad.slice" '


@pytest.mark.parametrize(
    "opts",
    [
        'image="{img}"',
        _SLICE + 'image="{img}" memory="16g"',
        _SLICE + 'image="{img}" memory="16g" memory-swap="32g"',
        _SLICE + 'image="{img}" memory-swap="16g"',
        _SLICE + 'image="{img}" memory="17g" memory-swap="17g"',
        _SLICE + 'image="{img}" memory="lots" memory-swap="lots"',
        'image="{img}" memory="16g" memory-swap="16g"',
        'cgroup-parent="other.slice" image="{img}" memory="16g" memory-swap="16g"',
    ],
)
def test_build_refuses_a_builder_without_the_limits(tmp_path, opts):
    """No memory limit, one above 16 GiB, swap above it, or a builder outside gf180-tcad.slice."""
    res, calls = _run_build(tmp_path, _inspect(opts.format(img=BUILDKIT_IMAGE)))
    assert res.returncode == 2, res.stderr
    assert "no memory limit of at most 16 GiB" in res.stderr
    assert not [c for c in calls if c.startswith("buildx build")]


@pytest.mark.parametrize("mem", ["16g", "8G", "16384m", "17179869184"])
def test_build_accepts_a_limit_of_at_most_16g_in_the_slice(tmp_path, mem):
    opts = _SLICE + f'image="{BUILDKIT_IMAGE}" memory="{mem}" memory-swap="{mem}"'
    res, _calls = _run_build(tmp_path, _inspect(opts))
    assert "build: builder" not in res.stderr, res.stderr


def test_build_accepts_the_16g_builder(tmp_path):
    opts = (
        f'cgroup-parent="gf180-tcad.slice" image="{BUILDKIT_IMAGE}" memory="16g" memory-swap="16g"'
    )
    res, _calls = _run_build(tmp_path, _inspect(opts))
    assert "build: builder" not in res.stderr, res.stderr


def test_build_creates_the_16g_builder_in_the_slice(tmp_path):
    res, calls = _run_build(tmp_path, None)
    assert "build: builder" not in res.stderr, res.stderr
    assert calls[1] == (
        f"buildx create --name {DEFAULT_BUILDER} --driver docker-container "
        f"--driver-opt image={BUILDKIT_IMAGE} --driver-opt memory=16g "
        "--driver-opt memory-swap=16g --driver-opt cgroup-parent=gf180-tcad.slice"
    )
