# SPDX-License-Identifier: Apache-2.0
"""The 2D validation numbers of the pages are the records' (the owner's rule: measured numbers are
substituted, never typed).

docs/comparison/cv-agreement.md, docs/index.md and docs/limitations/index.md print them through
the ``lim_v2d_*`` substitutions of :mod:`gf180tcad.limitations_figures`. Each one a page uses is
recomputed here from the validation files, the calibrated cells' cv.csv and the pfet calibration
result, independently of that module. The README cannot use substitutions, so its Status line is
compared with the same counts.
"""

import itertools
import json
import re

import numpy as np
import pytest

from gf180tcad import io
from gf180tcad import limitations_figures as lf
from gf180tcad.devices import DEVICES
from gf180tcad.sandbox import REPO_ROOT

TCAD = REPO_ROOT / "results" / "tcad"
PAGES = (
    "docs/comparison/cv-agreement.md",
    "docs/index.md",
    "docs/limitations/index.md",
    "docs/limitations/moscap2d.md",
)
WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
MINUS = "−"


def _val(device: str) -> dict:
    return json.loads((TCAD / "validation" / f"{device}.json").read_text("utf-8"))


def _used() -> set[str]:
    keys = set()
    for page in PAGES:
        text = (REPO_ROOT / page).read_text("utf-8")
        keys |= set(re.findall(r"\{\{ (lim_v2d_[a-z0-9_]+) \}\}", text))
    return keys


def _num(text: str) -> float:
    return float(text.replace(MINUS, "-"))


def _counts() -> dict[str, int]:
    out = {"Agree": 0, "Same process": 0, "Disagree": 0}
    for device in DEVICES:
        for e in _val(device)["two_d"].values():
            if e["status"] == "compared":
                out[e["verdict"]] += 1
    return out


def _cell_value(device: str, gid: str, name: str) -> float:
    """The value a ``lim_v2d_<dev>_<gid>_<name>`` key prints, from the records."""
    e = _val(device)["two_d"][gid]
    sr, win = e["spice_regions"], e["verdicts"]["dv_dep"]["window"]
    u_dep = e["tcad_crossings"]["u_dep"]
    one = _val(device)["one_d"].get(gid)
    if one is None:
        cal = json.loads((TCAD / "calibration" / f"{device}.result.json").read_text("utf-8"))
        one = cal["per_geometry"].get(gid)
    if name in ("cgg_acc", "cgg_inv"):
        cols = io.read_csv(TCAD / "moscap2d" / device / "calibrated" / gid / "cv.csv")[0]
        u = DEVICES[device].polarity * np.asarray(cols["vg"])
        return float(np.asarray(cols["cgg_total"])[u == (-5.0 if name == "cgg_acc" else 5.0)][0])
    simple = {
        "spice_acc": sr["c_acc"], "spice_inv": sr["c_inv"], "u_dep": u_dep, "spice_u_dep": sr["u_dep"],
        "env_lo": win["lo"], "env_hi": win["hi"], "env_width": win["hi"] - win["lo"],
        "env_width_long": win["hi"] - win["lo"], "past_ff_mv": abs(win["lo"] - u_dep) * 1e3,
        "dv_dep_mv": e["verdicts"]["dv_dep"]["dv_v"] * 1e3,
        "dv_inv_mv": e["verdicts"]["dv_inv"]["dv_v"] * 1e3,
        "acc_pct": e["metrics"]["plateau_acc_max_rel"] * 100,
        "inv_pct": e["metrics"]["plateau_inv_max_rel"] * 100,
    }  # fmt: skip
    if name in simple:
        return simple[name]
    u1 = one["tcad_crossings"]["u_dep"]
    return {
        "u_dep_1d": u1, "only_2d_mv": abs(u_dep - u1) * 1e3,
        "1d_inside_mv": abs(u1 - win["lo"]) * 1e3, "1d_off_mv": abs(u1 - sr["u_dep"]) * 1e3,
        "1d_acc_pct": one["metrics"]["plateau_acc_max_rel"] * 100,
        "1d_inv_pct": one["metrics"]["plateau_inv_max_rel"] * 100,
        "1d_dv_dep_mv": one["metrics"]["dv_dep_v"] * 1e3,
    }[name]  # fmt: skip


def _rounds(text: str, value: float) -> bool:
    """``text`` is ``value`` rounded at its last written digit."""
    digits = len(text.split(".")[1]) if "." in text else 0
    return abs(_num(text) - value) <= 0.5 * 10**-digits + 1e-12


