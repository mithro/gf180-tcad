# SPDX-License-Identifier: Apache-2.0
"""Hand-written numbers on the docs pages match the committed SPICE reference.

The generated results pages are computed from ``results/spice`` at build time; these prose
pages are not, so each number they quote from the results is listed here with where it comes
from. A number passes if it is the committed value correctly rounded at the last digit written
(``0.365 %`` for 0.3647 %). After a regeneration that moves one, the test names the page, the
text and the current value.
"""

import json
import re
from decimal import Decimal
from functools import cache
from pathlib import Path

import numpy as np
import pytest

from gf180tcad import io
from gf180tcad.devices import DEVICES, geometry_id
from gf180tcad.metrics import SS_I_HI, SS_I_LO
from gf180tcad.spice.xyce import engine_diff

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "spice"
ENGINE_PAGE = ROOT / "docs" / "limitations" / "engine-cross-check.md"
SPEC_PAGE = ROOT / "docs" / "comparison" / "pdk-spec-check.md"
LIMITS_PAGE = ROOT / "docs" / "limitations" / "index.md"
NUM = r"(-?[0-9]+(?:\.[0-9]+)?(?:e-?[0-9]+)?)"


@cache
def _cols(engine: str, device: str, gid: str, sweep: str) -> dict:
    return io.read_csv(RESULTS / engine / "typical" / device / gid / f"{sweep}.csv")[0]


def diff(device: str, sweep: str, gid: str | None = None) -> float:
    """engine_diff at the typical corner: one geometry, or the max over all of them."""
    gids = [gid] if gid else [geometry_id(g) for g in DEVICES[device].geometries]
    return max(
        engine_diff(_cols("ngspice", device, g, sweep), _cols("xyce", device, g, sweep))
        for g in gids
    )


def diffs(device: str, sweeps: tuple[str, ...]) -> list[float]:
    return [diff(device, s, geometry_id(g)) for s in sweeps for g in DEVICES[device].geometries]


def _sat_tt(engine: str) -> tuple:
    """nfet 10/0.6 ``idvg_sat`` (Vds = 5 V) at Vbs = 0, typical corner: Vg and Id."""
    c = _cols(engine, N, NLMIN, "idvg_sat")
    m = c["vb"] == 0.0
    return c["vg"][m], c["id"][m]


def vg_at(engine: str, i0: float) -> float:
    """First Vg where Id reaches ``i0``, log-linear between the bracketing points."""
    vg, i = _sat_tt(engine)
    k = int(np.flatnonzero(i >= i0)[0])
    y0, y1 = np.log10(i[k - 1]), np.log10(i[k])
    return float(vg[k - 1] + (np.log10(i0) - y0) * (vg[k] - vg[k - 1]) / (y1 - y0))


def shift_mv(i0: float) -> float:
    """|Vg(Xyce) - Vg(ngspice)| at Id = ``i0``, in mV."""
    return 1000 * abs(vg_at("xyce", i0) - vg_at("ngspice", i0))


def subthreshold_excess() -> float:
    """Max of Id,Xyce / Id,ngspice - 1 where Id/W is in the SS window [1e-11, 1e-8] A/um."""
    _, a = _sat_tt("ngspice")
    _, b = _sat_tt("xyce")
    w = 10.0
    m = (a / w > SS_I_LO) & (a / w < SS_I_HI)
    return float(np.max(b[m] / a[m] - 1))


def _at5() -> float:
    """Relative Id difference of the engines at Vgs = 5 V on that curve."""
    _, a = _sat_tt("ngspice")
    _, b = _sat_tt("xyce")
    return float(abs(b[-1] - a[-1]) / max(abs(a[-1]), abs(b[-1])))


def metric(device: str, gid: str, name: str) -> float:
    path = RESULTS / "ngspice" / "typical" / device / gid / "metrics.json"
    return json.loads(path.read_text(encoding="utf-8"))["metrics"][name]


