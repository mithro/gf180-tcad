# SPDX-License-Identifier: Apache-2.0
"""Process data files (data/process/*.toml) and their loader, gf180tcad.tcad.process.

The sandbox-marked test re-reads the SPICE card from the base image (run with
``pytest -m sandbox``); the others only read the committed TOML files.
"""

import json
import math
import re
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from gf180tcad import sandbox
from gf180tcad.tcad import process

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data" / "process"
DEVICES = ("nfet_05v0", "pfet_05v0")
CARD_IN_IMAGE = "$PDK_ROOT/gf180mcuD/libs.tech/ngspice/sm141064.ngspice"


def _raw(device: str) -> dict:
    return tomllib.loads((DATA / f"{device}.toml").read_text(encoding="utf-8"))


def _write(tmp_path: Path, device: str, raw: dict) -> Path:
    """Write ``raw`` back as TOML (only the subset of TOML these files use)."""

    def val(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, str):
            return json.dumps(v)
        if isinstance(v, list):
            return "[" + ", ".join(val(x) for x in v) + "]"
        return repr(v)

    lines = [f"{k} = {val(v)}" for k, v in raw.items() if not isinstance(v, dict)]
    for table, t in raw.items():
        if isinstance(t, dict) and table != "param":
            lines += [f"[{table}]"] + [f"{k} = {val(v)}" for k, v in t.items()]
    scalars = {k: v for k, v in raw["param"].items() if not isinstance(v, dict)}
    if scalars:  # malformed on purpose: a parameter that is not a table
        lines += ["[param]"] + [f"{k} = {val(v)}" for k, v in scalars.items()]
    for name, p in raw["param"].items():
        if isinstance(p, dict):
            lines += [f"[param.{name}]"] + [f"{k} = {val(v)}" for k, v in p.items()]
    (tmp_path / f"{device}.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


# --- the card expression evaluator -----------------------------------------------------------


def test_card_expression_evaluator():
    ev = process.eval_card_expr
    assert ev("1.52e-008+nfet_06v0_tox", {"nfet_06v0_tox": 0.0}) == 1.52e-8
    assert ev("1e-010*nfet_06v0_cgso", {"nfet_06v0_cgso": 1.0}) == 1e-10
    assert ev("7.6e-3+8.47e-3*d", {"d": 2.0}) == 7.6e-3 + 8.47e-3 * 2.0  # * before +
    assert ev("1.7e+017", {}) == 1.7e17
    assert ev("-0.8978+pfet_06v0_dvth0", {"pfet_06v0_dvth0": 0.0}) == -0.8978
    for bad in ("1-2", "1/2", "(1+2)", "2**3", "a+", "", "1e5e5", "sqrt(2)", "1+ +2"):
        with pytest.raises(ValueError):
            ev(bad, {"a": 1.0})
    with pytest.raises(KeyError, match="nfet_06v0_tox"):
        ev("1.52e-008+nfet_06v0_tox", {})


def test_card_assignment_parser():
    assert process.parse_card_assignment("+ toxe='1.52e-008+nfet_06v0_tox'") == (
        "toxe",
        "1.52e-008+nfet_06v0_tox",
    )
    assert process.parse_card_assignment("+ ndep=1.7e+017") == ("ndep", "1.7e+017")
    assert process.parse_card_assignment(".param nfet_06v0_tox=0") == ("nfet_06v0_tox", "0")
    with pytest.raises(ValueError):
        process.parse_card_assignment(".model nfet_06v0.0 nmos")


# --- the committed files ---------------------------------------------------------------------


@pytest.mark.parametrize("device", DEVICES)
def test_files_load(device):
    desc = process.load(device)
    assert desc.device == device
    assert desc.polarity == device[0]
    versions = json.loads((REPO_ROOT / "docker/base/versions.json").read_text(encoding="utf-8"))
    assert desc.card.sha256 == versions["sm141064_ngspice_sha256"]
    for p in desc.params.values():
        assert p.provenance in process.TAGS
        assert p.role in process.ROLES
        assert p.note, p.name
        if p.fixed:
            assert p.source, p.name
            assert p.provenance != "calibrated", p.name
        else:  # a tunable: tagged calibrated, with the source of its start and of its bounds
            assert p.provenance == "calibrated", p.name
            assert p.start_source and p.bounds_source, p.name


@pytest.mark.parametrize("device", DEVICES)
def test_tunables_present(device):
    desc = process.load(device)
    free = {n for n, p in desc.params.items() if not p.fixed}
    assert free == {"t_ox_eff_nm", "n_ch_cm3", "dv_fb_v"} == set(process.TUNABLES)
    for name in free:
        p = desc.params[name]
        assert p.role == "tunable"
        lo, hi = p.bounds
        assert all(isinstance(b, float) and math.isfinite(b) for b in (lo, hi))
        assert lo <= p.value <= hi
        assert p.provenance == "calibrated"
        assert p.start_source and p.bounds_source
    for p in desc.params.values():
        if p.fixed:
            assert p.bounds is None and p.role != "tunable", p.name


@pytest.mark.parametrize("device", DEVICES)
def test_tunable_starts(device):
    desc = process.load(device)
    v = desc.values()
    assert v["t_ox_eff_nm"] == v["toxe_nm"]
    assert v["n_ch_cm3"] == v["ndep_cm3"]
    assert v["dv_fb_v"] == 0.0
    assert desc.params["t_ox_eff_nm"].bounds[0] == v["toxe_nm"]
    assert desc.params["n_ch_cm3"].bounds[1] == 2 * v["ndep_cm3"]
    assert desc.params["dv_fb_v"].bounds == (-0.2, 0.2)
    assert "project choice" in desc.params["dv_fb_v"].bounds_source
    assert "project choice" in desc.params["dv_fb_v"].start_source
    assert "sm141064.ngspice:" in desc.params["t_ox_eff_nm"].start_source  # TOXE
    assert "sm141064.ngspice:" in desc.params["n_ch_cm3"].start_source  # NDEP
    assert "project choice" in desc.params["n_ch_cm3"].bounds_source


@pytest.mark.parametrize("device", DEVICES)
def test_source_kinds_are_structured(device):
    """Whether a start or bound is a card value, derived or a project choice is a field."""
    p = process.load(device).params
    assert p["t_ox_eff_nm"].start_kind == "card"
    assert p["t_ox_eff_nm"].bounds_kind == ("card", "derived")
    assert p["n_ch_cm3"].start_kind == "card"
    assert p["n_ch_cm3"].bounds_kind == ("project-choice", "project-choice")
    assert p["dv_fb_v"].start_kind == "project-choice"
    assert p["dv_fb_v"].bounds_kind == ("project-choice", "project-choice")
    for q in p.values():
        if q.fixed:
            assert q.start_kind is None and q.bounds_kind is None, q.name


@pytest.mark.parametrize(
    ("edit", "match"),
    [
        ({"start_kind": "guess"}, "start_kind"),
        ({"bounds_kind": ["card"]}, "bounds_kind"),
        ({"bounds_kind": ["card", "nope"]}, "bounds_kind"),
        ({"bounds_kind": ["card", "card"]}, "bounds_source"),  # the text cites no card line
        ({"start_kind": "card"}, "start_source"),  # "project choice" text, no card line
    ],
)
def test_source_kinds_checked(tmp_path, edit, match):
    raw = _raw("nfet_05v0")
    raw["param"]["dv_fb_v"].update(edit)
    with pytest.raises(ValueError, match=f"dv_fb_v.*{match}"):
        process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))