def test_pages_use_substitutions_that_exist():
    subs = lf.substitutions()
    used = _used()
    assert used, "no lim_v2d_ substitution on the pages"
    assert used <= set(subs), sorted(used - set(subs))


@pytest.mark.parametrize("key", sorted(_used()))
def test_each_used_number_is_the_records(key):
    subs = lf.substitutions()
    text = subs[key]
    counts = _counts()
    words = {"agree": "Agree", "same": "Same process", "disagree": "Disagree"}
    if key == "lim_v2d_disagree_count" or key.startswith("lim_v2d_count_"):
        verdict = "Disagree" if key == "lim_v2d_disagree_count" else words[key.rsplit("_", 1)[1]]
        assert text == WORDS[counts[verdict]], key
        return
    if key == "lim_v2d_disagree_cells":
        parts = []
        for device in DEVICES:
            gs = sorted((lf._geometry(device, gid) for gid, e in _val(device)["two_d"].items()
                         if e["status"] == "compared" and e["verdict"] == "Disagree"),
                        key=lambda g: (-g.w_um, g.l_um))  # fmt: skip
            labels = [f"W{g.w_um:g}/L{g.l_um:g}" for g in gs]
            if labels:
                joined = (
                    labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]
                )
                parts.append(f"{device.split('_')[0]} {joined}")
        assert text == ", and ".join(parts), (text, parts)
        return
    m = re.fullmatch(r"lim_v2d_(nfet|pfet)_others", key)
    if m:
        device = f"{m.group(1)}_05v0"
        for gid, e in _val(device)["two_d"].items():
            if e["status"] == "compared" and e["verdict"] != "Disagree":
                g = lf._geometry(device, gid)
                assert f"W{g.w_um:g}/L{g.l_um:g}" in text, (key, gid)
        return
    m = re.fullmatch(
        r"lim_v2d_pfet_(w[0-9]+p[0-9]+_l[0-9]+p[0-9]+)_(w[0-9]+p[0-9]+_l[0-9]+p[0-9]+)_(spice|two_d)_move(_mv)?",
        key,
    )
    if m:
        a, b, where, mv = m.groups()
        field = "spice_regions" if where == "spice" else "tcad_crossings"
        pv = _val("pfet_05v0")["two_d"]
        move = pv[b][field]["u_dep"] - pv[a][field]["u_dep"]
        assert _rounds(text, move * (1e3 if mv else 1)), (key, text, move)
        return
    m = re.fullmatch(r"lim_v2d_(nfet|pfet)_(w[0-9]+p[0-9]+_l[0-9]+p[0-9]+)_(.+)", key)
    assert m, key
    dev, gid, name = m.groups()
    check = re.fullmatch(r"(plateau_acc|plateau_inv|dv_dep|dv_inv)_verdict", name)
    if check:
        want = _val(f"{dev}_05v0")["two_d"][gid]["verdicts"][check.group(1)]["verdict"]
        assert text == want, (key, text, want)
        return
    value = _cell_value(f"{dev}_05v0", gid, name)
    assert _rounds(text, value), (key, text, value)


def test_every_disagree_cell_fails_on_the_depletion_crossing_alone():
    """The pages' "each on the depletion crossing" and "All ... fail on the depletion crossing
    alone": every Disagree 2D cell is Disagree on dv_dep and on no other check."""
    for device in DEVICES:
        for gid, e in _val(device)["two_d"].items():
            if e["status"] == "compared" and e["verdict"] == "Disagree":
                bad = [k for k, v in e["verdicts"].items() if v["verdict"] == "Disagree"]
                assert bad == ["dv_dep"], (device, gid, bad)


def test_readme_status_line_is_the_counts():
    """The README's 2D Status line, which cannot use substitutions, gives the same counts as
    docs/index.md's substituted one."""
    subs = lf.substitutions()
    readme = " ".join((REPO_ROOT / "README.md").read_text("utf-8").split())
    want = (
        f"Of them, {subs['lim_v2d_count_agree']} are Agree, {subs['lim_v2d_count_same']} Same "
        f"process and {subs['lim_v2d_count_disagree']} Disagree. Each Disagree is on the"
    )
    assert want in readme, want
    index = " ".join((REPO_ROOT / "docs/index.md").read_text("utf-8").split())
    assert (
        "Of them, {{ lim_v2d_count_agree }} are Agree, {{ lim_v2d_count_same }} Same process and "
        "{{ lim_v2d_count_disagree }} Disagree. Each Disagree is on the {term}`depletion` crossing."
    ) in index


