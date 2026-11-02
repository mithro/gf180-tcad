# SPDX-License-Identifier: Apache-2.0
"""The charon-libs image (docker/CHARON_LIBS_IMAGE): Charon 2.2.0 and Trilinos built from source.

The tests without a mark read only committed files. The sandbox-marked tests run inside the
pinned image through ``sandbox.run(image=...)`` (``pytest -m sandbox``), under exactly the
conditions of tools/sandbox-run: no network, read-only root filesystem with a tmpfs ``/tmp``,
a pids limit, one process (no ``mpirun``). The upstream test decks they run are the ones the
image installs under /opt/charon/share/gf180tcad/tests (copied from the Charon tarball).
"""

import importlib.util
import json
import re
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
TESTS = "/opt/charon/share/gf180tcad/tests"
# The OpenMPI settings the image sets so that charon_mp.exe runs as a singleton in the sandbox.
OMPI_ENV = {"OMPI_MCA_ess_singleton_isolated": "1"}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"charon_libs_{name}", LIBS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inputs = _load("inputs")


def _image() -> str:
    return PIN.read_text(encoding="utf-8").strip()


def _probe_tests() -> list[str]:
    build = (LIBS / "build-charon.sh").read_text(encoding="utf-8")
    block = re.search(r"^PROBE_TESTS=\((.*?)\)$", build, re.MULTILINE | re.DOTALL).group(1)
    return block.split()


def _run(script: str, tmp_path: Path) -> str:
    res = sandbox.run(["bash", "-euo", "pipefail", "-c", script], out_dir=tmp_path, image=_image())
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
def test_charon_environment(tmp_path):
    out = _run(
        "echo PATH=$PATH; echo OMP=$OMP_NUM_THREADS; command -v charon_mp.exe; "
        "env | grep ^OMPI_MCA_ | sort; charon_mp.exe --version",
        tmp_path,
    )
    assert "PATH=/opt/charon/bin:" in out
    assert "OMP=1" in out
    assert "/opt/charon/bin/charon_mp.exe" in out
    for k, v in OMPI_ENV.items():
        assert f"{k}={v}" in out, k


# While the solve runs, sample the process's thread count, the process list and /tmp every
# 0.2 s (until it is a zombie: `wait` has not reaped it yet).
_SAMPLE = (
    "while [ -e /proc/$pid/status ] && ! grep -q '^State:[[:space:]]*Z' /proc/$pid/status; do "
    "grep '^Threads:' /proc/$pid/status >> threads.txt; ps -eo comm >> procs.txt; "
    "ls -a /tmp >> tmpls.txt; sleep 0.2; done;"
)
LOCA = "moscap.hb.locaOxide.1e0Hz.inp"


def _solve(tmp_path: Path, deck: str, mesh: str, *, args: str = "", sample: bool = False) -> str:
    """Run an upstream deck as one process (no mpirun) in the workdir; return charon's log."""
    return _run(
        f"cp {TESTS}/{deck} {TESTS}/{mesh} . && "
        f"charonInterpreter.py -i {deck} > interp.log && "
        f"{{ charon_mp.exe --i={deck}.xml {args} > charon.log 2>&1 & pid=$!; "
        f"{_SAMPLE if sample else ''} wait $pid; }}; cat charon.log",
        tmp_path,
    )


@pytest.mark.sandbox
def test_charon_runs_the_upstream_pmoscap_nlp(tmp_path):
    out = _solve(tmp_path, "pmoscap.nlp.inp", "pmoscap.exo")
    assert "Charon run completed." in out
    assert (tmp_path / "pmoscap.nlp.exo").stat().st_size > 0


@pytest.mark.sandbox
def test_charon_mpi_singleton_in_the_sandbox(tmp_path):
    """Experiment A3: one rank, no orted, no PMIx shared-memory files, session under /tmp.

    tools/sandbox-run gives no network and a read-only root with only /tmp writable, so a
    write elsewhere would end the run. Without OMPI_MCA_ess_singleton_isolated=1 OpenMPI 4.1
    forks `orted` and writes /tmp/pmix-gds-shmem.* files (Experiment A3, A-2).
    """
    out = _solve(tmp_path, LOCA, "moscap.dd.equ.exo", args="--current", sample=True)
    assert "Charon run completed." in out
    procs = set((tmp_path / "procs.txt").read_text(encoding="utf-8").split())
    assert "charon_mp.exe" in procs
    assert not procs & {"orted", "mpirun", "mpiexec", "prted"}, procs
    tmp = set((tmp_path / "tmpls.txt").read_text(encoding="utf-8").split())
    assert any(n.startswith("ompi.") for n in tmp), tmp
    assert not any(n.startswith("pmix") for n in tmp), tmp


@pytest.mark.sandbox
def test_charon_single_thread(tmp_path):
    """Kokkos Serial and OMP_NUM_THREADS=1: the solve adds no compute thread.

    The process has two threads: the main thread, which runs the solve, and OpenMPI's
    progress thread, which a singleton starts in MPI_Init (Experiment A3 measured 2 threads,
    the same with or without the OpenMPI settings).
    """
    out = _solve(tmp_path, LOCA, "moscap.dd.equ.exo", args="--current", sample=True)
    assert "Charon run completed." in out
    counts = {int(ln.split()[1]) for ln in (tmp_path / "threads.txt").read_text().splitlines()}
    assert counts and max(counts) <= 2, counts


@pytest.mark.sandbox
def test_charon_two_runs_byte_identical(tmp_path):
    """Two runs of the upstream loca_moscap_cv 1 Hz deck give byte-identical currents.

    The output Exodus file is not compared byte for byte: its QA record holds the run's date,
    time and host name (Experiment A3). The backend never commits it.
    """
    for d in ("a", "b"):
        (tmp_path / d).mkdir()
        out = _solve(tmp_path / d, LOCA, "moscap.dd.equ.exo", args="--current")
        assert "Charon run completed." in out
    a = (tmp_path / "a" / "currents-loca.dat").read_bytes()
    b = (tmp_path / "b" / "currents-loca.dat").read_bytes()
    assert a and a == b