def test_spice_card_value_needs_a_card_line(tmp_path):
    """A spice-card value cites its card line, unless it says what it is derived from."""
    raw = _raw("nfet_05v0")
    del raw["param"]["ngate_cm3"]["card_key"], raw["param"]["ngate_cm3"]["card_line"]
    with pytest.raises(ValueError, match="ngate_cm3.*card_line"):
        process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))
    raw = _raw("nfet_05v0")
    del raw["param"]["cf_f_per_m"]["derived_from"]
    with pytest.raises(ValueError, match="cf_f_per_m.*card_line"):
        process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))


@pytest.mark.parametrize(
    ("derived_from", "match"),
    [(["nope"], "nope"), (["t_ox_eff_nm"], "t_ox_eff_nm"), ([], "derived_from"), ("toxe_nm", "")],
)
def test_derived_from_checked(tmp_path, derived_from, match):
    raw = _raw("nfet_05v0")
    raw["param"]["cf_f_per_m"]["derived_from"] = derived_from
    with pytest.raises(ValueError, match=f"cf_f_per_m.*{match}"):
        process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))
    raw = _raw("nfet_05v0")
    raw["param"]["ngate_cm3"]["derived_from"] = ["ndep_cm3"]  # a card value is not derived
    with pytest.raises(ValueError, match="ngate_cm3"):
        process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))


