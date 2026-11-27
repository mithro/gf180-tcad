# SPDX-License-Identifier: Apache-2.0
"""The numbers and figures of the high-voltage junction page (``docs/results/hv-junction.md``).

Everything is read from the committed records of ``experiments/hv-junction``
(``results/hv-junction/*.json``), the structure list ``experiments/hv-junction/structures.json``
and four host modules of that experiment, loaded from their files: ``predict.py`` (the case
sets), ``hvsite.py`` (the drawn structure as a cross-section), ``ionize.py`` (the ionisation
integral) and ``profile1d.py`` (the sheet resistance and capacitance of a well profile).

The prediction records are ``main``, ``rest``, ``rest2``, ``rest3``, ``mem`` and ``family``: a
case takes the row of the last of them that holds it. A row is read only when its parameters are
the ones ``predict.py`` gives now (the record's ``params_sha256``), so a record made before a
change of the structures or the process never prints a superseded number. The record ``p5`` is
its own set: its cases have the names of ordinary cases, with the first ring held at 0 V, and
are never merged with them. A value whose record or case is not committed prints as a dash, and
its points are missing from the figures. The other records are ``checks``, ``diodes``,
``charon-firstpass`` and ``charon``.

:func:`substitutions` gives the page's ``{{ hvj_<name> }}`` values, and :func:`write_all` writes
each figure of :data:`FIGURES` as ``<name>-light.svg`` and ``<name>-dark.svg`` into
``docs/_generated/hv-junction/`` at docs build time (:func:`gf180tcad.docgen.generate`). The
page's result tables are written into it by::

    uv run --locked --group docs python -m gf180tcad.hvjunction_figures tables
"""

from __future__ import annotations

import functools
import importlib.util
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import matplotlib
import matplotlib.patches
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from gf180tcad.explain import figures as ef
from gf180tcad.sandbox import REPO_ROOT

EXPERIMENT = REPO_ROOT / "experiments" / "hv-junction"
ROOT = REPO_ROOT / "results" / "hv-junction"
PAGE = REPO_ROOT / "docs" / "results" / "hv-junction.md"

#: The prediction records, in the order a later one replaces the cases of an earlier one.
PREDICTION_RECORDS = ("main", "rest", "rest2", "rest3", "mem", "gaps", "sharp", "family")
#: The record of the ring-sense structures with ring 1 held at 0 V; never merged with the others.
P5_RECORD = "p5"
#: Every record: the prediction records, the check cases, the 1D diodes and the Charon cases.
RECORDS = (*PREDICTION_RECORDS, P5_RECORD, "checks", "diodes", "charon-firstpass", "charon")
#: The text of a value whose record or case is not committed.
MISSING = "—"

#: The check cases of ``checks.py`` and the cases of the Charon cross-check.
CHECKS = ("bare-f0.1-x128-v2", "bare-f0.1-f64-v2", "bare-f0.1-f64-v4", "bare-f0.1-f64-v5",
          "bare-f0.05-f64-v4", "abut-f0.05", "abut-f0.03", "abut-f0.02")  # fmt: skip
DIODES = {"1e+15": 1e15, "1e+16": 1e16, "1e+17": 1e17}
#: diode1d.py's donor doping of the N+ side (cm^-3), dd.py's intrinsic density (cm^-3) and
#: thermal voltage at 300 K (V): the built-in potential of its diodes.
DIODE_ND, NI, VT = 1e19, 1.0e10, 1.380649e-23 * 300.0 / 1.602176634e-19
#: The cases of each Charon record: ``charon-firstpass`` ran six sections of the first doping
#: family (its process names were A and B), ``charon`` runs sections of the present one.
CHARON_CASES = {
    "charon-firstpass": ("NT20|A|edge", "NT20|B|edge", "NW1p5|B|edge", "NM1_6|B|edge",
                         "NR1_2|B|edge", "DT20|B|edge"),
    "charon": ("NP4|BL|edge", "NT20|BD|edge"),
}  # fmt: skip
#: The substitution prefix of each Charon record.
CHARON_PREFIX = {"charon-firstpass": "hvj_c1", "charon": "hvj_c2"}
CHARON_FIELDS = {"devsim": "devsim_bv_v", "current": "bv_current_v",
                 "integral": "bv_integral_v", "last": "last_converged_v"}  # fmt: skip

