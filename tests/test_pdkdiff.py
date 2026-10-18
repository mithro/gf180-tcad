# SPDX-License-Identifier: Apache-2.0
"""The secondary-PDK comparison (``python -m gf180tcad.pdkdiff``): open_pdks ``d658698``.

Unit tests use synthetic trees and a fake sandbox, so they need no Docker. The committed tree
``results/spice-pdk-d658698`` is checked against the current code and the committed reference.
"""

import hashlib
import json
from pathlib import Path

import pytest

from gf180tcad import io, manifest, pdkdiff, reference, sandbox
from gf180tcad.devices import DEVICES
from gf180tcad.reference import Job

REPO = Path(__file__).resolve().parents[1]
TREE = REPO / "results" / "spice-pdk-d658698"
SPICE = REPO / "results" / "spice"
# generator_sha256 of results/spice/provenance.json when this comparison was added (main a7dff78).
# pdkdiff must not change the SPICE generator: reference.py is reused, never edited.
BASE_GENERATOR_SHA256 = "f7aa3188c9e565eb7fb8dda263cbc69716390f37fd8d1fb5ae186caf46a41c62"


def _metrics_tree(root: Path, jobs: dict[str, dict[str, float]]) -> Path:
    """``root/<device>/<gid>/metrics.json`` (plus a cv.csv) for each ``device/gid`` of ``jobs``."""
    for rel, m in jobs.items():
        d = root / rel
        d.mkdir(parents=True)
        device, gid = rel.split("/")
        io.write_json(d / "metrics.json", {"device": device, "geometry_id": gid, "metrics": m})
        io.write_csv(d / "cv.csv", {"vg": [0.0, 1.0], "cgg": [1e-15, 2e-15]}, {"sweep": "cv"})
    return root


A = {
    "nfet_05v0/w10p0_l0p60": {"vt_lin_cc": 0.69, "idsat_ua_per_um": 500.0, "ioff_pa_per_um": 0.0},
    "pfet_05v0/w10p0_l0p50": {"vt_lin_cc": -0.83, "idsat_ua_per_um": 240.0, "ioff_pa_per_um": 1.0},
}


# --- compare -------------------------------------------------------------------------------


def test_pdkdiff_zero_for_identical(tmp_path):
    a = _metrics_tree(tmp_path / "a", A)
    b = _metrics_tree(tmp_path / "b", A)
    res = pdkdiff.compare(a, b)
    assert res["identical"] is True
    assert res["only_in_a"] == [] and res["only_in_b"] == []
    assert sorted(res["jobs"]) == sorted(A)
    for rel, job in res["jobs"].items():
        assert job["files_identical"] is True
        assert sorted(job["metrics"]) == sorted(A[rel])
        for name, m in job["metrics"].items():
            assert m == {"a": A[rel][name], "b": A[rel][name], "delta": 0.0, "rel": 0.0}
    assert res["max_abs_rel"] == {"idsat_ua_per_um": 0.0, "ioff_pa_per_um": 0.0, "vt_lin_cc": 0.0}
    json.dumps(res, allow_nan=False)  # writable with io.write_json


def test_pdkdiff_reports_metric_delta(tmp_path):
    b_jobs = {k: dict(v) for k, v in A.items()}
    b_jobs["nfet_05v0/w10p0_l0p60"]["idsat_ua_per_um"] = 505.0
    b_jobs["pfet_05v0/w10p0_l0p50"]["vt_lin_cc"] = -0.85
    b_jobs["nfet_05v0/w10p0_l0p60"]["ioff_pa_per_um"] = 0.5  # a = 0: no relative delta
    a = _metrics_tree(tmp_path / "a", A)
    b = _metrics_tree(tmp_path / "b", b_jobs)
    res = pdkdiff.compare(a, b)
    assert res["identical"] is False
    n = res["jobs"]["nfet_05v0/w10p0_l0p60"]["metrics"]
    assert n["idsat_ua_per_um"] == {"a": 500.0, "b": 505.0, "delta": 5.0, "rel": 0.01}
    assert n["ioff_pa_per_um"]["delta"] == 0.5 and n["ioff_pa_per_um"]["rel"] is None
    assert n["vt_lin_cc"]["delta"] == 0.0
    p = res["jobs"]["pfet_05v0/w10p0_l0p50"]["metrics"]["vt_lin_cc"]
    assert p["delta"] == pytest.approx(-0.02) and p["rel"] == pytest.approx(-0.02 / 0.83)
    assert res["max_abs_rel"]["idsat_ua_per_um"] == 0.01
    assert res["max_abs_rel"]["vt_lin_cc"] == pytest.approx(0.02 / 0.83)
    assert res["max_abs_rel"]["ioff_pa_per_um"] is None  # an undefined relative delta wins
    # the metric files differ, so the job's files are not byte-identical
    assert res["jobs"]["nfet_05v0/w10p0_l0p60"]["files_identical"] is False


