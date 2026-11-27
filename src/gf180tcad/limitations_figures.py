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
import re
import sys
from collections.abc import Callable
from pathlib import Path

import matplotlib
import matplotlib.lines
import matplotlib.patches
import matplotlib.ticker
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
from gf180tcad.tcad import analytic, meshconv, moscap1d, moscap2d, process, stack
from gf180tcad.tcad.mesh import MeshSpec

STYLE = {
    # Two rows of panels: a taller figure at the explainer figures' width.
    "tall_in": (6.4, 7.2),
    "marker_pt": 9.0,
    "small_marker_pt": 6.0,
    "device_ls": {"nfet_05v0": "-", "pfet_05v0": "--"},
    # the checks figure has four panels and a long legend; the tolerance figure's bottom panel
    # holds the long study labels
    "checks_in": (8.0, 11.0),
    # the Newton figure: the iteration panel, then three panels of one row per case
    "newton_in": (8.0, 18.0),
    "newton_rows": (1.3, 1.0, 1.3, 1.0, 1.0, 1.0),
    # one marker per failed solve in the Newton figure's iteration panels
    "newton_markers": ("o", "s", "^", "v", "D", "P", "X", "*"),
    # A failed solve alternates (a period-two cycle) when, over its last iterations, the
    # condition number of J on even and on odd iterations each repeats within the parity
    # spread, and the two values differ by at least the ratio.
    "newton_cycle_window": 20,
    # the Newton figure's second panel shows the solves whose smallest WRMS norm is below this,
    # over the last newton_cycle_window iterations
    "newton_inset_top": 2.0,
    # the minor ticks labelled on the Newton figure's residual-ratio axis, per decade
    "newton_res_subs": (2.0, 5.0),
    "newton_cycle_parity": 0.01,
    "newton_cycle_ratio": 2.0,
    "legend_beside": (1.01, 1.0),
    "tolerance_rows": (1.0, 1.4),
    # exact zeros of a relative change are drawn this factor below its smallest nonzero value
    "zero_floor_factor": 3.0,
    # the small marker on every point of a relative-change line (pt)
    "point_ms": 2.5,
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
    # The decimals of a level's largest change (%) the mesh-convergence page prints.
    "meshconv_change_digits": 3,
    # The plugin record: bar width (V) of the region ranges.
    "bar_width": 0.02,
    "hatch": "//",
    "bias_pad_v": 0.05,
    "legend_cols": 2,
    # The numbers the pages print: significant digits of e-notation, decimals of C/Cox.
    "page_digits": 2,
    "ccox_digits": 3,
    # The edge-sensitivity figure: the plateau biases (u, V) of the record, and the equal-gain
    # line's span past the largest gain (fraction).
    "edge_u_v": (-5.0, 5.0),
    "edge_headroom": 1.15,
    # The digits the page prints: gains and residuals (fF/µm), the slope (fF/µm per nm), δ (nm).
    "edge_digits": 3,
    # The Charon strip figure: the span (nm) shown around the poly/oxide interface.
    "strip_span_nm": (-20.0, 40.0),
    "edge_slope_digits": 5,
    "edge_delta_digits": 1,
    # The rerun check of the fitted poly length bias (plan Task E3, Decision 4): the share of
    # slope × δ allowed for the record's linearity (bias60 is twice bias30 within it), and the
    # record's variant lengths (nm) whose quadratic bounds the gain's non-linearity at δ.
    "edge_linearity": 0.02,
    "edge_quadratic_nm": (30, 60),
    # The digits of the tolerances and their sum of weights the page prints.
    "edge_weight_digits": 2,
    "edge_tol_digits": 4,
    # The abrupt-junction figure and numbers: significant digits of a width (µm) and of V_t,
    # of V_bi (as the page's junction drops), of a width difference, and the x span past the
    # widest bar (fraction) that leaves room for its value.
    "width_digits": 4,
    "vbi_digits": 6,
    "delta_digits": 2,
    "width_pad": 0.25,
    # Enough significant digits to print every input of that record as the record holds it.
    "input_digits": 10,
    # The decimals of the v0.8.0 junction drop (V), as the page's ramp tables print it.
    "drop_decimals": 5,
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
    # NOX's WRMS test passes below this value: <Parameter name="Tolerance" type="double"
    # value="1.0" /> under "Test Type" NormWRMS in every inp.xml charonInterpreter.py writes for
    # the experiments (results/charon-experiments, the Charon 2.2 image of docker/CHARON_IMAGE).
    "nox_wrms_tolerance": 1.0,
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


# The cells of the 2D validation figure: the shortest nfet cell and the pfet L = 2 µm cell,
# both Disagree on the depletion crossing.
VALIDATION_CELLS = (("nfet_05v0", "w10p0_l0p60"), ("pfet_05v0", "w10p0_l2p00"))


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


#: The records of the 2D mesh-convergence check at the fitted poly length bias
#: (``experiments/meshconv-fitted/record.py``; plan Task E3, Decision 5), one per device.
MESHCONV_FITTED_ROOT = REPO_ROOT / "results" / "meshconv-fitted"


def meshconv_fitted_root(roots: Roots = DEFAULT_ROOTS) -> Path:
    """The fitted-bias mesh-convergence records of ``roots``: ``meshconv-fitted`` beside its SPICE
    tree, so the committed :data:`MESHCONV_FITTED_ROOT` for the committed trees."""
    return Path(roots.spice).parent / "meshconv-fitted"


def meshconv_fitted(device: str, roots: Roots = DEFAULT_ROOTS) -> dict:
    """The committed fitted-bias mesh-convergence record of ``device``."""
    return json.loads((meshconv_fitted_root(roots) / f"{device}.json").read_text("utf-8"))


def meshconv_2d_fitted_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """Per device: the change |C / C_finer - 1| of the 2D levels 0 and 1 at the fitted poly
    length bias and the calibrated values (solid), the committed study's selected level at the
    start values (dashed), and the 1 % criterion."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    start = meshconv_curves(2, roots)
    colours = ("electron", "hole")
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        axes = fig.subplots(len(_DEVICES), 1, sharex=True)
        for ax, device in zip(axes, _DEVICES, strict=True):
            rec = meshconv_fitted(device, roots)
            rep = rec["report"]
            u = DEVICES[device].polarity * np.asarray(rep["vg"])
            tops = [rec["check"]["criterion"]]
            for i, lv in enumerate(rep["levels"]):
                if lv["rel_change"] is None:
                    continue
                change = np.abs(lv["rel_change"])
                tops.append(float(np.max(change)))
                ax.plot(u, change, color=pal[colours[i]], lw=lw,
                        label=f"level {i}, fitted bias", gid=f"{device} fitted level {i}")  # fmt: skip
            c = start[device]
            (sel,) = [lv for lv in c["levels"] if lv["level"] == c["selected"]]
            tops.append(float(np.max(sel["change"])))
            ax.plot(c["u"], sel["change"], color=pal[colours[c["selected"]]], lw=lw, ls="--",
                    label=f"level {c['selected']}, start values, drawn poly",
                    gid=f"{device} start level {c['selected']}")  # fmt: skip
            crit = rec["check"]["criterion"]
            ax.axhline(crit, color=pal["text"], lw=ef.STYLE["edge_width"], ls="--",
                       gid=f"{device} criterion")  # fmt: skip
            ax.text(u[0], crit, f" {crit * UNITS['percent']:g} %", ha="left", va="bottom")
            ax.set_yscale("log")
            ax.set_ylim(top=max(tops) * STYLE["criterion_headroom"])
            ax.set_ylabel(f"{_SHORT[device]}: change\nto next level")
            ax.grid(True)
        axes[-1].set_xlabel("u = polarity × Vg (V)")
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside lower center", ncols=STYLE["legend_cols"],
                   frameon=False)  # fmt: skip
        return fig


# --- the 2D edge sensitivity (issue #189) ---------------------------------------------------------

#: The committed edge-sensitivity records (``experiments/edge-sensitivity/record.py``): one per
#: device, at its shortest W = 10 µm calibrated 2D cell.
EDGE_CELLS = (("nfet_05v0", "w10p0_l0p60"), ("pfet_05v0", "w10p0_l0p50"))
EDGE_ROOT = REPO_ROOT / "results" / "edge-sensitivity"

# The variant families of the record, by the parts of their names, and how the figure draws them.
_EDGE_FAMILIES = (
    ("plugs+bias", "contact plugs and a longer poly", "hole", "D"),
    ("ldd", "a longer poly over an extension", "intrinsic", "s"),
    ("bias", "a longer poly", "electron", "o"),
    ("plugs", "contact plugs", "highlight", "^"),
)


def _edge_family(variant: str) -> str:
    """The family of a variant name: ``plugs+bias``, ``ldd`` (any variant with an extension),
    ``bias`` or ``plugs``."""
    if "ldd" in variant:
        return "ldd"
    if variant.startswith("plugs+bias"):
        return "plugs+bias"
    if variant.startswith("bias"):
        return "bias"
    if variant == "plugs":
        return "plugs"
    raise ValueError(f"no family for the variant {variant!r}")


def edge_root(roots: Roots = DEFAULT_ROOTS) -> Path:
    """The edge-sensitivity records of ``roots``: ``edge-sensitivity`` beside its SPICE tree, so
    the committed :data:`EDGE_ROOT` for the committed trees."""
    return Path(roots.spice).parent / "edge-sensitivity"


def edge_record(device: str, gid: str, root: Path = EDGE_ROOT) -> dict:
    """The committed record of ``device``'s cell ``gid`` (FileNotFoundError if missing)."""
    return json.loads((Path(root) / f"{device}-{gid}.json").read_text("utf-8"))


def edge_gains(device: str, gid: str, root: Path = EDGE_ROOT) -> dict[str, tuple[float, float]]:
    """``{variant: (gain at u = -5 V, gain at u = +5 V)}``: each variant's Cgg per unit width
    minus the base's (fF/µm), at the record's two biases (u = polarity × Vg)."""
    rec = edge_record(device, gid, root)
    pol = DEVICES[device].polarity
    base = rec["variants"]["base"]

    def at(v: dict) -> dict[float, float]:
        return {pol * vg: c for vg, c in zip(v["vg"], v["cgg_ff_per_um"], strict=True)}

    b = at(base)
    lo, hi = STYLE["edge_u_v"]
    return {
        name: (at(v)[lo] - b[lo], at(v)[hi] - b[hi])
        for name, v in rec["variants"].items()
        if name != "base"
    }


def edge_targets(device: str, roots: Roots = DEFAULT_ROOTS) -> tuple[float, float]:
    """The 2D edge's shortfall against SPICE (fF/µm) at u = -5 and +5 V that the poly length
    bias is fitted to: the SPICE minus the 2D ``C_edge`` of the δ = 0 cells.

    Once the fit is committed (``<tcad root>/edgefit``, :mod:`gf180tcad.tcad.edgefit`), they are
    its frozen targets, because the committed cells are then the fitted ones (plan Task E3).
    For a results tree without a fit, they come from the live edge split of its cells
    (:func:`gf180tcad.comparison_figures.edge_split`)."""
    from gf180tcad.tcad import edgefit

    fit = edgefit.read(device, Path(roots.tcad) / "edgefit")
    if fit is not None:
        lo, hi = fit["targets_ff_per_um"]
        return float(lo), float(hi)
    from gf180tcad.comparison_figures import edge_split

    s = edge_split(device, roots.spice, roots.tcad)
    out = []
    for u in STYLE["edge_u_v"]:
        (i,) = np.flatnonzero(s["u"] == u)
        out.append(float(s["spice"]["edge"][i] - s["two_d"]["edge"][i]))
    return out[0], out[1]


def edge_fit(device: str, gid: str, roots: Roots = DEFAULT_ROOTS) -> dict:
    """The least-squares poly length bias of ``device`` (issue #189).

    A poly longer by δ at each end adds the same Cgg per width on both plateaus, ``slope`` × δ
    (fF/µm per nm): the line through the origin of the record's ``bias<nm>`` variants, both
    biases. δ minimises the squared misses of the two targets, so ``slope`` × δ is their mean.
    Returns ``slope``, ``targets``, ``delta_nm`` and the ``residual`` (fF/µm) at each plateau,
    target minus gain."""
    gains = edge_gains(device, gid, edge_root(roots))
    xs, ys = [], []
    for name, (lo, hi) in gains.items():
        if name.startswith("bias") and name[len("bias") :].isdigit():
            xs += [float(name[len("bias") :])] * 2
            ys += [lo, hi]
    if not xs:
        raise ValueError(f"{device} {gid}: no bias<nm> variant in the record")
    x, y = np.array(xs), np.array(ys)
    slope = float(x @ y / (x @ x))
    targets = edge_targets(device, roots)
    delta = float(np.mean(targets)) / slope
    return {
        "slope": slope,
        "targets": targets,
        "delta_nm": delta,
        "residual": tuple(t - slope * delta for t in targets),
    }


def edge_sensitivity_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """Per device: each variant's gain at u = +5 V against its gain at u = -5 V, the target
    (SPICE minus 2D edge), the line of equal gain on which every longer poly lies, and the
    least-squares δ on that line."""
    pal = ef.PALETTES[palette]
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        axes = fig.subplots(1, len(EDGE_CELLS))
        for ax, (device, gid) in zip(axes, EDGE_CELLS, strict=True):
            gains = edge_gains(device, gid, edge_root(roots))
            fit = edge_fit(device, gid, roots)
            top = STYLE["edge_headroom"] * max(
                [*fit["targets"], *(v for g in gains.values() for v in g)]
            )
            ax.plot([0, top], [0, top], color=pal["band"], lw=ef.STYLE["line_width"],
                    label="equal gain", gid=f"{device} equal")  # fmt: skip
            for prefix, label, colour, marker in _EDGE_FAMILIES:
                names = [n for n in gains if _edge_family(n) == prefix]
                if not names:
                    continue
                ax.plot([gains[n][0] for n in names], [gains[n][1] for n in names], ls="none",
                        marker=marker, ms=STYLE["marker_pt"], color=pal[colour], label=label,
                        gid=f"{device} {prefix}")  # fmt: skip
            lo, hi = fit["targets"]
            ax.plot([lo], [hi], ls="none", marker="*", ms=STYLE["ring_pt"], color=pal["text"],
                    label="target: SPICE minus 2D", gid=f"{device} target")  # fmt: skip
            g = fit["slope"] * fit["delta_nm"]
            ax.plot([g], [g], ls="none", marker="o", ms=STYLE["ring_pt"], mfc="none",
                    color=pal["text"], label="fitted poly length bias", gid=f"{device} fit")  # fmt: skip
            ax.set_title(
                f"{_SHORT[device]} {_label(_geometry(device, gid))}", fontsize=ef.STYLE["text_pt"]
            )
            lo_u, hi_u = STYLE["edge_u_v"]
            ax.set_xlabel(f"gain at u = {lo_u:+g} V (fF/µm)".replace("-", "−"))
            ax.set_ylabel(f"gain at u = {hi_u:+g} V (fF/µm)")
            ax.grid(True)
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside lower center", ncols=STYLE["legend_cols"],
                   frameon=False)  # fmt: skip
        return fig


