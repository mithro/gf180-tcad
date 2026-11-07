# SPDX-License-Identifier: Apache-2.0
"""Generated results pages (Task 13): deterministic SVGs, page coverage, offline docs build."""

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from optional import importorskip

importorskip("matplotlib", reason="needs the docs dependency group")

from offline_build import NO_NETWORK

from gf180tcad import docgen
from gf180tcad import results_figures as rf
from gf180tcad.devices import DEVICES, geometry_id
from gf180tcad.known import KNOWN_ENGINE_DIFFS
from gf180tcad.sandbox import REPO_ROOT

DOCS = REPO_ROOT / "docs"

_RENDER_EXPLAINED = textwrap.dedent(
    """
    import sys
    from gf180tcad.explain import figures
    sys.stdout.buffer.write(figures.FIGURES[sys.argv[1]](sys.argv[2]))
    """
)


# Every explainer figure (test_explained_figures_all_deterministic holds the list complete).
EXPLAINED_FIGURES = [
    "silicon-doping",
    "oxide-stack",
    "bands-stack",
    "bands-flat",
    "parts-cell",
    "junction-cell",
    "junction-panels",
    "moscap-cell",
    "moscap-cv",
    "cv-regions",
    "band-regimes",
    "mesh-window",
    "calibration-limits",
    "calibration-compare",
    "calibration-pfet",
    "calibration-stack",
    "cv-parts",
    "silicon-bonds",
    "silicon-dopants",
    "junction-profile",
    "ldd-cell",
    "cv-overview",
    "spice-sweeps",
    "corner-cv",
    "corner-area",
    "corner-bounds",
    "corner-crosscheck",
    "corner-crossing",
    "corner-limits",
]


def test_explained_figures_all_deterministic():
    from gf180tcad.explain import figures

    assert sorted(EXPLAINED_FIGURES) == sorted(figures.FIGURES)


@pytest.mark.parametrize("figure", EXPLAINED_FIGURES)
@pytest.mark.parametrize("palette", ["light", "dark"])
def test_explained_svg_deterministic(figure, palette):
    """An explainer figure, both palettes: two fresh processes give the same bytes."""
    runs = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run(
            [sys.executable, "-c", _RENDER_EXPLAINED, figure, palette],
            env=env, capture_output=True, check=True, timeout=300,
        )  # fmt: skip
        runs.append(r.stdout)
    a, b = runs
    assert a.startswith(b"<?xml") and b"<text" in a and a == b
    assert b"<dc:date>" not in a and str(REPO_ROOT).encode() not in a


def test_pages_cover_all_geometries(generated_pages):
    tmp_path = generated_pages
    expected = {f"{name}/{geometry_id(g)}.md" for name, d in DEVICES.items() for g in d.geometries}
    pages = {
        str(p.relative_to(tmp_path / "results")) for p in (tmp_path / "results").glob("*/*.md")
    }
    assert len(expected) == 12
    assert pages == expected
    page = (tmp_path / "results" / "nfet_05v0" / "w10p0_l0p60.md").read_text(encoding="utf-8")
    for needle in ("idvg_lin", "idvg_sat", "idvd", "cv", "Corner min", '"Same process" window'):
        assert needle in page
    for palette in ("light", "dark"):
        assert (tmp_path / "results" / "nfet_05v0" / f"w10p0_l0p60_idvd-{palette}.svg").is_file()


def test_summary_lists_status_and_engine_diffs(generated_pages):
    tmp_path = generated_pages
    s = (tmp_path / "results" / "index.md").read_text(encoding="utf-8")
    assert "pdk-spec-check" in s and "engine-cross-check" in s
    # Six compared spec entries, all inside; nfet idvg_sat rows carry the known-case marker.
    assert s.count("| inside |") == 6
    assert s.count("(known)") == 12  # nfet idvg_lin and idvg_sat, six geometries each
    assert "**unexplained**" not in s
    # the TCAD pages exist next to these: the summary links them and does not deny them
    assert "{doc}`/_generated/tcad/index`" in s
    assert "no {term}`TCAD` result" not in s


def test_number_format_is_locale_independent():
    assert docgen.fmt(1234.56789) == "1235"
    assert docgen.fmt(0.000123456) == "0.0001235"
    assert docgen.fmt(float("inf")) == "inf" and docgen.fmt(-float("inf")) == "-inf"


def test_table_numbers_do_not_break_at_the_exponent():
    """A table cell's exponent sign is U+2212, which a browser never breaks a line at."""
    assert docgen.num(2.63e-05, 3) == "2.63e\u221205"
    assert docgen.num(-0.2) == "-0.2" and docgen.num(1.7e17) == "1.7e+17"
    assert docgen.unit_text("fF/um^2") == "fF/µm²" and docgen.unit_text("um") == "µm"


def test_geometry_links_name_the_geometry(generated_pages):
    """S7: a link to a geometry page shows the geometry id, never a bare W that links to
    different pages; each page with such links says how to read the id."""
    import re

    for p in generated_pages.rglob("*.md"):
        text = p.read_text(encoding="utf-8")
        links = re.findall(r"\{doc\}`([^`<]*?)\s*<([^`>]*)>`", text)
        for label, target in links:
            assert not re.fullmatch(r"[\d.]+", label), (p.name, label, target)
        if p.name == "index.md" and any(
            re.fullmatch(r"w\d+p\d+_l\d+p\d+", label) for label, _ in links
        ):
            assert docgen._GEOMETRY_ID_TEXT in text, p
        assert " um" not in text and "um^2" not in text, p