def test_pdkdiff_reports_file_difference_with_equal_metrics(tmp_path):
    a = _metrics_tree(tmp_path / "a", A)
    b = _metrics_tree(tmp_path / "b", A)
    (b / "nfet_05v0/w10p0_l0p60/cv.csv").write_bytes(b"other\n")
    res = pdkdiff.compare(a, b)
    assert res["jobs"]["nfet_05v0/w10p0_l0p60"]["files_identical"] is False
    assert res["jobs"]["pfet_05v0/w10p0_l0p50"]["files_identical"] is True
    assert res["identical"] is False


def test_pdkdiff_reports_missing_jobs_and_metrics(tmp_path):
    a = _metrics_tree(tmp_path / "a", A)
    b_jobs = {"nfet_05v0/w10p0_l0p60": {"vt_lin_cc": 0.69, "idsat_ua_per_um": 500.0}}
    b = _metrics_tree(tmp_path / "b", b_jobs)
    res = pdkdiff.compare(a, b)
    assert res["only_in_a"] == ["pfet_05v0/w10p0_l0p50"] and res["only_in_b"] == []
    assert res["jobs"]["nfet_05v0/w10p0_l0p60"]["metrics_only_in_a"] == ["ioff_pa_per_um"]
    assert res["identical"] is False


def test_pdkdiff_compare_empty_tree_rejected(tmp_path):
    (tmp_path / "a").mkdir()
    b = _metrics_tree(tmp_path / "b", A)
    with pytest.raises(ValueError, match="no metrics.json"):
        pdkdiff.compare(tmp_path / "a", b)


# --- the SPICE generator stays frozen ------------------------------------------------------


def test_reference_py_untouched():
    """pdkdiff reuses reference.py unmodified: the SPICE provenance does not move."""
    assert reference.generator_sha256() == BASE_GENERATOR_SHA256
    committed = json.loads((SPICE / "provenance.json").read_bytes())["generator_sha256"]
    assert committed == BASE_GENERATOR_SHA256
    assert "gf180tcad.pdkdiff" not in reference.GENERATOR_MODULES


def test_plan_is_the_reference_plan_at_tt_ngspice():
    want = reference.plan_jobs(("ngspice",), ("typical",), tuple(DEVICES))
    assert pdkdiff.plan() == want
    assert len(want) == sum(len(d.geometries) for d in DEVICES.values())


def test_job_patches_only_the_pdk_lookup(inside, tmp_path, monkeypatch):
    """The in-image job is reference.run_job with the PDK lookup replaced, then restored."""
    pdk_root = _fake_pdk(tmp_path / "pdk")
    pins = tmp_path / "pins.sha256"
    pins.write_text(_pins_text(pdk_root), encoding="utf-8")
    versions = tmp_path / "versions.json"
    info = pdkdiff.locate(pdk_root=pdk_root)
    versions.write_text(json.dumps(_versions_of(info)), encoding="utf-8")
    seen = []
    original = reference._image_pdk

    def fake_run_job(job, out):
        seen.append((job, Path(out), reference._image_pdk()))

    monkeypatch.setattr(reference, "run_job", fake_run_job)
    job = pdkdiff.plan()[0]
    pdkdiff.run_pdk_job(job, tmp_path / "out", pdk_root, versions=versions, pins=pins)
    assert seen == [(job, tmp_path / "out", info)]
    assert reference._image_pdk is original


def test_job_refuses_unpinned_pdk(inside, tmp_path, monkeypatch):
    pdk_root = _fake_pdk(tmp_path / "pdk")
    pins = tmp_path / "pins.sha256"
    pins.write_text(_pins_text(pdk_root), encoding="utf-8")
    versions = tmp_path / "versions.json"
    versions.write_text(json.dumps(_versions_of(pdkdiff.locate(pdk_root=pdk_root))), "utf-8")
    (pdk_root / "gf180mcuD/libs.tech/ngspice/sm141064.spice").write_text("changed\n")
    monkeypatch.setattr(reference, "run_job", lambda job, out: pytest.fail("ran"))
    with pytest.raises(pdkdiff.PinMismatch, match="sm141064.spice"):
        pdkdiff.run_pdk_job(pdkdiff.plan()[0], tmp_path / "o", pdk_root, versions, pins)


