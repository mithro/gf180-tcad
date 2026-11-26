# SPDX-License-Identifier: Apache-2.0
"""The numbers and figures of the high-voltage junction page (``docs/results/hv-junction.md``).

Everything is read from the committed records of ``experiments/hv-junction``
(``results/hv-junction/*.json``), the structure list ``experiments/hv-junction/structures.json``
and three host modules of that experiment, loaded from their files: ``hvsite.py`` (the drawn
structure as a cross-section), ``ionize.py`` (the ionisation integral) and ``profile1d.py`` (the
sheet resistance and capacitance of a well profile).

A record that is not committed gives a dash wherever the page prints one of its values, and its
points are missing from the figures; nothing else changes. The records are ``main``, ``supp`` (it
replaces the cases of ``main`` it reruns), ``family``, ``checks``, ``diodes`` and ``charon``.

:func:`substitutions` gives the page's ``{{ hvj_<name> }}`` values, and :func:`write_all` writes
each figure of :data:`FIGURES` as ``<name>-light.svg`` and ``<name>-dark.svg`` into
``docs/_generated/hv-junction/`` at docs build time (:func:`gf180tcad.docgen.generate`).
"""

from __future__ import annotations

import importlib.util
import json
import re
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

#: The records, in the order a later one replaces the cases of an earlier one.
PREDICTION_RECORDS = ("main", "supp", "family")
RECORDS = (*PREDICTION_RECORDS, "checks", "diodes", "charon")
#: The text of a value whose record or case is not committed.
MISSING = "—"

#: The process assumptions of the main cases and of the doping family (``predict.py``).
PROCESSES = ("A", "An", "Aq", "B", "Bq")
FAMILY = ("Alo", "Ahi", "Blo", "Bhi", "Bdp", "Bq3")
#: The structures ``predict.py`` runs under the family (its ``KEY``).
FAMILY_STRUCTURES = ("NT20", "NC0", "NA0p6", "NAM1_6", "NW3", "NR3_2", "NM1_6", "DT20", "DM1_6",
                     "DAo1")  # fmt: skip
#: The check cases of ``checks.py`` and the cases ``charon_batch.py`` ran.
CHECKS = ("bare-f0.1-x128-v2", "bare-f0.1-f64-v2", "bare-f0.1-f64-v4", "bare-f0.1-f64-v5",
          "bare-f0.05-f64-v4", "abut-f0.07", "abut-f0.05", "abut-f0.02")  # fmt: skip
DIODES = {"1e+15": 1e15, "1e+16": 1e16, "1e+17": 1e17}
#: diode1d.py's donor doping of the N+ side (cm^-3), dd.py's intrinsic density (cm^-3) and
#: thermal voltage at 300 K (V): the built-in potential of its diodes.
DIODE_ND, NI, VT = 1e19, 1.0e10, 1.380649e-23 * 300.0 / 1.602176634e-19
CHARON_CASES = ("NT20|A|edge", "NT20|B|edge", "NW1p5|B|edge", "NM1_6|B|edge", "NR1_2|B|edge",
                "DT20|B|edge")  # fmt: skip
CHARON_FIELDS = {"current": "bv_current_v", "integral": "bv_integral_v",
                 "last": "last_converged_v"}  # fmt: skip

# The published anchors of the doping family, each with its public source on the page: the
# N-well sheet resistance window and typical value (ohm/square), the zero-bias capacitance of
# the N-well diode model (F/cm^2), and the typical and minimum N-well breakdown voltage (V).
ANCHORS = {"rs_min": 800.0, "rs_typ": 1000.0, "rs_max": 1200.0, "cj0": 1.4914e-8,
           "bv_typ": 14.0, "bv_min": 10.0, "dnw_model_bv": 30.48}  # fmt: skip
#: The same section on two meshes: an abutting P-well, generated (A) and drawn at no distance (B).
MESH_PAIR = ("NT20|A|edge", "NW0|B|edge")

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
    "curve_cases": ("NT20|A|edge", "NT20|B|edge", "NM1_6|B|edge", "NR3_1p5|B|edge"),
    "analytic_points": 400,
}


