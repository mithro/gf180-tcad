# SPDX-License-Identifier: Apache-2.0
"""The committed Charon experiment records (results/charon-experiments, written by
experiments/charon-backend/record.py): one set of pins, scripts that are the committed ones at the
pinned commit, DEVSIM values that are the committed DEVSIM results, and internal consistency."""

import hashlib
import json
import re
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
    experiment directory has not changed a script since (README edits are allowed). record.py
    only reads the run directories after the run, so the records carry its sha256 apart."""
    pins = _record("cv")
    _git("cat-file", "-e", pins["commit"])  # needs full history (CI checks out with depth 0)
    for name, digest in pins["scripts_sha256"].items():
        at_pin = _git("show", f"{pins['commit']}:experiments/charon-backend/{name}")
        assert hashlib.sha256(at_pin).hexdigest() == digest, name
        now = hashlib.sha256(
            (REPO_ROOT / "experiments" / "charon-backend" / name).read_bytes()
        ).hexdigest()
        if name == "record.py":  # runs after the run, on the host; it records its own sha256
            assert all(_record(n)["record_py_sha256"] == now for n in RECORDS), name
            continue
        assert now == digest, f"{name} changed since the run"


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


def _rel_max(runs, name, ref):
    r, b = runs[name], runs[ref]
    common = [v for v in r["vg"] if v in b["vg"]]
    return max(abs(r["c_ff_um2"][r["vg"].index(v)] / b["c_ff_um2"][b["vg"].index(v)] - 1)
               for v in common)  # fmt: skip


def _num(text: str) -> float:
    return float(text.replace("−", "-"))


def _expected_page_numbers() -> dict:
    """Every ``lim_charon_*`` number recomputed from the records, independently of
    gf180tcad.limitations_figures: ``{key: value}`` (a float compared at the digits the page
    shows, or the exact text)."""
    runs = _record("cv")["runs"]
    hard = _record("hard-range")
    probes = _record("probes")
    hb = _record("harmonic-balance")
    studies = hard["step_studies"]
    ref_n, ref_p = runs["cv-nfet-tau15-1e-10"], runs["cv-pfet-tau15-1e-10"]
    v = hard["variants"]
    plain = [x["last_converged_v"] for x in v.values() if x["equilibrium_converged"]
             and not x["sweep_converged"] and "tau" not in x["settings"]]  # fmt: skip
    tau_stop = {x["last_converged_v"] for x in v.values() if "tau" in x["settings"]
                and x["settings"]["rel"] == 1e-10 and not x["sweep_converged"]}  # fmt: skip
    inv = sorted(float(b) for b in hard["inversion_side"]["direct"])
    pp = max(abs(abs(x) - 1) for run in hb["parallel_plate"]["runs"].values()
             for c, x in run["ratio"].items() if "CosH1" in c)  # fmt: skip
    mg = max(abs(abs(x) - 1) for c, x in hb["metal_gate"]["depletion"]["ratio"].items()
             if c.startswith("gate") and "CosH1" in c and "Disp" in c)  # fmt: skip
    hb1 = probes["harmonic_balance"]["b4_1e+06_0.0001"]
    hb_gate = {s: abs(next(x for c, x in hb1[s]["c_from_columns_over_c_qs"].items()
                           if c.startswith("gate") and "CosH1" in c and "Disp" in c))
               for s in ("accumulation", "depletion")}  # fmt: skip
    b7 = {
        "nfet_calibrated": _rel_max(runs, "cv-nfet-tau15-1e-9", "cv-nfet-tau15-1e-10"),
        "nfet_start": _rel_max(runs, "cv-nfet-start-tau15-1e-9", "cv-nfet-start-tau15-1e-10"),
        "pfet_calibrated": _rel_max(runs, "cv-pfet-tau15-1e-9", "cv-pfet-tau15-1e-10"),
        "pfet_start": max(_rel_max(runs, "cv-pfet-start-tau15-1e-9", r) for r in
                          ("cv-pfet-start-tau15-1e-10-above-0.6",
                           "cv-pfet-start-tau15-1e-10-from-minus-5")),
    }  # fmt: skip
    above = runs["cv-pfet-start-tau15-1e-10-above-0.6"]
    up = runs["cv-pfet-start-tau15-1e-10-from-minus-5"]
    pfet_9 = runs["cv-pfet-start-tau15-1e-9"]
    covered = {x for x in pfet_9["vg"] if x in above["vg"] or x in up["vg"]}
    stall = studies["study-pfet-start-1e-10"]["failed"]
    nlp = hard["nlp"]["points"]
    nlp_ok = [p for p in nlp if p["ok"]]
    (belos,) = [s for s in probes["solvers"].values()
                if isinstance(s, dict) and s.get("failed_at")]  # fmt: skip
    (ramp,) = [studies[n]["failed"] for n in studies if n.startswith("study-pfet-start")
               and studies[n]["failed"] and studies[n]["failed"]["deck"].startswith("ramp")]  # fmt: skip
    (ni,) = {d["ni_cm3"] for d in probes["doping"].values()}
    return {
        "lim_charon_nodes": f"{len(ref_n['x_um'])}",
        "lim_charon_points": f"{len(ref_n['vg'])}",
        "lim_charon_ni": ni,
        "lim_charon_doping_rel": f"{max(d['max_rel_doping'] for d in probes['doping'].values()):g}",
        "lim_charon_ref_tau": ref_n["settings"]["CX_TAU"],
        "lim_charon_nfet_devsim": np.max(
            np.abs(np.asarray(ref_n["c_ff_um2"]) / np.asarray(ref_n["c_devsim"]) - 1)
        ),
        "lim_charon_pfet_devsim": np.max(
            np.abs(np.asarray(ref_p["c_ff_um2"]) / np.asarray(ref_p["c_devsim"]) - 1)
        ),
        "lim_charon_lifetime": _rel_max(runs, "cv-nfet-tau14-1e-10", "cv-nfet-tau15-1e-10"),
        "lim_charon_pfet_lifetime": _rel_max(runs, "cv-pfet-tau14-1e-10", "cv-pfet-tau15-1e-10"),
        "lim_charon_default_lifetime": _rel_max(
            runs, "cv-nfet-default-1e-10", "cv-nfet-tau15-1e-10"
        ),
        "lim_charon_tol9": _rel_max(runs, "cv-nfet-tau15-1e-9", "cv-nfet-tau15-1e-10"),
        "lim_charon_tol8": _rel_max(runs, "cv-nfet-default-1e-8", "cv-nfet-default-1e-10"),
        "lim_charon_np_ref": max(
            r[f"max_abs_np_over_ni2_minus_1_{s}"] for r in (ref_n, ref_p) for s in "AB"
        ),
        "lim_charon_b6": max(
            r[f"{k}_vs_gate_{s}"] for r in (ref_n, ref_p) for k in ("poly", "body") for s in "AB"
        ),
        "lim_charon_fail_v": float(v["ref_1e-10"]["failed_at"][0]),
        "lim_charon_stop_lo": min(plain),
        "lim_charon_stop_hi": max(plain),
        "lim_charon_tau_stop": tau_stop.pop(),
        "lim_charon_ref_fnorm": v["ref_1e-10"]["failed_fnorm"],
        "lim_charon_ref_wrms": v["ref_1e-10"]["failed_wrms"],
        "lim_charon_inv_biases": ", ".join(f"{b:g}" for b in inv[:-1]) + f" and {inv[-1]:g}",
        "lim_charon_tri3_2d": abs(probes["tri3"]["rel_vs_devsim_1d"]),
        "lim_charon_tri3_strip": probes["tri3"]["strip_max_rel_c_tri3_vs_quad4"],
        "lim_charon_pp": pp,
        "lim_charon_mg": mg,
        "lim_charon_hb_acc": hb_gate["accumulation"],
        "lim_charon_hb_depl": hb_gate["depletion"],
        "lim_charon_tight": "1e-11",
        **{f"lim_charon_b7_{k}": x for k, x in b7.items()},
        "lim_charon_b7_max": max(b7.values()),
        "lim_charon_stall_v": float(stall["failed_at"][0]),
        "lim_charon_stall_fnorm": stall["final"][-1][0],
        "lim_charon_stall_wrms": stall["final"][-1][1],
        "lim_charon_stall_iters": f"{stall['newton_limit'][0][0]}",
        "lim_charon_stall_ramp_v": float(ramp["failed_at"][0]),
        "lim_charon_tight_ramp_v": float(
            studies["study-nfet-default-1e-11"]["failed"]["failed_at"][0]
        ),
        "lim_charon_pfet_start_from": min(above["vg"]),
        "lim_charon_pfet_start_up_to": max(up["vg"]),
        "lim_charon_pfet_start_points": f"{len(covered)}",
        "lim_charon_pfet_start_devsim": pfet_9["max_abs_rel_vs_devsim"],
        "lim_charon_nlp_c": max(abs(p["c_nlp"]) for p in nlp_ok),
        "lim_charon_nlp_ok": [p["vg"] for p in nlp_ok],
        "lim_charon_nlp_bad": [p["vg"] for p in nlp if not p["ok"]],
        "lim_charon_belos_stop": float(belos["failed_at"][0]),
    }


def test_page_numbers_are_the_records():
    """Every number the Charon page prints by substitution (``lim_charon_*``) is recomputed here
    from the records, independently of the figure module; every key is on the page; no
    hand-typed copy of any of them is left on the pages."""
    from gf180tcad import limitations_figures as lf

    subs = {k: v for k, v in lf.substitutions().items() if k.startswith("lim_charon_")}
    want = _expected_page_numbers()
    assert set(subs) == set(want), set(subs) ^ set(want)
    for key, value in want.items():
        text = subs[key]
        if isinstance(value, str):
            assert text == value, (key, text, value)
        elif isinstance(value, list):  # a list of biases: "a, b and c"
            assert [_num(t) for t in text.replace(" and ", ", ").split(", ")] == value, key
        elif "e" in text:
            assert _shown(text.replace("−", "-"), value), (key, text, value)
        else:  # a fixed-point bias or ratio at the digits shown
            digits = len(text.split(".")[1]) if "." in text else 0
            assert round(_num(text), digits) == round(value, digits), (key, text, value)
            assert abs(_num(text) - value) <= 0.5 * 10**-digits + 1e-12, (key, text, value)
    pages = {p: (REPO_ROOT / "docs" / p).read_text("utf-8") for p in
             ("limitations/charon.md", "limitations/index.md", "limitations/status.md",
              "roadmap.md", "index.md")}  # fmt: skip
    for key in subs:
        assert f"{{{{ {key} }}}}" in pages["limitations/charon.md"], key
    for page in ("limitations/index.md", "limitations/status.md", "roadmap.md", "index.md"):
        for dev in ("nfet", "pfet"):
            assert f"{{{{ lim_charon_{dev}_devsim }}}}" in pages[page], (page, dev)
    # no hand-typed copy: no substituted number (in its e-notation forms) is typed on the pages
    settings = {"lim_charon_ref_tau", "lim_charon_tight"}  # deck settings, typed where named
    typed = {t for k, t in subs.items() if "e-" in t and k not in settings}
    typed |= {t.replace("e-", "e-0") for t in typed}
    # and every measured decimal (0.569, 1.238, 0.45 ...), with an ASCII minus too
    # and on the Charon page every measured decimal (0.569, 1.238, 0.45 ...), ASCII minus too;
    # the other pages use such decimals for their own numbers
    decimals = {t for t in subs.values() if re.fullmatch("\u2212?[0-9]+[.][0-9]+", t)}
    decimals |= {t.replace("\u2212", "-") for t in decimals}
    for page, text in pages.items():
        prose = re.sub(r"\{\{[^}]*\}\}", "", text)
        for t in typed | (decimals if page == "limitations/charon.md" else set()):
            assert not re.search(rf"(?<![\w.\-\u2212]){re.escape(t)}(?![\w.]?[0-9])", prose), (
                page, t)  # fmt: skip


def test_step_studies_are_recorded():
    """The plan's step and tolerance studies ran as committed steps and recorded their outcome."""
    studies = _record("hard-range")["step_studies"]
    assert set(studies) == {
        "study-nfet-tau15-secant-50mV",
        "study-nfet-default-1e-11",
        "study-pfet-start-1e-10",
        "study-pfet-start-1e-10-rescue-off",
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
        ("cv-pfet-start-tau15-1e-9", "cv-pfet-start-tau15-1e-10-from-minus-5"),
    }
    for name, ref in pairs:
        r, b = runs[name], runs[ref]
        assert (r["settings"]["CX_REL"], r["settings"]["CX_ABS"]) == ("1e-9", "1e-11"), name
        assert (b["settings"]["CX_REL"], b["settings"]["CX_ABS"]) == ("1e-10", "1e-12"), ref
        assert r["n"] == len(r["vg"]) and len(r["vg"]) == len(runs["cv-nfet-tau15-1e-10"]["vg"])
        common = [v for v in r["vg"] if v in b["vg"]]
        assert len(common) == b["n"], name
        rel = max(abs(r["c_ff_um2"][r["vg"].index(v)] / b["c_ff_um2"][b["vg"].index(v)] - 1)
                  for v in common)  # fmt: skip
        assert rel < 1e-8, (name, rel)
    # the two pfet start reference runs cover the whole grid between them
    covered = set(runs["cv-pfet-start-tau15-1e-10-above-0.6"]["vg"]) | set(
        runs["cv-pfet-start-tau15-1e-10-from-minus-5"]["vg"]
    )
    assert covered == set(runs["cv-pfet-start-tau15-1e-9"]["vg"])
    studies = _record("hard-range")["step_studies"]
    stall = studies["study-pfet-start-1e-10"]["failed"]
    assert float(stall["failed_at"][0]) < min(runs["cv-pfet-start-tau15-1e-10-above-0.6"]["vg"])
    assert stall["newton_limit"] == [[50, 50]] and stall["final"][-1][1] > 1
    for name in ("study-pfet-start-rel-1e-9-abs-1e-12", "study-pfet-start-rel-1e-10-abs-1e-11"):
        assert studies[name]["b2_exit"] == 0, name


