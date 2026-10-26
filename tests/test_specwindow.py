# SPDX-License-Identifier: Apache-2.0
"""PDK spec-window sanity check and corner envelope (spec 5.2)."""

import json
import math

import pytest

from gf180tcad import specwindow
from gf180tcad.devices import CORNERS
from gf180tcad.sandbox import REPO_ROOT

RESULTS = REPO_ROOT / "results" / "spice"
INF = math.inf


# --- envelope ------------------------------------------------------------------------------


def test_envelope_is_min_max_per_metric():
    by_corner = {
        "typical": {"a": 2.0, "b": -1.0},
        "ff": {"a": 3.0, "b": -2.0},
        "ss": {"a": 1.0, "b": -0.5},
    }
    assert specwindow.envelope(by_corner) == {"a": (1.0, 3.0), "b": (-2.0, -0.5)}


def test_envelope_rejects_missing_metric_and_empty():
    with pytest.raises(ValueError, match="empty"):
        specwindow.envelope({})
    with pytest.raises(ValueError, match="'b'"):
        specwindow.envelope({"typical": {"a": 1.0, "b": 2.0}, "ff": {"a": 1.0}})


# --- window --------------------------------------------------------------------------------


def test_window_spec_contains_envelope():
    w = specwindow.window("vt", (0.58, 0.82), (0.6, 0.7))
    assert (w.lo, w.hi, w.source, w.metric) == (0.58, 0.82, "spec", "vt")


def test_window_envelope_contains_spec():
    w = specwindow.window("vt", (0.58, 0.82), (0.5, 0.9))
    assert (w.lo, w.hi, w.source) == (0.5, 0.9, "envelope")


def test_window_identical_intervals_are_the_spec():
    assert specwindow.window("m", (0.0, 1.0), (0.0, 1.0)).source == "spec"


def test_window_partial_overlap_is_the_hull():
    w = specwindow.window("m", (0.0, 10.0), (9.0, 12.0))
    assert (w.lo, w.hi, w.source) == (0.0, 12.0, "hull")
    w = specwindow.window("m", (5.0, 10.0), (-1.0, 7.0))
    assert (w.lo, w.hi, w.source) == (-1.0, 10.0, "hull")


def test_window_disjoint_is_the_hull():
    w = specwindow.window("m", (0.0, 1.0), (3.0, 4.0))
    assert (w.lo, w.hi, w.source) == (0.0, 4.0, "hull")
    w = specwindow.window("m", (3.0, 4.0), (0.0, 1.0))
    assert (w.lo, w.hi, w.source) == (0.0, 4.0, "hull")


def test_window_keeps_spec_typ_and_tt_inside_the_hull():
    w = specwindow.window("m", (0.0, 1.0), (3.0, 4.0))
    assert w.contains(0.5) and w.contains(3.5)


def test_window_one_sided_spec_stays_unbounded():
    w = specwindow.window("ioff", (-INF, 10.0), (0.1, 5.0))
    assert (w.lo, w.hi, w.source) == (-INF, 10.0, "spec")
    w = specwindow.window("ioff", (-INF, 10.0), (0.1, 50.0))
    assert (w.lo, w.hi, w.source) == (-INF, 50.0, "hull")


def test_window_one_sided_magnitude_spec():
    w = specwindow.window("ioff", (0.0, 10.0), (0.1, 5.0))
    assert (w.lo, w.hi, w.source) == (0.0, 10.0, "spec")
    w = specwindow.window("ioff", (0.0, 10.0), (0.1, 50.0))
    assert (w.lo, w.hi, w.source) == (0.0, 50.0, "hull")


def test_window_both_unbounded_is_spec():
    assert specwindow.window("m", (-INF, INF), (0.0, 1.0)).source == "spec"
    assert specwindow.window("m", (0.0, INF), (-1.0, 1.0)).hi == INF


