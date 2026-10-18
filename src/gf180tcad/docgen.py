# SPDX-License-Identifier: Apache-2.0
"""Generate the results pages of the documentation from the committed SPICE reference.

``generate`` is called by ``docs/conf.py`` at the start of every documentation build. It reads
only committed files (``results/spice/**``, ``data/pdk_elec_spec.json``) and writes only the
output directory it is given (``docs/_generated``). Nothing here is a published result: the
tables and plots are presentation of the committed dataset. The one derived quantity, the
ngspice-vs-Xyce maximum relative difference, is computed with
:func:`~gf180tcad.spice.xyce.engine_diff` on the host from the committed CSVs.

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

from gf180tcad import io, plots, specwindow
from gf180tcad.devices import CORNERS, DEVICES, Device, Geometry, geometry_id
from gf180tcad.known import KNOWN_ENGINE_DIFFS
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.spice.xyce import engine_diff

RESULTS = REPO_ROOT / "results" / "spice"
ENGINES = ("ngspice", "xyce")
TT = "typical"
DIFF_SWEEPS = ("idvg_lin", "idvg_sat", "idvd", "ioff")
DIFF_FLAG = 0.005  # design spec: more than 0.5 % between the engines flags the reference
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


def _cols(root: Path, engine: str, corner: str, device: str, gid: str, sweep: str):
    path = Path(root) / engine / corner / device / gid / f"{sweep}.csv"
    return io.read_csv(path)[0] if path.is_file() else None


def _metrics(root: Path, engine: str, corner: str, device: str, gid: str) -> dict | None:
    path = Path(root) / engine / corner / device / gid / specwindow.METRICS_NAME
    if not path.is_file():
        return None
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
        if cols is None:
            raise FileNotFoundError(f"ngspice {corner} {device.name} {gid} {sweep}")
        per_corner.append(_series(cols, sweep, pol))
    tt = per_corner[CORNERS.index(TT)]
    xcols = _cols(root, "xyce", TT, device.name, gid, sweep)
    xs = _series(xcols, sweep, pol) if xcols is not None else None

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
    return {
        e["metric"]: e
        for e in spec["entries"]
        if e["metric"] and e["device"] == device and e["geometry_id"] == gid
    }


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
            sw = "-"
        x = fmt(xy[name]) if xy is not None and name in xy else "-"
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
            "sets it (see {ref}`pdk-same-process-window`). A dash means the PDK publishes no spec "
            "for this metric at this geometry."
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
        if not e["metric"]:
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
                if a is None or b is None:
                    cells.append("-")
                    continue
                d = engine_diff(a, b)
                cell = f"{fmt(100 * d, 3)} %"
                if d > DIFF_FLAG:
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
            "reference dataset ({repo}`results/spice`). There is no {term}`TCAD` result yet: these "
            "plots and tables are the {term}`golden reference` that TCAD will later be compared "
            "against ({doc}`/comparison/agreement`)."
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


def generate(out_dir: Path, results_root: Path = RESULTS) -> None:
    """Write the summary page, 12 geometry pages and their SVGs under ``out_dir/results``."""
    out = Path(out_dir)
    shutil.rmtree(out / "results", ignore_errors=True)
    (out / "results").mkdir(parents=True)
    spec = specwindow.load_spec()
    envelope = json.loads((Path(results_root) / specwindow.ENVELOPE_NAME).read_text("utf-8"))
    for device in DEVICES.values():
        for g in device.geometries:
            _geometry_page(results_root, device, g, spec, envelope, out)
    _summary_page(results_root, spec, out)
