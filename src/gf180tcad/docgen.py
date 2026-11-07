# SPDX-License-Identifier: Apache-2.0
"""Generate the results pages of the documentation from the committed results.

``generate`` is called by ``docs/conf.py`` at the start of every documentation build. It reads
only committed files (``results/spice/**``, ``results/tcad/**``, ``data/pdk_elec_spec.json``,
``data/process/*.toml``) and writes only the output directory it is given
(``docs/_generated``). Nothing here is a published result: the tables and plots are
presentation of the committed datasets. The one derived quantity of the SPICE pages, the
ngspice-vs-Xyce maximum relative difference, is computed with
:func:`~gf180tcad.spice.xyce.engine_diff` on the host from the committed CSVs.

The TCAD pages (:func:`generate_tcad`, under ``tcad/``) render the MOS capacitor calibration,
validation and mesh convergence. Every TCAD-vs-SPICE number and verdict on them is read from
the committed calibration and validation files, which were computed in the TCAD image; this
module never compares TCAD with SPICE itself. For the plots it applies the fixed BSIM4
bookkeeping (:meth:`gf180tcad.tcad.moscap1d.MoscapCV.area_scaled`, the function the
calibration uses) to the committed 1D C per area. A geometry page draws the mesh of each 2D
cell from its committed reduced mesh artefact (``results/tcad/meshes/<image>/...``,
:mod:`gf180tcad.meshcut`), never from a full mesh, which is not committed; a 2D cell without an
artefact gets a sentence that says why.

Every figure of these pages is drawn by :mod:`gf180tcad.results_figures` from the committed
files and embedded by :func:`figure_pair` as a named light/dark ``{figure}`` pair that the text
cites with ``{numref}`` (spec §10.3). Numbers in tables use :func:`fmt` (fixed significant
figures, locale independent), so the generated text is byte-identical from run to run.
"""

from __future__ import annotations

import json
import math
import os
import shutil
from pathlib import Path

from gf180tcad import metrics, specwindow
from gf180tcad import results_figures as rf
from gf180tcad.devices import DEVICES, Device, Geometry, geometry_id
from gf180tcad.explain.figures import PALETTES
from gf180tcad.known import KNOWN_ENGINE_DIFFS
from gf180tcad.layout import METRICS_NAME
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.spice.xyce import ENGINE_DIFF_FLOOR, ENGINE_DIFF_THRESHOLD

RESULTS = REPO_ROOT / "results" / "spice"
#: Amperes per picoampere, for the current floor the summary page prints in pA.
PICO = 1e-12
TT = "typical"
DIFF_SWEEPS = rf.DIFF_SWEEPS
# Cases explained on the engine cross-check page (nfet BSIM4 version 4.5 vs Xyce 4.6.1).
KNOWN_DIFFS = KNOWN_ENGINE_DIFFS
ENGINE_DOC = "/limitations/engine-cross-check"
SPEC_DOC = "/comparison/pdk-spec-check"

_UNITS = {
    "_ua_per_um": "µA/µm",
    "_pa_per_um": "pA/µm",
    "_mv_per_dec": "mV/dec",
    "_mv_per_v": "mV/V",
    "_ff": "fF",
    "_a": "A",
    "_s": "S",
    "_v": "V",
}


def fmt(x: float, digits: int = 4) -> str:
    """``x`` with ``digits`` significant figures; ``.`` decimal separator whatever the locale."""
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return format(x, f".{digits}g")


def num(x: float, digits: int = 4) -> str:
    """:func:`fmt` for a table cell: the exponent sign is U+2212 MINUS SIGN, which a browser
    never breaks a line at (an ASCII hyphen in ``2.63e-05`` wraps in a narrow column)."""
    return fmt(x, digits).replace("e-", "e−")


# Unit spellings of the data files, as the pages print them.
_UNIT_TEXT = {"fF/um^2": "fF/µm²", "um^2": "µm²", "um": "µm", "cm^-3": "cm⁻³"}


def unit_text(unit: str) -> str:
    """A unit as a page prints it: ``fF/um^2`` becomes ``fF/µm²``, ``um`` becomes ``µm``."""
    return _UNIT_TEXT.get(unit, unit)


# How to read a geometry id, said once on each page whose tables are keyed by it.
_GEOMETRY_ID_TEXT = (
    "A {term}`geometry id` gives W and L in µm, with p for the decimal point: "
    "`w10p0_l0p60` is W = 10 µm, L = 0.6 µm."
)


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    """A pipe table; every cell must hold text (a blank cell is a bug, not a gap)."""
    for r in rows:
        if len(r) != len(header) or any(not str(c).strip() or str(c).strip() == "-" for c in r):
            raise ValueError(f"table row {r} does not fill the columns {header}")
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def _unit(metric: str) -> str:
    if metric.startswith("vt_"):
        return "V"
    for suffix, unit in _UNITS.items():
        if metric.endswith(suffix):
            return unit
    return ""


def _metrics(root: Path, engine: str, corner: str, device: str, gid: str) -> dict:
    """The metrics of one committed ``metrics.json``; FileNotFoundError if it is missing."""
    path = Path(root) / engine / corner / device / gid / METRICS_NAME
    if not path.is_file():
        raise FileNotFoundError(f"missing result file {path}")
    return json.loads(path.read_text(encoding="utf-8"))["metrics"]


# --- figures -------------------------------------------------------------------------------


def figure_pair(ddir: Path, stem: str, draw, args: tuple, label: str, alt: str, caption: str,
                roots: rf.Roots = rf.DEFAULT_ROOTS) -> list[str]:  # fmt: skip
    """Write ``draw(*args, palette, roots)`` (a :mod:`gf180tcad.results_figures` function) as
    ``<stem>-light.svg`` and ``<stem>-dark.svg`` in ``ddir``, and return the page's two
    ``{figure}`` directives: adjacent, the same caption, the light one named ``label`` (the
    house form of spec §10.3, merged into one numbered figure by ``docs/_ext/theme_figures.py``)."""
    lines = []
    for palette in PALETTES:
        name = f"{stem}-{palette}.svg"
        (ddir / name).write_bytes(rf.svg(draw, *args, palette=palette, roots=roots))
        head = [f"```{{figure}} {name}", f":figclass: only-{palette}"]
        if palette == "light":
            head.append(f":name: {label}")
        lines += [*head, f":alt: {alt}", "", caption, "```", ""]
    return lines


def figure_label(*parts: str) -> str:
    """A figure's ``:name:``, unique on the site: ``fig-`` and ``parts`` joined by hyphens."""
    return "-".join(("fig", *parts)).replace("_", "-")


def numref(label: str, page_title: str | None = None) -> str:
    """A ``{numref}`` citation of figure ``label``: "Figure N" on its own page, "Figure N of
    <title>" from another page (``page_title``), as tests/test_doc_links.py requires."""
    if page_title is None:
        return f"{{numref}}`{label}`"
    return f"{{numref}}`Figure %s of {page_title} <{label}>`"


def spice_title(device: Device, g: Geometry) -> str:
    """The title of the SPICE page of one geometry."""
    return f"{device.name}, W/L = {fmt(g.w_um)}/{fmt(g.l_um)} µm"


def spice_label(device: str, gid: str, sweep: str) -> str:
    """The figure label of one sweep on the SPICE page of a geometry."""
    return figure_label("spice", device, gid, sweep)


# --- tables --------------------------------------------------------------------------------


def _interval(lo: float, hi: float) -> str:
    return f"[{fmt(lo)}, {fmt(hi)}]"


# What sets a "Same process" window (specwindow.Window.source), in the words the pages use.
_WINDOW_SOURCE = {
    "spec": "spec",
    "envelope": "corner envelope",
    "hull": "{term}`combined range`",
}


def _spec_entries(spec: dict, device: str, gid: str) -> dict[str, dict]:
    """The compared spec entries of one SPICE geometry; ``per_area`` entries (no geometry, a
    metric SPICE does not extract) are never among them."""
    return {
        e["metric"]: e
        for e in spec["entries"]
        if e["metric"]
        and not e.get("per_area")
        and e["device"] == device
        and e["geometry_id"] == gid
    }


def _tcad_only(spec: dict) -> list[dict]:
    """The ``per_area`` spec entries: metrics SPICE does not extract, compared by the TCAD."""
    return [e for e in spec["entries"] if e["metric"] and e.get("per_area")]