def test_job_outside_sandbox_refused(tmp_path, monkeypatch):
    monkeypatch.delenv(sandbox.IN_SANDBOX_ENV, raising=False)
    with pytest.raises(RuntimeError, match="inside the sandbox"):
        pdkdiff.run_pdk_job(pdkdiff.plan()[0], tmp_path, tmp_path)


# --- pins ----------------------------------------------------------------------------------

_FILES = (
    "gf180mcuD/.config/nodeinfo.json",
    "gf180mcuD/libs.tech/ngspice/design.ngspice",
    "gf180mcuD/libs.tech/ngspice/sm141064.ngspice",
    "gf180mcuD/libs.tech/ngspice/sm141064.spice",
    "gf180mcuD/libs.tech/xyce/design.xyce",
    "gf180mcuD/libs.tech/xyce/sm141064.xyce",
)


def _fake_pdk(root: Path) -> Path:
    for rel in _FILES:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith("nodeinfo.json"):
            p.write_text(json.dumps({"commit": {"open_pdks": "d" * 40}}), encoding="utf-8")
        else:
            p.write_text(f"* {rel}\n", encoding="utf-8")
    return root


def _pins_text(root: Path) -> str:
    return "".join(
        f"{hashlib.sha256((root / r).read_bytes()).hexdigest()}  {r}\n" for r in sorted(_FILES)
    )


def _versions_of(info) -> dict:
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    return {
        "gf180mcu_variant": info.variant,
        "open_pdks_commit": info.open_pdks_commit,
        "sm141064_ngspice_sha256": sha(info.ngspice_lib),
        "design_ngspice_sha256": sha(info.ngspice_design),
        "sm141064_xyce_sha256": sha(info.xyce_lib),
    }


def test_load_pins_round_trip(tmp_path):
    root = _fake_pdk(tmp_path / "pdk")
    p = tmp_path / "pins"
    p.write_text(_pins_text(root), encoding="utf-8")
    pins = pdkdiff.load_pins(p)
    assert sorted(pins) == sorted(_FILES)
    assert pdkdiff.pin_problems(root, pins) == []


@pytest.mark.parametrize(
    "text, match",
    [
        ("", "no files"),
        ("abc  x\n", "malformed"),
        ("a" * 64 + "  ../x\n", "relative"),
        ("a" * 64 + "  /x\n", "relative"),
        ("a" * 64 + "  x\n" + "b" * 64 + "  x\n", "duplicate"),
    ],
)
def test_load_pins_rejects_bad_files(tmp_path, text, match):
    p = tmp_path / "pins"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        pdkdiff.load_pins(p)


def test_pin_problems_lists_changed_and_missing(tmp_path):
    root = _fake_pdk(tmp_path / "pdk")
    pins = {r: hashlib.sha256((root / r).read_bytes()).hexdigest() for r in _FILES}
    (root / _FILES[1]).write_text("x\n")
    (root / _FILES[2]).unlink()
    probs = pdkdiff.pin_problems(root, pins)
    assert len(probs) == 2
    assert any(_FILES[1] in p and "sha256" in p for p in probs)
    assert any(_FILES[2] in p and "missing" in p for p in probs)


def test_copy_pinned_copies_only_pinned_files(tmp_path):
    src = _fake_pdk(tmp_path / "src")
    (src / "gf180mcuD/libs.ref").mkdir()
    (src / "gf180mcuD/libs.ref/extra.gds").write_text("x")
    pins = {r: hashlib.sha256((src / r).read_bytes()).hexdigest() for r in _FILES}
    dst = tmp_path / "dst"
    pdkdiff.copy_pinned(src, dst, pins)
    got = sorted(p.relative_to(dst).as_posix() for p in dst.rglob("*") if p.is_file())
    assert got == sorted(_FILES)
    (src / _FILES[0]).write_text("tampered")
    with pytest.raises(pdkdiff.PinMismatch):
        pdkdiff.copy_pinned(src, tmp_path / "dst2", pins)


def test_committed_pins_match_versions_json():
    pins = pdkdiff.load_pins(pdkdiff.PINS)
    v = json.loads(pdkdiff.VERSIONS.read_text(encoding="utf-8"))
    base = f"{v['gf180mcu_variant']}/libs.tech/"
    assert pins[base + "ngspice/sm141064.ngspice"] == v["sm141064_ngspice_sha256"]
    assert pins[base + "ngspice/design.ngspice"] == v["design_ngspice_sha256"]
    assert pins[base + "xyce/sm141064.xyce"] == v["sm141064_xyce_sha256"]
    assert v["open_pdks_commit"].startswith("d658698bd8bc") and len(v["open_pdks_commit"]) == 40
    # every model file ngspice can reach from sm141064.ngspice is pinned
    for name in ("sm141064.spice", "sm141064_mim.spice", "smbb000149.spice"):
        assert base + "ngspice/" + name in pins