def test_offline_block_positive_control(tmp_path):
    (tmp_path / "sitecustomize.py").write_text(NO_NETWORK, encoding="utf-8")
    code = textwrap.dedent(
        """
        import socket
        for call in (
            lambda: socket.create_connection(("127.0.0.1", 9)),
            lambda: socket.getaddrinfo("example.com", 80),
            lambda: socket.gethostbyname("example.com"),
            lambda: socket.socket().sendto(b"x", ("127.0.0.1", 9)),
        ):
            try:
                call()
            except OSError as e:
                assert "network disabled" in str(e), e
            else:
                raise SystemExit("network call was not blocked")
        print("blocked")
        """
    )
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    r = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False
    )
    assert r.returncode == 0 and r.stdout.strip() == "blocked", r.stdout + r.stderr


def test_docs_build_offline(offline_html):
    """The session's offline build (tests/offline_build.py) passed with -W; check its pages."""
    out = offline_html
    assert (out / "results" / "index.html").is_file()
    assert Path(out / "_images").is_dir()
    # the TCAD MOS capacitor pages (Task 13a) are in the build, with their figures
    tcad = out / "_generated" / "tcad"
    assert (tcad / "index.html").is_file()
    for name, d in DEVICES.items():
        assert (tcad / name / "index.html").is_file()
        for g in d.geometries:
            assert (tcad / name / f"{geometry_id(g)}.html").is_file()
    assert any(p.name.endswith("_cgg-light.svg") for p in (out / "_images").iterdir())


_RACE_WORKER = textwrap.dedent(
    """
    import runpy
    import sys
    from pathlib import Path

    conf = runpy.run_path(sys.argv[1])
    release = conf.get("_release_lock", lambda app, exc=None: None)
    generated = Path(sys.argv[1]).parent / "_generated"
    for _ in range(2):
        conf["_generate_results"](None)
        # the read phase of a build: every file of the tree must stay put until the build ends
        for f in sorted(p for p in generated.rglob("*") if p.is_file()):
            f.read_bytes()
        release(None)
    """
)


def test_concurrent_docs_generation_does_not_race(tmp_path):
    """Two builds of one checkout (issue #40) both finish and never see a missing file."""
    script = tmp_path / "worker.py"
    script.write_text(_RACE_WORKER, encoding="utf-8")
    procs = []
    for i in range(2):
        log = (tmp_path / f"w{i}.log").open("wb")
        procs.append(
            (
                subprocess.Popen(
                    [sys.executable, "-I", str(script), str(DOCS / "conf.py")],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                ),
                log,
            )
        )
    codes = []
    for proc, log in procs:
        codes.append(proc.wait(timeout=900))
        log.close()
    logs = [(tmp_path / f"w{i}.log").read_text(encoding="utf-8")[-2000:] for i in range(2)]
    assert codes == [0, 0], logs
    assert not list(DOCS.glob("_generated.*")), "temporary directories left behind"


def test_known_diffs_single_source():
    assert docgen.KNOWN_DIFFS is KNOWN_ENGINE_DIFFS
    assert KNOWN_ENGINE_DIFFS == {("nfet_05v0", "idvg_sat"), ("nfet_05v0", "idvg_lin")}


def test_idvd_series_selects_vb_zero():
    import numpy as np

    vd = np.tile(np.array([0.0, 1.0]), 4)
    vg = np.repeat([1.0, 2.0], 4)
    vb = np.tile(np.repeat([0.0, 1.0], 2), 2)
    cols = {"vd": vd, "vg": vg, "vb": vb, "id": np.arange(8.0) + 1}
    series = rf.series(cols, "idvd", 1)
    assert [list(y) for _, _, y in series] == [[1.0, 2.0], [5.0, 6.0]]
    cols["vb"] = np.ones(8)
    with pytest.raises(ValueError, match="vb"):
        rf.series(cols, "idvd", 1)


# --- missing inputs fail loudly; no silent "-" -------------------------------------------------


def _link_tree(dst: Path) -> Path:
    """A copy of the committed results/spice made of symlinks to its files (cheap)."""
    src = docgen.RESULTS
    for p in src.rglob("*"):
        if p.is_file():
            q = dst / p.relative_to(src)
            q.parent.mkdir(parents=True, exist_ok=True)
            q.symlink_to(p)
    return dst


NFET = DEVICES["nfet_05v0"]
GID = geometry_id(NFET.geometries[0])


@pytest.mark.parametrize("engine", ["ngspice", "xyce"])
def test_missing_csv_raises_in_the_engine_table(tmp_path, engine):
    root = _link_tree(tmp_path / "spice")
    (root / engine / "typical" / NFET.name / GID / "idvg_sat.csv").unlink()
    with pytest.raises(FileNotFoundError, match="idvg_sat.csv"):
        docgen._engine_table(root)


def test_missing_xyce_csv_raises_in_the_plots(tmp_path):
    root = _link_tree(tmp_path / "spice")
    (root / "xyce" / "typical" / NFET.name / GID / "idvd.csv").unlink()
    with pytest.raises(FileNotFoundError, match="idvd.csv"):
        rf.sweep_data(NFET.name, GID, "idvd", root)


def test_xyce_has_no_cv_and_that_is_not_an_error(tmp_path):
    assert rf.sweep_data(NFET.name, GID, "cv", docgen.RESULTS).xyce is None  # no Xyce overlay
    fig = rf.cv_figure(NFET.name, GID, "light")
    assert not [ln for ln in fig.axes[0].get_lines() if (ln.get_gid() or "").startswith("xyce")]