def _metrics_table(root: Path, device: Device, gid: str, spec: dict, envelope: dict) -> list[str]:
    tt = _metrics(root, "ngspice", TT, device.name, gid)
    xy = _metrics(root, "xyce", TT, device.name, gid)
    env = envelope["ngspice"][device.name][gid]
    specs = _spec_entries(spec, device.name, gid)
    values, corners, windows = [], [], []
    for name in sorted(tt):
        lo, hi = env[name]
        key = f"{{term}}`{name}`"
        if name in specs:
            w = specwindow.window(name, specwindow.spec_range(specs[name]), (lo, hi))
            windows.append([key, num(w.lo), num(w.hi), _WINDOW_SOURCE[w.source]])
        else:
            windows.append([key, num(lo), num(hi), _WINDOW_SOURCE["envelope"]])
        if name in xy:
            x = num(xy[name])
        elif name in metrics.CV_METRICS and not rf.has_sweep("xyce", "cv"):
            x = "not applicable"
        else:
            raise KeyError(f"xyce {TT} {device.name} {gid} metrics.json has no {name}")
        values.append([key, _unit(name) or "none", num(tt[name]), x])
        corners.append([key, num(lo), num(hi)])
    return [
        "### Values",
        "",
        (
            "The {term}`TT` value of each metric from both engines. Xyce has no C-V sweep, so "
            f"its {{term}}`Cgg` cells are not applicable ({numref(spice_label(device.name, gid, 'cv'))} "
            "draws ngspice alone)."
        ),
        "",
        *_table(["Metric", "Unit", "TT ngspice", "TT Xyce"], values),
        "",
        "### Corner envelope",
        "",
        (
            "The {term}`corner envelope`: min and max over the five corners (ngspice), in the "
            "unit of the values table."
        ),
        "",
        *_table(["Metric", "Corner min", "Corner max"], corners),
        "",
        "### Same process window",
        "",
        (
            'The {term}`"Same process" window`: the {term}`combined range` of the {term}`PDK` '
            "{term}`spec window` and the corner envelope. The last column says which sets it "
            "({ref}`pdk-same-process-window`)."
        ),
        "",
        (
            "Where the PDK publishes no spec for a metric at this geometry, the window is the "
            "corner envelope alone."
        ),
        "",
        *_table(["Metric", "Window min", "Window max", "Set by"], windows),
    ]


#: The figures of a SPICE geometry page, in page order: (sweep, section title, alt text).
SPICE_FIGURES = (
    ("idvg_lin", "Id-Vg, linear region (idvg_lin)",
     ("Drain current rising with gate voltage above threshold, on a linear and a log axis: a "
     "grey band round a solid line, with a dashed line on it.")),
    ("idvg_sat", "Id-Vg, saturation (idvg_sat)",
     ("Drain current rising with gate voltage above threshold, on a linear and a log axis: a "
     "grey band round a solid line, with a dashed line on it.")),
    ("idvd", "Id-Vd (idvd)",
     ("Drain current rising with drain voltage and levelling off, one coloured curve and band "
     "per gate voltage.")),
    ("cv", "Cgg-Vg (cv)",
     ("Gate capacitance high at both ends of the gate voltage and lower in between: a grey band "
     "round a solid line.")),
)  # fmt: skip


def _sweep_text(device: Device, gid: str, sweep: str, roots: rf.Roots) -> tuple[str, str]:
    """``(sentence, caption)`` of one sweep's figure; its bias values are read from the data."""
    label = numref(spice_label(device.name, gid, sweep))
    where = f"{device.name} `{gid}`"
    if sweep in ("idvg_lin", "idvg_sat"):
        vds = fmt(rf.bias(device.name, gid, sweep, "vd", roots.spice))
        csv = repo_path(
            roots.spice / "ngspice" / rf.TYPICAL / device.name / gid / f"{sweep}.csv",
            roots.spice,
            RESULTS,
        )
        return (
            (
                f"{label} shows |Id| against |Vgs| at |Vds| = {vds} V, read from "
                f"{{repo}}`{sweep}.csv <{csv}>`, on a linear and a log axis."
            ),
            (
                f"|Id| against |Vgs| of {where} at |Vds| = {vds} V and |Vbs| = 0 "
                f"({{repo}}`{sweep}.csv <{csv}>`): a linear axis (top) and a log axis (bottom)."
            ),
        )
    if sweep == "idvd":
        return (
            (
                f"{label} shows |Id| against |Vds| at |Vbs| = 0, one colour for each |Vgs| of "
                "the sweep."
            ),
            f"|Id| against |Vds| of {where} at |Vbs| = 0, each |Vgs| with its own corner band.",
        )
    return (
        (
            f"{label} shows the gate capacitance {{term}}`Cgg` against the sign-flipped Vgs, from "
            "{{ ngspice }} alone."
        ),
        f"Cgg against polarity × Vgs of {where} at 1 MHz: the ngspice corner band and TT line.",
    )


def _geometry_page(roots: rf.Roots, device: Device, g: Geometry, spec: dict, envelope: dict,
                   out: Path):  # fmt: skip
    gid = geometry_id(g)
    ddir = out / "results" / device.name
    ddir.mkdir(parents=True, exist_ok=True)
    first, last = (spice_label(device.name, gid, s) for s in (SPICE_FIGURES[0][0], "cv"))
    lines = [
        f"# {spice_title(device, g)}",
        "",
        (
            f"{{term}}`{device.name}`, {{term}}`geometry <geometry id>` `{gid}` "
            f"({{ref}}`{g.role} <calibration-validation>`). The "
            "{term}`SPICE reference <SPICE reference results>` at 25 C is in "
            "{repo}`results/spice`. Axes are {term}`sign-flipped` (|Vgs|, |Vds|, |Id|), so the "
            "nfet and the pfet look alike. Summary and engine differences: {doc}`../index`."
        ),
        "",
        (
            f"In {numref(first)} to {numref(last)}, the shaded band is the "
            "{term}`corner envelope` of {{ ngspice }}. It is the min-max over the {term}`TT`, "
            "{term}`FF`, {term}`SS <SS corner>`, {term}`FS` and {term}`SF` "
            "{term}`corners <corner>`. The solid line is ngspice TT and the dashed line is "
            "{{ Xyce }} TT. Xyce has no C-V {term}`sweep` ({ref}`results-layout`)."
        ),
        "",
    ]
    for sweep, title, alt in SPICE_FIGURES:
        sentence, caption = _sweep_text(device, gid, sweep, roots)
        draw, args = (
            (rf.idvg_figure, (device.name, gid, sweep))
            if sweep in ("idvg_lin", "idvg_sat")
            else ({"idvd": rf.idvd_figure, "cv": rf.cv_figure}[sweep], (device.name, gid))
        )
        lines += [f"## {title}", "", sentence, ""]
        lines += figure_pair(ddir, f"{gid}_{sweep}", draw, args,
                             spice_label(device.name, gid, sweep), alt, caption, roots)  # fmt: skip
    lines += ["## Metrics", ""]
    lines += _metrics_table(roots.spice, device, gid, spec, envelope)
    lines += [""]
    (ddir / f"{gid}.md").write_bytes("\n".join(lines).encode("utf-8"))


def _spec_status(root, spec: dict) -> list[str]:
    """The TT-against-spec tables: which PDK parameter each metric is, then one table per
    device and geometry (the device and the geometry page are named in its lead-in)."""
    compared = [e for e in spec["entries"] if e["metric"] and not e.get("per_area")]
    names = {}
    for e in compared:
        names.setdefault((e["symbol"], e["metric"]), None)
    lines = [
        "The PDK parameter each metric stands for:",
        "",
        *_table(
            ["PDK parameter", "Metric"],
            [[f"{{term}}`{s}`", f"{{term}}`{m}`"] for s, m in names],
        ),
    ]
    groups: dict[tuple[str, str], list[list[str]]] = {}
    for e in compared:
        v = _metrics(root, "ngspice", TT, e["device"], e["geometry_id"])[e["metric"]]
        lo, hi = specwindow.spec_range(e)
        status = "inside" if lo <= v <= hi else "OUTSIDE"
        groups.setdefault((e["device"], e["geometry_id"]), []).append(
            [f"{{term}}`{e['metric']}`", num(v), num(lo), num(hi), status]
        )
    for (device, gid), rows in groups.items():
        lines += [
            "",
            f"{{term}}`{device}` at geometry {{doc}}`{gid} <{device}/{gid}>`:",
            "",
            *_table(["Metric", "TT ngspice", "Spec min", "Spec max", "Status"], rows),
        ]
    return lines


def _tcad_only_rows(spec: dict) -> list[str]:
    """The "TCAD only" table: the per-area spec entries, with no SPICE value. Their one unit
    is in the header."""
    entries = _tcad_only(spec)
    units = {e["units"] for e in entries}
    if len(units) != 1:
        raise ValueError(f"TCAD-only spec entries in several units {sorted(units)}")
    u = unit_text(units.pop())
    return _table(
        ["Device", "Parameter", "Metric", f"Spec min ({u})", f"Spec max ({u})"],
        [
            [f"{{term}}`{e['device']}`", e["symbol"], f"`{e['metric']}`",
             num(float(e["min"])), num(float(e["max"]))]
            for e in entries
        ],
    )  # fmt: skip


