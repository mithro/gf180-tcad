# SPDX-License-Identifier: Apache-2.0
"""The two Charon images: charon-libs and charon.

charon-libs (docker/CHARON_LIBS_IMAGE) holds Charon 2.2.0 and Trilinos built from source. charon
(docker/CHARON_IMAGE) is the dev-HEAD TCAD image plus that /opt/charon and netCDF4.

The tests without a mark read only committed files. The sandbox-marked tests run inside the
pinned images through ``sandbox.run(image=...)`` (``pytest -m sandbox``), under exactly the
conditions of tools/sandbox-run: no network, read-only root filesystem with a tmpfs ``/tmp``,
a pids limit, one process (no ``mpirun``). The Charon solves run in both images (the ``image``
fixture). The upstream test decks they run are the ones charon-libs installs under
/opt/charon/share/gf180tcad/tests (copied from the Charon tarball); charon copies them with
/opt/charon.
"""

import importlib.util
import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from gf180tcad import sandbox

REPO = Path(__file__).resolve().parents[1]
DOCKER = REPO / "docker"
LIBS = DOCKER / "charon-libs"
PIN = DOCKER / "CHARON_LIBS_IMAGE"
VERSIONS = LIBS / "versions.json"
UPSTREAM = json.loads((LIBS / "upstream.json").read_text(encoding="utf-8"))
KEYS = {
    "base",
    "base_image_ref",
    "charon_build",
    "charon_mp_sha256",
    "compilers",
    "kokkos_backends",
    "runtime_packages",
    "sources",
}
CHARON = DOCKER / "charon"
CHARON_PIN = DOCKER / "CHARON_IMAGE"
CHARON_VERSIONS = CHARON / "versions.json"
# The keys of charon-libs that the charon probe reports with the same values (/opt/charon is
# copied unchanged and both images have the same Debian packages).
SHARED_KEYS = KEYS - {"base", "base_image_ref"}
CHARON_KEYS = SHARED_KEYS | {
    "tcad_dev",
    "tcad_dev_image_ref",
    "charon_libs_image_ref",
    "netcdf4_python",
}
TESTS = "/opt/charon/share/gf180tcad/tests"
# The OpenMPI settings both images set so that charon_mp.exe runs as a singleton in the sandbox.
OMPI_ENV = {"OMPI_MCA_ess_singleton_isolated": "1"}
# What the charon image adds to the dev image's environment (issue #124).
CHARON_ENV = {
    "CHARON_EXECUTABLE_PATH": "/opt/charon/bin",
    "CHARON_EXECUTABLE": "charon_mp.exe",
    "PYTHON_CPU_COUNT": "1",
}
PINS = {"charon-libs": PIN, "charon": CHARON_PIN}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"charon_libs_{name}", LIBS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inputs = _load("inputs")


def _image(name: str = "charon-libs") -> str:
    return PINS[name].read_text(encoding="utf-8").strip()


@pytest.fixture(params=sorted(PINS))
def image(request) -> str:
    """The name of a Charon image ("charon" or "charon-libs"); the solves run in both."""
    return request.param


def _probe_tests() -> list[str]:
    build = (LIBS / "build-charon.sh").read_text(encoding="utf-8")
    block = re.search(r"^PROBE_TESTS=\((.*?)\)$", build, re.MULTILINE | re.DOTALL).group(1)
    return block.split()


def _run(script: str, tmp_path: Path, image: str = "charon-libs") -> str:
    res = sandbox.run(
        ["bash", "-euo", "pipefail", "-c", script], out_dir=tmp_path, image=_image(image)
    )
    return res.stdout


# --- committed files (no Docker) -------------------------------------------------------------


def test_charon_libs_image_pinned_by_digest():
    text = PIN.read_text(encoding="utf-8")
    assert re.fullmatch(r"ghcr\.io/mithro/gf180-tcad-charon-libs@sha256:[0-9a-f]{64}\n", text)


def test_charon_libs_image_id_is_a_digest():
    text = (LIBS / "IMAGE_ID").read_text(encoding="utf-8")
    assert re.fullmatch(r"sha256:[0-9a-f]{64}\n", text)
    for other in ("base", "tcad", "tcad-dev"):
        assert text != (DOCKER / other / "IMAGE_ID").read_text(encoding="utf-8"), other


