# SPDX-License-Identifier: Apache-2.0
"""The high-voltage junction experiment (experiments/hv-junction/): the physics of its host
modules, what each committed record pins, the record writers' refusals, and the numbers and
figures of docs/results/hv-junction.md against the records.

A record under results/hv-junction/ is tested when it is committed: main, supp, family and
checks (record.py), diodes (checks.py) and charon (charon_record.py)."""

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
SWEEP_RECORDS = ("main", "supp", "family", "checks")
ALL_RECORDS = (*SWEEP_RECORDS, "diodes", "charon")
# The case the sandbox test reruns (297 s in the main batch) and its tolerance in volts.
RERUN_CASE, RERUN_TOL_V = "NW0|B|edge", 1e-6


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
    got = predict.cases(sorted(predict.STRUCTS), predict.PROCESSES)
    nat = [
        n for n, st in predict.STRUCTS.items() if st["nat_gap"] is not None and st["nat_gap"] > 0
    ]
    got.update(predict.cases(sorted(nat), predict.NAT_ONLY))
    return got


def _supp_cases() -> dict:
    """The cases of predict.py's set "supp"."""
    deep = sorted(n for n, st in predict.STRUCTS.items() if st["kind"] == "dnw")
    ring = sorted(n for n, st in predict.STRUCTS.items() if st["rings"])
    got = predict.cases(deep, {k: predict.PROCESSES[k] for k in ("A", "Aq")})
    got.update(predict.cases(ring, {"Bq": predict.PROCESSES["Bq"]}))
    slow = predict.cases(["NR5_2"], {"B": predict.PROCESSES["B"]})
    for p in slow.values():
        p["extended"] = True
    got.update(slow)
    return got


def _expected(name: str) -> dict:
    return {
        "main": _main_cases,
        "supp": _supp_cases,
        "family": lambda: predict.cases(predict.KEY, predict.FAMILY),
        "checks": checks.check_cases,
    }[name]()


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
    """Sheet resistance 800 to 1200 ohm/sq (electrical specification 5.1) and the zero-bias
    capacitance of diode_nw2ps_06v0, 1.4914e-4 F/m^2, within 15 %."""
    pr = hvsite.DEFAULT_PROCESS
    y = np.linspace(0, 12e-4, 24001)
    wells = [(g["peak"], g["rp"] * UM, g["sy"] * UM) for g in pr["nw"]]
    n, total = profile1d.net(y, wells, pr["sub"])
    assert 800 < profile1d.sheet_resistance(y, n, total) < 1200
    c0 = profile1d.cv(y, n, np.array([0.0]))[0]
    assert abs(c0 - 1.4914e-8) / 1.4914e-8 < 0.15, c0


def _acceptor_starts(p: dict) -> list[float]:
    return sorted(b["x0"] for b in p["pfield"] if b["peak"] < 1e19)


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
    assert poly["y1"] == 0.0 and m1["y1"] == -0.86
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


@pytest.mark.parametrize("name", _present())
def test_record_pins_what_the_runs_used(name):
    """The record's pins are checked against the checkout at the record's own commit: the
    commit is an ancestor of HEAD, the image is the one docker/ named then and names now, and
    files_sha256 lists every file of the experiment at that commit with its sha256 there."""
    rec = _load(name)
    pins = rec["pins"]
    assert rec["schema"] == 1 and pins["dirty"] is False
    want = {"commit", "dirty", "files_sha256", "image"} | (
        {"charon_image"} if name == "charon" else set()
    )
    assert set(pins) == want
    commit = pins["commit"]
    assert _git("cat-file", "-e", commit + "^{commit}").returncode == 0, commit
    assert _git("merge-base", "--is-ancestor", commit, "HEAD").returncode == 0, commit
    for key, path in (("image", "docker/TCAD_DEV_IMAGE"), ("charon_image", "docker/CHARON_IMAGE")):
        if key in pins:
            then = _git("show", f"{commit}:{path}").stdout.decode().split()[0]
            assert pins[key] == then == (REPO_ROOT / path).read_text("utf-8").split()[0]
    tree = (
        _git("ls-tree", "--name-only", commit, "experiments/hv-junction/").stdout.decode().split()
    )
    assert sorted(pins["files_sha256"]) == sorted(t.rsplit("/", 1)[1] for t in tree)
    for file, digest in pins["files_sha256"].items():
        blob = _git("show", f"{commit}:experiments/hv-junction/{file}")
        assert blob.returncode == 0, file
        assert hashlib.sha256(blob.stdout).hexdigest() == digest, file


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