@pytest.mark.parametrize("engine", ["ngspice", "xyce"])
def test_missing_metrics_json_raises(tmp_path, engine):
    root = _link_tree(tmp_path / "spice")
    (root / engine / "typical" / NFET.name / GID / "metrics.json").unlink()
    spec = docgen.specwindow.load_spec()
    env = json.loads((root / "envelope.json").read_text(encoding="utf-8"))
    with pytest.raises(FileNotFoundError, match="metrics.json"):
        docgen._metrics_table(root, NFET, GID, spec, env)
    if engine == "ngspice":
        with pytest.raises(FileNotFoundError, match="metrics.json"):
            docgen._spec_status(root, spec)


def test_xyce_metric_missing_raises(tmp_path):
    root = _link_tree(tmp_path / "spice")
    path = root / "xyce" / "typical" / NFET.name / GID / "metrics.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["metrics"]["idsat_ua_per_um"]
    path.unlink()
    path.write_text(json.dumps(data), encoding="utf-8")
    spec = docgen.specwindow.load_spec()
    env = json.loads((root / "envelope.json").read_text(encoding="utf-8"))
    with pytest.raises(KeyError, match="idsat_ua_per_um"):
        docgen._metrics_table(root, NFET, GID, spec, env)


def _md_tables(lines: list[str]) -> list[tuple[list[str], list[list[str]]]]:
    """``(header, rows)`` of each pipe table in ``lines``, cells stripped."""
    out, block = [], []
    for line in [*lines, ""]:
        if line.startswith("|"):
            block.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif block:
            out.append((block[0], block[2:]))
            block = []
    return out


def test_window_column_shows_the_envelope_where_there_is_no_spec():
    spec = docgen.specwindow.load_spec()
    env = json.loads((docgen.RESULTS / "envelope.json").read_text(encoding="utf-8"))
    tables = _md_tables(docgen._metrics_table(docgen.RESULTS, NFET, GID, spec, env))
    (vh, values), (ch, corners), (wh, windows) = tables
    assert vh == ["Metric", "Unit", "TT ngspice", "TT Xyce"]
    assert ch == ["Metric", "Corner min", "Corner max"]
    assert wh == ["Metric", "Window min", "Window max", "Set by"]
    with_spec = set(docgen._spec_entries(spec, NFET.name, GID))
    assert with_spec and len(windows) > len(with_spec)
    assert [r[0] for r in values] == [r[0] for r in corners] == [r[0] for r in windows]
    for v, c, w in zip(values, corners, windows, strict=True):
        name = v[0].split("`")[1]
        lo, hi = env["ngspice"][NFET.name][GID][name]
        assert c[1:] == [docgen.num(lo), docgen.num(hi)]
        assert w[-1] not in ("", "-")
        if name not in with_spec:
            assert w[1:] == [docgen.num(lo), docgen.num(hi), "corner envelope"]
        # Xyce has no cv sweep, so only its Cgg cells are "not applicable"
        assert (v[3] == "not applicable") == name.startswith("cgg_")


def test_per_area_spec_entries_are_tcad_only(generated_pages):
    """The Cox spec is per area (no geometry) and SPICE extracts no such metric: it is left out
    of the SPICE spec table and the geometry pages and listed under "TCAD only"."""
    spec = docgen.specwindow.load_spec()
    per_area = [e for e in spec["entries"] if e.get("per_area")]
    assert {e["device"] for e in per_area} == set(DEVICES)
    assert {e["metric"] for e in per_area} == {"cox_ff_per_um2"}
    for device in DEVICES.values():
        for g in device.geometries:
            assert "cox_ff_per_um2" not in docgen._spec_entries(spec, device.name, geometry_id(g))
    rows = docgen._spec_status(docgen.RESULTS, spec)
    assert not any("cox_ff_per_um2" in r for r in rows)
    ((header, tcad),) = _md_tables(docgen._tcad_only_rows(spec))
    assert header[-2:] == ["Spec min (fF/µm²)", "Spec max (fF/µm²)"]
    assert len(tcad) == 2 and all(r[-3:] == ["`cox_ff_per_um2`", "1.8", "2.8"] for r in tcad)
    s = (generated_pages / "results" / "index.md").read_text(encoding="utf-8")
    # the two rows sit under "TCAD only", whose lead-in gives their one status
    section = s.split("### TCAD only", 1)[1].split("\n## ", 1)[0]
    assert 'The status of every row is "TCAD only"' in section
    assert section.count("| `cox_ff_per_um2` |") == 2


# --- TCAD MOS capacitor pages (Task 13a) ---------------------------------------------------------

TCAD = REPO_ROOT / "results" / "tcad"


def _tcad_json(device: str, gid: str) -> dict:
    """The committed 1D comparison of one geometry: calibration or validation file."""
    cal = json.loads((TCAD / "calibration" / f"{device}.result.json").read_text("utf-8"))
    if gid in cal["per_geometry"]:
        return cal["per_geometry"][gid]
    val = json.loads((TCAD / "validation" / f"{device}.json").read_text("utf-8"))
    return val["one_d"][gid]