def _load(name: str) -> ModuleType:
    """A host module of the experiment, from its file (it is not a package)."""
    spec = importlib.util.spec_from_file_location(f"_hvj_{name}", EXPERIMENT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    the capacitance wells, as ``predict.py`` selects them."""
    data = json.loads((EXPERIMENT / "structures.json").read_text("utf-8"))
    return {k: v for k, v in data.items() if v["kind"] != "open" and v["half"] < 40}


def cases(root: Path = ROOT) -> dict[str, dict]:
    """Every prediction case of the committed records, ``{case name: its row}``; a case of
    ``supp`` replaces the one of ``main`` it reruns."""
    out = {}
    recs = records(root)
    for name in PREDICTION_RECORDS:
        out.update(recs.get(name, {}).get("cases", {}))
    return out


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


#: The columns of each group's table: (process, shape).
COLUMNS = {
    "bare": (("A", "edge"), ("B", "edge"), ("B", "corner"), ("Bq", "edge"), ("Bq", "corner")),
    "pwell": (("A", "edge"), ("B", "edge"), ("B", "corner"), ("Bq", "edge"), ("Bq", "corner")),
    "plates": (("A", "edge"), ("B", "edge"), ("B", "corner"), ("Bq", "edge"), ("Bq", "corner")),
    "rings": (("A", "edge"), ("B", "edge"), ("B", "corner"), ("Bq", "edge"), ("Bq", "corner")),
    "nat": (("A", "edge"), ("An", "edge"), ("An", "corner"), ("Bq", "edge"), ("Bq", "corner")),
    "deep": (("A", "edge"), ("A", "corner"), ("B", "edge"), ("B", "corner"), ("Bq", "edge")),
}
FAMILY_COLUMNS = {
    "family-b": (("Blo", "edge"), ("B", "edge"), ("Bhi", "edge"), ("Bdp", "edge"),
                 ("Bq3", "edge")),
    "family-a": (("Alo", "edge"), ("A", "edge"), ("Ahi", "edge")),
}  # fmt: skip


def key(case: str) -> str:
    """The substitution key of a case: ``hvj_`` and the case name with ``@`` and ``|`` as ``_``."""
    return "hvj_" + re.sub(r"[^0-9A-Za-z]", "_", case)


def table(name: str) -> str:
    """The Markdown rows of the table of group ``name`` (or ``family-a``, ``family-b``), as the page holds them:
    a header, then one row per structure with a substitution per value."""
    if name in FAMILY_COLUMNS:
        columns, names = FAMILY_COLUMNS[name], list(FAMILY_STRUCTURES)
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
        out += [f"{row}|{p}|{s}" for row in FAMILY_STRUCTURES for p, s in columns]
    return out


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


def nwell_anchors() -> dict[str, float]:
    """The N-well profile of ``hvsite.DEFAULT_PROCESS`` in ``profile1d.py``: its sheet
    resistance (ohm/square) and zero-bias junction capacitance (F/cm^2)."""
    hvsite, profile1d = _load("hvsite"), _load("profile1d")
    pr = hvsite.DEFAULT_PROCESS
    um = 1e-4
    y = np.linspace(0, 12 * um, 24001)
    wells = [(g["peak"], g["rp"] * um, g["sy"] * um) for g in pr["nw"]]
    n, total = profile1d.net(y, wells, pr["sub"])
    return {
        "rs": float(profile1d.sheet_resistance(y, n, total)),
        "cj0": float(profile1d.cv(y, n, np.array([0.0]))[0]),
    }


def _two(v: float | None) -> str:
    return MISSING if v is None else f"{v:.2f}"


def substitutions(root: Path = ROOT) -> dict[str, str]:
    """``{"hvj_<name>": text}``: every number the page prints.

    ``hvj_<case>`` (:func:`key`) is :func:`shown` of each case of the records and of each table
    cell; ``hvj_n_<record>`` and ``hvj_n_<record>_missing`` count a prediction record's cases and
    the cases its runs left without a result; ``hvj_chk_<name>`` is a check case's breakdown
    voltage; ``hvj_diode_<doping>`` the 1D diode's, ``hvj_diode_<doping>_analytic`` the
    triangular-field value, ``_vbi`` the built-in potential and ``_applied`` their difference; ``hvj_charon_<case>_<field>`` the Charon values; ``hvj_nw_rs``,
    ``hvj_nw_cj0`` and ``hvj_nw_cj0_pct`` the N-well anchors; ``hvj_abut_pct`` how far the
    abutting junction lies above the published typical value; ``hvj_mesh_pair_pct`` the
    difference of the two meshes of :data:`MESH_PAIR`."""
    recs = records(root)
    got = cases(root)
    out = {key(c): shown(got.get(c)) for c in {*got, *table_cases()}}
    if len(out) != len({*got, *table_cases()}):
        raise ValueError("two case names give one substitution key")
    for name in PREDICTION_RECORDS:
        rec = recs.get(name)
        out[f"hvj_n_{name}"] = MISSING if rec is None else str(len(rec["cases"]))
        out[f"hvj_n_{name}_missing"] = MISSING if rec is None else str(len(rec["not_converged"]))
    checks = recs.get("checks", {}).get("cases", {})
    for name in CHECKS:
        row = checks.get(name)
        out["hvj_chk_" + re.sub(r"[^0-9A-Za-z]", "_", name)] = _two(row and row["bv_v"])
    diodes = recs.get("diodes", {}).get("diodes", {})
    for name, doping in DIODES.items():
        short = name.replace("+", "")
        out[f"hvj_diode_{short}"] = _two(diodes.get(name, {}).get("bv_v"))
        analytic = analytic_diode_bv(doping)
        out[f"hvj_diode_{short}_analytic"] = _two(analytic)
        out[f"hvj_diode_{short}_vbi"] = _two(built_in(doping))
        out[f"hvj_diode_{short}_applied"] = _two(analytic - built_in(doping))
    charon = recs.get("charon", {}).get("cases", {})
    for case in CHARON_CASES:
        for field, source in CHARON_FIELDS.items():
            out[f"{key(case)}_charon_{field}"] = _two(charon.get(case, {}).get(source))
    anchors = nwell_anchors()
    out["hvj_nw_rs"] = f"{anchors['rs']:.0f}"
    out["hvj_nw_cj0"] = f"{anchors['cj0'] * 1e8:.3f}"
    out["hvj_nw_cj0_pct"] = f"{100 * abs(anchors['cj0'] / ANCHORS['cj0'] - 1):.0f}"
    abut, coarse = (got.get(c) for c in MESH_PAIR)
    ok = abut is not None and abut["bv_v"] is not None
    out["hvj_abut_pct"] = f"{100 * (abut['bv_v'] / ANCHORS['bv_typ'] - 1):.0f}" if ok else MISSING
    ok = ok and coarse is not None and coarse["bv_v"] is not None
    out["hvj_mesh_pair_pct"] = f"{100 * (coarse['bv_v'] / abut['bv_v'] - 1):.0f}" if ok else MISSING
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
    :data:`STYLE` ``section_struct``) under assumption A, as boxes in µm: ``{"width", "sti_depth",
    "boxes": [(kind, x0, x1, depth)], "plates": [(x0, x1, y0, y1)], "contacts": {name: (x0, x1)}}``.
    ``kind`` is ``n-well``, ``ring``, ``p-well``, ``n+`` or ``p+``; a box reaches down to its
    implant's peak plus :data:`STYLE` ``box_sigmas`` standard deviations."""
    hvsite = _load("hvsite")
    p = hvsite.section(struct or STYLE["section_struct"], {"pwell": "everywhere"})
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
    fig.legend(loc="outside lower center", ncols=2, frameon=False, fontsize=STYLE["legend_pt"])
    return fig


def _series(ax, pal, got, points, process, shape, colour, marker, label):
    """One line of breakdown voltage against a drawn dimension: ``points`` is [(x, row)]."""
    xs = [x for x, _ in points]
    ys = [_bv(got, f"{row}|{process}|{shape}") for _, row in points]
    ax.plot(xs, ys, color=pal[colour], marker=marker, ms=STYLE["marker_pt"],
            lw=STYLE["line_width"], ls="-" if shape == "edge" else "--",
            mfc=pal[colour] if shape == "edge" else "none", label=label,
            gid=f"{label} {process} {shape}")  # fmt: skip


def pwell_points() -> dict[str, list[tuple[float, str]]]:
    """Per well kind, [(drawn P-well distance in µm, structure)] of the structures that differ
    from the plain 20 µm termination only by a drawn P-well."""
    out = {"nw": [], "dnw": []}
    for name, st in structures().items():
        if group(name) in ("pwell", "deep") and st["pwell_gap"] is not None and not st["plates"]:
            out[st["kind"]].append((st["pwell_gap"], name))
    return {k: sorted(v) for k, v in out.items()}


def pwell_figure(palette: str, root: Path = ROOT):
    """Breakdown voltage against the distance of a drawn P-well, assumption B."""
    pal = ef.PALETTES[palette]
    got = cases(root)
    pts = pwell_points()
    fig = _figure(STYLE["size_in"])
    ax = fig.subplots()
    for kind, colour, marker, label in (("nw", "electron", "o", "N-well"),
                                        ("dnw", "hole", "s", "deep N-well")):  # fmt: skip
        for shape in ("edge", "corner"):
            _series(ax, pal, got, pts[kind], "B", shape, colour, marker, f"{label}, {shape}")
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
        if group(name) == "plates" and len(st["plates"]) == 1 and not st["gate"]:
            ((layer, length),) = st["plates"].items()
            out[layer].append((length, name))
    return {k: sorted(v) for k, v in out.items()}


def plate_figure(palette: str, root: Path = ROOT):
    """Breakdown voltage against the length of a single field plate, by layer, assumption B."""
    pal = ef.PALETTES[palette]
    got = cases(root)
    fig = _figure(STYLE["size_in"])
    ax = fig.subplots()
    for (layer, pts), colour, marker, label in zip(
        plate_points().items(), ("hole", "electron", "highlight"), "o^s",
        ("Poly2", "Metal1", "Metal2"), strict=True):  # fmt: skip
        for shape in ("edge", "corner"):
            _series(ax, pal, got, pts, "B", shape, colour, marker, f"{label}, {shape}")
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
        if not rings or st["plates"] or {w for _, w in rings} != {2.0}:
            continue
        if len(rings) == 1 and not name.startswith("NR1S"):
            gap.append((rings[0][0], name))
        if rings[0][0] == 2.0 and not name.startswith("NR1S"):
            count.append((float(len(rings)), name))
    return {"count": sorted(count), "gap": sorted(gap)}


def ring_figure(palette: str, root: Path = ROOT):
    """Breakdown voltage against the number of floating rings and against the gap of a single
    ring, assumption B."""
    pal = ef.PALETTES[palette]
    got = cases(root)
    pts = ring_points()
    fig = _figure(STYLE["size_in"])
    left, right = fig.subplots(1, 2, sharey=True)
    for ax, name, xlabel in ((left, "count", "number of rings, first gap 2 µm"),
                             (right, "gap", "gap of a single ring (µm)")):  # fmt: skip
        for shape in ("edge", "corner"):
            _series(ax, pal, got, pts[name], "B", shape, "electron", "o", shape)
        ax.set_xlabel(xlabel)
        ax.grid(True)
    left.set_ylabel("breakdown voltage (V)")
    left.set_ylim(bottom=0)
    handles, labels = left.get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncols=2, frameon=False,
               fontsize=STYLE["legend_pt"])  # fmt: skip
    return fig


