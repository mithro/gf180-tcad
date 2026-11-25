# SPDX-License-Identifier: Apache-2.0
"""The committed Charon experiment records (results/charon-experiments, written by
experiments/charon-backend/record.py): one set of pins, scripts that are the committed ones at the
pinned commit, DEVSIM values that are the committed DEVSIM results, and internal consistency."""

import hashlib
import json
import subprocess

import numpy as np
import pytest

from gf180tcad import io
from gf180tcad.sandbox import REPO_ROOT

ROOT = REPO_ROOT / "results" / "charon-experiments"
RECORDS = ("cv", "hard-range", "probes", "harmonic-balance")
PIN_KEYS = ("commit", "image", "gplugins_commit", "scripts_sha256")


def _record(name: str) -> dict:
    return json.loads((ROOT / f"{name}.json").read_text("utf-8"))


def test_records_share_one_set_of_pins():
    pins = [{k: _record(n)[k] for k in PIN_KEYS} for n in RECORDS]
    assert all(p == pins[0] for p in pins)
    assert _record("cv")["image"] == (REPO_ROOT / "docker" / "CHARON_IMAGE").read_text().strip()


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, check=True, capture_output=True).stdout


def test_pinned_scripts_are_the_committed_ones():
    """Each script's sha256 in the pins is that of the script at the pinned commit, and the
    experiment directory has not changed a script since (README edits are allowed)."""
    pins = _record("cv")
    _git("cat-file", "-e", pins["commit"])  # needs full history (CI checks out with depth 0)
    for name, digest in pins["scripts_sha256"].items():
        at_pin = _git("show", f"{pins['commit']}:experiments/charon-backend/{name}")
        assert hashlib.sha256(at_pin).hexdigest() == digest, name
        now = (REPO_ROOT / "experiments" / "charon-backend" / name).read_bytes()
        assert hashlib.sha256(now).hexdigest() == digest, f"{name} changed since the run"


def test_devsim_values_are_the_committed_results():
    for name, run in _record("cv")["runs"].items():
        cols, _meta = io.read_csv(
            REPO_ROOT / "results/tcad/moscap1d" / run["device"] / run["params"] / "per_area.csv"
        )
        vg = list(cols["vg"])
        idx = [vg.index(v) for v in run["vg"]]
        assert np.array_equal(np.asarray(cols["c_per_area"])[idx], run["c_devsim"]), name


def test_cv_records_are_consistent():
    for name, run in _record("cv")["runs"].items():
        c, dv = np.asarray(run["c_ff_um2"]), np.asarray(run["c_devsim"])
        assert len(c) == len(dv) == len(run["vg"]) == run["n"], name
        assert np.allclose(run["rel_vs_devsim"], (c - dv) / dv, rtol=1e-12, atol=0), name
        assert run["max_abs_rel_vs_devsim"] == pytest.approx(np.max(np.abs((c - dv) / dv)))
        for side in "AB":
            assert run[f"extra_states_{side}"] <= 1, name
            assert len(run[f"iterations_{side}"]) >= len(run["vg"]), name


def test_reference_runs_agree_with_devsim_within_the_tolerance():
    """The page's headline: the short-lifetime reference runs agree with DEVSIM within 1 %."""
    from gf180tcad.tcad import meshconv

    runs = _record("cv")["runs"]
    for name in ("cv-nfet-tau15-1e-10", "cv-pfet-tau15-1e-10"):
        assert runs[name]["n"] == len(runs[name]["vg"])
        assert runs[name]["max_abs_rel_vs_devsim"] < meshconv.CRITERION, name


def test_hard_range_reached_biases():
    variants = _record("hard-range")["variants"]
    for name, v in variants.items():
        if v["sweep_converged"]:
            assert v["last_converged_v"] == v["end_v"], name
        elif v["equilibrium_converged"]:
            assert v["last_converged_v"] < v["end_v"] and v["failed_at"], name
        else:
            assert v["last_converged_v"] is None, name