def test_moscap_page_per_device_geometry(generated_pages):
    tmp_path = generated_pages
    root = tmp_path / "tcad"
    expected = {f"{name}/{geometry_id(g)}.md" for name, d in DEVICES.items() for g in d.geometries}
    pages = {
        str(p.relative_to(root))
        for p in root.glob("*/*.md")
        if p.name not in ("index.md", docgen.CORNER_FRAGMENT)
    }
    assert len(expected) == 12 and pages == expected
    for name, device in DEVICES.items():
        for g in device.geometries:
            gid = geometry_id(g)
            page = (root / name / f"{gid}.md").read_text(encoding="utf-8")
            r = _tcad_json(name, gid)
            # the overlay (TCAD against ngspice TT and the corner envelope) and the 1D split
            for fig in ("cgg", "split"):
                for palette in ("light", "dark"):
                    assert f"```{{figure}} {gid}_{fig}-{palette}.svg" in page
                    assert (root / name / f"{gid}_{fig}-{palette}.svg").is_file()
                assert f"{{numref}}`{docgen.tcad_label(name, gid, fig)}`" in page
            # verdicts and numbers rendered from the committed JSON, not recomputed
            assert f"Verdict (1D): **{r['verdict']}**" in page
            for key in ("plateau_acc", "plateau_inv", "dv_dep", "dv_inv"):
                assert f"| {r['verdicts'][key]['verdict']} |" in page
            m = r["metrics"]
            assert f"| {1e3 * m['dv_dep_v']:+.1f} |" in page  # mV, the unit in the header
            assert f"| {1e3 * m['dv_inv_v']:+.1f} |" in page
            assert f"{100 * m['depletion_max_rel']:.2f} %" in page
            assert g.role in page
            # mesh pictures: from each 2D cell's committed reduced mesh artefact, or a reason;
            # a geometry with no 2D cell has no mesh section at all
            has_2d = any(
                (TCAD / "moscap2d" / name / p / gid / "cv.meta.json").is_file()
                for p in ("calibrated", "start")
            )
            assert "issues/39" not in page
            assert ("### Mesh picture" in page) == has_2d
            for params in ("calibrated", "start"):
                if not (TCAD / "moscap2d" / name / params / gid / "cv.meta.json").is_file():
                    continue
                if list((TCAD / "meshes").glob(f"*/{name}/{params}/{gid}/mesh-window.meta.json")):
                    assert f":name: mesh-{name}-{gid}-{params}" in page
                    for palette in ("light", "dark"):
                        assert (root / name / f"{gid}_mesh_{params}-{palette}.svg").is_file()
                else:
                    assert docgen._no_artefact(params) in page
            meta = TCAD / "moscap2d" / name / "start" / gid / "cv.meta.json"
            if meta.is_file():
                assert json.loads(meta.read_text("utf-8"))["mesh_sha256"] in page
            else:
                assert "No 2D result" in page
            # every committed 2D cell is drawn against its 1D stack
            two_d = (root / name / f"{gid}_2d-light.svg").is_file()
            assert two_d == bool(list((TCAD / "moscap2d" / name).glob(f"*/{gid}/cv.meta.json")))
            # a committed calibrated 2D cell is named on its page, with its mesh
            cal_meta = TCAD / "moscap2d" / name / "calibrated" / gid / "cv.meta.json"
            if cal_meta.is_file():
                rel = f"results/tcad/moscap2d/{name}/calibrated/{gid}"
                assert f"{{repo}}`{rel}`" in page
                assert json.loads(cal_meta.read_text("utf-8"))["mesh_sha256"] in page
                assert "Calibrated 2D validation: not run" not in page
        index = (root / name / "index.md").read_text(encoding="utf-8")
        cal = json.loads((TCAD / "calibration" / f"{name}.result.json").read_text("utf-8"))
        assert f"{cal['budget_used']} of {cal['budget']}" in index
        for p in cal["params"]:
            assert f"`{p}`" in index
        assert "dlc_nm" in index  # the reference-bookkeeping rows, listed separately
        for dim in ("1d", "2d"):
            assert (root / name / f"meshconv_{dim}-light.svg").is_file()
            assert f"```{{figure}} meshconv_{dim}-light.svg" in index
    summary = (root / "index.md").read_text(encoding="utf-8")
    for name, device in DEVICES.items():
        for g in device.geometries:
            assert f"<{name}/{geometry_id(g)}>" in summary
    # the calibrated 2D validation (issue #35): the summary never says "not run for any
    # geometry" while a calibrated 2D cell is committed
    if list((TCAD / "moscap2d").glob("*/calibrated/*/cv.csv")):
        assert "not run for any geometry" not in summary
    else:
        assert "not run for any geometry" in summary


def test_validation_two_d_matches_committed_calibrated_cells():
    """A validation ``two_d`` entry is "not run" if and only if no calibrated 2D cv.csv is
    committed for its geometry."""
    for name, device in DEVICES.items():
        val = json.loads((TCAD / "validation" / f"{name}.json").read_text("utf-8"))
        for g in device.geometries:
            gid = geometry_id(g)
            committed = (TCAD / "moscap2d" / name / "calibrated" / gid / "cv.csv").is_file()
            assert (val["two_d"][gid]["status"] == "not run") == (not committed), (name, gid)