def edge_nonlinearity(device: str, gid: str, fit: dict, roots: Roots = DEFAULT_ROOTS) -> float:
    """The record's bound (fF/µm) on how far the gain at the fit's applied δ departs from
    slope × δ: the quadratic through 0 and the two record variants of
    :data:`STYLE` ``edge_quadratic_nm``, against the fitted line, worst plateau."""
    rec = edge_record(device, gid, edge_root(roots))["variants"]
    pol = DEVICES[device].polarity

    def at(v: dict) -> list[float]:
        by_u = {pol * vg: c for vg, c in zip(v["vg"], v["cgg_ff_per_um"], strict=True)}
        return [by_u[u] for u in STYLE["edge_u_v"]]

    n1, n2 = STYLE["edge_quadratic_nm"]
    base, g1, g2 = at(rec["base"]), at(rec[f"bias{n1}"]), at(rec[f"bias{n2}"])
    delta, slope = fit["poly_bias_nm"], fit["slope_ff_per_um_per_nm"]
    worst = 0.0
    for b, c1, c2 in zip(base, g1, g2, strict=True):
        y1, y2 = c1 - b, c2 - b
        quad = (y2 * n1 - y1 * n2) / (n1 * n2 * (n2 - n1))
        lin = (y1 - quad * n1**2) / n1
        worst = max(worst, abs(lin * delta + quad * delta**2 - slope * delta))
    return worst


def edge_rerun(device: str, roots: Roots = DEFAULT_ROOTS) -> dict:
    """The check of the cells rerun at the committed poly length bias fit (plan Task E3,
    Decision 4), from the fit file's frozen δ = 0 rows and today's cells.

    Per W = 10 µm cell (``cells``): its length, its gain over the frozen δ = 0 Cgg per unit width
    at each plateau of :data:`STYLE` ``edge_u_v`` (fF/µm), and its tolerance there: the 2D mesh
    criterion (:data:`gf180tcad.tcad.meshconv.CRITERION` of the cell's Cgg) plus
    :func:`edge_nonlinearity`. ``want`` is slope × δ. Per device: the live edge split's ``gap``
    (SPICE minus 2D ``C_edge``) at each plateau, the fit's frozen ``residual`` and the ``bound``
    on their difference, Σ|wᵢ| × the largest per-cell tolerance plus :data:`STYLE`
    ``edge_linearity`` × slope × δ (wᵢ: the intercept's least-squares weights, ``weights``)."""
    from gf180tcad.calibrate import edge
    from gf180tcad.tcad import edgefit

    fit = edgefit.read(device, Path(roots.tcad) / "edgefit")
    if fit is None:
        raise FileNotFoundError(f"{device}: no poly length bias fit under {roots.tcad}")
    gid = edge.RECORD_CELLS[device]
    nonlin = edge_nonlinearity(device, gid, fit, roots)
    want = fit["slope_ff_per_um_per_nm"] * fit["poly_bias_nm"]
    geoms = {geometry_id(g): g for g in DEVICES[device].geometries}
    rows, cells = [], []
    for frozen in fit["cells"]:
        row = edge.cell_row(device, geoms[frozen["gid"]], roots.spice, roots.tcad)
        rows.append(row)
        cells.append({
            "gid": row["gid"],
            "l_um": row["l_um"],
            "gain": [c - c0 for c, c0 in zip(row["two_d"], frozen["two_d"], strict=True)],
            "tol": [meshconv.CRITERION * c + nonlin for c in row["two_d"]],
        })  # fmt: skip
    spice, two_d = edge.intercepts(rows, "spice"), edge.intercepts(rows, "two_d")
    weights = float(np.abs(edge.intercept_weights(rows)).sum())
    bound = [
        weights * max(c["tol"][i] for c in cells) + STYLE["edge_linearity"] * want
        for i in range(len(STYLE["edge_u_v"]))
    ]
    return {
        "cells": cells,
        "applied_nm": float(fit["poly_bias_nm"]),
        "want": want,
        "nonlinearity": nonlin,
        "weights": weights,
        "gap": [a - b for a, b in zip(spice, two_d, strict=True)],
        "residual": [float(r) for r in fit["residual_ff_per_um"]],
        "bound": bound,
    }


def edge_rerun_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """Per device: each rerun W = 10 µm cell's gain over its δ = 0 Cgg per unit width against L,
    at both plateaus, with slope × δ and each plateau's tolerance band around it."""
    pal = ef.PALETTES[palette]
    lo_u, hi_u = STYLE["edge_u_v"]
    sides = ((f"u = {lo_u:+g} V".replace("-", "\u2212"), "electron", "o"),
             (f"u = {hi_u:+g} V", "hole", "s"))  # fmt: skip
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        axes = fig.subplots(1, len(EDGE_CELLS))
        for ax, (device, _gid) in zip(axes, EDGE_CELLS, strict=True):
            r = edge_rerun(device, roots)
            lengths = [c["l_um"] for c in r["cells"]]
            ax.axhline(r["want"], color=pal["text"], lw=ef.STYLE["line_width"],
                       label="slope × δ", gid=f"{device} want")  # fmt: skip
            for i, (label, colour, marker) in enumerate(sides):
                tol = np.array([c["tol"][i] for c in r["cells"]])
                ax.fill_between(lengths, r["want"] - tol, r["want"] + tol, color=pal[colour],
                                alpha=ef.STYLE["band_alpha"]["highlight"], lw=0,
                                label=f"tolerance at {label}", gid=f"{device} tol {i}")  # fmt: skip
                ax.plot(lengths, [c["gain"][i] for c in r["cells"]], ls="none", marker=marker,
                        ms=STYLE["marker_pt"], color=pal[colour], label=f"gain at {label}",
                        gid=f"{device} gain {i}")  # fmt: skip
            ax.set_title(_SHORT[device], fontsize=ef.STYLE["text_pt"])
            ax.set_xlabel("L (µm)")
            ax.set_ylabel("gain over the drawn poly (fF/µm)")
            ax.grid(True)
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside lower center", ncols=STYLE["legend_cols"],
                   frameon=False)  # fmt: skip
        return fig


# --- the plugin history ---------------------------------------------------------------------------

# The committed records of the plugin-history page: the release at its own mesh, then at half it.
PLUGIN_FILES = ("v0.8.0.json", "v0.8.0-mesh0p5.json")
#: The latest-stack records (issue #162): the same PN slab, solved by the fork at the submodule
#: pin with the connected rib, in the stable TCAD image (``python -m gf180tcad.history --version
#: latest``).
LATEST_FILES = ("latest.json", "latest-mesh0p5.json")
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


def latest_drops(root: Path = PLUGIN_ROOT) -> dict[str, tuple[list[float], list[float]]]:
    """``{name: (cathode biases V, junction drops V)}`` of :data:`LATEST_FILES` under ``root``,
    named as :func:`plugin_records` names the v0.8.0 records ("latest", "latest × 0.5")."""
    out = {}
    for file in LATEST_FILES:
        rec = json.loads((Path(root) / file).read_text("utf-8"))
        slab = rec["pn_slab"]
        scale = rec["mesh_scale"]
        drops = [s["junction"]["drop_v"] for s in (slab["equilibrium"], *slab["bias"])]
        out[rec["gplugins_tag"] + ("" if scale == 1 else f" × {scale:g}")] = (slab["bias_v"], drops)
    return out


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
    potential and the junction drop (top), with the junction drop of the latest-stack records,
    whose rib is connected (:func:`latest_drops`); and the Potential range of the rib (``core``)
    and the slab (``slab90``) at each step of both v0.8.0 meshes (bottom), the half-size mesh
    hatched."""
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
        for (name, (bias, drops)), ls in zip(latest_drops(root).items(), (":", "-."),
                                              strict=True):  # fmt: skip
            top.plot(bias, drops, color=pal["muted"], lw=lw, ls=ls, marker="^",
                     label=f"junction drop, {name} (connected rib)",
                     gid=f"{name} drop")  # fmt: skip
        b = np.array([s["bias"] for s in pn_slab_steps(names[0], root)])
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


#: The record of the ideal abrupt-junction depletion width of the v0.8.0 rib (issue #80),
#: written by ``experiments/plugin-history/abrupt_junction.py``.
ABRUPT_FILE = "abrupt-junction.json"


def abrupt_junction(root: Path = PLUGIN_ROOT) -> dict:
    """The record :data:`ABRUPT_FILE` under ``root``."""
    return json.loads((Path(root) / ABRUPT_FILE).read_text("utf-8"))


def _mesh_words(scale: float) -> str:
    """The page's words for a record's mesh: "full mesh" at its own size, else "mesh × <scale>"."""
    return "full mesh" if scale == 1 else f"mesh × {scale:g}"


def abrupt_widths(root: Path = PLUGIN_ROOT) -> list[tuple[str, float, str]]:
    """``[(label, width µm, palette colour), ...]``: the PN slab's recorded equilibrium depletion
    width in each v0.8.0 record (n and p below the record's fraction of |NetDoping| on the bottom
    edge), then the two widths of the depletion approximation of :func:`abrupt_junction`: the
    span where n and p are below that fraction, and the full width x_n + x_p."""
    rec = abrupt_junction(root)
    pct = f"{rec['fraction'] * UNITS['percent']:g} %"
    out = [(f"{r['gplugins_tag']} {_mesh_words(r['mesh_scale'])}, recorded",
            r["ddcomponent"]["equilibrium"]["depletion_width_um"], colour)
           for r, colour in zip(plugin_records(root).values(), ("electron", "hole"),
                                strict=True)]  # fmt: skip
    out.append((f"approximation, n and p < {pct} |N|", rec["inner_width_um"], "highlight"))
    out.append(("approximation, $x_n + x_p$", rec["width_um"], "muted"))
    return out


def abrupt_junction_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The depletion width of the PN slab's rib junction: the two v0.8.0 records' measured widths
    against the depletion approximation of the same junction (:func:`abrupt_widths`), one
    horizontal bar each, its value written at its end."""
    pal = ef.PALETTES[palette]
    rows = abrupt_widths(plugin_root(roots))
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        ax = fig.subplots()
        span = max(w for _, w, _ in rows)
        for i, (label, width, colour) in enumerate(rows):
            ax.barh(i, width, color=pal[colour], gid=label)
            ax.text(width + span * STYLE["label_lift"], i, f"{width:.{STYLE['width_digits']}g}",
                    va="center", color=pal["text"])  # fmt: skip
        ax.set_yticks(range(len(rows)), [label for label, _, _ in rows])
        ax.invert_yaxis()
        ax.set_xlim(0, span * (1 + STYLE["width_pad"]))
        ax.set_xlabel("depletion width (µm)")
        ax.grid(True, axis="x")
        return fig


