# SPDX-License-Identifier: Apache-2.0
"""The high-voltage junction experiment (experiments/hv-junction/): the physics of its host
modules, what each committed record pins, the record writers' refusals, and the numbers and
figures of docs/results/hv-junction.md against the records.

A record under results/hv-junction/ is tested when it is committed. A prediction case takes the
row of the last of main, rest, rest2, rest3, mem and family that holds it, and only a row that
was run with the parameters predict.py gives now. The p5 record is its own set: its cases carry
the names of ordinary cases and are never merged with them."""

import hashlib
import json
import re
import subprocess
import sys

import numpy as np
import pytest
from optional import importorskip

from gf180tcad.sandbox import REPO_ROOT

HERE = REPO_ROOT / "experiments" / "hv-junction"
sys.path.append(str(HERE))  # the experiment's modules import each other by bare name

import batch
import charon_deck
import charon_mesh
import charon_record
import checks
import fieldline
import hvsite
import ionize
import predict
import profile1d
import record

ROOT = REPO_ROOT / "results" / "hv-junction"
PAGE = REPO_ROOT / "docs" / "results" / "hv-junction.md"
Q, EPS, UM = 1.602176634e-19, 11.7 * 8.8541878128e-14, 1e-4

# The records record.py writes, and every record a file under results/hv-junction/ may be.
SWEEP_RECORDS = (
    "main",
    "rest",
    "rest2",
    "rest3",
    "mem",
    "gaps",
    "sharp",
    "family",
    "family3",
    "p5",
    "checks",
)
# The prediction records, in the order a later one replaces the cases of an earlier one.
PREDICTION_RECORDS = ("main", "rest", "rest2", "rest3", "mem", "gaps", "sharp", "family", "family3")
CHARON_RECORDS = ("charon-firstpass", "charon")
ALL_RECORDS = (*SWEEP_RECORDS, "diodes", *CHARON_RECORDS)
# The case the sandbox test reruns and its tolerance in volts. It is a case of the record
# rest3, whose runs used the sweep code as it is now (later commits only reformatted it);
# main.json's runs used an earlier ramp, which solves other bias points.
RERUN_RECORD = "rest3"
RERUN_CASE, RERUN_TOL_V = "NT20c|BD|corner", 1e-6


def _load(name: str) -> dict:
    return json.loads((ROOT / f"{name}.json").read_text("utf-8"))


def _present(names=ALL_RECORDS) -> list[str]:
    return [n for n in names if (ROOT / f"{n}.json").is_file()]


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, check=False, capture_output=True)