# --- card sections and values --------------------------------------------------------------

CARD = """\
* header
.lib typical
.param nfet_06v0_tox=0
.lib 'sm141064.spice' nfet_06v0_t
.endl typical
.lib nfet_06v0_t
.model nfet_06v0.0 nmos
+ toxe='1.52e-008+nfet_06v0_tox'
+ vth0=0.67314
+ u0='0.0525*(1+0)'
.endl nfet_06v0_t
.lib res
.model fox_sub c
+ cox=8.85e-05
.endl res
"""


def test_lib_sections():
    s = pdkdiff.lib_sections(CARD)
    assert list(s) == ["typical", "nfet_06v0_t", "res"]
    assert s["res"][0] == 12 and s["res"][1] == [
        ".lib res",
        ".model fox_sub c",
        "+ cox=8.85e-05",
        ".endl res",
    ]


def test_section_diff():
    b = CARD.replace(".model fox_sub c\n+ cox=8.85e-05", ".model fox_sub c cj=8.85e-05")
    d = pdkdiff.section_diff(CARD, b)
    assert d == {"changed": ["res"], "only_in_a": [], "only_in_b": [], "same": 2}
    assert pdkdiff.section_diff(CARD, CARD)["changed"] == []


def test_model_values():
    tt = pdkdiff.tt_params(CARD)
    assert tt == {"nfet_06v0_tox": 0.0}
    v = pdkdiff.model_values(CARD, "nfet_06v0_t", "nfet_06v0.0", ("toxe", "vth0", "u0", "ndep"), tt)
    assert v["toxe"] == {"expr": "1.52e-008+nfet_06v0_tox", "line": 8, "tt": 1.52e-08}
    assert v["vth0"] == {"expr": "0.67314", "line": 9, "tt": 0.67314}
    assert v["u0"] == {"expr": "0.0525*(1+0)", "line": 10, "tt": None}  # not a +/* expression
    assert v["ndep"] is None  # not set on this card


# --- host orchestration (fake sandbox) -----------------------------------------------------


def test_run_network_only_in_fetch_and_layout(tmp_path):
    src = _fake_pdk(tmp_path / "fetched")
    pins_file = tmp_path / "pins"
    pins_file.write_text(_pins_text(src), encoding="utf-8")
    pins = pdkdiff.load_pins(pins_file)
    ref = _metrics_tree(
        tmp_path / "ref", {f"{j.device}/{j.geometry}": {"m": 1.0} for j in pdkdiff.plan()}
    )
    calls = []

    def fake_sb(cmd, *, out_dir, network=False, **kw):
        calls.append((cmd, network))
        out_dir = Path(out_dir)
        if cmd[0] == "ciel":
            dest = out_dir / "pdk" / "ciel" / "gf180mcu" / "versions" / cmd[-1]
            pdkdiff.copy_pinned(src, dest, pins)
        elif "cards-job" in cmd:
            assert (out_dir / "pdk" / _FILES[2]).is_file()
            io.write_json(out_dir / "out" / pdkdiff.CARDS_NAME, {"cards": {}})
            (out_dir / "out" / "sm141064.ngspice.diff").write_text("")
            (out_dir / "out" / "sm141064.xyce.diff").write_text("")
        else:
            assert "job" in cmd and (out_dir / "pdk" / _FILES[2]).is_file()
            d = out_dir / "out"
            for name in reference.expected_files("ngspice"):
                if name == "metrics.json":
                    io.write_json(d / name, {"metrics": {"m": 1.0}})
                else:
                    (d / name).write_text("x\n")

    out = tmp_path / "result"
    rc = pdkdiff.run(
        out, scratch_root=tmp_path / "scratch", jobs_n=2, sb=fake_sb, pins_file=pins_file,
        reference_dir=ref, commit="d" * 40, log=lambda s: None,
    )  # fmt: skip
    assert rc == 0
    assert [n for c, n in calls if n] == [True] and calls[0][0][0] == "ciel"
    assert all(not n for c, n in calls[1:])
    assert len(calls) == 1 + 1 + len(pdkdiff.plan())
    for j in pdkdiff.plan():
        assert sorted(p.name for p in (out / j.relpath).iterdir()) == list(
            reference.expected_files("ngspice")
        )
    for name in (pdkdiff.CARDS_NAME, pdkdiff.COMPARISON_NAME, "provenance.json"):
        assert (out / name).is_file()
    assert list((tmp_path / "scratch").iterdir()) == []  # scratch removed on success