def _engine_table(root) -> list[str]:
    """One engine_diff table per device, keyed by the geometry id: the values
    :func:`gf180tcad.results_figures.engine_diffs` gives, which the summary's figure draws."""
    lines = []
    for device in DEVICES.values():
        diffs = rf.engine_diffs(device.name, root)
        rows = []
        for k, g in enumerate(device.geometries):
            gid = geometry_id(g)
            cells = [f"{{doc}}`{gid} <{device.name}/{gid}>`"]
            for sweep in DIFF_SWEEPS:
                d = diffs[sweep][k]
                cell = num(100 * d, 3)
                if d > ENGINE_DIFF_THRESHOLD:
                    if (device.name, sweep) in KNOWN_DIFFS:
                        cell += f" {{doc}}`(known) <{ENGINE_DOC}>`"
                    else:
                        cell += f" **unexplained** ({{doc}}`{ENGINE_DOC}`)"
                cells.append(cell)
            rows.append(cells)
        lines += [
            "",
            f"{{term}}`{device.name}`:",
            "",
            *_table(["Geometry", *(f"{{term}}`{s}` (%)" for s in DIFF_SWEEPS)], rows),
        ]
    return lines[1:]


#: The Results page (docs/results/index.md), its title and its C-V figure of both transistors.
RESULTS_CV = ("Results", "results-cv-figure")
#: The figure of the summary page: the engine difference of every sweep and geometry.
ENGINE_LABEL = figure_label("spice", "engine-diff")


def _summary_page(roots: rf.Roots, spec: dict, out: Path):
    cv_ref = numref(RESULTS_CV[1], RESULTS_CV[0])
    threshold = fmt(100 * ENGINE_DIFF_THRESHOLD)
    floor_pa = fmt(ENGINE_DIFF_FLOOR / PICO)
    lines = [
        "# SPICE reference results",
        "",
        (
            "Pages generated at documentation build time from the committed {term}`SPICE` "
            "reference dataset ({repo}`results/spice`). It is the "
            "{term}`SPICE reference <SPICE reference results>` that {term}`TCAD` is compared "
            "against ({doc}`/comparison/agreement`)."
        ),
        "",
        (
            "The TCAD results are on "
            "{doc}`/_generated/tcad/index`. They are the {term}`C–V` calibration of the "
            "{term}`MOS capacitors <MOSCAP>` against these {term}`Cgg`-Vg curves "
            f"({{doc}}`/comparison/cv-agreement`). {cv_ref} shows them."
        ),
        "",
        "## TT against the PDK spec",
        "",
        (
            "The {{ ngspice }} {term}`TT` (typical corner) value of each metric the {term}`PDK` "
            "publishes a spec for, against the spec interval ({term}`spec window`). Definitions, "
            f"sources and caveats are on {{doc}}`{SPEC_DOC}`."
        ),
        "",
        _GEOMETRY_ID_TEXT,
        "",
        *_spec_status(roots.spice, spec),
        "",
        "### TCAD only",
        "",
        (
            "Per-area specs with no geometry, for a metric the SPICE reference does not extract. "
            "They are compared with the 1D TCAD plateau C per area, not with {term}`SPICE` "
            "({doc}`/comparison/cv-agreement`)."
        ),
        "",
        'The status of every row is "TCAD only": these specs have no SPICE value.',
        "",
        *_tcad_only_rows(spec),
        "",
        "## ngspice against Xyce",
        "",
        (
            "{term}`engine_diff` {math:numref}`eq-engine-diff` is the largest relative "
            "difference in drain current between {{ ngspice }} and {{ Xyce }} over one "
            "{term}`sweep` ({py:func}`gf180tcad.spice.xyce.engine_diff`):"
        ),
        "",
        "$$",
        r"d = \max_{k} \frac{|I_{n,k} - I_{x,k}|}{\max(|I_{n,k}|, |I_{x,k}|)}",
        "$$ (eq-engine-diff)",
        "",
        "where",
        "",
        "- $d$ is the engine difference of the sweep, dimensionless;",
        "- $I_{n,k}$ is the drain current ngspice gives at bias point $k$, in A;",
        "- $I_{x,k}$ is the drain current Xyce gives at the same bias point, in A;",
        (
            f"- $k$ counts the bias points where either engine gives |Id| > {floor_pa} pA, "
            "dimensionless."
        ),
        "",
        (
            "Both engines run the typical corner at 25 C. The threshold is "
            f"{threshold} % ({{ref}}`comparison-space`). Cases above it that are explained are "
            f"marked known, see {{doc}}`{ENGINE_DOC}`. Anything else above the threshold is "
            f"flagged unexplained in bold. {numref(ENGINE_LABEL)} draws every value of the tables."
        ),
        "",
        *figure_pair(
            out / "results",
            "engine_diff",
            rf.engine_diff_figure,
            (),
            ENGINE_LABEL,
            "Two panels of markers on a log axis, one shape per sweep for each geometry, under "
            "or near a dashed threshold line.",
            f"The engine difference of each sweep at each geometry; the dashed line is the "
            f"{threshold} % threshold.",
            roots,
        ),
        *_engine_table(roots.spice),
        "",
        "## Pages by device and geometry",
        "",
        "```{toctree}",
        ":maxdepth: 1",
        "",
    ]
    for device in DEVICES.values():
        for g in device.geometries:
            lines.append(f"{device.name}/{geometry_id(g)}")
    lines += ["```", ""]
    (out / "results" / "index.md").write_bytes("\n".join(lines).encode("utf-8"))


def generate(out_dir: Path, results_root: Path = RESULTS, tcad_root: Path | None = None) -> None:
    """Write the SPICE pages under ``out_dir/results`` (summary, 12 geometry pages, SVGs), the
    TCAD pages under ``out_dir/tcad`` (:func:`generate_tcad`), the explainer figures under
    ``out_dir/explained`` (:func:`gf180tcad.explain.figures.write_all`), the reproduce pages'
    figures under ``out_dir/reproduce`` (:func:`gf180tcad.imagefig.write_all` and
    :func:`gf180tcad.reproduce_figures.write_all`), the figures of the comparison pages under
    ``out_dir/comparison`` (:func:`gf180tcad.comparison_figures.write_all`) and those of the
    limitations pages under ``out_dir/limitations``
    (:func:`gf180tcad.limitations_figures.write_all`)."""
    from gf180tcad import comparison_figures, imagefig, limitations_figures, reproduce_figures
    from gf180tcad.explain import figures as explained_figures

    out = Path(out_dir)
    shutil.rmtree(out / "results", ignore_errors=True)
    (out / "results").mkdir(parents=True)
    spec = specwindow.load_spec()
    envelope = json.loads((Path(results_root) / specwindow.ENVELOPE_NAME).read_text("utf-8"))
    results_roots = rf.Roots(spice=Path(results_root), tcad=Path(TCAD_RESULTS if tcad_root is None
                                                                  else tcad_root))  # fmt: skip
    for device in DEVICES.values():
        for g in device.geometries:
            _geometry_page(results_roots, device, g, spec, envelope, out)
    _summary_page(results_roots, spec, out)
    generate_tcad(out, TCAD_RESULTS if tcad_root is None else tcad_root, results_root)
    shutil.rmtree(out / "explained", ignore_errors=True)
    explained_figures.write_all(out / "explained")
    shutil.rmtree(out / "reproduce", ignore_errors=True)
    imagefig.write_all(out / "reproduce")
    reproduce_figures.write_all(out / "reproduce")
    shutil.rmtree(out / "comparison", ignore_errors=True)
    roots = comparison_figures.Roots(
        spice=Path(results_root), tcad=TCAD_RESULTS if tcad_root is None else Path(tcad_root)
    )
    comparison_figures.write_all(out / "comparison", roots)
    shutil.rmtree(out / "limitations", ignore_errors=True)
    limitations_figures.write_all(out / "limitations", roots)


# --- TCAD MOS capacitor pages (Task 13a) ------------------------------------------------------
# Rendered from the committed results/tcad/** only. Every verdict, error, crossing shift, window
# and fitted value is read from the calibration and validation files, which were computed in the
# TCAD image; nothing here compares TCAD with SPICE. The one model step done on the host is the
# fixed BSIM4 bookkeeping that turns the committed 1D C per area into a Cgg of one geometry
# (MoscapCV.area_scaled, the same function the calibration uses), for the plots.

TCAD_RESULTS = REPO_ROOT / "results" / "tcad"
CV_DOC = "/comparison/cv-agreement"
# The four checks of a geometry, in page order (gf180tcad.calibrate.cv.verdicts).
CHECKS = (
    ("plateau_acc", "{term}`Accumulation <accumulation>` plateau"),
    ("plateau_inv", "{term}`Inversion <inversion>` plateau"),
    ("dv_dep", "ΔV_dep ({term}`depletion`-side crossing)"),
    ("dv_inv", "ΔV_inv ({term}`inversion`-side crossing)"),
)
# Sources the process files cite on a host that has refused automated clients since
# 2026-10-24: linked to the web.archive.org snapshot the rest of the docs use (docs/conf.py).
_URL_ALIASES = {
    "https://www.bsim.berkeley.edu/BSIM4/BSIM450.zip": (
        "https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip"
    ),
}
#: The .gitignore pattern that keeps the 2D meshes out of git.
MESH_IGNORE = "results/**/mesh.msh"