_RENDER_TCAD = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    from gf180tcad import docgen
    docgen.generate(Path(sys.argv[1]))
    """
)


def test_moscap_pages_deterministic(tmp_path):
    trees = []
    for seed in ("1", "2"):
        out = tmp_path / seed
        env = {**os.environ, "PYTHONHASHSEED": seed}
        subprocess.run(
            [sys.executable, "-c", _RENDER_TCAD, str(out)], env=env, check=True, timeout=600
        )
        root = out / "tcad"
        trees.append(
            {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        )
    a, b = trees
    assert sum(k.endswith(".svg") for k in a) >= 2 * 12 + 2 * 2
    assert a.keys() == b.keys() and all(a[k] == b[k] for k in a)
    for k, data in a.items():
        assert str(REPO_ROOT).encode() not in data, k
        if k.endswith(".svg"):
            assert b"<dc:date>" not in data and b"<text" in data


def _link_tcad_tree(dst: Path) -> Path:
    for p in TCAD.rglob("*"):
        if p.is_file():
            q = dst / p.relative_to(TCAD)
            q.parent.mkdir(parents=True, exist_ok=True)
            q.symlink_to(p)
    return dst


def test_moscap_verdicts_are_read_not_recomputed(tmp_path):
    """A verdict changed in the committed JSON shows on the page: docgen renders, it does not
    recompute the TCAD-vs-SPICE comparison."""
    tcad = _link_tcad_tree(tmp_path / "tcad_in")
    path = tcad / "calibration" / "nfet_05v0.result.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["per_geometry"]["w10p0_l10p00"]["verdict"] = "Disagree"
    data["per_geometry"]["w10p0_l10p00"]["verdicts"]["dv_dep"]["verdict"] = "Disagree"
    path.unlink()
    path.write_text(json.dumps(data), encoding="utf-8")
    docgen.generate(tmp_path / "out", tcad_root=tcad)
    page = (tmp_path / "out" / "tcad" / "nfet_05v0" / "w10p0_l10p00.md").read_text("utf-8")
    assert "Verdict (1D): **Disagree**" in page


def test_moscap_summary_2d_sentence_follows_the_statuses(tmp_path):
    """The summary's 2D sentence and column are derived from the two_d statuses and the
    committed calibrated 2D cells, not fixed text."""
    tree = _link_tcad_tree(tmp_path / "tcad_in")
    out = tmp_path / "out"

    def summary() -> str:
        docgen.generate_tcad(out, tcad_root=tree)
        return (out / "tcad" / "index.md").read_text("utf-8")

    def row(text: str, gid: str) -> str:
        return next(ln for ln in text.splitlines() if f"<nfet_05v0/{gid}>" in ln)

    # a committed calibrated 2D cell the validation file does not compare: pending
    first = min(tree.glob("moscap2d/*/calibrated/*/cv.csv"), default=None)
    if first is not None:
        vpath = tree / "validation" / f"{first.parents[2].name}.json"
        val = json.loads(vpath.read_text("utf-8"))
        val["two_d"][first.parent.name] = {"causes": [], "reason": "none", "status": "not run"}
        vpath.unlink()
        vpath.write_text(json.dumps(val), "utf-8")
    # each committed calibrated 2D cell: its verdict once compared, else pending
    text = summary()
    if first is not None:
        assert docgen._TWO_D_PENDING in text
    for csv in sorted(tree.glob("moscap2d/*/calibrated/*/cv.csv")):
        device, gid = csv.parents[2].name, csv.parent.name
        entry = json.loads((tree / "validation" / f"{device}.json").read_text("utf-8"))
        entry = entry["two_d"][gid]
        want = entry["verdict"] if entry["status"] == "compared" else docgen._TWO_D_PENDING
        line = next(ln for ln in text.splitlines() if f"<{device}/{gid}>" in ln)
        assert line.endswith(f"| {want} |"), line
        for f in csv.parent.iterdir():
            f.unlink()
    # no calibrated 2D cell and nothing compared, for either device: every geometry not run
    for device in DEVICES:
        path = tree / "validation" / f"{device}.json"
        val = json.loads(path.read_text("utf-8"))
        for gid in val["two_d"]:
            val["two_d"][gid] = {"causes": [], "reason": "none", "status": "not run"}
        path.unlink()
        path.write_text(json.dumps(val), "utf-8")
    text = summary()
    assert "not run for any geometry" in text and docgen._TWO_D_PENDING not in text
    # a compared entry shows its verdict
    path = tree / "validation" / "nfet_05v0.json"
    val = json.loads(path.read_text("utf-8"))
    gid = next(iter(val["two_d"]))
    val["two_d"][gid].update(status="compared", verdict="Disagree")
    path.unlink()
    path.write_text(json.dumps(val), "utf-8")
    text = summary()
    assert "not run for any geometry" not in text and row(text, gid).endswith("| Disagree |")
    # only a pfet entry compared: the sentence must follow the pfet too
    val["two_d"][gid] = {"causes": [], "reason": "none", "status": "not run"}
    path.unlink()
    path.write_text(json.dumps(val), "utf-8")
    ppath = tree / "validation" / "pfet_05v0.json"
    pval = json.loads(ppath.read_text("utf-8"))
    pgid = next(iter(pval["two_d"]))
    pval["two_d"][pgid].update(status="compared", verdict="Disagree")
    ppath.unlink()
    ppath.write_text(json.dumps(pval), "utf-8")
    text = summary()
    prow = next(ln for ln in text.splitlines() if f"<pfet_05v0/{pgid}>" in ln)
    assert "not run for any geometry" not in text and prow.endswith("| Disagree |")


def test_checks_match_the_committed_verdicts():
    """docgen.CHECKS names exactly the checks of every committed 1D comparison record, so a
    check added to gf180tcad.calibrate.cv.verdicts cannot be left off the pages silently."""
    keys = {key for key, _ in docgen.CHECKS}
    n = 0
    for name in DEVICES:
        cal = json.loads((TCAD / "calibration" / f"{name}.result.json").read_text("utf-8"))
        val = json.loads((TCAD / "validation" / f"{name}.json").read_text("utf-8"))
        for rec in (*cal["per_geometry"].values(), *val["one_d"].values()):
            assert set(rec["verdicts"]) == keys
            n += 1
    assert n == 12


def test_bound_hit_rule_is_the_calibration_constant(tmp_path, monkeypatch):
    """The bound-hit sentence is formatted from the constant, not typed: change it and the page follows."""
    from gf180tcad.calibrate.cv import BOUND_HIT_REL

    docgen.generate_tcad(tmp_path / "a")
    page = (tmp_path / "a" / "tcad" / "nfet_05v0" / "index.md").read_text("utf-8")
    assert BOUND_HIT_REL == 1e-3 and "within 1e-3 of a bound" in page

    monkeypatch.setattr("gf180tcad.calibrate.cv.BOUND_HIT_REL", 2e-3)
    docgen.generate_tcad(tmp_path / "b")
    page = (tmp_path / "b" / "tcad" / "nfet_05v0" / "index.md").read_text("utf-8")
    assert "within 2e-3 of a bound" in page and "1e-3" not in page


def test_plateau_tolerance_lines_are_per_side(tmp_path):
    """The errors panel draws each plateau's own tolerance (one key while they are equal)."""
    tree = _link_tcad_tree(tmp_path / "tcad_in")
    out = tmp_path / "out"
    svg = out / "tcad" / "nfet_05v0" / "w10p0_l10p00_cgg-light.svg"
    docgen.generate_tcad(out, tcad_root=tree)
    assert "tolerance ±5 %" in svg.read_text("utf-8")
    path = tree / "calibration" / "nfet_05v0.result.json"
    data = json.loads(path.read_text("utf-8"))
    data["per_geometry"]["w10p0_l10p00"]["verdicts"]["plateau_inv"]["tolerance"] = 0.1
    path.unlink()
    path.write_text(json.dumps(data), "utf-8")
    docgen.generate_tcad(out, tcad_root=tree)
    text = svg.read_text("utf-8")
    assert "tolerance (acc) ±5 %" in text and "tolerance (inv) ±10 %" in text