def _sha(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()


def _main_cases() -> dict:
    """The cases of predict.py's set "main"."""
    return predict.main_cases()


def _current_cases() -> dict:
    """Every prediction case predict.py gives now: the sets "main" and "family"."""
    return {**predict.main_cases(), **predict.family_cases()}


def _latest_rows() -> dict:
    """Each case's row in the last prediction record that holds it, for the rows that were run
    with the parameters predict.py gives now."""
    rows, now = {}, _current_cases()
    for name in _present(PREDICTION_RECORDS):
        rows.update(_load(name)["cases"])
    return {c: r for c, r in rows.items() if c in now and r["params_sha256"] == _sha(now[c])}


# --- the physics of the host modules --------------------------------------------------------------


def _abrupt_bv(n: float) -> float:
    """Breakdown of a one-sided abrupt junction of doping n, from the triangular field."""
    volts = np.geomspace(2.0, 2000.0, 400)
    ints = []
    for v in volts:
        w = np.sqrt(2 * EPS * v / (Q * n))
        s = np.linspace(0.0, w, 4000)
        ints.append(ionize.ionisation_integrals(s, Q * n * s / EPS)[0])
    return ionize.breakdown_voltage(volts, ints)


def test_electron_and_hole_integrals_agree_on_the_side_of_one():
    """I_n = 1 and I_p = 1 are the same condition: away from 1 both lie on the same side."""
    s = np.linspace(0, 2e-4, 2000)
    i_n, i_p = ionize.ionisation_integrals(s, 3.5e5 * s / s[-1])
    assert (i_n - 1) * (i_p - 1) > 0


@pytest.mark.parametrize(("n", "lo", "hi"), [(1e15, 250, 380), (1e16, 45, 75), (1e17, 9, 16)])
def test_abrupt_junction_breakdown_matches_textbook(n, lo, hi):
    """Sze and Ng, 3rd ed., ch. 2: BV = 60 V x (N / 1e16 cm^-3)^-0.75 for a one-sided abrupt
    silicon junction; the van Overstraeten coefficients lie within 25 % of it."""
    assert lo < _abrupt_bv(n) < hi


def test_breakdown_voltage_interpolates_the_logarithm():
    assert ionize.breakdown_voltage([10.0, 20.0], [0.1, 0.5]) is None
    got = ionize.breakdown_voltage([10.0, 20.0, 30.0], [0.01, 0.1, 10.0])
    assert np.isclose(got, 25.0)


def test_field_line_integral_matches_the_1d_integral():
    """fieldline.max_integral on a 1D triangular field laid out on a 2D grid."""
    n, v = 1e16, 50.0
    w = np.sqrt(2 * EPS * v / (Q * n))
    ys = np.linspace(0, 1.5 * w, 600)  # junction at y = 0 (N side), P depletion edge at y = w
    xs = np.linspace(0, 1e-4, 12)
    e = np.where(ys < w, Q * n * (w - ys) / EPS, 0.0)
    psi = v - np.concatenate([[0], np.cumsum(0.5 * (e[1:] + e[:-1]) * np.diff(ys))])
    xx, yy = np.meshgrid(xs, ys, indexing="ij")
    pp = np.broadcast_to(psi, xx.shape)
    got, _, emax = fieldline.max_integral(xx.ravel(), yy.ravel(), pp.ravel(), step=w / 2000)
    s = np.linspace(0, w, 4000)
    want, _ = ionize.ionisation_integrals(s, Q * n * s / EPS)
    assert abs(emax - Q * n * w / EPS) / emax < 0.01
    assert abs(got - want) / want < 0.03, (got, want)


def test_nwell_profile_meets_the_public_anchors():
    """The N-well under the trench oxide has a sheet resistance of 800 to 1200 ohm/sq
    (electrical specification 5.1), and its zero-bias capacitance lies within 15 % of
    diode_nw2ps_06v0's 1.4914e-4 F/m^2."""
    pr = hvsite.DEFAULT_PROCESS
    y = np.linspace(0, 16e-4, 32001)
    wells = [(g["peak"], g["rp"] * UM, g["sy"] * UM) for g in pr["nw"]]
    n, total = profile1d.net(y, wells, pr["sub"])
    assert 800 < profile1d.sheet_resistance(y, n, total, top=hvsite.STI * UM) < 1200
    c0 = profile1d.cv(y, n, np.array([0.0]))[0]
    assert abs(c0 - 1.4914e-8) / 1.4914e-8 < 0.15, c0


def test_no_plate_face_lies_on_a_region_boundary():
    """A plate whose face lay on y = 0, the boundary between the dielectric and the trench
    oxide, left the trench oxide under it floating: every plate lies wholly above the surface,
    and every drawn structure's plates lie inside the dielectric of its section."""
    for layer, (y0, y1) in hvsite.LAYER_Y.items():
        assert y0 < y1 < 0.0, layer
    for name, st in predict.STRUCTS.items():
        p = hvsite.section(st)
        for pl in p["plates"]:
            assert -p["ox_top"] < pl["y0"] < pl["y1"] < 0.0, name
            assert 0.0 < pl["x0"] < pl["x1"] < p["width"], name


def _acceptor_starts(p: dict) -> list[float]:
    """Where the P-well boxes start (not the P+ ring, not the deep P layer)."""
    return sorted(b["x0"] for b in p["pfield"] if b["peak"] < 1e19 and b["rp"] <= 3)


def test_generated_pwell_abuts_an_nwell_but_not_a_deep_nwell():
    edge = 8.0
    assert _acceptor_starts(hvsite.section({}, {"pwell": "everywhere"}))[0] == edge
    deep = hvsite.section({"kind": "dnw"}, {"pwell": "everywhere"})
    assert _acceptor_starts(deep)[0] == edge + 1.5
    assert _acceptor_starts(hvsite.section({}, {"pwell": "drawn"})) == []


def test_nat_keeps_the_pwell_out_to_the_ring():
    p = hvsite.section({"nat_gap": 0.6, "term": 20.0}, {"pwell": "everywhere"})
    starts = _acceptor_starts(p)
    assert starts[0] == 8.0  # the strip between the well and the NAT layer
    assert max(starts) == 8.0 + 20.0 - 0.5
    deep = hvsite.section({"kind": "dnw", "nat_gap": -1.0}, {"pwell": "everywhere"})
    assert min(_acceptor_starts(deep)) == 8.0 + 20.0 - 0.5


def test_plates_and_rings_follow_the_layout():
    p = hvsite.section({"plates": {"poly": 2.0, "m1": 5.0}, "rings": [[2.0, 2.0], [2.5, 2.0]]})
    poly, m1 = p["plates"]
    assert (poly["x1"], m1["x1"]) == (10.0, 13.0)
    assert poly["y1"] == -0.01 and m1["y1"] == -0.86
    assert sorted({w["x0"] for w in p["wells"] if w["x0"] > 8.0}) == [10.0, 14.5]
    assert len(p["probes"]) == 2


def test_a_drawn_pwell_starts_where_drawn_under_b_only():
    plain = hvsite.section({}, {"pwell": "everywhere"})
    drawn = hvsite.section({"pwell_gap": 6.0}, {"pwell": "everywhere"})
    assert drawn["pfield"] == plain["pfield"]
    assert _acceptor_starts(hvsite.section({"pwell_gap": 6.0}, {"pwell": "drawn"})) == [14.0, 14.0]


def _two_regions():
    def grid(xs, ys):
        gx, gy = np.meshgrid(xs, ys, indexing="ij")
        idx = np.arange(gx.size).reshape(len(xs), len(ys))
        tri = []
        for i in range(len(xs) - 1):
            for j in range(len(ys) - 1):
                a, b, c, d = idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1]
                tri += [[a, c, b], [a, d, c]]  # clockwise on purpose: merge must turn them
        return np.stack([gx.ravel(), gy.ravel()], axis=1), np.array(tri), idx

    xs = np.array([0.0, 1e-4, 2e-4])
    xy_si, tri_si, idx_si = grid(xs, np.array([0.0, 1e-4, 3e-4]))
    xy_ox, tri_ox, _ = grid(xs, np.array([-2e-4, 0.0]))
    top = idx_si[:, 0]
    meta = {"regions": [["si", "Si"], ["ox", "Oxide"]], "contacts": {"well": "si"}, "extra": {}}
    arrays = {"xy_si": xy_si, "tri_si": tri_si, "xy_ox": xy_ox, "tri_ox": tri_ox,
              "contact_well": np.array([[top[0], top[1]]])}  # fmt: skip
    return meta, arrays