def test_cf_is_derived():
    for device in DEVICES:
        cf = process.load(device).params["cf_f_per_m"]
        assert cf.card_line is None and cf.derived_from == ("toxe_nm", "epsrox")


@pytest.mark.parametrize(
    ("table", "key", "value"),
    [
        ("param.t_ox_eff_nm", "bounds", [15.2, 17.0]),  # hi is not TOXP + delta
        ("centroid_allowance", "delta_nm", 1.0),
    ],
)
def test_t_ox_upper_bound_is_toxp_plus_delta(tmp_path, table, key, value):
    raw = _raw("nfet_05v0")
    t = raw
    for part in table.split("."):
        t = t[part]
    t[key] = value
    with pytest.raises(ValueError, match="TOXP"):
        process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))


@pytest.mark.parametrize(
    ("key", "value"),
    [("model_line", "37055"), ("tt_lib_line", 105.0), ("sha256", 1), ("file", ""), ("model", 7)],
)
def test_card_table_types(tmp_path, key, value):
    raw = _raw("nfet_05v0")
    raw["card"][key] = value
    with pytest.raises(ValueError, match=key):
        process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))


def test_param_must_be_a_table(tmp_path):
    raw = _raw("nfet_05v0")
    raw["param"]["bogus"] = 1.0
    with pytest.raises(ValueError, match="bogus"):
        process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))


@pytest.mark.parametrize("bad", [True, False, "0.1", None])
def test_with_values_rejects_non_numbers(bad):
    with pytest.raises(ValueError, match="dv_fb_v"):
        process.load("nfet_05v0").with_values({"dv_fb_v": bad})


@pytest.mark.parametrize(
    ("device", "toxe_nm", "toxp_nm", "k1", "ngate", "dlc_nm", "cgso", "cgsl", "acde"),
    [
        ("nfet_05v0", 15.2, 16.0, 0.9, 1e20, 54.0, 1e-10, 1.5e-10, 0.3),
        ("pfet_05v0", 15.6, 15.6, 0.9588, 3.6e19, 7.4, 7.71e-11, 5.25e-11, 0.7),
    ],
)
def test_brief_values(device, toxe_nm, toxp_nm, k1, ngate, dlc_nm, cgso, cgsl, acde):
    v = process.load(device).values()
    close = lambda a, b: math.isclose(a, b, rel_tol=1e-12)
    assert close(v["toxe_nm"], toxe_nm) and close(v["toxp_nm"], toxp_nm)
    assert v["ndep_cm3"] == 1.7e17 and v["k1_sqrt_v"] == k1 and v["ngate_cm3"] == ngate
    assert v["xj_um"] == 0.15 and close(v["dlc_nm"], dlc_nm)
    assert v["cgso_f_per_m"] == v["cgdo_f_per_m"] == cgso
    assert v["cgsl_f_per_m"] == v["cgdl_f_per_m"] == cgsl
    assert v["tnom_c"] == 25.0 and v["epsrox"] == 3.9
    assert v["acde_m_per_v"] == acde and v["moin"] == 15.0 and v["capmod"] == 2.0


