# SPDX-License-Identifier: Apache-2.0
"""Process descriptions of ``nfet_05v0`` and ``pfet_05v0`` for the TCAD MOS capacitors.

Each device has one TOML file, ``data/process/<device>.toml``, read with the standard
library's ``tomllib``. Every parameter has a value, a unit, a provenance tag (:data:`TAGS`)
and a public source. A source is a line of the PDK's public SPICE card
(``sm141064.ngspice:<line>``, a file with the sha256 given in the file's ``[card]`` table) or
an ``https://`` link. Values taken from the card cite its model line and the ``.param`` lines
of its ``.lib typical`` section that the card expression uses; :func:`eval_card_expr`
evaluates those expressions.

Exactly three parameters are free (:data:`TUNABLES`). They are the calibration tunables, and
their numeric bounds are written into the files before any fit. All the other parameters are
fixed. :meth:`ProcessDescription.with_values` returns a copy with new tunable values. The
files never hold calibrated values: those are written under ``results/tcad/calibration/``.

The upper bound of ``t_ox_eff_nm`` is TOXP + Δ. Δ is the charge-centroid allowance, computed
by :func:`centroid_allowance_nm` from the BSIM4 4.5.0 charge-thickness model (CTM,
``capMod=2``), evaluated with the card values. Poly depletion is never part of Δ: the
poly-gate region of the TCAD MOS capacitors simulates it.

This module is TCAD code. It is not one of the SPICE generator modules
(:data:`gf180tcad.reference.GENERATOR_MODULES`).
"""

from __future__ import annotations

import hashlib
import math
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from types import MappingProxyType

from gf180tcad.devices import SWEEPS
from gf180tcad.sandbox import REPO_ROOT

# Directory of the process files, ``data/process/<device>.toml``.
DATA_DIR = REPO_ROOT / "data" / "process"

# The devices that have a process file.
DEVICES = ("nfet_05v0", "pfet_05v0")

# Provenance tags. ``calibrated`` is set only by :meth:`ProcessDescription.with_values`.
TAGS = ("pdk-doc", "spice-card", "literature", "calibrated")

# What a parameter is for. ``tunable``: a calibration parameter, with bounds. ``bound-basis``: a
# card value that a tunable's start or bounds come from. ``process``: a fixed input of the TCAD
# structure. ``reference-bookkeeping``: how BSIM4 splits the SPICE Cgg into intrinsic and
# extrinsic parts, used only by the 1D comparison; not process data, and not part of the parameter
# budget.
ROLES = ("tunable", "bound-basis", "process", "reference-bookkeeping")

# The free parameters of every process file.
TUNABLES = ("t_ox_eff_nm", "n_ch_cm3", "dv_fb_v")

# File name of the PDK's ngspice model card, as cited in sources.
CARD_FILE = "sm141064.ngspice"

# The BSIM4 4.5.0 release from UC Berkeley: its user's manual and reference C code.
BSIM4_450_URL = "https://www.bsim.berkeley.edu/BSIM4/BSIM450.zip"

# The project-choice Δ, used only if the CTM equations could not be evaluated (they can).
FALLBACK_DELTA_NM = 0.5

# Gate biases of the SPICE ``cv`` sweep (V), over which Δ is maximised.
CV_VG = next(s for s in SWEEPS if s.kind == "cv").vgs

_SCHEMA = 1
_KEYS = {
    "value",
    "unit",
    "provenance",
    "source",
    "fixed",
    "role",
    "note",
    "bounds",
    "bounds_source",
    "card_key",
    "card_line",
    "card_params",
    "card_scale",
    "bsim_name",
}
_CARD_KEYS = {"file", "pdk_variant", "sha256", "model", "model_line", "tt_lib_line"}
_CARD_REF = re.compile(re.escape(CARD_FILE) + r":([1-9][0-9]*)")
_URL = re.compile(r"https://[^\s;]+")


