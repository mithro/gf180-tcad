# SPDX-License-Identifier: Apache-2.0
"""Every figure of the limitations pages (``docs/limitations/``), in a light and a dark twin.

Each figure shows what a limitation describes, drawn from committed files only: the SPICE
reference of both engines (``results/spice``), the 1D and 2D TCAD results, the
mesh-convergence reports and the validation files (``results/tcad``), the plugin-history
records (``results/plugin-history``), the process files (``data/process``) and the mesh and
stack code they were made with (:class:`gf180tcad.tcad.mesh.MeshSpec`,
:func:`gf180tcad.tcad.stack.sd_straggle_um`). It uses the colours, text size and deterministic
SVG settings of the explainer figures (:mod:`gf180tcad.explain.figures`), and :func:`write_all`
writes each as ``<name>-light.svg`` and ``<name>-dark.svg`` into
``docs/_generated/limitations/`` at docs build time (:func:`gf180tcad.docgen.generate`).

No number is typed below except in :data:`STYLE` (sizes, offsets, axis spans), :data:`UNITS`
(unit conversions) and :data:`TOOLS` (the defaults of the meshing and solver tools, each with
its source), so a figure's data come only from the committed files (tested).
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Callable
from pathlib import Path

import matplotlib
import matplotlib.lines
import matplotlib.patches
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from gf180tcad import engine46, io
from gf180tcad.calibrate import cv as calcv
from gf180tcad.comparison_figures import DEFAULT_ROOTS, Roots
from gf180tcad.devices import DEVICES, Geometry, geometry_id
from gf180tcad.explain import data
from gf180tcad.explain import figures as ef
from gf180tcad.sandbox import REPO_ROOT
from gf180tcad.spice import xyce
from gf180tcad.tcad import analytic, moscap1d, moscap2d, process, stack
from gf180tcad.tcad.mesh import MeshSpec

STYLE = {
    # Two rows of panels: a taller figure at the explainer figures' width.
    "tall_in": (6.4, 7.2),
    "marker_pt": 9.0,
    "small_marker_pt": 6.0,
    # Ring round a marked point, this size (pt).
    "ring_pt": 16.0,
    # Label lift above a point or line, as a fraction of the axis span.
    "label_lift": 0.03,
    # The engine plot: markers of the three sweeps side by side, this far apart (category units).
    "sweep_offset": 0.22,
    # A hollow marker (the card forced to 4.6) sits this far right of its filled one, so the two
    # stay apart where their values are close.
    "forced_offset": 0.1,
    # The engine plot's y axis spans these decades of relative difference.
    "engine_decades": (-8.0, -1.0),
    "decade": 10,
    # Tick labels of geometries stand upright.
    "tick_deg": 90,
    # Legends of many entries use smaller text, this fraction of the page's text size.
    "legend_scale": 0.75,
    # Text placed below a point sits this many label lifts below it.
    "label_drop": 2,
    # The vertex-grid figure: drawn grid lines over this span of depth (nm), oxide box width.
    "grid_span_nm": (12.0, 16.0),
    "box_width": 0.6,
    # The mesh-size figure: distance from the interface (nm) on this many points.
    "grading_span_nm": (0.0, 400.0),
    "grading_points": 801,
    # The round-off figure: |psi| from 1e-12 to 1 V on this many points.
    "psi_decades": (-12.0, 0.0),
    "psi_points": 241,
    # The source/drain figure: depth and lateral span (um) and points per curve; the three
    # peaks of the page, as factors of the process file's peak.
    "sd_depth_um": (0.0, 0.25),
    "sd_lateral_um": (-0.15, 0.15),
    "sd_points": 601,
    "sd_factors": (0.5, 1.0, 2.0),
    # The doping axis spans from this factor below the body doping to this factor above the peak.
    "sd_headroom": 3.0,
    # The C/Cox figure: room above and below the curves (fraction of Cox).
    "ccox_span": (0.55, 1.2),
    # The 2D-metrics figure: the cells' labels and markers.
    "metric_headroom": 1.25,
    # Log axes with a labelled criterion line reach this factor above the line or the data.
    "criterion_headroom": 3.0,
    # The plugin record: bar width (V) of the region ranges.
    "bar_width": 0.02,
    "hatch": "//",
    "bias_pad_v": 0.05,
    "legend_cols": 2,
    # The numbers the pages print: significant digits of e-notation, decimals of C/Cox.
    "page_digits": 2,
    "ccox_digits": 3,
}

# Unit conversions: fraction to per cent, µm to nm, V to mV, A to pA, Hz to MHz.
UNITS = {
    "percent": 100.0,
    "nm_per_um": 1e3,
    "mv_per_v": 1e3,
    "pa_per_a": 1e12,
    "hz_per_mhz": 1e6,
}

# Defaults of the tools the 2D mesh and solve use, each read from the tool's source.
TOOLS = {
    # meshwell's vertex grid (µm) when none is given: DEFAULT_POINT_TOLERANCE = 1e-3 in
    # meshwell/cad_settings.py line 52 of the meshwell pinned by docker/tcad-dev/versions.json
    # (https://github.com/mithro/meshwell/blob/4184d3138e80c3b0b365aee615a07adf7f9f8ac5/
    # meshwell/cad_settings.py#L52), which PolySurface's point_tolerance defaults to.
    "meshwell_point_tolerance_um": 1e-3,
    # DEVSIM's relative error per node, |update| / (|psi| + 1e-10 V): the offset (V), from
    # src/Equation/Equation.cc of DEVSIM 2.11.1 (https://github.com/devsim/devsim/blob/
    # c83824c7a84e3154b690e4d59966a136fb00296f/src/Equation/Equation.cc).
    "devsim_rel_offset_v": 1e-10,
    # The BSIM4 version the nfet card declares, which ngspice runs: "+ version=4.5" at line 37330
    # of models/ngspice/sm141064.spice of gf180mcu_fd_pr 4e132a23 (the file whose sha256
    # docker/base/versions.json pins as sm141064_ngspice_sha256;
    # https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/
    # 4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37330).
    "ngspice_nfet_bsim4": "4.5",
    # The oldest BSIM4 of Xyce 7.10, which it runs for the 4.5 card: "the oldest version
    # supported in Xyce (4.6.1)" at line 9266 of src/DeviceModelPKG/OpenModels/N_DEV_MOSFET_B4.C
    # of Xyce Release-7.10.0 (https://github.com/Xyce/Xyce/blob/
    # f18ab3816fcab005f510d429898f1067d0420d36/src/DeviceModelPKG/OpenModels/N_DEV_MOSFET_B4.C#L9266).
    "xyce_nfet_bsim4": "4.6.1",
}

_DEVICES = ("nfet_05v0", "pfet_05v0")
_SHORT = {"nfet_05v0": "nfet", "pfet_05v0": "pfet"}
_CARRIER = {"nfet_05v0": "electron", "pfet_05v0": "hole"}
_SWEEPS = ("idvg_lin", "idvg_sat", "idvd")
_SWEEP_COLOUR = {"idvg_lin": "electron", "idvg_sat": "hole", "idvd": "highlight"}
_SWEEP_MARKER = {"idvg_lin": "o", "idvg_sat": "s", "idvd": "^"}
#: The nfet engine differences with the card forced to BSIM4 4.6, recorded by
#: :mod:`gf180tcad.engine46`.
FORCED_RECORD = engine46.RECORD


def forced_diffs(path: Path = FORCED_RECORD) -> tuple[str, dict[tuple[str, str], float]]:
    """``(device, {(geometry id, sweep): engine_diff})`` of the record: each nfet geometry and
    sweep with the card's ``version`` forced to 4.6."""
    record = json.loads(path.read_text(encoding="utf-8"))
    cases = record["cases"]
    return record["device"], {
        (g, s): v["forced_4p6"] for g, d in cases.items() for s, v in d.items()
    }