def _gid(w: str, l: str) -> str:
    """geometry_id of W/L as written on the page."""
    want = (float(w), float(l))
    return geometry_id(
        next(g for d in DEVICES.values() for g in d.geometries if (g.w_um, g.l_um) == want)
    )


N, P = "nfet_05v0", "pfet_05v0"
NLMIN, PLMIN = "w10p0_l0p60", "w10p0_l0p50"
GEOMS = [("10", "0.6"), ("10", "0.7"), ("10", "1"), ("10", "2"), ("10", "10"), ("1.6", "0.7")]

# (page, regex with one group per number, values in the same order)
CASES = [
    # engine-cross-check.md: the claims table, in percent
    (ENGINE_PAGE, rf"^\| nfet \| `idvd` \| {NUM} % \|$", lambda: [100 * diff(N, "idvd")]),
    (ENGINE_PAGE, rf"^\| pfet \| `idvd` \| {NUM} \|$", lambda: [diff(P, "idvd")]),
    (ENGINE_PAGE, rf"^\| pfet \| `idvg_lin` \| {NUM} % \|$", lambda: [100 * diff(P, "idvg_lin")]),
    (ENGINE_PAGE, rf"^\| pfet \| `idvg_sat` \| {NUM} % \|$", lambda: [100 * diff(P, "idvg_sat")]),
    # the twelve known failures, in percent
    (
        ENGINE_PAGE,
        rf"`idvg_lin`\n?\s*\({NUM} to {NUM} %\) and `idvg_sat` \({NUM} to {NUM} %\)",
        lambda: [
            100 * min(diffs(N, ("idvg_lin",))),
            100 * max(diffs(N, ("idvg_lin",))),
            100 * min(diffs(N, ("idvg_sat",))),
            100 * max(diffs(N, ("idvg_sat",))),
        ],
    ),
    (
        ENGINE_PAGE,
        rf"disagrees there by {NUM} to {NUM} %",
        lambda: [
            100 * min(diffs(N, ("idvg_lin", "idvg_sat"))),
            100 * max(diffs(N, ("idvg_lin", "idvg_sat"))),
        ],
    ),
    (ENGINE_PAGE, rf"engine_diff stays {NUM} for `idvg_lin`", lambda: [diff(N, "idvg_lin", NLMIN)]),
    # the PDK-as-published column of the forced-4.6 table (W10/L0.6)
    *(
        (ENGINE_PAGE, rf"^ *\| `{s}` \| {NUM} \| [^|]+ \|$", lambda s=s: [diff(N, s, NLMIN)])
        for s in ("idvg_lin", "idvg_sat", "idvd")
    ),
    # the per-geometry stock columns
    *(
        (
            ENGINE_PAGE,
            rf"^\| {re.escape(w)} \| {re.escape(l)} \| {NUM} \| [^|]+ \| {NUM} \| [^|]+ \|$",
            lambda w=w, l=l: [diff(N, "idvg_lin", _gid(w, l)), diff(N, "idvg_sat", _gid(w, l))],
        )
        for w, l in GEOMS
    ),
    # the subthreshold evidence table (nfet 10/0.6, typical, Vds = 5 V, Vbs = 0)
    *(
        (
            ENGINE_PAGE,
            rf"^\| {label} \| {NUM} \| {NUM} \| \u2212{NUM} \|$",
            lambda i0=i0: [vg_at("ngspice", i0), vg_at("xyce", i0), shift_mv(i0)],
        )
        for label, i0 in (("1 nA", 1e-9), ("100 nA", 1e-7), ("1 \u00b5A", 1e-6))
    ),
    (
        ENGINE_PAGE,
        (
            rf"current is a nearly constant {NUM} % higher\. That is\na gate-voltage shift of "
            rf"about {NUM} mV, and its effect fades in strong\ninversion \({NUM} at Vgs = 5 V\)"
        ),
        lambda: [
            100 * subthreshold_excess(),
            shift_mv(1e-9),
            _at5(),
        ],
    ),
    (
        ENGINE_PAGE,
        rf"comparison \(\{{doc\}}`\.\./comparison/agreement`\): about {NUM} mV of",
        lambda: [shift_mv(1e-9)],
    ),
    # pdk-spec-check.md: the TT column
    *(
        (
            SPEC_PAGE,
            rf"^\| {dev_label} \| {param} \| `{name}` \| {NUM} \|",
            lambda dev=dev, gid=gid, name=name: [metric(dev, gid, name)],
        )
        for dev, gid, dev_label in (
            (N, NLMIN, r"NE2 `nfet_05v0`"),
            (P, PLMIN, r"PE2 `pfet_05v0`"),
        )
        for param, name in (
            (r"VT0 \(V\)", "vt_lin_maxgm"),
            (r"Idsat \(uA/um\)", "idsat_ua_per_um"),
            (r"Ioff \(pA/um\)", "ioff_pa_per_um"),
        )
    ),
    (
        SPEC_PAGE,
        rf"\(VT0 {NUM} vs 0\.70 V, Idsat {NUM}\n?\s*vs 500 uA/um\)",
        lambda: [metric(N, NLMIN, "vt_lin_maxgm"), metric(N, NLMIN, "idsat_ua_per_um")],
    ),
    (
        SPEC_PAGE,
        rf"differs from it by {NUM} mV \(n\) and {NUM} mV \(p\)",
        lambda: [
            1000 * abs(metric(N, NLMIN, "vt_lin_cc") - metric(N, NLMIN, "vt_lin_maxgm")),
            1000 * abs(metric(P, PLMIN, "vt_lin_cc") - metric(P, PLMIN, "vt_lin_maxgm")),
        ],
    ),
    # limitations/index.md: the headline engine difference, in percent
    (
        LIMITS_PAGE,
        rf"disagree by {NUM} % on the nfet",
        lambda: [100 * max(diffs(N, ("idvg_lin", "idvg_sat")))],
    ),
]