@dataclass(frozen=True)
class Constants:
    """Physical constants of the plan's constants table (no DEVSIM ``simple_physics`` default).

    ``q_c`` and ``k_b_j_per_k`` are exact SI; ``eps0_f_per_cm`` is CODATA 2018; ``eps_si`` is
    Sze & Ng, *Physics of Semiconductor Devices*, 3rd ed., Appendix
    (https://doi.org/10.1002/0470068329), equal to the BSIM4 EPSRSUB default; ``t_k`` is the
    card's TNOM of 25 °C.
    """

    q_c: float = 1.602176634e-19
    k_b_j_per_k: float = 1.380649e-23
    eps0_f_per_cm: float = 8.8541878128e-14
    eps_si: float = 11.7
    t_k: float = 298.15

    @property
    def vt_v(self) -> float:
        """Thermal voltage k_B·T/q (V)."""
        return self.k_b_j_per_k * self.t_k / self.q_c


# The constants used by every TCAD calculation.
CONSTANTS = Constants()


# --- card expressions ------------------------------------------------------------------------

_NUM = r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?"
_TOKEN = re.compile(rf"\s*(?:(?P<num>-?{_NUM})|(?P<name>[A-Za-z_][A-Za-z0-9_]*)|(?P<op>[+*]))")


def _tokens(expr: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    pos = 0
    while pos < len(expr):
        if expr[pos:].strip() == "":
            break
        m = _TOKEN.match(expr, pos)
        if not m:
            raise ValueError(f"card expression {expr!r}: cannot parse at {expr[pos:]!r}")
        kind = m.lastgroup
        text = m.group(kind)
        if kind == "num" and text.startswith("-") and out:
            raise ValueError(f"card expression {expr!r}: a sign is allowed only at the start")
        out.append((kind, text))
        pos = m.end()
    return out


def card_expr_names(expr: str) -> frozenset[str]:
    """The parameter names used in a card expression."""
    return frozenset(t for k, t in _tokens(expr) if k == "name")


def eval_card_expr(expr: str, params: Mapping[str, float]) -> float:
    """Evaluate a card expression such as ``'1.52e-008+nfet_06v0_tox'``.

    Only numbers (a sign is allowed on the first one), ``+``, ``*`` (which binds tighter)
    and parameter names are accepted; anything else raises ``ValueError``, and an
    unknown parameter name raises ``KeyError``.
    """
    toks = _tokens(expr)
    if not toks:
        raise ValueError(f"card expression {expr!r} is empty")
    total = 0.0
    term: float | None = None
    expect_operand = True
    for kind, text in toks:
        if expect_operand:
            if kind == "op":
                raise ValueError(f"card expression {expr!r}: operand expected, got {text!r}")
            x = float(text) if kind == "num" else float(params[text])
            term = x if term is None else term * x
            expect_operand = False
        else:
            if kind != "op":
                raise ValueError(f"card expression {expr!r}: operator expected, got {text!r}")
            if text == "+":
                total += term
                term = None
            expect_operand = True
    if expect_operand:
        raise ValueError(f"card expression {expr!r} ends with an operator")
    return total + term


_ASSIGN = re.compile(r"(?:\+|\.param)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:'([^']*)'|(\S+))\s*")


def parse_card_assignment(line: str) -> tuple[str, str]:
    """``(key, expression)`` of a card line ``+ key=expr`` or ``.param key=expr``."""
    m = _ASSIGN.fullmatch(line.strip())
    if not m:
        raise ValueError(f"not a card assignment: {line!r}")
    return m.group(1), m.group(2) if m.group(2) is not None else m.group(3)


def sha256_hex(data: bytes) -> str:
    """Hex sha256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


# --- the data model --------------------------------------------------------------------------


@dataclass(frozen=True)
class CardRef:
    """The SPICE card the values come from: file, sha256, model and ``.lib typical`` lines."""

    file: str
    pdk_variant: str
    sha256: str
    model: str
    model_line: int
    tt_lib_line: int


@dataclass(frozen=True)
class Parameter:
    """One process parameter.

    ``card_line``/``card_key`` name the card line ``+ card_key=expr`` the value comes from and
    ``card_params`` the ``.param`` lines its expression uses; ``value`` is the expression times
    ``card_scale``. ``bsim_name`` is the BSIM4 parameter it sets (default ``card_key``), used
    by :meth:`ProcessDescription.card_values`.
    """

    name: str
    value: float
    unit: str
    provenance: str
    source: tuple[str, ...]
    fixed: bool
    role: str
    note: str
    bounds: tuple[float, float] | None = None
    bounds_source: str | None = None
    card_key: str | None = None
    card_line: int | None = None
    card_params: tuple[int, ...] = ()
    card_scale: float = 1.0
    bsim_name: str | None = None


@dataclass(frozen=True)
class ProcessDescription:
    """A loaded, validated process file (:func:`load`)."""

    device: str
    polarity: str
    card: CardRef
    params: Mapping[str, Parameter]

    def values(self) -> dict[str, float]:
        """Every parameter's value by name."""
        return {n: p.value for n, p in self.params.items()}

    def card_values(self) -> dict[str, float]:
        """The fixed parameters as BSIM4 card values (card units), plus ``type`` (+1/-1)."""
        out: dict[str, float] = {"type": 1.0 if self.polarity == "n" else -1.0}
        for p in self.params.values():
            name = p.bsim_name or p.card_key
            if p.fixed and name is not None:
                out[name] = p.value / p.card_scale
        return out

    def with_values(self, mapping: Mapping[str, float]) -> ProcessDescription:
        """A copy with tunables replaced (tagged ``calibrated``).

        Raises ``KeyError`` for an unknown name and ``ValueError`` for a fixed
        parameter or a value outside the bounds.
        """
        params = dict(self.params)
        for name, value in mapping.items():
            if name not in params:
                raise KeyError(f"{self.device}: no parameter {name!r}")
            p = params[name]
            if p.fixed:
                raise ValueError(f"{self.device}: {name} is fixed and cannot be changed")
            v = float(value)
            lo, hi = p.bounds
            if not (math.isfinite(v) and lo <= v <= hi):
                raise ValueError(f"{self.device}: {name}={v!r} is outside its bounds [{lo}, {hi}]")
            params[name] = replace(p, value=v, provenance="calibrated")
        return replace(self, params=MappingProxyType(params))


# --- loading ---------------------------------------------------------------------------------


def parse_source(source: str) -> tuple[str, ...]:
    """Split a ``"; "``-separated source into references; each is a card line or a link."""
    refs = tuple(s.strip() for s in source.split(";"))
    for ref in refs:
        if not (_CARD_REF.fullmatch(ref) or _URL.fullmatch(ref)):
            raise ValueError(f"source {ref!r} is neither {CARD_FILE}:<line> nor an https:// link")
    return refs


def _number(x: object, what: str) -> float:
    if isinstance(x, bool) or not isinstance(x, int | float) or not math.isfinite(x):
        raise ValueError(f"{what} must be a finite number, got {x!r}")
    return float(x)


def _text(x: object, what: str) -> str:
    if not isinstance(x, str) or not x.strip():
        raise ValueError(f"{what} must be a non-empty string, got {x!r}")
    return x


def _int(x: object, what: str) -> int:
    if isinstance(x, bool) or not isinstance(x, int) or x < 1:
        raise ValueError(f"{what} must be a positive integer, got {x!r}")
    return x


def _parameter(name: str, raw: Mapping) -> Parameter:
    unknown = set(raw) - _KEYS
    if unknown:
        raise ValueError(f"unknown keys {sorted(unknown)}")
    for key in ("value", "unit", "provenance", "source", "fixed", "role", "note"):
        if key not in raw:
            raise ValueError(f"missing {key!r}")
    provenance = raw["provenance"]
    if provenance not in TAGS:
        raise ValueError(f"provenance {provenance!r} is not one of {TAGS}")
    if provenance == "calibrated":
        raise ValueError("process files never hold calibrated values")
    fixed = raw["fixed"]
    if fixed is not True and fixed is not False:
        raise ValueError(f"fixed must be true or false, got {fixed!r}")
    role = raw["role"]
    if role not in ROLES:
        raise ValueError(f"role {role!r} is not one of {ROLES}")
    if (role == "tunable") == fixed:
        raise ValueError(f"role {role!r} does not match fixed={fixed}")
    p = Parameter(
        name=name,
        value=_number(raw["value"], "value"),
        unit=_text(raw["unit"], "unit"),
        provenance=provenance,
        source=parse_source(_text(raw["source"], "source")),
        fixed=fixed,
        role=role,
        note=_text(raw["note"], "note"),
    )
    if fixed:
        if "bounds" in raw or "bounds_source" in raw:
            raise ValueError("a fixed parameter has no bounds")
    else:
        if "bounds" not in raw or "bounds_source" not in raw:
            raise ValueError("a tunable needs bounds and bounds_source")
        b = raw["bounds"]
        if not isinstance(b, list) or len(b) != 2:
            raise ValueError(f"bounds must be [lo, hi], got {b!r}")
        lo, hi = (_number(x, "bound") for x in b)
        if not lo <= p.value <= hi:
            raise ValueError(f"start {p.value!r} is not within bounds [{lo}, {hi}]")
        p = replace(p, bounds=(lo, hi), bounds_source=_text(raw["bounds_source"], "bounds_source"))
    if ("card_key" in raw) != ("card_line" in raw):
        raise ValueError("card_key and card_line go together")
    if "card_line" in raw:
        line = _int(raw["card_line"], "card_line")
        lines = raw.get("card_params", [])
        if not isinstance(lines, list):
            raise ValueError(f"card_params must be a list, got {lines!r}")
        params = tuple(_int(n, "card_params entry") for n in lines)
        cited = {int(m.group(1)) for r in p.source if (m := _CARD_REF.fullmatch(r))}
        if not {line, *params} <= cited:
            raise ValueError(f"card lines {sorted({line, *params} - cited)} are not in source")
        p = replace(
            p,
            card_key=_text(raw["card_key"], "card_key"),
            card_line=line,
            card_params=params,
            card_scale=_number(raw.get("card_scale", 1.0), "card_scale"),
        )
    elif "card_params" in raw or "card_scale" in raw:
        raise ValueError("card_params and card_scale need card_line")
    if "bsim_name" in raw:
        p = replace(p, bsim_name=_text(raw["bsim_name"], "bsim_name"))
    return p


def load(device: str, data_dir: Path | None = None) -> ProcessDescription:
    """Read and validate ``<data_dir>/<device>.toml`` (default :data:`DATA_DIR`).

    Checks the provenance tags (no ``calibrated``), that every source is a card line or a
    link, that exactly :data:`TUNABLES` are free and have bounds with lo ≤ start ≤ hi, and
    that every cited card line of a card value is in its source.
    """
    if device not in DEVICES:
        raise ValueError(f"no process file for {device!r}; known: {DEVICES}")
    path = Path(data_dir or DATA_DIR) / f"{device}.toml"
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if set(raw) != {"schema", "device", "polarity", "card", "param"}:
        raise ValueError(f"{path}: top-level keys are {sorted(raw)}")
    if raw["schema"] != _SCHEMA or raw["device"] != device:
        raise ValueError(f"{path}: schema/device mismatch")
    if raw["polarity"] != device[0]:
        raise ValueError(f"{path}: polarity {raw['polarity']!r} does not match {device}")
    card = raw["card"]
    if set(card) != _CARD_KEYS:
        raise ValueError(f"{path}: [card] keys are {sorted(card)}")
    if not re.fullmatch(r"[0-9a-f]{64}", card["sha256"]):
        raise ValueError(f"{path}: [card] sha256 is not a hex digest")
    card_ref = CardRef(
        file=card["file"],
        pdk_variant=card["pdk_variant"],
        sha256=card["sha256"],
        model=card["model"],
        model_line=_int(card["model_line"], "model_line"),
        tt_lib_line=_int(card["tt_lib_line"], "tt_lib_line"),
    )
    params = {}
    for name, p in raw["param"].items():
        try:
            params[name] = _parameter(name, p)
        except ValueError as e:
            raise ValueError(f"{path}: parameter {name}: {e}") from None
    free = {n for n, p in params.items() if not p.fixed}
    if free != set(TUNABLES):
        raise ValueError(f"{path}: free parameters are {sorted(free)}, expected {TUNABLES}")
    return ProcessDescription(device, raw["polarity"], card_ref, MappingProxyType(params))


# --- the BSIM4 charge-thickness model (CTM) --------------------------------------------------
#
# Equation numbers are those of the BSIM4.5.0 MOSFET Model User's Manual (UC Berkeley, in
# BSIM4_450_URL, doc/BSIM450_Manu.tar), with two places where the manual's text and its own
# reference code (src/b4temp.c, src/b4ld.c of the same release) differ settled by the code:
#   - eq. (7.3.2) prints VFBeff in the exponent; b4ld.c uses Vfbzb. VFBeff equals Vgb
#     throughout accumulation (eq. 7.2.13), which would make X_DC bias independent there.
#   - "Ldebye" is not defined in the manual; b4temp.c:1111 uses sqrt(εsi·vt/(q·NDEP)).


def bsim4_ni_cm3(c: Constants = CONSTANTS) -> float:
    """BSIM4 intrinsic density at TNOM = ``c.t_k`` (eqs. 12.7.2 and 12.7.3)."""
    t = c.t_k
    eg0 = 1.16 - 7.02e-4 * t * t / (t + 1108.0)
    return (
        1.45e10 * (t / 300.15) * math.sqrt(t / 300.15) * math.exp(21.5565981 - eg0 / (2 * c.vt_v))
    )


def bsim4_phi_s_v(cv: Mapping[str, float], c: Constants = CONSTANTS) -> float:
    """Φs = 0.4 + vt·ln(NDEP/ni) + PHIN (eq. 2.2.7)."""
    return 0.4 + c.vt_v * math.log(cv["ndep"] / bsim4_ni_cm3(c)) + cv.get("phin", 0.0)


def bsim4_vfbzb_v(cv: Mapping[str, float], c: Constants = CONSTANTS) -> float:
    """Vfbzb = type·VTH0 − Φs − K1·√Φs (eq. 7.2.14), long-channel, Vbs = 0."""
    phi = bsim4_phi_s_v(cv, c)
    return cv["type"] * cv["vth0"] - phi - cv["k1"] * math.sqrt(phi)


def bsim4_vfb_v(cv: Mapping[str, float], c: Constants = CONSTANTS) -> float:
    """VFB: the card's ``vfb`` if given, else VTH0 − Φs − K1·√Φs (Appendix A, note 4)."""
    if "vfb" in cv:
        return cv["vfb"]
    phi = bsim4_phi_s_v(cv, c)
    return cv["type"] * cv["vth0"] - phi - cv["k1"] * math.sqrt(phi)


def ctm_x_dc_acc_m(vg: float, cv: Mapping[str, float], c: Constants = CONSTANTS) -> float:
    """Accumulation/depletion charge thickness X_DC (m) at gate-body bias ``vg`` (Vbs = 0).

    Eqs. (7.3.2) and (7.3.3): X_DC = Ldebye/3·exp(ACDE·(NDEP/2e16)^−0.25·E), with E the
    field (type·vg − Vfbzb)/TOXP in MV/cm, smoothed to stay below Xmax = Ldebye/3 with
    δx = 1e-3·TOXE. The gate bias is used for Vgse (no poly depletion: an upper bound).
    """
    eps_si_f_per_m = c.eps_si * c.eps0_f_per_cm * 100
    ldebye = math.sqrt(eps_si_f_per_m * c.vt_v / (c.q_c * cv["ndep"] * 1e6))
    x_max = ldebye / 3
    field_mv_per_cm = (cv["type"] * vg - bsim4_vfbzb_v(cv, c)) / (cv["toxp"] * 1e8)
    x_dc = x_max * math.exp(cv["acde"] * (cv["ndep"] / 2e16) ** -0.25 * field_mv_per_cm)
    dx = 1e-3 * cv["toxe"]
    x0 = x_max - x_dc - dx
    return x_max - 0.5 * (x0 + math.sqrt(x0 * x0 + 4 * dx * x_max))


def ctm_x_dc_inv_sup_m(cv: Mapping[str, float], c: Constants = CONSTANTS) -> float:
    """Supremum of the inversion charge thickness X_DC (m), eq. (7.3.4).

    X_DC = 1.9 nm/(1 + ((Vgsteff + 4(VTH0 − VFB − Φs))/(2·TOXP))^0.7) falls with Vgsteff > 0,
    so its supremum is the Vgsteff → 0 value. The 4(VTH0 − VFB − Φs) term is clamped at 0, as
    in b4temp.c. MOIN does not enter X_DC; it enters only φδ (eq. 7.3.5).
    """
    t3 = cv["type"] * cv["vth0"] - bsim4_vfb_v(cv, c) - bsim4_phi_s_v(cv, c)
    vtfbphi2 = max(4.0 * t3, 0.0)
    return 1.9e-9 / (1 + (vtfbphi2 / (2 * cv["toxp"] * 1e8)) ** 0.7)


@dataclass(frozen=True)
class Centroid:
    """The CTM charge thickness over a gate sweep (:func:`centroid`)."""

    x_dc_acc_max_m: float
    vg_at_max_v: float
    x_dc_inv_sup_m: float
    x_dc_max_m: float
    delta_nm: float


def round_up_nm(x_nm: float) -> float:
    """Round up to 0.01 nm."""
    return float(Decimal(repr(x_nm)).quantize(Decimal("0.01"), rounding=ROUND_CEILING))


def centroid(
    cv: Mapping[str, float], c: Constants = CONSTANTS, vg: Iterable[float] = CV_VG
) -> Centroid:
    """X_DC over the gate biases ``vg`` and Δ = max X_DC·EPSROX/εsi, rounded up to 0.01 nm."""
    acc = [(ctm_x_dc_acc_m(v, cv, c), v) for v in vg]
    x_acc, v_max = max(acc)
    x_inv = ctm_x_dc_inv_sup_m(cv, c)
    x = max(x_acc, x_inv)
    return Centroid(x_acc, v_max, x_inv, x, round_up_nm(x * cv["epsrox"] / c.eps_si * 1e9))


def centroid_allowance_nm(
    card_values: Mapping[str, float], constants: Constants = CONSTANTS, vg: Iterable[float] = CV_VG
) -> float:
    """Δ (nm): the CTM charge-centroid allowance added to TOXP for the ``t_ox_eff`` bound."""
    return centroid(card_values, constants, vg).delta_nm


def k1_doping_cm3(cv: Mapping[str, float], c: Constants = CONSTANTS) -> float:
    """The doping K1 implies: N = (K1·Cox(TOXE))²/(2·q·εsi·ε0), cm⁻³ (BSIM4 K1 definition)."""
    cox = cv["epsrox"] * c.eps0_f_per_cm / (cv["toxe"] * 100)
    return (cv["k1"] * cox) ** 2 / (2 * c.q_c * c.eps_si * c.eps0_f_per_cm)


def cf_default_f_per_m(cv: Mapping[str, float], c: Constants = CONSTANTS) -> float:
    """The BSIM4 default CF = 2·EPSROX·ε0/π·ln(1 + 4e-7/TOXE), F/m (eq. 7.5.1)."""
    return 2 * cv["epsrox"] * c.eps0_f_per_cm * 100 / math.pi * math.log(1 + 4e-7 / cv["toxe"])