def _plain(v: float) -> str:
    """``v`` as the record holds it, in the pages' e-notation (1e17, not 1e+17)."""
    return f"{v:.{STYLE['input_digits']}g}".replace("e+", "e")


def _meshconv_fitted_substitutions(roots: Roots) -> dict[str, str]:
    """The fitted-bias mesh-convergence numbers of the mesh-convergence page, per device
    (``<dev>`` is ``nfet`` or ``pfet``): ``lim_mcfit_<dev>_change_<i>`` the largest change of
    level ``i`` against the next finer one (%), ``lim_mcfit_<dev>_nodes_<i>`` each level's node
    count, ``lim_mcfit_<dev>_selected`` the committed study's selected level, and
    ``lim_mcfit_criterion`` the criterion (%)."""
    digits = STYLE["meshconv_change_digits"]
    out = {}
    for device in _DEVICES:
        dev, rec = _SHORT[device], meshconv_fitted(device, roots)
        out["lim_mcfit_criterion"] = f"{rec['check']['criterion'] * UNITS['percent']:g}"
        for i, lv in enumerate(rec["report"]["levels"]):
            out[f"lim_mcfit_{dev}_nodes_{i}"] = f"{lv['node_count']:,}"
            if lv["max_rel_change"] is not None:
                out[f"lim_mcfit_{dev}_change_{i}"] = (
                    f"{lv['max_rel_change'] * UNITS['percent']:.{digits}f}"
                )
        out[f"lim_mcfit_{dev}_selected"] = f"{rec['check']['selected_level']}"
    return out


def _abrupt_substitutions(roots: Roots) -> dict[str, str]:
    """The plugin-history page's abrupt-junction numbers (``lim_abrupt_*``), from
    :func:`abrupt_junction` and the v0.8.0 records: the inputs (dopings, temperature, constants),
    V_t and V_bi, the widths, the half-mesh record's width minus the approximation's span, its
    depleted nodes and their mean spacing, the own-mesh record's count of depleted nodes, and the
    equilibrium junction drop, the same in both records."""
    root = plugin_root(roots)
    rec = abrupt_junction(root)
    c = rec["constants"]
    d = STYLE["width_digits"]
    full, *_, half = plugin_records(root).values()  # PLUGIN_FILES order: own mesh, then half
    eq = half["ddcomponent"]["equilibrium"]
    measured, nodes = eq["depletion_width_um"], eq["depleted_nodes"]
    drops = {r["ddcomponent"]["equilibrium"]["junction"]["drop_v"] for r in (full, half)}
    (drop,) = {f"{v:.{STYLE['drop_decimals']}f}" for v in drops}  # one drop at both meshes
    return {
        "lim_abrupt_full_nodes": str(full["ddcomponent"]["equilibrium"]["depleted_nodes"]),
        "lim_abrupt_half_nodes": str(nodes),
        "lim_abrupt_spacing": f"{measured / (nodes - 1):.{STYLE['delta_digits']}g}",
        "lim_abrupt_drop": drop,
        "lim_abrupt_na": _plain(rec["doping"]["n_a_cm3"]),
        "lim_abrupt_nd": _plain(rec["doping"]["n_d_cm3"]),
        "lim_abrupt_ni": _plain(c["n_i_cm3"]),
        "lim_abrupt_eps_si": _plain(c["eps_si"]),
        "lim_abrupt_eps0": _plain(c["eps_0_f_per_cm"]),
        "lim_abrupt_q": _plain(c["q_c"]),
        "lim_abrupt_k": _plain(c["k_j_per_k"]),
        "lim_abrupt_t": _plain(rec["t_k"]),
        "lim_abrupt_pct": f"{rec['fraction'] * UNITS['percent']:g}",
        "lim_abrupt_vt": f"{rec['v_t_v']:.{d}g}",
        "lim_abrupt_vbi": f"{rec['v_bi_v']:.{STYLE['vbi_digits']}g}",
        "lim_abrupt_w": f"{rec['width_um']:.{d}g}",
        "lim_abrupt_xn": f"{rec['x_n_um']:.{d}g}",
        "lim_abrupt_inner": f"{rec['inner_width_um']:.{d}g}",
        "lim_abrupt_measured": f"{measured:.{d}g}",
        "lim_abrupt_delta": f"{measured - rec['inner_width_um']:.{STYLE['delta_digits']}g}",
    }


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
    inversion ends of its sweep. ``lim_edge_<dev>_{slope,delta,residual}``: :func:`edge_fit` of
    each :data:`EDGE_CELLS` cell (``<dev>`` is ``nfet`` or ``pfet``); ``lim_edge_<variant>_{acc,inv}``
    (``plugs``, ``bias30``): the nfet record's gains (:func:`edge_gains`) at u = -5 and +5 V."""
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
        **_edge_substitutions(roots),
        **_charon_substitutions(roots),
        **_abrupt_substitutions(roots),
        **_meshconv_fitted_substitutions(roots),
    }


def _edge_substitutions(roots: Roots) -> dict[str, str]:
    """The edge section's numbers: per device the fit's slope, δ and signed miss (target minus
    gain) at each plateau and the target's step from u = -5 to +5 V; from the nfet record the plug height, the plug and bias30 gains, and
    the extension variants' common poly bias and spacer and the range of their gains."""

    def fmt(v: float) -> str:
        return f"{v:.{STYLE['edge_digits']}f}".replace("-", "\u2212")

    out = {}
    for device, gid in EDGE_CELLS:
        fit = edge_fit(device, gid, roots)
        dev = _SHORT[device]
        out[f"lim_edge_{dev}_slope"] = f"{fit['slope']:.{STYLE['edge_slope_digits']}f}"
        out[f"lim_edge_{dev}_delta"] = f"{fit['delta_nm']:.{STYLE['edge_delta_digits']}f}"
        for side, r in zip(("acc", "inv"), fit["residual"], strict=True):
            out[f"lim_edge_{dev}_miss_{side}"] = fmt(r)
        out[f"lim_edge_{dev}_target_step"] = fmt(fit["targets"][1] - fit["targets"][0])
    device, gid = EDGE_CELLS[0]
    root = edge_root(roots)
    gains = edge_gains(device, gid, root)
    for variant in ("plugs", "bias30"):
        for side, g in zip(("acc", "inv"), gains[variant], strict=True):
            out[f"lim_edge_{variant}_{side}"] = fmt(g)
    variants = edge_record(device, gid, root)["variants"]
    (plug_um,) = {v["plug_um"] for v in variants.values() if v["plugs"]}
    out["lim_edge_plug_um"] = f"{plug_um:g}"
    ldd = [n for n in gains if _edge_family(n) == "ldd"]
    (bias_um,) = {variants[n]["bias_um"] for n in ldd}
    (spacer_um,) = {variants[n]["ldd"]["spacer_um"] for n in ldd}
    out["lim_edge_ldd_bias_nm"] = f"{bias_um * UNITS['nm_per_um']:.0f}"
    out["lim_edge_ldd_spacer_nm"] = f"{spacer_um * UNITS['nm_per_um']:.0f}"
    for i, side in enumerate(("acc", "inv")):
        lo, hi = (fmt(f([gains[n][i] for n in ldd])) for f in (min, max))
        out[f"lim_edge_ldd_{side}"] = lo if lo == hi else f"{lo} to {hi}"
    tol = STYLE["edge_tol_digits"]
    for device, _gid in EDGE_CELLS:
        dev, r = _SHORT[device], edge_rerun(device, roots)
        out[f"lim_edge_{dev}_want"] = fmt(r["want"])
        out[f"lim_edge_{dev}_applied"] = f"{r['applied_nm']:g}"
        miss = max(abs(g - r["want"]) for c in r["cells"] for g in c["gain"])
        out[f"lim_edge_{dev}_rerun_miss"] = f"{miss:.{tol}f}"
        out[f"lim_edge_{dev}_rerun_tol"] = f"{min(t for c in r['cells'] for t in c['tol']):.{tol}f}"
        out[f"lim_edge_{dev}_nonlin"] = f"{r['nonlinearity']:.{tol}f}"
        out[f"lim_edge_{dev}_weights"] = f"{r['weights']:.{STYLE['edge_weight_digits']}f}"
        for i, side in enumerate(("acc", "inv")):
            out[f"lim_edge_{dev}_gap_{side}"] = fmt(r["gap"][i])
            out[f"lim_edge_{dev}_gap_off_{side}"] = f"{abs(r['gap'][i] - r['residual'][i]):.{tol}f}"
            out[f"lim_edge_{dev}_gap_bound_{side}"] = f"{r['bound'][i]:.{tol}f}"
    return out


# --- the Charon backend experiments ---------------------------------------------------------------

#: The committed Charon experiment records (``experiments/charon-backend/record.py``): the C-V
#: runs (``cv.json``), the solver variants through the onset of inversion (``hard-range.json``)
#: and the other probes (``probes.json``).
CHARON_ROOT = REPO_ROOT / "results" / "charon-experiments"

#: The reference C-V run of each device: short SRH lifetimes, LOCA sub-steps, WRMS 1e-10.
CHARON_REF = {"nfet_05v0": "cv-nfet-tau15-1e-10", "pfet_05v0": "cv-pfet-tau15-1e-10"}

#: The runs compared with the reference to show what it does not depend on: another lifetime,
#: a looser tolerance, and the default lifetime (which converges in accumulation and depletion
#: only). Each is drawn as ``abs(C / C_ref - 1)`` over the biases both have.
CHARON_CHECKS = {
    "cv-nfet-tau14-1e-10": ("nfet_05v0", "another SRH lifetime", "highlight"),
    "cv-pfet-tau14-1e-10": ("pfet_05v0", "another SRH lifetime", "highlight_oxide"),
    "cv-nfet-tau15-1e-9": ("nfet_05v0", "WRMS tolerance ten times looser", "intrinsic"),
    "cv-nfet-default-1e-10": ("nfet_05v0", "the default SRH lifetime", "muted"),
}


def charon_root(roots: Roots = DEFAULT_ROOTS) -> Path:
    """The Charon experiment records of ``roots``: ``charon-experiments`` beside its SPICE tree,
    so the committed :data:`CHARON_ROOT` for the committed trees."""
    return Path(roots.spice).parent / "charon-experiments"


def charon_record(name: str, root: Path = CHARON_ROOT) -> dict:
    """The committed record ``name`` (``cv``, ``hard-range`` or ``probes``)."""
    return json.loads((Path(root) / f"{name}.json").read_text("utf-8"))


def _setting(run: dict, key: str) -> str:
    return run["settings"][key] or "default"