def test_charon_libs_versions_json_shape():
    text = VERSIONS.read_text(encoding="utf-8")
    data = json.loads(text)
    assert set(data) == KEYS
    assert text == json.dumps(data, indent=2, sort_keys=True) + "\n"
    # built FROM the pinned base image, which the base probe describes
    assert data["base_image_ref"] == (DOCKER / "IMAGE").read_text(encoding="utf-8").strip()
    assert data["base"] == json.loads((DOCKER / "base" / "versions.json").read_text("utf-8"))
    # the build record and the corresponding-source list are those of the committed recipe
    assert data["charon_build"] == inputs.record(UPSTREAM, LIBS, _probe_tests())
    assert data["sources"] == inputs.sources(UPSTREAM, LIBS)
    assert re.fullmatch(r"[0-9a-f]{64}", data["charon_mp_sha256"])
    assert data["compilers"] and all(c.startswith("GCC: ") for c in data["compilers"])
    assert data["kokkos_backends"] == ["Serial"]
    assert any(p.startswith("libopenmpi") for p in data["runtime_packages"])


def test_charon_libs_installs_the_upstream_test_decks():
    """The sandbox tests below need the upstream decks in the image (the source tree is not)."""
    dockerfile = (LIBS / "Dockerfile").read_text(encoding="utf-8")
    for deck in (
        "capability/pmoscap.nlp.inp",
        "capability/pmoscap.exo",
        "freqdom/loca_moscap_cv/moscap.hb.locaOxide.1e0Hz.inp",
        "freqdom/loca_moscap_cv/moscap.dd.equ.exo",
    ):
        assert f"test/nightlyTests/{deck}" in dockerfile, deck
    assert TESTS in dockerfile


def test_charon_libs_sets_the_mpi_singleton_environment():
    dockerfile = (LIBS / "Dockerfile").read_text(encoding="utf-8")
    final = dockerfile[dockerfile.rindex("FROM ${BASE_IMAGE}") :]
    for k, v in OMPI_ENV.items():
        assert f"{k}={v}" in final, k


# --- the charon image: committed files (no Docker) -------------------------------------------


def _requirements(path: Path) -> dict[str, str]:
    """name -> version of a hashed requirements file; every requirement has a sha256 hash."""
    text = path.read_text(encoding="utf-8")
    reqs = {}
    for block in re.split(r"\n(?=\S)", text):
        m = re.match(r"([A-Za-z0-9_.-]+)==(\S+) \\\n", block)
        if m:
            assert re.search(r"--hash=sha256:[0-9a-f]{64}", block), m.group(1)
            reqs[m.group(1).lower()] = m.group(2)
    return reqs


def _lock_command() -> list[str]:
    head = (CHARON / "requirements.lock").read_text(encoding="utf-8").splitlines()[1]
    assert head.startswith("#    uv pip compile "), head
    return shlex.split(head.removeprefix("#    "))


def test_charon_image_pinned_by_digest():
    text = CHARON_PIN.read_text(encoding="utf-8")
    assert re.fullmatch(r"ghcr\.io/mithro/gf180-tcad-charon@sha256:[0-9a-f]{64}\n", text)


def test_charon_image_id_is_a_digest():
    text = (CHARON / "IMAGE_ID").read_text(encoding="utf-8")
    assert re.fullmatch(r"sha256:[0-9a-f]{64}\n", text)
    for other in ("base", "tcad", "tcad-dev", "charon-libs"):
        assert text != (DOCKER / other / "IMAGE_ID").read_text(encoding="utf-8"), other


def test_charon_versions_json_shape():
    text = CHARON_VERSIONS.read_text(encoding="utf-8")
    data = json.loads(text)
    assert set(data) == CHARON_KEYS
    assert text == json.dumps(data, indent=2, sort_keys=True) + "\n"
    # built FROM the pinned dev image, which the dev probe describes
    assert data["tcad_dev_image_ref"] == (DOCKER / "TCAD_DEV_IMAGE").read_text("utf-8").strip()
    assert data["tcad_dev"] == json.loads(
        (DOCKER / "tcad-dev" / "versions.json").read_text("utf-8")
    )
    # /opt/charon is the pinned charon-libs image's, unchanged
    assert data["charon_libs_image_ref"] == _image("charon-libs")
    libs = json.loads(VERSIONS.read_text(encoding="utf-8"))
    for k in SHARED_KEYS:
        assert data[k] == libs[k], k
    # the venv's netCDF4 and cftime are the locked ones
    reqs = _requirements(CHARON / "requirements.lock")
    nc = data["netcdf4_python"]
    assert set(nc) == {"netCDF4", "cftime", "netcdf_c", "hdf5"}
    assert nc["netCDF4"] == reqs["netcdf4"]
    assert nc["cftime"] == reqs["cftime"]
    assert all(isinstance(v, str) and v for v in nc.values())