# The published anchors of the doping family, each with its public source on the page: the
# zero-bias capacitance, grading coefficient and junction potential of the N-well and deep
# N-well diode models (F/cm^2, dimensionless, V), the typical N-well breakdown voltage (V) and
# the deep N-well model's breakdown voltage (V).
ANCHORS = {
    "nw": {"cj0": 1.4914e-8, "mj": 0.30525, "pb": 0.43905},
    "dnw": {"cj0": 2.2998e-8, "mj": 0.14716, "pb": 0.35175},
    "bv_typ": 14.0,
    "dnw_model_bv": 30.48,
}
#: The reverse bias (V) at which the anchors table compares the capacitances a second time.
ANCHOR_BIAS_V = 10.0
#: The shifts of the deep P layer (µm, positive is deeper) at which the N-well's plane breakdown
#: under assumption D is recomputed, and the key suffix of each.
LAYER_SHIFTS_UM = {"m100": -1.0, "m025": -0.25, "p025": 0.25, "p100": 1.0}
#: The same section and mesh with two bias steps (1.5 V and 3 V): an abutting P-well, generated
#: (AL) and drawn at no distance (BL).
STEP_PAIR = ("NT20|AL|edge", "NW0|BL|edge")
#: A sharp-corner case. Its 64-bit sweep in ``main`` stopped converging before the integral
#: reached 1; its 128-bit sweep in a later record runs to breakdown.
OPEN_CORNER = "NC0|BD|corner"

STYLE = {
    "size_in": (6.4, 4.4),
    "section_in": (6.4, 3.6),
    "marker_pt": 7,
    "line_width": 1.6,
    "legend_pt": 9,
    # the cross-section: a doped box is drawn to this many standard deviations below its peak
    "box_sigmas": 2.0,
    "section_depth_um": 4.0,
    # the contact labels of the cross-section sit at this height (µm, above the plate)
    "label_y_um": -2.1,
    "section_struct": {"rings": [[2.0, 2.0]], "plates": {"m1": 6.0}, "term": 12.0},
    "curve_cases": ("NT20|AL|edge", "NT20|BL|edge", "NM1_6|BL|edge", "NR3_1p5|BL|edge"),
    "analytic_points": 400,
}


@functools.cache
def _load(name: str) -> ModuleType:
    """A host module of the experiment, from its file. The folder is not a package, and its
    modules import each other by bare name, so it is on ``sys.path`` during the import."""
    sys.path.insert(0, str(EXPERIMENT))
    try:
        spec = importlib.util.spec_from_file_location(f"_hvj_{name}", EXPERIMENT / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(EXPERIMENT))


def _predict() -> ModuleType:
    """``predict.py``."""
    return _load("predict")


# --- the records ----------------------------------------------------------------------------------


def records(root: Path = ROOT) -> dict[str, dict]:
    """``{name: record}`` of the records of :data:`RECORDS` that are committed under ``root``."""
    out = {}
    for name in RECORDS:
        path = Path(root) / f"{name}.json"
        if path.is_file():
            out[name] = json.loads(path.read_text("utf-8"))
    return out


def structures() -> dict[str, dict]:
    """The simulated structures of the test die: ``structures.json`` without the open site and
    the capacitance wells (``predict.STRUCTS``)."""
    return _predict().STRUCTS


@functools.cache
def current_cases() -> dict[str, dict]:
    """``{case: parameters}`` of the case sets ``predict.py`` gives now: ``main`` and
    ``family``."""
    predict = _predict()
    return {**predict.main_cases(), **predict.family_cases()}


@functools.cache
def current_hashes() -> dict[str, str]:
    """``{case: sha256 of its parameters}`` of :func:`current_cases`, hashed as ``record.py``
    hashes them."""
    digest = _predict().digest
    return {c: digest(p) for c, p in current_cases().items()}


@functools.cache
def p5_hashes() -> dict[str, str]:
    """``{case: sha256 of its parameters}`` of ``predict.py``'s set ``p5``."""
    predict = _predict()
    return {c: predict.digest(p) for c, p in predict.p5_cases().items()}


def p5_cases(root: Path = ROOT) -> dict[str, dict]:
    """``{case name: its row}`` of the ``p5`` record, for the rows run with the parameters
    ``predict.py`` gives now."""
    got = records(root).get(P5_RECORD, {}).get("cases", {})
    now = p5_hashes()
    return {c: row for c, row in got.items() if row["params_sha256"] == now.get(c)}


def cases(root: Path = ROOT) -> dict[str, dict]:
    """``{case name: its row}`` of every prediction case of the committed records that was run
    with the parameters ``predict.py`` gives now. A case takes the row of the last record of
    :data:`PREDICTION_RECORDS` that holds it."""
    out = {}
    recs = records(root)
    for name in PREDICTION_RECORDS:
        out.update(recs.get(name, {}).get("cases", {}))
    now = current_hashes()
    return {c: row for c, row in out.items() if row["params_sha256"] == now.get(c)}


def shown(row: dict | None) -> str:
    """A case's breakdown voltage as the page prints it: one decimal; ``> V`` with the highest
    bias solved when the integral stays below 1 up to it; a dash when the case has no result."""
    if row is None:
        return MISSING
    if row["bv_v"] is None:
        return f"> {row['reached_v']:.1f}"
    return f"{row['bv_v']:.1f}"