def charon_cv_curves(roots: Roots = DEFAULT_ROOTS) -> dict:
    """Per device the reference run's u = polarity * vg, Charon's and DEVSIM's C (fF/um^2) and
    ``abs(C_Charon / C_DEVSIM - 1)``; per check run its u and ``abs(C / C_ref - 1)`` on the
    common biases."""
    runs = charon_record("cv", charon_root(roots))["runs"]
    out = {"devices": {}, "checks": {}}
    for device, name in CHARON_REF.items():
        r = runs[name]
        pol = DEVICES[device].polarity
        c, dv = np.asarray(r["c_ff_um2"]), np.asarray(r["c_devsim"])
        out["devices"][device] = {"u": pol * np.asarray(r["vg"]), "c": c, "devsim": dv,
                                  "rel": np.abs(c / dv - 1), "run": name}  # fmt: skip
    for name, (device, what, colour) in CHARON_CHECKS.items():
        r, ref = runs[name], runs[CHARON_REF[device]]
        vg = [v for v in r["vg"] if v in ref["vg"]]
        c = np.asarray([r["c_ff_um2"][r["vg"].index(v)] for v in vg])
        c_ref = np.asarray([ref["c_ff_um2"][ref["vg"].index(v)] for v in vg])
        out["checks"][name] = {
            "device": device,
            "what": what,
            "colour": colour,
            "u": DEVICES[device].polarity * np.asarray(vg),
            "rel": np.abs(c / c_ref - 1),
            "tau": _setting(r, "CX_TAU"),
            "rel_tol": _setting(r, "CX_REL"),
        }
    return out