TYPICAL = "typical"


def _label(g: Geometry) -> str:
    return f"W{g.w_um:g}/L{g.l_um:g}"


def _figure(size: tuple[float, float]) -> Figure:
    fig = Figure(figsize=size, layout="constrained")
    FigureCanvasAgg(fig)
    return fig


def _geometries(device: str) -> list[Geometry]:
    """Every geometry of ``device``, by falling W and then falling L."""
    return sorted(DEVICES[device].geometries, key=lambda g: (-g.w_um, -g.l_um))


def _geometry(device: str, gid: str) -> Geometry:
    (g,) = [g for g in DEVICES[device].geometries if geometry_id(g) == gid]
    return g


# --- the engine cross-check ---------------------------------------------------------------------


def engine_diffs(roots: Roots = DEFAULT_ROOTS) -> dict[tuple[str, str, str], float]:
    """``{(device, geometry id, sweep): engine_diff}`` of every typical-corner sweep, computed by
    :func:`gf180tcad.spice.xyce.engine_diff` from the committed ngspice and Xyce files."""
    out = {}
    for device in _DEVICES:
        for g in _geometries(device):
            gid = geometry_id(g)
            for sweep in _SWEEPS:
                a = data.spice_columns(roots.spice, "ngspice", TYPICAL, device, gid, sweep)
                b = data.spice_columns(roots.spice, "xyce", TYPICAL, device, gid, sweep)
                out[(device, gid, sweep)] = xyce.engine_diff(a, b)
    return out


def engine_diff_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The engine difference of every geometry and sweep, one panel per device, on a log axis
    with the 0.5 % threshold of :data:`gf180tcad.spice.xyce.ENGINE_DIFF_THRESHOLD`. The
    device of :data:`FORCED_RECORD` also shows each sweep with its card forced to BSIM4 4.6,
    as hollow markers."""
    pal = ef.PALETTES[palette]
    diffs = engine_diffs(roots)
    forced_device, forced = forced_diffs()
    thr = xyce.ENGINE_DIFF_THRESHOLD
    lo, hi = STYLE["engine_decades"]
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        # Not sharex: the devices' geometries differ (nfet Lmin 0.6 µm, pfet 0.5 µm), so each
        # panel carries its own tick labels.
        axes = fig.subplots(len(_DEVICES), 1)
        for ax, device in zip(axes, _DEVICES, strict=True):
            gs = _geometries(device)
            x = np.arange(len(gs))
            for k, sweep in enumerate(_SWEEPS):
                dx = (k - (len(_SWEEPS) - 1) / 2) * STYLE["sweep_offset"]
                y = [diffs[(device, geometry_id(g), sweep)] for g in gs]
                ax.plot(x + dx, y, ls="none", marker=_SWEEP_MARKER[sweep],
                        ms=STYLE["marker_pt"], color=pal[_SWEEP_COLOUR[sweep]], label=sweep,
                        gid=f"{device} {sweep}")  # fmt: skip
                if device == forced_device:
                    y = [forced[(geometry_id(g), sweep)] for g in gs]
                    ax.plot(x + dx + STYLE["forced_offset"], y, ls="none",
                            marker=_SWEEP_MARKER[sweep], ms=STYLE["marker_pt"], mfc="none", color=pal[_SWEEP_COLOUR[sweep]],
                            label=f"{sweep}, card at {engine46.FORCED_VERSION}",
                            gid=f"{device} {sweep} at {engine46.FORCED_VERSION}")  # fmt: skip
            ax.axhline(thr, color=pal["text"], lw=ef.STYLE["edge_width"], ls="--",
                       label=f"threshold {thr * UNITS['percent']:g} %",
                       gid="threshold")  # fmt: skip
            ax.set_yscale("log")
            ax.set_ylim(STYLE["decade"] ** lo, STYLE["decade"] ** hi)
            ax.set_xticks(x, [_label(g) for g in gs], rotation=STYLE["tick_deg"])
            ax.set_ylabel(f"{_SHORT[device]}: engine_diff")
            ax.grid(True)
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside lower center", ncols=STYLE["legend_cols"],
                   frameon=False)  # fmt: skip
        return fig


# The sweep of the subthreshold figure: the page's evidence geometry, Vds = 5 V.
EVIDENCE_DEVICE = "nfet_05v0"
EVIDENCE_GEOMETRY = "w10p0_l0p60"
EVIDENCE_SWEEP = "idvg_sat"


def evidence_curves(roots: Roots = DEFAULT_ROOTS) -> dict[str, np.ndarray]:
    """The committed :data:`EVIDENCE_SWEEP` of :data:`EVIDENCE_GEOMETRY` at Vbs = 0 from both
    engines: ``vg``, ``id_ngspice``, ``id_xyce`` (A) and ``rel``, (Id,Xyce − Id,ngspice) /
    ``max(|Id|)``, NaN where both currents are at or below
    :data:`gf180tcad.spice.xyce.ENGINE_DIFF_FLOOR`; and the sweep's one ``vd`` and ``vb`` (V)."""
    cols = {
        eng: data.spice_columns(
            roots.spice, eng, TYPICAL, EVIDENCE_DEVICE, EVIDENCE_GEOMETRY, EVIDENCE_SWEEP
        )
        for eng in ("ngspice", "xyce")
    }
    a, b = cols["ngspice"], cols["xyce"]
    for col in xyce.BIAS_COLUMNS:
        if not np.array_equal(a[col], b[col]):
            raise ValueError(f"bias column {col} differs between the engines")
    keep = a["vb"] == 0
    vg, x, y = a["vg"][keep], a["id"][keep], b["id"][keep]
    (vd,) = set(a["vd"][keep].tolist())
    (vb,) = set(a["vb"][keep].tolist())
    den = np.maximum(np.abs(x), np.abs(y))
    rel = np.where(den > xyce.ENGINE_DIFF_FLOOR, (y - x) / np.where(den > 0, den, 1), np.nan)
    return {"vg": vg, "id_ngspice": x, "id_xyce": y, "rel": rel, "vd": vd, "vb": vb}