def gitignore_line(pattern: str) -> int:
    """The line number of ``pattern`` in the repository's .gitignore; ValueError if absent."""
    lines = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for n, line in enumerate(lines, start=1):
        if line.strip() == pattern:
            return n
    raise ValueError(f".gitignore has no line {pattern!r}")


def repo_path(path: Path, root: Path, committed: Path) -> str:
    """The repository path a page links ``path``, a file or folder under the results tree
    ``root``, by. A tree in the repository's ``results/`` folder is linked where it lies. Any
    other tree, a copy elsewhere or a scratch tree inside the checkout, has the layout of the
    committed tree ``committed`` and is linked at the same place in it, whatever its folder is
    named (issue #173). Relative paths are taken from the working directory, as the files are
    read. ValueError if ``path`` is not under ``root``."""
    path, root = (Path(os.path.normpath(Path(p).absolute())) for p in (path, root))
    if not path.is_relative_to(root):
        raise ValueError(f"{path} is not under the results tree {root}")
    rel = path.relative_to(root)
    if root.is_relative_to(REPO_ROOT / "results"):
        return (root.relative_to(REPO_ROOT) / rel).as_posix()
    return (Path(committed) / rel).relative_to(REPO_ROOT).as_posix()


def _mesh_link() -> str:
    """The ``mesh.msh`` file link: the .gitignore line that keeps the 2D meshes out of git."""
    return f"{{repo}}`mesh.msh <.gitignore#L{gitignore_line(MESH_IGNORE)}>`"


# Why a committed 2D cell has no reduced mesh artefact, by its parameter set; MESH stands for
# the mesh file link of _mesh_link().
_NO_ARTEFACT = {
    "start": (
        "The 2D cell at the start values has no mesh picture. Its full mesh (MESH) is not "
        "committed and is in no cache, so no reduced mesh artefact is cut from it "
        "({ref}`moscap2d-mesh-artefact`)."
    ),
    "calibrated": (
        "The 2D cell at the calibrated values has no mesh picture: no reduced mesh artefact is "
        "committed for it ({ref}`moscap2d-mesh-artefact`)."
    ),
}


def _no_artefact(params: str) -> str:
    """The sentence a geometry page prints for a 2D cell at ``params`` with no artefact."""
    return _NO_ARTEFACT[params].replace("MESH", _mesh_link())


_MESH_ALT = (
    "The mesh around the gate of the 2D cell: thousands of small triangles, densest in a thin "
    "band at the silicon surface under the gate, coloured by region: the gate on top, the gate "
    "oxide under it, the insulator beside the gate and the silicon body below."
)


_VERDICT_TERMS = (
    "Verdicts are {term}`Agree`, {term}`Same process` or {term}`Disagree` "
    "({ref}`definition <agreement-verdicts>`)."
)