def charon_cv_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """Top: the 1D C-V of both devices from Charon (points) and DEVSIM (lines). Bottom, log:
    Charon's relative difference from DEVSIM, and from Charon's reference run of each run that
    changes one setting, against the 1 % comparison tolerance."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["line_width"]
    k = charon_cv_curves(roots)
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        top, bottom = fig.subplots(2, 1, sharex=True)
        for device, d in k["devices"].items():
            short, colour = _SHORT[device], pal[_CARRIER[device]]
            top.plot(d["u"], d["devsim"], color=colour, lw=lw, label=f"{short} DEVSIM",
                     gid=f"{device} DEVSIM")  # fmt: skip
            top.plot(d["u"], d["c"], ls="none", marker="o", ms=STYLE["small_marker_pt"],
                     mfc="none", color=colour, label=f"{short} Charon",
                     gid=f"{device} Charon")  # fmt: skip
            bottom.plot(d["u"], d["rel"], color=colour, lw=lw,
                        label=f"{short}: Charon against DEVSIM",
                        gid=f"{device} against DEVSIM")  # fmt: skip
        for name, c in k["checks"].items():
            bottom.plot(c["u"], c["rel"], color=pal[c["colour"]], lw=ef.STYLE["edge_width"],
                        label=f"{_SHORT[c['device']]}: {c['what']} (tau {c['tau']} s, "
                        f"WRMS {c['rel_tol']}) against the reference", gid=name)  # fmt: skip
        bottom.axhline(meshconv.CRITERION, color=pal["text"], ls="--", lw=ef.STYLE["edge_width"],
                       label="comparison tolerance", gid="tolerance")  # fmt: skip
        bottom.set_yscale("log")
        top.set_ylabel("C per area (fF/µm²)")
        bottom.set_ylabel("relative difference")
        bottom.set_xlabel("u = polarity × Vg (V)")
        top.grid(True)
        bottom.grid(True)
        fig.legend(loc="outside lower center", ncols=1, frameon=False,
                   fontsize=STYLE["legend_scale"] * ef.STYLE["text_pt"])  # fmt: skip
        return fig


def charon_hard_range_points(roots: Roots = DEFAULT_ROOTS) -> dict:
    """Per solver variant of the hard-range record (in the record's order): the last converged
    device bias (V; the sweep end when it converged throughout) and whether it did."""
    rec = charon_record("hard-range", charon_root(roots))
    out = {}
    for name, v in rec["variants"].items():
        out[name] = {"reached_v": v["last_converged_v"] if v["equilibrium_converged"] else None,
                     "passed": v["sweep_converged"], "end_v": v["end_v"]}  # fmt: skip
    return out


def charon_hard_range_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The last device bias each solver variant converged at, sweeping up from 0 V: filled where
    the sweep reached its end, hollow where it stopped; variants whose equilibrium failed sit at
    0 V as crosses."""
    pal = ef.PALETTES[palette]
    k = charon_hard_range_points(roots)
    names = list(k)
    y = np.arange(len(names))
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        ax = fig.subplots()
        groups = (
            ("reached the sweep end", lambda p: p["passed"], "o", pal["highlight"]),
            (
                "failed after its last converged bias",
                lambda p: not p["passed"] and p["reached_v"] is not None,
                "o",
                "none",
            ),
            ("equilibrium failed", lambda p: p["reached_v"] is None, "x", pal["text"]),
        )
        for label, pick, marker, face in groups:
            idx = [i for i, n in enumerate(names) if pick(k[n])]
            xs = [k[names[i]]["reached_v"] or 0.0 for i in idx]
            ax.scatter(xs, y[idx], marker=marker, s=STYLE["marker_pt"] ** 2,
                       facecolors=face if marker == "o" else pal["text"],
                       edgecolors=pal["highlight"] if marker == "o" else None,
                       label=label, gid=label)  # fmt: skip
        ax.set_yticks(y, names)
        ax.invert_yaxis()
        ax.set_xlabel("last converged gate bias of the device (V)")
        ax.grid(True, axis="x")
        fig.legend(loc="outside lower center", ncols=STYLE["legend_cols"], frameon=False)
        return fig


def charon_strip_mesh(roots: Roots = DEFAULT_ROOTS) -> dict:
    """The nfet reference run's strip near the oxide: per layer its node positions (nm from the
    poly/oxide interface) within :data:`STYLE` ``strip_span_nm``, and the strip width (um)."""
    run = charon_record("cv", charon_root(roots))["runs"][CHARON_REF["nfet_05v0"]]
    x = np.asarray(run["x_um"]) * UNITS["nm_per_um"]
    bn = run["boundary_nodes"]
    x0 = x[bn[1]]
    lo, hi = STYLE["strip_span_nm"]
    out = {"layers": {}, "width_um": run["strip_width_um"]}
    for i, layer in enumerate(run["layers"]):
        xs = x[bn[i] : bn[i + 1] + 1] - x0
        keep = xs[(xs >= lo) & (xs <= hi)]
        out["layers"][layer] = {"x_nm": keep, "span": (max(xs[0], lo), min(xs[-1], hi))}
    return out


def charon_strip_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """The 1D stack as Charon reads it: the description's nodes extruded into a strip one element
    wide, shown near the oxide. Each vertical line is a node pair (x, 0) and (x, w); the shading
    marks the element blocks."""
    pal = ef.PALETTES[palette]
    k = charon_strip_mesh(roots)
    colours = {"gate_poly": "electron", "oxide": "highlight_oxide", "body": "hole"}
    w = k["width_um"]
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(ef.STYLE["size_in"])
        ax = fig.subplots()
        for layer, d in k["layers"].items():
            lo, hi = d["span"]
            ax.axvspan(lo, hi, color=pal[colours[layer]], alpha=ef.STYLE["fill_alpha"], lw=0,
                       label=f"block {layer}", gid=f"block {layer}")  # fmt: skip
            segment = [0.0, w, np.nan]  # one node pair: bottom, top, a break
            xs = np.repeat(d["x_nm"], len(segment))
            ys = np.tile(segment, len(d["x_nm"]))
            ax.plot(xs, ys, color=pal[colours[layer]], lw=ef.STYLE["edge_width"],
                    gid=f"nodes {layer}")  # fmt: skip
        ax.set_xlabel("distance from the poly/oxide interface (nm)")
        ax.set_ylabel("strip width (µm)")
        fig.legend(loc="outside lower center", ncols=len(k["layers"]), frameon=False)
        return fig


#: The reference variant of ``hard-range.json``: the project's lifetimes at the reference
#: tolerance; the page gives the bias where it stops and its residual there.
CHARON_REF_VARIANT = "ref_1e-10"
#: The B7 step study of a ten times tighter WRMS tolerance (``hard-range.json``,
#: ``step_studies``).
CHARON_TIGHT_STUDY = "study-nfet-default-1e-11"
#: The two ``cv.json`` runs with the project's lifetimes a hundred times apart in tolerance (looser,
#: reference), compared for B7.
CHARON_LOOSE_PAIR = ("cv-nfet-default-1e-8", "cv-nfet-default-1e-10")


def _sci_full(v: float) -> str:
    """``v`` with every digit of its shortest repr, as ``8.265841554853887e9``."""
    mantissa, exponent = np.format_float_scientific(v, unique=True).split("e")
    return f"{mantissa}e{int(exponent)}"


def _charon_rel(runs: dict, name: str, ref: str) -> float:
    """The largest ``abs(C / C_ref - 1)`` of run ``name`` against run ``ref`` on their common
    biases."""
    r, b = runs[name], runs[ref]
    vg = [v for v in r["vg"] if v in b["vg"]]
    return max(
        abs(r["c_ff_um2"][r["vg"].index(v)] / b["c_ff_um2"][b["vg"].index(v)] - 1) for v in vg
    )


def _charon_substitutions(roots: Roots) -> dict[str, str]:
    """The Charon page's numbers (``lim_charon_*``), each from a committed record."""
    root = charon_root(roots)
    cv = charon_record("cv", root)["runs"]
    hard = charon_record("hard-range", root)
    probes = charon_record("probes", root)
    hb = charon_record("harmonic-balance", root)
    n_ref, p_ref = CHARON_REF["nfet_05v0"], CHARON_REF["pfet_05v0"]
    ref_runs = (cv[n_ref], cv[p_ref])
    np_ref = max(r[f"max_abs_np_over_ni2_minus_1_{s}"] for r in ref_runs for s in "AB")
    b6 = max(r[f"{k}_vs_gate_{s}"] for r in ref_runs for k in ("poly", "body") for s in "AB")
    variants = hard["variants"]
    plain = [v for n, v in variants.items() if v["equilibrium_converged"]
             and not v["sweep_converged"] and "tau" not in v["settings"]]  # fmt: skip
    ref = variants[CHARON_REF_VARIANT]
    # the shorter lifetimes that still stop, at the reference tolerance
    tau_fail = {v["last_converged_v"] for v in variants.values() if "tau" in v["settings"]
                and v["settings"]["rel"] == ref["settings"]["rel"]
                and not v["sweep_converged"]}  # fmt: skip
    (tau_stop,) = tau_fail
    step = ref["step_v"]
    inv = sorted(float(v) for v in hard["inversion_side"]["direct"])
    biases = [f"{v:g}" for v in inv]
    tri3 = probes["tri3"]
    pp = max(abs(abs(x) - 1) for run in hb["parallel_plate"]["runs"].values()
             for c, x in run["ratio"].items() if "CosH1" in c)  # fmt: skip
    mg = hb["metal_gate"]["depletion"]["ratio"]
    mg_err = max(abs(abs(x) - 1) for c, x in mg.items() if "CosH1" in c and "Disp" in c
                 and "gate" in c)  # fmt: skip
    runs = list(probes["harmonic_balance"].values())
    amps = [r["amplitude_v"] for r in runs]
    amp = max(set(amps), key=amps.count)  # the amplitude of the frequency scan
    b4 = max((r for r in runs if r["amplitude_v"] == amp), key=lambda r: r["f_hz"])
    hb_cols = {s: b4[s]["c_from_columns_over_c_qs"] for s in ("accumulation", "depletion")}
    hb_gate = {s: abs(next(x for c, x in v.items() if c.startswith("gate") and "CosH1" in c
                           and "Disp" in c)) for s, v in hb_cols.items()}  # fmt: skip
    tight = hard["step_studies"][CHARON_TIGHT_STUDY]
    rel_tight = next(w.split("=", 1)[1] for w in tight["command"].split()
                     if w.startswith("CX_REL="))  # fmt: skip
    doping = probes["doping"]
    (ni,) = {v["ni_cm3"] for v in doping.values()}
    sig = STYLE["page_digits"]
    tol = charon_tolerance(roots)
    b7 = {f"lim_charon_b7_{_SHORT[d]}_{params}": _sci(float(np.nanmax(v["rel"])))
          for d, by in tol["pairs"].items() for params, v in by.items()}  # fmt: skip
    studies = hard["step_studies"]
    stall = studies[CHARON_STALL_STUDIES[0]]["failed"]
    ((iters, _limit),) = stall["newton_limit"]
    fnorm, wrms = stall["final"][-1]
    ramp = {n: studies[n]["failed"] for n in CHARON_STALL_STUDIES if studies[n]["failed"]
            and studies[n]["failed"]["deck"].startswith("ramp")}  # fmt: skip
    (ramp_stop,) = ramp.values()

    def signed(v: float) -> str:
        return f"{v:g}".replace("-", "\u2212")

    above, up = (cv[n] for n in CHARON_B7_PAIRS["pfet_05v0"]["start"][1])
    pfet_start = cv[CHARON_B7_PAIRS["pfet_05v0"]["start"][0]]
    checks = charon_checks(roots)
    nlp_ok = sorted(v for v, c in checks["nlp"].items() if c is not None)
    nlp_bad = sorted(v for v, c in checks["nlp"].items() if c is None)

    def listed(vs) -> str:
        words = [signed(v) for v in vs]
        return ", ".join(words[:-1]) + " and " + words[-1] if len(words) > 1 else words[0]

    (belos_stop,) = {d["stop_v"] for d in checks["solvers"].values() if d["stop_v"] is not None}

    return {
        **b7,
        "lim_charon_b7_max": _sci(
            max(float(np.nanmax(v["rel"])) for by in tol["pairs"].values() for v in by.values())
        ),
        "lim_charon_stall_v": f"{float(stall['failed_at'][0]):g}",
        "lim_charon_stall_last": f"{stall['last_converged_v']:g}",
        "lim_charon_stall_fnorm": _sci(fnorm),
        "lim_charon_stall_wrms": f"{wrms:g}",
        "lim_charon_stall_iters": f"{iters}",
        # a ramp goes on converging past its first failed step (LOCA retries with smaller
        # steps): the page gives where it last converged
        "lim_charon_stall_ramp_v": f"{ramp_stop['last_converged_v']:g}",
        "lim_charon_tight_ramp_v": signed(tight["failed"]["last_converged_v"]),
        # the nfet ramp's target, the first grid point as a device bias, and the shift
        "lim_charon_tight_ramp_to": signed(
            round(cv[CHARON_LOOSE_PAIR[1]]["vg"][0] - cv[CHARON_LOOSE_PAIR[1]]["dv_fb_v"], 1)
        ),
        "lim_charon_nfet_dv_fb": f"{cv[CHARON_LOOSE_PAIR[1]]['dv_fb_v']:.3g}",
        "lim_charon_pfet_start_from": f"{min(above['vg']):g}",
        "lim_charon_pfet_start_up_to": signed(max(up["vg"])),
        "lim_charon_pfet_start_points": f"{tol['pairs']['pfet_05v0']['start']['biases']}",
        "lim_charon_nlp_c": f"{max(abs(checks['nlp'][v][0]) for v in nlp_ok):g}",
        "lim_charon_nlp_ok": listed(nlp_ok),
        "lim_charon_nlp_bad": listed(nlp_bad),
        "lim_charon_belos_stop": f"{belos_stop:g}",
        "lim_charon_pfet_start_devsim": _sci(pfet_start["max_abs_rel_vs_devsim"]),
        "lim_charon_nodes": f"{cv[n_ref]['boundary_nodes'][-1] + 1}",
        "lim_charon_points": f"{cv[n_ref]['n']}",
        "lim_charon_ni": _sci_full(ni),
        "lim_charon_doping_rel": f"{max(v['max_rel_doping'] for v in doping.values()):g}",
        "lim_charon_ref_tau": cv[n_ref]["settings"]["CX_TAU"],
        "lim_charon_nfet_devsim": _sci(cv[n_ref]["max_abs_rel_vs_devsim"]),
        "lim_charon_pfet_devsim": _sci(cv[p_ref]["max_abs_rel_vs_devsim"]),
        "lim_charon_lifetime": _sci(_charon_rel(cv, "cv-nfet-tau14-1e-10", n_ref)),
        "lim_charon_pfet_lifetime": _sci(_charon_rel(cv, "cv-pfet-tau14-1e-10", p_ref)),
        "lim_charon_default_lifetime": _sci(_charon_rel(cv, "cv-nfet-default-1e-10", n_ref)),
        "lim_charon_tol9": _sci(_charon_rel(cv, "cv-nfet-tau15-1e-9", n_ref)),
        "lim_charon_tol8": _sci(_charon_rel(cv, *CHARON_LOOSE_PAIR)),
        "lim_charon_np_ref": _sci(np_ref),
        "lim_charon_b6": _sci(b6),
        "lim_charon_fail_v": f"{ref['last_converged_v'] + step:.{sig}f}",
        "lim_charon_stop_lo": f"{min(v['last_converged_v'] for v in plain):.{sig}f}",
        "lim_charon_stop_hi": f"{max(v['last_converged_v'] for v in plain):.{sig}f}",
        "lim_charon_tau_stop": f"{tau_stop:.{sig}f}",
        "lim_charon_ref_fnorm": _sci(ref["failed_fnorm"]),
        "lim_charon_ref_wrms": f"{ref['failed_wrms']:.0f}",
        "lim_charon_inv_biases": ", ".join(biases[:-1]) + " and " + biases[-1],
        "lim_charon_tri3_2d": _sci(abs(tri3["rel_vs_devsim_1d"])),
        "lim_charon_tri3_strip": _sci(tri3["strip_max_rel_c_tri3_vs_quad4"]),
        "lim_charon_pp": _sci(pp),
        "lim_charon_mg": _sci(mg_err),
        "lim_charon_hb_acc": f"{hb_gate['accumulation']:.{sig}f}",
        "lim_charon_hb_depl": f"{hb_gate['depletion']:.{sig}f}",
        "lim_charon_tight": rel_tight,
        **_charon_newton_substitutions(roots),
    }


def newton_cycle(sv: dict) -> dict:
    """Whether a failed solve's last STYLE["newton_cycle_window"] iterations alternate: the
    1-norm condition number of J on even and on odd iterations each repeats within
    STYLE["newton_cycle_parity"] (``parity``, the larger relative spread), and the two values
    differ by at least STYLE["newton_cycle_ratio"] (``ratio``); ``dx``: the relative spread of
    the update's 2-norm over the window (max / min - 1)."""
    its = sv["iterations"][-STYLE["newton_cycle_window"] :]
    c = np.asarray([it["cond1"] for it in its])
    d = np.asarray([it["dx_2"] for it in its])
    even, odd = c[0::2], c[1::2]
    parity = max(even.max() / even.min(), odd.max() / odd.min()) - 1
    ratio = max(even.mean(), odd.mean()) / min(even.mean(), odd.mean())
    return {"parity": float(parity), "ratio": float(ratio), "dx": float(d.max() / d.min() - 1),
            "alternates": bool(parity < STYLE["newton_cycle_parity"]
                               and ratio >= STYLE["newton_cycle_ratio"])}  # fmt: skip


def _charon_newton_substitutions(roots: Roots) -> dict[str, str]:
    """The numbers of issues #223 and #224 on the Charon page (``lim_charon_trap_*``,
    ``lim_charon_newton_*``), from ``probes.json`` (``deck_traps``) and ``hard-range.json``
    (``newton``). "Loose" and "tight" are the larger and smaller of the two tolerances."""
    root = charon_root(roots)
    traps = charon_record("probes", root)["deck_traps"]
    rec = charon_record("hard-range", root)["newton"]
    stalled = [n for n in rec.values() if n["stalled"]]
    loose_rel = max(n["search_rel"] for n in rec.values())
    tols = sorted({t for n in stalled for t in n["solves"]}, key=float)
    tight, loose = tols[0], tols[-1]

    def at(n, key, tol=loose):
        return n["solves"][tol]["iterations"][-1][key]

    def smallest(n, tol=loose):
        return min(it["wrms"] for it in n["solves"][tol]["iterations"])

    def signed(v: float) -> str:
        return f"{v:g}".replace("-", "\u2212")

    def own(n):  # the repeat at the tolerance the sweep failed at
        return n["solves"][f"{n['search_rel']:g}"]

    def other(n):
        (t,) = [t for t in n["solves"] if t != f"{n['search_rel']:g}"]
        return n["solves"][t]

    def ratio(sv):
        return sv["iterations"][-1]["f_2"] / sv["last"]["f_roundoff_2"]

    def kappa(sv):
        return sv["iterations"][-1]["cond1_row_scaled"]

    failed = [own(n) for n in stalled]
    conv = [sv for n in stalled for sv in (own(n), other(n)) if sv["converged"]]
    cycles = [c for c in (newton_cycle(sv) for sv in failed) if c["alternates"]]
    (pfet_v,) = {n["failed_at_v"] for n in stalled
                 if n["device"] == "pfet_05v0" and n["search_rel"] == loose_rel}  # fmt: skip
    pfet = [n for n in stalled if n["device"] == "pfet_05v0" and n["search_rel"] == loose_rel]
    (nfet,) = [n for n in stalled if n["device"] == "nfet_05v0" and n["tau"] is None
               and n["search_rel"] == loose_rel]  # fmt: skip
    tight_sweeps = [n for n in stalled if n["search_rel"] < loose_rel]
    ramps = [signed(n["failed_at_v"]) for n in tight_sweeps if n["deck"] != "eq"]
    scales = stalled[0]["solves"][loose]["scales"]
    return {
        "lim_charon_trap_side_exit": f"{traps['side_set_named_body']['charon_exit']}",
        "lim_charon_trap_body_doping": f"{traps['doping_block_misnamed']['doping']['body_max_abs_cm3']:g}",
        "lim_charon_newton_floor_x": _sci(
            max(n["solves"][loose]["last"]["floor_x"] for n in stalled)
        ),
        "lim_charon_newton_floor_x_tight": _sci(
            max(n["solves"][tight]["last"]["floor_x"] for n in stalled)
        ),
        "lim_charon_newton_res_lo": f"{min(ratio(sv) for sv in failed):.2g}",
        "lim_charon_newton_res_hi": f"{max(ratio(sv) for sv in failed):.2g}",
        "lim_charon_newton_cond_lo": _sci(min(kappa(sv) for sv in failed)),
        "lim_charon_newton_cond_hi": _sci(max(kappa(sv) for sv in failed)),
        "lim_charon_newton_conv_res_lo": f"{min(ratio(sv) for sv in conv):.2g}",
        "lim_charon_newton_conv_res_hi": f"{max(ratio(sv) for sv in conv):.2g}",
        "lim_charon_newton_conv_cond_lo": _sci(min(kappa(sv) for sv in conv)),
        "lim_charon_newton_conv_cond_hi": _sci(max(kappa(sv) for sv in conv)),
        "lim_charon_newton_failed": f"{len(failed)}",
        "lim_charon_newton_cycles": f"{len(cycles)}",
        "lim_charon_newton_cycle_window": f"{STYLE['newton_cycle_window']}",
        "lim_charon_newton_cycle_parity": f"{max(c['parity'] for c in cycles) * UNITS['percent']:.1g}",
        "lim_charon_newton_cycle_lo": f"{min(c['ratio'] for c in cycles):.2g}",
        "lim_charon_newton_cycle_hi": f"{max(c['ratio'] for c in cycles):.2g}",
        "lim_charon_newton_cycle_dx": f"{max(c['dx'] for c in cycles) * UNITS['percent']:.2g}",
        "lim_charon_newton_conv_hi": f"{max(smallest(n) for n in tight_sweeps):.2g}",
        "lim_charon_newton_pfet_v": f"{pfet_v:g}",
        "lim_charon_newton_pfet_floor": f"{max(smallest(n) for n in pfet):.3g}",
        "lim_charon_newton_nfet_v": f"{nfet['failed_at_v']:g}",
        "lim_charon_newton_nfet_floor": _sci(smallest(nfet)),
        "lim_charon_newton_nfet_cond": _sci(kappa(own(nfet))),
        "lim_charon_newton_tight_v": ", ".join(ramps[:-1]) + " and " + ramps[-1],
        "lim_charon_newton_v0": f"{scales['V0']:g}",
        "lim_charon_newton_c0": _sci(scales["C0"]),
    }


#: The B7 pairs (``cv.json``): per device and parameter set, the run at the backend's default
#: WRMS tolerance (1e-9 relative) and the runs at the reference tolerance (1e-10). The pfet start
#: reference stalls on the way down from 5 V, so it has two runs: from 5 V down to above the stall,
#: and from -5 V up as far as it converges.
CHARON_B7_PAIRS = {
    "nfet_05v0": {
        "calibrated": ("cv-nfet-tau15-1e-9", ("cv-nfet-tau15-1e-10",)),
        "start": ("cv-nfet-start-tau15-1e-9", ("cv-nfet-start-tau15-1e-10",)),
    },
    "pfet_05v0": {
        "calibrated": ("cv-pfet-tau15-1e-9", ("cv-pfet-tau15-1e-10",)),
        "start": (
            "cv-pfet-start-tau15-1e-9",
            ("cv-pfet-start-tau15-1e-10-above-0.6", "cv-pfet-start-tau15-1e-10-from-minus-5"),
        ),
    },
}

#: The pfet start sweeps of ``hard-range.json`` (``step_studies``): the reference tolerance, then
#: one setting changed each. The first is the stall the page describes.
CHARON_STALL_STUDIES = (
    "study-pfet-start-1e-10",
    "study-pfet-start-1e-10-rescue-off",
    "study-pfet-start-1e-10-5mV",
    "study-pfet-start-1e-10-tau16",
    "study-pfet-start-1e-11",
    "study-pfet-start-rel-1e-9-abs-1e-12",
    "study-pfet-start-rel-1e-10-abs-1e-11",
)


#: How a study label names each setting that differs from the reference study.
STUDY_SETTINGS = {"CX_REL": "rel {}", "CX_ABS": "abs {}", "CX_TAU": "lifetime {} s",
                  "CX_SUB": "{} LOCA steps per grid step", "CX_NORESCUE": "rescue off"}  # fmt: skip


def _study_env(command: str) -> dict[str, str]:
    return dict(w.split("=", 1) for w in command.split() if w.startswith("CX_") and "=" in w)


def _study_label(env: dict[str, str], reference: dict[str, str]) -> str:
    """A study's label: the settings of :data:`STUDY_SETTINGS` that differ from ``reference``
    (the reference study, labelled with its tolerances)."""
    if env == reference:
        return "reference: " + ", ".join(
            STUDY_SETTINGS[k].format(env[k]) for k in ("CX_REL", "CX_ABS")
        )
    return ", ".join(STUDY_SETTINGS[k].format(env.get(k, "")) for k in STUDY_SETTINGS
                     if env.get(k, "") != reference.get(k, ""))  # fmt: skip


def charon_tolerance(roots: Roots = DEFAULT_ROOTS) -> dict:
    """``pairs``: per device and parameter set of :data:`CHARON_B7_PAIRS`, the biases both runs
    have (``u``, polarity times vg) and ``abs(C_default / C_reference - 1)`` there. ``stall``: per
    study of :data:`CHARON_STALL_STUDIES` and the default-tolerance pfet start run, its label,
    whether it stopped, and the gate bias of the device where it stopped (V), or the end of its
    grid."""
    root = charon_root(roots)
    runs = charon_record("cv", root)["runs"]
    studies = charon_record("hard-range", root)["step_studies"]
    pairs = {}
    for device, by_params in CHARON_B7_PAIRS.items():
        pol = DEVICES[device].polarity
        for params, (name, refs) in by_params.items():
            r = runs[name]
            us, rels = [], []
            for ref in refs:  # one segment per reference run, a NaN break between them
                b = runs[ref]
                vg = [v for v in r["vg"] if v in b["vg"]]
                us += [pol * v for v in vg] + [np.nan]
                rels += [abs(r["c_ff_um2"][r["vg"].index(v)] / b["c_ff_um2"][b["vg"].index(v)]
                             - 1) for v in vg] + [np.nan]  # fmt: skip
            pairs.setdefault(device, {})[params] = {
                "u": np.asarray(us[:-1]),
                "rel": np.asarray(rels[:-1]),
                "biases": int(np.sum(np.isfinite(rels))),
            }
    default = runs[CHARON_B7_PAIRS["pfet_05v0"]["start"][0]]
    reference = _study_env(studies[CHARON_STALL_STUDIES[0]]["command"])
    stall = {}
    for name in CHARON_STALL_STUDIES:
        s = studies[name]
        failed = s["failed"]
        stall[name] = {
            "label": _study_label(_study_env(s["command"]), reference),
            "stopped": failed is not None,
            # a failure on the ramp from 0 V to the sweep's first bias: the sweep never started
            "on_ramp": failed is not None and failed["deck"].startswith("ramp"),
            # where the failed solve last converged, or the end of the grid
            "bias_v": failed["last_converged_v"] if failed else default["vg"][-1],
        }
    stall["default"] = {
        "label": "backend default: " + _study_label(default["settings"], reference),
        "stopped": False,
        "on_ramp": False,
        "bias_v": default["vg"][-1],
    }
    return {"pairs": pairs, "stall": stall}


def _zero_floor(values) -> float:
    """The log axis floor of relative changes ``values``: below the smallest nonzero one by
    :data:`STYLE` ``zero_floor_factor``; exact zeros are drawn there."""
    v = np.asarray(values, float)
    return float(np.nanmin(v[v > 0]) / STYLE["zero_floor_factor"])


def _zero_handle(colour: str):
    """The legend entry of the exact-zero markers of :func:`_log_with_zeros` (not drawn)."""
    return matplotlib.lines.Line2D([], [], ls="none", marker="v", ms=STYLE["marker_pt"],
                                   color=colour, label="exactly zero (identical)")  # fmt: skip


def _log_with_zeros(ax, x, rel, floor: float, colour: str, gid: str, dots: bool = True,
                    **line) -> None:  # fmt: skip
    """``rel`` against ``x`` on a log axis: the line breaks at exact zeros, which are drawn as
    markers at ``floor`` (gid ``gid + " zeros"``). Every nonzero point carries a small marker,
    so a point between two zeros stays visible; ``dots=False`` leaves them off a line that has
    no such point (its dashes stay readable)."""
    x, rel = np.asarray(x, float), np.asarray(rel, float)
    marks = {"marker": "o", "ms": STYLE["point_ms"]} if dots else {}
    ax.plot(x, np.where(rel == 0, np.nan, rel), color=colour, gid=gid, **marks, **line)
    zero = rel == 0
    if zero.any():
        ax.scatter(x[zero], np.full(int(zero.sum()), floor), marker="v",
                   s=STYLE["marker_pt"] ** 2, color=colour, gid=f"{gid} zeros")  # fmt: skip


def charon_tolerance_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """Top: ``abs(C / C_ref - 1)`` between the backend's default tolerance and the reference, for
    both devices and parameter sets. Bottom: the pfet start sweeps under each setting, at the gate
    bias where each stopped (hollow) or at the end of the grid (filled)."""
    pal = ef.PALETTES[palette]
    k = charon_tolerance(roots)
    colours = {("nfet_05v0", "calibrated"): "electron", ("nfet_05v0", "start"): "highlight",
               ("pfet_05v0", "calibrated"): "hole", ("pfet_05v0", "start"): "highlight_oxide"}  # fmt: skip
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        # subfigures: the bottom panel's long study labels do not narrow the top panel
        top_fig, bottom_fig = fig.subfigures(len(CHARON_PANELS), 1,
                                             height_ratios=STYLE["tolerance_rows"])  # fmt: skip
        top, bottom = top_fig.subplots(), bottom_fig.subplots()
        floor = _zero_floor([v for by in k["pairs"].values() for d in by.values()
                             for v in d["rel"]])  # fmt: skip
        for device, by_params in k["pairs"].items():
            for params, d in by_params.items():
                _log_with_zeros(top, d["u"], d["rel"], floor, pal[colours[device, params]],
                                f"tolerance pair {device} {params}", lw=ef.STYLE["line_width"],
                                label=f"{device} {params}")  # fmt: skip
        top.set_yscale("log")
        top.set_ylim(bottom=floor / STYLE["zero_floor_factor"])
        top.set_xlabel("u = polarity × vg (V)")
        top.set_ylabel("relative change of C")
        names = list(k["stall"])
        y = np.arange(len(names))
        groups = (
            ("reached the grid end", lambda d: not d["stopped"], "o", pal["highlight"]),
            ("failed in the sweep", lambda d: d["stopped"] and not d["on_ramp"], "o", "none"),
            ("ramp from equilibrium failed,\nsweep never started", lambda d: d["on_ramp"], "x",
             pal["highlight"]),
        )  # fmt: skip
        for gid, pick, marker, face in groups:
            idx = [i for i, n in enumerate(names) if pick(k["stall"][n])]
            bottom.scatter([k["stall"][names[i]]["bias_v"] for i in idx], y[idx],
                           marker=marker, s=STYLE["marker_pt"] ** 2, facecolors=face,
                           edgecolors=pal["highlight"] if marker == "o" else None,
                           label=gid, gid=gid)  # fmt: skip
        bottom.set_yticks(y, [k["stall"][n]["label"] for n in names])
        bottom.invert_yaxis()
        bottom.set_xlabel("pfet start: last converged\ngate bias of the device (V)")
        bottom.grid(True, axis="x")
        handles = [*top.get_legend_handles_labels()[0], _zero_handle(pal["text"]),
                   *bottom.get_legend_handles_labels()[0]]  # fmt: skip
        fig.legend(handles=handles, loc="outside lower center", ncols=STYLE["legend_cols"],
                   frameon=False)  # fmt: skip
        return fig


#: The panels of :func:`charon_tolerance_figure`, top to bottom.
CHARON_PANELS = ("tolerance pairs", "pfet start sweeps")


def charon_doping(roots: Roots = DEFAULT_ROOTS) -> dict:
    """B5: per device and parameter set, the semiconductor nodes' depth from the gate end (um),
    the description's net doping there and Charon's nodal ``Doping`` (cm^-3, signed), a NaN
    break at the oxide; and the record's largest relative difference of the two."""
    out = {}
    for tag, rec in charon_record("probes", charon_root(roots))["doping"].items():
        semi = np.asarray(rec["semiconductor_nodes"])
        gap = np.nonzero(np.diff(semi) > 1)[0] + 1  # the oxide between poly and body
        out[tag] = {
            k: np.insert(np.asarray(rec[key], float)[semi], gap, np.nan)
            for k, key in (("x_um", "x_um"), ("description", "description_cm3"),
                           ("charon", "doping_cm3"))
        }  # fmt: skip
        out[tag]["max_rel_doping"] = rec["max_rel_doping"]
    return out


def charon_doping_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """B5: the magnitude of the net doping against depth from the gate end, the description as a
    line and Charon's nodal values as markers, one panel per device, both parameter sets."""
    pal = ef.PALETTES[palette]
    k = charon_doping(roots)
    colours = {"start": "highlight", "calibrated": "electron"}
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        axes = dict(zip(DEVICES, fig.subplots(len(DEVICES), 1), strict=True))
        for tag, d in k.items():
            device, params = tag.rsplit("_", 1)
            ax = axes[device]
            colour = pal[colours[params]]
            ax.plot(d["x_um"], np.abs(d["description"]), color=colour, lw=ef.STYLE["line_width"],
                    label=f"description, {params}", gid=f"{tag} description")  # fmt: skip
            ax.plot(d["x_um"], np.abs(d["charon"]), ls="none", marker="o",
                    ms=STYLE["small_marker_pt"], mfc="none", mec=colour,
                    label=f"Charon nodes, {params}", gid=f"{tag} charon")  # fmt: skip
            ax.set_yscale("log")
            ax.set_ylabel(f"{device}: |net doping| (cm⁻³)")
        axes[list(DEVICES)[-1]].set_xlabel("depth from the gate end (µm)")
        handles, labels = axes[next(iter(DEVICES))].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside lower center", ncols=STYLE["legend_cols"],
                   frameon=False)  # fmt: skip
        return fig