def test_temperature_is_tnom():
    for device in DEVICES:
        assert process.load(device).values()["tnom_c"] + 273.15 == process.CONSTANTS.t_k


@pytest.mark.parametrize("device", DEVICES)
def test_k1_bound_recomputed(device):
    desc = process.load(device)
    v = desc.values()
    c = process.CONSTANTS
    cox = v["epsrox"] * c.eps0_f_per_cm / (v["toxe_nm"] * 1e-7)  # F/cm^2
    n_k1 = (v["k1_sqrt_v"] * cox) ** 2 / (2 * c.q_c * c.eps_si * c.eps0_f_per_cm)
    lo = desc.params["n_ch_cm3"].bounds[0]
    assert math.isclose(lo, 0.5 * n_k1, rel_tol=1e-6)
    expected = {"nfet_05v0": 6.30e16, "pfet_05v0": 6.78e16}[device]  # the brief's values
    assert math.isclose(lo, expected, rel_tol=1e-3)


@pytest.mark.parametrize("device", DEVICES)
def test_cf_is_the_bsim4_default(device):
    """CF is not on the card, so BSIM4 4.5.0 eq. (7.5.1) applies: 2·EPSROX·ε0/π·ln(1+4e-7/TOXE)."""
    v = process.load(device).values()
    eps0_f_per_m = process.CONSTANTS.eps0_f_per_cm * 100
    cf = 2 * v["epsrox"] * eps0_f_per_m / math.pi * math.log(1 + 4e-7 / (v["toxe_nm"] * 1e-9))
    assert math.isclose(v["cf_f_per_m"], cf, rel_tol=1e-12)
    assert math.isclose(v["cf_f_per_m"], 7.3e-11, rel_tol=0.02)


# --- the charge-centroid allowance -----------------------------------------------------------


def test_centroid_allowance_hand_point():
    """nfet, hand-evaluated (BSIM4.5.0 manual §7.3, constants of the plan's table).

    vt = k_B·298.15/q = 0.0256926 V; ni (eq. 12.7.3) = 1.23019e10 cm⁻³;
    Φs (eq. 2.2.7) = 0.4 + vt·ln(1.7e17/ni) = 0.822426 V;
    Vfbzb (eq. 7.2.14, long channel) = 0.67314 − Φs − 0.9·√Φs = −0.965475 V;
    Ldebye = √(11.7·ε0·vt/(q·1.7e23 m⁻³)) = 9.88534 nm, Xmax = Ldebye/3 = 3.29511 nm;
    ACDE·(NDEP/2e16)^−0.25 = 0.3·8.5^−0.25 = 0.175698; δx = 1e-3·TOXE = 0.0152 nm.
    At Vg = −2 V (edge of the accumulation plateau): field (−2 + 0.965475)/(1.6e-8 m·1e8)
    = −0.646578 MV/cm, raw X_DC = 3.29511·exp(0.175698·−0.646578) = 2.94126 nm,
    X0 = 3.29511 − 2.94126 − 0.0152 = 0.33865 nm,
    X_DC = 3.29511 − ½(0.33865 + √(0.33865² + 4·0.0152·3.29511)) = 2.84515 nm.
    X_DC rises towards flat band, so this is the accumulation-plateau maximum; at Vg = −5 V
    the same steps give 2.08940 nm. In depletion (Vg = +5 V, outside the plateaus) the
    formula saturates near Xmax: 3.27885 nm, which is not used.
    Inversion (eq. 7.3.4) at Vgsteff → 0: 4(VTH0 − VFB − Φs) = 4·0.9·√Φs = 3.26476 V,
    1.9 nm/(1 + (3.26476/3.2)^0.7) = 0.943339 nm (an upper bound on the inversion plateau).
    Δ = 2.84515·3.9/11.7 = 0.948383 nm, rounded up to 0.95 nm.
    """
    cv = process.load("nfet_05v0").card_values()
    c = process.CONSTANTS
    assert math.isclose(process.bsim4_ni_cm3(c), 1.23019e10, rel_tol=1e-5)
    assert math.isclose(process.bsim4_phi_s_v(cv, c), 0.822426, rel_tol=1e-6)
    assert math.isclose(process.bsim4_vfbzb_v(cv, c), -0.965475, rel_tol=1e-6)
    assert math.isclose(process.ctm_x_dc_acc_m(-2.0, cv, c), 2.84515e-9, rel_tol=1e-5)
    assert math.isclose(process.ctm_x_dc_acc_m(-5.0, cv, c), 2.08940e-9, rel_tol=1e-5)
    assert math.isclose(process.ctm_x_dc_acc_m(5.0, cv, c), 3.27885e-9, rel_tol=1e-5)
    assert math.isclose(process.ctm_x_dc_inv_sup_m(cv, c), 0.943339e-9, rel_tol=1e-5)
    res = process.centroid(cv, c)
    assert res.plateau_v == 2.0 and res.vg_at_max_v == -2.0
    assert math.isclose(res.x_dc_max_m, 2.84515e-9, rel_tol=1e-5)
    assert process.centroid_allowance_nm(cv, c) == 0.95


