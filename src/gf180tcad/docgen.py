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
calibration uses) to the committed 1D C per area. No mesh picture is drawn: the 2D meshes are
not committed, and the pages say so.

Plots are drawn against polarity-stripped axes (|Vgs|, |Vds|, |Id|) so the nfet and the pfet
look alike. Numbers in tables use :func:`fmt` (fixed significant figures, locale independent),
so the generated text is byte-identical from run to run.
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np

from gf180tcad import io, metrics, plots, specwindow
from gf180tcad.devices import CORNERS, DEVICES, Device, Geometry, geometry_id
from gf180tcad.known import KNOWN_ENGINE_DIFFS
from gf180tcad.layout import METRICS_NAME
from gf180tcad.reference import engine_sweeps
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.spice.xyce import ENGINE_DIFF_THRESHOLD, engine_diff

RESULTS = REPO_ROOT / "results" / "spice"
TT = "typical"
DIFF_SWEEPS = ("idvg_lin", "idvg_sat", "idvd", "ioff")
# Cases explained on the engine cross-check page (nfet BSIM4 version 4.5 vs Xyce 4.6.1).
KNOWN_DIFFS = KNOWN_ENGINE_DIFFS
ENGINE_DOC = "/limitations/engine-cross-check"
SPEC_DOC = "/comparison/pdk-spec-check"
ID_FLOOR = 1e-15  # A, lower edge of the log-scale panels