def rows(struct: dict[str, dict] | None = None) -> list[str]:
    """The table rows: each structure, a gated one once per gate connection (``@g0`` held at
    0 V, ``@gw`` tied to the well)."""
    out = []
    for name, st in sorted((struct or structures()).items()):
        out += [f"{name}@g0", f"{name}@gw"] if st["gate"] else [name]
    return out


def group(row: str, struct: dict[str, dict] | None = None) -> str:
    """The table a row belongs to: ``deep`` (a deep N-well), else ``rings``, ``nat``, ``pwell``,
    ``plates`` or ``bare`` by what is drawn beside the N-well."""
    st = (struct or structures())[row.split("@")[0]]
    if st["kind"] == "dnw":
        return "deep"
    for key, name in (("rings", "rings"), ("nat_gap", "nat"), ("pwell_gap", "pwell"),
                      ("plates", "plates")):  # fmt: skip
        if st[key] not in (None, [], {}):
            return name
    return "bare"


_NWELL = (("AL", "edge"), ("BL", "edge"), ("BL", "corner"), ("BD", "edge"))
#: The columns of each group's table: (process, shape). A table has at most four of them.
COLUMNS = {
    "bare": _NWELL,
    "pwell": _NWELL,
    "plates": _NWELL,
    "rings": _NWELL,
    "nat": (("AL", "edge"), ("AnL", "edge"), ("AnL", "corner"), ("AnD", "edge")),
    "deep": (("AL", "edge"), ("AD", "edge"), ("BL", "edge"), ("BD", "edge")),
}
#: The columns of the family tables: the substrate doping under each extent of the deep P
#: layer, then the oxide charge and the generated P-well.
FAMILY_COLUMNS = {
    "family-l": (("BLlo", "edge"), ("BL", "edge"), ("BLhi", "edge")),
    "family-d": (("BDlo", "edge"), ("BD", "edge"), ("BDhi", "edge")),
    "family-other": (("BLq", "edge"), ("BLq3", "edge"), ("AL", "edge"), ("ALhi", "edge")),
}
#: The ``:name:`` of each table on the page.
TABLE_NAMES = {name: f"tab-hvj-{name}" for name in (*COLUMNS, *FAMILY_COLUMNS, "p5")}


def key(case: str) -> str:
    """The substitution key of a case: ``hvj_`` and the case name with ``@`` and ``|`` as ``_``."""
    return "hvj_" + re.sub(r"[^0-9A-Za-z]", "_", case)


def p5_key(case: str) -> str:
    """The substitution key of a case of the ``p5`` record."""
    return "hvj_p5_" + key(case)[len("hvj_") :]


def p5_structures() -> list[str]:
    """The ring-sense structures, the rows of the ``p5`` table."""
    return sorted(n for n, st in structures().items() if st["sense"])


def family_structures() -> list[str]:
    """The structures of the family tables: ``predict.KEY``."""
    return [k for k in _predict().KEY if k in structures()]


