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
    lines += ["[card]"] + [f"{k} = {val(v)}" for k, v in raw["card"].items()]
    for name, p in raw["param"].items():
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
        assert p.source, p.name
        assert p.note, p.name


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
        assert p.bounds_source
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
    assert "project choice" in desc.params["n_ch_cm3"].bounds_source


@pytest.mark.parametrize(
    ("device", "toxe_nm", "toxp_nm", "k1", "ngate", "dlc_nm", "cgso", "cgsl", "acde"),
    [
        ("nfet_05v0", 15.2, 16.0, 0.9, 1e20, 54.0, 1e-10, 1.5e-10, 0.3),
        ("pfet_05v0", 15.6, 15.6, 0.9588, 3.6e19, 7.4, 7.71e-11, 5.25e-11, 0.7),
    ],
)
def test_brief_values(device, toxe_nm, toxp_nm, k1, ngate, dlc_nm, cgso, cgsl, acde):
    v = process.load(device).values()
    close = lambda a, b: math.isclose(a, b, rel_tol=1e-12)  # noqa: E731
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
    ACDE·(NDEP/2e16)^−0.25 = 0.3·8.5^−0.25 = 0.175698.
    At Vg = −5 V: field (−5 + 0.965475)/(1.6e-8 m·1e8) = −2.52158 MV/cm,
    raw X_DC = 3.29511·exp(0.175698·−2.52158) = 2.11574 nm, δx = 1e-3·TOXE = 0.0152 nm,
    X0 = 3.29511 − 2.11574 − 0.0152 = 1.16417 nm,
    X_DC = 3.29511 − ½(1.16417 + √(1.16417² + 4·0.0152·3.29511)) = 2.08940 nm.
    At Vg = +5 V the same steps give 3.27885 nm, the maximum over the sweep.
    Inversion (eq. 7.3.4) at Vgsteff → 0: 4(VTH0 − VFB − Φs) = 4·0.9·√Φs = 3.26476 V,
    1.9 nm/(1 + (3.26476/3.2)^0.7) = 0.943339 nm.
    Δ = 3.27885·3.9/11.7 = 1.09295 nm, rounded up to 1.10 nm.
    """
    cv = process.load("nfet_05v0").card_values()
    c = process.CONSTANTS
    assert math.isclose(process.bsim4_ni_cm3(c), 1.23019e10, rel_tol=1e-5)
    assert math.isclose(process.bsim4_phi_s_v(cv, c), 0.822426, rel_tol=1e-6)
    assert math.isclose(process.bsim4_vfbzb_v(cv, c), -0.965475, rel_tol=1e-6)
    assert math.isclose(process.ctm_x_dc_acc_m(-5.0, cv, c), 2.08940e-9, rel_tol=1e-5)
    assert math.isclose(process.ctm_x_dc_acc_m(5.0, cv, c), 3.27885e-9, rel_tol=1e-5)
    assert math.isclose(process.ctm_x_dc_inv_sup_m(cv, c), 0.943339e-9, rel_tol=1e-5)
    res = process.centroid(cv, c)
    assert res.vg_at_max_v == 5.0
    assert math.isclose(res.x_dc_max_m, 3.27885e-9, rel_tol=1e-5)
    assert process.centroid_allowance_nm(cv, c) == 1.10


def test_centroid_allowance_rounds_up():
    assert process.round_up_nm(1.09295) == 1.10
    assert process.round_up_nm(1.10) == 1.10
    assert process.round_up_nm(1.1000001) == 1.11


@pytest.mark.parametrize("device", DEVICES)
def test_centroid_allowance(device):
    desc = process.load(device)
    delta = process.centroid_allowance_nm(desc.card_values())
    assert delta == 1.10  # computed from the BSIM4 CTM, not the 0.5 nm fallback
    hi = desc.params["t_ox_eff_nm"].bounds[1]
    assert math.isclose(hi, desc.values()["toxp_nm"] + delta, rel_tol=1e-12)
    src = desc.params["t_ox_eff_nm"].bounds_source
    assert "7.3.2" in src and "7.3.4" in src and "project choice" not in src


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
    for f in sorted(DATA.glob("*.toml")):
        assert "calibrated" not in {p["provenance"] for p in tomllib.loads(f.read_text())["param"].values()}
    assert sorted(f.stem for f in DATA.glob("*.toml")) == sorted(DEVICES)
    raw = _raw("nfet_05v0")
    raw["param"]["n_ch_cm3"]["provenance"] = "calibrated"
    with pytest.raises(ValueError, match="calibrated"):
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
    assert checked >= 20
    # what the files say is absent from the card is absent from this model
    keys = {process.parse_card_assignment(card_lines[n - 1])[0] for n in model if card_lines[n - 1].startswith("+")}
    assert "cf" not in keys
    assert ("toxp" in keys) == (desc.polarity == "n")
    assert ("vfb" in keys) == (desc.polarity == "p")
    assert "dtox" not in keys