def test_window_contains_and_frozen():
    w = specwindow.window("m", (0.0, 10.0), (1.0, 2.0))
    assert w.contains(0.0) and w.contains(10.0) and not w.contains(10.1)
    with pytest.raises(AttributeError):
        w.lo = 1.0


def test_window_rejects_inverted():
    with pytest.raises(ValueError):
        specwindow.window("m", (2.0, 1.0), (0.0, 1.0))


def test_envelope_tree_skips_incomplete_corner_sets(tmp_path):
    def put(corner, device, gid, v):
        d = tmp_path / "ngspice" / corner / device / gid
        d.mkdir(parents=True)
        (d / "metrics.json").write_text(json.dumps({"metrics": {"m": v}}))

    for i, c in enumerate(CORNERS):
        put(c, "nfet_05v0", "full", float(i))
    for c in CORNERS[:3]:
        put(c, "nfet_05v0", "partial", 1.0)
    assert specwindow.envelope_tree(tmp_path) == {
        "ngspice": {"nfet_05v0": {"full": {"m": [0.0, 4.0]}}}
    }
    assert specwindow.incomplete(tmp_path) == [("ngspice", "nfet_05v0", "partial")]


# --- spec file -----------------------------------------------------------------------------


def test_spec_file_matches_the_published_page():
    spec = specwindow.load_spec()
    assert spec["source_url"].endswith("/elec_specs_3.html") and spec["retrieved"]
    by = {(e["device"], e["symbol"]): e for e in spec["entries"]}
    ne, pe = "nfet_05v0", "pfet_05v0"
    assert [by[ne, "VT0"][k] for k in ("min", "typ", "max")] == [0.58, 0.7, 0.82]
    assert [by[pe, "VT0"][k] for k in ("min", "typ", "max")] == [-0.96, -0.83, -0.7]
    assert [by[ne, "Idsat"][k] for k in ("min", "typ", "max")] == [400, 500, 600]
    assert [by[pe, "Idsat"][k] for k in ("min", "typ", "max")] == [-280, -240, -200]
    assert [by[ne, "Ioff"][k] for k in ("min", "typ", "max")] == [None, 1, 10]
    assert [by[pe, "Ioff"][k] for k in ("min", "typ", "max")] == [-10, -1, None]
    assert (by[ne, "VT0"]["geometry_id"], by[pe, "VT0"]["geometry_id"]) == (
        "w10p0_l0p60",
        "w10p0_l0p50",
    )
    for e in spec["entries"]:
        assert e["units"] and e["bias"]
        if e.get("per_area"):
            continue  # its own page (test_cox_entry_is_tcad_only)
        assert e["source_url"] == spec["source_url"] and e["retrieved"] == spec["retrieved"]


COX_PAGE = (
    "https://gf180mcu-pdk.readthedocs.io/en/latest/analog/spice/elec_specs/elec_specs_5_3.html"
)


def test_cox_entry_is_tcad_only():
    """The public 6 V Cox (section 5.3, rows 'COX (Poly) 6V', 6V GATE N and P): a per-area
    entry with no geometry, for a metric SPICE does not extract, so the SPICE spec check lists it
    as "TCAD only" and never compares it (gf180tcad.docgen._tcad_only)."""
    spec = specwindow.load_spec()
    cox = [e for e in spec["entries"] if e.get("per_area")]
    assert sorted(e["device"] for e in cox) == ["nfet_05v0", "pfet_05v0"]
    for e in cox:
        assert (e["geometry_id"], e["w_um"], e["l_um"]) == (None, None, None)
        assert e["metric"] == "cox_ff_per_um2" and e["units"] == "fF/um^2"
        assert [e[k] for k in ("min", "typ", "max")] == [1.8, 2.3, 2.8]
        assert e["source_url"] == COX_PAGE and e["section"] == "5.3 Gate oxide capacitance"
        assert e["retrieved"]
        assert e not in _compared_entries()
    tt = _metrics("ngspice", "typical", "nfet_05v0", "w10p0_l10p00")
    assert "cox_ff_per_um2" not in tt  # SPICE does not extract it