def test_charon_mesh_shares_interface_nodes_and_orients():
    meta, arrays = _two_regions()
    m = charon_mesh.merge(meta, arrays)
    assert len(m["xy_cm"]) == 9 + 6 - 3  # the three surface nodes are shared
    assert np.array_equal(m["xy_cm"][m["node_map"]["si"]], arrays["xy_si"])
    for _, _, tri in m["blocks"]:
        a, b, c = (m["xy_cm"][tri[:, k]] for k in range(3))
        ab, ac = b - a, c - a
        assert np.all(ab[:, 0] * ac[:, 1] - ab[:, 1] * ac[:, 0] > 0)
    block, elems, locs = m["sides"]["well"]
    tri = m["blocks"][0][2][elems[0]]
    edge = {int(tri[locs[0]]), int(tri[(locs[0] + 1) % 3])}
    assert block == 0 and edge == {int(g) for g in m["node_map"]["si"][arrays["contact_well"][0]]}


def test_charon_deck_doping_is_the_devsim_expression():
    p = {"sub": 3e15, "wells": [{"x0": -5, "x1": 4, "peak": 9e16, "rp": 0.5, "sy": 0.4, "sx": 0.3}],
         "pfield": [{"x0": 6, "x1": 20, "peak": 1e17, "rp": 0.5, "sy": 0.4, "sx": 0.3}],
         "plates": [{"x0": 3, "x1": 8, "y0": -0.2, "y1": 0.0, "tie": "well"}]}  # fmt: skip
    dev = charon_deck.describe_params(p, [["ox", "Oxide"], ["si", "Si"]])
    net = charon_deck.net_doping(dev, np.array([4.0, 0.0, 12.0]), np.array([0.5, 0.5, 5.0]))
    assert np.isclose(net[0], -3e15 + 9e16 * 0.5, rtol=1e-6)  # on the drawn edge: half the peak
    assert np.isclose(net[1], -3e15 + 9e16, rtol=1e-6)
    text = charon_deck.deck(dev, "sweep", "dd0.exo", "sweep.exo", v1=50.0, step=2.0)
    assert "BC is ohmic for well on si swept from 0 to 50" in text
    assert "avalanche is on" in text and "electron E0 = 1.231e+06" in text


# --- the committed records ------------------------------------------------------------------------


def test_records_are_known_files():
    files = sorted(p.name for p in ROOT.iterdir())
    assert set(files) <= {f"{n}.json" for n in ALL_RECORDS}, files
    assert "main.json" in files


def _files_at(commit: str, files: dict[str, str]) -> None:
    """Each file of the experiment has the recorded sha256 at ``commit``, an ancestor of HEAD."""
    assert _git("cat-file", "-e", commit + "^{commit}").returncode == 0, commit
    assert _git("merge-base", "--is-ancestor", commit, "HEAD").returncode == 0, commit
    for file, digest in files.items():
        blob = _git("show", f"{commit}:experiments/hv-junction/{file}")
        assert blob.returncode == 0, (commit, file)
        assert hashlib.sha256(blob.stdout).hexdigest() == digest, (commit, file)


def _image_at(commit: str, pins: dict) -> None:
    """The pinned images are the ones docker/ named at ``commit`` and names now."""
    for key, path in (("image", "docker/TCAD_DEV_IMAGE"), ("charon_image", "docker/CHARON_IMAGE")):
        if key in pins:
            then = _git("show", f"{commit}:{path}").stdout.decode().split()[0]
            assert pins[key] == then == (REPO_ROOT / path).read_text("utf-8").split()[0]


@pytest.mark.parametrize("name", _present())
def test_record_pins_what_the_runs_used(name):
    """The record's pins are checked against the checkout at each commit its runs were made
    at. Every such commit is an ancestor of HEAD, named the pinned image, and held the modules
    a sweep imports (record.SWEEP_FILES) with the recorded sha256. A Charon record also pins
    the Charon image and, per case, the Charon modules at the case's commit. The diode record
    pins one commit and every file of the experiment at it."""
    rec = _load(name)
    pins = rec["pins"]
    if name == "diodes":
        assert rec["schema"] == 1 and pins["dirty"] is False
        assert set(pins) == {"commit", "dirty", "files_sha256", "image"}
        tree = _git("ls-tree", "--name-only", pins["commit"], "experiments/hv-junction/")
        assert sorted(pins["files_sha256"]) == sorted(
            t.rsplit("/", 1)[1] for t in tree.stdout.decode().split())  # fmt: skip
        _files_at(pins["commit"], pins["files_sha256"])
        _image_at(pins["commit"], pins)
        return
    assert rec["schema"] == 2
    charon = name in CHARON_RECORDS
    assert set(pins) == {"commits", "files_sha256", "image"} | (
        {"charon_image"} if charon else {"commit"})  # fmt: skip
    assert tuple(sorted(pins["files_sha256"])) == record.SWEEP_FILES
    assert pins["commits"] == sorted(set(pins["commits"])) and pins["commits"]
    if not charon:
        assert pins["commit"] == (pins["commits"][0] if len(pins["commits"]) == 1 else None)
    for commit in pins["commits"]:
        _files_at(commit, pins["files_sha256"])
        _image_at(commit, pins)
    if charon:
        assert {row["commit"] for row in rec["cases"].values()} == set(pins["commits"])
        for row in rec["cases"].values():
            assert tuple(sorted(row["charon_files_sha256"])) == charon_record.CHARON_FILES
            _files_at(row["commit"], row["charon_files_sha256"])
        src = rec["devsim_record"]
        blob = _git("show", f"{src['commit']}:{src['path']}")
        assert blob.returncode == 0 and hashlib.sha256(blob.stdout).hexdigest() == src["sha256"]
        assert _git("merge-base", "--is-ancestor", src["commit"], "HEAD").returncode == 0