def test_run_failure_keeps_out_and_scratch(tmp_path):
    src = _fake_pdk(tmp_path / "fetched")
    pins_file = tmp_path / "pins"
    pins_file.write_text(_pins_text(src), encoding="utf-8")
    pins = pdkdiff.load_pins(pins_file)

    def fake_sb(cmd, *, out_dir, network=False, **kw):
        if cmd[0] == "ciel":
            pdkdiff.copy_pinned(src, Path(out_dir) / "pdk/ciel/gf180mcu/versions" / cmd[-1], pins)
        else:
            raise RuntimeError("boom")

    out = tmp_path / "result"
    out.mkdir()
    (out / "keep").write_text("old")
    (out / "provenance.json").write_text("{}")
    rc = pdkdiff.run(
        out, scratch_root=tmp_path / "scratch", jobs_n=2, sb=fake_sb, pins_file=pins_file,
        reference_dir=tmp_path, commit="d" * 40, log=lambda s: None,
    )  # fmt: skip
    assert rc == 1
    assert (out / "keep").read_text() == "old"
    assert list((tmp_path / "scratch").iterdir())  # kept for inspection


@pytest.mark.parametrize("out", [SPICE, SPICE / "ngspice", REPO / "results", REPO])
def test_run_refuses_the_golden_reference(out):
    with pytest.raises(ValueError, match="golden reference"):
        pdkdiff.run(out, sb=None, log=lambda s: None)


def test_run_refuses_unrelated_nonempty_out(tmp_path):
    (tmp_path / "x").write_text("x")
    with pytest.raises(ValueError, match="not an earlier pdkdiff tree"):
        pdkdiff.run(tmp_path, sb=None, log=lambda s: None)


def test_run_refuses_scratch_in_repo(tmp_path):
    with pytest.raises(ValueError, match="outside the repo"):
        pdkdiff.run(tmp_path / "o", scratch_root=REPO / "results", sb=None, log=lambda s: None)


def test_fetch_and_job_commands():
    c = pdkdiff.fetch_cmd("d" * 40)
    assert c[:2] == ["ciel", "fetch"] and c[-1] == "d" * 40
    assert "--pdk-root" in c and "/work/out/pdk" in c and "gf180mcu_fd_pr" in c
    j = pdkdiff.job_cmd(Job("ngspice", "typical", "nfet_05v0", "w10p0_l0p60"))
    assert j[:3] == ["python3", "-m", "gf180tcad.pdkdiff"] and "job" in j
    assert "/work/out/pdk" in j and "/work/out/out" in j


# --- the committed tree --------------------------------------------------------------------


def test_committed_tree_is_complete():
    for j in pdkdiff.plan():
        names = sorted(p.name for p in (TREE / j.relpath).iterdir())
        assert names == list(reference.expected_files("ngspice")), j
    rels = {p.relative_to(TREE).as_posix() for p in TREE.rglob("metrics.json")}
    assert rels == {f"{j.relpath.as_posix()}/metrics.json" for j in pdkdiff.plan()}


def test_committed_provenance_is_current():
    committed = json.loads((TREE / "provenance.json").read_bytes())
    assert committed == pdkdiff.provenance(), (
        "results/spice-pdk-d658698/provenance.json is stale; rerun "
        "`uv run --locked python -m gf180tcad.pdkdiff run --out results/spice-pdk-d658698` "
        "and `make manifest`"
    )


def test_committed_comparison_is_current():
    committed = json.loads((TREE / pdkdiff.COMPARISON_NAME).read_bytes())
    current = pdkdiff.compare(TREE / "ngspice" / "typical", SPICE / "ngspice" / "typical")
    assert committed == current


def test_committed_tree_is_in_the_manifest_but_not_under_spice():
    entries = manifest._load(REPO / "results" / "MANIFEST.sha256")
    ours = {r for r in entries if r.startswith("spice-pdk-d658698/")}
    files = {
        "spice-pdk-d658698/" + p.relative_to(TREE).as_posix()
        for p in TREE.rglob("*")
        if p.is_file()
    }
    assert ours == files
    # the SPICE cross-check and verify-subset select the reference by the "spice/" prefix
    assert not any(r.startswith("spice/") for r in ours)