def engine_subthreshold_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The drain current of both engines (top, log) and their relative difference (bottom)
    against Vg, with the 1 pA floor and the 0.5 % threshold."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    c = evidence_curves(roots)
    thr = xyce.ENGINE_DIFF_THRESHOLD * UNITS["percent"]
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        top, bottom = fig.subplots(2, 1, sharex=True)
        top.plot(c["vg"], np.abs(c["id_ngspice"]), color=pal["electron"], lw=lw,
                 label=f"ngspice (BSIM4 {TOOLS['ngspice_nfet_bsim4']})", gid="ngspice")  # fmt: skip
        top.plot(c["vg"], np.abs(c["id_xyce"]), color=pal["hole"], lw=lw, ls="--",
                 label=f"Xyce (BSIM4 {TOOLS['xyce_nfet_bsim4']})", gid="xyce")  # fmt: skip
        top.axhline(xyce.ENGINE_DIFF_FLOOR, color=pal["text"], lw=ef.STYLE["edge_width"], ls=":",
                    gid="floor")  # fmt: skip
        top.text(c["vg"][0], xyce.ENGINE_DIFF_FLOOR,
                 f" floor {xyce.ENGINE_DIFF_FLOOR * UNITS['pa_per_a']:g} pA", ha="left",
                 va="top")  # fmt: skip
        top.set_yscale("log")
        top.set_ylabel("|Id| (A)")
        top.grid(True)
        top.legend(loc="center right", frameon=False)
        bottom.plot(c["vg"], c["rel"] * UNITS["percent"], color=pal["highlight"], lw=lw,
                    gid="relative difference")  # fmt: skip
        for s in (1, -1):
            bottom.axhline(s * thr, color=pal["text"], lw=ef.STYLE["edge_width"], ls="--",
                           gid=f"threshold {s:+d}")  # fmt: skip
        bottom.text(c["vg"][-1], thr, f"±{thr:g} % ", ha="right", va="bottom")
        bottom.set_xlabel(f"Vg (V), Vds = {c['vd']:g} V, Vbs = {c['vb']:g} V")
        bottom.set_ylabel("(Xyce − ngspice) / max (%)")
        bottom.grid(True)
        return fig


# --- the 2D MOS capacitor -----------------------------------------------------------------------

# The oxide of the vertex-grid figure: the nfet's start value.
GRID_DEVICE = "nfet_05v0"


def vertex_grid(device: str = GRID_DEVICE) -> dict[str, float]:
    """The start oxide thickness of ``device`` (nm, its process file) and the thickness meshed
    when every vertex is rounded to a grid: meshwell's default grid and the fix's
    (:data:`gf180tcad.tcad.stack.POINT_TOLERANCE_UM`), with the relative error of Cox each gives
    (Cox scales as 1 / thickness)."""
    t = process.load(device).values()["t_ox_eff_nm"]
    out = {"t_ox_nm": t}
    for key, grid_um in (("default", TOOLS["meshwell_point_tolerance_um"]),
                         ("fix", stack.POINT_TOLERANCE_UM)):  # fmt: skip
        grid_nm = grid_um * UNITS["nm_per_um"]
        meshed = round(t / grid_nm) * grid_nm
        out[f"{key}_grid_nm"] = grid_nm
        out[f"{key}_nm"] = meshed
        out[f"{key}_cox_error"] = t / meshed - 1
    return out


def vertex_grid_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The top of the start oxide on meshwell's default 1 nm vertex grid (left) and on the fix's
    grid (right): the drawn thickness as a dashed line, the meshed oxide filled, the default
    grid's lines grey. The view shows the top nanometres of the oxide only."""
    pal = ef.PALETTES[palette]
    v = vertex_grid()
    lo, hi = STYLE["grid_span_nm"]
    half = STYLE["box_width"] / 2
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        ax = fig.subplots()
        for x0, key, title in ((0, "default", "meshwell default grid"),
                               (1, "fix", "grid of the fix")):  # fmt: skip
            meshed = v[f"{key}_nm"]
            ax.fill_between([x0 - half, x0 + half], 0, meshed, color=pal["highlight_oxide"],
                            alpha=ef.STYLE["cell_alpha"], lw=0, gid=f"meshed {key}")  # fmt: skip
            ax.plot([x0 - half, x0 + half], [v["t_ox_nm"], v["t_ox_nm"]], color=pal["text"],
                    lw=ef.STYLE["edge_width"] * 2, ls="--", gid=f"drawn {key}")  # fmt: skip
            ax.text(x0, hi, f"{title}, {v[f'{key}_grid_nm']:g} nm", ha="center", va="bottom")
            if key == "default":
                g = v["default_grid_nm"]
                for y in np.arange(math.ceil(lo / g), math.floor(hi / g) + 1) * g:
                    ax.plot([x0 - half, x0 + half], [y, y], color=pal["muted"],
                            lw=ef.STYLE["edge_width"], gid=f"grid line {y:g}")  # fmt: skip
                note = f"Cox {v['default_cox_error'] * UNITS['percent']:+.2g} %"
            else:
                note = f"Cox within {v['fix_grid_nm'] / 2 / v['t_ox_nm']:.0e}"
            ax.text(x0, meshed, f"meshed {meshed:.4g} nm\n{note}", ha="center", va="top",
                    gid=f"label {key}")  # fmt: skip
        # Between the two boxes, so it sits on neither.
        ax.text(STYLE["box_width"] - half + (1 - STYLE["box_width"]) / 2, v["t_ox_nm"],
                f"drawn\n{v['t_ox_nm']:g} nm", ha="center", va="center")  # fmt: skip
        ax.set_xlim(-half * STYLE["label_drop"], 1 + half * STYLE["label_drop"])
        ax.set_ylim(lo, hi)
        ax.set_xticks([])
        ax.set_ylabel("height above the silicon (nm)")
        return fig


# The 2D cells of the C/Cox figure: the start-value cells at Lmin and at L = 2 µm.
CCOX_CELLS = {
    "nfet_05v0": ("w10p0_l0p60", "w10p0_l2p00"),
    "pfet_05v0": ("w10p0_l0p50", "w10p0_l2p00"),
}


def _csv(path: Path) -> dict[str, np.ndarray]:
    return io.read_csv(path)[0]


def c_over_cox(device: str, roots: Roots = DEFAULT_ROOTS) -> dict:
    """The C/Cox curves of ``device`` at the start values: ``cox`` (fF/µm², from the 1D stack's
    oxide), the 1D curve ``one_d`` (``u``, ``ratio``), and per 2D cell of :data:`CCOX_CELLS` the
    QS curve per drawn area (``u``, ``ratio``), the AC points (``u_ac``, ``ratio_ac``) at the
    job's ``freq_hz``, empty where the job has no AC result, and the job's ``resumed`` record.
    u = polarity × Vg."""
    pol = DEVICES[device].polarity
    one = moscap1d.read(Path(roots.tcad) / "moscap1d" / device / "start")
    s = one.stack
    cox = analytic.f_per_cm2_to_ff_per_um2(analytic.cox_f_per_cm2(s.t_ox_nm, s.eps_ox))
    out = {"cox": cox, "one_d": {"u": pol * np.asarray(one.vg),
                                 "ratio": np.asarray(one.c_per_area_ff_um2) / cox}}  # fmt: skip
    for gid in CCOX_CELLS[device]:
        g = _geometry(device, gid)
        job = moscap2d.job_dir(Path(roots.tcad) / "moscap2d", device, "start", g)
        qs = _csv(job / moscap2d.CV_CSV)
        meta = json.loads((job / moscap2d.META_JSON).read_bytes())
        if meta["t_ox_nm"] != s.t_ox_nm:
            raise ValueError(f"{job}: oxide {meta['t_ox_nm']} nm, the 1D stack's {s.t_ox_nm} nm")
        cell = {"u": pol * qs["vg"], "ratio": qs["cgg_per_um"] / g.l_um / cox,
                "resumed": meta.get("resumed", {}),
                "freq_hz": meta.get("ac_freq_hz")}  # fmt: skip
        cgx = job / moscap2d.CGX_CSV
        if cgx.is_file():
            ac = _csv(cgx)
            cell["u_ac"], cell["ratio_ac"] = pol * ac["vg"], ac["cgg_per_um"] / g.l_um / cox
        else:
            cell["u_ac"], cell["ratio_ac"] = np.array([]), np.array([])
        out[gid] = cell
    return out