@pytest.mark.parametrize("name", _present(SWEEP_RECORDS))
def test_record_cases_are_the_case_set(name):
    """The record's cases and the ones its runs left out are the case set, and a row's
    parameters are the ones the case set gives now. The main record's deep N-wells under A and
    Aq are the exception: the supp set reruns them with other parameters."""
    rec = _load(name)
    want = _expected(name)
    assert set(rec["cases"]) | set(rec["not_converged"]) <= set(want)
    other = {c for c, row in rec["cases"].items() if row["params_sha256"] != _sha(want[c])}
    if name == "main":
        assert other <= set(_supp_cases()), sorted(other - set(_supp_cases()))
        assert all(predict.STRUCTS[c.split("|")[0].split("@")[0]]["kind"] == "dnw" for c in other)
    else:
        assert not other, sorted(other)


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


def test_charon_record_agrees_with_devsim():
    """Charon's integral on its own potential lies within 1 % of DEVSIM's breakdown voltage."""
    if "charon" not in _present():
        pytest.skip("results/hv-junction/charon.json is not committed")
    rec = _load("charon")
    devsim = {**_load("main")["cases"]}
    for case, row in rec["cases"].items():
        assert set(row) == {"params_sha256", "integral", *charon_record.KEEP}, case
        assert row["params_sha256"] == devsim[case]["params_sha256"], case
        assert abs(row["bv_integral_v"] / devsim[case]["bv_v"] - 1) < 0.01, case


# --- the record writers refuse what they should ---------------------------------------------------

_PINS = {"commit": "c0ffee", "dirty": False, "image": "img@sha256:1", "files_sha256": {"a.py": "1"}}
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
    assert rec["pins"] == _PINS and sorted(rec["cases"]) == sorted(cases)
    assert rec["cases"]["A|B|edge"]["params_sha256"] == _sha(cases["A|B|edge"])
    for bad, match in (
        ({"commit": "other"}, "pins differ"),
        ({"dirty": True}, "uncommitted changes"),
    ):
        pins = {"C@g0|B|edge": {**_PINS, **bad}}
        work = tmp_path / f"work-{match[:4]}"
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
    work = tmp_path / "work"
    _fake_runs(work, cases, pins=dict.fromkeys(cases, pins), results=dict.fromkeys(cases, res))
    rec = charon_record.record(work, cases, list(cases))
    assert rec["pins"] == pins and sorted(rec["cases"]) == sorted(cases)
    assert set(rec["cases"]["A|B|edge"]["integral"]) == set(charon_record.KEEP_INTEGRAL)
    with pytest.raises(SystemExit, match="not run"):
        charon_record.record(work, {**cases, "E|B|edge": {}}, [*cases, "E|B|edge"])
    for bad, match in (({"dirty": True}, "uncommitted"), ({"charon_image": "x"}, "pins differ")):
        work = tmp_path / f"work-{match[:4]}"
        both = {"A|B|edge": pins, "D|B|edge": {**pins, **bad}}
        _fake_runs(work, cases, pins=both, results=dict.fromkeys(cases, res))
        with pytest.raises(SystemExit, match=match):
            charon_record.record(work, cases, list(cases))
    work = tmp_path / "work-nopin"
    _fake_runs(work, cases, results=dict.fromkeys(cases, res))  # DEVSIM pins only
    with pytest.raises(SystemExit, match=r"pins\.json holds"):
        charon_record.record(work, cases, list(cases))


def test_check_cases_and_the_diode_record(tmp_path):
    got = checks.check_cases()
    assert sorted(got) == sorted([*checks.BARE, *checks.ABUT_MESH])
    one, two = got["bare-f0.1-x128-v2"], got["bare-f0.1-f64-v2"]
    assert {k for k in one if one[k] != two[k]} == {"extended"}
    assert got["abut-f0.07"]["mesh"]["fine"] == _main_cases()["NT20|A|edge"]["mesh"]["fine"]
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
    case's breakdown voltage in the committed records to one decimal (supp before main)."""
    subs = hf.substitutions()
    page = PAGE.read_text("utf-8")
    used = set(re.findall(r"\{\{ (hvj_\w+) \}\}", page))
    assert used <= set(subs), sorted(used - set(subs))
    rows = {}
    for name in ("main", "supp", "family"):
        if name in _present():
            rows.update(_load(name)["cases"])
    assert rows == hf.cases()
    for case in {*rows, *hf.table_cases()}:
        assert subs[hf.key(case)] == _text(rows.get(case)), case
    assert subs["hvj_n_main"] == str(len(_load("main")["cases"]))
    assert subs["hvj_n_main_missing"] == str(len(_load("main")["not_converged"]))
    fine, coarse = (rows[c]["bv_v"] for c in hf.MESH_PAIR)
    assert subs["hvj_abut_pct"] == f"{100 * (fine / 14.0 - 1):.0f}"
    assert subs["hvj_mesh_pair_pct"] == f"{100 * (coarse / fine - 1):.0f}"
    for name, short in (("1e+15", "1e15"), ("1e+16", "1e16"), ("1e+17", "1e17")):
        assert subs[f"hvj_diode_{short}_analytic"] == f"{_abrupt_bv(float(name)):.2f}"