def test_moscap_missing_result_raises(tmp_path):
    tcad = _link_tcad_tree(tmp_path / "tcad_in")
    (tcad / "validation" / "pfet_05v0.json").unlink()
    with pytest.raises(FileNotFoundError, match="pfet_05v0.json"):
        docgen.generate(tmp_path / "out", tcad_root=tcad)


# --- the mesh picture of a 2D cell (renders plan, Task R0) ------------------------------------


def _fake_device(tcad, name="nfet_05v0"):
    from types import SimpleNamespace

    def two_d(gid, params="start"):
        job = tcad / "moscap2d" / name / params / gid
        return job if (job / "cv.meta.json").is_file() else None

    return SimpleNamespace(root=tcad, device=SimpleNamespace(name=name), two_d=two_d)


def _synthetic_artefact(tcad, name, params, gid):
    """A 2D job and a reduced mesh artefact of it cut from the meshcut test fixture."""
    import numpy as np

    from gf180tcad.meshcut import artefact, msh, window

    job = tcad / "moscap2d" / name / params / gid
    job.mkdir(parents=True)
    (job / "cv.meta.json").write_text("{}\n", encoding="utf-8")
    fixture = REPO_ROOT / "tests" / "fixtures" / "meshcut" / "grid30.msh"
    mesh = msh.read(fixture)
    win = window.cut(mesh, x_um=(0.0, 0.5), y_um=(-0.15, 0.2))
    win = win.with_net_doping(np.zeros(len(win.node_id)))
    out = tcad / "meshes" / "stable" / name / params / gid
    out.mkdir(parents=True)
    rule = {"depth_um": 0.15, "gate_x_um": [0.0, 0.5], "kx": 0.0, "poly_top_um": 0.2,
            "surface_um": 0.0}  # fmt: skip
    job_rec = {"cv_meta_sha256": "0" * 64, "device": name, "geometry_id": gid, "params": params,
               "tree": "tcad/moscap2d"}  # fmt: skip
    from gf180tcad.meshcut import job as cut_job

    return out, artefact.write(
        out, win, job=job_rec, full_mesh_sha256="a" * 64, full_mesh_node_count=30,
        full_mesh_triangle_count=40, rule=rule, source="cache",
        region_bounds_um=cut_job.region_bounds(mesh),
    )  # fmt: skip


def test_mesh_figure_from_committed_artefact(tmp_path):
    tcad = tmp_path / "results" / "tcad"
    _, meta = _synthetic_artefact(tcad, "nfet_05v0", "calibrated", "w1p0_l0p50")
    ddir = tmp_path / "page"
    ddir.mkdir()
    lines = docgen._mesh_section(_fake_device(tcad), "w1p0_l0p50", ddir)
    text = "\n".join(lines)
    assert text.count("```{figure}") == 2  # a light and a dark twin
    assert ":name: mesh-nfet_05v0-w1p0_l0p50-calibrated" in text
    assert "{numref}`mesh-nfet_05v0-w1p0_l0p50-calibrated` shows the mesh" in text
    assert ":figclass: only-light" in text and ":figclass: only-dark" in text
    assert f"{meta['triangle_count']} of the full mesh's 40 triangles" in text
    assert "results/tcad/meshes/stable/nfet_05v0/calibrated/w1p0_l0p50" in text
    assert "a" * 64 in text
    light = (ddir / "w1p0_l0p50_mesh_calibrated-light.svg").read_bytes()
    dark = (ddir / "w1p0_l0p50_mesh_calibrated-dark.svg").read_bytes()
    assert light.startswith(b"<?xml") and light != dark
    again = tmp_path / "again"
    again.mkdir()
    docgen._mesh_section(_fake_device(tcad), "w1p0_l0p50", again)
    assert (again / "w1p0_l0p50_mesh_calibrated-light.svg").read_bytes() == light


def test_mesh_figure_absent_states_why(tmp_path):
    tcad = tmp_path / "results" / "tcad"
    _synthetic_artefact(tcad, "nfet_05v0", "calibrated", "w1p0_l0p50")
    start = tcad / "moscap2d" / "nfet_05v0" / "start" / "w1p0_l0p50"
    start.mkdir(parents=True)
    (start / "cv.meta.json").write_text("{}\n", encoding="utf-8")
    ddir = tmp_path / "page"
    ddir.mkdir()
    text = "\n".join(docgen._mesh_section(_fake_device(tcad), "w1p0_l0p50", ddir))
    assert docgen._no_artefact("start") in text
    # the start cell's sentence links mesh.msh to its .gitignore line (spec §10.3 file links)
    assert "{repo}`mesh.msh <.gitignore#L" in text and "MESH" not in text
    assert ":name: mesh-nfet_05v0-w1p0_l0p50-calibrated" in text
    assert not list(ddir.glob("*_mesh_start-*.svg"))
    # a geometry with no 2D cell gets no mesh section: its 2D section already says why
    assert docgen._mesh_section(_fake_device(tcad), "w9p9_l9p90", ddir) == []