def test_centroid_window_excludes_depletion():
    """Only polarity·Vg ≤ −2 V and ≥ +2 V count; the depletion saturation of X_DC does not."""
    for device, delta in (("nfet_05v0", 0.95), ("pfet_05v0", 0.79)):
        cv = process.load(device).card_values()
        res = process.centroid(cv)
        assert res.vg_at_max_v == -2.0 * cv["type"]
        assert res.delta_nm == delta
        # the whole sweep would pick up the depletion end (about Ldebye/3): 1.10 nm
        full = max(process.ctm_x_dc_acc_m(v, cv) for v in process.CV_VG)
        assert process.round_up_nm(full * cv["epsrox"] / 11.7 * 1e9) == 1.10 > delta
        with pytest.raises(ValueError, match="plateau"):
            process.centroid(cv, plateau_v=6.0)  # no bias of the sweep in the window


def test_centroid_allowance_rounds_up():
    assert process.round_up_nm(1.09295) == 1.10
    assert process.round_up_nm(1.10) == 1.10
    assert process.round_up_nm(1.1000001) == 1.11


@pytest.mark.parametrize("device", DEVICES)
def test_centroid_allowance(device):
    desc = process.load(device)
    ca = desc.centroid_allowance
    assert ca.plateau_v == process.PLATEAU_V == 2.0
    delta = process.centroid_allowance_nm(desc.card_values(), plateau_v=ca.plateau_v)
    # computed from the BSIM4 CTM over the plateaus, not the 0.5 nm fallback
    assert delta == ca.delta_nm == {"nfet_05v0": 0.95, "pfet_05v0": 0.79}[device]
    hi = desc.params["t_ox_eff_nm"].bounds[1]
    assert math.isclose(hi, desc.values()["toxp_nm"] + delta, rel_tol=1e-12)
    src = desc.params["t_ox_eff_nm"].bounds_source
    assert "7.3.2" in src and "7.3.4" in src and "project choice" not in src
    assert "2 V" in src and "2 V" in ca.note


def test_centroid_vfbzb_inside_the_sweep():
    """The maximum is over the cv sweep; both flat bands lie inside it."""
    for device in DEVICES:
        cv = process.load(device).card_values()
        assert -5.0 < process.bsim4_vfbzb_v(cv, process.CONSTANTS) < 5.0


# --- loader validation -----------------------------------------------------------------------


