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


def fit_table(device: str, root: Path = ROOT) -> str:
    """A Markdown table of :func:`fits` of ``device``: one row per fitted number, its lower
    limit, start, fitted value and upper limit."""
    rows = ["| Number | Lower limit | Start | Fitted | Upper limit |", "|---|---|---|---|---|"]
    for f in fits(device, root):
        words, unit, most = TUNABLES[f.name]
        cells = (shortest(v, unit, most) for v in (f.lower, f.start, f.fitted, f.upper))
        rows.append(f"| {words} | " + " | ".join(cells) + " |")
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
        ("dv_dep", "u_dep", "Falling crossing"),
        ("dv_inv", "u_inv", "Rising crossing"),
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


def format_value(v: float, digits: int, unit: str) -> str:
    """``v`` to ``digits`` significant digits with its unit: plain from 0.001 to 9999, else as
    a mantissa times a power of ten; a typographic minus sign; no space when ``unit`` is
    empty (a pure number)."""
    if not math.isfinite(v):
        raise ValueError(f"{v!r} is not a finite number")
    sign = "−" if v < 0 else ""
    mant, exp = f"{abs(v):.{digits - 1}e}".split("e")
    e = int(exp)
    if -3 <= e < 4:
        body = f"{abs(v):.{max(digits - 1 - e, 0)}f}"
    else:
        body = f"{mant} × 10{str(e).translate(_SUP)}"
    return f"{sign}{body} {unit}" if unit else f"{sign}{body}"


def text(name: str) -> str:
    """The value of entry ``name`` as a page prints it."""
    n = REGISTRY[name]
    return format_value(value(name) * n.factor, n.digits, n.unit)


def substitutions() -> dict[str, str]:
    """``{"x_<name>": text, "x_<name>_label": label}`` for every entry, and ``{"x_<name>":
    word}`` for every :data:`WORDS` entry, and the 2D cells' table and Disagree clause
    (``x_two_d_table``, ``x_two_d_disagree``), the :func:`counts`, and the calibration page's
    tables and sentence (``x_fit_table_nfet``, ``x_fit_table_pfet``, ``x_limit_kinds_table``,
    ``x_bound_hits``, ``x_fit_verdict_table``, ``x_corner_table``), for MyST."""
    out: dict[str, str] = {}
    for name, n in REGISTRY.items():
        out[f"x_{name}"] = text(name)
        out[f"x_{name}_label"] = LABELS[n.kind]
    for name in WORDS:
        out[f"x_{name}"] = word(name)
    out.update({f"x_{k}": str(v) for k, v in counts().items()})
    out["x_two_d_table"] = two_d_table()
    out["x_two_d_disagree"] = two_d_disagree()
    for device in FITS:
        out[f"x_fit_table_{device.split('_')[0]}"] = fit_table(device)
    out["x_limit_kinds_table"] = limit_kinds_table()
    out["x_bound_hits"] = bound_hits()
    out["x_fit_verdict_table"] = fit_verdict_table()
    out["x_corner_table"] = corner_table()
    return out