@pytest.mark.parametrize("name", _present(SWEEP_RECORDS))
def test_record_rows_are_whole(name):
    """Every row holds the kept fields with one value per bias point, its breakdown voltage is
    the crossing of 1 of its own integral, and no case is both a row and not converged."""
    rec = _load(name)
    assert set(rec) == {"schema", "pins", "cases", "not_converged"}
    assert not set(rec["cases"]) & set(rec["not_converged"])
    for case, row in rec["cases"].items():
        assert set(row) == {"params_sha256", "bv_v", "reached_v", "nodes", *record.KEEP}, case
        assert {len(row[k]) for k in record.KEEP} == {len(row["v"])}, case
        assert row["v"] == sorted(row["v"]) and row["reached_v"] >= row["v"][-1], case
        bv = ionize.breakdown_voltage(row["v"], row["i_n"])
        assert bv == row["bv_v"] or np.isclose(bv, row["bv_v"], rtol=1e-12), case


def test_only_current_cases_are_read(hf):
    """A record is the record of what ran at its commit. The page and the figures read a row
    only when its parameters are the ones predict.py gives now, from the last prediction record
    that holds the case, and every table case is one of the present case set. The check
    record's parameters are the ones checks.py gives now."""
    assert hf.cases() == _latest_rows()
    assert hf.current_cases() == _current_cases()
    assert set(hf.table_cases()) <= set(_current_cases())
    if "checks" in _present():
        want = checks.check_cases()
        for case, row in _load("checks")["cases"].items():
            assert row["params_sha256"] == _sha(want[case]), case


def test_p5_is_its_own_set(hf):
    """The p5 cases carry the names of ordinary cases with other parameters (ring 1 held at
    0 V), so the p5 record is never read as a prediction record: no ordinary row has a p5
    case's parameters, and the page prints the p5 rows under their own keys."""
    p5, main = predict.p5_cases(), _main_cases()
    assert set(p5) <= set(main) and hf.P5_RECORD not in hf.PREDICTION_RECORDS
    assert all(_sha(p5[c]) != _sha(main[c]) for c in p5)
    assert sorted({c.split("|")[0] for c in p5}) == hf.p5_structures()
    rows = _load("p5")["cases"] if "p5" in _present() else {}
    want = {c: r for c, r in rows.items() if c in p5 and r["params_sha256"] == _sha(p5[c])}
    assert hf.p5_cases() == want
    ordinary = hf.cases()
    assert all(
        ordinary[c]["params_sha256"] != r["params_sha256"] for c, r in want.items() if c in ordinary
    )
    subs = hf.substitutions()
    for case in p5:
        assert subs[hf.p5_key(case)] == _text(want.get(case)), case
        assert hf.p5_key(case) != hf.key(case)


def test_copies_have_the_section_of_the_original():
    """A copy (a name ending in b or c), a lead control (ending in L) and NT20V give the cases
    of the structure they copy."""
    got = _main_cases()
    pairs = (("NT20b", "NT20"), ("NT20c", "NT20"), ("NT20L", "NT20"), ("NT20V", "NT20"),
             ("DT20b", "DT20"), ("NA0p6b", "NA0p6"), ("NM1_6b", "NM1_6"), ("NM1_6L", "NM1_6"),
             ("NR1_2L", "NR1_2"))  # fmt: skip
    for copy, orig in pairs:
        for proc in ("AL", "BL"):
            assert got[f"{copy}|{proc}|edge"] == got[f"{orig}|{proc}|edge"], copy


def test_diode_record_is_the_three_diodes():
    if "diodes" not in _present():
        pytest.skip("results/hv-junction/diodes.json is not committed")
    rec = _load("diodes")
    assert (
        set(rec) == {"schema", "pins", "diodes"} and tuple(sorted(rec["diodes"])) == checks.DIODES
    )
    for name, row in rec["diodes"].items():
        # the applied bias at breakdown is the triangular-field value less the built-in potential
        assert abs(row["bv_v"] - (_abrupt_bv(float(name)) - 0.9)) < 0.3, name