def _read_json(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"missing result file {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _pct(x: float) -> str:
    return f"{100 * x:.2f} %"


def _mv_num(v: float) -> str:
    """A voltage in mV, signed, for a table column whose header carries the unit."""
    return f"{1e3 * v:+.1f}"


def _pct_num(x: float) -> str:
    """A fraction in %, for a table column whose header carries the unit."""
    return f"{100 * x:.2f}"


def _source_text(src: str) -> str:
    """A process-file source: a card line as text, a URL as a link."""
    if src.startswith("https://"):
        return f"[link]({_URL_ALIASES.get(src, src)})"
    return src


class _Device:
    """The committed TCAD results of one device that its pages render."""

    def __init__(self, tcad_root: Path, device: Device):
        from gf180tcad.tcad import moscap1d, process

        self.device = device
        name = device.name
        self.root = Path(tcad_root)
        self.cal = _read_json(self.root / "calibration" / f"{name}.result.json")
        self.val = _read_json(self.root / "validation" / f"{name}.json")
        self.proc = process.load(name)
        self.start = moscap1d.read(self.root / "moscap1d" / name / "start")
        self.calibrated = moscap1d.read(self.root / "moscap1d" / name / "calibrated")
        self.meshconv = {
            dim: _read_json(self.root / "meshconv" / f"moscap{dim}" / name / "report.json")
            for dim in ("1d", "2d")
        }
        self.corners = _read_json(self.root / "corners" / name / "summary.json")

    def comparison(self, gid: str) -> tuple[dict, str]:
        """``(record, repo path)`` of the committed 1D comparison of one geometry."""
        name = self.device.name
        if gid in self.cal["per_geometry"]:
            return self.cal["per_geometry"][gid], f"results/tcad/calibration/{name}.result.json"
        if gid in self.val["one_d"]:
            return self.val["one_d"][gid], f"results/tcad/validation/{name}.json"
        raise KeyError(f"{name} {gid}: in neither the calibration nor the validation file")

    def two_d(self, gid: str, params: str = "start") -> Path | None:
        """The committed 2D job of one geometry at ``params``, if there is one."""
        job = self.root / "moscap2d" / self.device.name / params / gid
        return job if (job / "cv.meta.json").is_file() else None


# --- TCAD tables ------------------------------------------------------------------------------


def _check_rows(rec: dict, overlay: str) -> list[str]:
    """The plateau checks and the crossing checks, as two tables of bare values; ``overlay`` is
    the label of the page's C-V figure, whose curves the crossings are on."""
    m, reg, tc = rec["metrics"], rec["spice_regions"], rec["tcad_crossings"]
    if set(rec["verdicts"]) != {key for key, _ in CHECKS}:
        raise ValueError(f"checks {sorted(rec['verdicts'])} are not docgen.CHECKS")
    tol = "{term}`Tolerance <tolerance>`"
    na = "not applicable"
    plateau, p_window, p_tight, crossing, c_window = [], [], [], [], []
    for key, label in CHECKS:
        v = rec["verdicts"][key]
        w = v.get("window")
        if key.startswith("plateau_"):
            side = key.removeprefix("plateau_")
            plateau.append(
                [label, _pct_num(v["max_rel"]), str(m[f"plateau_{side}_points"]),
                 num(100 * v["tolerance"]), v["verdict"]]
            )  # fmt: skip
            if w:
                src = ", ".join(w["sources"])
                tt = w["tightest"]
                p_window.append(
                    [label, _WINDOW_SOURCE.get(src, src), "yes" if w["all_inside"] else "no"]
                )
                p_tight.append(
                    [label, num(tt["u"]), num(tt["c_tcad"]), num(tt["lo"]), num(tt["hi"])]
                )
            else:
                p_window.append([label, "none", na])
                p_tight.append([label, na, na, na, na])
        else:
            which = key.replace("dv_", "u_")
            src = _WINDOW_SOURCE.get(w["source"], w["source"]) if w else "none"
            crossing.append(
                [label, _mv_num(v["dv_v"]), num(1e3 * v["tolerance_v"]), src, v["verdict"]]
            )
            c_window.append(
                [label, num(tc[which]), num(reg[which]),
                 num(w["lo"]) if w else na, num(w["hi"]) if w else na]
            )  # fmt: skip
    return [
        "### Plateaus",
        "",
        *_table(["Plateau", "max \\|ΔCgg\\|/Cgg (%)", "Points", f"{tol} (%)", "Verdict"], plateau),
        "",
        (
            "The window that decides {term}`Same process`, and whether the TCAD is inside it "
            "at every plateau bias:"
        ),
        "",
        *_table(["Plateau", "Window set by", "Inside at every bias"], p_window),
        "",
        (
            "The tightest bias u is where the TCAD value is closest to, or furthest past, a "
            "window edge; the window there:"
        ),
        "",
        *_table(
            [
                "Plateau",
                "Tightest u (V)",
                "TCAD C there (fF)",
                "Window min (fF)",
                "Window max (fF)",
            ],
            p_tight,
        ),
        "",
        "### Crossings",
        "",
        *_table(["Crossing", "ΔV (mV)", f"{tol} (mV)", "Window set by", "Verdict"], crossing),
        "",
        (
            f"The crossing biases of the TCAD and the SPICE curves of {numref(overlay)}, and the "
            "window of the crossing:"
        ),
        "",
        *_table(
            ["Crossing", "TCAD u (V)", "SPICE u (V)", "Window min (V)", "Window max (V)"],
            c_window,
        ),
        "",
        (
            "The crossing tolerance is a proposal: no published standard exists "
            "({ref}`the agreement metric <cv-agreement-metric>`). The depletion region has no "
            f"verdict; its max |ΔC|/C, reported only, is {_pct(m['depletion_max_rel'])}."
        ),
    ]


def _regions_rows(rec: dict) -> list[str]:
    """The SPICE regions of one geometry, as the comparison record holds them."""
    r = rec["spice_regions"]
    rows = [
        ["u_fb (V)", fmt(r["u_fb"])],
        ["u_t (V)", fmt(r["u_t"])],
        ["C_acc (fF)", fmt(r["c_acc"])],
        ["C_min (fF)", fmt(r["c_min"])],
        ["u at C_min (V)", fmt(r["u_min"])],
        ["C_inv (fF)", fmt(r["c_inv"])],
        ["C_mid (fF)", fmt(r["c_mid"])],
    ]
    return [
        "The SPICE regions of this geometry, from the result file:",
        "",
        *_table(["Quantity", "Value"], rows),
    ]


# The 2D status of a geometry whose calibrated 2D cell is committed but which the validation
# file does not list (the file was written before the cell; issue #35).
_TWO_D_PENDING = "not compared"
_ISSUE_35 = "[issue #35](https://github.com/mithro/gf180-tcad/issues/35)"


def _two_d_status(d: _Device, gid: str) -> str:
    """The calibrated 2D validation of ``gid``: the verdict, ``_TWO_D_PENDING`` or the
    validation file's status ("not run")."""
    entry = d.val["two_d"].get(gid)
    if entry is None:
        raise KeyError(f"{d.device.name} validation file has no two_d entry for {gid}")
    if entry["status"] == "compared":
        return entry["verdict"]
    if d.two_d(gid, "calibrated") is not None:
        return _TWO_D_PENDING
    return entry["status"]


def tcad_title(name: str, g: Geometry) -> str:
    """The title of the TCAD page of one geometry."""
    return f"{name} MOS capacitor, W/L = {fmt(g.w_um)}/{fmt(g.l_um)} µm"


def tcad_label(name: str, gid: str, figure: str) -> str:
    """The figure label of one figure on the TCAD page of a geometry."""
    return figure_label("tcad", name, gid, figure)


def _tcad_geometry_page(roots: rf.Roots, d: _Device, g: Geometry, out: Path) -> None:
    name, gid = d.device.name, geometry_id(g)
    ddir = out / "tcad" / name
    rec, src = d.comparison(gid)
    causes = rec.get("causes") or []
    cause_text = (
        f" Causes tagged in advance: {', '.join(f'`{c}`' for c in causes)} "
        "({ref}`mismatch taxonomy <mismatch-taxonomy>`)."
        if causes
        else ""
    )
    cgg, split = tcad_label(name, gid, "cgg"), tcad_label(name, gid, "split")
    lines = [
        f"# {tcad_title(name, g)}",
        "",
        (
            f"{{term}}`{name}`, {{term}}`geometry <geometry id>` `{gid}`, a {g.role} geometry "
            f"({{ref}}`calibration-validation`). The 1D {{term}}`TCAD` "
            "{term}`MOS capacitor <MOSCAP>` against the {term}`SPICE` {term}`Cgg`-Vg of "
            "{{ ngspice }} ({term}`TT`, 1 MHz, Vds = 0). Every number and verdict below is read "
            f"from {{repo}}`{src}`; the method is {{doc}}`{CV_DOC}`. Device summary: "
            "{doc}`index`. " + _VERDICT_TERMS
        ),
        "",
        f"Verdict (1D): **{rec['verdict']}**.{cause_text}",
        "",
        "## Cgg-Vg overlay",
        "",
        (
            f"The top of {numref(cgg)} draws the TCAD Cgg of this geometry at the calibrated "
            "and at the start values. It is the committed 1D C per area "
            f"({{repo}}`results/tcad/moscap1d/{name}`) through the fixed {{term}}`BSIM4` "
            "bookkeeping ({py:meth}`gf180tcad.tcad.moscap1d.MoscapCV.area_scaled`). Under it are "
            "the ngspice TT curve and the {term}`corner envelope`, the min-max over the five "
            "{term}`corners <corner>` at each bias. The axis is u = polarity × Vg "
            "({term}`sign-flipped`)."
        ),
        "",
        (
            "The bottom draws the relative error at each plateau bias, as recorded in the result "
            "file. The plateaus, crossings and regions are defined in "
            "{ref}`the agreement metric <cv-agreement-metric>`."
        ),
        "",
        *figure_pair(
            ddir,
            f"{gid}_cgg",
            rf.cgg_figure,
            (name, gid),
            cgg,
            "Two plots: gate capacitance curves against u almost on top of each other in a grey "
            "band, and below them the plateau errors between dashed tolerance lines.",
            f"Top: the TCAD and ngspice Cgg of {name} `{gid}` against u. Bottom: the TCAD error "
            "at each plateau bias, with the {term}`tolerance`.",
            roots,
        ),
        "## Verdicts",
        "",
        *_check_rows(rec, cgg),
        "",
        *_regions_rows(rec),
        "",
        "## Intrinsic and parasitic parts (1D)",
        "",
        (
            f"{numref(split)} splits the calibrated TCAD Cgg into two parts. The intrinsic part "
            "is the C per area times the BSIM4 capacitance area LeffCV × WeffCV ({term}`DLC`, "
            "{term}`DWC`). The parasitic part is the BSIM4 overlap, fringe and {term}`CGBO` "
            "terms ({py:func}`gf180tcad.tcad.moscap1d.parasitic_ff`). The parasitic part is "
            "fixed reference-model bookkeeping, not part of the {term}`parameter budget`."
        ),
        "",
        *figure_pair(
            ddir,
            f"{gid}_split",
            rf.split_figure,
            (name, gid),
            split,
            "Gate capacitance against u: the TCAD total on the SPICE curve, a dashed intrinsic "
            "part under it and a low dotted parasitic part.",
            f"The calibrated TCAD Cgg of {name} `{gid}`, its intrinsic and parasitic parts, and "
            "the ngspice TT Cgg.",
            roots,
        ),
        "## 2D",
        "",
    ]
    status = _two_d_status(d, gid)
    if status == _TWO_D_PENDING:
        lines += [
            f"Calibrated 2D validation: {status}.",
            "",
            (
                "The calibrated 2D cell is committed; the validation file "
                f"({{repo}}`results/tcad/validation/{name}.json`) does not list it ({_ISSUE_35}). "
                "Its comparison is in {ref}`the validation section <cv-agreement-validation>` "
                f"of {{doc}}`{CV_DOC}`."
            ),
        ]
    else:
        lines.append(f"Calibrated 2D validation: {status} ({{doc}}`{CV_DOC}`, {_ISSUE_35}).")
    lines.append("")
    cells = rf.two_d_cells(roots.tcad, name, gid)
    two_d = tcad_label(name, gid, "2d")
    for params in cells:
        meta = _read_json(d.two_d(gid, params) / "cv.meta.json")
        rel = f"results/tcad/moscap2d/{name}/{params}/{gid}"
        lines += [
            (
                f"The committed 2D cell at the {params} values is {{repo}}`{rel}`: "
                f"{meta['node_count']} nodes, mesh sha256 `{meta['mesh_sha256']}`."
            ),
            "",
        ]
        if "with_sd" in meta and "mesh_source" in meta:
            lines += [
                (
                    f"Its source and drain are {'included' if meta['with_sd'] else 'left out'}, "
                    f"and its mesh comes from {{repo}}`{meta['mesh_source']}`."
                ),
                "",
            ]
    if "start" not in cells:
        lines += [
            (
                "No 2D result at the start values is committed for this geometry "
                "({doc}`/limitations/moscap2d`)."
            ),
            "",
        ]
    if cells:
        lines += [
            (
                f"{numref(two_d)} draws the C per area of each 2D cell against the 1D stack at the "
                "same values. Both are TCAD; the 2D C per area divides the per-width Cgg by the "
                "drawn L, with no bookkeeping."
            ),
            "",
            *figure_pair(
                ddir,
                f"{gid}_2d",
                rf.two_d_figure,
                (name, gid),
                two_d,
                "C per area against u of the 2D cell and of the 1D stack, with the cell's curve "
                "higher everywhere and most of all near depletion.",
                f"The C per area of each committed 2D cell of {name} `{gid}`, against the 1D "
                "stack at the same values.",
                roots,
            ),
        ]
    lines += _mesh_section(d, gid, ddir)
    (ddir / f"{gid}.md").write_bytes("\n".join(lines).encode("utf-8"))


# The mesh figures drawn in this process, by the artefact's npz sha256 and the palette.
_MESH_SVG: dict[tuple[str, str], bytes] = {}


def _mesh_section(d: _Device, gid: str, ddir: Path) -> list[str]:
    """The geometry page's mesh pictures: for each committed 2D cell, the figure of its reduced
    mesh artefact in a light and a dark twin (written into ``ddir``), or why it has none."""
    from gf180tcad import meshcut
    from gf180tcad.explain import figures

    name = d.device.name
    cells = [p for p in ("calibrated", "start") if d.two_d(gid, p) is not None]
    if not cells:
        # the 2D section above already says no 2D result is committed: no mesh to show
        return []
    lines = ["### Mesh picture", ""]
    for params in cells:
        found = sorted((d.root / "meshes").glob(f"*/{name}/{params}/{gid}/{meshcut.META}"))
        if not found:
            lines += [_no_artefact(params), ""]
            continue
        adir = found[0].parent
        meta = _read_json(adir / meshcut.META)
        rel = repo_path(adir, d.root, TCAD_RESULTS)
        caption = (
            f"The mesh of the 2D cell at the {params} values, around the gate: "
            f"{meta['triangle_count']} of the full mesh's {meta['full_mesh_triangle_count']} "
            "triangles, kept by the window rule ({ref}`mesh-artefact`). Drawn to scale from "
            f"{{repo}}`{rel}`; full mesh sha256 `{meta['full_mesh_sha256']}`."
        )
        target = f"mesh-{name}-{gid}-{params}"
        lines += [f"{{numref}}`{target}` shows the mesh of the 2D cell at the {params} values.", ""]
        for palette in figures.PALETTES:
            svg = f"{gid}_mesh_{params}-{palette}.svg"
            # cells that share a mesh (W1.6/L0.7 and W10/L0.7) have the same npz: drawn once
            key = (meta["npz_sha256"], palette)
            if key not in _MESH_SVG:
                _MESH_SVG[key] = figures.mesh_artefact(adir, palette)
            (ddir / svg).write_bytes(_MESH_SVG[key])
            head = [f"```{{figure}} {svg}"]
            if palette == "light":
                head.append(f":name: {target}")
            lines += [*head, f":figclass: only-{palette}", f":alt: {_MESH_ALT}", "", caption,
                      "```", ""]  # fmt: skip
    return lines


def _param_rows(d: _Device) -> list[str]:
    cal = d.cal
    values, bounds, kinds = [], [], []
    for p in cal["params"]:
        par = d.proc.params[p]
        lo, hi = cal["bounds"][p]
        hit = cal["bound_hits"].get(p, "no")
        lo_kind, hi_kind = par.bounds_kind or ("not recorded", "not recorded")
        key = f"`{p}`"
        values.append(
            [key, unit_text(par.unit), num(cal["start"][p], 6), num(cal["values"][p], 6), hit]
        )
        bounds.append([key, num(lo), num(hi), f"`{par.provenance}`"])
        kinds.append([key, par.start_kind or "not recorded", lo_kind, hi_kind])
    return [
        *_table(["Parameter", "Unit", "Start", "Fitted", "Bound hit"], values),
        "",
        "The bounds, in the unit of the table above, and the {term}`provenance tag`:",
        "",
        *_table(["Parameter", "Lower bound", "Upper bound", "Tag"], bounds),
        "",
        "Where the start value and each bound come from:",
        "",
        *_table(["Parameter", "Start from", "Lower bound from", "Upper bound from"], kinds),
    ]


def _bookkeeping_rows(d: _Device) -> list[str]:
    """The bookkeeping values as a table, then where each comes from as a second table, one row
    per source (a parameter can have several, and a cell holds one value)."""
    rows, sources = [], []
    for n, p in d.proc.params.items():
        if p.role != "reference-bookkeeping":
            continue
        rows.append([f"`{n}`", num(p.value, 6), unit_text(p.unit), f"`{p.provenance}`"])
        sources += [[f"`{n}`", _source_text(s)] for s in p.source]
    return [
        *_table(["Parameter", "Value", "Unit", "Tag"], rows),
        "",
        "The card line or document each value comes from:",
        "",
        *_table(["Parameter", "Source"], sources),
    ]


def _meshconv_rows(report: dict) -> list[str]:
    """The levels of one mesh-convergence report; the selected level is named below the table."""
    sel = report["selected"]["level"]
    two_d = report["dim"] == 2
    header = ["Level", "Scale", "Nodes", "max change to next finer"]
    if two_d:
        header.append("max \\|2D/1D - 1\\|")
    rows = []
    for i, lv in enumerate(report["levels"]):
        mc = "finest" if lv["max_rel_change"] is None else num(lv["max_rel_change"], 3)
        row = [str(i), num(lv["scale"]), str(lv["node_count"]), mc]
        if two_d:
            a = lv["agreement_1d"]
            row.append("not applicable" if a is None else num(a, 3))
        rows.append(row)
    return [*_table(header, rows), "", f"Level {sel} is the selected mesh."]


# The corner bounds of the three tunables (Task 16a): read from results/tcad/corners/<device>/
# summary.json (gf180tcad.calibrate.corners.summary), never recomputed here.
#: Each tunable's unit on the pages, the factor from its process-file unit and the most
#: significant digits shown: those of the explainer's tables
#: (:data:`gf180tcad.explain.numbers.TUNABLES`), so one quantity reads the same on every page.
CORNER_UNITS = {
    "t_ox_eff_nm": ("nm", 1.0, 4),
    "n_ch_cm3": ("cm⁻³", 1.0, 3),
    "dv_fb_v": ("V", 1.0, 3),
}
#: The mark of a value that sits on a limit of its fit, explained in prose below its table.
LIMIT_MARK = "†"
#: The note below a table holding a :data:`LIMIT_MARK`.
LIMIT_NOTE = f"A value marked {LIMIT_MARK} sits on a limit of its fit: the limit sets it, not the SPICE curve."
#: The tunables with a card shift (the oxide's TOXE, the flat band's VTH0) for the cross-check.
CORNER_SHIFT_TUNABLES = ("t_ox_eff_nm", "dv_fb_v")
#: The name of the generated corner fragment of a device, included by docs/comparison/cv-agreement.md.
CORNER_FRAGMENT = "corners.inc.md"


def _corner_value(name: str, v: float, on_limit: bool = False) -> str:
    """A tunable's value as the explainer prints it (:func:`gf180tcad.explain.numbers.shortest`:
    a typographic minus, a power of ten as × 10ⁿ), with :data:`LIMIT_MARK` when ``on_limit``."""
    from gf180tcad.explain.numbers import shortest

    _unit, factor, digits = CORNER_UNITS[name]
    return shortest(v * factor, "", digits) + (LIMIT_MARK if on_limit else "")


def _corner_label(name: str) -> str:
    return f"`{name}` ({CORNER_UNITS[name][0]})"


def _verdict_term(verdict: str) -> str:
    """A verdict linked to its glossary entry; "not applicable" as it is."""
    return verdict if verdict == "not applicable" else f"{{term}}`{verdict}`"


def _limit_word(hit: str | None) -> str:
    return {"lower": "lower limit", "upper": "upper limit", None: "no"}[hit]


def _with_note(table: list[str]) -> list[str]:
    """``table`` followed by :data:`LIMIT_NOTE` when one of its cells holds :data:`LIMIT_MARK`."""
    return [*table, "", LIMIT_NOTE] if any(LIMIT_MARK in r for r in table) else table


def corner_tables(name: str, summary: dict) -> list[str]:
    """The corner tables of one device from its corner ``summary``
    (:func:`gf180tcad.calibrate.corners.summary`): the bounds and spread of each tunable, the
    corner of each bound and whether it sits on a limit of its fit, the value at each corner, the
    card cross-check of the oxide and the flat band, and the verdicts at each corner. One value
    per cell; the unit is in the row label or the header. A value on a limit of its fit carries
    :data:`LIMIT_MARK`, and :data:`LIMIT_NOTE` follows its table."""
    from gf180tcad.calibrate import cv
    from gf180tcad.calibrate.corners import FIT_CORNERS

    if summary["device"] != name or set(summary["tunables"]) != set(CORNER_UNITS):
        tun = summary["tunables"]
        raise ValueError(f"{name}: the corner summary is of {summary['device']}, {sorted(tun)}")
    tun = {n: summary["tunables"][n] for n in CORNER_UNITS}
    src = f"{{repo}}`results/tcad/corners/{name}/summary.json`"
    corners = [cv.TT, *FIT_CORNERS]
    on = {c: summary["corners"][c]["bound_hits"] for c in corners}
    bounds, where = [], []
    for n, row in tun.items():
        bounds.append([
            _corner_label(n),
            _corner_value(n, row["typical"], n in on[cv.TT]),
            _corner_value(n, row["min"], row["min_at_bound"] is not None),
            _corner_value(n, row["max"], row["max_at_bound"] is not None),
            _corner_value(n, row["spread"]),
        ])  # fmt: skip
        where.append([f"`{n}`", row["min_corner"], _limit_word(row["min_at_bound"]),
                      row["max_corner"], _limit_word(row["max_at_bound"])])  # fmt: skip
    per = [[c, *(_corner_value(n, tun[n]["values"][c], n in on[c]) for n in tun)] for c in corners]
    verdicts, hits = [], []
    for c in corners:
        e = summary["corners"][c]
        held = cv.worst(e["held_out"].values()) if "held_out" in e else "not applicable"
        verdicts.append([c, _verdict_term(e["verdict"]), _verdict_term(held)])
        hits += [f"`{k}` at {c} is on its {v} limit" for k, v in sorted(e["bound_hits"].items())]
    lines = [
        (
            f"From {src}: each fitted number at the {{term}}`typical corner` (the committed "
            "calibration) and the lowest and highest value over the five {term}`corners <corner>`. "
            "The spread is the highest minus the lowest. A lowest or highest value on a limit of "
            "its fit is reported as that limit ({ref}`reproduce-corners`)."
        ),
        "",
        *_with_note(_table(["Number", "Typical", "Lowest", "Highest", "Spread"], bounds)),
        "",
        "The corner of the lowest and the highest value, and whether it sits on a limit of its fit:",
        "",
        *_table(["Number", "Lowest at", "On a limit", "Highest at", "On a limit"], where),
        "",
        "The fitted value at each corner:",
        "",
        *_with_note(_table(["Corner", *(_corner_label(n) for n in tun)], per)),
        "",
    ]
    for n in CORNER_SHIFT_TUNABLES:
        row = tun[n]
        unit = CORNER_UNITS[n][0]
        shifts = [
            [c, _corner_value(n, row["card_shift"][c]),
             _corner_value(n, row["tcad_shift"][c], n in on[c]),
             _corner_value(n, row["shift_difference"][c], n in on[c])]
            for c in FIT_CORNERS
        ]  # fmt: skip
        lines += [
            (
                f"Card cross-check of `{n}`. The table gives the {{term}}`model card`'s shift of "
                "it at each corner, the fit's shift from the typical value, and their difference:"
            ),
            "",
            *_with_note(
                _table(
                    ["Corner", f"Card ({unit})", f"Fit ({unit})", f"Difference ({unit})"], shifts
                )
            ),
            "",
        ]
    lines += [
        (
            "The verdict at each corner against that corner's {term}`SPICE` reference: at the "
            "calibration geometries, and the worst at the held-out geometries (1D):"
        ),
        "",
        *_table(["Corner", "Calibration", "Held out (1D)"], verdicts),
        "",
        (
            "Limit hits: " + "; ".join(hits) + "."
            if hits
            else "No fit, typical or corner, sits on a limit."
        ),
    ]
    return lines


#: The page that shades the three regions of the C-V curve, its title and its figure.
REGIONS_PAGE = ("Accumulation, depletion and inversion", "fig-regions-cv")


def _tcad_device_page(roots: rf.Roots, d: _Device, out: Path) -> None:
    from gf180tcad.calibrate.cv import BOUND_HIT_REL

    bound_rel = f"{BOUND_HIT_REL:.0e}".replace("e-0", "e-")  # 1e-3, as the prose pages write it
    name, cal, val = d.device.name, d.cal, d.val
    ddir = out / "tcad" / name
    ddir.mkdir(parents=True, exist_ok=True)
    opt = cal["optimiser"]
    cox = cal["cox_check"]
    g0 = d.device.geometries[0]
    split = numref(tcad_label(name, geometry_id(g0), "split"), tcad_title(name, g0))
    meshconv = {dim: figure_label("tcad", name, "meshconv", dim) for dim in ("1d", "2d")}
    stack = figure_label("tcad", name, "stack")
    lines = [
        f"# {name} MOS capacitor (TCAD)",
        "",
        (
            f"The {{term}}`TCAD` {{term}}`MOS capacitor <MOSCAP>` of {{term}}`{name}`. This "
            "page gives the {term}`C–V` calibration of its 1D stack against the {term}`SPICE` "
            "{term}`Cgg`-Vg, and its validation at the "
            "{term}`held-out geometries <held-out geometry>`. It also gives the "
            "{term}`mesh convergence` of the 1D and 2D structures."
        ),
        "",
        (
            "Generated from "
            f"{{repo}}`results/tcad/calibration/{name}.result.json`, "
            f"{{repo}}`results/tcad/validation/{name}.json`, {{repo}}`results/tcad/meshconv` "
            f"and the {{term}}`process file` {{repo}}`data/process/{name}.toml`. The method and "
            f"its deviations are on {{doc}}`{CV_DOC}`; summary: {{doc}}`../index`. "
            + _VERDICT_TERMS
        ),
        "",
        (
            f"Verdict of the calibration geometries: **{cal['verdict']}**; of the held-out "
            f"geometries (1D): **{val['verdict_1d']}**."
        ),
        "",
        (
            f"{numref(stack)} draws the calibrated 1D stack: the gate, the {{term}}`gate oxide` and the "
            "body, with the two layers the fit sets highlighted."
        ),
        "",
        *figure_pair(
            ddir,
            "stack",
            rf.stack_figure,
            (name,),
            stack,
            "Three stacked boxes, gate on top, thin gate oxide, body below, each labelled with "
            "its material, thickness and doping; the oxide and body shaded.",
            f"The calibrated 1D stack of {name}; the oxide and the body are the layers the fit "
            "sets.",
            roots,
        ),
        "## Calibrated parameters",
        "",
        (
            f"{{term}}`Parameter budget <parameter budget>` used: {cal['budget_used']} of "
            f"{cal['budget']} per device type. Optimiser: {{{{ scipy }}}} `least_squares` "
            f"{opt['method']} ({{py:data}}`~gf180tcad.calibrate.cv.LSQ`), "
            f'"{opt["message"].replace("`", "")}", {opt["nfev"]} evaluations and '
            f"{opt['njev']} Jacobians, final cost {fmt(opt['cost'])}. A value within "
            f"{bound_rel} of a bound, relative to the bound width, is a bound hit "
            "({py:data}`~gf180tcad.calibrate.cv.BOUND_HIT_REL`)."
        ),
        "",
        (
            "The tag is the {term}`provenance tag`. The kinds say where the start value and each bound come "
            "from ({ref}`process-data-tunables`). A kind is the {term}`model card` (card), "
            "computed from card values (derived), or a project choice."
        ),
        "",
        *_param_rows(d),
        "",
        (
            f"{{term}}`Cox` check: the oxide's own Cox is {fmt(cox['c_ox_ff_per_um2'])} "
            f"fF/µm² ({numref(stack)} draws the oxide). The 1D C per area is "
            f"{fmt(cox['c_per_area_acc_ff_per_um2'])} fF/µm² ({{term}}`accumulation`) and "
            f"{fmt(cox['c_per_area_inv_ff_per_um2'])} fF/µm² ({{term}}`inversion`). Against the "
            f"public spec {_interval(cox['spec']['min'], cox['spec']['max'])} fF/µm² "
            f"([{cox['spec']['section']}]({cox['spec']['source_url']})), the check gives: "
            f"{'inside' if cox['inside'] else 'OUTSIDE'}."
        ),
        "",
        "### Fixed reference bookkeeping",
        "",
        (
            "These {term}`BSIM4` values are not fitted and not part of the budget. They turn the "
            "C per area into a Cgg of one geometry ({term}`DLC`, {term}`DWC`, {term}`XL`, "
            "{term}`XW`). They also give its parasitic part (overlaps, fringe, {term}`CGBO`). "
            f"{split} draws the two parts. Card lines are in the card the process file names; "
            "they are linked line by line on {ref}`process-data-card`."
        ),
        "",
        *_bookkeeping_rows(d),
        "",
        "## Corner bounds",
        "",
        *corner_tables(name, d.corners),
        "",
        "## Geometries",
        "",
        _GEOMETRY_ID_TEXT,
        "",
    ]
    (ddir / CORNER_FRAGMENT).write_bytes("\n".join(corner_tables(name, d.corners) + [""]).encode())
    verdicts, errors, shifts = [], [], []
    for g in d.device.geometries:
        gid = geometry_id(g)
        rec, _ = d.comparison(gid)
        m = rec["metrics"]
        key = f"{{doc}}`{gid} <{gid}>`"
        verdicts.append([key, g.role, rec["verdict"], _two_d_status(d, gid)])
        errors.append(
            [key, _pct_num(m["plateau_acc_max_rel"]), _pct_num(m["plateau_inv_max_rel"]),
             _pct_num(m["depletion_max_rel"])]
        )  # fmt: skip
        shifts.append([key, _mv_num(m["dv_dep_v"]), _mv_num(m["dv_inv_v"])])
    lines += [
        *_table(["Geometry", "Role", "Verdict (1D)", "2D (calibrated)"], verdicts),
        "",
        f"Validation reasons for the 2D column are in {{repo}}`results/tcad/validation/{name}.json`.",
        "",
        (
            "The largest relative error max |ΔCgg|/Cgg in each region; "
            f"{numref(REGIONS_PAGE[1], REGIONS_PAGE[0])} shades the three regions:"
        ),
        "",
        *_table(
            ["Geometry", "Accumulation (%)", "Inversion (%)", "{term}`Depletion <depletion>` (%)"],
            errors,
        ),
        "",
        (
            "ΔV is the shift of the TCAD mid-capacitance crossing from the SPICE one "
            "({ref}`the agreement metric <cv-agreement-metric>`):"
        ),
        "",
        *_table(["Geometry", "ΔV_dep (mV)", "ΔV_inv (mV)"], shifts),
        "",
        "## Mesh convergence",
        "",
        (
            "From {repo}`results/tcad/meshconv` ({doc}`/limitations/mesh-convergence`). Each "
            "level refines every mesh spacing of the previous one ({term}`uniform refinement`). "
            f"In {numref(meshconv['1d'])} and {numref(meshconv['2d'])}, the dashed curves are "
            "the levels not selected."
        ),
        "",
    ]
    for dim in ("1d", "2d"):
        report = d.meshconv[dim]
        lines += [
            f"### {dim.upper()}",
            "",
            (
                f"{numref(meshconv[dim])} draws the {dim.upper()} C per area at each mesh level, "
                "and its change against the next finer level."
            ),
            "",
            *figure_pair(
                ddir,
                f"meshconv_{dim}",
                rf.meshconv_figure,
                (name, f"moscap{dim}"),
                meshconv[dim],
                "C per area against u at each mesh level, the curves on top of each other, and "
                "below them each level's change on a log axis under the criterion line.",
                f"The {dim.upper()} mesh convergence of {name}: the C per area by mesh level "
                "(top) and the change against the next finer level (bottom).",
                roots,
            ),
            *_meshconv_rows(report),
            "",
        ]
        for ex in report.get("excluded_levels", []):
            lines += [
                (
                    f"Level {ex['level']} is not run: it is as large as the 2D cell at L = 10 µm, "
                    "whose equilibrium solve fails. Level "
                    f"{ex['level']} has not been attempted "
                    "([issue #58](https://github.com/mithro/gf180-tcad/issues/58))."
                ),
                "",
                (
                    "Its node counts and estimated run times are on "
                    "{ref}`the mesh-convergence page <mesh-convergence-2d>`."
                ),
                "",
            ]
        if dim == "2d":
            study = report["settings"]["geometry"]
            lines += [
                (
                    f"The 2D study runs at the geometry {{doc}}`{study} <{study}>`. There the 2D "
                    "C per area exceeds {term}`Cox` by the fringe and the source/drain overlap at "
                    "the gate edges ({doc}`/limitations/moscap2d`). The 2D cells use the selected "
                    "level's mesh. Each geometry page draws the mesh of its cells from their "
                    "reduced mesh artefacts."
                ),
                "",
            ]
    lines += ["```{toctree}", ":maxdepth: 1", "", *(geometry_id(g) for g in d.device.geometries)]
    lines += ["```", ""]
    (ddir / "index.md").write_bytes("\n".join(lines).encode("utf-8"))
    for g in d.device.geometries:
        _tcad_geometry_page(roots, d, g, out)


def _tcad_summary_page(devices: list[_Device], out: Path) -> None:
    lines = [
        "# TCAD MOS capacitor results",
        "",
        (
            "Pages generated at documentation build time from the committed {term}`TCAD` "
            "results ({repo}`results/tcad`). They give the {term}`C–V` calibration of the 1D "
            "{term}`MOS capacitor <MOSCAP>` against the {term}`SPICE` {term}`Cgg`-Vg. They also "
            "give its validation at the {term}`held-out geometries <held-out geometry>` "
            f"({{doc}}`{CV_DOC}`)."
        ),
        "",
        (
            "Every verdict is read from "
            "{repo}`results/tcad/calibration` and {repo}`results/tcad/validation`, which were "
            "computed in the {term}`dev-HEAD TCAD image`; these pages only render them. How "
            "each results folder was made: {ref}`tcad-provenance`. " + _VERDICT_TERMS
        ),
        "",
        "## Verdicts (1D)",
        "",
        _GEOMETRY_ID_TEXT,
        "",
    ]
    rows = []
    for d in devices:
        name = d.device.name
        for g in d.device.geometries:
            gid = geometry_id(g)
            rec, _ = d.comparison(gid)
            rows.append(
                [f"{{term}}`{name}`", f"{{doc}}`{gid} <{name}/{gid}>`", g.role, rec["verdict"],
                 _two_d_status(d, gid)]
            )  # fmt: skip
    lines += _table(["Device", "Geometry", "Role", "Verdict (1D)", "2D (calibrated)"], rows)
    statuses = {_two_d_status(d, geometry_id(g)) for d in devices for g in d.device.geometries}
    if _TWO_D_PENDING in statuses:
        two_d_text = (
            "The 2D column is the calibrated 2D validation of each geometry, read from "
            f'{{repo}}`results/tcad/validation`. "{_TWO_D_PENDING}": the calibrated 2D cell is '
            "committed under {repo}`results/tcad/moscap2d`; the validation file does not list "
            f"it ({_ISSUE_35}). Its comparison is in "
            "{ref}`the validation section <cv-agreement-validation>`."
        )
    elif statuses == {"not run"}:
        two_d_text = (
            "The 2D column is the calibrated 2D validation: not run for any geometry, since no "
            "calibrated 2D result is committed ([issue "
            "#35](https://github.com/mithro/gf180-tcad/issues/35)). The committed 2D results "
            "are at the start values only, and are shown on the geometry pages that have one."
        )
    else:
        two_d_text = (
            "The 2D column is the status of the calibrated 2D validation of each geometry, read "
            "from {repo}`results/tcad/validation` ([issue "
            "#35](https://github.com/mithro/gf180-tcad/issues/35))."
        )
    lines += [
        "",
        two_d_text,
        "",
        "## Devices",
        "",
        "```{toctree}",
        ":maxdepth: 2",
        "",
        *(f"{d.device.name}/index" for d in devices),
        "```",
        "",
    ]
    (out / "tcad" / "index.md").write_bytes("\n".join(lines).encode("utf-8"))


def generate_tcad(out_dir: Path, tcad_root: Path = TCAD_RESULTS, spice_root: Path = RESULTS):
    """Write the TCAD summary, device and geometry pages and their SVGs under ``out_dir/tcad``."""
    out = Path(out_dir)
    shutil.rmtree(out / "tcad", ignore_errors=True)
    (out / "tcad").mkdir(parents=True)
    roots = rf.Roots(spice=Path(spice_root), tcad=Path(tcad_root))
    devices = [_Device(tcad_root, device) for device in DEVICES.values()]
    for d in devices:
        _tcad_device_page(roots, d, out)
    _tcad_summary_page(devices, out)


# README.md is read on GitHub, where no docs build runs, so its figures are committed files. Each
# is an explainer figure (gf180tcad.explain.figures) in both palettes; README.md shows them in a
# <picture> whose dark source follows GitHub's dark theme. tests/test_docgen.py fails when a
# committed file differs from what this draws: rerun `make readme-figures` after the results
# change.
#: The folder of README.md's committed figures.
README_FIGURES_DIR = REPO_ROOT / "docs" / "images" / "readme"
#: README figure name -> the explainer figure (:data:`gf180tcad.explain.figures.FIGURES`); each is
#: written as ``<name>-light.svg`` and ``<name>-dark.svg``.
README_FIGURES = {"cell": "parts-cell", "cv": "cv-overview", "pfet-lengths": "calibration-pfet"}


def readme_figures() -> dict[str, bytes]:
    """``{file name: svg bytes}`` of every README figure of :data:`README_FIGURES`, in each
    palette of :data:`gf180tcad.explain.figures.PALETTES`."""
    from gf180tcad.explain import figures as explained_figures

    return {
        f"{name}-{palette}.svg": explained_figures.FIGURES[figure](palette)
        for name, figure in README_FIGURES.items()
        for palette in explained_figures.PALETTES
    }


def write_readme_figures(out_dir: Path = README_FIGURES_DIR) -> list[Path]:
    """Write :func:`readme_figures` into ``out_dir``, removing any other SVG there; return the
    paths written."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    drawn = readme_figures()
    for stale in out.glob("*.svg"):
        if stale.name not in drawn:
            stale.unlink()
    written = []
    for name, svg in drawn.items():
        (out / name).write_bytes(svg)
        written.append(out / name)
    return written


def main(argv: list[str] | None = None) -> int:
    """``python -m gf180tcad.docgen readme-figures [--out DIR]``: write the README's figures."""
    import argparse

    parser = argparse.ArgumentParser(prog="python -m gf180tcad.docgen", description=main.__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    readme = sub.add_parser("readme-figures", help="write the README's committed figures")
    readme.add_argument("--out", type=Path, default=README_FIGURES_DIR)
    args = parser.parse_args(argv)
    for path in write_readme_figures(args.out):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