def test_page_tables_are_the_generated_rows(hf):
    """Each results table of the page is hvjunction_figures.table of its group, so every
    simulated structure is in exactly one table."""
    page = PAGE.read_text("utf-8")
    groups = [*hf.COLUMNS, *hf.FAMILY_COLUMNS]
    for group in groups:
        assert hf.table(group) in page, group
    listed = [r for g in hf.COLUMNS for r in hf.rows() if hf.group(r) == g]
    assert sorted(listed) == sorted(hf.rows())
    assert tuple(hf.FAMILY_STRUCTURES) == tuple(predict.KEY)
    assert set(hf.FAMILY) == set(predict.FAMILY) and set(hf.PROCESSES) == {
        *predict.PROCESSES, *predict.NAT_ONLY}  # fmt: skip
    assert hf.structures() == predict.STRUCTS
    assert tuple(hf.CHECKS) == tuple(checks.check_cases())
    assert tuple(hf.DIODES) == checks.DIODES


def test_page_mesh_pair_is_one_section():
    """NT20 under A and NW0 under B, which the page calls one junction on two meshes, differ
    only in the mesh, the bias step and the end of the sweep."""
    got = _main_cases()
    a, b = got["NT20|A|edge"], got["NW0|B|edge"]
    assert {k for k in a if a[k] != b[k]} == {"mesh", "vstep", "vmax"}
    assert (a["mesh"]["fine"], b["mesh"]["fine"]) == (0.07, 0.1)
    assert (a["vstep"], b["vstep"], a["vmax"], b["vmax"]) == (1.5, 3.0, 60.0, 150.0)


def test_page_states_the_code_constants():
    """The model constants the page types are the ones of the code."""
    page = " ".join(PAGE.read_text("utf-8").split())
    pr = hvsite.DEFAULT_PROCESS
    assert pr["sub"] == 3.5e15 and "uniform at 3.5e15 cm⁻³" in page
    assert (predict.FAMILY["Blo"]["sub"], predict.FAMILY["Bhi"]["sub"]) == (2e15, 5e15)
    assert "2e15 cm⁻³ (lo) or 5e15 cm⁻³ (hi)" in page
    assert predict.PROCESSES["Bq"]["qf"] == 1e11 and "charge of 1e11 cm⁻²" in page
    assert predict.FAMILY["Bq3"]["qf"] == 3e11 and "charge of 3e11 cm⁻²" in page
    (deep,) = predict.FAMILY["Bdp"]["deep_p"]
    assert (deep["peak"], deep["rp"]) == (4e16, 5.0) and "peak at 4e16 cm⁻³, 5 µm below" in page
    assert (hvsite.STI, hvsite.M1[1], hvsite.POLY[0], hvsite.M1[1] - hvsite.M1[0]) == pytest.approx(
        (0.32, -0.86, -0.2, 0.55))  # fmt: skip
    assert predict.MIN_CORNER == 2.0 and "under 2 µm is simulated at 2 µm" in page
    assert (ionize.AN, ionize.BN) == (7.03e5, 1.231e6)
    assert "$a$ = 7.03e5 cm⁻¹ and $b$ = 1.231e6 V/cm" in page
    assert (ionize.AP_LO, ionize.BP_LO, ionize.E_SWITCH) == (1.582e6, 2.036e6, 4e5)
    assert "1.582e6 cm⁻¹ and 2.036e6 V/cm up to 4e5 V/cm" in page
    assert (ionize.AP_HI, ionize.BP_HI) == (6.71e5, 1.693e6)
    assert "6.71e5 cm⁻¹ and 1.693e6 V/cm" in page
    assert hf_anchor("cj0") == 1.4914e-8 and hf_anchor("dnw_model_bv") == 30.48


def hf_anchor(key: str) -> float:
    from gf180tcad import hvjunction_figures

    return hvjunction_figures.ANCHORS[key]


def test_missing_records_give_dashes(hf, tmp_path):
    subs = hf.substitutions(tmp_path)
    assert subs["hvj_NT20_B_edge"] == subs["hvj_n_main"] == subs["hvj_abut_pct"] == hf.MISSING
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
    """A rerun of one short case of the main record in the sandbox gives its breakdown voltage
    within RERUN_TOL_V and its bias points exactly (5 minutes, one 8 GiB container)."""
    import run as runner

    want = _load("main")["cases"][RERUN_CASE]
    params = _main_cases()[RERUN_CASE]
    assert _sha(params) == want["params_sha256"]
    work = tmp_path / "work"
    work.mkdir()
    (work / "params.json").write_text(json.dumps(params, indent=1))
    rc = runner.run(work, "sweep.py", ["params.json", "result.json"])
    assert rc == 0, (work / "run.log").read_text()[-2000:]
    got = json.loads((work / "result.json").read_text())
    assert got["v"] == want["v"] and got["nodes"] == want["nodes"]
    assert abs(got["bv_v"] - want["bv_v"]) < RERUN_TOL_V, (got["bv_v"], want["bv_v"])
    assert runner.image() == _load("main")["pins"]["image"]