_UNITS = {
    "_ua_per_um": "uA/um",
    "_pa_per_um": "pA/um",
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


def _unit(metric: str) -> str:
    if metric.startswith("vt_"):
        return "V"
    for suffix, unit in _UNITS.items():
        if metric.endswith(suffix):
            return unit
    return ""


def _has_sweep(engine: str, sweep: str) -> bool:
    """Does ``engine`` run ``sweep`` at all (Xyce has no cv)? Absent by design, not missing."""
    return sweep in engine_sweeps(engine)


def _cols(root: Path, engine: str, corner: str, device: str, gid: str, sweep: str) -> dict:
    """Columns of one committed CSV; FileNotFoundError if it is missing (never a silent gap)."""
    path = Path(root) / engine / corner / device / gid / f"{sweep}.csv"
    if not path.is_file():
        raise FileNotFoundError(f"missing result file {path}")
    return io.read_csv(path)[0]


def _metrics(root: Path, engine: str, corner: str, device: str, gid: str) -> dict:
    """The metrics of one committed ``metrics.json``; FileNotFoundError if it is missing."""
    path = Path(root) / engine / corner / device / gid / METRICS_NAME
    if not path.is_file():
        raise FileNotFoundError(f"missing result file {path}")
    return json.loads(path.read_text(encoding="utf-8"))["metrics"]


# --- plot data ----------------------------------------------------------------------------


def _series(cols: dict, sweep: str, pol: int) -> list[tuple[str | None, np.ndarray, np.ndarray]]:
    """Polarity-stripped ``(group label, x, y)``: |Id| in A against |Vgs| or |Vds|; cv in fF."""
    if sweep == "cv":
        order = np.argsort(pol * cols["vg"], kind="stable")
        return [(None, (pol * cols["vg"])[order], (cols["cgg"] * 1e15)[order])]
    if sweep in ("idvg_lin", "idvg_sat"):
        m = cols["vb"] == 0.0
        return [(None, pol * cols["vg"][m], np.abs(cols["id"][m]))]
    zero_vb = cols["vb"] == 0.0
    if not np.any(zero_vb):
        raise ValueError("idvd: no vb = 0 rows to plot")
    out = []
    for v in sorted(set(np.abs(cols["vg"][zero_vb]).tolist())):
        m = zero_vb & (np.abs(cols["vg"]) == v)
        out.append((f"|Vgs| = {fmt(v)} V", pol * cols["vd"][m], np.abs(cols["id"][m])))
    return out


def _curves(root: Path, device: Device, gid: str, sweep: str, scale: float, floor: float | None):
    """Band, TT line and Xyce dashed overlay curves for one sweep, as ``plots.Curve`` objects."""
    pol = device.polarity
    per_corner = []
    for corner in CORNERS:
        cols = _cols(root, "ngspice", corner, device.name, gid, sweep)
        per_corner.append(_series(cols, sweep, pol))
    tt = per_corner[CORNERS.index(TT)]
    xs = None
    if _has_sweep("xyce", sweep):
        xs = _series(_cols(root, "xyce", TT, device.name, gid, sweep), sweep, pol)

    def y(a):
        a = a * scale
        return a if floor is None else np.maximum(a, floor)

    multi = len(tt) > 1
    curves, legend = [], {}
    for i, (label, x, ytt) in enumerate(tt):
        color = plots.FAMILY[i % len(plots.FAMILY)] if multi else plots.NGSPICE_COLOR
        xcolor = color if multi else plots.XYCE_COLOR
        stack = []
        for series in per_corner:
            if not np.array_equal(series[i][1], x):
                raise ValueError(f"{device.name} {gid} {sweep}: corner grids differ")
            stack.append(y(series[i][2]))
        curves.append(plots.Curve(x, np.min(stack, axis=0), color, y2=np.max(stack, axis=0)))
        curves.append(plots.Curve(x, y(ytt), color))
        if xs is not None:
            if not np.array_equal(xs[i][1], x):
                raise ValueError(f"{device.name} {gid} {sweep}: Xyce grid differs")
            curves.append(plots.Curve(x, y(xs[i][2]), xcolor, dashed=True))
        if label:
            legend[label] = color
    return curves, legend


def _figures(root: Path, device: Device, gid: str) -> list[tuple[str, str, bytes]]:
    """``(suffix, alt text, svg bytes)`` for the four figures of a geometry page."""
    out = []
    for sweep, vds in (("idvg_lin", "0.1"), ("idvg_sat", "5")):
        lin, _ = _curves(root, device, gid, sweep, 1e3, None)
        log, _ = _curves(root, device, gid, sweep, 1.0, ID_FLOOR)
        panels = [
            plots.Panel(f"Id-Vg, |Vds| = {vds} V, |Vbs| = 0", "|Vgs| (V)", "|Id| (mA)", lin),
            plots.Panel(
                f"Id-Vg, |Vds| = {vds} V, |Vbs| = 0 (log)", "|Vgs| (V)", "|Id| (A)", log, "log",
                (ID_FLOOR, None),
            ),
        ]  # fmt: skip
        out.append(
            (
                sweep,
                f"|Id| against |Vgs| at |Vds| = {vds} V, linear and log",
                plots.figure_svg(panels),
            )
        )
    curves, legend = _curves(root, device, gid, "idvd", 1e3, None)
    panel = plots.Panel("Id-Vd, |Vbs| = 0", "|Vds| (V)", "|Id| (mA)", curves)
    out.append(
        ("idvd", "|Id| against |Vds| for |Vgs| = 1 to 5 V", plots.figure_svg([panel], legend))
    )
    curves, _ = _curves(root, device, gid, "cv", 1.0, None)
    panel = plots.Panel("Cgg-Vg, 1 MHz, ngspice only", "Vgs x polarity (V)", "Cgg (fF)", curves)
    out.append(("cv", "Gate capacitance against polarity-stripped Vgs", plots.figure_svg([panel])))
    return out


def demo_svg() -> bytes:
    """One real figure (nfet_05v0 10/0.6 Id-Vd), for the byte-determinism test."""
    device = DEVICES["nfet_05v0"]
    gid = geometry_id(device.geometries[0])
    curves, legend = _curves(RESULTS, device, gid, "idvd", 1e3, None)
    panel = plots.Panel("Id-Vd, |Vbs| = 0", "|Vds| (V)", "|Id| (mA)", curves)
    return plots.figure_svg([panel], legend)


# --- tables --------------------------------------------------------------------------------


def _interval(lo: float, hi: float) -> str:
    return f"[{fmt(lo)}, {fmt(hi)}]"


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
    rows = [
        (
            "| Metric | Unit | TT ngspice | TT Xyce | Envelope [lo, hi] (5 corners, ngspice) "
            '| {term}`"Same process" window` (set by) |'
        ),
        "|---|---|---|---|---|---|",
    ]
    for name in sorted(tt):
        lo, hi = env[name]
        if name in specs:
            w = specwindow.window(name, specwindow.spec_range(specs[name]), (lo, hi))
            source = "{term}`hull`" if w.source == "hull" else w.source
            sw = f"{_interval(w.lo, w.hi)} ({source})"
        else:
            sw = f"{_interval(lo, hi)} (envelope)"
        if name in xy:
            x = fmt(xy[name])
        elif name in metrics.CV_METRICS and not _has_sweep("xyce", "cv"):
            x = "n/a"
        else:
            raise KeyError(f"xyce {TT} {device.name} {gid} metrics.json has no {name}")
        rows.append(
            f"| {{term}}`{name}` | {_unit(name)} | {fmt(tt[name])} | {x} | {_interval(lo, hi)} "
            f"| {sw} |"
        )
    return rows


def _geometry_page(root, device: Device, g: Geometry, spec: dict, envelope: dict, out: Path):
    gid = geometry_id(g)
    ddir = out / "results" / device.name
    ddir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {device.name}, W/L = {fmt(g.w_um)}/{fmt(g.l_um)} um",
        "",
        (
            f"{{term}}`{device.name}`, {{term}}`geometry <geometry id>` `{gid}` "
            f"({{ref}}`{g.role} <calibration-validation>`). {{term}}`SPICE` reference at 25 C "
            "from {repo}`results/spice`. Axes are {term}`polarity-stripped` (|Vgs|, |Vds|, |Id|), "
            "so the nfet and the pfet look alike. The shaded band is the {term}`corner envelope`, "
            "the min-max over the {term}`TT`, {term}`FF`, {term}`SS <SS corner>`, {term}`FS` and "
            "{term}`SF` {term}`corners <corner>` ({{ ngspice }}); the solid line is ngspice TT "
            "and the dashed line is {{ Xyce }} TT. Xyce has no C-V {term}`sweep` "
            "({ref}`results-layout`). Summary and engine differences: {doc}`../index`."
        ),
        "",
    ]
    titles = {
        "idvg_lin": "Id-Vg, linear region (idvg_lin)",
        "idvg_sat": "Id-Vg, saturation (idvg_sat)",
        "idvd": "Id-Vd (idvd)",
        "cv": "Cgg-Vg (cv)",
    }
    for suffix, alt, svg in _figures(root, device, gid):
        name = f"{gid}_{suffix}.svg"
        (ddir / name).write_bytes(svg)
        lines += [f"## {titles[suffix]}", "", f"![{alt}]({name})", ""]
    lines += ["## Metrics", ""]
    lines += _metrics_table(root, device, gid, spec, envelope)
    lines += [
        "",
        (
            "The last two columns are in the units of the metric. The last column is the "
            '{term}`"Same process" window`: the {term}`hull` of the {term}`PDK` '
            "{term}`spec window` and the corner envelope, and the word in brackets says which "
            "sets it (see {ref}`pdk-same-process-window`). Where the PDK publishes no spec for "
            "this metric at this geometry, the window is the corner envelope alone. Xyce has no "
            "C-V sweep, so its Cgg cells are n/a."
        ),
        "",
    ]
    (ddir / f"{gid}.md").write_bytes("\n".join(lines).encode("utf-8"))