def charon_checks(roots: Roots = DEFAULT_ROOTS) -> dict:
    """The other experiments' outcomes. ``solvers``: B3, per linear solver its sweep's bias range
    (V) and the bias it stopped at (None if it reached the end). ``nlp``: B2, per bias whether
    the nonlinear-Poisson solve converged and its C (fF/um^2), or None. ``b6``: per reference run,
    u and the per-state oxide-flux spread and poly and body charge mismatches (both sides).
    ``b7``: the default-lifetime runs a hundred times apart in tolerance (u and the relative C
    change), and per ten-times-tighter study the bias it stopped at."""
    root = charon_root(roots)
    probes = charon_record("probes", root)
    hard = charon_record("hard-range", root)
    runs = charon_record("cv", root)["runs"]
    solvers = {}
    for name, rec in probes["solvers"].items():
        if isinstance(rec, dict) and "sweep_v" in rec:
            # where a failed sweep last converged (None: it reached the end)
            solvers[name] = {"sweep_v": rec["sweep_v"], "stop_v": rec.get("last_converged_v")}
    nlp = {p["vg"]: ((p["c_nlp"], p["c_devsim"]) if p["ok"] else None)
           for p in hard["nlp"]["points"]}  # fmt: skip
    b6 = {}
    for device, name in CHARON_REF.items():
        r = runs[name]
        b6[device] = {"u": DEVICES[device].polarity * np.asarray(r["vg"]),
                      **{f"{k}_{s}": np.asarray(r[f"{k}_per_state_{s}"])
                         for k in ("oxide_flux_spread", "poly_vs_gate", "body_vs_gate")
                         for s in "AB"}}  # fmt: skip
    loose, ref = (runs[n] for n in CHARON_LOOSE_PAIR)
    vg = [v for v in loose["vg"] if v in ref["vg"]]
    rel = [abs(loose["c_ff_um2"][loose["vg"].index(v)] / ref["c_ff_um2"][ref["vg"].index(v)] - 1)
           for v in vg]  # fmt: skip
    tight = {n: hard["step_studies"][n]["failed"]["last_converged_v"] for n in CHARON_TIGHT}
    # on the axis of the tight study's last converged bias: the gate bias of the device, vg - dv_fb
    device_v = np.asarray(vg) - loose["dv_fb_v"]
    return {"solvers": solvers, "nlp": nlp, "b6": b6,
            "b7": {"device_v": device_v, "rel": np.asarray(rel), "tight": tight}}  # fmt: skip


