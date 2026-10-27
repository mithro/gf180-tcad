# SPDX-License-Identifier: Apache-2.0
"""The Makefile's reproduce targets call the real command lines, for the committed results.

``make -n`` prints every command without running it; each one is parsed with the argument
parser of the command line it calls, so a flag the CLI does not have fails here. The jobs are
compared with the committed trees under results/tcad.
"""

import importlib.machinery
import importlib.util
import itertools
import json
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from gf180tcad import manifest, outcache, reference
from gf180tcad.calibrate.__main__ import _parser as calibrate_parser
from gf180tcad.tcad import process
from gf180tcad.tcad.__main__ import _parser as tcad_parser
from gf180tcad.tcad.moscap2d import AC_INFEASIBLE

REPO = Path(__file__).resolve().parents[1]
TCAD = REPO / "results" / "tcad"
MARK = "PYTHON-MARK"

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")


def _tool_parser():
    path = REPO / "tools" / "crosscheck-tcad-run"
    loader = importlib.machinery.SourceFileLoader("crosscheck_tcad_run_mk", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod.parser()


def _commands(target: str) -> list[tuple[str, object]]:
    """``(module, parsed args)`` of every command ``make -n target`` prints, in order."""
    r = subprocess.run(
        ["make", "--no-print-directory", "-n", target, f"PYTHON={MARK}"],
        cwd=REPO, check=True, capture_output=True, text=True,
    )  # fmt: skip
    lines = r.stdout.replace("\\\n", " ").splitlines()
    out = []
    for line in lines:
        argv = shlex.split(line)
        if argv[0] == "make":  # the $(MAKE) sub-target lines; their commands follow
            continue
        assert argv[0] == MARK, f"{target}: a command not run with $(PYTHON): {line!r}"
        if argv[1] == "tools/output-cache":
            out.append(("tools/output-cache", outcache._parser().parse_args(argv[2:])))
            continue
        if argv[1] == "tools/crosscheck-tcad-run":
            out.append(("tools/crosscheck-tcad-run", _tool_parser().parse_args(argv[2:])))
            continue
        assert argv[1] == "-m", line
        module, rest = argv[2], argv[3:]
        if module == "gf180tcad":
            out.append((module, reference.parse_args(rest)))
        elif module == "gf180tcad.tcad":
            out.append((module, tcad_parser().parse_args(rest)))
        elif module == "gf180tcad.calibrate":
            out.append((module, calibrate_parser().parse_args(rest)))
        elif module == "gf180tcad.manifest":
            out.append((module, manifest._parser().parse_args(rest)))
        else:
            raise AssertionError(f"{target}: unknown command line {line!r}")
    return out


@pytest.fixture(scope="module")
def reproduce():
    return _commands("reproduce")


def _index(cmds, pred) -> list[int]:
    return [i for i, (m, a) in enumerate(cmds) if pred(m, a)]


def _moscap(dim, params):
    return lambda m, a: (
        m == "gf180tcad.tcad" and a.command == "moscap" and a.dim == dim and a.params == params
    )


def test_reproduce_runs_in_dependency_order(reproduce):
    spice = _index(reproduce, lambda m, a: m == "gf180tcad")
    meshconv = _index(reproduce, lambda m, a: m == "gf180tcad.tcad" and a.command == "meshconv")
    start = _index(reproduce, lambda m, a: _moscap(1, "start")(m, a) or _moscap(2, "start")(m, a))
    cal = _index(reproduce, lambda m, a: m == "gf180tcad.calibrate" and a.command == "run")
    calibrated = _index(
        reproduce,
        lambda m, a: _moscap(1, "calibrated")(m, a) or _moscap(2, "calibrated")(m, a),
    )
    validate = _index(
        reproduce, lambda m, a: m == "gf180tcad.calibrate" and a.command == "validate"
    )
    verify = _index(reproduce, lambda m, a: m == "gf180tcad.manifest")
    groups = [spice, meshconv, start, cal, calibrated, validate, verify]
    assert all(groups), groups
    assert sorted(i for g in groups for i in g) == list(range(len(reproduce)))
    for a, b in itertools.pairwise(groups):
        assert max(a) < min(b), groups
    ((_, a),) = (reproduce[i] for i in verify)
    assert (a.command, a.root) == ("verify", Path("results"))


def test_reproduce_spice_is_the_full_reference(reproduce):
    ((_, a),) = [c for c in reproduce if c[0] == "gf180tcad"]
    assert a.out == Path("results/spice")
    plan = reference.plan_jobs(a.engines, a.corners, a.devices, a.geometries)
    assert sorted(j.relpath.as_posix() for j in plan) == sorted(manifest.all_jobs())


def test_reproduce_meshconv_both_devices_and_dims(reproduce):
    runs = [a for m, a in reproduce if m == "gf180tcad.tcad" and a.command == "meshconv"]
    assert sorted((a.device, a.dim) for a in runs) == [
        (d, dim) for d in process.DEVICES for dim in (1, 2)
    ]
    for a in runs:
        assert a.out == Path("results/tcad/meshconv") and a.image is None and a.mem is None
        assert a.jobs == (1 if a.dim == 2 else None)  # 2D: one 16 GiB job at a time
        assert (TCAD / "meshconv" / f"moscap{a.dim}d" / a.device / "selected.json").is_file()


def test_reproduce_1d_moscap_jobs_are_the_committed_ones(reproduce):
    runs = [a for m, a in reproduce if m == "gf180tcad.tcad" and a.command == "moscap"]
    one_d = sorted((a.device, a.params) for a in runs if a.dim == 1)
    committed = sorted(
        (p.parent.name, p.name) for p in (TCAD / "moscap1d").glob("*/*") if p.is_dir()
    )
    assert (
        one_d
        == committed
        == sorted((d, p) for d in process.DEVICES for p in ("start", "calibrated"))
    )
    for a in runs:
        assert a.out == Path(f"results/tcad/moscap{a.dim}d")
        assert a.image is None and a.mem is None


def test_reproduce_2d_moscap_jobs_are_the_committed_cells(reproduce):
    runs = [
        a for m, a in reproduce if m == "gf180tcad.tcad" and a.command == "moscap" and a.dim == 2
    ]
    # every committed 2D cell, start and calibrated (tcad-start, tcad-calibrated), and no other
    cells = {}
    for a in runs:
        cells.setdefault((a.device, a.params, a.geometry), []).append(a)
    committed = sorted(
        (p.parents[1].name, p.parent.name, p.name)
        for p in (TCAD / "moscap2d").glob("*/*/*")
        if p.is_dir()
    )
    assert sorted(cells) == committed
    assert {p for _, p, _ in committed} <= {"start", "calibrated"}
    assert {(d, p) for d, p, _ in committed} >= {(d, "start") for d in process.DEVICES}
    for (device, params, gid), steps in cells.items():
        meta = json.loads((TCAD / "moscap2d" / device / params / gid / "cv.meta.json").read_bytes())
        # older metas (Task 11, AC computed) have no "ac" entry
        if meta.get("ac") == AC_INFEASIBLE:
            # QS alone, then the job files from it, on one scratch directory
            assert [s.method for s in steps] == ["qs", "combine-qs"]
            assert steps[0].resume == steps[1].resume is not None
        else:
            assert [(s.method, s.resume) for s in steps] == [("both", None)]


def test_reproduce_calibration_and_validation(reproduce):
    cal = [a for m, a in reproduce if m == "gf180tcad.calibrate"]
    assert sorted((a.command, a.device, a.out.as_posix()) for a in cal) == sorted(
        [("run", d, "results/tcad/calibration") for d in process.DEVICES]
        + [("validate", d, "results/tcad/validation") for d in process.DEVICES]
    )


def test_reproduce_quick_is_the_crosschecked_subset():
    cmds = _commands("reproduce-quick")
    assert [m for m, _ in cmds] == ["tools/crosscheck-tcad-run", "gf180tcad.manifest"]
    run, verify = cmds[0][1], cmds[1][1]
    subset = Path("tests/crosscheck_tcad_subset.txt")
    assert run.subset == subset and run.clean and not run.images
    assert not run.out.resolve().is_relative_to(REPO / "results")
    assert (verify.command, verify.root, verify.kind, verify.prefix, verify.subset) == (
        "verify-subset",
        run.out,
        "tcad",
        "tcad/",
        subset,
    )
    assert verify.against == Path("results/MANIFEST.sha256")


def test_cache_targets():
    ((m, st),) = _commands("cache-status")
    assert m == "tools/output-cache" and st.command == "status"
    assert st.cache is None and st.results == Path("results")  # the configured HTTPS URL
    ((m, pu),) = _commands("cache-push")
    assert m == "tools/output-cache" and pu.command == "push"
    assert (pu.cache, pu.results, pu.publish, pu.dry_run) == (
        Path("tmp/output-cache"), Path("results"), True, False,
    )  # fmt: skip