@pytest.mark.parametrize(
    "device,symbol,expected",
    [
        ("nfet_05v0", "VT0", (0.58, 0.82)),
        ("pfet_05v0", "VT0", (-0.96, -0.7)),  # signed metric: as published
        ("nfet_05v0", "Idsat", (400.0, 600.0)),
        ("pfet_05v0", "Idsat", (200.0, 280.0)),  # magnitude metric
        ("nfet_05v0", "Ioff", (0.0, 10.0)),  # one-sided: open side is 0 for a magnitude
        ("pfet_05v0", "Ioff", (0.0, 10.0)),
    ],
)
def test_spec_range_in_metric_convention(device, symbol, expected):
    spec = specwindow.load_spec()
    (e,) = [x for x in spec["entries"] if x["device"] == device and x["symbol"] == symbol]
    assert specwindow.spec_range(e) == expected


def test_spec_range_one_sided_signed_metric_is_infinite():
    e = {"device": "nfet_05v0", "metric": "vt_lin_cc", "min": None, "max": 0.82}
    assert specwindow.spec_range(e) == (-INF, 0.82)


def test_spec_range_rejects_unmapped_entry():
    spec = specwindow.load_spec()
    (e,) = [x for x in spec["entries"] if x["symbol"] == "BVDSS" and x["device"] == "nfet_05v0"]
    with pytest.raises(ValueError, match="no metric"):
        specwindow.spec_range(e)


# --- committed results ---------------------------------------------------------------------


def _metrics(engine, corner, device, gid):
    path = RESULTS / engine / corner / device / gid / "metrics.json"
    return json.loads(path.read_text(encoding="utf-8"))["metrics"]


def _compared_entries():
    """The entries compared with a SPICE metric (not the per-area, TCAD-only ones)."""
    return [e for e in specwindow.load_spec()["entries"] if e["metric"] and not e.get("per_area")]


@pytest.mark.parametrize("entry", _compared_entries(), ids=lambda e: f"{e['device']}-{e['symbol']}")
def test_tt_within_pdk_spec(entry):
    value = _metrics("ngspice", "typical", entry["device"], entry["geometry_id"])[entry["metric"]]
    lo, hi = specwindow.spec_range(entry)
    assert lo <= value <= hi, f"{entry['metric']} = {value} outside spec [{lo}, {hi}]"


def _all_jobs():
    return sorted(
        (engine, device, gid)
        for engine in ("ngspice", "xyce")
        for device_dir in sorted((RESULTS / engine / "typical").iterdir())
        for device in [device_dir.name]
        for gid in sorted(p.name for p in device_dir.iterdir())
    )


def test_envelope_json_shape_and_contains_tt():
    env = json.loads((RESULTS / "envelope.json").read_text(encoding="utf-8"))
    jobs = _all_jobs()
    assert len(jobs) == 24
    assert set(env) == {"ngspice", "xyce"}
    n = 0
    for engine, device, gid in jobs:
        tt = _metrics(engine, "typical", device, gid)
        got = env[engine][device][gid]
        assert set(got) == set(tt), (engine, device, gid)
        for metric, (lo, hi) in got.items():
            assert lo <= tt[metric] <= hi, (engine, device, gid, metric)
            corner_vals = [_metrics(engine, c, device, gid)[metric] for c in CORNERS]
            assert (lo, hi) == (min(corner_vals), max(corner_vals))
            n += 1
    assert n == 12 * 13 + 12 * 11


def test_nfet_notes_do_not_describe_the_pfet():
    for e in specwindow.load_spec()["entries"]:
        if e["device"] == "nfet_05v0":
            assert "pfet" not in (e["definition_note"] or "").lower(), e["symbol"]