def table(name: str) -> str:
    """The Markdown rows of the table ``name`` (a key of :data:`COLUMNS` or
    :data:`FAMILY_COLUMNS`), as the page holds them: a header, then one row per structure with
    a substitution per value."""
    if name == "p5":
        procs = _predict().P5_PROCESSES
        lines = ["| Structure | " + " | ".join(procs) + " |", "|" + "---|" * (len(procs) + 1)]
        for row in p5_structures():
            cells = [f"{{{{ {p5_key(f'{row}|{p}|edge')} }}}}" for p in procs]
            lines.append(f"| {row} | " + " | ".join(cells) + " |")
        return "\n".join(lines)
    if name in FAMILY_COLUMNS:
        columns, names = FAMILY_COLUMNS[name], family_structures()
    else:
        columns, names = COLUMNS[name], [r for r in rows() if group(r) == name]
    head = ["Structure", *(p if s == "edge" else f"{p} corner" for p, s in columns)]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for row in names:
        cells = [f"{{{{ {key(f'{row}|{p}|{s}')} }}}}" for p, s in columns]
        lines.append(f"| {row} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def table_cases() -> list[str]:
    """Every case a table of the page prints."""
    out = []
    for row in rows():
        out += [f"{row}|{p}|{s}" for p, s in COLUMNS[group(row)]]
    for columns in FAMILY_COLUMNS.values():
        out += [f"{row}|{p}|{s}" for row in family_structures() for p, s in columns]
    return out


def write_tables(page: Path = PAGE) -> bool:
    """Rewrite the rows of every result table of ``page`` (the table blocks named by
    :data:`TABLE_NAMES`) from :func:`table`. Returns whether the page changed."""
    text = old = page.read_text("utf-8")
    for name, label in TABLE_NAMES.items():
        m = re.search(rf"(:name: {re.escape(label)}\n\n)((?:\|.*\n)+)", text)
        if m is None:
            raise ValueError(f"{page}: no table named {label}")
        text = text[: m.start(2)] + table(name) + "\n" + text[m.end(2) :]
    if text != old:
        page.write_text(text, "utf-8")
    return text != old


# --- the checks -----------------------------------------------------------------------------------


def analytic_diode_bv(doping: float) -> float:
    """The breakdown voltage (V) of a one-sided abrupt junction of ``doping`` (cm^-3): the bias
    at which ``ionize.py``'s electron integral over the triangular field of the depletion
    approximation reaches 1."""
    ionize = _load("ionize")
    q, eps = 1.602176634e-19, 11.7 * 8.8541878128e-14
    volts = np.geomspace(2.0, 2000.0, STYLE["analytic_points"])
    ints = []
    for v in volts:
        w = np.sqrt(2 * eps * v / (q * doping))
        s = np.linspace(0.0, w, 4000)
        ints.append(ionize.ionisation_integrals(s, q * doping * s / eps)[0])
    return ionize.breakdown_voltage(volts, ints)


def built_in(doping: float) -> float:
    """The built-in potential (V) of diode1d.py's abrupt N+/P junction of acceptor ``doping``."""
    return VT * float(np.log(DIODE_ND * doping / NI**2))


@functools.cache
def well_anchors() -> dict[str, float]:
    """The wells of ``hvsite.DEFAULT_PROCESS`` in ``profile1d.py``, depletion approximation.

    ``nw_rs`` is the sheet resistance of the N-well under the trench oxide (ohm/square).
    ``<well>_c0`` and ``<well>_c10`` are the junction capacitance at 0 V and
    :data:`ANCHOR_BIAS_V` (F/cm^2) and ``<well>_<c0|c10>_model`` the diode model's value;
    ``<well>`` is ``nw`` (the N-well with no deep P layer under it, assumption L), ``nwd`` (with
    the layer under it, assumption D) or ``dnw`` (the deep N-well over the layer).
    ``plane_<well>`` is the plane breakdown voltage of the well's deepest junction (V, junction
    potential), and ``plane_nwd_<suffix>`` that of the N-well with the deep P layer shifted by
    each of :data:`LAYER_SHIFTS_UM`."""
    hvsite, profile1d = _load("hvsite"), _load("profile1d")
    pr = hvsite.DEFAULT_PROCESS
    um = 1e-4
    y = np.linspace(0, 16 * um, 32001)
    volts = np.array([0.0, ANCHOR_BIAS_V])

    def boxes(implants, shift=0.0):
        return [(g["peak"], (g["rp"] + shift) * um, g["sy"] * um) for g in implants]

    n, total = profile1d.net(y, boxes(pr["nw"]), pr["sub"])
    out = {"nw_rs": float(profile1d.sheet_resistance(y, n, total, top=hvsite.STI * um))}
    blanket, _ = profile1d.net(y, boxes(pr["nw"]), pr["sub"], boxes(pr["deep_p"]))
    deep, _ = profile1d.net(y, boxes(pr["dnw"]), pr["sub"], boxes(pr["deep_p"]))
    for well, model, profile in (("nw", "nw", n), ("nwd", "nw", blanket), ("dnw", "dnw", deep)):
        c = profile1d.cv(y, profile, volts)
        m = ANCHORS[model]
        want = profile1d.model_c(volts, m["cj0"], m["mj"], m["pb"])
        for tag, got, ref in zip(("c0", "c10"), c, want, strict=True):
            out[f"{well}_{tag}"], out[f"{well}_{tag}_model"] = float(got), float(ref)
        out[f"plane_{well}"] = profile1d.plane_breakdown(y, profile)
    for suffix, shift in LAYER_SHIFTS_UM.items():
        moved, _ = profile1d.net(y, boxes(pr["nw"]), pr["sub"], boxes(pr["deep_p"], shift))
        out[f"plane_nwd_{suffix}"] = profile1d.plane_breakdown(y, moved)
    return out


def open_corner(root: Path = ROOT) -> dict[str, float] | None:
    """The end of the superseded 64-bit sweep of :data:`OPEN_CORNER` in the ``main`` record:
    ``v`` the last bias solved, ``i`` the integral there, ``slope`` its rise per volt over the
    last step, and ``extrapolated`` the bias at which that straight line reaches 1. None when
    ``main`` has no such row or the row broke down."""
    row = records(root).get("main", {}).get("cases", {}).get(OPEN_CORNER)
    if row is None or row["bv_v"] is not None or len(row["v"]) < 2:
        return None
    (v0, v1), (i0, i1) = row["v"][-2:], row["i_n"][-2:]
    slope = (i1 - i0) / (v1 - v0)
    return {"v": v1, "i": i1, "slope": slope, "extrapolated": v1 + (1 - i1) / slope}


def _two(v: float | None) -> str:
    return MISSING if v is None else f"{v:.2f}"


def substitutions(root: Path = ROOT) -> dict[str, str]:
    """``{"hvj_<name>": text}``: every number the page prints.

    ``hvj_<case>`` (:func:`key`) is :func:`shown` of each current case and ``hvj_p5_<case>`` that
    of each case of the ``p5`` set; ``hvj_n_cases`` counts the cases of the ``main`` set,
    ``hvj_n_absent`` those of them no record holds with the present parameters and ``hvj_n_open``
    those whose integral stayed below 1; ``hvj_open_corner_<name>`` are :func:`open_corner`;
    ``hvj_chk_<name>`` is a check case's breakdown voltage; ``hvj_diode_<doping>`` the 1D
    diode's, ``hvj_diode_<doping>_analytic`` the triangular-field value, ``_vbi`` the built-in
    potential and ``_applied`` their difference; ``hvj_c1_<case>_<field>`` and
    ``hvj_c2_<case>_<field>`` the values of the two Charon records (:data:`CHARON_PREFIX`,
    :data:`CHARON_FIELDS`); ``hvj_nw_rs``, ``hvj_<well>_<c0|c10>[_model]`` and ``hvj_plane_<name>`` the anchors of
    :func:`well_anchors` (capacitances in fF/µm²); ``hvj_abut_pct`` how far the abutting
    junction lies above the published typical value; ``hvj_step_pair_pct`` the difference of
    the two bias steps of :data:`STEP_PAIR`."""
    recs = records(root)
    got = cases(root)
    names = {*current_cases(), *table_cases()}
    out = {key(c): shown(got.get(c)) for c in names}
    if len(out) != len(names):
        raise ValueError("two case names give one substitution key")
    checks = recs.get("checks", {}).get("cases", {})
    for name in CHECKS:
        row = checks.get(name)
        out["hvj_chk_" + re.sub(r"[^0-9A-Za-z]", "_", name)] = _two(row and row["bv_v"])
    diodes = recs.get("diodes", {}).get("diodes", {})
    for name, doping in DIODES.items():
        short = name.replace("+", "")
        analytic = analytic_diode_bv(doping)
        out[f"hvj_diode_{short}"] = _two(diodes.get(name, {}).get("bv_v"))
        out[f"hvj_diode_{short}_analytic"] = _two(analytic)
        out[f"hvj_diode_{short}_vbi"] = _two(built_in(doping))
        out[f"hvj_diode_{short}_applied"] = _two(analytic - built_in(doping))
    for name, names in CHARON_CASES.items():
        charon = recs.get(name, {}).get("cases", {})
        for case in names:
            for field, source in CHARON_FIELDS.items():
                k = f"{CHARON_PREFIX[name]}_{key(case)[len('hvj_') :]}_{field}"
                out[k] = _two(charon.get(case, {}).get(source))
    for name, value in well_anchors().items():
        if name == "nw_rs" or name.startswith("plane_"):
            out[f"hvj_{name}"] = f"{value:.0f}"
        else:  # F/cm^2 to fF/µm^2 is a factor of 1e7
            out[f"hvj_{name}"] = f"{value * 1e7:.3f}"
    fine, coarse = (got.get(c) for c in STEP_PAIR)
    ok = fine is not None and fine["bv_v"] is not None
    out["hvj_abut_pct"] = f"{100 * (fine['bv_v'] / ANCHORS['bv_typ'] - 1):.0f}" if ok else MISSING
    ok = ok and coarse is not None and coarse["bv_v"] is not None
    out["hvj_step_pair_pct"] = (
        f"{100 * abs(coarse['bv_v'] / fine['bv_v'] - 1):.1f}" if ok else MISSING
    )
    p5 = p5_cases(root)
    for case in p5_hashes():
        out[p5_key(case)] = shown(p5.get(case))
    main_set = _predict().main_cases()
    have = [c for c in main_set if c in got]
    out["hvj_n_cases"] = str(len(main_set))
    out["hvj_n_absent"] = str(len(main_set) - len(have))
    out["hvj_n_open"] = str(len([c for c in have if got[c]["bv_v"] is None]))
    end = open_corner(root)
    for name, digits in (("v", 1), ("i", 3), ("slope", 3), ("extrapolated", 0)):
        out[f"hvj_open_corner_{name}"] = MISSING if end is None else f"{end[name]:.{digits}f}"
    return out


# --- the figures ----------------------------------------------------------------------------------


def _figure(size: tuple[float, float]) -> Figure:
    fig = Figure(figsize=size, layout="constrained")
    FigureCanvasAgg(fig)
    return fig


def _bv(got: dict, case: str) -> float:
    row = got.get(case)
    return float("nan") if row is None or row["bv_v"] is None else row["bv_v"]


def section_boxes(struct: dict | None = None) -> dict:
    """The cross-section ``hvsite.section`` gives the structure ``struct`` (default
    :data:`STYLE` ``section_struct``) under assumption AL, as boxes in µm: ``{"width", "sti_depth",
    "boxes": [(kind, x0, x1, depth)], "plates": [(x0, x1, y0, y1)], "contacts": {name: (x0, x1)}}``.
    ``kind`` is ``n-well``, ``ring``, ``p-well``, ``n+`` or ``p+``; a box reaches down to its
    implant's peak plus :data:`STYLE` ``box_sigmas`` standard deviations."""
    hvsite = _load("hvsite")
    p = hvsite.section(
        struct or STYLE["section_struct"], {"pwell": "everywhere", "deep_p_where": "dnw"}
    )
    width, edge = p["width"], 8.0
    boxes = []
    for sign, items in (("n", p["wells"]), ("p", p["pfield"])):
        for w in items:
            x0, x1 = max(w["x0"], 0.0), min(w["x1"], width)
            heavy = w["peak"] >= 1e19
            if sign == "n":
                kind = "n+" if heavy else ("n-well" if w["x0"] < edge <= w["x1"] else "ring")
                if not heavy and w["x1"] < edge:
                    kind = "n-well"
            else:
                kind = "p+" if heavy else "p-well"
            boxes.append((kind, x0, x1, w["rp"] + STYLE["box_sigmas"] * w["sy"]))
    return {
        "width": width,
        "sti": p["sti"],
        "sti_depth": p["sti_depth"],
        "top": p["ox_top"],
        "boxes": boxes,
        "plates": [(pl["x0"], pl["x1"], pl["y0"], pl["y1"]) for pl in p["plates"]],
        "contacts": {k: tuple(v) for k, v in p["contacts"].items()},
    }


def section_figure(palette: str, root: Path = ROOT):
    """The simulated cross-section of a structure with one floating ring and a Metal1 plate."""
    pal = ef.PALETTES[palette]
    s = section_boxes()
    colours = {"n-well": "electron", "ring": "electron", "n+": "electron", "p-well": "hole",
               "p+": "hole"}  # fmt: skip
    alpha = {"n-well": 0.35, "ring": 0.35, "p-well": 0.35, "n+": 0.9, "p+": 0.9}
    fig = _figure(STYLE["section_in"])
    ax = fig.subplots()
    depth = STYLE["section_depth_um"]
    ax.add_patch(matplotlib.patches.Rectangle((0, 0), s["width"], depth, fc=pal["band"], ec="none",
                                              alpha=0.5, gid="substrate"))  # fmt: skip
    seen = set()
    order = {"n-well": 0, "ring": 0, "p-well": 0, "n+": 1, "p+": 1}
    for kind, x0, x1, d in sorted(s["boxes"], key=lambda b: (order[b[0]], -b[3])):
        label = None if kind in seen else {"ring": "floating N-well ring"}.get(kind, kind)
        seen.add(kind)
        ax.add_patch(matplotlib.patches.Rectangle(
            (x0, 0), x1 - x0, d, fc=pal[colours[kind]], ec=pal["text"], lw=0.6,
            alpha=alpha[kind], label=label, hatch="//" if kind == "ring" else None,
            gid=f"{kind} {x0:g}"))  # fmt: skip
    for k, (x0, x1) in enumerate(s["sti"]):
        ax.add_patch(matplotlib.patches.Rectangle(
            (x0, 0), x1 - x0, s["sti_depth"], fc=pal["highlight_oxide"], ec="none", alpha=0.8,
            label=None if k else "trench oxide", gid=f"sti {x0:g}"))  # fmt: skip
    for x0, x1, y0, y1 in s["plates"]:
        ax.add_patch(matplotlib.patches.Rectangle(
            (x0, y0), x1 - x0, y1 - y0, fc=pal["highlight"], ec=pal["text"], lw=0.6,
            label="Metal1 plate, tied to the well", gid=f"plate {x0:g}"))  # fmt: skip
    for name, (x0, x1) in s["contacts"].items():
        ax.plot([x0, x1], [0, 0], color=pal["text"], lw=3, solid_capstyle="butt",
                gid=f"contact {name}")  # fmt: skip
        ax.annotate(f"{name} contact", ((x0 + x1) / 2, 0), ((x0 + x1) / 2, STYLE["label_y_um"]),
                    ha="center", fontsize=STYLE["legend_pt"],
                    arrowprops={"arrowstyle": "-", "color": pal["text"], "lw": 0.8})  # fmt: skip
    ax.axvline(0, color=pal["muted"], ls="--", lw=1)
    ax.set_xlim(0, s["width"])
    ax.set_ylim(depth, -s["top"])
    ax.set_xlabel("x, along the surface (µm)")
    ax.set_ylabel("y, depth (µm)")
    fig.legend(loc="outside lower center", ncols=3, frameon=False, fontsize=STYLE["legend_pt"])
    return fig


def integral_figure(palette: str, root: Path = ROOT):
    """The largest electron ionisation integral against the reverse bias, for four cases, with
    the line at 1 that defines the breakdown voltage."""
    pal = ef.PALETTES[palette]
    got = cases(root)
    fig = _figure(STYLE["size_in"])
    ax = fig.subplots()
    colours = ("hole", "electron", "highlight", "highlight_oxide")
    for case, colour, marker in zip(STYLE["curve_cases"], colours, "osD^", strict=True):
        row = got.get(case)
        if row is None:
            continue
        v, i = np.array(row["v"]), np.array(row["i_n"])
        keep = i > 0
        ax.plot(v[keep], i[keep], color=pal[colour], marker=marker, ms=STYLE["marker_pt"] - 3,
                lw=STYLE["line_width"], label=case.replace("|", " | "), gid=case)  # fmt: skip
    ax.axhline(1.0, color=pal["text"], ls="--", lw=1, gid="unity")
    ax.set_yscale("log")
    ax.set_ylim(1e-6, 3)
    ax.set_xlabel("reverse bias of the well (V)")
    ax.set_ylabel("largest ionisation integral")
    ax.grid(True)
    if ax.get_legend_handles_labels()[0]:
        fig.legend(loc="outside lower center", ncols=2, frameon=False,
                   fontsize=STYLE["legend_pt"])  # fmt: skip
    return fig


def _series(ax, pal, got, points, process, shape, colour, marker, label):
    """One line of breakdown voltage against a drawn dimension: ``points`` is [(x, row)]."""
    xs = [x for x, _ in points]
    ys = [_bv(got, f"{row}|{process}|{shape}") for _, row in points]
    ax.plot(xs, ys, color=pal[colour], marker=marker, ms=STYLE["marker_pt"],
            lw=STYLE["line_width"], ls="-" if shape == "edge" else "--",
            mfc=pal[colour] if shape == "edge" else "none", label=label,
            gid=f"{label} {process} {shape}")  # fmt: skip


def _is_copy(name: str) -> bool:
    """Whether a structure is a copy or a control of another one: a name of a plate or ring
    structure that ends in ``b``, ``L`` or ``C0`` after its size."""
    return re.search(r"_\d+(p\d+)?(b|L|C0)$", name) is not None


def pwell_points() -> dict[str, list[tuple[float, str]]]:
    """Per well kind, [(drawn P-well distance in µm, structure)] of the structures that differ
    from the plain 20 µm termination only by a drawn P-well."""
    out = {"nw": [], "dnw": []}
    for name, st in structures().items():
        if group(name) in ("pwell", "deep") and st["pwell_gap"] is not None and not st["plates"]:
            out[st["kind"]].append((st["pwell_gap"], name))
    return {k: sorted(v) for k, v in out.items()}


def pwell_figure(palette: str, root: Path = ROOT):
    """Breakdown voltage against the distance of a drawn P-well, assumption BL."""
    pal = ef.PALETTES[palette]
    got = cases(root)
    pts = pwell_points()
    fig = _figure(STYLE["size_in"])
    ax = fig.subplots()
    for kind, colour, marker, label in (("nw", "electron", "o", "N-well"),
                                        ("dnw", "hole", "s", "deep N-well")):  # fmt: skip
        for shape in ("edge", "corner"):
            _series(ax, pal, got, pts[kind], "BL", shape, colour, marker, f"{label}, {shape}")
    ax.set_xlabel("drawn P-well distance from the well edge (µm)")
    ax.set_ylabel("breakdown voltage (V)")
    ax.set_ylim(bottom=0)
    ax.grid(True)
    fig.legend(loc="outside lower center", ncols=2, frameon=False, fontsize=STYLE["legend_pt"])
    return fig


def plate_points() -> dict[str, list[tuple[float, str]]]:
    """Per layer, [(plate length beyond the well edge in µm, structure)] of the N-wells with one
    plate tied to the well and nothing else drawn; length 0 is the plain termination NT20."""
    out = {"poly": [(0.0, "NT20")], "m1": [(0.0, "NT20")], "m2": [(0.0, "NT20")]}
    for name, st in structures().items():
        if _is_copy(name):
            continue
        if group(name) == "plates" and len(st["plates"]) == 1 and not st["gate"]:
            ((layer, length),) = st["plates"].items()
            out[layer].append((length, name))
    return {k: sorted(v) for k, v in out.items()}


def plate_figure(palette: str, root: Path = ROOT):
    """Breakdown voltage against the length of a single field plate, by layer, assumption BL."""
    pal = ef.PALETTES[palette]
    got = cases(root)
    fig = _figure(STYLE["size_in"])
    ax = fig.subplots()
    for (layer, pts), colour, marker, label in zip(
        plate_points().items(), ("hole", "electron", "highlight"), "o^s",
        ("Poly2", "Metal1", "Metal2"), strict=True):  # fmt: skip
        for shape in ("edge", "corner"):
            _series(ax, pal, got, pts, "BL", shape, colour, marker, f"{label}, {shape}")
    ax.set_xlabel("plate length beyond the well edge (µm)")
    ax.set_ylabel("breakdown voltage (V)")
    ax.set_ylim(bottom=0)
    ax.grid(True)
    fig.legend(loc="outside lower center", ncols=3, frameon=False, fontsize=STYLE["legend_pt"])
    return fig


def ring_points() -> dict[str, list[tuple[float, str]]]:
    """``count``: [(number of 2 µm rings, structure)] of the ring sets whose first gap is 2 µm,
    with NT20 at 0; ``gap``: [(gap in µm, structure)] of the single 2 µm rings."""
    count, gap = [(0.0, "NT20")], []
    for name, st in structures().items():
        rings = st["rings"]
        if not rings or st["plates"] or {w for _, w in rings} != {2.0} or _is_copy(name):
            continue
        if len(rings) == 1 and not name.startswith("NR1S"):
            gap.append((rings[0][0], name))
        if rings[0][0] == 2.0 and not name.startswith("NR1S"):
            count.append((float(len(rings)), name))
    return {"count": sorted(count), "gap": sorted(gap)}


def ring_figure(palette: str, root: Path = ROOT):
    """Breakdown voltage against the number of floating rings and against the gap of a single
    ring, assumption BL."""
    pal = ef.PALETTES[palette]
    got = cases(root)
    pts = ring_points()
    fig = _figure(STYLE["size_in"])
    left, right = fig.subplots(1, 2, sharey=True)
    for ax, name, xlabel in ((left, "count", "number of rings, first gap 2 µm"),
                             (right, "gap", "gap of a single ring (µm)")):  # fmt: skip
        for shape in ("edge", "corner"):
            _series(ax, pal, got, pts[name], "BL", shape, "electron", "o", shape)
        ax.set_xlabel(xlabel)
        ax.grid(True)
    left.set_ylabel("breakdown voltage (V)")
    left.set_ylim(bottom=0)
    handles, labels = left.get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncols=2, frameon=False,
               fontsize=STYLE["legend_pt"])  # fmt: skip
    return fig