def rounds_to(written: str, value: float) -> bool:
    """Is ``written`` the value ``value`` rounded to the significant digits written?

    ``written`` has n significant digits (``0.365``: 3, ``5.60e-3``: 3, ``7e-7``: 1); the
    value rounded to n significant digits must equal it. So ``1e-6`` does not pass for
    6.6e-7 (that rounds to ``7e-7``), although it is within half a unit of its last digit.
    """
    d = Decimal(written)
    n = len(d.as_tuple().digits)
    return Decimal(format(value, f".{n - 1}e")) == d


def test_rounds_to():
    assert rounds_to("0.365", 0.3647) and not rounds_to("0.37", 0.3647)
    assert rounds_to("0.221", 0.2209) and not rounds_to("0.23", 0.2209)
    assert rounds_to("5.62e-3", 0.005619) and rounds_to("5.60e-3", 0.005598)
    assert rounds_to("7e-7", 6.6e-7) and not rounds_to("1e-6", 6.6e-7)
    assert rounds_to("0.6", 0.6052) and rounds_to("25", 25.36) and not rounds_to("0.60", 0.6052)
    assert rounds_to("-0.8421", -0.84209854) and not rounds_to("-0.8421", 0.8421)


@pytest.mark.parametrize(
    "page, pattern, values",
    CASES,
    ids=[f"{c[0].name}:{i}" for i, c in enumerate(CASES)],
)
def test_hand_written_number_matches_the_results(page, pattern, values):
    text = page.read_text(encoding="utf-8")
    found = re.findall(pattern, text, re.MULTILINE)
    rel = page.relative_to(ROOT)
    assert len(found) == 1, f"{rel}: expected one match of {pattern!r}, found {len(found)}"
    written = found[0] if isinstance(found[0], tuple) else (found[0],)
    want = values()
    assert len(written) == len(want)
    for w, v in zip(written, want, strict=True):
        assert rounds_to(w, v), f"{rel}: {w!r} (in {pattern!r}) should read {v:.6g}"