def test_readme_charon_numbers_are_the_records():
    """README.md is read on GitHub without substitutions: its Charon numbers are typed, and
    must equal the page's substitutions."""
    from gf180tcad import limitations_figures as lf

    subs = lf.substitutions()
    readme = (REPO_ROOT / "README.md").read_text("utf-8")
    want = (f"within {subs['lim_charon_nfet_devsim']} (nfet) and "
            f"{subs['lim_charon_pfet_devsim']} (pfet) of DEVSIM's")  # fmt: skip
    assert want in " ".join(readme.split()), want


#: Numbers the plan's Task B amendment types that are settings or citations, not measurements: the
#: tolerances, lifetimes and scalings tried, biases and sweep ends chosen, the frequencies and
#: amplitudes, the grid, the spec section, years, file-resolution and scale factors.
PLAN_SETTINGS = {
    "1", "3", "5", "10", "11", "14", "26", "50", "2026", "12.1", "0.3", "0.5", "1.5", "−5",
    "1e-3", "1e-4", "1e-5", "1e-7", "1e-8", "1e-9", "1e-10", "1e-11", "1e-12", "1e-13", "1e-14",
    "1e-15", "1e-16", "1e4", "1e10", "1e20",
}  # fmt: skip


def _plan_tokens(text: str) -> list[str]:
    """The numbers a Markdown text types, outside code spans, {repo} links and issue links."""
    text = re.sub(r"\{repo\}`[^`]*`|`[^`]*`|\[issue #[0-9]+\]\([^)]*\)", "", text)
    return re.findall(r"(?<![\w.#])[−-]?[0-9]+(?:\.[0-9]+)?(?:e[-+]?[0-9]+)?(?!\w)", text)