#: The ten times tighter tolerance study of the nfet calibrated values with the project's
#: lifetimes (``hard-range.json``, ``step_studies``): the case of the B7 panel's curve. The pfet
#: start study at 1e-11 is in :func:`charon_tolerance_figure`.
CHARON_TIGHT = ("study-nfet-default-1e-11",)

#: The panels of :func:`charon_checks_figure`, top to bottom.
CHARON_CHECK_PANELS = ("B3 linear solvers", "B2 nonlinear Poisson", "B6 charge checks",
                       "B7 tolerance")  # fmt: skip


def charon_checks_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """B3: each linear solver's sweep, as the range it covered. B2: the nonlinear-Poisson C at
    the biases where it converged, DEVSIM's C there, and a dotted line at each bias where Newton
    diverged. B6: the per-state charge checks of both reference runs, exact zeros at the axis
    floor. B7: the nfet C change a hundred times looser, exact zeros at the floor, and a dashed
    line where the ten times tighter study of the same case failed on its ramp."""
    pal = ef.PALETTES[palette]
    k = charon_checks(roots)
    lw = ef.STYLE["line_width"]
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["checks_in"])
        b3, b2, b6, b7 = fig.subplots(len(CHARON_CHECK_PANELS), 1)
        p_b3, p_b2, p_b6, p_b7 = CHARON_CHECK_PANELS
        names = list(k["solvers"])
        for i, n in enumerate(names):
            lo, hi = k["solvers"][n]["sweep_v"]
            stop = k["solvers"][n]["stop_v"]
            b3.plot([lo, hi if stop is None else stop], [i, i], color=pal["highlight"], lw=lw,
                    gid=f"solver {n}")  # fmt: skip
        b3.set_yticks(range(len(names)), names)
        b3.set_xlabel(f"{p_b3}: from the first bias to the last converged one (V)")
        ok = {v: c for v, c in k["nlp"].items() if c is not None}
        bad = [v for v, c in k["nlp"].items() if c is None]
        b2.scatter(list(ok), [c for c, _ in ok.values()], s=STYLE["marker_pt"] ** 2,
                   color=pal["highlight"], label="nonlinear Poisson C",
                   gid="nlp converged")  # fmt: skip
        b2.scatter(list(ok), [d for _, d in ok.values()], s=STYLE["marker_pt"] ** 2,
                   marker="s", facecolors="none", edgecolors=pal["electron"],
                   label="DEVSIM C at the same bias", gid="nlp devsim")  # fmt: skip
        for i, v in enumerate(bad):  # no value: the solve diverged there
            b2.axvline(v, color=pal["text"], lw=lw, ls=":",
                       label="Newton diverged, no C" if i == 0 else None,
                       gid=f"nlp diverged {i}")  # fmt: skip
        b2.set_xlabel(f"{p_b2}: gate bias vg (V)")
        b2.set_ylabel("C (fF/µm²)")
        b6_keys = {"oxide_flux_spread": ("highlight", "oxide-flux spread"),
                   "poly_vs_gate": ("electron", "poly charge mismatch"),
                   "body_vs_gate": ("hole", "body charge mismatch")}  # fmt: skip
        first = next(iter(k["b6"]))
        b6_floor = _zero_floor([v for d in k["b6"].values() for key in b6_keys
                                for s in "AB" for v in d[f"{key}_{s}"]])  # fmt: skip
        for device, d in k["b6"].items():
            for key, (colour, label) in b6_keys.items():
                for s in "AB":
                    _log_with_zeros(b6, d["u"], d[f"{key}_{s}"], b6_floor, pal[colour],
                                    f"charge check {device} {key} {s}", dots=False, lw=lw,
                                    ls=STYLE["device_ls"][device],
                                    label=label if (device, s) == (first, "A") else None)  # fmt: skip
        b6.set_yscale("log")
        b6.set_xlabel(f"{p_b6}: u = polarity × vg (V)")
        b6.set_ylabel("relative mismatch")
        b6.set_ylim(bottom=b6_floor / STYLE["zero_floor_factor"])
        floor = _zero_floor(k["b7"]["rel"])
        _log_with_zeros(b7, k["b7"]["device_v"], k["b7"]["rel"], floor, pal["highlight"],
                        "tolerance looser", lw=lw,
                        label="a hundred times looser\n(nfet, project lifetimes)")  # fmt: skip
        for n, v in k["b7"]["tight"].items():
            b7.axvline(v, color=pal["hole"], lw=lw, ls="--",
                       label="ten times tighter:\nlast converged on its ramp",
                       gid=f"tighter {n}")  # fmt: skip
        b7.set_yscale("log")
        b7.set_xlabel(f"{p_b7}: gate bias of the device, vg − dv_fb (V)")
        b7.set_ylabel("relative change of C")
        b7.set_ylim(bottom=floor / STYLE["zero_floor_factor"])
        # each panel's own legend, beside it: one figure legend would not fit
        devices = [matplotlib.lines.Line2D([], [], color=pal["text"], lw=lw,
                                           ls=STYLE["device_ls"][dev], label=dev)
                   for dev in k["b6"]]  # fmt: skip
        extra = {b6: [*devices, _zero_handle(pal["text"])], b7: [_zero_handle(pal["highlight"])]}
        for ax in (b2, b6, b7):
            handles = ax.get_legend_handles_labels()[0] + extra.get(ax, [])
            ax.legend(handles=handles, loc="upper left", bbox_to_anchor=STYLE["legend_beside"],
                      fontsize="small", frameon=False)  # fmt: skip
        return fig


def _edges(pairs) -> tuple[np.ndarray, np.ndarray]:
    """One polyline of segments ``(a, b)`` (points ``(x, y)``), a NaN break after each."""
    pts = np.array([[a, b, (np.nan, np.nan)] for a, b in pairs], float).reshape(-1, 2)
    return pts[:, 0], pts[:, 1]


def charon_structures(roots: Roots = DEFAULT_ROOTS) -> dict:
    """The structures of B4 and B1. ``plate_nm``: the parallel plate's node depths (nm);
    ``metal_nm`` and ``metal_oxide_nodes``: the metal-gate stack's node depths and how many of
    them are oxide nodes (the last oxide node is the first body node); ``width_um``: the strips'
    width; ``mesh``: per block of the 2D mesh its triangle edges (um) as one polyline;
    ``sides``: per contact side set its segments (um) as one polyline."""
    root = charon_root(roots)
    hb = charon_record("harmonic-balance", root)
    tri3 = charon_record("probes", root)["tri3"]
    xy = np.asarray(tri3["mesh2d_xy_um"], float)
    blocks = {k: np.asarray(v, int) for k, v in tri3["mesh2d_triangles"].items()}
    mesh = {}
    for name, tris in blocks.items():
        edges = sorted({tuple(sorted((int(a), int(b)))) for t in tris
                        for a, b in zip(t, np.roll(t, -1), strict=True)})  # fmt: skip
        mesh[name] = _edges((xy[a], xy[b]) for a, b in edges)
    tris = np.concatenate(list(blocks.values()))  # Exodus element ids run through the blocks
    sides = {}
    for name, ss in tri3["mesh2d_side_sets"].items():
        segs = []
        for eid, side in zip(ss["elements"], ss["sides"], strict=True):
            t = tris[eid - 1]
            ring = np.roll(t, -(side - 1))  # TRI3 side k joins nodes k and k + 1 (1-based)
            segs.append((xy[ring[0]], xy[ring[1]]))
        sides[name] = _edges(segs)
    mg = hb["metal_gate"]
    return {
        "plate_nm": np.asarray(hb["parallel_plate"]["x_um"]) * UNITS["nm_per_um"],
        "metal_nm": np.asarray(mg["x_um"]) * UNITS["nm_per_um"],
        "metal_oxide_nodes": mg["oxide_nodes"],
        "width_um": charon_strip_mesh(roots)["width_um"],
        "mesh": mesh,
        "sides": sides,
    }


#: The panels of :func:`charon_structures_figure`, top to bottom.
STRUCTURE_PANELS = ("parallel plate", "metal-gate stack", "2D mesh")


def charon_structures_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """Top: the B4 parallel plate, the oxide strip's node pairs between its two contacts.
    Middle: the B4 metal-gate stack, oxide and body node pairs, the gate contact on the oxide
    and the body contact at the far end (depth on a symmetric log scale). Bottom: the B1 2D mesh,
    its triangle edges by block, with the two contacts' sides."""
    pal = ef.PALETTES[palette]
    lw = ef.STYLE["edge_width"]
    k = charon_structures(roots)
    colours = {"gate_poly": "electron", "oxide": "highlight_oxide", "body": "hole"}
    contact = {"gate": "highlight", "body_contact": "text", "top": "highlight", "bottom": "text"}
    segment = [0.0, k["width_um"], np.nan]  # one node pair: bottom, top, a break

    def pairs(ax, x, colour, gid, label=None):
        ax.plot(np.repeat(x, len(segment)), np.tile(segment, len(x)), color=pal[colour], lw=lw,
                gid=gid, label=label)  # fmt: skip

    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        top, mid, bottom = fig.subplots(len(STRUCTURE_PANELS), 1)
        x = k["plate_nm"]
        pairs(top, x, "highlight_oxide", "plate oxide nodes")
        for name, at in (("top", x[0]), ("bottom", x[-1])):
            top.axvline(at, color=pal[contact[name]], lw=ef.STYLE["line_width"],
                        gid=f"plate contact {name}")  # fmt: skip
        top.set_xlabel("depth in the oxide (nm)")
        x = k["metal_nm"]
        n_ox = k["metal_oxide_nodes"]
        pairs(mid, x[:n_ox], "highlight_oxide", "metal oxide nodes")
        pairs(mid, x[n_ox - 1 :], "hole", "metal body nodes")
        for name, at in (("gate", x[0]), ("body_contact", x[-1])):
            mid.axvline(at, color=pal[contact[name]], lw=ef.STYLE["line_width"],
                        gid=f"metal contact {name}")  # fmt: skip
        mid.set_xscale("symlog", linthresh=x[n_ox - 1])
        mid.set_xlabel("depth from the gate (nm)")
        for ax in (top, mid):
            ax.set_ylabel("width (µm)")
        for name, (xs, ys) in k["mesh"].items():
            bottom.plot(xs, ys, color=pal[colours[name]], lw=lw, label=f"block {name}",
                        gid=f"mesh {name}")  # fmt: skip
        for name, (xs, ys) in k["sides"].items():
            bottom.plot(xs, ys, color=pal[contact[name]], lw=ef.STYLE["line_width"],
                        label=f"contact {name}", gid=f"side {name}")  # fmt: skip
        bottom.set_xlabel("x (µm)")
        bottom.set_ylabel("y (µm)")
        fig.legend(loc="outside lower center", ncols=STYLE["legend_cols"], frameon=False)
        return fig


def _newton_label(rec: dict) -> str:
    """A Newton case's row label from its record: device, lifetime, the sweep's tolerance and
    the solve that failed (a device bias, or the equilibrium)."""
    tau = f"τ {rec['tau']} s" if rec["tau"] else "project τ"
    where = ("equilibrium" if rec["deck"] == "eq"
             else f"{rec['failed_at_v']:g} V".replace("-", "\u2212"))  # fmt: skip
    return f"{_SHORT[rec['device']]}, {tau}, {rec['search_rel']:g}, {where}"