def corner_points() -> dict[str, list[tuple[float, str]]]:
    """Per well kind, [(simulated corner radius in µm, structure)] of the plain 20 µm
    terminations; a drawn radius below 2 µm is simulated at 2 µm (``predict.MIN_CORNER``)."""
    out = {"nw": [], "dnw": []}
    for name, st in structures().items():
        plain = group(name) in ("bare", "deep") and st["term"] == 20.0 and not st["plates"]
        if plain and st["pwell_gap"] is None and st["nat_gap"] is None:
            out[st["kind"]].append((max(st["corner"], 2.0), name))
    return {k: sorted(v) for k, v in out.items()}


def corner_figure(palette: str, root: Path = ROOT):
    """Breakdown voltage of the cylindrical corner section against its radius, assumption B, with
    the straight edge's value as a horizontal line."""
    pal = ef.PALETTES[palette]
    got = cases(root)
    fig = _figure(STYLE["size_in"])
    ax = fig.subplots()
    for (kind, pts), colour, marker, label in zip(
        corner_points().items(), ("electron", "hole"), "os", ("N-well", "deep N-well"),
        strict=True):  # fmt: skip
        _series(ax, pal, got, pts, "B", "corner", colour, marker, f"{label}, corner")
        edge = _bv(got, f"{'NT20' if kind == 'nw' else 'DT20'}|B|edge")
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