@pytest.mark.parametrize("name", _present(CHARON_RECORDS))
def test_charon_record_agrees_with_devsim(name, hf):
    """Each Charon case has the parameters and the breakdown voltage of the DEVSIM record it
    names, the integral on Charon's potential lies within 3 % of DEVSIM's breakdown voltage,
    and the record's cases are the ones the page lists."""
    rec = _load(name)
    src = rec["devsim_record"]
    devsim = json.loads(_git("show", f"{src['commit']}:{src['path']}").stdout)["cases"]
    assert tuple(sorted(rec["cases"])) == tuple(sorted(hf.CHARON_CASES[name]))
    for case, row in rec["cases"].items():
        assert set(row) == {"params_sha256", "commit", "charon_files_sha256", "devsim_bv_v",
                            "integral", *charon_record.KEEP}, case  # fmt: skip
        assert row["params_sha256"] == devsim[case]["params_sha256"], case
        assert row["devsim_bv_v"] == devsim[case]["bv_v"], case
        assert abs(row["bv_integral_v"] / row["devsim_bv_v"] - 1) < 0.03, case
        prefix = f"{hf.CHARON_PREFIX[name]}_{hf.key(case)[4:]}"
        subs = hf.substitutions()
        assert subs[f"{prefix}_devsim"] == f"{row['devsim_bv_v']:.2f}"
        assert subs[f"{prefix}_integral"] == f"{row['bv_integral_v']:.2f}"
        assert subs[f"{prefix}_last"] == f"{row['last_converged_v']:.2f}"
        cur = row["bv_current_v"]
        assert subs[f"{prefix}_current"] == ("\u2014" if cur is None else f"{cur:.2f}")
    if name == "charon":  # the present family: the DEVSIM rows are the ones the page reads
        rows = _latest_rows()
        assert all(rows[c]["params_sha256"] == r["params_sha256"] for c, r in rec["cases"].items())


# --- the record writers refuse what they should ---------------------------------------------------

_PINS = {"commit": "c0ffee", "dirty": False, "image": "img@sha256:1",
         "files_sha256": {f: "1" for f in (*record.SWEEP_FILES, *charon_record.CHARON_FILES, "x.py")}}  # fmt: skip
_SHARED = {"image": "img@sha256:1", "files_sha256": dict.fromkeys(record.SWEEP_FILES, "1")}
_RESULT = {"bv_v": 12.0, "reached_v": 13.0, "nodes": {"si": 3}, "v": [0.0, 13.0], "i_n": [0.0, 1.1],
           "emax": [1.0, 2.0], "eox_max": [1.0, 2.0], "i_well": [0.0, 0.0], "probes": [[], []],
           "where_um": [None, [1.0, 0.1]]}  # fmt: skip


def _fake_runs(work, cases, pins=None, results=None):
    for name, params in cases.items():
        d = work / batch.safe(name)
        d.mkdir(parents=True)
        res = {**_RESULT, "params": params, **(results or {}).get(name, {})}
        (d / "result.json").write_text(json.dumps(res))
        (d / "pins.json").write_text(json.dumps({"case": name, **((pins or {}).get(name, _PINS))}))
    (work / "cases.json").write_text(json.dumps(cases))


def test_record_py_writes_and_refuses(tmp_path):
    cases = {"A|B|edge": {"vmax": 1.0}, "C@g0|B|edge": {"vmax": 2.0}}
    work, out = tmp_path / "work", tmp_path / "out.json"
    _fake_runs(work, cases)
    record.main([str(work), str(work / "cases.json"), str(out)])
    rec = json.loads(out.read_text())
    assert rec["schema"] == 2 and sorted(rec["cases"]) == sorted(cases)
    assert rec["pins"] == {**_SHARED, "commit": "c0ffee", "commits": ["c0ffee"]}
    assert rec["cases"]["A|B|edge"]["params_sha256"] == _sha(cases["A|B|edge"])
    # a batch restarted at another commit with the same image and sweep modules is accepted
    work = tmp_path / "work-commits"
    _fake_runs(work, cases, pins={"C@g0|B|edge": {**_PINS, "commit": "beef"}})
    record.main([str(work), str(work / "cases.json"), str(out)])
    pins = json.loads(out.read_text())["pins"]
    assert (pins["commit"], pins["commits"]) == (None, ["beef", "c0ffee"])
    for bad, match in (
        ({"image": "other"}, "image or simulation files differ"),
        ({"files_sha256": {**_PINS["files_sha256"], "sweep.py": "2"}}, "files differ"),
        ({"dirty": True}, "uncommitted changes"),
    ):
        pins = {"C@g0|B|edge": {**_PINS, **bad}}
        work = tmp_path / f"work-{next(iter(bad))}-{match[:4]}"
        _fake_runs(work, cases, pins=pins)
        with pytest.raises(SystemExit, match=match):
            record.main([str(work), str(work / "cases.json"), str(out)])
    work = tmp_path / "work-params"
    _fake_runs(work, cases, results={"A|B|edge": {"params": {"vmax": 9.0}}})
    with pytest.raises(SystemExit, match="parameters are not those"):
        record.main([str(work), str(work / "cases.json"), str(out)])
    work = tmp_path / "work-missing"
    _fake_runs(work, cases)
    (work / batch.safe("A|B|edge") / "result.json").unlink()
    with pytest.raises(SystemExit, match="not run"):
        record.main([str(work), str(work / "cases.json"), str(out)])
    record.main([str(work), str(work / "cases.json"), str(out), "--allow-missing"])
    assert json.loads(out.read_text())["not_converged"] == ["A|B|edge"]