def _spec_status(root, spec: dict) -> list[str]:
    rows = [
        "| Device | Parameter | Metric | TT ngspice | Spec window | Status |",
        "|---|---|---|---|---|---|",
    ]
    for e in spec["entries"]:
        if not e["metric"] or e.get("per_area"):
            continue
        v = _metrics(root, "ngspice", TT, e["device"], e["geometry_id"])[e["metric"]]
        lo, hi = specwindow.spec_range(e)
        status = "inside" if lo <= v <= hi else "OUTSIDE"
        page = f"{e['device']}/{e['geometry_id']}"
        rows.append(
            f"| {{term}}`{e['device']}` {{doc}}`{fmt(e['w_um'])}/{fmt(e['l_um'])} <{page}>` "
            f"| {{term}}`{e['symbol']}` | {{term}}`{e['metric']}` | {fmt(v)} | {_interval(lo, hi)} "
            f"| {status} |"
        )
    return rows


def _tcad_only_rows(spec: dict) -> list[str]:
    """The "TCAD only" table: the per-area spec entries, with no SPICE value."""
    rows = [
        "| Device | Parameter | Metric | Spec [min, max] | Status |",
        "|---|---|---|---|---|",
    ]
    for e in _tcad_only(spec):
        rows.append(
            f"| {{term}}`{e['device']}` | {e['symbol']} | `{e['metric']}` "
            f"| {_interval(float(e['min']), float(e['max']))} {e['units']} | TCAD only |"
        )
    return rows


def _engine_table(root) -> list[str]:
    rows = [
        "| Device | Geometry | " + " | ".join(f"{{term}}`{s}`" for s in DIFF_SWEEPS) + " |",
        "|---|---|" + "---|" * len(DIFF_SWEEPS),
    ]
    for device in DEVICES.values():
        for g in device.geometries:
            gid = geometry_id(g)
            cells = []
            for sweep in DIFF_SWEEPS:
                a = _cols(root, "ngspice", TT, device.name, gid, sweep)
                b = _cols(root, "xyce", TT, device.name, gid, sweep)
                d = engine_diff(a, b)
                cell = f"{fmt(100 * d, 3)} %"
                if d > ENGINE_DIFF_THRESHOLD:
                    if (device.name, sweep) in KNOWN_DIFFS:
                        cell += f" {{doc}}`(known) <{ENGINE_DOC}>`"
                    else:
                        cell += f" **unexplained** ({{doc}}`{ENGINE_DOC}`)"
                cells.append(cell)
            rows.append(
                f"| {{term}}`{device.name}` | {{doc}}`{gid} <{device.name}/{gid}>` | "
                + " | ".join(cells)
                + " |"
            )
    return rows


