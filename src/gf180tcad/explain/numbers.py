# SPDX-License-Identifier: Apache-2.0
"""The named numbers of the explainer pages, each read from a committed file or computed.

A page writes ``{{ x_<name> }}`` and the docs build prints the value: ``docs/conf.py`` merges
:func:`substitutions` into ``myst_substitutions`` when it is read. Every entry of
:data:`REGISTRY` names its kind (:data:`KINDS`):

- ``committed``: a file under ``data/`` or ``results/``, read by a :class:`gf180tcad.quantity.Selector`;
- ``textbook``: a value of ``data/render/display.toml`` (or ``data/explain/textbook.toml``, in
  the same layout), whose ``sources`` table cites an anchor of ``docs/limitations/literature.md``
  (:func:`citation`);
- ``idealised``: a formula of :mod:`gf180tcad.explain.idealised` (or a shared one of
  :mod:`gf180tcad.derive`) over other entries, its ``inputs``.

The page sentence says which kind a value is; ``x_<name>_label`` gives the words
(:data:`LABELS`). A value is shown to ``digits`` significant digits in ``unit``, after
multiplying by ``factor`` (1000 shows a value in V as mV).

:data:`WORDS` holds the words a page prints from a committed file, the verdicts of the
calibration files, so a new verdict changes the page's sentence (:func:`word`).

:func:`two_d_cells` reads every 2D cell with a verdict from the validation files
(``results/tcad/validation/*.json``), so the page's table of them (:func:`two_d_table`) and
its sentence on the Disagree cells (:func:`two_d_disagree`) grow with each new cell.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from gf180tcad import derive, quantity
from gf180tcad.explain import idealised

ROOT = Path(__file__).resolve().parents[3]
KINDS = ("committed", "idealised", "textbook")
LABELS = {
    "committed": "this repo's committed value",
    "idealised": "idealised example",
    "textbook": "textbook value",
}
DISPLAY = "data/render/display.toml"
TEXTBOOK = "data/explain/textbook.toml"
#: The model card's selector values the pages print, each with its card line.
MODEL_CARD = "data/explain/model_card.toml"


@dataclass(frozen=True)
class Number:
    """One registry entry (see the module docstring)."""

    name: str
    kind: str
    unit: str
    digits: int
    source: str | None = None
    key: dict | None = None
    formula: str | None = None
    inputs: tuple[str, ...] = ()
    factor: float = 1.0


def _meta(device: str, params: str = "calibrated") -> str:
    return f"results/tcad/moscap1d/{device}/{params}/per_area.meta.json"


def _proc(device: str) -> str:
    return f"data/process/{device}.toml"


_CM3 = "cm⁻³"
_CAP = "fF/µm²"
_RESULT = "results/tcad/calibration/nfet_05v0.result.json"
_CELL = "results/tcad/moscap2d/nfet_05v0/calibrated/w10p0_l0p70/cv.meta.json"
_SPICE_L10 = "results/spice/ngspice/typical/nfet_05v0/w10p0_l10p00/metrics.json"
_L10 = ("per_geometry", "w10p0_l10p00")
_ENTRIES = (
    Number("n_i_tcad", "committed", _CM3, 3, _meta("nfet_05v0"), {"json": ["constants", "n_i_cm3"]}),
    Number("t_tcad", "committed", "K", 5, _meta("nfet_05v0"), {"json": ["constants", "t_k"]}),
    Number("ndep_nfet", "committed", _CM3, 2, _proc("nfet_05v0"), {"toml": ["param", "ndep_cm3", "value"]}),
    Number("n_ch_nfet_cal", "committed", _CM3, 3, _meta("nfet_05v0"), {"json": ["stack", "n_ch_cm3"]}),
    Number("n_ch_pfet_cal", "committed", _CM3, 3, _meta("pfet_05v0"), {"json": ["stack", "n_ch_cm3"]}),
    Number("ngate_nfet", "committed", _CM3, 1, _proc("nfet_05v0"), {"toml": ["param", "ngate_cm3", "value"]}),
    Number("sd_peak_nfet", "committed", _CM3, 1, _proc("nfet_05v0"), {"toml": ["param", "sd_peak_cm3", "value"]}),
    Number(
        "n_minority_nfet", "idealised", _CM3, 3,
        formula="mass_action", inputs=("n_i_tcad", "n_ch_nfet_cal"),
    ),
    Number("dv_fb_nfet_cal", "committed", "V", 3, "results/tcad/calibration/nfet_05v0.json", {"json": ["values", "dv_fb_v"]}),
    # The gate oxide and the poly-silicon gate (oxide-and-poly.md).
    Number("ngate_pfet", "committed", _CM3, 2, _proc("pfet_05v0"), {"toml": ["param", "ngate_cm3", "value"]}),
    Number("toxe_nfet", "committed", "nm", 3, _proc("nfet_05v0"), {"toml": ["param", "toxe_nm", "value"]}),
    Number("toxp_nfet", "committed", "nm", 3, _proc("nfet_05v0"), {"toml": ["param", "toxp_nm", "value"]}),
    Number("epsrox_nfet", "committed", "", 2, _proc("nfet_05v0"), {"toml": ["param", "epsrox", "value"]}),
    Number("delta_nfet", "committed", "nm", 2, _proc("nfet_05v0"), {"toml": ["centroid_allowance", "delta_nm"]}),
    Number("t_ox_upper_nfet", "committed", "nm", 4, _RESULT, {"json": ["bounds", "t_ox_eff_nm", 1]}),
    Number("t_ox_nfet_cal", "committed", "nm", 4, _meta("nfet_05v0"), {"json": ["stack", "t_ox_nm"]}),
    Number("eps_ox_nfet_cal", "committed", "", 2, _meta("nfet_05v0"), {"json": ["stack", "eps_ox"]}),
    Number("eps0_tcad", "committed", "F/cm", 5, _meta("nfet_05v0"), {"json": ["constants", "eps0_f_per_cm"]}),
    Number("poly_nfet", "committed", "µm", 1, _meta("nfet_05v0"), {"json": ["stack", "poly_um"]}),
    Number(
        "cox_toxe_nfet", "idealised", _CAP, 3,
        formula="oxide_capacitance", inputs=("epsrox_nfet", "eps0_tcad", "toxe_nfet"),
    ),
    Number(
        "cox_nfet_cal", "idealised", _CAP, 3,
        formula="oxide_capacitance", inputs=("eps_ox_nfet_cal", "eps0_tcad", "t_ox_nfet_cal"),
    ),
    Number("cox_check_nfet", "committed", _CAP, 3, _RESULT, {"json": ["cox_check", "c_ox_ff_per_um2"]}),
    Number("cox_spec_min", "committed", _CAP, 2, _RESULT, {"json": ["cox_check", "spec", "min"]}),
    Number("cox_spec_max", "committed", _CAP, 2, _RESULT, {"json": ["cox_check", "spec", "max"]}),
    Number("c_acc_nfet_cal", "committed", _CAP, 3, _RESULT, {"json": ["cox_check", "c_per_area_acc_ff_per_um2"]}),
    Number("c_inv_nfet_cal", "committed", _CAP, 3, _RESULT, {"json": ["cox_check", "c_per_area_inv_ff_per_um2"]}),
    # Energy bands and the Fermi level (bands-and-fermi-level.md).
    Number("vt_tcad", "committed", "V", 3, _meta("nfet_05v0"), {"json": ["constants", "vt_v"]}),
    Number("band_gap_si", "textbook", "eV", 3, DISPLAY, {"toml": ["silicon", "band_gap_ev"]}),
    Number(
        "fermi_gate_nfet", "idealised", "eV", 3,
        formula="boltzmann_fermi", inputs=("ngate_nfet", "n_i_tcad", "vt_tcad"),
    ),
    # Below the middle of the gap: the page prints the distance, so the factor is -1.
    Number(
        "fermi_body_nfet", "idealised", "eV", 3,
        formula="boltzmann_fermi", inputs=("n_minority_nfet", "n_i_tcad", "vt_tcad"), factor=-1.0,
    ),
    # The pn junction (pn-junction.md).
    Number("eps_si_tcad", "committed", "", 3, _meta("nfet_05v0"), {"json": ["constants", "eps_si"]}),
    Number("q_tcad", "committed", "C", 5, _meta("nfet_05v0"), {"json": ["constants", "q_c"]}),
    Number("xj_nfet", "committed", "µm", 2, _proc("nfet_05v0"), {"toml": ["param", "xj_um", "value"]}),
    Number(
        "vbi_nfet", "idealised", "V", 3,
        formula="built_in_potential", inputs=("n_ch_nfet_cal", "sd_peak_nfet", "n_i_tcad", "vt_tcad"),
    ),
    # depletion_width is in cm; the page prints µm.
    Number(
        "w_dep_nfet", "idealised", "µm", 3,
        formula="depletion_width",
        inputs=("n_ch_nfet_cal", "sd_peak_nfet", "vbi_nfet", "eps_si_tcad", "eps0_tcad", "q_tcad"),
        factor=1e4,
    ),
    # The transistor's parts (transistor-parts.md): the calibrated nfet 2D cell w10p0_l0p70.
    Number("l_cell", "committed", "µm", 1, _CELL, {"json": ["geometry", "l_um"]}),
    Number("w_cell", "committed", "µm", 2, _CELL, {"json": ["geometry", "w_um"]}),
    Number("t_ox_cell", "committed", "nm", 4, _CELL, {"json": ["meshed_t_ox_nm"]}),
    Number("node_count_cell", "committed", "", 3, _CELL, {"json": ["node_count"]}),
    # F/m on the card; the page prints fF/µm (1e15 fF/F over 1e6 µm/m).
    Number("cgdl_nfet", "committed", "fF/µm", 2, _proc("nfet_05v0"), {"toml": ["param", "cgdl_f_per_m", "value"]}, factor=1e9),
    # The MOS capacitor (mos-capacitor.md): the SPICE model and the calibration at w10p0_l10p00.
    Number("cgg_acc_l10", "committed", "fF", 3, _SPICE_L10, {"json": ["metrics", "cgg_acc_ff"]}),
    Number("cgg_inv_l10", "committed", "fF", 3, _SPICE_L10, {"json": ["metrics", "cgg_inv_ff"]}),
    # Fractions in the file; the page prints per cent.
    Number("plateau_acc_l10", "committed", "%", 2, _RESULT, {"json": [*_L10, "metrics", "plateau_acc_max_rel"]}, factor=100.0),
    Number("plateau_inv_l10", "committed", "%", 2, _RESULT, {"json": [*_L10, "metrics", "plateau_inv_max_rel"]}, factor=100.0),
    Number("plateau_tol_l10", "committed", "%", 1, _RESULT, {"json": [*_L10, "verdicts", "plateau_acc", "tolerance"]}, factor=100.0),
    # The regions (accumulation-depletion-inversion.md): the calibration's marks on the SPICE
    # curve and the crossings of both curves at w10p0_l10p00. The nfet's u is its gate voltage.
    Number("u_fb_l10", "committed", "V", 3, _RESULT, {"json": [*_L10, "spice_regions", "u_fb"]}),
    Number("u_t_l10", "committed", "V", 3, _RESULT, {"json": [*_L10, "spice_regions", "u_t"]}),
    Number("u_min_l10", "committed", "V", 2, _RESULT, {"json": [*_L10, "spice_regions", "u_min"]}),
    Number("c_min_l10", "committed", "fF", 3, _RESULT, {"json": [*_L10, "spice_regions", "c_min"]}),
    Number("u_dep_spice_l10", "committed", "V", 3, _RESULT, {"json": [*_L10, "spice_regions", "u_dep"]}),
    Number("u_inv_spice_l10", "committed", "V", 3, _RESULT, {"json": [*_L10, "spice_regions", "u_inv"]}),
    Number("u_dep_tcad_l10", "committed", "V", 3, _RESULT, {"json": [*_L10, "tcad_crossings", "u_dep"]}),
    Number("u_inv_tcad_l10", "committed", "V", 3, _RESULT, {"json": [*_L10, "tcad_crossings", "u_inv"]}),
    # V in the file; the page prints mV.
    Number("dv_tol_l10", "committed", "mV", 2, _RESULT, {"json": [*_L10, "verdicts", "dv_dep", "tolerance_v"]}, factor=1000.0),
    Number(
        "v_fb_nfet", "idealised", "V", 3,
        formula="flat_band", inputs=("n_ch_nfet_cal", "ngate_nfet", "n_i_tcad", "vt_tcad"),
    ),
    Number(
        "v_t_nfet", "idealised", "V", 3,
        formula="threshold",
        inputs=("n_ch_nfet_cal", "n_i_tcad", "vt_tcad", "v_fb_nfet", "eps_si_tcad", "eps0_tcad",
                "q_tcad", "cox_nfet_cal"),
    ),
    # What sets each part of the C-V curve (cv-curve.md): the calibration's start values of the
    # three tunables, as the result file records them, and the fit's errors at w10p0_l10p00.
    Number("t_ox_nfet_start", "committed", "nm", 3, _RESULT, {"json": ["start", "t_ox_eff_nm"]}),
    Number("n_ch_nfet_start", "committed", _CM3, 2, _RESULT, {"json": ["start", "n_ch_cm3"]}),
    Number("dv_fb_nfet_start", "committed", "V", 1, _RESULT, {"json": ["start", "dv_fb_v"]}),
    # V in the file; the page prints mV. Simulated crossing minus the SPICE one.
    Number("dv_dep_l10", "committed", "mV", 2, _RESULT, {"json": [*_L10, "metrics", "dv_dep_v"]}, factor=1000.0),
    Number("dv_inv_l10", "committed", "mV", 2, _RESULT, {"json": [*_L10, "metrics", "dv_inv_v"]}, factor=1000.0),
    # A fraction in the file; the page prints per cent.
    Number("depletion_l10", "committed", "%", 2, _RESULT, {"json": [*_L10, "metrics", "depletion_max_rel"]}, factor=100.0),
    # The card's non-quasi-static model selectors (BSIM4 manual section 8.1), bin nfet_06v0.0;
    # tests/test_explained.py checks that every bin of the nfet has the same values.
    Number("acnqsmod_nfet", "committed", "", 1, MODEL_CARD, {"toml": ["nfet_05v0", "nfet_06v0.0", "acnqsmod", "value"]}),
    Number("trnqsmod_nfet", "committed", "", 1, MODEL_CARD, {"toml": ["nfet_05v0", "nfet_06v0.0", "trnqsmod", "value"]}),
)  # fmt: skip
REGISTRY: dict[str, Number] = {n.name: n for n in _ENTRIES}


@dataclass(frozen=True)
class Word:
    """A word a page prints from a committed file, read by key and never typed: a verdict."""

    name: str
    source: str
    key: dict


_WORDS = (
    Word("verdict_nfet_1d", _RESULT, {"json": ["verdict"]}),
    Word("verdict_pfet_1d", "results/tcad/calibration/pfet_05v0.result.json", {"json": ["verdict"]}),
    Word("verdict_dv_dep_l10", _RESULT, {"json": [*_L10, "verdicts", "dv_dep", "verdict"]}),
    Word("verdict_dv_inv_l10", _RESULT, {"json": [*_L10, "verdicts", "dv_inv", "verdict"]}),
)  # fmt: skip
#: The verdict words of the pages, by name (see :class:`Word`).
WORDS: dict[str, Word] = {w.name: w for w in _WORDS}


def word(name: str, root: Path = ROOT) -> str:
    """The word entry ``name`` reads from its file under ``root`` (a copy of the repo in tests)."""
    w = WORDS[name]
    v = quantity.read(quantity.Selector.from_dict(w.key), Path(root) / w.source)
    if not isinstance(v, str) or not v:
        raise TypeError(f"{name}: {w.source} {w.key} holds {v!r}, not a word")
    return v


#: The validation files of the 2D cells, relative to the repo root (:func:`two_d_cells`).
VALIDATION = "results/tcad/validation"

#: The checks of a validated cell (``verdicts`` of a ``two_d`` entry), in plain words
#: (``docs/comparison/cv-agreement.md``, "The agreement metric"). The checks run in
#: u = polarity × Vg, so each side is named for the nfet and the pfet, whose signs are reversed.
#: Both crossings are of one level, (C_min + C_acc)/2, each curve of its own
#: (:func:`gf180tcad.calibrate.cv.crossings`), which
#: ``docs/explained/accumulation-depletion-inversion.md`` names the halfway level: midway between
#: the curve's own minimum and accumulation flat part, on either side of the dip.
CHECKS = {
    "plateau_acc": "the flat part on the nfet's negative side, the pfet's positive side",
    "plateau_inv": "the flat part on the nfet's positive side, the pfet's negative side",
    "dv_dep": "the halfway-level crossing on the nfet's negative side, the pfet's positive side",
    "dv_inv": "the halfway-level crossing on the nfet's positive side, the pfet's negative side",
}


@dataclass(frozen=True)
class Cell:
    """One 2D cell with a verdict in a validation file; ``failing``: its Disagree checks."""

    device: str
    geometry_id: str
    w_um: float
    l_um: float
    verdict: str
    failing: tuple[str, ...]


def two_d_cells(root: Path = ROOT) -> list[Cell]:
    """Every ``two_d`` entry with a verdict in ``results/tcad/validation/*.json`` under ``root``,
    by device, then gate width, then gate length. Entries without one ("not run") are left out."""
    cells = []
    for path in sorted((Path(root) / VALIDATION).glob("*.json")):
        doc = json.loads(path.read_text("utf-8"))
        if "two_d" not in doc:  # provenance.json
            continue
        for gid, e in doc["two_d"].items():
            if e.get("verdict") is None:
                continue
            failing = tuple(k for k, v in e["verdicts"].items() if v["verdict"] == "Disagree")
            unknown = [k for k in e["verdicts"] if k not in CHECKS]
            if unknown:
                raise KeyError(f"{path.name} {gid}: checks {unknown} have no plain words in CHECKS")
            g = e["geometry"]
            cells.append(Cell(doc["device"], gid, g["w_um"], g["l_um"], e["verdict"], failing))
    return sorted(cells, key=lambda c: (c.device, c.w_um, c.l_um))


def _um(v: float) -> str:
    return f"{v:g} µm"


def two_d_table(root: Path = ROOT) -> str:
    """A Markdown table of :func:`two_d_cells`: transistor, gate width, gate length, verdict."""
    rows = ["| Transistor | Gate width | Gate length | Verdict |", "|---|---|---|---|"]
    rows += [
        f"| {{term}}`{c.device}` | {_um(c.w_um)} | {_um(c.l_um)} | {{term}}`{c.verdict}` |"
        for c in two_d_cells(root)
    ]
    return "\n".join(rows)


def two_d_disagree(root: Path = ROOT) -> str:
    """A clause on what the Disagree cells of :func:`two_d_cells` fail on, from their checks."""
    bad = [c for c in two_d_cells(root) if c.verdict == "Disagree"]
    if not bad:
        return "No 2D cell is Disagree"
    failing = sorted({k for c in bad for k in c.failing}, key=list(CHECKS).index)
    if len(failing) == 1:
        return f"Every Disagree cell fails only one check: {CHECKS[failing[0]]}"
    return "The Disagree cells fail on " + "; and on ".join(CHECKS[k] for k in failing)


def counts(root: Path = ROOT) -> dict[str, int]:
    """Counts a page prints: ``corner_count``, the SPICE corners of
    :data:`gf180tcad.devices.CORNERS`; ``fit_length_count``, the gate lengths of the nfet
    calibration's fit (``per_geometry`` of its result file under ``root``)."""
    from gf180tcad.devices import CORNERS

    fit = json.loads((Path(root) / _RESULT).read_text("utf-8"))["per_geometry"]
    lengths = {g["geometry"]["l_um"] for g in fit.values()}
    return {"corner_count": len(CORNERS), "fit_length_count": len(lengths)}


def _formula(name: str):
    if name in idealised.FORMULAS:
        return idealised.FORMULAS[name]
    return derive.FORMULAS[name]


@cache
def value(name: str) -> float:
    """The value of entry ``name`` (before :attr:`Number.factor`)."""
    n = REGISTRY[name]
    if n.kind == "idealised":
        f = _formula(n.formula)
        return float(f.fn(*(value(i) for i in n.inputs)))
    sel = quantity.Selector.from_dict(n.key)
    return float(quantity.read(sel, ROOT / n.source))


def citation(name: str) -> str:
    """The literature source of a ``textbook`` entry: its file's ``sources`` entry."""
    n = REGISTRY[name]
    if n.kind != "textbook":
        raise ValueError(f"{name} is a {n.kind} number, not a textbook value")
    *table, key = n.key["toml"]
    sel = quantity.Selector.from_dict({"toml": [*table, "sources", key]})
    return quantity.read(sel, ROOT / n.source)


_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


#: The non-breaking space (U+00A0) that joins a value to its unit and the parts of "a × 10ⁿ"
#: (issue #119).
NBSP = "\u00a0"
#: The word joiner (U+2060) put after the "/" of a compound unit such as fF/µm², so the line
#: never breaks at the slash (issue #119).
WORD_JOINER = "\u2060"


def format_value(v: float, digits: int, unit: str) -> str:
    """``v`` to ``digits`` significant digits with its unit: plain from 0.001 to 9999, else as
    a mantissa times a power of ten; a typographic minus sign; no space when ``unit`` is
    empty (a pure number). The value and its unit are joined by a non-breaking space
    (``NBSP``) and a "/" in the unit is followed by a word joiner (``WORD_JOINER``),
    so a page never breaks a number from its unit across lines."""
    if not math.isfinite(v):
        raise ValueError(f"{v!r} is not a finite number")
    sign = "−" if v < 0 else ""
    mant, exp = f"{abs(v):.{digits - 1}e}".split("e")
    e = int(exp)
    if -3 <= e < 4:
        body = f"{abs(v):.{max(digits - 1 - e, 0)}f}"
    else:
        body = f"{mant}{NBSP}×{NBSP}10{str(e).translate(_SUP)}"
    unit = unit.replace("/", "/" + WORD_JOINER)
    return f"{sign}{body}{NBSP}{unit}" if unit else f"{sign}{body}"


def text(name: str) -> str:
    """The value of entry ``name`` as a page prints it."""
    n = REGISTRY[name]
    return format_value(value(name) * n.factor, n.digits, n.unit)


def substitutions() -> dict[str, str]:
    """``{"x_<name>": text, "x_<name>_label": label}`` for every entry, and ``{"x_<name>":
    word}`` for every :data:`WORDS` entry, and the 2D cells' table and Disagree clause
    (``x_two_d_table``, ``x_two_d_disagree``) and the :func:`counts`, for MyST."""
    out: dict[str, str] = {}
    for name, n in REGISTRY.items():
        out[f"x_{name}"] = text(name)
        out[f"x_{name}_label"] = LABELS[n.kind]
    for name in WORDS:
        out[f"x_{name}"] = word(name)
    out.update({f"x_{k}": str(v) for k, v in counts().items()})
    out["x_two_d_table"] = two_d_table()
    out["x_two_d_disagree"] = two_d_disagree()
    return out