def corner_points() -> dict[str, list[tuple[float, str]]]:
    """Per well kind, [(simulated corner radius in µm, structure)] of the corner structures
    (NC, DC) and of the plain 20 µm terminations NT20 and DT20; a drawn radius below 2 µm is
    simulated at ``predict.MIN_CORNER``."""
    out = {"nw": [], "dnw": []}
    for name, st in structures().items():
        if re.fullmatch(r"[ND]C\d+|[ND]T20", name):
            out[st["kind"]].append((max(st["corner"], _predict().MIN_CORNER), name))
    return {k: sorted(v) for k, v in out.items()}


def corner_figure(palette: str, root: Path = ROOT):
    """Breakdown voltage of the cylindrical corner section against its radius, assumption BL, with
    the straight edge's value as a horizontal line."""
    pal = ef.PALETTES[palette]
    got = cases(root)
    fig = _figure(STYLE["size_in"])
    ax = fig.subplots()
    for (kind, pts), colour, marker, label in zip(
        corner_points().items(), ("electron", "hole"), "os", ("N-well", "deep N-well"),
        strict=True):  # fmt: skip
        _series(ax, pal, got, pts, "BL", "corner", colour, marker, f"{label}, corner")
        edge = _bv(got, f"{'NT20' if kind == 'nw' else 'DT20'}|BL|edge")
        ax.axhline(edge, color=pal[colour], lw=STYLE["line_width"], ls="-",
                   label=f"{label}, straight edge", gid=f"{kind} edge")  # fmt: skip
    ax.set_xlabel("corner radius (µm)")
    ax.set_ylabel("breakdown voltage (V)")
    ax.set_ylim(bottom=0)
    ax.grid(True)
    fig.legend(loc="outside lower center", ncols=2, frameon=False, fontsize=STYLE["legend_pt"])
    return fig