def test_charon_requirements_lock_is_hashed_and_python_313():
    """netCDF4 and cftime only, hashed, compiled for the dev image's CPython patch.

    numpy and certifi, netCDF4's other dependencies, are the dev venv's (the install uses
    --no-deps); test_charon_netcdf4_dependencies_are_installed checks them in the image.
    """
    reqs = _requirements(CHARON / "requirements.lock")
    assert set(reqs) == {"netcdf4", "cftime"}
    m = re.search(
        r"^ARG TCAD_PYTHON=(3\.13\.\d+)$",
        (DOCKER / "tcad-dev" / "Dockerfile").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert m, "docker/tcad-dev/Dockerfile must pin ARG TCAD_PYTHON=3.13.<patch>"
    assert re.fullmatch(
        r"uv pip compile docker/charon/requirements\.in --no-deps --generate-hashes "
        rf"--python-version {re.escape(m.group(1))} --python-platform x86_64-manylinux_2_28 "
        r"--exclude-newer \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ",
        shlex.join(_lock_command()),
    )


def test_charon_requirements_lock_fresh():
    """Re-running the recorded command reproduces the lock (needs network)."""
    uv = shutil.which("uv")
    assert uv, "uv is required to check docker/charon/requirements.lock"
    res = subprocess.run(
        [uv, *_lock_command()[1:]], cwd=REPO, capture_output=True, text=True, check=True
    )

    def body(text: str) -> list[str]:
        return [ln for ln in text.splitlines() if not ln.startswith("#    uv pip compile ")]

    have = (CHARON / "requirements.lock").read_text(encoding="utf-8")
    assert body(have) == body(res.stdout), "docker/charon/requirements.lock is stale"


def test_charon_dockerfile_layers():
    """FROM the dev image, /opt/charon from the pinned charon-libs image, the issue #124 ENV."""
    dockerfile = (CHARON / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM ${CHARON_LIBS_IMAGE} AS charon-libs" in dockerfile
    final = dockerfile[dockerfile.rindex("FROM ${TCAD_DEV_IMAGE}\n") :]
    assert "COPY --from=charon-libs /opt/charon /opt/charon" in final
    assert "--require-hashes --no-deps --only-binary=:all:" in final
    assert "--network=none" in final
    assert "build-charon.sh check-runtime /opt/charon" in final
    for k, v in {**CHARON_ENV, **OMPI_ENV}.items():
        assert f"{k}={v}" in final, k
    assert "PATH=/opt/charon/bin:${PATH}" in final
    assert "GF180TCAD_CHARON_LIBS_IMAGE=${CHARON_LIBS_IMAGE}" in final
    assert "GF180TCAD_CHARON_TCAD_DEV_IMAGE=${TCAD_DEV_IMAGE}" in final
    assert 'licenses="GPL-3.0-or-later AND' in final


def test_charon_build_inputs_cover_what_the_dockerfile_reads():
    """Every file the Dockerfile mounts dates the build (SOURCE_DATE_EPOCH), and both pins do."""
    build = (CHARON / "build").read_text(encoding="utf-8")
    block = re.search(r"^INPUTS=\((.*?)\)$", build, re.MULTILINE | re.DOTALL).group(1)
    listed = set(block.split())
    dockerfile = (CHARON / "Dockerfile").read_text(encoding="utf-8")
    mounts = re.findall(r"--mount=type=bind,(?:from=([\w-]+),)?source=([\w./-]+),", dockerfile)
    want = set()
    for ctx, src in mounts:
        if ctx == "":
            want.add(f"docker/charon/{src}")
        elif ctx == "charon-libs-recipe":
            want.add(f"docker/charon-libs/{src}")
        else:
            assert ctx == "wheels", ctx  # a build stage, not a file
    assert want == {"docker/charon/requirements.lock", "docker/charon-libs/build-charon.sh"}
    assert (
        want
        | {
            "docker/charon/Dockerfile",
            "docker/charon/build",
            "docker/TCAD_DEV_IMAGE",
            "docker/CHARON_LIBS_IMAGE",
        }
        == listed
    )
    assert '--build-context "charon-libs-recipe=$REPO/docker/charon-libs"' in build


# --- inside the pinned image (Docker) --------------------------------------------------------


@pytest.mark.sandbox
def test_charon_libs_versions_json_matches_image(tmp_path):
    res = sandbox.run(
        ["python3", "/work/src/docker/charon-libs/probe_versions.py"],
        out_dir=tmp_path,
        image=_image(),
    )
    assert res.stdout == VERSIONS.read_text(encoding="utf-8")


@pytest.mark.sandbox
def test_charon_versions_json_matches_image(tmp_path):
    res = sandbox.run(
        ["python3", "/work/src/docker/charon/probe_versions.py"],
        out_dir=tmp_path,
        image=_image("charon"),
    )
    assert res.stdout == CHARON_VERSIONS.read_text(encoding="utf-8")


@pytest.mark.sandbox
def test_charon_netcdf4_dependencies_are_installed(tmp_path):
    """The --no-deps install left nothing out: every requirement of netCDF4 and cftime is met."""
    script = (
        "from importlib.metadata import requires, version\n"
        "from packaging.requirements import Requirement\n"
        "for dist in ('netCDF4', 'cftime'):\n"
        "    for r in map(Requirement, requires(dist) or []):\n"
        "        if r.marker and not r.marker.evaluate({'extra': ''}):\n"
        "            continue\n"
        "        ok = r.specifier.contains(version(r.name), prereleases=True)\n"
        "        print(dist, r.name, version(r.name), 'ok' if ok else 'MISSING')\n"
    )
    out = _run(f"python3 -c {shlex.quote(script)}", tmp_path, "charon")
    assert "MISSING" not in out, out
    assert re.search(r"^netCDF4 numpy ", out, re.MULTILINE), out
    assert re.search(r"^netCDF4 cftime ", out, re.MULTILINE), out


@pytest.mark.sandbox
def test_charon_environment(image, tmp_path):
    """PATH, one OpenMP thread, the singleton setting, and charon_mp.exe starting without mpirun.

    charon_mp.exe has no ``--version``; ``--help`` prints the usage and then ends through
    MPI_Abort (exit 14), so the test reads the usage text, not the exit code. The charon image
    also sets CHARON_EXECUTABLE_PATH, CHARON_EXECUTABLE and PYTHON_CPU_COUNT=1, and its PATH is
    /opt/charon/bin followed by exactly the dev image's PATH (the TCAD venv first).
    """
    out = _run(
        "echo PATH=$PATH; echo OMP=$OMP_NUM_THREADS; command -v charon_mp.exe; "
        "env | grep -E '^(OMPI_MCA_|CHARON_|PYTHON_CPU_COUNT=|GF180TCAD_CHARON_)' | sort; "
        "command -v python3; { charon_mp.exe --help 2>&1 || echo help-exit=$?; }",
        tmp_path,
        image,
    )
    assert "PATH=/opt/charon/bin:" in out
    if image == "charon":
        for k, v in CHARON_ENV.items():
            assert f"\n{k}={v}\n" in out, k
        assert f"\nGF180TCAD_CHARON_LIBS_IMAGE={_image('charon-libs')}\n" in out
        dev = (DOCKER / "TCAD_DEV_IMAGE").read_text(encoding="utf-8").strip()
        assert f"\nGF180TCAD_CHARON_TCAD_DEV_IMAGE={dev}\n" in out
        assert "PATH=/opt/charon/bin:/opt/gf180tcad-tcad/bin:" in out
        assert "\n/opt/gf180tcad-tcad/bin/python3\n" in out
    else:
        assert not set(CHARON_ENV) & set(re.findall(r"^(\w+)=", out, re.MULTILINE)), out
    assert "OMP=1" in out
    assert "/opt/charon/bin/charon_mp.exe" in out
    for k, v in OMPI_ENV.items():
        assert f"{k}={v}" in out, k
    assert "Usage: charon_mp.exe [options]" in out
    assert re.search(r"^\s*--i\s+string\s+Charon input xml/yaml filename", out, re.MULTILINE)


# While the solve runs, sample the process's thread count, the process list and /tmp every
# 0.2 s (until it is a zombie: `wait` has not reaped it yet).
_SAMPLE = (
    "while [ -e /proc/$pid/status ] && ! grep -q '^State:[[:space:]]*Z' /proc/$pid/status; do "
    "grep '^Threads:' /proc/$pid/status >> threads.txt; ps -eo comm >> procs.txt; "
    "ls -a /tmp >> tmpls.txt; sleep 0.2; done;"
)
LOCA = "moscap.hb.locaOxide.1e0Hz.inp"


def _solve(
    tmp_path: Path,
    deck: str,
    mesh: str,
    image: str,
    *,
    args: str = "",
    sample: bool = False,
) -> str:
    """Run an upstream deck as one process (no mpirun) in the workdir; return charon's log."""
    return _run(
        f"cp {TESTS}/{deck} {TESTS}/{mesh} . && "
        f"charonInterpreter.py -i {deck} > interp.log && "
        f"{{ charon_mp.exe --i={deck}.xml {args} > charon.log 2>&1 & pid=$!; "
        f"{_SAMPLE if sample else ''} wait $pid; }}; cat charon.log",
        tmp_path,
        image,
    )


@pytest.mark.sandbox
def test_charon_runs_the_upstream_pmoscap_nlp(image, tmp_path):
    out = _solve(tmp_path, "pmoscap.nlp.inp", "pmoscap.exo", image)
    assert "Charon run completed." in out
    assert (tmp_path / "pmoscap.nlp.exo").stat().st_size > 0
    info = _run("io_info pmoscap.nlp.exo", tmp_path, image)
    # the nonlinear Poisson solve writes one state to the output Exodus file
    assert re.search(r"^\s*Time steps\s*=\s*1\s*$", info, re.MULTILINE), info
    if image == "charon":
        # the venv's netCDF4 reads the same file: one time step
        steps = _run(
            'python3 -c "import netCDF4; '
            "print('steps', netCDF4.Dataset('pmoscap.nlp.exo').dimensions['time_step'].size)\"",
            tmp_path,
            image,
        )
        assert steps.strip() == "steps 1", steps


@pytest.mark.sandbox
def test_charon_mpi_singleton_in_the_sandbox(image, tmp_path):
    """Experiment A3: one rank, no orted, no PMIx shared-memory files, session under /tmp.

    tools/sandbox-run gives no network and a read-only root with only /tmp writable, so a
    write elsewhere would end the run. Without OMPI_MCA_ess_singleton_isolated=1 OpenMPI 4.1
    forks `orted` and writes /tmp/pmix-gds-shmem.* files (Experiment A3, A-2).
    """
    out = _solve(tmp_path, LOCA, "moscap.dd.equ.exo", image, args="--current", sample=True)
    assert "Charon run completed." in out
    procs = set((tmp_path / "procs.txt").read_text(encoding="utf-8").split())
    assert "charon_mp.exe" in procs
    assert not procs & {"orted", "mpirun", "mpiexec", "prted"}, procs
    tmp = set((tmp_path / "tmpls.txt").read_text(encoding="utf-8").split())
    assert any(n.startswith("ompi.") for n in tmp), tmp
    assert not any(n.startswith("pmix") for n in tmp), tmp


@pytest.mark.sandbox
def test_charon_single_thread(image, tmp_path):
    """Kokkos Serial and OMP_NUM_THREADS=1: the solve adds no compute thread.

    The test asserts that the most threads at any sample is exactly two, so a new compute
    thread fails it.

    The process has two threads: the main thread, which runs the solve, and OpenMPI's
    progress thread, which a singleton starts in MPI_Init (Experiment A3 measured 2 threads,
    the same with or without the OpenMPI settings).
    """
    out = _solve(tmp_path, LOCA, "moscap.dd.equ.exo", image, args="--current", sample=True)
    assert "Charon run completed." in out
    counts = {int(ln.split()[1]) for ln in (tmp_path / "threads.txt").read_text().splitlines()}
    # a sample taken before MPI_Init sees 1 thread; the most at any sample is exactly 2
    assert counts and max(counts) == 2, counts


@pytest.mark.sandbox
def test_charon_two_runs_byte_identical(image, tmp_path):
    """Two runs of the upstream loca_moscap_cv 1 Hz deck give the same currents and fields.

    The currents file is compared byte for byte. The output Exodus file is not: its QA record
    holds the run's date, time and host name (Experiment A3), so it is compared through
    ``exodiff -absolute -tolerance 0`` (every time step and every global, nodal and element
    variable, with zero difference allowed). The backend never commits the Exodus file.
    """
    for d in ("a", "b"):
        (tmp_path / d).mkdir()
        out = _solve(tmp_path / d, LOCA, "moscap.dd.equ.exo", image, args="--current")
        assert "Charon run completed." in out
    a = (tmp_path / "a" / "currents-loca.dat").read_bytes()
    b = (tmp_path / "b" / "currents-loca.dat").read_bytes()
    assert a and a == b
    exo = LOCA.removesuffix(".inp") + ".exo"
    out = _run(
        f"{{ exodiff -absolute -tolerance 0 a/{exo} b/{exo}; echo exodiff-exit=$?; }}",
        tmp_path,
        image,
    )
    assert "exodiff: Files are the same" in out, out
    assert "exodiff-exit=0" in out, out
    assert re.search(r"Times = 2\b", out), out