def _plan_measured() -> dict[str, float | list]:
    """Every measured number the plan's Task B amendment types, recomputed from the records:
    ``{text: value}`` (a list for a text the amendment types more than once)."""
    runs, hard = _record("cv")["runs"], _record("hard-range")
    probes, hb = _record("probes"), _record("harmonic-balance")
    v, studies = hard["variants"], hard["step_studies"]
    ref_n, ref_p = runs["cv-nfet-tau15-1e-10"], runs["cv-pfet-tau15-1e-10"]
    listed = ("tol_1e-8", "tol_1e-6", "tol_1e-4", "scale_1e20", "step_5mV", "nosrh")
    short = [r for r in runs.values() if r["settings"].get("CX_TAU") in ("1e-14", "1e-15")]
    nlp = hard["nlp"]["points"]
    hb1 = probes["harmonic_balance"]
    gate = {s: abs(next(x for c, x in hb1["b4_1e+06_0.0001"][s]["c_from_columns_over_c_qs"]
                        .items() if c.startswith("gate") and "CosH1" in c and "Disp" in c))
            for s in ("accumulation", "depletion")}  # fmt: skip
    body_1hz = hb1["b4_1_0.0001"]["depletion"]["c_from_columns_over_c_qs"]
    b7 = [_rel_max(runs, "cv-nfet-tau15-1e-9", "cv-nfet-tau15-1e-10"),
          _rel_max(runs, "cv-pfet-tau15-1e-9", "cv-pfet-tau15-1e-10"),
          _rel_max(runs, "cv-nfet-start-tau15-1e-9", "cv-nfet-start-tau15-1e-10"),
          max(_rel_max(runs, "cv-pfet-start-tau15-1e-9", r) for r in
              ("cv-pfet-start-tau15-1e-10-above-0.6", "cv-pfet-start-tau15-1e-10-from-minus-5"))]  # fmt: skip
    devsim = [ref_n["max_abs_rel_vs_devsim"], ref_p["max_abs_rel_vs_devsim"]]
    return {
        "0.35": [
            float(v["ref_1e-10"]["failed_at"][0]),
            max(v[n]["last_converged_v"] for n in listed),
            float(v["step_5mV"]["failed_at"][0]),
        ],
        "0.30": v["ref_1e-10"]["last_converged_v"],
        "0.25": min(v[n]["last_converged_v"] for n in listed),
        "0.05": v["gfem"]["last_converged_v"],
        "0.1": float(v["gfem"]["failed_at"][0]),
        "1.1e-9": _rel_max(runs, "cv-nfet-tau14-1e-10", "cv-nfet-tau15-1e-10"),
        "5.7e-10": _rel_max(runs, "cv-pfet-tau14-1e-10", "cv-pfet-tau15-1e-10"),
        "1.0e-9": [_rel_max(runs, "cv-nfet-default-1e-10", "cv-nfet-tau15-1e-10"), b7[0]],
        "2e-16": max(
            max(abs(d["np_over_ni2_body_bulk"] - 1), abs(d["np_over_ni2_poly_bulk"] - 1))
            for d in probes["doping"].values()
        ),
        "7e-6": max(r[f"max_abs_np_over_ni2_minus_1_{s}"] for r in short for s in "AB"),
        "201": [len(ref_n["vg"]), len(runs["cv-pfet-start-tau15-1e-9"]["vg"])],
        "0.55": [
            float(studies["study-nfet-tau15-secant-50mV"]["failed"]["failed_at"][0]),
            max(runs["cv-pfet-start-tau15-1e-10-from-minus-5"]["vg"]),
        ],
        "12": v["ref_1e-10"]["failed_wrms"],
        "59": v["step_5mV"]["failed_wrms"],
        "0.2": float(
            next(
                s for s in probes["solvers"].values() if isinstance(s, dict) and s.get("failed_at")
            )["failed_at"][0]
        ),
        "0.569": float(studies["study-pfet-start-1e-10"]["failed"]["failed_at"][0]),
        "1.238": studies["study-pfet-start-1e-10"]["failed"]["final"][-1][1],
        "0.45": float(studies["study-pfet-start-1e-11"]["failed"]["failed_at"][0]),
        "−0.15": float(studies["study-nfet-default-1e-11"]["failed"]["failed_at"][0]),
        "4.4e-10": b7[1],
        "1.4e-9": b7[2],
        "5.1e-10": b7[3],
        "3e-5": min(devsim),
        "5e-5": max(devsim),
        "1.3e-9": _rel_max(runs, "cv-nfet-default-1e-8", "cv-nfet-default-1e-10"),
        "−1": next(p["vg"] for p in nlp if p["ok"]),
        "0": [[p["vg"] for p in nlp if p["ok"]][1], max(abs(p["c_nlp"]) for p in nlp if p["ok"])],
        "−3": next(p["vg"] for p in nlp if not p["ok"]),
        "2.8e-13": max(ref_n["poly_vs_gate_A"], ref_n["poly_vs_gate_B"]),
        "8.0e-13": max(ref_p["poly_vs_gate_A"], ref_p["poly_vs_gate_B"]),
        "4.4e-13": max(ref_n["body_vs_gate_A"], ref_n["body_vs_gate_B"]),
        "8.1e-13": max(ref_p["body_vs_gate_A"], ref_p["body_vs_gate_B"]),
        "1.0e-12": max(ref_n["oxide_flux_spread_A"], ref_n["oxide_flux_spread_B"]),
        "1.4e-12": max(ref_p["oxide_flux_spread_A"], ref_p["oxide_flux_spread_B"]),
        "3.0e-5": devsim[0],
        "5.4e-5": devsim[1],
        "1.5e-9": max(ref_n["align_A"], ref_n["align_B"]),
        "2.8e-9": max(ref_p["align_A"], ref_p["align_B"]),
        "2472": probes["tri3"]["mesh2d"]["nodes"],
        "2.6e-4": abs(probes["tri3"]["rel_vs_devsim_1d"]),
        "1.3e-3": probes["tri3"]["strip_max_rel_c_tri3_vs_quad4"],
        "2.1e-9": max(
            abs(abs(x) - 1)
            for run in hb["parallel_plate"]["runs"].values()
            for c, x in run["ratio"].items()
            if "CosH1" in c
        ),
        "3.4e-7": max(
            abs(abs(x) - 1)
            for c, x in hb["metal_gate"]["depletion"]["ratio"].items()
            if c.startswith("gate") and "CosH1" in c and "Disp" in c
        ),
        "0.20": gate["accumulation"],
        "0.38": gate["depletion"],
        "−0.16": next(
            x
            for c, x in body_1hz.items()
            if c.startswith("body") and "CosH1" in c and c.endswith("__Current")
        ),
    }


