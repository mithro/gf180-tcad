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


def _shown(text: str, value: float) -> bool:
    """Whether ``text`` (a number as the page prints it) is ``value`` at the digits shown."""
    mantissa = text.split("e")[0].replace(".", "").lstrip("0")
    return float(text) == float(f"{value:.{max(len(mantissa), 1) - 1}e}")


def test_page_numbers_are_the_records():
    """The Charon page and the status pages print their numbers by substitution
    (``lim_charon_*``); each is recomputed here from the records, and no hand-typed copy of the
    headline numbers is left on the pages."""
    from gf180tcad import limitations_figures as lf

    subs = {k: v for k, v in lf.substitutions().items() if k.startswith("lim_charon_")}
    runs = _record("cv")["runs"]
    for dev, name in (("nfet", "cv-nfet-tau15-1e-10"), ("pfet", "cv-pfet-tau15-1e-10")):
        c, dv = np.asarray(runs[name]["c_ff_um2"]), np.asarray(runs[name]["c_devsim"])
        assert _shown(subs[f"lim_charon_{dev}_devsim"], np.max(np.abs(c / dv - 1))), dev
    assert subs["lim_charon_points"] == str(len(runs["cv-nfet-tau15-1e-10"]["vg"]))
    ref = _record("hard-range")["variants"]["ref_1e-10"]
    assert float(subs["lim_charon_fail_v"]) == float(ref["failed_at"][0])
    assert _shown(subs["lim_charon_ref_fnorm"], ref["failed_fnorm"])
    assert float(subs["lim_charon_ref_wrms"]) > 1
    b6 = max(runs[n][f"{k}_vs_gate_{s}"] for n in ("cv-nfet-tau15-1e-10", "cv-pfet-tau15-1e-10")
             for k in ("poly", "body") for s in "AB")  # fmt: skip
    assert _shown(subs["lim_charon_b6"], b6)
    tri3 = _record("probes")["tri3"]
    assert _shown(subs["lim_charon_tri3_strip"], tri3["strip_max_rel_c_tri3_vs_quad4"])
    assert _shown(subs["lim_charon_tri3_2d"], abs(tri3["rel_vs_devsim_1d"]))
    pages = {p: (REPO_ROOT / "docs" / p).read_text("utf-8") for p in
             ("limitations/charon.md", "limitations/index.md", "limitations/status.md",
              "roadmap.md")}  # fmt: skip
    for key in subs:
        assert f"{{{{ {key} }}}}" in pages["limitations/charon.md"], key
    for page in ("limitations/index.md", "limitations/status.md", "roadmap.md"):
        for dev in ("nfet", "pfet"):
            assert f"{{{{ lim_charon_{dev}_devsim }}}}" in pages[page], (page, dev)
    for old in ("3.0e-5", "5.4e-5", "1.1e-9", "8.2e-13", "2.6e-4", "2.1e-9", "1.3e-9"):
        assert old not in pages["limitations/charon.md"], old


def test_step_studies_are_recorded():
    """The plan's step and tolerance studies ran as committed steps and recorded their outcome."""
    studies = _record("hard-range")["step_studies"]
    assert set(studies) == {
        "study-nfet-tau15-secant-50mV",
        "study-nfet-default-1e-11",
        "study-pfet-start-1e-10",
        "study-pfet-start-1e-10-5mV",
        "study-pfet-start-1e-10-tau16",
        "study-pfet-start-1e-11",
        "study-pfet-start-rel-1e-9-abs-1e-12",
        "study-pfet-start-rel-1e-10-abs-1e-11",
    }
    for name, s in studies.items():
        assert (s["b2_exit"] == 0) == (s["failed"] is None), name


def test_backend_tolerance_is_b7_equivalent():
    """B7 for the backend's WRMS 1e-9/1e-11: on both devices and both parameter sets, wherever
    1e-10/1e-12 converges, C moves by less than 1e-8 relative; 1e-9 covers every grid, and the
    pfet start reference stops where the page says."""
    runs = _record("cv")["runs"]
    pairs = {
        ("cv-nfet-tau15-1e-9", "cv-nfet-tau15-1e-10"),
        ("cv-pfet-tau15-1e-9", "cv-pfet-tau15-1e-10"),
        ("cv-nfet-start-tau15-1e-9", "cv-nfet-start-tau15-1e-10"),
        ("cv-pfet-start-tau15-1e-9", "cv-pfet-start-tau15-1e-10-above-0.6"),
    }
    for name, ref in pairs:
        r, b = runs[name], runs[ref]
        assert r["settings"]["CX_REL"] == "1e-9" and b["settings"]["CX_REL"] == "1e-10"
        assert r["n"] == len(r["vg"]) and len(r["vg"]) == len(runs["cv-nfet-tau15-1e-10"]["vg"])
        common = [v for v in r["vg"] if v in b["vg"]]
        assert len(common) == b["n"], name
        rel = max(abs(r["c_ff_um2"][r["vg"].index(v)] / b["c_ff_um2"][b["vg"].index(v)] - 1)
                  for v in common)  # fmt: skip
        assert rel < 1e-8, (name, rel)
    studies = _record("hard-range")["step_studies"]
    stall = studies["study-pfet-start-1e-10"]["failed"]
    assert float(stall["failed_at"][0]) < min(runs["cv-pfet-start-tau15-1e-10-above-0.6"]["vg"])
    assert stall["newton_limit"] == [[50, 50]] and stall["final"][-1][1] > 1
    for name in ("study-pfet-start-rel-1e-9-abs-1e-12", "study-pfet-start-rel-1e-10-abs-1e-11"):
        assert studies[name]["b2_exit"] == 0, name