def _e(device: str, gid: str) -> dict:
    return _val(device)["two_d"][gid]


def _one_d_u_dep(device: str, gid: str) -> float:
    one = _val(device)["one_d"].get(gid)
    if one is None:
        cal = json.loads((TCAD / "calibration" / f"{device}.result.json").read_text("utf-8"))
        one = cal["per_geometry"][gid]
    return one["tcad_crossings"]["u_dep"]


def test_the_c_v_page_s_statements_hold():
    """The sentences of the C-V page's 2D validation that the tables back, checked on the
    records: the nfet above SPICE at accumulation and below at inversion, its gap shrinking with
    L; the pfet W10/L0.7 plateaus closer in 2D than in 1D and the crossings on opposite sides of
    SPICE's; below the 1D crossing at W10/L0.7 and W10/L1 in both devices, by less at longer L;
    the SPICE pfet edge moving faster with L than the 2D crossing and the envelope narrowing;
    the pfet W10/L1 2D crossing inside the envelope and its 1D one at SPICE's (within 1 mV);
    the pfet W10/L2 2D crossing past the ff end and its 1D one inside it."""
    nfet = ("w10p0_l0p60", "w10p0_l0p70", "w10p0_l1p00", "w10p0_l2p00")
    for gid in nfet:
        cols = io.read_csv(TCAD / "moscap2d" / "nfet_05v0" / "calibrated" / gid / "cv.csv")[0]
        vg, c = np.asarray(cols["vg"]), np.asarray(cols["cgg_total"])
        sr = _e("nfet_05v0", gid)["spice_regions"]
        assert c[vg == -5.0][0] > sr["c_acc"] and c[vg == 5.0][0] < sr["c_inv"], gid
    for part in ("plateau_acc_max_rel", "plateau_inv_max_rel"):
        gaps = [_e("nfet_05v0", g)["metrics"][part] for g in nfet]
        assert gaps == sorted(gaps, reverse=True), part
    e07 = _e("pfet_05v0", "w10p0_l0p70")
    one07 = _val("pfet_05v0")["one_d"]["w10p0_l0p70"]
    for part in ("plateau_acc_max_rel", "plateau_inv_max_rel"):
        assert e07["metrics"][part] < one07["metrics"][part], part
    assert e07["metrics"]["dv_dep_v"] < 0 < one07["metrics"]["dv_dep_v"]
    for device in DEVICES:
        shifts = []
        for gid in ("w10p0_l0p70", "w10p0_l1p00"):
            u2, u1 = _e(device, gid)["tcad_crossings"]["u_dep"], _one_d_u_dep(device, gid)
            assert u2 < u1, (device, gid)
            shifts.append(u1 - u2)
        assert shifts[0] > shifts[1], device
    lengths = ("w10p0_l0p70", "w10p0_l1p00", "w10p0_l2p00")
    pf = [_e("pfet_05v0", g) for g in lengths]
    only = [
        _one_d_u_dep("pfet_05v0", g) - e["tcad_crossings"]["u_dep"] for g, e in zip(lengths, pf)
    ]
    assert only == sorted(only, reverse=True)
    widths = [e["verdicts"]["dv_dep"]["window"] for e in pf]
    widths = [w["hi"] - w["lo"] for w in widths]
    assert widths == sorted(widths, reverse=True)
    for a, b in itertools.pairwise(pf):
        spice = b["spice_regions"]["u_dep"] - a["spice_regions"]["u_dep"]
        two_d = b["tcad_crossings"]["u_dep"] - a["tcad_crossings"]["u_dep"]
        assert spice > two_d > 0
    l1, l2 = pf[1], pf[2]
    w1 = l1["verdicts"]["dv_dep"]["window"]
    assert w1["lo"] < l1["tcad_crossings"]["u_dep"] < w1["hi"]
    assert abs(_one_d_u_dep("pfet_05v0", "w10p0_l1p00") - l1["spice_regions"]["u_dep"]) < 1e-3
    w2 = l2["verdicts"]["dv_dep"]["window"]
    assert l2["tcad_crossings"]["u_dep"] < w2["lo"] < _one_d_u_dep("pfet_05v0", "w10p0_l2p00")