def _matches(text: str, value: float) -> bool:
    """Whether ``text`` is ``value`` at the digits it shows (an integer text: the nearest one;
    "0" only an exact zero)."""
    t = text.replace("−", "-")
    if t == "0":
        return value == 0.0
    if "e" in t:
        return _shown(t, value)
    digits = len(t.split(".")[1]) if "." in t else 0
    return float(t) == round(float(value), digits)


def test_plan_charon_numbers_are_the_records():
    """The plan is read on GitHub without substitutions. Every number its Task B amendment
    types is either a setting (:data:`PLAN_SETTINGS`) or a measurement tied here to its record,
    by token (0.2 does not match inside 0.20), as often as the amendment types it."""
    plan = (REPO_ROOT / "docs/superpowers/plans/2026-10-27-phase4-charon-backend.md").read_text(
        "utf-8"
    )
    amendment = plan[plan.index("**Amended by experiments B1–B7"):plan.index(
        "**Decision: mesh and regions.**")]  # fmt: skip
    tokens = _plan_tokens(amendment)
    measured = _plan_measured()
    untied = sorted({t for t in tokens if t not in measured and t not in PLAN_SETTINGS})
    assert not untied, f"numbers in the amendment tied to no record: {untied}"
    # the bias lists, which also type numbers that are settings elsewhere (1, 3, 5)
    hard = _record("hard-range")
    nlp = hard["nlp"]["points"]
    lists = {
        r"At (.+?) V Newton's first update overshoots": [p["vg"] for p in nlp if not p["ok"]],
        r"where the solve converges, (.+?) V\.": [p["vg"] for p in nlp if p["ok"]],
        r"Steady-state solves started at (.+?) V fail": sorted(
            float(b) for b in hard["inversion_side"]["direct"]
        ),
    }
    for pattern, want in lists.items():
        (typed,) = re.findall(pattern, amendment)
        assert [_num(t) for t in re.split(r", | and ", typed)] == want, (pattern, typed)
    for text, values in measured.items():
        values = values if isinstance(values, list) else [values]
        assert tokens.count(text) >= len(values), (text, tokens.count(text), len(values))
        for value in values:
            assert _matches(text, value), (text, value)