def test_no_mesh_deviation_text_when_artefact_exists(tmp_path):
    tcad = tmp_path / "results" / "tcad"
    _synthetic_artefact(tcad, "nfet_05v0", "calibrated", "w1p0_l0p50")
    ddir = tmp_path / "page"
    ddir.mkdir()
    text = "\n".join(docgen._mesh_section(_fake_device(tcad), "w1p0_l0p50", ddir))
    for old in ("issues/39", "deviation", "not committed (git-ignored", "No mesh picture"):
        assert old not in text
    assert not hasattr(docgen, "_NO_MESH")


_RENDER_MESH = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    from gf180tcad.explain import figures
    sys.stdout.buffer.write(figures.mesh_artefact(Path(sys.argv[1]), sys.argv[2]))
    """
)


@pytest.mark.parametrize("palette", ["light", "dark"])
def test_mesh_figure_svg_deterministic(tmp_path, palette):
    """The mesh figure (its triangles embedded as an image): two fresh processes, same bytes."""
    out, _ = _synthetic_artefact(tmp_path / "tcad", "nfet_05v0", "calibrated", "w1p0_l0p50")
    runs = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run(
            [sys.executable, "-c", _RENDER_MESH, str(out), palette],
            env=env, capture_output=True, check=True, timeout=300,
        )  # fmt: skip
        runs.append(r.stdout)
    a, b = runs
    assert a.startswith(b"<?xml") and b"<text" in a and b"data:image/png;base64" in a and a == b
    assert b"<dc:date>" not in a and str(tmp_path).encode() not in a


def _corner_summary() -> dict:
    """A synthetic corner summary of the nfet (the layout of
    :func:`gf180tcad.calibrate.corners.summary`), with the ff oxide on its lower limit."""
    from gf180tcad.devices import CORNERS

    fit = [c for c in CORNERS if c != "typical"]
    values = {
        "t_ox_eff_nm": dict(zip(CORNERS, (16.05, 15.05, 17.0, 15.3, 16.8), strict=True)),
        "n_ch_cm3": dict(zip(CORNERS, (8.8e16, 8.1e16, 9.6e16, 8.5e16, 9.1e16), strict=True)),
        "dv_fb_v": dict(zip(CORNERS, (0.0987, -0.03, 0.22, 0.01, 0.18), strict=True)),
    }
    tunables = {}
    for n, per in values.items():
        lo = min(per, key=per.get)
        hi = max(per, key=per.get)
        row = {"typical": per["typical"], "values": per, "min": per[lo], "min_corner": lo,
               "max": per[hi], "max_corner": hi, "spread": per[hi] - per[lo],
               "min_at_bound": "lower" if n == "t_ox_eff_nm" else None, "max_at_bound": None}  # fmt: skip
        if n == "n_ch_cm3":
            row["card_shift"] = row["tcad_shift"] = row["shift_difference"] = None
        else:
            card = {c: (per[c] - per["typical"]) * 0.9 for c in fit}
            tcad = {c: per[c] - per["typical"] for c in fit}
            row |= {"card_shift": card, "tcad_shift": tcad,
                    "shift_difference": {c: tcad[c] - card[c] for c in fit}}  # fmt: skip
        tunables[n] = row
    corners = {"typical": {"bound_hits": {}, "per_geometry": {"g": "Agree"}, "verdict": "Agree"}}
    for c in fit:
        corners[c] = {
            "bound_hits": {"t_ox_eff_nm": "lower"} if c == "ff" else {},
            "held_out": {"a": "Agree", "b": "Same process" if c == "ss" else "Agree"},
            "per_geometry": {"g": "Agree"},
            "verdict": "Agree",
        }
    return {"corners": corners, "device": "nfet_05v0", "tunables": tunables}


def test_docgen_corner_table_one_value_per_cell():
    """The corner tables of a device page: at most five columns, one value per cell (a number,
    a corner, a verdict or a limit word), each read from the summary, the unit in the row label
    or the header; a limit hit is named below the tables, not in a cell."""
    import re

    from gf180tcad.explain.numbers import shortest

    s = _corner_summary()
    lines = docgen.corner_tables("nfet_05v0", s)
    tables = _md_tables(lines)
    assert len(tables) == 6
    one_value = re.compile(r"^(`[a-z_0-9]+`( \([^)]+\))?|−?[0-9.]+(\xa0×\xa010[⁻⁰¹²³⁴⁵⁶⁷⁸⁹]+)?†?|"
                           r"[a-z]+|lower limit|upper limit|"
                           r"\{term\}`(Agree|Same process|Disagree)`|not applicable)$")  # fmt: skip
    for header, rows in tables:
        assert len(header) <= 5, header
        for r in rows:
            assert len(r) == len(header)
            for cell in r:
                assert one_value.match(cell), (header, cell)
    bounds, where, per, tox, fb, verdicts = tables
    assert bounds[0] == ["Number", "Typical", "Lowest", "Highest", "Spread"]
    tox_row = s["tunables"]["t_ox_eff_nm"]
    assert bounds[1][0] == ["`t_ox_eff_nm` (nm)", shortest(tox_row["typical"], "", 4),
                            shortest(tox_row["min"], "", 4) + "†", shortest(tox_row["max"], "", 4),
                            shortest(tox_row["spread"], "", 4)]  # fmt: skip
    fb_row = s["tunables"]["dv_fb_v"]
    assert bounds[1][2][1:] == [
        shortest(fb_row[k], "", 3) for k in ("typical", "min", "max", "spread")
    ]
    assert bounds[1][2][2] == "−0.03"
    assert bounds[1][1][1] == "8.8\xa0×\xa010¹⁶"
    assert where[0] == ["Number", "Lowest at", "On a limit", "Highest at", "On a limit"]
    assert where[1][0] == ["`t_ox_eff_nm`", "ff", "lower limit", "ss", "no"]
    assert [r[0] for r in per[1]] == ["typical", "ff", "ss", "fs", "sf"]
    assert per[1][2][1:] == ["17", "9.6\xa0×\xa010¹⁶", "0.22"]
    assert per[1][1][1] == "15.05†" and per[1][1][3] == "−0.03"
    assert tox[0] == ["Corner", "Card (nm)", "Fit (nm)", "Difference (nm)"]
    assert tox[1][0][2].endswith("†") and tox[1][0][3].endswith("†") and "†" not in tox[1][0][1]
    assert not any("†" in c for r in fb[1] for c in r)
    assert fb[0][1] == "Card (V)"
    assert [r[0] for r in tox[1]] == ["ff", "ss", "fs", "sf"]
    assert verdicts[1][0] == ["typical", "{term}`Agree`", "not applicable"]
    assert verdicts[1][2] == ["ss", "{term}`Agree`", "{term}`Same process`"]
    assert "Limit hits: `t_ox_eff_nm` at ff is on its lower limit." in lines
    # the note below each table with a marked value, and only below those
    note = [i for i, ln in enumerate(lines) if ln == docgen.LIMIT_NOTE]
    marked = [i for i, ln in enumerate(lines) if ln.startswith("|") and "†" in ln]
    assert len(note) == 3 and all(any(m < n for m in marked) for n in note)
    assert not any(
        "bound" in ln.lower().replace("bounds", "") for ln in lines if "{repo}" not in ln
    )


def test_docgen_corner_tables_mark_nothing_without_a_limit_hit():
    """With no fit on a limit, no cell carries the mark and no note is written."""
    s = _corner_summary()
    s["tunables"]["t_ox_eff_nm"]["min_at_bound"] = None
    s["corners"]["ff"]["bound_hits"] = {}
    lines = docgen.corner_tables("nfet_05v0", s)
    assert not any("†" in ln for ln in lines)
    assert docgen.LIMIT_NOTE not in lines
    assert "No fit, typical or corner, sits on a limit." in lines


def test_docgen_corner_table_refuses_another_device():
    with pytest.raises(ValueError, match="pfet_05v0"):
        docgen.corner_tables("pfet_05v0", _corner_summary())


def test_readme_figures_are_current():
    """README.md's committed figures are what docgen draws from the committed results now (run
    `make readme-figures` when this fails after a results change)."""
    drawn = docgen.readme_figures()
    assert len(drawn) == 2 * len(docgen.README_FIGURES)
    for name, svg in drawn.items():
        committed = (docgen.README_FIGURES_DIR / name).read_bytes()
        assert committed == svg, f"{name} is stale: run make readme-figures"
    assert sorted(p.name for p in docgen.README_FIGURES_DIR.iterdir()) == sorted(drawn)


def readme_prose(text: str) -> str:
    """README.md without its figure captions (``*Figure N. ...*`` blocks) and image lines: the
    text a prose citation of a figure must sit in."""
    text = re.sub(r"^\*Figure \d+\. .*?\*$", " ", text, flags=re.MULTILINE | re.DOTALL)
    return re.sub(r"^\s*(!\[|<).*$", " ", text, flags=re.MULTILINE)


def test_readme_shows_each_figure():
    """Each README figure is a <picture> in README.md that follows the theme (the dark twin as
    the dark source, the light one as the image, with alt text), captioned "*Figure N. ...*" in
    order and cited as "Figure N" in the prose outside every caption."""
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    prose = readme_prose(text)
    rel = docgen.README_FIGURES_DIR.relative_to(REPO_ROOT).as_posix()
    for n, name in enumerate(docgen.README_FIGURES, start=1):
        picture = (
            r"<picture>\s*"
            rf'<source media="\(prefers-color-scheme: dark\)" srcset="{rel}/{name}-dark\.svg">\s*'
            rf'<img alt="(?P<alt>[^"]+)" src="{rel}/{name}-light\.svg">\s*</picture>'
        )
        m = re.search(picture, text)
        assert m, f"no <picture> of {name}"
        assert len(m.group("alt")) <= 150, name
        assert f"*Figure {n}. " in text, name
        assert re.search(rf"\bFigure {n}\b", prose), f"no prose citation of Figure {n} ({name})"


def test_readme_corner_count_is_the_registry():
    """The README's C-V captions give the number of SPICE corners the figures draw."""
    from gf180tcad.devices import CORNERS

    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    n = len(CORNERS)
    found = re.findall(r"grey band of its (\d+)\s*\[corners\]", text)
    assert found and all(int(k) == n for k in found), (found, n)


def test_readme_prose_drops_the_captions():
    """Positive control: a citation that sits only in a caption is not a prose citation."""
    text = "Some text.\n\n![alt](a.svg)\n\n*Figure 2. A caption that names Figure 1\nover two lines.*\n"
    assert "Figure 1" not in readme_prose(text)
    assert "Figure 1" in readme_prose(text + "\nAs Figure 1 shows.\n")
