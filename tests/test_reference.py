# SPDX-License-Identifier: Apache-2.0
"""SPICE golden-reference generation (``python -m gf180tcad spice-reference``).

Unit tests use a fake job runner and fake simulators, so they need no Docker; the one sandbox
test runs a real ngspice job twice and compares every byte.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from gf180tcad import io, reference, sandbox
from gf180tcad.devices import CORNERS, DEVICES, SWEEPS, geometry_id
from gf180tcad.reference import AdmissionError, Job

GIB = 1 << 30
NFET_LMIN = Job("ngspice", "typical", "nfet_05v0", "w10p0_l0p60")


# --- admission control ---------------------------------------------------------------------


@pytest.mark.parametrize("n,mem", [(1, "4g"), (8, "4g"), (32, "4g"), (8, "16g"), (1, "128g")])
def test_admission_within_budget(n, mem):
    reference.check_admission(n, mem)


@pytest.mark.parametrize("n,mem", [(33, "4g"), (9, "16g"), (1, "129g"), (300, "512m")])
def test_admission_over_budget_rejected(n, mem):
    with pytest.raises(AdmissionError, match="128 GiB"):
        reference.check_admission(n, mem)


@pytest.mark.parametrize("n", [0, -1])
def test_admission_needs_a_positive_job_count(n):
    with pytest.raises(AdmissionError):
        reference.check_admission(n, "4g")


@pytest.mark.parametrize(
    "text,nbytes", [("4g", 4 * GIB), ("16G", 16 * GIB), ("512m", 512 << 20), ("1024k", 1 << 20)]
)
def test_parse_mem(text, nbytes):
    assert reference.parse_mem(text) == nbytes


@pytest.mark.parametrize("text", ["", "4", "4gb", "-1g", "1.5g", "g"])
def test_parse_mem_rejects(text):
    with pytest.raises(ValueError):
        reference.parse_mem(text)


def test_default_job_memory_is_the_engine_limit():
    from gf180tcad.spice import ngspice, xyce

    assert reference.job_mem(("ngspice",)) == ngspice.MEM == "4g"
    assert reference.job_mem(("xyce",)) == xyce.MEM == "4g"
    assert reference.job_mem(("ngspice", "xyce")) == "4g"


# --- job plan ------------------------------------------------------------------------------


def test_engine_sweeps():
    names = [s.name for s in SWEEPS]
    assert reference.engine_sweeps("ngspice") == tuple(names)
    assert reference.engine_sweeps("xyce") == tuple(n for n in names if n != "cv")


def test_full_plan():
    jobs = reference.plan_jobs(("ngspice", "xyce"), CORNERS, tuple(DEVICES))
    ngeo = sum(len(d.geometries) for d in DEVICES.values())
    assert len(jobs) == 2 * len(CORNERS) * ngeo == 120
    assert len(set(jobs)) == len(jobs)
    assert jobs == sorted(jobs)
    assert NFET_LMIN in jobs


def test_subset_plan():
    jobs = reference.plan_jobs(("ngspice",), ("typical",), ("nfet_05v0",))
    assert [j.geometry for j in jobs] == sorted(geometry_id(g) for g in DEVICES["nfet_05v0"].geometries)
    assert {(j.engine, j.corner, j.device) for j in jobs} == {("ngspice", "typical", "nfet_05v0")}


def test_job_layout_and_expected_files():
    assert NFET_LMIN.relpath == Path("ngspice/typical/nfet_05v0/w10p0_l0p60")
    assert reference.expected_files("ngspice") == (
        "cv.csv", "idvd.csv", "idvg_lin.csv", "idvg_sat.csv", "ioff.csv", "metrics.json",
    )  # fmt: skip
    assert "cv.csv" not in reference.expected_files("xyce")


def test_unknown_geometry_rejected():
    with pytest.raises(ValueError, match="geometry"):
        reference.geometry_of("nfet_05v0", "w10p0_l0p50")  # pfet's Lmin, not an nfet geometry


# --- CSV meta --------------------------------------------------------------------------------


def test_csv_meta_is_only_deterministic_fields():
    sw = {s.name: s for s in SWEEPS}
    g = reference.geometry_of("nfet_05v0", "w10p0_l0p60")
    meta = reference.csv_meta(NFET_LMIN, g, sw["idvg_lin"], 25.0)
    assert meta == {
        "corner": "typical",
        "device": "nfet_05v0",
        "engine": "ngspice",
        "geometry_id": "w10p0_l0p60",
        "l_um": "0.6",
        "sweep": "idvg_lin",
        "temp_c": "25.0",
        "units": "vd=V vg=V vb=V id=A ig=A ib=A",
        "w_um": "10.0",
    }
    cv = reference.csv_meta(NFET_LMIN, g, sw["cv"], 25.0)
    assert cv["units"] == "vg=V cgg=F" and cv["sweep"] == "cv"


# --- provenance ------------------------------------------------------------------------------


def _fake_repo(root: Path) -> Path:
    pkg = root / "src" / "gf180tcad"
    (pkg / "spice").mkdir(parents=True)
    (pkg / "a.py").write_text("A = 1\n")
    (pkg / "spice" / "b.py").write_text("B = 2\n")
    (pkg / "notes.txt").write_text("not code\n")
    (pkg / "__pycache__").mkdir()
    (pkg / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\0junk")
    (root / "docker" / "base").mkdir(parents=True)
    (root / "docker" / "base" / "versions.json").write_text('{"ngspice": "47", "python": "3"}\n')
    (root / "docker" / "IMAGE").write_text("ghcr.io/x/y@sha256:" + "a" * 64 + "\n")
    return root


def test_generator_sha256_stable_and_sensitive(tmp_path):
    repo = _fake_repo(tmp_path / "r")
    h = reference.generator_sha256(repo)
    assert len(h) == 64 and h == reference.generator_sha256(repo)
    pkg = repo / "src" / "gf180tcad"
    (pkg / "notes.txt").write_text("changed, but not a .py file\n")
    (pkg / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"other")
    assert reference.generator_sha256(repo) == h
    (pkg / "spice" / "b.py").write_text("B = 3\n")
    h2 = reference.generator_sha256(repo)
    assert h2 != h
    (pkg / "spice" / "b.py").rename(pkg / "c.py")  # same bytes, other path
    assert reference.generator_sha256(repo) not in (h, h2)


def test_generator_sha256_independent_of_location_and_mtime(tmp_path):
    a = _fake_repo(tmp_path / "a")
    b = _fake_repo(tmp_path / "elsewhere" / "b")
    os.utime(b / "src" / "gf180tcad" / "a.py", (0, 0))
    assert reference.generator_sha256(a) == reference.generator_sha256(b)


def test_generator_sha256_of_this_repo_covers_the_package():
    assert reference.generator_sha256(sandbox.REPO_ROOT) == reference.generator_sha256()


def test_provenance_contents(tmp_path):
    repo = _fake_repo(tmp_path / "r")
    prov = reference.provenance(repo)
    assert prov == {
        "generator_sha256": reference.generator_sha256(repo),
        "image": "ghcr.io/x/y@sha256:" + "a" * 64,
        "versions": {"ngspice": "47", "python": "3"},
    }
    text = json.dumps(prov).lower()
    assert "commit" not in text and "date" not in text


# --- staging, failures and the swap into place -------------------------------------------------


def _fake_runner(fail=(), omit=None):
    """A job runner that writes deterministic files; jobs in ``fail`` raise."""

    def run(job, scratch, mem):
        assert mem == "4g"
        assert not Path(scratch).resolve().is_relative_to(sandbox.REPO_ROOT)
        if job in fail:
            (Path(scratch) / "debug.log").write_text("boom\n")
            raise RuntimeError(f"simulated failure of {job.relpath}")
        for name in reference.expected_files(job.engine):
            if name != omit:
                (Path(scratch) / name).write_text(f"{job.relpath}/{name}\n")
        (Path(scratch) / "work").mkdir()
        (Path(scratch) / "work" / "ngspice.log").write_text("not published\n")

    return run


def _tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


def _gen(tmp_path, jobs, runner, out, **kw):
    scratch = tmp_path / "scratch"
    scratch.mkdir(exist_ok=True)
    return reference.generate(
        jobs,
        out,
        jobs_n=2,
        mem="4g",
        runner=runner,
        scratch_root=scratch,
        log=lambda *a: None,
        **kw,
    )


JOBS = reference.plan_jobs(("ngspice", "xyce"), ("typical",), ("nfet_05v0",))


def test_success_writes_only_published_files(tmp_path):
    out = tmp_path / "results" / "spice"
    failures = _gen(tmp_path, JOBS, _fake_runner(), out)
    assert failures == []
    tree = _tree(out)
    expected = {"provenance.json"} | {
        f"{j.relpath.as_posix()}/{n}" for j in JOBS for n in reference.expected_files(j.engine)
    }
    assert set(tree) == expected
    assert json.loads(tree["provenance.json"]) == reference.provenance()
    # no staging/old dirs left next to the output, scratch dirs of good jobs deleted
    assert sorted(p.name for p in out.parent.iterdir()) == ["spice"]
    assert list((tmp_path / "scratch").rglob("*.csv")) == []


def test_success_replaces_an_existing_tree(tmp_path):
    out = tmp_path / "spice"
    out.mkdir()
    (out / "stale.csv").write_text("old\n")
    assert _gen(tmp_path, JOBS[:1], _fake_runner(), out) == []
    assert "stale.csv" not in _tree(out)


@pytest.mark.parametrize("existing", [False, True])
def test_failure_leaves_no_partial_tree(tmp_path, existing):
    out = tmp_path / "results" / "spice"
    if existing:
        out.mkdir(parents=True)
        (out / "keep.csv").write_text("previous good result\n")
    before = _tree(out) if existing else None
    bad = JOBS[1]
    failures = _gen(tmp_path, JOBS, _fake_runner(fail={bad}), out)
    assert [f.job for f in failures] == [bad]
    assert "simulated failure" in failures[0].error
    # the failed job's scratch dir is kept, with what it wrote, and named in the failure
    assert (failures[0].scratch / "debug.log").read_text() == "boom\n"
    if existing:
        assert _tree(out) == before
    else:
        assert not out.exists()
    assert sorted(p.name for p in out.parent.iterdir()) == (["spice"] if existing else [])


def test_missing_output_file_is_a_failure(tmp_path):
    out = tmp_path / "spice"
    failures = _gen(tmp_path, JOBS[:1], _fake_runner(omit="metrics.json"), out)
    assert len(failures) == 1 and "metrics.json" in failures[0].error
    assert not out.exists()


def test_progress_lines(tmp_path):
    lines = []
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    reference.generate(
        JOBS, tmp_path / "o", jobs_n=1, mem="4g", runner=_fake_runner(), scratch_root=scratch,
        log=lines.append,
    )  # fmt: skip
    prog = [ln for ln in lines if ln.startswith("[")]
    assert len(prog) == len(JOBS)
    assert prog[-1].startswith(f"[{len(JOBS)}/{len(JOBS)}]")
    assert all(" ok " in ln and "jobs/min" in ln and "ETA" in ln for ln in prog)


def test_progress_line_format():
    line = reference.progress_line(3, 12, 30.0, NFET_LMIN, "ok", 9.5, now=0.0)
    assert line.startswith("[3/12] ok ngspice/typical/nfet_05v0/w10p0_l0p60 9.5s")
    at = time.strftime("%H:%M:%S", time.localtime(90.0))
    assert "6.0 jobs/min" in line and "ETA 90s" in line and f"(at {at})" in line


# --- the in-image job ------------------------------------------------------------------------


def _fake_simulate(engine):
    def sim(device, g, sweep, corner, temp_c, pdk, out_dir):
        assert sandbox.in_sandbox() and Path(out_dir).is_dir() and not any(Path(out_dir).iterdir())
        assert sweep.name in reference.engine_sweeps(engine)
        if sweep.kind == "cv":
            vg = device.polarity * np.array(sweep.vgs)
            return {"vg": vg, "cgg": 1e-13 + 0 * vg}
        from gf180tcad.spice.netlist import bias_plan

        grid = bias_plan(device, sweep).grid()
        n = len(grid["vd"])
        return {**grid, "id": np.linspace(1e-12, 1e-3, n), "ig": np.zeros(n), "ib": np.zeros(n)}

    return sim


@pytest.mark.parametrize("engine", ["ngspice", "xyce"])
def test_spice_job_writes_csvs_and_metrics(monkeypatch, tmp_path, engine):
    monkeypatch.setenv(sandbox.IN_SANDBOX_ENV, "1")
    calls = []
    monkeypatch.setattr(reference, "_image_pdk", lambda: calls.append("checked") or "PDK")
    monkeypatch.setattr(reference, "simulate", _fake_simulate("ngspice"))
    monkeypatch.setattr(reference, "simulate_xyce", _fake_simulate("xyce"))
    monkeypatch.setattr(reference.metrics, "extract_all", lambda d, g, data: {"k": float(len(data))})
    job = Job(engine, "typical", "nfet_05v0", "w10p0_l0p60")
    reference.run_job(job, tmp_path)
    assert calls == ["checked"]
    files = sorted(p.name for p in tmp_path.iterdir() if p.is_file())
    assert tuple(files) == reference.expected_files(engine)
    cols, meta = io.read_csv(tmp_path / "idvg_lin.csv")
    assert list(cols) == ["vd", "vg", "vb", "id", "ig", "ib"] and meta["engine"] == engine
    m = json.loads((tmp_path / "metrics.json").read_text())
    assert m["metrics"] == {"k": float(len(reference.engine_sweeps(engine)))}
    assert {k: m[k] for k in m if k != "metrics"} == {
        "corner": "typical",
        "device": "nfet_05v0",
        "engine": engine,
        "geometry_id": "w10p0_l0p60",
        "l_um": 0.6,
        "temp_c": 25.0,
        "w_um": 10.0,
    }


def test_spice_job_refuses_to_run_outside_the_sandbox(monkeypatch, tmp_path):
    monkeypatch.delenv(sandbox.IN_SANDBOX_ENV, raising=False)
    with pytest.raises(RuntimeError, match="inside the sandbox"):
        reference.run_job(NFET_LMIN, tmp_path)


# --- CLI ---------------------------------------------------------------------------------------


def test_cli_defaults():
    a = reference.parse_args(["spice-reference", "--out", "results/spice"])
    assert a.engines == ("ngspice", "xyce")
    assert a.corners == CORNERS and a.devices == tuple(DEVICES)
    assert a.jobs == 8 and a.out == Path("results/spice")


def test_cli_subset_and_repeats():
    a = reference.parse_args(
        ["spice-reference", "--engine", "xyce", "--corner", "ss", "--corner", "ff",
         "--device", "pfet_05v0", "--jobs", "4", "--out", "o"]
    )  # fmt: skip
    assert a.engines == ("xyce",) and a.corners == ("ff", "ss") and a.devices == ("pfet_05v0",)
    assert a.jobs == 4


@pytest.mark.parametrize(
    "argv",
    [
        ["spice-reference"],  # --out is required
        ["spice-reference", "--out", "o", "--engine", "spectre"],
        ["spice-reference", "--out", "o", "--corner", "tt"],
        ["spice-reference", "--out", "o", "--device", "nfet_03v3"],
    ],
)
def test_cli_rejects_bad_arguments(argv):
    with pytest.raises(SystemExit) as exc:
        reference.parse_args(argv)
    assert exc.value.code == 2


def test_cli_rejects_jobs_over_budget(capsys):
    assert reference.main(["spice-reference", "--out", "o", "--jobs", "33"]) == 2
    err = capsys.readouterr().err
    assert "33" in err and "128 GiB" in err


def test_cli_spice_job_arguments():
    a = reference.parse_args(
        ["spice-job", "--engine", "ngspice", "--corner", "typical", "--device", "nfet_05v0",
         "--geometry", "w10p0_l0p60", "--out", "/work/out"]
    )  # fmt: skip
    assert a.job == NFET_LMIN and a.out == Path("/work/out")


def test_module_entry_point():
    res = subprocess.run(
        [sys.executable, "-m", "gf180tcad", "spice-reference", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr
    assert "--engine" in res.stdout and "--jobs" in res.stdout


# --- sandbox: real ngspice, byte-identical twice ------------------------------------------------


@pytest.mark.sandbox
def test_reference_subset_hash_stable(tmp_path):
    trees = []
    for name in ("a", "b"):
        scratch = tmp_path / f"scratch-{name}"
        scratch.mkdir()
        out = tmp_path / name / "spice"
        failures = reference.generate(
            [NFET_LMIN], out, jobs_n=1, mem="4g", scratch_root=scratch, log=lambda *a: None
        )
        assert failures == []
        trees.append(_tree(out))
    a, b = trees
    rel = NFET_LMIN.relpath.as_posix()
    assert set(a) == {"provenance.json"} | {f"{rel}/{n}" for n in reference.expected_files("ngspice")}
    assert a == b
    m = json.loads(a[f"{rel}/metrics.json"])["metrics"]
    assert 0.5 < m["vt_lin_cc"] < 0.9 and 300 < m["idsat_ua_per_um"] < 700
    assert m["cgg_inv_ff"] > 0
    for blob in a.values():
        text = blob.decode("utf-8")
        assert str(tmp_path) not in text and "/work/" not in text and "\r" not in text