def test_charon_record_writes_and_refuses(tmp_path):
    cases = {"A|B|edge": {"vmax": 1.0}, "D|B|edge": {"vmax": 2.0}}
    pins = {**_PINS, "charon_image": "charon@sha256:2"}
    res = {k: None for k in charon_record.KEEP} | {
        "integral": {k: [] for k in (*charon_record.KEEP_INTEGRAL, "where_um")}}  # fmt: skip
    devsim = {c: {"params_sha256": _sha(p), "bv_v": 10.0} for c, p in cases.items()}
    source = {"commit": "c0ffee", "path": "main.json", "sha256": "0"}
    work = tmp_path / "work"
    later = {"A|B|edge": pins, "D|B|edge": {**pins, "commit": "beef"}}
    _fake_runs(work, cases, pins=later, results=dict.fromkeys(cases, res))
    rec = charon_record.record(work, list(cases), devsim, source)
    assert rec["pins"] == {**_SHARED, "charon_image": pins["charon_image"],
                           "commits": ["beef", "c0ffee"]}  # fmt: skip
    assert rec["devsim_record"] == source and sorted(rec["cases"]) == sorted(cases)
    row = rec["cases"]["D|B|edge"]
    assert (row["commit"], row["devsim_bv_v"]) == ("beef", 10.0)
    assert tuple(sorted(row["charon_files_sha256"])) == charon_record.CHARON_FILES
    assert set(row["integral"]) == set(charon_record.KEEP_INTEGRAL)
    with pytest.raises(SystemExit, match="not run"):
        charon_record.record(work, [*cases, "E|B|edge"], devsim, source)
    other = {**devsim, "A|B|edge": {"params_sha256": "0", "bv_v": 1.0}}
    with pytest.raises(SystemExit, match="no case with these parameters"):
        charon_record.record(work, list(cases), other, source)
    for bad, match in (({"dirty": True}, "uncommitted"), ({"charon_image": "x"}, "differ")):
        work = tmp_path / f"work-{match[:4]}"
        both = {"A|B|edge": pins, "D|B|edge": {**pins, **bad}}
        _fake_runs(work, cases, pins=both, results=dict.fromkeys(cases, res))
        with pytest.raises(SystemExit, match=match):
            charon_record.record(work, list(cases), devsim, source)


def test_check_cases_and_the_diode_record(tmp_path):
    got = checks.check_cases()
    assert sorted(got) == sorted([*checks.BARE, *checks.ABUT_MESH])
    one, two = got["bare-f0.1-x128-v2"], got["bare-f0.1-f64-v2"]
    assert {k for k in one if one[k] != two[k]} == {"extended"}
    assert got["abut-f0.03"]["mesh"]["fine"] == _main_cases()["NT20|AL|edge"]["mesh"]["fine"]
    with pytest.raises(SystemExit, match="not run"):
        checks.diode_record(tmp_path)
    (tmp_path / "diode1d.json").write_text(json.dumps({k: {"bv_v": 1.0} for k in checks.DIODES}))
    (tmp_path / "pins.json").write_text(json.dumps({**_PINS, "dirty": True}))
    with pytest.raises(SystemExit, match="uncommitted"):
        checks.diode_record(tmp_path)
    (tmp_path / "pins.json").write_text(json.dumps(_PINS))
    assert checks.diode_record(tmp_path)["pins"] == _PINS


# --- the page -------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def hf():
    importorskip("matplotlib", reason="needs the docs dependency group")
    from gf180tcad import hvjunction_figures

    return hvjunction_figures


def _text(row: dict | None) -> str:
    if row is None:
        return "—"
    return f"> {row['reached_v']:.1f}" if row["bv_v"] is None else f"{row['bv_v']:.1f}"


def test_page_numbers_are_the_records(hf):
    """Every value of the page is a substitution, and every substitution of a case is that
    case's breakdown voltage to one decimal, from the last prediction record that holds it
    with the present parameters."""
    subs = hf.substitutions()
    page = PAGE.read_text("utf-8")
    used = set(re.findall(r"\{\{ (hvj_\w+) \}\}", page))
    assert used <= set(subs), sorted(used - set(subs))
    rows = _latest_rows()
    for case in {*_current_cases(), *hf.table_cases()}:
        assert subs[hf.key(case)] == _text(rows.get(case)), case
    fine, coarse = (rows.get(c, {}).get("bv_v") for c in hf.STEP_PAIR)
    assert subs["hvj_abut_pct"] == ("\u2014" if fine is None else f"{100 * (fine / 14.0 - 1):.0f}")
    both = fine is not None and coarse is not None
    assert subs["hvj_step_pair_pct"] == (
        f"{100 * abs(coarse / fine - 1):.1f}" if both else "\u2014")  # fmt: skip
    main = _main_cases()
    have = [c for c in main if c in rows]
    assert subs["hvj_n_cases"] == str(len(main))
    assert subs["hvj_n_absent"] == str(len(main) - len(have))
    assert subs["hvj_n_open"] == str(sum(rows[c]["bv_v"] is None for c in have))
    # the sharp corner: its 128-bit row breaks down, and the superseded 64-bit row of main.json
    # extrapolates to within 2 V of it
    sharp = _main_cases()[hf.OPEN_CORNER]
    assert sharp["extended"] is True and sharp["cyl"] and predict.MIN_CORNER < 2.0
    assert _main_cases()["NT20|BD|corner"]["extended"] is False
    old = _load("main")["cases"].get(hf.OPEN_CORNER)
    if old is not None and old["bv_v"] is None:
        slope = (old["i_n"][-1] - old["i_n"][-2]) / (old["v"][-1] - old["v"][-2])
        line = old["v"][-1] + (1 - old["i_n"][-1]) / slope
        assert subs["hvj_open_corner_v"] == f"{old['v'][-1]:.1f}"
        assert subs["hvj_open_corner_i"] == f"{old['i_n'][-1]:.3f}"
        assert subs["hvj_open_corner_extrapolated"] == f"{line:.0f}"
        new = rows.get(hf.OPEN_CORNER)
        if new is not None and new["bv_v"] is not None:
            assert old["params_sha256"] != new["params_sha256"]
            assert abs(line - new["bv_v"]) < 2.0


