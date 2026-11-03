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

The calibration page's tables are written from the calibration result files and the process
files: the fitted numbers within their limits (:func:`fit_table`), where each start and limit
comes from (:func:`limit_kinds_table`), the :term:`SPICE` :term:`corner` spread (:func:`corner_table`), the
fit's verdicts (:func:`fit_verdict_table`) and, from the corner summaries, each fitted number's
lowest and highest value over the corners and its spread (:func:`corner_bounds_table`).
"""

from __future__ import annotations

import json
import math
import tomllib
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
    """Counts a page prints: ``corner_count``, the :term:`SPICE` :term:`corners <corner>` of
    :data:`gf180tcad.devices.CORNERS`; ``fit_length_count``, the gate lengths of the nfet
    calibration's fit (``per_geometry`` of its result file under ``root``); ``budget`` and
    ``budget_used``, the parameter budget of each transistor and the part its fit uses (the
    same in both result files, else ValueError); ``nfev_nfet`` and ``nfev_pfet``, the
    evaluations each fit counted (``optimiser.nfev``)."""
    from gf180tcad.devices import CORNERS

    fit = json.loads((Path(root) / _RESULT).read_text("utf-8"))["per_geometry"]
    lengths = {g["geometry"]["l_um"] for g in fit.values()}
    docs = {d: _fit_doc(d, root) for d in FITS}
    budgets = {(doc["budget"], doc["budget_used"]) for doc in docs.values()}
    if len(budgets) != 1:
        raise ValueError(f"the transistors' budgets differ: {sorted(budgets)}")
    ((budget, used),) = budgets
    return {
        "corner_count": len(CORNERS),
        "fit_length_count": len(lengths),
        "budget": budget,
        "budget_used": used,
        "nfev_nfet": docs["nfet_05v0"]["optimiser"]["nfev"],
        "nfev_pfet": docs["pfet_05v0"]["optimiser"]["nfev"],
    }


# --- the calibration page (calibration.md) ---------------------------------------------------

#: The calibration's result files, by transistor, relative to the repo root.
FITS = {d: f"results/tcad/calibration/{d}.result.json" for d in ("nfet_05v0", "pfet_05v0")}

#: The three numbers the calibration fits, in the order of a result file's ``params``: the words
#: a page names each by, its unit, and the most significant digits it is printed with.
TUNABLES = {
    "t_ox_eff_nm": ("Oxide thickness", "nm", 4),
    "n_ch_cm3": ("Body doping", _CM3, 3),
    "dv_fb_v": ("Gate voltage shift", "V", 3),
}

#: The kinds of a start value or limit in a process file (``start_kind``, ``bounds_kind``;
#: :data:`gf180tcad.tcad.process.KINDS`), in plain words.
KIND_WORDS = {
    "card": "model card",
    "derived": "derived from the model card",
    "project-choice": "project choice",
}


def shortest(v: float, unit: str, most: int) -> str:
    """``v`` with the fewest significant digits (up to ``most``) that print the same value as
    ``most`` digits do: 0.2 V, not 0.200 V (:func:`format_value`)."""
    target = float(f"{v:.{most - 1}e}")
    for d in range(1, most + 1):
        if float(f"{v:.{d - 1}e}") == target:
            return format_value(v, d, unit)
    return format_value(v, most, unit)


@dataclass(frozen=True)
class Fit:
    """One fitted number of one transistor: its limits, start and fitted value (its unit)."""

    device: str
    name: str
    lower: float
    start: float
    fitted: float
    upper: float


def _fit_doc(device: str, root: Path) -> dict:
    doc = json.loads((Path(root) / FITS[device]).read_text("utf-8"))
    if doc["params"] != list(TUNABLES):
        raise KeyError(f"{FITS[device]}: params {doc['params']} are not {list(TUNABLES)}")
    return doc


def fits(device: str, root: Path = ROOT) -> list[Fit]:
    """The limits (``bounds``), start (``start``) and fitted value (``values``) of each of
    :data:`TUNABLES`, read from the result file of ``device`` under ``root``."""
    doc = _fit_doc(device, root)
    out = []
    for name in TUNABLES:
        lo, hi = doc["bounds"][name]
        out.append(Fit(device, name, lo, doc["start"][name], doc["values"][name], hi))
    return out


def fit_record(device: str, gid: str, root: Path = ROOT) -> dict:
    """The ``per_geometry`` entry ``gid`` of the result file of ``device`` under ``root``."""
    return _fit_doc(device, root)["per_geometry"][gid]


def fit_geometries(device: str, root: Path = ROOT) -> dict[str, float]:
    """The gate length (µm) of each geometry of the fit of ``device``, by geometry id."""
    return {g: e["geometry"]["l_um"] for g, e in _fit_doc(device, root)["per_geometry"].items()}


def spice_edges(device: str, root: Path = ROOT) -> dict[str, float]:
    """The SPICE accumulation-to-depletion edge ``u_dep`` (V, u = polarity × Vg) at the
    :term:`typical corner` of each geometry of the fit of ``device``, by geometry id: the
    ``spice_regions`` of its result file."""
    doc = _fit_doc(device, root)["per_geometry"]
    return {g: e["spice_regions"]["u_dep"] for g, e in doc.items()}


def fit_table(device: str, root: Path = ROOT) -> str:
    """A Markdown table of :func:`fits` of ``device``: one row per fitted number, its lower
    limit, start, fitted value and upper limit. The unit is in the row label and the cells hold
    the values alone, so the five columns fit a phone's width."""
    rows = ["| Number | Lower limit | Start | Fitted | Upper limit |", "|---|---|---|---|---|"]
    for f in fits(device, root):
        words, unit, most = TUNABLES[f.name]
        cells = (shortest(v, "", most) for v in (f.lower, f.start, f.fitted, f.upper))
        rows.append(f"| {words} ({unit}) | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _process(device: str, root: Path) -> dict:
    return tomllib.loads((Path(root) / _proc(device)).read_text("utf-8"))


def limit_kinds(root: Path = ROOT) -> dict[str, tuple[str, str, str]]:
    """The kind of the start, lower limit and upper limit of each of :data:`TUNABLES`, read from
    the process files under ``root``; ValueError when the two transistors' kinds differ."""
    out: dict[str, tuple[str, str, str]] = {}
    for device in FITS:
        params = _process(device, root)["param"]
        kinds = {n: (params[n]["start_kind"], *params[n]["bounds_kind"]) for n in TUNABLES}
        if out and kinds != out:
            raise ValueError(f"{device}: the kinds of the starts and limits differ: {kinds} {out}")
        out = kinds
    return out


def limit_kinds_table(root: Path = ROOT) -> str:
    """A Markdown table of :func:`limit_kinds` in :data:`KIND_WORDS`: where each fitted number's
    start and limits come from, the same for both transistors."""
    rows = ["| Number | Start | Lower limit | Upper limit |", "|---|---|---|---|"]
    for name, kinds in limit_kinds(root).items():
        rows.append(f"| {TUNABLES[name][0]} | " + " | ".join(KIND_WORDS[k] for k in kinds) + " |")
    return "\n".join(rows)


def bound_hits(root: Path = ROOT) -> str:
    """A sentence on the fitted values that sit on a limit (``bound_hits`` of the result files)."""
    hits = [
        f"the {TUNABLES[name][0].lower()} of the {device}"
        for device in FITS
        for name in _fit_doc(device, root)["bound_hits"]
    ]
    if not hits:
        return "No fitted value of either transistor sits on a limit"
    return "The fit stopped on a limit for " + " and ".join(hits)


def fit_verdict_table(root: Path = ROOT) -> str:
    """A Markdown table of the verdict of each gate length of the fit (``per_geometry`` of the
    result files): transistor, gate width, gate length, verdict."""
    rows = ["| Transistor | Gate width | Gate length | Verdict |", "|---|---|---|---|"]
    cells = []
    for device in FITS:
        for e in _fit_doc(device, root)["per_geometry"].values():
            g = e["geometry"]
            cells.append((device, g["w_um"], g["l_um"], e["verdict"]))
    rows += [
        f"| {{term}}`{d}` | {_um(w)} | {_um(length)} | {{term}}`{v}` |"
        for d, w, length, v in sorted(cells)
    ]
    return "\n".join(rows)


#: The SPICE corner spread of the calibration page: the nfet at its longest fit gate.
SPREAD_DEVICE, SPREAD_GEOMETRY = "nfet_05v0", "w10p0_l10p00"


@dataclass(frozen=True)
class Spread:
    """One quantity of the SPICE curve at the typical corner, and its lowest and highest value
    over the corners."""

    words: str
    unit: str
    typical: float
    lowest: float
    highest: float


def corner_spread(root: Path = ROOT) -> list[Spread]:
    """The flat parts and halfway-level crossings of the SPICE curve of :data:`SPREAD_DEVICE` at
    :data:`SPREAD_GEOMETRY`: the flat parts' Cgg from each corner's ``metrics.json``, the crossings
    from the nfet result file (``spice_regions`` at the typical corner and the corner window of
    each crossing check, ``verdicts.<check>.window``)."""
    from gf180tcad.devices import CORNERS

    base = Path(root) / "results" / "spice" / "ngspice"
    rel = Path(SPREAD_DEVICE) / SPREAD_GEOMETRY / "metrics.json"
    metrics = {c: json.loads((base / c / rel).read_text("utf-8"))["metrics"] for c in CORNERS}
    out = []
    for key, words in (
        ("cgg_acc_ff", "Accumulation flat part"),
        ("cgg_inv_ff", "Inversion flat part"),
    ):
        vals = [m[key] for m in metrics.values()]
        out.append(Spread(words, "fF", metrics["typical"][key], min(vals), max(vals)))
    rec = _fit_doc(SPREAD_DEVICE, root)["per_geometry"][SPREAD_GEOMETRY]
    for check, key, words in (
        ("dv_dep", "u_dep", "Depletion crossing"),
        ("dv_inv", "u_inv", "Inversion crossing"),
    ):
        w = rec["verdicts"][check]["window"]
        if w["source"] != "envelope":
            raise ValueError(f"{check}: the window is {w['source']!r}, not the corner envelope")
        out.append(Spread(words, "V", rec["spice_regions"][key], w["lo"], w["hi"]))
    return out


#: Most significant digits of the corner spread table.
SPREAD_DIGITS = 3


def corner_table(root: Path = ROOT) -> str:
    """A Markdown table of :func:`corner_spread`: typical, lowest, highest and the spread
    (highest minus lowest)."""
    rows = ["| Quantity | Typical | Lowest | Highest | Spread |", "|---|---|---|---|---|"]
    for s in corner_spread(root):
        vals = (s.typical, s.lowest, s.highest, s.highest - s.lowest)
        rows.append(
            f"| {s.words} | "
            + " | ".join(format_value(v, SPREAD_DIGITS, s.unit) for v in vals)
            + " |"
        )
    return "\n".join(rows)


#: The corner summaries of the corner fits (Task 16a, written by
#: :func:`gf180tcad.calibrate.corners.summary`), by transistor.
CORNER_SUMMARIES = {d: f"results/tcad/corners/{d}/summary.json" for d in FITS}
#: The words of a lowest or highest value that sits on a bound of its fit, by bound.
BOUND_WORDS = {"lower": "lower limit", "upper": "upper limit"}


@dataclass(frozen=True)
class Bound:
    """One fitted number of one transistor over the :term:`corners <corner>`: the typical fit,
    the lowest and highest value with their corner and the limit each sits on (None when it
    sits on none), the spread (highest minus lowest) and the value at each corner (its unit)."""

    device: str
    name: str
    typical: float
    lowest: float
    lowest_corner: str
    lowest_at_bound: str | None
    highest: float
    highest_corner: str
    highest_at_bound: str | None
    spread: float
    values: dict[str, float]


def corner_summary(device: str, root: Path = ROOT) -> dict:
    """The corner summary of ``device`` under ``root``; KeyError when its tunables are not
    :data:`TUNABLES` in order."""
    doc = json.loads((Path(root) / CORNER_SUMMARIES[device]).read_text("utf-8"))
    if doc["device"] != device or set(doc["tunables"]) != set(TUNABLES):
        raise KeyError(f"{CORNER_SUMMARIES[device]}: {doc['device']}, {sorted(doc['tunables'])}")
    doc["tunables"] = {n: doc["tunables"][n] for n in TUNABLES}
    return doc


def corner_bounds(device: str, root: Path = ROOT) -> list[Bound]:
    """The :class:`Bound` of each of :data:`TUNABLES` of ``device``, read from its corner
    summary under ``root``. A lowest or highest value on a limit of its fit is that limit."""
    out = []
    for name, t in corner_summary(device, root)["tunables"].items():
        out.append(
            Bound(device, name, t["typical"], t["min"], t["min_corner"], t["min_at_bound"],
                  t["max"], t["max_corner"], t["max_at_bound"], t["spread"], dict(t["values"]))
        )  # fmt: skip
    return out


def corner_bounds_table(device: str, root: Path = ROOT) -> str:
    """A Markdown table of :func:`corner_bounds` of ``device``: one row per fitted number, its
    typical fit, lowest and highest value over the corners and the spread. The unit is in the
    row label, as in :func:`fit_table`."""
    rows = ["| Number | Typical | Lowest | Highest | Spread |", "|---|---|---|---|---|"]
    for b in corner_bounds(device, root):
        words, unit, most = TUNABLES[b.name]
        cells = (shortest(v, "", most) for v in (b.typical, b.lowest, b.highest, b.spread))
        rows.append(f"| {words} ({unit}) | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def corner_extremes_table(root: Path = ROOT) -> str:
    """A Markdown table of the corner of each lowest and highest value of :func:`corner_bounds`,
    for both transistors: transistor, number, corner of the lowest, corner of the highest."""
    rows = ["| Transistor | Number | Lowest at | Highest at |", "|---|---|---|---|"]
    for device in FITS:
        for b in corner_bounds(device, root):
            rows.append(
                f"| {{term}}`{device}` | {TUNABLES[b.name][0]} | {b.lowest_corner} | "
                f"{b.highest_corner} |"
            )
    return "\n".join(rows)


def corner_bound_hits(root: Path = ROOT) -> str:
    """A sentence on the lowest and highest values of :func:`corner_bounds` that sit on a limit
    of their fit, which the bounds table gives as that limit."""
    hits = []
    for device in FITS:
        for b in corner_bounds(device, root):
            for side, corner, at in (
                ("lowest", b.lowest_corner, b.lowest_at_bound),
                ("highest", b.highest_corner, b.highest_at_bound),
            ):
                if at is not None:
                    hits.append(
                        f"The {side} {TUNABLES[b.name][0].lower()} of the {device}, at {corner}, "
                        f"sits on its {BOUND_WORDS[at]}, so the table gives that limit"
                    )
    if not hits:
        return "No lowest or highest value sits on a limit of its fit"
    return ". ".join(hits)


#: The corner fit files (Task 16a), by transistor and corner (the typical fit is the calibration).
CORNER_FITS = "results/tcad/corners/{device}/{corner}.json"
#: The gate width of the gate-length series of :func:`corner_crossing_gaps` (µm).
CROSSING_WIDTH_UM = 10.0


def corner_crossing_gaps(device: str, root: Path = ROOT) -> dict[str, dict[float, float]]:
    """``{corner: {gate length (µm): ΔV_dep (V)}}``: the depletion crossing shift of each fit, at
    every W = 10 µm gate, fitted and held out (1D). Typical from the calibration result file and
    the validation file, each other corner from its corner file (``per_geometry``, ``held_out``)."""
    from gf180tcad.devices import CORNERS

    out: dict[str, dict[float, float]] = {}
    for corner in CORNERS:
        if corner == "typical":
            recs = list(_fit_doc(device, root)["per_geometry"].values())
            val = json.loads((Path(root) / VALIDATION / f"{device}.json").read_text("utf-8"))
            recs += list(val["one_d"].values())
        else:
            path = Path(root) / CORNER_FITS.format(device=device, corner=corner)
            doc = json.loads(path.read_text("utf-8"))
            recs = [*doc["per_geometry"].values(), *doc["held_out"].values()]
        gaps = {
            r["geometry"]["l_um"]: r["metrics"]["dv_dep_v"]
            for r in recs
            if r["geometry"]["w_um"] == CROSSING_WIDTH_UM
        }
        out[corner] = dict(sorted(gaps.items()))
    return out


@dataclass(frozen=True)
class CornerFit:
    """One fitted number of one fit (typical or a corner): its limits, the fitted value and the
    limit it sits on (None when it sits on none)."""

    device: str
    corner: str
    name: str
    lower: float
    fitted: float
    upper: float
    at_bound: str | None


def corner_fit_limits(device: str, root: Path = ROOT) -> list[CornerFit]:
    """The :class:`CornerFit` of each of :data:`TUNABLES` at each corner, typical first (the
    calibration result file), each other corner from its corner file (``bounds``, ``values``,
    ``bound_hits``)."""
    from gf180tcad.devices import CORNERS

    out = []
    for corner in CORNERS:
        if corner == "typical":
            doc = _fit_doc(device, root)
        else:
            path = Path(root) / CORNER_FITS.format(device=device, corner=corner)
            doc = json.loads(path.read_text("utf-8"))
        for name in TUNABLES:
            lo, hi = doc["bounds"][name]
            out.append(CornerFit(device, corner, name, lo, doc["values"][name], hi,
                                 doc["bound_hits"].get(name)))  # fmt: skip
    return out


def corner_fit_hits(root: Path = ROOT) -> str:
    """A sentence naming every fit, typical or corner, whose fitted value sits on a limit."""
    hits = [
        f"The {TUNABLES[f.name][0].lower()} of the {f.device} at {f.corner} stops on its "
        f"{BOUND_WORDS[f.at_bound]}"
        for device in FITS
        for f in corner_fit_limits(device, root)
        if f.at_bound is not None
    ]
    if not hits:
        return "No fit, typical or corner, stops on a limit"
    return ". ".join(hits)


#: The fitted numbers of the card cross-check: the summary key, the unit and digits a page prints
#: the gap in, and the factor from the summary unit.
CROSSCHECK = {"t_ox_eff_nm": ("tox", "nm", 2, 1.0), "dv_fb_v": ("vfb", "mV", 2, 1e3)}


def crosscheck_largest(device: str, name: str, root: Path = ROOT) -> tuple[str, float]:
    """``(corner, difference)`` of the largest ``shift_difference`` (the fit's shift from the
    typical fit minus the card's shift, by absolute value) of ``name`` in the corner summary of
    ``device``, in the summary's unit."""
    diffs = corner_summary(device, root)["tunables"][name]["shift_difference"]
    corner = max(diffs, key=lambda c: abs(diffs[c]))
    return corner, diffs[corner]


def crosscheck_substitutions(root: Path = ROOT) -> dict[str, str]:
    """``x_crosscheck_<key>_gap_<transistor>`` (the largest difference of :func:`crosscheck_largest`,
    signed, with its unit) and ``x_crosscheck_<key>_corner_<transistor>`` for each of
    :data:`CROSSCHECK` and each transistor (``nfet``, ``pfet``)."""
    out = {}
    for device in FITS:
        short = device.split("_")[0]
        for name, (key, unit, digits, factor) in CROSSCHECK.items():
            corner, d = crosscheck_largest(device, name, root)
            out[f"x_crosscheck_{key}_gap_{short}"] = shortest(d * factor, unit, digits)
            out[f"x_crosscheck_{key}_corner_{short}"] = corner
    return out


def corner_verdicts(root: Path = ROOT) -> str:
    """A sentence on the verdict of every corner fit (at its calibration geometries), per
    transistor, from the corner summaries: one clause per transistor and verdict."""
    from gf180tcad.devices import CORNERS

    clauses = []
    for device in FITS:
        doc = corner_summary(device, root)
        by: dict[str, list[str]] = {}
        for corner in CORNERS:
            if corner != "typical":
                by.setdefault(doc["corners"][corner]["verdict"], []).append(corner)
        for verdict, corners in by.items():
            where = (
                "at every corner"
                if len(corners) == len(CORNERS) - 1
                else ("at " + ", ".join(corners))
            )
            clauses.append(f"the {{term}}`{device}` is {{term}}`{verdict}` {where}")
    return "Against each corner's SPICE curves, " + "; ".join(clauses)


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
    word}`` and ``{"x_<name>_term": word linked to the glossary}`` for every :data:`WORDS`
    entry, and the 2D cells' table and Disagree clause
    (``x_two_d_table``, ``x_two_d_disagree``), the :func:`counts`, the calibration page's
    tables and sentence (``x_fit_table_nfet``, ``x_fit_table_pfet``, ``x_limit_kinds_table``,
    ``x_bound_hits``, ``x_fit_verdict_table``, ``x_corner_table``), the corner bounds
    (``x_corner_bounds_table_nfet``, ``x_corner_bounds_table_pfet``,
    ``x_corner_extremes_table``, ``x_corner_bound_hits``), and the :func:`corner_pvth0`
    numbers of the reproduce page, for MyST."""
    out: dict[str, str] = {}
    for name, n in REGISTRY.items():
        out[f"x_{name}"] = text(name)
        out[f"x_{name}_label"] = LABELS[n.kind]
    for name in WORDS:
        out[f"x_{name}"] = word(name)
        out[f"x_{name}_term"] = f"{{term}}`{word(name)}`"
    out.update({f"x_{k}": str(v) for k, v in counts().items()})
    out["x_two_d_table"] = two_d_table()
    out["x_two_d_disagree"] = two_d_disagree()
    for device in FITS:
        out[f"x_fit_table_{device.split('_')[0]}"] = fit_table(device)
    out["x_limit_kinds_table"] = limit_kinds_table()
    out["x_bound_hits"] = bound_hits()
    out["x_fit_verdict_table"] = fit_verdict_table()
    out["x_corner_table"] = corner_table()
    for device in FITS:
        out[f"x_corner_bounds_table_{device.split('_')[0]}"] = corner_bounds_table(device)
    out["x_corner_extremes_table"] = corner_extremes_table()
    out["x_corner_bound_hits"] = corner_bound_hits()
    out.update(crosscheck_substitutions())
    out["x_corner_fit_hits"] = corner_fit_hits()
    out["x_corner_verdicts"] = corner_verdicts()
    out.update({f"x_{k}": v for k, v in corner_pvth0().items()})
    return out


def corner_pvth0() -> dict[str, str]:
    """The numbers of the PVTH0 paragraph of the corner fits (docs/reproduce/index.md), from
    :func:`gf180tcad.calibrate.corners.largest_pvth0_shift`: the corner, the gate, its DVTH0,
    dL, dW, L_eff, W_eff, ΔP_VTH0 and ΔV_th0, each as the page prints it."""
    from gf180tcad.calibrate import corners

    corner, g, v = corners.largest_pvth0_shift()
    row = corners.load_table()["devices"]["pfet_05v0"]["other_lines"]["pvth0"]
    dvth0 = corners.load_table()["devices"]["pfet_05v0"]["corners"][corner][row["param"]]["value"]
    return {
        "corner_pvth0_corner": corner,
        "corner_pvth0_l": format_value(g.l_um, 1, "µm"),
        "corner_pvth0_w": format_value(g.w_um, 2, "µm"),
        "corner_pvth0_dvth0": format_value(dvth0, 4, "V"),
        "corner_pvth0_dl": format_value(v["dl"] * 1e9, 4, "nm"),
        "corner_pvth0_dw": format_value(v["dw"] * 1e9, 4, "nm"),
        "corner_pvth0_leff": format_value(v["leff"] * 1e6, 4, "µm"),
        "corner_pvth0_weff": format_value(v["weff"] * 1e6, 5, "µm"),
        "corner_pvth0_dp": format_value(v["dp"], 4, "V·µm²"),
        "corner_pvth0_dv": format_value(v["dv"] * 1e3, 4, "mV"),
    }