def _summary_page(root, spec: dict, out: Path):
    lines = [
        "# SPICE reference results",
        "",
        (
            "Pages generated at documentation build time from the committed {term}`SPICE` "
            "reference dataset ({repo}`results/spice`): the {term}`golden reference` that "
            "{term}`TCAD` is compared against ({doc}`/comparison/agreement`). The TCAD results so "
            "far, the {term}`C–V` calibration of the {term}`MOS capacitors <MOSCAP>` against these "
            "{term}`Cgg`-Vg curves, are on {doc}`/_generated/tcad/index` "
            "({doc}`/comparison/cv-agreement`)."
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
        *_spec_status(root, spec),
        "",
        "### TCAD only",
        "",
        (
            "Per-area specs with no geometry, for a metric the SPICE reference does not extract. "
            "They are compared with the 1D TCAD plateau C per area, not with SPICE "
            "({doc}`/comparison/cv-agreement`)."
        ),
        "",
        *_tcad_only_rows(spec),
        "",
        "## ngspice against Xyce",
        "",
        (
            "{term}`engine_diff` between ngspice and {{ Xyce }}: the maximum relative difference "
            "|Id,ngspice - Id,Xyce| / max(|Id,ngspice|, |Id,Xyce|) over the bias points where "
            "either engine gives |Id| > 1 pA, at the typical corner and 25 C, for each "
            "{term}`sweep` ({py:func}`gf180tcad.spice.xyce.engine_diff`). The threshold is 0.5 % "
            "({ref}`comparison-space`). Cases above it "
            f"that are explained are marked known, see {{doc}}`{ENGINE_DOC}`. Anything else "
            "above the threshold is flagged unexplained in bold."
        ),
        "",
        *_engine_table(root),
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
    """Write the SPICE pages under ``out_dir/results`` (summary, 12 geometry pages, SVGs) and
    the TCAD pages under ``out_dir/tcad`` (:func:`generate_tcad`)."""
    out = Path(out_dir)
    shutil.rmtree(out / "results", ignore_errors=True)
    (out / "results").mkdir(parents=True)
    spec = specwindow.load_spec()
    envelope = json.loads((Path(results_root) / specwindow.ENVELOPE_NAME).read_text("utf-8"))
    for device in DEVICES.values():
        for g in device.geometries:
            _geometry_page(results_root, device, g, spec, envelope, out)
    _summary_page(results_root, spec, out)
    generate_tcad(out, TCAD_RESULTS if tcad_root is None else tcad_root, results_root)


# --- TCAD MOS capacitor pages (Task 13a) ------------------------------------------------------
# Rendered from the committed results/tcad/** only. Every verdict, error, crossing shift, window
# and fitted value is read from the calibration and validation files, which were computed in the
# TCAD image; nothing here compares TCAD with SPICE. The one model step done on the host is the
# fixed BSIM4 bookkeeping that turns the committed 1D C per area into a Cgg of one geometry
# (MoscapCV.area_scaled, the same function the calibration uses), for the plots.

TCAD_RESULTS = REPO_ROOT / "results" / "tcad"
CV_DOC = "/comparison/cv-agreement"
TCAD_COLOR = "#009E73"  # calibrated TCAD
START_COLOR = "#E69F00"  # TCAD at the start values
INTRINSIC_COLOR = "#56B4E9"
PARASITIC_COLOR = "#CC79A7"
TOL_COLOR = "#555555"
# The four checks of a geometry, in page order (gf180tcad.calibrate.cv.verdicts).
CHECKS = (
    ("plateau_acc", "Accumulation plateau"),
    ("plateau_inv", "Inversion plateau"),
    ("dv_dep", "ΔV_dep (depletion-side crossing)"),
    ("dv_inv", "ΔV_inv (inversion-side crossing)"),
)
# Sources the process files cite on a host that has refused automated clients since
# 2026-10-24: linked to the web.archive.org snapshot the rest of the docs use (docs/conf.py).
_URL_ALIASES = {
    "https://www.bsim.berkeley.edu/BSIM4/BSIM450.zip": (
        "https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip"
    ),
}
_NO_MESH = (
    "No mesh picture: the 2D meshes (`mesh.msh`) are not committed (git-ignored, "
    "{ref}`for their size <moscap2d-meshes>`), and this page renders only committed files. A "
    "{term}`job`'s `cv.meta.json` records the sha256 of its mesh, from which it regenerates "
    "byte for byte. The design spec asks for mesh pictures here: a recorded "
    "{ref}`deviation <limitations-spec-deviations>`, "
    "[issue #39](https://github.com/mithro/gf180-tcad/issues/39)."
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


def _mv(v: float) -> str:
    return f"{1e3 * v:+.1f} mV"


def _pct(x: float) -> str:
    return f"{100 * x:.2f} %"


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


def _u_sorted(vg, pol: int, *ys) -> list[np.ndarray]:
    """``u = polarity * vg`` ascending, and each of ``ys`` in the same order."""
    u = pol * np.asarray(vg, dtype=float)
    order = np.argsort(u, kind="stable")
    return [u[order], *(np.asarray(y, dtype=float)[order] for y in ys)]


def _spice_cv(spice_root: Path, device: Device, gid: str) -> list[plots.Curve]:
    """ngspice corner envelope (band) and TT (line) of the cv sweep, against u."""
    curves, _ = _curves(spice_root, device, gid, "cv", 1.0, None)
    return curves


def _tcad_total(d: _Device, g: Geometry, which: str):
    m = d.calibrated if which == "calibrated" else d.start
    vg, intrinsic, parasitic, total = m.area_scaled(g, d.proc)
    return _u_sorted(vg, d.device.polarity, intrinsic, parasitic, total)


_U_LABEL = "u = polarity x Vg (V)"
_SPICE_KEYS = (
    plots.Key("ngspice TT", plots.NGSPICE_COLOR),
    plots.Key("ngspice corner envelope", plots.NGSPICE_COLOR, "band"),
)


def _cgg_svg(spice_root: Path, d: _Device, g: Geometry, rec: dict) -> bytes:
    gid = geometry_id(g)
    u, _, _, cal = _tcad_total(d, g, "calibrated")
    us, _, _, start = _tcad_total(d, g, "start")
    overlay = plots.Panel(
        "Cgg-Vg: 1D TCAD against ngspice",
        _U_LABEL,
        "Cgg (fF)",
        [
            *_spice_cv(spice_root, d.device, gid),
            plots.Curve(us, start, START_COLOR, dashed=True),
            plots.Curve(u, cal, TCAD_COLOR),
        ],
        keys=[
            *_SPICE_KEYS,
            plots.Key("TCAD calibrated", TCAD_COLOR),
            plots.Key("TCAD start values", START_COLOR, "dashed"),
        ],
    )
    res = rec["residuals"]
    # each plateau's points, and its own tolerance drawn over its own span
    curves, tols = [], {}
    for side in ("acc", "inv"):
        u = np.array(res[f"plateau_{side}_u"])
        tol = 100 * rec["verdicts"][f"plateau_{side}"]["tolerance"]
        tols[side] = tol
        span = np.array([u.min(), u.max()])
        curves += [
            plots.Curve(u, 100 * np.array(res[f"plateau_{side}_rel"]), TCAD_COLOR),
            plots.Curve(span, np.array([tol, tol]), TOL_COLOR, dashed=True),
            plots.Curve(span, np.array([-tol, -tol]), TOL_COLOR, dashed=True),
        ]
    if tols["acc"] == tols["inv"]:
        tol_keys = [plots.Key(f"tolerance ±{fmt(tols['acc'])} %", TOL_COLOR, "dashed")]
    else:
        tol_keys = [
            plots.Key(f"tolerance ({side}) ±{fmt(t)} %", TOL_COLOR, "dashed")
            for side, t in tols.items()
        ]
    errors = plots.Panel(
        "Plateau errors (from the result file)",
        _U_LABEL,
        "(TCAD - SPICE) / SPICE (%)",
        curves,
        keys=[plots.Key("TCAD calibrated, plateau points", TCAD_COLOR), *tol_keys],
    )
    return plots.figure_svg([overlay, errors])


def _split_svg(spice_root: Path, d: _Device, g: Geometry) -> bytes:
    gid = geometry_id(g)
    u, intrinsic, parasitic, total = _tcad_total(d, g, "calibrated")
    spice = [c for c in _spice_cv(spice_root, d.device, gid) if c.y2 is None]
    panel = plots.Panel(
        "Calibrated 1D TCAD Cgg: intrinsic and parasitic parts",
        _U_LABEL,
        "Cgg (fF)",
        [
            *spice,
            plots.Curve(u, total, TCAD_COLOR),
            plots.Curve(u, intrinsic, INTRINSIC_COLOR),
            plots.Curve(u, parasitic, PARASITIC_COLOR),
        ],
        keys=[
            plots.Key("ngspice TT", plots.NGSPICE_COLOR),
            plots.Key("TCAD total", TCAD_COLOR),
            plots.Key("intrinsic: C per area x LeffCV x WeffCV", INTRINSIC_COLOR),
            plots.Key("parasitic: overlap, fringe, gate-bulk", PARASITIC_COLOR),
        ],
    )
    return plots.figure_svg([panel])


def _two_d_svg(d: _Device, job: Path) -> bytes:
    cols, _ = io.read_csv(job / "cv.csv")
    pol = d.device.polarity
    u2, c2 = _u_sorted(cols["vg"], pol, cols["c_per_area"])
    u1, c1 = _u_sorted(d.start.vg, pol, d.start.c_per_area_ff_um2)
    panel = plots.Panel(
        "C per area at the start values: 2D cell against the 1D stack",
        _U_LABEL,
        "C per area (fF/um^2)",
        [plots.Curve(u1, c1, START_COLOR, dashed=True), plots.Curve(u2, c2, "#000000")],
        keys=[
            plots.Key("2D, with source and drain (start values)", "#000000"),
            plots.Key("1D stack (start values)", START_COLOR, "dashed"),
        ],
    )
    return plots.figure_svg([panel])


def _meshconv_svg(d: _Device, report: dict) -> bytes:
    pol = d.device.polarity
    sel = report["selected"]["level"]
    vals, changes, keys = [], [], []
    for i, lv in enumerate(report["levels"]):
        color = plots.FAMILY[i % len(plots.FAMILY)]
        u, c = _u_sorted(report["vg"], pol, lv["c_per_area_ff_um2"])
        vals.append(plots.Curve(u, c, color, dashed=i != sel))
        if lv["rel_change"] is not None:
            u, r = _u_sorted(report["vg"], pol, lv["rel_change"])
            changes.append(plots.Curve(u, np.maximum(np.abs(r), 1e-12), color, dashed=i != sel))
        mark = ", selected" if i == sel else ""
        keys.append(
            plots.Key(f"level {i}: {lv['node_count']} nodes{mark}", color,
                      "line" if i == sel else "dashed")
        )  # fmt: skip
    crit = report["criterion"]
    span = np.array([-5.0, 5.0])
    changes.append(plots.Curve(span, np.array([crit, crit]), TOL_COLOR))
    dim = report["dim"]
    panels = [
        plots.Panel(f"{dim}D C per area by mesh level", _U_LABEL, "C per area (fF/um^2)", vals,
                    keys=keys),
        plots.Panel(
            f"{dim}D change against the next finer level", _U_LABEL, "|C / C_finer - 1|",
            changes, "log",
            keys=[plots.Key(f"criterion {fmt(crit)}", TOL_COLOR)],
        ),
    ]  # fmt: skip
    return plots.figure_svg(panels)


# --- TCAD tables ------------------------------------------------------------------------------


def _window_cell(key: str, check: dict) -> str:
    w = check.get("window")
    if not w:
        return "none"
    if key.startswith("dv_"):
        which = key.replace("dv_", "u_")
        return f"{which} in {_interval(w['lo'], w['hi'])} V ({w['source']})"
    t = w["tightest"]
    inside = "TCAD inside at every bias" if w["all_inside"] else "TCAD outside at some bias"
    return (
        f"{inside}; set by {', '.join(w['sources'])}; tightest at u = {fmt(t['u'])} V: "
        f"{fmt(t['c_tcad'])} fF in {_interval(t['lo'], t['hi'])} fF"
    )


def _check_rows(rec: dict) -> list[str]:
    rows = [
        '| Check | TCAD | {term}`Tolerance <tolerance>` | {term}`"Same process" window` | Verdict |',
        "|---|---|---|---|---|",
    ]
    m, reg, tc = rec["metrics"], rec["spice_regions"], rec["tcad_crossings"]
    if set(rec["verdicts"]) != {key for key, _ in CHECKS}:
        raise ValueError(f"checks {sorted(rec['verdicts'])} are not docgen.CHECKS")
    for key, label in CHECKS:
        v = rec["verdicts"][key]
        if key.startswith("plateau_"):
            side = key.removeprefix("plateau_")
            tcad = (
                f"max \\|ΔCgg\\|/Cgg = {_pct(v['max_rel'])} ({m[f'plateau_{side}_points']} points)"
            )
            tol = f"≤ {fmt(100 * v['tolerance'])} %"
        else:
            which = key.replace("dv_", "u_")
            tcad = f"{_mv(v['dv_v'])} ({which} TCAD {fmt(tc[which])} V, SPICE {fmt(reg[which])} V)"
            tol = f"≤ {fmt(1e3 * v['tolerance_v'])} mV (a proposal)"
        rows.append(f"| {label} | {tcad} | {tol} | {_window_cell(key, v)} | {v['verdict']} |")
    rows.append(
        f"| Depletion, max \\|ΔC\\|/C (reported only) | {_pct(m['depletion_max_rel'])} | none | "
        "none | no verdict |"
    )
    return rows


def _regions_line(rec: dict) -> str:
    r = rec["spice_regions"]
    return (
        f"SPICE regions of this geometry (from the result file): u_fb = {fmt(r['u_fb'])} V, "
        f"u_t = {fmt(r['u_t'])} V, C_acc = {fmt(r['c_acc'])} fF, C_min = {fmt(r['c_min'])} fF "
        f"at u = {fmt(r['u_min'])} V, C_inv = {fmt(r['c_inv'])} fF, C_mid = {fmt(r['c_mid'])} fF."
    )


# The 2D status of a geometry whose calibrated 2D cell is committed but which the validation
# file does not compare yet (it was written before the cell; issue #35).
_TWO_D_PENDING = "committed, not yet compared"


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


def _tcad_geometry_page(spice_root: Path, d: _Device, g: Geometry, out: Path) -> None:
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
    lines = [
        f"# {name} MOS capacitor, W/L = {fmt(g.w_um)}/{fmt(g.l_um)} um",
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
            "Left: the TCAD Cgg of this geometry, the committed 1D C per area "
            f"({{repo}}`results/tcad/moscap1d/{name}`) through the fixed {{term}}`BSIM4` "
            "bookkeeping ({py:meth}`gf180tcad.tcad.moscap1d.MoscapCV.area_scaled`), at the "
            "calibrated and at the start values, over the ngspice TT curve and the "
            "{term}`corner envelope` (min-max over the five {term}`corners <corner>`, at each "
            "bias), against u = polarity × Vg ({term}`polarity-stripped`). Right: the relative "
            "error at each plateau bias, as recorded in the result file. The plateaus, crossings "
            "and regions are defined in {ref}`the agreement metric <cv-agreement-metric>`."
        ),
        "",
        f"![TCAD and ngspice Cgg against u, and the plateau errors]({gid}_cgg.svg)",
        "",
        "## Verdicts",
        "",
        *_check_rows(rec),
        "",
        _regions_line(rec),
        "",
        "## Intrinsic and parasitic parts (1D)",
        "",
        (
            "The calibrated TCAD Cgg split into its intrinsic part, the C per area times the "
            "BSIM4 capacitance area LeffCV x WeffCV ({term}`DLC`, {term}`DWC`), and its "
            "parasitic part, the BSIM4 overlap, fringe and {term}`CGBO` terms "
            "({py:func}`gf180tcad.tcad.moscap1d.parasitic_ff`). The parasitic part is fixed "
            "reference-model bookkeeping, not part of the {term}`parameter budget`."
        ),
        "",
        f"![Intrinsic, parasitic and total TCAD Cgg]({gid}_split.svg)",
        "",
        "## 2D",
        "",
    ]
    (ddir / f"{gid}_cgg.svg").write_bytes(_cgg_svg(spice_root, d, g, rec))
    (ddir / f"{gid}_split.svg").write_bytes(_split_svg(spice_root, d, g))
    job = d.two_d(gid)
    status = _two_d_status(d, gid)
    pending = (
        "; the calibrated 2D cell is committed, but the validation file "
        f"({{repo}}`results/tcad/validation/{name}.json`) does not compare it yet; its comparison "
        "is in {ref}`the validation section <cv-agreement-validation>`"
        if status == _TWO_D_PENDING
        else ""
    )
    lines.append(
        f"Calibrated 2D validation: {status}{pending} ({{doc}}`{CV_DOC}`, "
        "[issue #35](https://github.com/mithro/gf180-tcad/issues/35))."
    )
    lines.append("")
    cal_job = d.two_d(gid, "calibrated")
    if cal_job is not None:
        cal_meta = _read_json(cal_job / "cv.meta.json")
        rel = f"results/tcad/moscap2d/{name}/calibrated/{gid}"
        lines += [
            (
                f"The committed 2D cell at the calibrated values ({{repo}}`{rel}`): "
                f"{cal_meta['node_count']} nodes, mesh sha256 `{cal_meta['mesh_sha256']}`."
            ),
            "",
        ]
    if job is None:
        lines += [
            (
                "No 2D result at the start values is committed for this geometry "
                "({doc}`/limitations/moscap2d`)."
            ),
            "",
        ]
    else:
        meta = _read_json(job / "cv.meta.json")
        rel = f"results/tcad/moscap2d/{name}/start/{gid}"
        lines += [
            (
                f"The committed 2D cell at the start values ({{repo}}`{rel}`): "
                f"{meta['node_count']} nodes, source and drain "
                f"{'included' if meta['with_sd'] else 'left out'}, mesh from "
                f"{{repo}}`{meta['mesh_source']}`, mesh sha256 `{meta['mesh_sha256']}`. Its C "
                "per area against the 1D stack at the same start values (both TCAD; the 2D "
                "C per area divides the per-width Cgg by the drawn L, with no bookkeeping):"
            ),
            "",
            f"![2D and 1D C per area at the start values]({gid}_2d.svg)",
            "",
        ]
        (ddir / f"{gid}_2d.svg").write_bytes(_two_d_svg(d, job))
    lines += ["### Mesh picture", "", _NO_MESH, ""]
    if job is None and cal_job is None:
        lines += ["No 2D result exists for this geometry, so there is no mesh either.", ""]
    (ddir / f"{gid}.md").write_bytes("\n".join(lines).encode("utf-8"))


def _param_rows(d: _Device) -> list[str]:
    cal = d.cal
    rows = [
        (
            "| Parameter | Start | Fitted | Bounds [lo, hi] | Bound hit | Tag | Start from | "
            "Bounds from |"
        ),
        "|---|---|---|---|---|---|---|---|",
    ]
    for p in cal["params"]:
        par = d.proc.params[p]
        lo, hi = cal["bounds"][p]
        hit = cal["bound_hits"].get(p, "no")
        rows.append(
            f"| `{p}` | {fmt(cal['start'][p], 6)} {par.unit} | {fmt(cal['values'][p], 6)} "
            f"{par.unit} | {_interval(lo, hi)} | {hit} | `{par.provenance}` | "
            f"{par.start_kind} | {' / '.join(par.bounds_kind or ())} |"
        )
    return rows


def _bookkeeping_rows(d: _Device) -> list[str]:
    rows = ["| Parameter | Value | Tag | Source |", "|---|---|---|---|"]
    for n, p in d.proc.params.items():
        if p.role != "reference-bookkeeping":
            continue
        srcs = ", ".join(_source_text(s) for s in p.source)
        rows.append(f"| `{n}` | {fmt(p.value, 6)} {p.unit} | `{p.provenance}` | {srcs} |")
    return rows


def _meshconv_rows(report: dict) -> list[str]:
    sel = report["selected"]["level"]
    two_d = report["dim"] == 2
    head = "| Level | Scale | Nodes | max change to next finer |"
    rule = "|---|---|---|---|"
    if two_d:
        head += " max \\|2D/1D - 1\\| |"
        rule += "---|"
    rows = [head + " Selected |", rule + "---|"]
    for i, lv in enumerate(report["levels"]):
        mc = "finest" if lv["max_rel_change"] is None else fmt(lv["max_rel_change"], 3)
        row = f"| {i} | {fmt(lv['scale'])} | {lv['node_count']} | {mc} |"
        if two_d:
            a = lv["agreement_1d"]
            row += f" {'n/a' if a is None else fmt(a, 3)} |"
        rows.append(row + f" {'yes' if i == sel else ''} |")
    return rows


def _tcad_device_page(spice_root: Path, d: _Device, out: Path) -> None:
    from gf180tcad.calibrate.cv import BOUND_HIT_REL

    bound_rel = f"{BOUND_HIT_REL:.0e}".replace("e-0", "e-")  # 1e-3, as the prose pages write it
    name, cal, val = d.device.name, d.cal, d.val
    ddir = out / "tcad" / name
    ddir.mkdir(parents=True, exist_ok=True)
    opt = cal["optimiser"]
    cox = cal["cox_check"]
    lines = [
        f"# {name} MOS capacitor (TCAD)",
        "",
        (
            f"The {{term}}`TCAD` {{term}}`MOS capacitor <MOSCAP>` of {{term}}`{name}`: the "
            "{term}`C–V` calibration of its 1D stack against the {term}`SPICE` {term}`Cgg`-Vg, its "
            "validation at the {term}`held-out geometries <held-out geometry>`, and the "
            "{term}`mesh convergence` of the 1D and 2D structures. Generated from "
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
        "## Calibrated parameters",
        "",
        (
            f"{{term}}`Parameter budget <parameter budget>` used: {cal['budget_used']} of "
            f"{cal['budget']} per device type. Optimiser: {{{{ scipy }}}} `least_squares` "
            f"{opt['method']} ({{py:data}}`~gf180tcad.calibrate.cv.LSQ`), "
            f'"{opt["message"].replace("`", "")}", {opt["nfev"]} evaluations and '
            f"{opt['njev']} Jacobians, final cost {fmt(opt['cost'])}. A value within "
            f"{bound_rel} of a bound, relative to the bound width, is a bound hit "
            "({py:data}`~gf180tcad.calibrate.cv.BOUND_HIT_REL`). The tag is the "
            "{term}`provenance tag`; the kinds say where the start value and each bound come "
            "from: the {term}`model card` (card), computed from card values (derived), or a "
            "project choice, as set out on {ref}`process-data-tunables`."
        ),
        "",
        *_param_rows(d),
        "",
        (
            f"{{term}}`Cox` check: the oxide's own Cox is {fmt(cox['c_ox_ff_per_um2'])} "
            f"fF/um^2 and the 1D C per area is {fmt(cox['c_per_area_acc_ff_per_um2'])} "
            f"(accumulation) and {fmt(cox['c_per_area_inv_ff_per_um2'])} fF/um^2 (inversion), "
            f"against the public spec {_interval(cox['spec']['min'], cox['spec']['max'])} "
            f"fF/um^2 ([{cox['spec']['section']}]({cox['spec']['source_url']})): "
            f"{'inside' if cox['inside'] else 'OUTSIDE'}."
        ),
        "",
        "### Fixed reference bookkeeping",
        "",
        (
            "Not fitted and not part of the budget: the {term}`BSIM4` values that turn the C per area "
            "into a Cgg of one geometry ({term}`DLC`, {term}`DWC`, {term}`XL`, {term}`XW`) and "
            "its parasitic part (overlaps, fringe, {term}`CGBO`). Card lines are in the card "
            "the process file names; they are linked line by line on {ref}`process-data-card`."
        ),
        "",
        *_bookkeeping_rows(d),
        "",
        "## Geometries",
        "",
        (
            "| W/L (um) | Role | Accumulation | Inversion | ΔV_dep | ΔV_inv | Depletion | "
            "Verdict (1D) | 2D (calibrated) |"
        ),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for g in d.device.geometries:
        gid = geometry_id(g)
        rec, _ = d.comparison(gid)
        m = rec["metrics"]
        lines.append(
            f"| {{doc}}`{fmt(g.w_um)}/{fmt(g.l_um)} <{gid}>` | {g.role} | "
            f"{_pct(m['plateau_acc_max_rel'])} | {_pct(m['plateau_inv_max_rel'])} | "
            f"{_mv(m['dv_dep_v'])} | {_mv(m['dv_inv_v'])} | {_pct(m['depletion_max_rel'])} | "
            f"{rec['verdict']} | {_two_d_status(d, gid)} |"
        )
    lines += [
        "",
        (
            "The plateau and depletion columns are max |ΔCgg|/Cgg; ΔV is the shift of the "
            "TCAD mid-capacitance crossing from the SPICE one "
            "({ref}`the agreement metric <cv-agreement-metric>`). Validation reasons for the 2D "
            f"column are in {{repo}}`results/tcad/validation/{name}.json`."
        ),
        "",
        "## Mesh convergence",
        "",
        (
            "From {repo}`results/tcad/meshconv` ({doc}`/limitations/mesh-convergence`). Each "
            "level refines every mesh spacing of the previous one ({term}`uniform refinement`); "
            "the dashed curves are the "
            "levels not selected."
        ),
        "",
    ]
    for dim in ("1d", "2d"):
        report = d.meshconv[dim]
        (ddir / f"meshconv_{dim}.svg").write_bytes(_meshconv_svg(d, report))
        lines += [
            f"### {dim.upper()}",
            "",
            f"![{dim.upper()} mesh convergence of the C per area](meshconv_{dim}.svg)",
            "",
            *_meshconv_rows(report),
            "",
        ]
        for ex in report.get("excluded_levels", []):
            lines += [
                (
                    f"Level {ex['level']} is not run: it is as large as the 2D cell at L = 10 µm, "
                    "whose equilibrium solve fails, and is expected to fail the same way (not yet "
                    "attempted; [issue #58](https://github.com/mithro/gf180-tcad/issues/58)). "
                    "Its node counts and estimated run times are on "
                    "{ref}`the mesh-convergence page <mesh-convergence-2d>`."
                ),
                "",
            ]
        if dim == "2d":
            study = report["settings"]["geometry"]
            lines += [
                (
                    f"The 2D study runs at the geometry {{doc}}`{study} <{study}>`, "
                    "where the 2D C per area exceeds {term}`Cox` by the fringe and the source/drain "
                    "overlap at the gate edges ({doc}`/limitations/moscap2d`). " + _NO_MESH
                ),
                "",
            ]
    lines += ["```{toctree}", ":maxdepth: 1", "", *(geometry_id(g) for g in d.device.geometries)]
    lines += ["```", ""]
    (ddir / "index.md").write_bytes("\n".join(lines).encode("utf-8"))
    for g in d.device.geometries:
        _tcad_geometry_page(spice_root, d, g, out)


def _tcad_summary_page(devices: list[_Device], out: Path) -> None:
    lines = [
        "# TCAD MOS capacitor results",
        "",
        (
            "Pages generated at documentation build time from the committed {term}`TCAD` "
            "results ({repo}`results/tcad`): the {term}`C–V` calibration of the 1D "
            "{term}`MOS capacitor <MOSCAP>` against the {term}`SPICE` {term}`Cgg`-Vg and its "
            "validation at the {term}`held-out geometries <held-out geometry>` "
            f"({{doc}}`{CV_DOC}`). Every verdict is read from "
            "{repo}`results/tcad/calibration` and {repo}`results/tcad/validation`, which were "
            "computed in the {term}`dev-HEAD TCAD image`; these pages only render them. How the "
            "trees were made "
            "and which were restamped: {ref}`tcad-provenance`. " + _VERDICT_TERMS
        ),
        "",
        "## Verdicts (1D)",
        "",
        "| Device | Geometry | Role | Verdict (1D) | 2D (calibrated) |",
        "|---|---|---|---|---|",
    ]
    for d in devices:
        name = d.device.name
        for g in d.device.geometries:
            gid = geometry_id(g)
            rec, _ = d.comparison(gid)
            lines.append(
                f"| {{term}}`{name}` | {{doc}}`{fmt(g.w_um)}/{fmt(g.l_um)} <{name}/{gid}>` | "
                f"{g.role} | {rec['verdict']} | {_two_d_status(d, gid)} |"
            )
    statuses = {_two_d_status(d, geometry_id(g)) for d in devices for g in d.device.geometries}
    if _TWO_D_PENDING in statuses:
        two_d_text = (
            "The 2D column is the calibrated 2D validation of each geometry, read from "
            "{repo}`results/tcad/validation`, or "
            f'"{_TWO_D_PENDING}" where a calibrated 2D cell is committed under '
            "{repo}`results/tcad/moscap2d` but the validation file does not compare it yet; "
            "its comparison is in {ref}`the validation section <cv-agreement-validation>` "
            "([issue #35](https://github.com/mithro/gf180-tcad/issues/35))."
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
    devices = [_Device(tcad_root, device) for device in DEVICES.values()]
    for d in devices:
        _tcad_device_page(spice_root, d, out)
    _tcad_summary_page(devices, out)