def test_page_tables_are_the_generated_rows(hf, tmp_path):
    """Each results table of the page is hvjunction_figures.table of its group (the command
    `python -m gf180tcad.hvjunction_figures tables` leaves the page unchanged), every simulated
    structure is in exactly one table, and every column is a process of predict.py."""
    page = PAGE.read_text("utf-8")
    for group in hf.TABLE_NAMES:
        assert hf.table(group) in page, group
    copy = tmp_path / "page.md"
    copy.write_text(page, "utf-8")
    assert hf.write_tables(copy) is False
    listed = [r for g in hf.COLUMNS for r in hf.rows() if hf.group(r) == g]
    assert sorted(listed) == sorted(hf.rows())
    main = {*predict.PROCESSES, *predict.NAT_ONLY}
    assert {p for cols in hf.COLUMNS.values() for p, _ in cols} <= main
    assert all(len(cols) <= 4 for cols in (*hf.COLUMNS.values(), *hf.FAMILY_COLUMNS.values()))
    family = {p for cols in hf.FAMILY_COLUMNS.values() for p, _ in cols}
    assert set(predict.FAMILY) <= family <= main | set(predict.FAMILY)
    assert hf.family_structures() == [k for k in predict.KEY if k in predict.STRUCTS]
    assert tuple(hf.PREDICTION_RECORDS) == PREDICTION_RECORDS
    assert hf.structures() == predict.STRUCTS
    assert tuple(hf.CHECKS) == tuple(checks.check_cases())
    assert tuple(hf.DIODES) == checks.DIODES
    assert set(hf.CHARON_CASES) == set(CHARON_RECORDS)
    assert set(hf.CHARON_CASES["charon"]) <= set(_current_cases())


def test_page_step_pair_is_one_section():
    """NT20 under AL and NW0 under BL, which the page calls one junction with two bias steps,
    differ only in the bias step and the end of the sweep."""
    got = _main_cases()
    a, b = got["NT20|AL|edge"], got["NW0|BL|edge"]
    assert {k for k in a if a[k] != b[k]} == {"vstep", "vmax"}
    assert a["mesh"]["fine"] == 0.03 and _main_cases()["NT20|BL|edge"]["mesh"]["fine"] == 0.1
    assert (a["vstep"], b["vstep"], a["vmax"], b["vmax"]) == (1.5, 3.0, 60.0, 150.0)
    assert not [c for c in got if c.split("|")[1] == "AD" and c.startswith("NT")]


def test_anchors_are_the_profiles(hf):
    """The anchors the page prints: the N-well's capacitance follows the diode model within
    4 % from 0 to 10 V only with the deep P layer under it, and the plane breakdown voltages
    are profile1d.plane_breakdown of the profiles."""
    pr = hvsite.DEFAULT_PROCESS
    y = np.linspace(0, 16e-4, 32001)

    def boxes(implants, shift=0.0):
        return [(g["peak"], (g["rp"] + shift) * UM, g["sy"] * UM) for g in implants]

    volts = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0])
    model = profile1d.model_c(volts, 1.4914e-8, 0.30525, 0.43905)
    bare, _ = profile1d.net(y, boxes(pr["nw"]), pr["sub"])
    under, _ = profile1d.net(y, boxes(pr["nw"]), pr["sub"], boxes(pr["deep_p"]))
    assert np.all(np.abs(profile1d.cv(y, under, volts) / model - 1) < 0.04)
    ratio = profile1d.cv(y, bare, volts) / model
    assert abs(ratio[0] - 1) < 0.01 and 0.80 < ratio[-1] < 0.86
    subs = hf.substitutions()
    assert subs["hvj_plane_nwd"] == f"{profile1d.plane_breakdown(y, under):.0f}"
    assert subs["hvj_plane_nw"] == f"{profile1d.plane_breakdown(y, bare):.0f}"
    for suffix, shift in hf.LAYER_SHIFTS_UM.items():
        moved, _ = profile1d.net(y, boxes(pr["nw"]), pr["sub"], boxes(pr["deep_p"], shift))
        assert subs[f"hvj_plane_nwd_{suffix}"] == f"{profile1d.plane_breakdown(y, moved):.0f}"
    assert subs["hvj_nwd_c10"] == f"{profile1d.cv(y, under, volts)[-1] * 1e7:.3f}"
    page = " ".join(PAGE.read_text("utf-8").split())
    assert "A layer 1 µm or 0.25 µm shallower" in page and "0.25 µm or 1 µm deeper" in page
    assert list(hf.LAYER_SHIFTS_UM.values()) == [-1.0, -0.25, 0.25, 1.0]