def test_bounds_enforced(tmp_path):
    desc = process.load("nfet_05v0")
    lo, hi = desc.params["t_ox_eff_nm"].bounds
    new = desc.with_values({"t_ox_eff_nm": hi, "dv_fb_v": -0.2})
    assert new.values()["t_ox_eff_nm"] == hi and new.values()["dv_fb_v"] == -0.2
    assert new.params["t_ox_eff_nm"].provenance == "calibrated"
    assert desc.values()["t_ox_eff_nm"] == 15.2  # the original is unchanged
    for bad in (lo - 1e-9, hi + 1e-9, math.nan, math.inf):
        with pytest.raises(ValueError, match="t_ox_eff_nm"):
            desc.with_values({"t_ox_eff_nm": bad})
    with pytest.raises(KeyError, match="nope"):
        desc.with_values({"nope": 1.0})
    # the files are checked too: a start outside its bounds, missing bounds, lo > hi
    for edit in (
        {"value": 30.0},
        {"bounds": None},
        {"bounds": [17.1, 15.2]},
        {"bounds": [15.2]},
        {"bounds_source": None},
        {"start_source": None},
        {"start_source": "my notebook"},
    ):
        raw = _raw("nfet_05v0")
        p = raw["param"]["t_ox_eff_nm"]
        for k, v in edit.items():
            if v is None:
                del p[k]
            else:
                p[k] = v
        with pytest.raises(ValueError, match="t_ox_eff_nm"):
            process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))


def test_fixed_cannot_change():
    desc = process.load("pfet_05v0")
    for name in ("toxe_nm", "ngate_cm3", "dlc_nm", "cgso_f_per_m", "cf_f_per_m"):
        assert desc.params[name].fixed
        with pytest.raises(ValueError, match=name):
            desc.with_values({name: desc.values()[name]})
    with pytest.raises(AttributeError):
        desc.device = "x"
    with pytest.raises(TypeError):
        desc.params["toxe_nm"] = desc.params["toxe_nm"]


def test_no_calibrated_values_in_data(tmp_path):
    """Only the tunables carry the calibrated tag, and the files hold their starts."""
    assert sorted(f.stem for f in DATA.glob("*.toml")) == sorted(DEVICES)
    for f in sorted(DATA.glob("*.toml")):
        for name, p in tomllib.loads(f.read_text(encoding="utf-8"))["param"].items():
            assert (p["provenance"] == "calibrated") == (p["role"] == "tunable"), name
    raw = _raw("nfet_05v0")
    raw["param"]["ndep_cm3"]["provenance"] = "calibrated"
    with pytest.raises(ValueError, match="ndep_cm3.*calibrated"):
        process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))


@pytest.mark.parametrize("tag", ["spice-card", "literature", "pdk-doc"])
def test_tunable_must_be_tagged_calibrated(tmp_path, tag):
    raw = _raw("nfet_05v0")
    raw["param"]["n_ch_cm3"]["provenance"] = tag
    with pytest.raises(ValueError, match="n_ch_cm3.*calibrated"):
        process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))


def test_tunable_needs_both_sources(tmp_path):
    for key in ("start_source", "bounds_source"):
        raw = _raw("pfet_05v0")
        del raw["param"]["dv_fb_v"][key]
        with pytest.raises(ValueError, match="dv_fb_v"):
            process.load("pfet_05v0", data_dir=_write(tmp_path, "pfet_05v0", raw))
    raw = _raw("pfet_05v0")
    raw["param"]["ngate_cm3"]["start_source"] = "sm141064.ngspice:38200"  # fixed: no start
    with pytest.raises(ValueError, match="ngate_cm3"):
        process.load("pfet_05v0", data_dir=_write(tmp_path, "pfet_05v0", raw))


def test_centroid_allowance_table_checked(tmp_path):
    raw = _raw("nfet_05v0")
    raw["centroid_allowance"]["plateau_v"] = -1.0
    with pytest.raises(ValueError, match="plateau_v"):
        process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("provenance", "guess"),
        ("source", "my notebook"),
        ("source", "sm141064.ngspice:37309; http://example.com/x"),
        ("role", "other"),
        ("fixed", "yes"),
        ("unit", ""),
    ],
)
def test_bad_fields_rejected(tmp_path, key, value):
    raw = _raw("nfet_05v0")
    raw["param"]["ngate_cm3"][key] = value
    with pytest.raises(ValueError, match="ngate_cm3"):
        process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))