def c_over_cox_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """C/Cox against u at the start values, one panel per device: the 1D stack, the 2D cell at
    Lmin (QS line, AC points) and the 2D cell at L = 2 µm (QS only), per drawn gate area,
    with the line C/Cox = 1."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    lo, hi = STYLE["ccox_span"]
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        axes = fig.subplots(len(_DEVICES), 1, sharex=True)
        for ax, device in zip(axes, _DEVICES, strict=True):
            k = c_over_cox(device, roots)
            lmin, l2 = CCOX_CELLS[device]
            ax.plot(k["one_d"]["u"], k["one_d"]["ratio"], color=pal["text"], lw=lw,
                    label="1D stack", gid=f"{device} 1D")  # fmt: skip
            for gid, ls, colour in ((lmin, "--", pal[_CARRIER[device]]),
                                    (l2, ":", pal["highlight"])):  # fmt: skip
                g = _geometry(device, gid)
                cell = k[gid]
                ax.plot(cell["u"], cell["ratio"], color=colour, lw=lw, ls=ls,
                        label=f"2D L = {g.l_um:g} µm, QS", gid=f"{device} {gid} QS")  # fmt: skip
                if len(cell["u_ac"]):
                    ax.plot(cell["u_ac"], cell["ratio_ac"], ls="none", marker="o",
                            ms=STYLE["small_marker_pt"], color=colour,
                            label=f"2D L = {g.l_um:g} µm, "
                                  f"{cell['freq_hz'] / UNITS['hz_per_mhz']:g} MHz AC",
                            gid=f"{device} {gid} AC")  # fmt: skip
            ax.axhline(1, color=pal["muted"], lw=ef.STYLE["edge_width"], gid="C = Cox")
            ax.set_ylim(lo, hi)
            ax.set_ylabel(f"{_SHORT[device]}: C / Cox")
            ax.grid(True)
            ax.legend(
                loc="lower left",
                frameon=False,
                fontsize=ef.STYLE["text_pt"] * STYLE["legend_scale"],
            )
        axes[-1].set_xlabel("u = polarity × Vg (V)")
        return fig


# The cells of the 2D validation figure: the shortest nfet cell and the pfet L = 1 µm cell,
# both Disagree on the depletion crossing.
VALIDATION_CELLS = (("nfet_05v0", "w10p0_l0p60"), ("pfet_05v0", "w10p0_l1p00"))


def validation_record(device: str, roots: Roots = DEFAULT_ROOTS) -> dict:
    """The committed validation file of ``device``."""
    path = Path(roots.tcad) / "validation" / f"{device}.json"
    return json.loads(path.read_text("utf-8"))


def two_d_curves(device: str, gid: str, roots: Roots = DEFAULT_ROOTS) -> dict:
    """The calibrated 2D Cgg of one cell (``u``, ``cgg``, fF), as
    :func:`gf180tcad.calibrate.cv.devsim_2d_results` reads it, the SPICE curves of
    :func:`gf180tcad.explain.figures.cv_curves` and the record's crossings and levels."""
    pol = DEVICES[device].polarity
    res = calcv.devsim_2d_results(Path(roots.tcad) / "moscap2d")(device, _geometry(device, gid))
    u, cgg = data.u_sorted(np.asarray(res.vg), pol, np.asarray(res.cgg_total))
    spice = ef.cv_curves(device, "calibrated", gid, roots.spice, roots.tcad)
    rec = validation_record(device, roots)["two_d"][gid]
    return {"u": u, "cgg": cgg, "spice": spice, "record": rec}


def two_d_validation_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """Cgg against u at the cells of :data:`VALIDATION_CELLS`: the SPICE typical corner inside the
    band of its five corners, the calibrated 2D cell (dashed), the level C_mid and the
    depletion crossing of each (SPICE ring, 2D dot), with the recorded shift."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        axes = fig.subplots(len(VALIDATION_CELLS), 1, sharex=True)
        for ax, (device, gid) in zip(axes, VALIDATION_CELLS, strict=True):
            k = two_d_curves(device, gid, roots)
            s, rec = k["spice"], k["record"]
            reg, cross = rec["spice_regions"], rec["tcad_crossings"]
            ax.fill_between(s["u_spice"], s["spice_lo"], s["spice_hi"], color=pal["band"], lw=0,
                            label="SPICE, all corners", gid="corners")  # fmt: skip
            ax.plot(s["u_spice"], s["spice_tt"], color=pal["text"], lw=lw, label="SPICE, typical",
                    gid="typical")  # fmt: skip
            ax.plot(k["u"], k["cgg"], color=pal["highlight"], lw=lw, ls="--",
                    zorder=ef.STYLE["cv_zorder"], label="2D, calibrated", gid="2D")  # fmt: skip
            ax.axhline(reg["c_mid"], color=pal["muted"], lw=ef.STYLE["edge_width"], ls=":",
                       gid="c_mid")  # fmt: skip
            ax.plot([reg["u_dep"]], [reg["c_mid"]], ls="none", marker="o", mfc="none",
                    ms=STYLE["ring_pt"], color=pal["text"], gid="SPICE u_dep")  # fmt: skip
            ax.plot([cross["u_dep"]], [reg["c_mid"]], ls="none", marker="o",
                    ms=STYLE["marker_pt"], color=pal["highlight"], gid="2D u_dep")  # fmt: skip
            dv = rec["metrics"]["dv_dep_v"] * UNITS["mv_per_v"]
            lift = reg["c_acc"] * STYLE["label_lift"]
            ax.text(cross["u_dep"], reg["c_mid"] - lift * STYLE["label_drop"], f"{dv:+.0f} mV ",
                    ha="right", va="top", color=pal["highlight"])  # fmt: skip
            ax.set_ylim(bottom=0)
            ax.set_title(f"{_SHORT[device]} {_label(_geometry(device, gid))}: {rec['verdict']}",
                         fontsize=ef.STYLE["text_pt"])  # fmt: skip
            ax.set_ylabel("Cgg (fF)")
            ax.grid(True)
        axes[-1].set_xlabel("u = polarity × Vg (V)")
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside lower center", ncols=len(labels),
                   frameon=False, fontsize=ef.STYLE["text_pt"] * STYLE["legend_scale"])  # fmt: skip
        return fig


def two_d_metrics(roots: Roots = DEFAULT_ROOTS) -> list[dict]:
    """Per compared 2D cell of both devices (validation files, by device then falling W and L):
    ``device``, ``geometry``, the cell's ``verdict``, ``dv_dep_mv`` and the signed plateau
    residual of largest magnitude, ``acc`` and ``inv`` (per cent), each with its own verdict
    (``verdict_dv_dep``, ``verdict_acc``, ``verdict_inv``) and tolerance (``tol_mv``, and
    ``tol_acc`` and ``tol_inv`` in per cent)."""
    out = []
    for device in _DEVICES:
        two_d = validation_record(device, roots)["two_d"]
        for g in _geometries(device):
            rec = two_d.get(geometry_id(g))
            if rec is None or rec["status"] != "compared":
                continue
            res, vds = rec["residuals"], rec["verdicts"]
            row = {
                "device": device,
                "geometry": g,
                "verdict": rec["verdict"],
                "dv_dep_mv": rec["metrics"]["dv_dep_v"] * UNITS["mv_per_v"],
                "tol_mv": vds["dv_dep"]["tolerance_v"] * UNITS["mv_per_v"],
                "verdict_dv_dep": vds["dv_dep"]["verdict"],
            }
            for part in ("acc", "inv"):
                vals = res[f"plateau_{part}_rel"]
                row[part] = max(vals, key=abs) * UNITS["percent"]
                row[f"tol_{part}"] = vds[f"plateau_{part}"]["tolerance"] * UNITS["percent"]
                row[f"verdict_{part}"] = vds[f"plateau_{part}"]["verdict"]
            out.append(row)
    return out


# The verdict a hollow marker shows: inside the SPICE corner window, so the same process.
SAME_PROCESS = "Same process"


def _faces(rows: list[dict], key: str, colours: list[str]) -> list[str]:
    """Marker faces: hollow ("none") where the metric's verdict is :data:`SAME_PROCESS`."""
    return [
        "none" if r[f"verdict_{key}"] == SAME_PROCESS else c
        for r, c in zip(rows, colours, strict=True)
    ]