def _svg_of(draw: Callable) -> Callable[[str, Path], bytes]:
    def svg(palette: str, root: Path = ROOT) -> bytes:
        with matplotlib.rc_context(ef.palette_rc(palette)):
            return ef.svg_bytes(draw(palette, root))

    svg.__doc__ = f":func:`{draw.__name__}` as SVG bytes, saved inside the palette's rc context."
    return svg


FIGURES: dict[str, Callable[[str, Path], bytes]] = {
    "section": _svg_of(section_figure),
    "integral": _svg_of(integral_figure),
    "pwell-distance": _svg_of(pwell_figure),
    "plates": _svg_of(plate_figure),
    "rings": _svg_of(ring_figure),
    "corners": _svg_of(corner_figure),
}


def write_all(out_dir: Path, root: Path = ROOT) -> None:
    """Write every figure of :data:`FIGURES` as ``<name>-light.svg`` and ``<name>-dark.svg``,
    from the records under ``root``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, draw in FIGURES.items():
        for palette in ef.PALETTES:
            (out / f"{name}-{palette}.svg").write_bytes(draw(palette, root))


if __name__ == "__main__":
    if sys.argv[1:] != ["tables"]:
        sys.exit("usage: python -m gf180tcad.hvjunction_figures tables")
    print(f"{PAGE}: {'rewritten' if write_tables() else 'unchanged'}")