def _newton_solve(sv: dict) -> dict:
    its = sv["iterations"]
    return {
        "converged": sv["converged"],
        "iteration": np.asarray([it["iteration"] for it in its]),
        "wrms": np.asarray([it["wrms"] for it in its]),
        "cond1_per_iteration": np.asarray([it["cond1"] for it in its]),
        "smallest": min(it["wrms"] for it in its),
        "floor_x": sv["last"]["floor_x"],
        "res_ratio": its[-1]["f_2"] / sv["last"]["f_roundoff_2"],
        "cond1_row_scaled": its[-1]["cond1_row_scaled"],
    }


def charon_newton(roots: Roots = DEFAULT_ROOTS) -> dict:
    """The Newton diagnostics of issue #223 (``hard-range.json``, ``newton``), per stalled case in
    the record's order. ``failed``: the repeat at the tolerance the case's sweep failed at, which
    fails again; ``other``: the repeat at the other tolerance. Per repeat: the WRMS norm and
    the 1-norm condition number of J per iteration, the smallest WRMS norm, floor_x, and at the
    last iteration the residual over its round-off scale and the condition number of D^-1 J.
    ``passed``: the cases whose sweep reached the end of its grid."""
    rec = charon_record("hard-range", charon_root(roots))["newton"]
    cases, passed = {}, []
    for name, n in rec.items():
        if not n["stalled"]:
            passed.append(name)
            continue
        own = f"{n['search_rel']:g}"
        (other,) = [t for t in n["solves"] if t != own]
        cases[name] = {"label": _newton_label(n), "device": n["device"], "tau": n["tau"],
                       "failed": _newton_solve(n["solves"][own]),
                       "other": _newton_solve(n["solves"][other])}  # fmt: skip
    return {"cases": cases, "passed": passed}


def charon_newton_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """Issue #223. Top three panels: per Newton iteration of every failed solve, at the tolerance
    its sweep failed at, the WRMS norm against the test's limit, the same over the last
    iterations for the solves that come close to it, and the condition number of J.
    Below, one row per case: the smallest WRMS norm beside floor_x; the last residual over its
    round-off scale; the condition number of D^-1 J beside 1/eps. Filled: the failed repeat;
    hollow: the repeat at the other tolerance."""
    pal = ef.PALETTES[palette]
    k = charon_newton(roots)
    cases = k["cases"]
    names = list(cases)
    y = np.arange(len(names))
    lw = ef.STYLE["line_width"]
    ms = STYLE["marker_pt"] ** 2
    colour = {"nfet_05v0": pal["electron"], "pfet_05v0": pal["hole"]}
    small = ef.STYLE["text_pt"] * STYLE["legend_scale"]
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["newton_in"])
        wr_it, zoom, cond_it, wr, res, cond = fig.subplots(
            len(CHARON_NEWTON_PANELS), 1, height_ratios=STYLE["newton_rows"]
        )
        for i, (name, c) in enumerate(cases.items()):
            f = c["failed"]
            style = {"color": colour[c["device"]], "lw": lw, "ls": "-" if c["tau"] else "--",
                     "marker": STYLE["newton_markers"][i], "ms": STYLE["small_marker_pt"],
                     "mfc": "none"}  # fmt: skip
            wr_it.plot(f["iteration"], f["wrms"], label=c["label"], gid=f"wrms {name}", **style)
            cond_it.plot(f["iteration"], f["cond1_per_iteration"], gid=f"cond {name}", **style)
        wr_it.axhline(TOOLS["nox_wrms_tolerance"], color=pal["text"], lw=lw, ls=":",
                      label="the WRMS test's limit", gid="wrms limit")  # fmt: skip
        # the plateaus close to the limit, over the last iterations, on a linear axis
        window = STYLE["newton_cycle_window"]
        for i, (name, c) in enumerate(cases.items()):
            f = c["failed"]
            if f["smallest"] < STYLE["newton_inset_top"]:
                zoom.plot(f["iteration"][-window:], f["wrms"][-window:], color=colour[c["device"]],
                          lw=lw, ls="-" if c["tau"] else "--", marker=STYLE["newton_markers"][i],
                          ms=STYLE["small_marker_pt"], mfc="none", gid=f"plateau {name}")  # fmt: skip
        for ax, ylabel in zip(
            (wr_it, zoom, cond_it),
            CHARON_NEWTON_PANELS[: len(CHARON_NEWTON_PANELS) // 2],
            strict=True,
        ):
            ax.set_ylabel(ylabel)
            ax.grid(True)
        wr_it.set_yscale("log")
        cond_it.set_yscale("log")
        for ax in (wr_it, zoom, cond_it):
            ax.set_xlabel("Newton iteration of the failed solve")
        zoom.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))

        def rows(ax, key, values, marker, filled, label):
            if filled:
                colours = {"color": pal["highlight"]}
            else:  # hollow: the outline only
                colours = {"facecolors": "none", "edgecolors": pal["highlight"]}
            ax.scatter(values, y, marker=marker, s=ms, label=label, gid=key, **colours)

        rows(wr, "smallest wrms failed", [cases[n]["failed"]["smallest"] for n in names], "o",
             True, "smallest WRMS norm of the failed solve")  # fmt: skip
        rows(wr, "floor_x failed", [cases[n]["failed"]["floor_x"] for n in names], "s", False,
             "floor_x of the failed solve")  # fmt: skip
        wr.axvline(TOOLS["nox_wrms_tolerance"], color=pal["text"], lw=lw, ls=":",
                   gid="wrms limit rows")  # fmt: skip
        for which, filled, words in (
            ("failed", True, "the failed solve"),
            ("other", False, "the repeat at the other tolerance"),
        ):
            rows(res, f"residual ratio {which}", [cases[n][which]["res_ratio"] for n in names],
                 "D", filled, f"residual over its round-off scale, {words}")  # fmt: skip
            rows(cond, f"condition row scaled {which}",
                 [cases[n][which]["cond1_row_scaled"] for n in names], "^", filled,
                 f"condition number of D⁻¹J, {words}")  # fmt: skip
        cond.axvline(1 / np.finfo(np.float64).eps, color=pal["text"], lw=lw, ls="-.",
                     label="inverse of eps", gid="inverse eps")  # fmt: skip
        for ax, title in zip(
            (wr, res, cond), CHARON_NEWTON_PANELS[len(CHARON_NEWTON_PANELS) // 2 :], strict=True
        ):
            ax.set_xscale("log")
            ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
            ax.set_yticks(y, [cases[n]["label"] for n in names], fontsize=small)
            ax.invert_yaxis()
            ax.set_xlabel(title)
            ax.grid(True, axis="x")
        # the residual ratios span less than two decades: label the 2s and 5s between them too
        res.xaxis.set_minor_locator(matplotlib.ticker.LogLocator(subs=STYLE["newton_res_subs"]))
        plain = matplotlib.ticker.FuncFormatter(lambda v, _pos: f"{v:g}")
        res.xaxis.set_major_formatter(plain)
        res.xaxis.set_minor_formatter(plain)
        handles, labels = [], []
        for ax in (wr_it, wr, res, cond):
            h, lab = ax.get_legend_handles_labels()
            handles += h
            labels += lab
        fig.legend(handles, labels, loc="outside lower center", ncols=STYLE["legend_cols"],
                   frameon=False, fontsize=small)  # fmt: skip
        return fig


#: The panels of the Newton figure, top to bottom: the y-axis titles of the three iteration
#: panels, then the x-axis titles of the three row panels.
CHARON_NEWTON_PANELS = ("WRMS norm", "WRMS norm near the limit", "condition number of J",
                        "WRMS norm",
                        "residual over its round-off scale",
                        "condition number at the last iteration")  # fmt: skip


def charon_traps(roots: Roots = DEFAULT_ROOTS) -> dict:
    """Issue #224 (``probes.json``, ``deck_traps``): the misnamed doping block's nodal doping
    against the description, per block (interior nodes), depth (um) and cm^-3."""
    rec = charon_record("probes", charon_root(roots))["deck_traps"]["doping_block_misnamed"]
    d = rec["doping"]
    x, dop = np.asarray(d["x_um"]), np.asarray(d["doping_cm3"])
    cv = charon_record("cv", charon_root(roots))["runs"][CHARON_REF["nfet_05v0"]]
    bn = cv["boundary_nodes"]
    blocks = {"gate_poly": (slice(0, bn[1]), d["poly_description_cm3"]),
              "body": (slice(bn[2] + 1, len(x)), d["body_description_cm3"])}  # fmt: skip
    return {b: {"x_um": x[sl], "charon": dop[sl], "description": np.full(len(x[sl]), want)}
            for b, (sl, want) in blocks.items()}  # fmt: skip


def charon_traps_figure(palette: str, roots: Roots = DEFAULT_ROOTS):
    """Issue #224: the nodal net doping of the deck whose body doping block is named BodyDoping,
    one panel per block, the description as a line and Charon's nodal values as markers."""
    pal = ef.PALETTES[palette]
    k = charon_traps(roots)
    with matplotlib.rc_context(ef.palette_rc(palette)):
        fig = _figure(STYLE["tall_in"])
        axes = fig.subplots(len(k), 1)
        for ax, (block, d) in zip(axes, k.items(), strict=True):
            ax.plot(d["x_um"], d["description"], color=pal["highlight"], lw=ef.STYLE["line_width"],
                    label="description", gid=f"{block} description")  # fmt: skip
            ax.plot(d["x_um"], d["charon"], ls="none", marker="o", ms=STYLE["small_marker_pt"],
                    mfc="none", mec=pal["electron"], label="Charon nodes",
                    gid=f"{block} charon")  # fmt: skip
            ax.set_ylabel(f"{block}: net doping (cm⁻³)")
        axes[-1].set_xlabel("depth from the gate end (µm)")
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside lower center", ncols=STYLE["legend_cols"],
                   frameon=False)  # fmt: skip
        return fig


# --- the registry -------------------------------------------------------------------------------


#: A clip path's id in matplotlib's SVG, where it is defined and where it is used.
_CLIP_ID = re.compile(rb'(?<=id=")p[a-f\d]+(?=")|(?<=url\(#)p[a-f\d]+(?=\))')


def _stable_clip_ids(svg: bytes) -> bytes:
    """``svg`` with each clip path's id replaced by its order of first appearance. matplotlib
    hashes a clip rectangle's float bounds into the id, and constrained layout can move those
    bounds in their last bits between processes (the charon-newton figure did, one hash seed in
    about eight), though the drawn coordinates stay the same."""
    ids: dict[bytes, bytes] = {}
    return _CLIP_ID.sub(lambda m: ids.setdefault(m.group(0), f"clip{len(ids)}".encode()), svg)


def _svg_of(draw: Callable) -> Callable[[str, Roots], bytes]:
    def svg(palette: str, roots: Roots = DEFAULT_ROOTS) -> bytes:
        with matplotlib.rc_context(ef.palette_rc(palette)):
            return _stable_clip_ids(ef.svg_bytes(draw(palette, roots)))

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
    "meshconv-2d-fitted": _svg_of(meshconv_2d_fitted_figure),
    "pn-slab": _svg_of(pn_slab_figure),
    "pin-depletion": _svg_of(pin_depletion_figure),
    "abrupt-junction": _svg_of(abrupt_junction_figure),
    "edge-sensitivity": _svg_of(edge_sensitivity_figure),
    "edge-rerun": _svg_of(edge_rerun_figure),
    "charon-strip": _svg_of(charon_strip_figure),
    "charon-cv": _svg_of(charon_cv_figure),
    "charon-hard-range": _svg_of(charon_hard_range_figure),
    "charon-structures": _svg_of(charon_structures_figure),
    "charon-tolerance": _svg_of(charon_tolerance_figure),
    "charon-doping": _svg_of(charon_doping_figure),
    "charon-checks": _svg_of(charon_checks_figure),
    "charon-newton": _svg_of(charon_newton_figure),
    "charon-traps": _svg_of(charon_traps_figure),
}


def write_all(out_dir: Path, roots: Roots = DEFAULT_ROOTS) -> None:
    """Write every figure of :data:`FIGURES` as ``<name>-light.svg`` and ``<name>-dark.svg``,
    from the trees of ``roots``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, draw in FIGURES.items():
        for palette in ef.PALETTES:
            (out / f"{name}-{palette}.svg").write_bytes(draw(palette, roots))