def test_page_states_the_code_constants():
    """The model constants the page types are the ones of the code."""
    page = " ".join(PAGE.read_text("utf-8").split())
    pr = hvsite.DEFAULT_PROCESS
    assert pr["sub"] == 3.56e15 and "uniform at 3.56e15 cm⁻³" in page
    assert pr["dnw"][0]["rp"] == 2.55 and "peaks 2.55 µm below" in page
    assert pr["deep_p"][0]["rp"] == 4.36 and "peaks 4.36 µm down" in page
    assert (predict.FAMILY["BLlo"]["sub"], predict.FAMILY["BLhi"]["sub"]) == (2e15, 5e15)
    assert "2e15 cm⁻³ or 5e15 cm⁻³" in page
    assert predict.PROCESSES["BLq"]["qf"] == 1e11 and "charge of 1e11 cm⁻²" in page
    assert predict.FAMILY["BLq3"]["qf"] == 3e11 and "charge to 3e11 cm⁻²" in page
    assert (hvsite.STI, hvsite.M1[1], hvsite.M1[1] - hvsite.M1[0]) == pytest.approx(
        (0.32, -0.86, 0.55))  # fmt: skip
    assert (hvsite.POLY[1], hvsite.POLY[1] - hvsite.POLY[0]) == pytest.approx((-0.01, 0.2))
    assert "meshed 10 nm above the trench oxide" in page
    assert predict.MIN_CORNER == 1.0 and "under 1 µm is simulated at 1 µm" in page
    assert (ionize.AN, ionize.BN) == (7.03e5, 1.231e6)
    assert "$a$ = 7.03e5 cm⁻¹ and $b$ = 1.231e6 V/cm" in page
    assert (ionize.AP_LO, ionize.BP_LO, ionize.E_SWITCH) == (1.582e6, 2.036e6, 4e5)
    assert "1.582e6 cm⁻¹ and 2.036e6 V/cm up to 4e5 V/cm" in page
    assert (ionize.AP_HI, ionize.BP_HI) == (6.71e5, 1.693e6)
    assert "6.71e5 cm⁻¹ and 1.693e6 V/cm" in page
    assert "falls under 2e3 V/cm" in page  # fieldline.trace's e_stop default
    assert fieldline.trace.__defaults__[0] == 2.0e3
    assert hf_anchor("nw")["cj0"] == 1.4914e-8 and hf_anchor("dnw_model_bv") == 30.48


def hf_anchor(key: str):
    from gf180tcad import hvjunction_figures

    return hvjunction_figures.ANCHORS[key]


def test_missing_records_give_dashes(hf, tmp_path):
    subs = hf.substitutions(tmp_path)
    assert subs["hvj_NT20_BL_edge"] == subs["hvj_abut_pct"] == hf.MISSING
    assert subs["hvj_n_absent"] == subs["hvj_n_cases"] and subs["hvj_n_open"] == "0"
    assert subs["hvj_p5_NR1S2_BL_edge"] == subs["hvj_open_corner_v"] == hf.MISSING
    assert subs["hvj_diode_1e17_analytic"] != hf.MISSING
    for palette in ("light", "dark"):
        for draw in hf.FIGURES.values():
            assert draw(palette, tmp_path).startswith(b"<?xml")


def test_figures_are_deterministic_and_embedded(hf):
    page = PAGE.read_text("utf-8")
    for name, draw in hf.FIGURES.items():
        assert draw("light") == draw("light"), name
        assert draw("light") != draw("dark"), name
        for palette in ("light", "dark"):
            assert f"/_generated/hv-junction/{name}-{palette}.svg" in page, name


def test_figure_points_are_the_structures(hf):
    """Each graph's x values are the drawn dimensions of structures.json."""
    st = predict.STRUCTS
    for pts in hf.pwell_points().values():
        assert all(st[n]["pwell_gap"] == x for x, n in pts)
    for layer, pts in hf.plate_points().items():
        assert all(st[n]["plates"] == {layer: x} for x, n in pts[1:]) and pts[0] == (0.0, "NT20")
    rings = hf.ring_points()
    assert all(len(st[n]["rings"]) == x for x, n in rings["count"])
    assert all(st[n]["rings"] == [[x, 2.0]] for x, n in rings["gap"])
    for pts in hf.corner_points().values():
        assert all(max(st[n]["corner"], predict.MIN_CORNER) == x for x, n in pts)
    boxes = hf.section_boxes()
    assert {b[0] for b in boxes["boxes"]} == {"n-well", "ring", "p-well", "n+", "p+"}


# --- the sandbox rerun ----------------------------------------------------------------------------


@pytest.mark.sandbox
def test_rerun_reproduces_the_record(tmp_path):
    """A rerun of one short case of the record RERUN_RECORD in the sandbox gives its breakdown
    voltage within RERUN_TOL_V and its bias points exactly (minutes, one 8 GiB container)."""
    import run as runner

    params = _main_cases()[RERUN_CASE]
    want = _latest_rows().get(RERUN_CASE)
    if RERUN_RECORD not in _present() or want != _load(RERUN_RECORD)["cases"].get(RERUN_CASE):
        pytest.skip(f"{RERUN_RECORD} does not hold the latest row of {RERUN_CASE}")
    work = tmp_path / "work"
    work.mkdir()
    (work / "params.json").write_text(json.dumps(params, indent=1))
    rc = runner.run(work, "sweep.py", ["params.json", "result.json"])
    assert rc == 0, (work / "run.log").read_text()[-2000:]
    got = json.loads((work / "result.json").read_text())
    assert got["v"] == want["v"] and got["nodes"] == want["nodes"]
    assert abs(got["bv_v"] - want["bv_v"]) < RERUN_TOL_V, (got["bv_v"], want["bv_v"])
    assert runner.image() == _load(RERUN_RECORD)["pins"]["image"]