def two_d_metrics_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The depletion-crossing shift of every compared 2D cell against its tolerance band (top),
    and the largest signed plateau difference from SPICE of each, accumulation and inversion,
    against theirs (bottom). A hollow marker is a metric whose verdict is "Same process" (outside
    the band, inside the SPICE corner window); a filled one is Agree (inside the band) or
    Disagree (outside both)."""
    pal = ef.PALETTES[palette]
    rows = two_d_metrics(roots)
    x = np.arange(len(rows))
    labels = [f"{_SHORT[r['device']]} {_label(r['geometry'])}" for r in rows]
    colours = [pal[_CARRIER[r["device"]]] for r in rows]
    size = STYLE["marker_pt"] ** 2
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        top, bottom = fig.subplots(2, 1, sharex=True)
        (tol,) = {r["tol_mv"] for r in rows}
        top.axhspan(-tol, tol, color=pal["band"], lw=0, gid="tolerance")
        top.text(x[-1], tol, f"±{tol:g} mV", ha="right", va="top")
        top.scatter(x, [r["dv_dep_mv"] for r in rows], facecolors=_faces(rows, "dv_dep", colours),
                    edgecolors=colours, s=size, zorder=ef.STYLE["cv_zorder"],
                    gid="dv_dep")  # fmt: skip
        top.axhline(0, color=pal["text"], lw=ef.STYLE["edge_width"], gid="zero dv_dep")
        top.set_ylabel("depletion crossing\nshift (mV)")
        top.grid(True)
        proxies = [
            matplotlib.lines.Line2D([], [], ls="none", marker="o", ms=STYLE["marker_pt"],
                                    color=pal["text"], label="Agree or Disagree"),
            matplotlib.lines.Line2D([], [], ls="none", marker="o", ms=STYLE["marker_pt"],
                                    color=pal["text"], mfc="none", label=SAME_PROCESS),
        ]  # fmt: skip
        (ptol,) = {r[f"tol_{part}"] for r in rows for part in ("acc", "inv")}
        bottom.axhspan(-ptol, ptol, color=pal["band"], lw=0, gid="plateau tolerance")
        bottom.text(x[-1], ptol, f"±{ptol:g} %", ha="right", va="top")
        for part, marker in (("acc", "o"), ("inv", "s")):
            bottom.scatter(x, [r[part] for r in rows], facecolors=_faces(rows, part, colours),
                           edgecolors=colours, marker=marker, s=size,
                           zorder=ef.STYLE["cv_zorder"],
                           label={"acc": "accumulation", "inv": "inversion"}[part],
                           gid=f"plateau {part}")  # fmt: skip
        bottom.axhline(0, color=pal["text"], lw=ef.STYLE["edge_width"], gid="zero plateau")
        bottom.set_ylabel("plateau difference\nfrom SPICE (%)")
        bottom.grid(True)
        bottom.set_xticks(x, labels, rotation=STYLE["tick_deg"])
        handles, _ = bottom.get_legend_handles_labels()
        fig.legend(handles=[*handles, *proxies], loc="outside lower center",
                   ncols=STYLE["legend_cols"], frameon=False)  # fmt: skip
        return fig


# --- the 2D solver --------------------------------------------------------------------------------

# The device whose 2D mesh-convergence sweeps accepted solves at round-off.
ROUNDOFF_DEVICE = "nfet_05v0"


def roundoff_points(roots: Roots = DEFAULT_ROOTS) -> dict:
    """The round-off acceptances of the 2D mesh-convergence report of :data:`ROUNDOFF_DEVICE`:
    ``rel_tol`` (the report's solver setting), per accepted solve its ``level``, ``scale``,
    ``vg``, ``region``, ``min_abs_psi`` (V) and ``abs_error`` (V, the accepted update), the one
    acceptance ``bound`` (V) of every solve, and ``k`` of that bound, k·eps·max|psi| (eps the
    double machine epsilon), read back from the recorded bound and max|psi|."""
    path = Path(roots.tcad) / "meshconv" / "moscap2d" / ROUNDOFF_DEVICE / "report.json"
    rep = json.loads(path.read_text("utf-8"))
    pts = [{"level": i, "scale": lv["scale"], **p}
           for i, lv in enumerate(rep["levels"]) for p in lv["roundoff_accepted"]]  # fmt: skip
    (bound,) = {p["roundoff_bound"] for p in pts}
    (max_psi,) = {p["max_abs_psi"] for p in pts}
    k = round(bound / (sys.float_info.epsilon * max_psi))
    return {"rel_tol": rep["settings"]["rel_tol"], "points": pts, "bound": bound, "k": k}


def roundoff_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The update DEVSIM's relative criterion asks for at a node, ``rel_tol * (|psi| + offset)``,
    against ``|psi|`` (log-log), and each accepted solve of :func:`roundoff_points` at its smallest
    ``|psi|`` and its update: the solves sit where the criterion asks for less than the round-off."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    k = roundoff_points(roots)
    lo, hi = STYLE["psi_decades"]
    psi = np.logspace(lo, hi, STYLE["psi_points"])
    need = k["rel_tol"] * (psi + TOOLS["devsim_rel_offset_v"])
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        ax = fig.subplots()
        ax.plot(psi, need, color=pal["text"], lw=lw, label="update the criterion asks for",
                gid="criterion")  # fmt: skip
        ups = [p["abs_error"] for p in k["points"]]
        ax.axhline(k["bound"], color=pal["muted"], lw=ef.STYLE["edge_width"], ls="--",
                   label=f"acceptance bound, {k['k']}·eps·max|psi|",
                   gid="roundoff bound")  # fmt: skip
        ax.plot([p["min_abs_psi"] for p in k["points"]], ups, ls="none", marker="o",
                ms=STYLE["marker_pt"], color=pal["highlight"],
                label="accepted solves (update, smallest |psi|)", gid="accepted")  # fmt: skip
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("|psi| at the node (V)")
        ax.set_ylabel("potential update (V)")
        ax.grid(True)
        fig.legend(loc="outside lower center", ncols=1, frameon=False)
        return fig


# --- the source/drain peak ------------------------------------------------------------------------

# The device of the source/drain figure: the pfet, whose peak is a literature value.
SD_DEVICE = "pfet_05v0"


def sd_profiles(device: str = SD_DEVICE) -> dict:
    """The source/drain doping of ``device`` at the start values for the peaks of
    :data:`STYLE` ``sd_factors`` × the process file's peak: per peak the straggle
    (:func:`gf180tcad.tcad.stack.sd_straggle_um`), the vertical Gaussian inside the source/drain,
    away from the gate edge (where the lateral factor below is 1), and the
    surface doping across the gate edge (x = 0, gate at x > 0) with the lateral straggle of
    :data:`gf180tcad.tcad.stack.LATERAL_STRAGGLE_RATIO` (the lateral mask-edge factor
    (1 − erf(x / (√2 s))) / 2 of the plugin's ``doping.Lateral``)."""
    proc = process.load(device)
    v = proc.values()
    y = np.linspace(*STYLE["sd_depth_um"], STYLE["sd_points"])
    x = np.linspace(*STYLE["sd_lateral_um"], STYLE["sd_points"])
    out = {"n_body": v["n_ch_cm3"], "xj_um": v["xj_um"], "y_um": y, "x_um": x, "peaks": []}
    for f in STYLE["sd_factors"]:
        peak = v["sd_peak_cm3"] * f
        s = stack.sd_straggle_um(proc, peak)
        lat = stack.LATERAL_STRAGGLE_RATIO * s
        erf = np.vectorize(math.erf)
        out["peaks"].append({
            "peak": peak,
            "straggle_um": s,
            "vertical": peak * np.exp(-(y**2) / (2 * s**2)),
            "surface": peak * (1 - erf(x / (math.sqrt(2) * lat))) / 2,
        })  # fmt: skip
    return out


def sd_profile_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The pfet source/drain doping for three peaks with XJ fixed: against depth inside the
    source/drain, away from the gate edge (top), meeting the body doping at XJ, and along the
    surface across the gate edge (bottom), half the peak at the edge,
    where each reaches the body doping at a different distance under the gate."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    k = sd_profiles()
    colours = ("electron", "highlight", "hole")
    nm = UNITS["nm_per_um"]
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        top, bottom = fig.subplots(2, 1)
        for p, colour in zip(k["peaks"], colours, strict=True):
            label = f"peak {p['peak']:.0e} cm⁻³, s = {p['straggle_um'] * nm:.1f} nm"
            top.plot(k["y_um"] * nm, p["vertical"], color=pal[colour], lw=lw, label=label,
                     gid=f"vertical {p['peak']:.0e}")  # fmt: skip
            bottom.plot(k["x_um"] * nm, p["surface"], color=pal[colour], lw=lw,
                        gid=f"surface {p['peak']:.0e}")  # fmt: skip
        for ax in (top, bottom):
            ax.axhline(k["n_body"], color=pal["muted"], lw=ef.STYLE["edge_width"], ls="--",
                       gid="body doping")  # fmt: skip
            ax.set_yscale("log")
            ax.set_ylim(k["n_body"] / STYLE["sd_headroom"],
                        max(p["peak"] for p in k["peaks"]) * STYLE["sd_headroom"])  # fmt: skip
            ax.set_ylabel("doping (cm⁻³)")
            ax.grid(True)
        top.axvline(k["xj_um"] * nm, color=pal["text"], lw=ef.STYLE["edge_width"], ls=":",
                    gid="XJ")  # fmt: skip
        top.text(k["xj_um"] * nm, k["n_body"], " XJ", ha="left", va="bottom")
        top.set_xlabel("depth below the surface, away from the gate edge (nm)")
        top.legend(
            loc="upper right", frameon=False, fontsize=ef.STYLE["text_pt"] * STYLE["legend_scale"]
        )
        bottom.axvline(0, color=pal["text"], lw=ef.STYLE["edge_width"], ls=":", gid="gate edge")
        bottom.text(0, k["n_body"], " under the gate →", ha="left", va="bottom")
        bottom.set_xlabel("distance along the surface from the gate edge (nm)")
        return fig


# --- mesh convergence ---------------------------------------------------------------------------


def grading_curves(roots: Roots = DEFAULT_ROOTS) -> dict:
    """The 2D body mesh size against the distance d from the oxide interface,
    min(h_surface + (grading − 1)·d, h_bulk) (nm), at each 2D level of the committed report of
    the nfet: with the grading refined, the report's own spec of the level, and with the grading
    held fixed, :meth:`gf180tcad.tcad.mesh.MeshSpec.scaled` of the report's start spec."""
    path = Path(roots.tcad) / "meshconv" / "moscap2d" / "nfet_05v0" / "report.json"
    rep = json.loads(path.read_text("utf-8"))
    start = MeshSpec(**rep["start"])
    d = np.linspace(*STYLE["grading_span_nm"], STYLE["grading_points"])

    def size(spec: MeshSpec) -> np.ndarray:
        return np.minimum(spec.h_si_surface_nm + (spec.grading - 1) * d, spec.h_si_bulk_nm)

    levels = []
    for i, lv in enumerate(rep["levels"]):
        refined = MeshSpec(**lv["spec"])
        if refined != start.scaled(lv["scale"], refine_grading=True):
            raise ValueError(f"level {i}: the report's spec is not the refined start spec")
        levels.append({"level": i, "scale": lv["scale"], "refined": size(refined),
                       "fixed": size(start.scaled(lv["scale"]))})  # fmt: skip
    return {"d_nm": d, "levels": levels}


def mesh_grading_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The 2D body mesh size against the distance from the interface at levels 0 to 2: with the
    grading refined as the study does (solid) and held fixed (dashed). Fixed, every level has the
    same size beyond a few nm."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    k = grading_curves(roots)
    colours = ("electron", "hole", "highlight")
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        ax = fig.subplots()
        for lv, colour in zip(k["levels"], colours, strict=True):
            ax.plot(k["d_nm"], lv["refined"], color=pal[colour], lw=lw,
                    label=f"level {lv['level']}, grading refined",
                    gid=f"level {lv['level']} refined")  # fmt: skip
            ax.plot(k["d_nm"], lv["fixed"], color=pal[colour], lw=lw, ls="--",
                    label=f"level {lv['level']}, grading fixed",
                    gid=f"level {lv['level']} fixed")  # fmt: skip
        ax.set_xlabel("distance from the oxide interface into the body (nm)")
        ax.set_ylabel("mesh size (nm)")
        ax.grid(True)
        fig.legend(loc="outside lower center", ncols=STYLE["legend_cols"], frameon=False)
        return fig


def meshconv_curves(dim: int, roots: Roots = DEFAULT_ROOTS) -> dict:
    """Per device, the committed ``dim``-D mesh-convergence report: ``u`` and per level with a
    finer neighbour its scale and ``|C / C_finer - 1|`` at every bias; the criterion; in 2D also the
    2D-against-1D difference of the extruded stack at each level (``agreement``) and its
    criterion."""
    out = {}
    for device in _DEVICES:
        path = Path(roots.tcad) / "meshconv" / f"moscap{dim}d" / device / "report.json"
        rep = json.loads(path.read_text("utf-8"))
        pol = DEVICES[device].polarity
        k = {"u": pol * np.asarray(rep["vg"]), "criterion": rep["criterion"], "levels": [],
             "agreement": [], "selected": rep["selected"]["level"]}  # fmt: skip
        for i, lv in enumerate(rep["levels"]):
            if lv["rel_change"] is not None:
                k["levels"].append({"level": i, "change": np.abs(lv["rel_change"])})
            cur = lv.get("agreement_1d_curve")
            if cur:
                k["agreement"].append({"level": i, "u": pol * np.asarray(cur["vg"]),
                                       "rel": np.abs(cur["rel"])})  # fmt: skip
        if dim == 2:
            k["agreement_criterion"] = rep["selected"]["criteria"]["agreement_1d"]["max"]
        out[device] = k
    return out


def _meshconv_figure(dim: int, palette: str, roots: Roots):
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    k = meshconv_curves(dim, roots)
    colours = ("electron", "hole", "highlight")
    cols = 2 if dim == 2 else 1
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        axes = np.atleast_2d(fig.subplots(len(_DEVICES), cols, sharex="col", squeeze=False))
        for row, device in enumerate(_DEVICES):
            c = k[device]
            ax = axes[row][0]
            for lv in c["levels"]:
                ax.plot(
                    c["u"],
                    lv["change"],
                    color=pal[colours[lv["level"]]],
                    lw=lw,
                    label=f"level {lv['level']}",
                    gid=f"{device} level {lv['level']}",
                )
            ax.axhline(c["criterion"], color=pal["text"], lw=ef.STYLE["edge_width"], ls="--",
                       gid="criterion")  # fmt: skip
            ax.text(c["u"][0], c["criterion"], f" {c['criterion'] * UNITS['percent']:g} %",
                    ha="left", va="bottom")  # fmt: skip
            ax.set_yscale("log")
            top = max(c["criterion"], *(float(np.max(lv["change"])) for lv in c["levels"]))
            ax.set_ylim(top=top * STYLE["criterion_headroom"])
            ax.set_ylabel(f"{_SHORT[device]}: change\nto next level")
            ax.grid(True)
            if dim == 2:
                ax2 = axes[row][1]
                for a in c["agreement"]:
                    ax2.plot(a["u"], a["rel"], color=pal[colours[a["level"]]], lw=lw,
                             marker="o", ms=STYLE["small_marker_pt"],
                             label=f"level {a['level']}",
                             gid=f"{device} agreement {a['level']}")  # fmt: skip
                crit = c["agreement_criterion"]
                ax2.axhline(crit, color=pal["text"], lw=ef.STYLE["edge_width"], ls="--",
                            gid="agreement criterion")  # fmt: skip
                ax2.text(c["u"][0], crit, f" {crit * UNITS['percent']:g} %", ha="left",
                         va="bottom")  # fmt: skip
                ax2.set_yscale("log")
                top = max(crit, *(float(np.max(a["rel"])) for a in c["agreement"]))
                ax2.set_ylim(top=top * STYLE["criterion_headroom"])
                ax2.set_ylabel("2D against 1D")
                ax2.grid(True)
        for ax in axes[-1]:
            ax.set_xlabel("u = polarity × Vg (V)")
        handles, labels = axes[0][-1].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside lower center", ncols=len(labels),
                   frameon=False)  # fmt: skip
        return fig


def meshconv_1d_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """``|C / C_finer - 1|`` against u at each 1D level with a finer neighbour, one panel per device,
    with the 1 % criterion."""
    return _meshconv_figure(1, palette, roots)


def meshconv_2d_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The same for the 2D levels (left), and the extruded stack's 2D-against-1D difference at
    each level with the 0.5 % criterion (right)."""
    return _meshconv_figure(2, palette, roots)


# --- the plugin history ---------------------------------------------------------------------------

# The committed records of the plugin-history page: the release at its own mesh, then at half it.
PLUGIN_FILES = ("v0.8.0.json", "v0.8.0-mesh0p5.json")
PLUGIN_ROOT = REPO_ROOT / "results" / "plugin-history"


def plugin_root(roots: Roots = DEFAULT_ROOTS) -> Path:
    """The plugin-history records of ``roots``: ``plugin-history`` beside its SPICE tree, the
    results tree :func:`gf180tcad.docgen.generate` is given as ``results_root``, so the committed
    :data:`PLUGIN_ROOT` for the committed trees. (A TCAD tree given on its own, as the docgen
    tests do, keeps the committed records.)"""
    return Path(roots.spice).parent / "plugin-history"


def plugin_records(root: Path = PLUGIN_ROOT) -> dict[str, dict]:
    """``{name: record}`` of :data:`PLUGIN_FILES` under ``root``, in that order, each named by
    its ``gplugins_tag`` and, where it is not 1, its ``mesh_scale`` ("<tag> × <scale>")."""
    out = {}
    for file in PLUGIN_FILES:
        rec = json.loads((Path(root) / file).read_text("utf-8"))
        scale = rec["mesh_scale"]
        out[rec["gplugins_tag"] + ("" if scale == 1 else f" × {scale:g}")] = rec
    return out


def plugin_record(name: str, root: Path = PLUGIN_ROOT) -> dict:
    """The record ``name`` of :func:`plugin_records`."""
    return plugin_records(root)[name]


def pn_slab_steps(name: str, root: Path = PLUGIN_ROOT) -> list[dict]:
    """The PN-slab solves of one record, equilibrium first then the ramp: ``bias`` (the cathode
    voltage, V), ``anode_minus_cathode`` and ``drop`` (V) and the Potential range of each silicon
    region (``core``, ``slab90``)."""
    dd = plugin_record(name, root)["ddcomponent"]
    out = []
    for step in [{"v": 0.0, **dd["equilibrium"]}, *dd["bias"]]:
        out.append({
            "bias": step["v"],
            "anode_minus_cathode": step["anode_minus_cathode_v"],
            "drop": step["junction"]["drop_v"],
            "ranges": step["potential_range_by_region"],
        })  # fmt: skip
    return out


def pn_slab_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The PN slab of the v0.8.0 records against the cathode bias: the anode − cathode contact
    potential and the junction drop (top), with the drop a connected rib would have (its
    equilibrium value minus the bias); and the Potential range of the rib (``core``) and the slab
    (``slab90``) at each step of both meshes (bottom), the half-size mesh hatched."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    w = STYLE["bar_width"]
    root = plugin_root(roots)
    names = list(plugin_records(root))
    records = tuple(zip(names, ("-", "--"), ("", STYLE["hatch"]), strict=True))
    regions = (("core", "hole", "rib"), ("slab90", "electron", "slab"))
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        top, bottom = fig.subplots(2, 1, sharex=True)
        ends, handles = [], []
        for i, (name, ls, hatch) in enumerate(records):
            steps = pn_slab_steps(name, root)
            b = np.array([s["bias"] for s in steps])
            top.plot(b, [s["anode_minus_cathode"] for s in steps], color=pal["electron"], lw=lw,
                     ls=ls, marker="o", label=f"anode − cathode, {name}",
                     gid=f"{name} anode-cathode")  # fmt: skip
            top.plot(b, [s["drop"] for s in steps], color=pal["hole"], lw=lw, ls=ls, marker="s",
                     label=f"junction drop, {name}", gid=f"{name} drop")  # fmt: skip
            for j, (region, colour, label) in enumerate(regions):
                slot = i * len(regions) + j - (len(records) * len(regions) - 1) / 2
                for s in steps:
                    lo, hi = s["ranges"][region]
                    ends += [lo, hi]
                    bottom.bar(s["bias"] + slot * w, hi - lo, bottom=lo, width=w,
                               color=pal[colour], hatch=hatch, edgecolor=pal["background"],
                               gid=f"{name} {region} {s['bias']:g}")  # fmt: skip
                handles.append(matplotlib.patches.Patch(
                    facecolor=pal[colour], hatch=hatch, edgecolor=pal["background"],
                    label=f"{label} ({region}), {name}"))  # fmt: skip
        eq = pn_slab_steps(names[0], root)
        b = np.array([s["bias"] for s in eq])
        top.plot(b, eq[0]["drop"] - b, color=pal["muted"], lw=lw, ls=":",
                 label="drop if the bias reached the junction", gid="connected")  # fmt: skip
        top.set_ylabel("potential (V)")
        top.grid(True)
        top.legend(loc="lower left", frameon=False,
                   fontsize=ef.STYLE["text_pt"] * STYLE["legend_scale"])  # fmt: skip
        pad = (max(ends) - min(ends)) * STYLE["label_lift"]
        bottom.set_ylim(min(ends) - pad, max(ends) + pad)
        bottom.set_ylabel("Potential range\nof each region (V)")
        bottom.grid(True)
        bottom.set_xlabel("cathode bias (V)")
        bottom.set_xticks(b)
        bottom.set_xlim(b[0] - STYLE["bias_pad_v"], b[-1] + STYLE["bias_pad_v"])
        fig.legend(handles=handles, loc="outside lower center", ncols=STYLE["legend_cols"],
                   frameon=False, fontsize=ef.STYLE["text_pt"] * STYLE["legend_scale"])  # fmt: skip
        return fig


def pin_widths(root: Path = PLUGIN_ROOT) -> dict[str, list[tuple[float, float]]]:
    """``{record: [(bias V, depletion width µm), ...]}`` of the PIN waveguide in each v0.8.0
    record."""
    out = {}
    for name, rec in plugin_records(root).items():
        out[name] = [(b["v"], b["depletion_width_um"]) for b in rec["pin"]["bias"]]
    return out


def pin_depletion_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The PIN waveguide's depletion width against the bias in both v0.8.0 records: the two
    meshes give the same widths, since the waveguide uses DEVSIM's own mesh."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    k = pin_widths(plugin_root(roots))
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        ax = fig.subplots()
        for (name, pts), (colour, ls, marker) in zip(k.items(), (("electron", "-", "o"),
                                                                 ("hole", "--", "s")),
                                                      strict=True):  # fmt: skip
            b, wdt = zip(*pts, strict=True)
            ax.plot(b, wdt, color=pal[colour], lw=lw, ls=ls, marker=marker,
                    ms=STYLE["marker_pt"], label=name, gid=name)  # fmt: skip
        ax.set_xlabel("bias (V)")
        ax.set_ylabel("depletion width (µm)")
        ax.set_ylim(bottom=0)
        ax.grid(True)
        ax.legend(loc="upper right", frameon=False)
        return fig


# --- the numbers the pages print ----------------------------------------------------------------

# The level of the nfet 2D mesh-convergence study whose round-off acceptance the moscap2d page
# describes (its one accepted solve).
ROUNDOFF_LEVEL = 1


def _sci(v: float) -> str:
    """``v`` to :data:`STYLE` ``page_digits`` significant digits in the pages' e-notation."""
    mant, exp = f"{v:.{STYLE['page_digits'] - 1}e}".split("e")
    return f"{mant}e{int(exp)}"


def substitutions(roots: Roots = DEFAULT_ROOTS) -> dict[str, str]:
    """``{"lim_<name>": text}``: the numbers the limitations pages print beside these figures,
    from the functions the figures draw. ``lim_roundoff_min_psi``, ``lim_roundoff_region``,
    ``lim_roundoff_update`` and ``lim_roundoff_bound``: the accepted solve of level
    :data:`ROUNDOFF_LEVEL` of :func:`roundoff_points`; ``lim_ccox_acc`` and ``lim_ccox_inv``: C/Cox
    per drawn area of the nfet's Lmin start cell (:func:`c_over_cox`) at the accumulation and
    inversion ends of its sweep."""
    k = roundoff_points(roots)
    (p,) = [p for p in k["points"] if p["level"] == ROUNDOFF_LEVEL]
    nfet = c_over_cox(EVIDENCE_DEVICE, roots)
    cell = nfet[CCOX_CELLS[EVIDENCE_DEVICE][0]]
    ccox = STYLE["ccox_digits"]
    return {
        "lim_roundoff_min_psi": _sci(p["min_abs_psi"]),
        "lim_roundoff_region": p["region"],
        "lim_roundoff_update": _sci(p["abs_error"]),
        "lim_roundoff_bound": _sci(k["bound"]),
        "lim_ccox_acc": f"{cell['ratio'][np.argmin(cell['u'])]:.{ccox}f}",
        "lim_ccox_inv": f"{cell['ratio'][np.argmax(cell['u'])]:.{ccox}f}",
    }


# --- the registry -------------------------------------------------------------------------------


def _svg_of(draw: Callable) -> Callable[[str, Roots], bytes]:
    def svg(palette: str, roots: Roots = DEFAULT_ROOTS) -> bytes:
        with matplotlib.rc_context(ef.palette_rc(palette)):
            return ef.svg_bytes(draw(palette, roots))

    svg.__doc__ = f":func:`{draw.__name__}` as SVG bytes, saved inside the palette's rc context."
    return svg


FIGURES: dict[str, Callable[[str, Roots], bytes]] = {
    "engine-diff": _svg_of(engine_diff_figure),
    "engine-subthreshold": _svg_of(engine_subthreshold_figure),
    "vertex-grid": _svg_of(vertex_grid_figure),
    "c-over-cox": _svg_of(c_over_cox_figure),
    "twod-validation": _svg_of(two_d_validation_figure),
    "twod-metrics": _svg_of(two_d_metrics_figure),
    "roundoff": _svg_of(roundoff_figure),
    "sd-profile": _svg_of(sd_profile_figure),
    "mesh-grading": _svg_of(mesh_grading_figure),
    "meshconv-1d": _svg_of(meshconv_1d_figure),
    "meshconv-2d": _svg_of(meshconv_2d_figure),
    "pn-slab": _svg_of(pn_slab_figure),
    "pin-depletion": _svg_of(pin_depletion_figure),
}


def write_all(out_dir: Path, roots: Roots = DEFAULT_ROOTS) -> None:
    """Write every figure of :data:`FIGURES` as ``<name>-light.svg`` and ``<name>-dark.svg``,
    from the trees of ``roots``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, draw in FIGURES.items():
        for palette in ef.PALETTES:
            (out / f"{name}-{palette}.svg").write_bytes(draw(palette, roots))