def test_card_refs_match_source(tmp_path):
    """A parameter's card_line and card_params are exactly the card lines its source cites."""
    for device in DEVICES:
        for p in process.load(device).params.values():
            cited = {int(m) for m in re.findall(r"sm141064\.ngspice:(\d+)", ";".join(p.source))}
            if p.card_line is not None:
                assert {p.card_line, *p.card_params} <= cited, p.name
    raw = _raw("nfet_05v0")
    raw["param"]["ngate_cm3"]["card_line"] = 37203
    with pytest.raises(ValueError, match="ngate_cm3"):
        process.load("nfet_05v0", data_dir=_write(tmp_path, "nfet_05v0", raw))


def test_unknown_device():
    with pytest.raises(ValueError, match="nfet_03v3"):
        process.load("nfet_03v3")


def test_parameter_is_frozen():
    p = process.load("nfet_05v0").params["toxe_nm"]
    with pytest.raises(AttributeError):
        p.value = 1.0
    assert replace(p, value=1.0).value == 1.0


# --- the card in the image (Docker) ----------------------------------------------------------


@pytest.fixture(scope="module")
def card_lines(tmp_path_factory) -> list[str]:
    out = tmp_path_factory.mktemp("card")
    sandbox.run(["sh", "-c", f'cp "{CARD_IN_IMAGE}" /work/out/card'], out_dir=out, mem="1g", cpus=1)
    data = (out / "card").read_bytes()
    assert process.sha256_hex(data) == process.load("nfet_05v0").card.sha256
    return data.decode("utf-8").splitlines()


def _section(lines: list[str], start: int, end_pattern: str) -> range:
    """1-based line range from ``start`` up to (not including) the first line matching."""
    for n in range(start + 1, len(lines) + 1):
        if re.match(end_pattern, lines[n - 1]):
            return range(start, n)
    raise AssertionError(f"no end after line {start}")


@pytest.mark.sandbox
@pytest.mark.parametrize("device", DEVICES)
def test_card_values_and_lines(card_lines, device):
    desc = process.load(device)
    card = desc.card
    kind = "nmos" if desc.polarity == "n" else "pmos"
    assert card_lines[card.model_line - 1].split() == [".model", card.model, kind]
    model = _section(card_lines, card.model_line, r"\.model |\.endl")
    assert card_lines[card.tt_lib_line - 1].strip() == ".lib typical"
    tt = _section(card_lines, card.tt_lib_line, r"\.endl")
    tt_params = {}
    for n in tt:
        if card_lines[n - 1].startswith(".param "):
            k, e = process.parse_card_assignment(card_lines[n - 1])
            tt_params[k] = (n, process.eval_card_expr(e, {}))
    checked = 0
    for p in desc.params.values():
        if p.card_line is None:
            continue
        assert p.card_line in model, f"{p.name}: line {p.card_line} is outside {card.model}"
        key, expr = process.parse_card_assignment(card_lines[p.card_line - 1])
        assert key == p.card_key, p.name
        names = process.card_expr_names(expr)
        assert {tt_params[n][0] for n in names} == set(p.card_params), p.name
        value = process.eval_card_expr(expr, {n: tt_params[n][1] for n in names}) * p.card_scale
        start = p.value
        assert math.isclose(start, value, rel_tol=1e-12, abs_tol=0.0), (p.name, start, value)
        checked += 1
    # every fixed value but the derived CF is a card value (the tunable starts equal them)
    assert checked == sum(p.fixed for p in desc.params.values()) - 1
    assert desc.params["cf_f_per_m"].card_line is None
    # what the files say is absent from the card is absent from this model
    keys = {
        process.parse_card_assignment(card_lines[n - 1])[0]
        for n in model
        if card_lines[n - 1].startswith("+")
    }
    assert "cf" not in keys
    assert ("toxp" in keys) == (desc.polarity == "n")
    assert ("vfb" in keys) == (desc.polarity == "p")
    assert "dtox" not in keys
