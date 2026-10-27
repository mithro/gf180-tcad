# SPDX-License-Identifier: Apache-2.0
"""Generated results pages (Task 13): deterministic SVGs, page coverage, offline docs build."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from optional import importorskip

importorskip("matplotlib", reason="needs the docs dependency group")

from gf180tcad import docgen
from gf180tcad.devices import DEVICES, geometry_id
from gf180tcad.known import KNOWN_ENGINE_DIFFS
from gf180tcad.sandbox import REPO_ROOT

DOCS = REPO_ROOT / "docs"

_RENDER = textwrap.dedent(
    """
    import sys
    from gf180tcad import docgen
    sys.stdout.buffer.write(docgen.demo_svg())
    """
)


def _render_in_fresh_process(hashseed: str) -> bytes:
    env = {**os.environ, "PYTHONHASHSEED": hashseed}
    r = subprocess.run(
        [sys.executable, "-c", _RENDER], env=env, capture_output=True, check=True, timeout=300
    )
    return r.stdout


def test_svg_deterministic():
    a = _render_in_fresh_process("1")
    b = _render_in_fresh_process("2")
    assert a.startswith(b"<?xml") and b"<svg" in a and len(a) > 5000
    assert a == b
    # No date, no font outlines (text stays text), no absolute host path.
    assert b"<dc:date>" not in a and b"<text" in a and str(REPO_ROOT).encode() not in a


_RENDER_EXPLAINED = textwrap.dedent(
    """
    import sys
    from gf180tcad.explain import figures
    sys.stdout.buffer.write(figures.FIGURES[sys.argv[1]](sys.argv[2]))
    """
)


# Every explainer figure (test_explained_figures_all_deterministic holds the list complete).
EXPLAINED_FIGURES = ["silicon-doping", "oxide-stack", "bands-stack", "bands-flat"]


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


def test_pages_cover_all_geometries(tmp_path):
    docgen.generate(tmp_path)
    expected = {f"{name}/{geometry_id(g)}.md" for name, d in DEVICES.items() for g in d.geometries}
    pages = {
        str(p.relative_to(tmp_path / "results")) for p in (tmp_path / "results").glob("*/*.md")
    }
    assert len(expected) == 12
    assert pages == expected
    page = (tmp_path / "results" / "nfet_05v0" / "w10p0_l0p60.md").read_text(encoding="utf-8")
    for needle in ("idvg_lin", "idvg_sat", "idvd", "cv", "Corner min", '"Same process" window'):
        assert needle in page
    assert (tmp_path / "results" / "nfet_05v0" / "w10p0_l0p60_idvd.svg").is_file()


def test_summary_lists_status_and_engine_diffs(tmp_path):
    docgen.generate(tmp_path)
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


def test_geometry_links_name_the_geometry(tmp_path):
    """S7: a link to a geometry page shows the geometry id, never a bare W that links to
    different pages; each page with such links says how to read the id."""
    import re

    docgen.generate(tmp_path)
    for p in tmp_path.rglob("*.md"):
        text = p.read_text(encoding="utf-8")
        links = re.findall(r"\{doc\}`([^`<]*?)\s*<([^`>]*)>`", text)
        for label, target in links:
            assert not re.fullmatch(r"[\d.]+", label), (p.name, label, target)
        if p.name == "index.md" and any(
            re.fullmatch(r"w\d+p\d+_l\d+p\d+", label) for label, _ in links
        ):
            assert docgen._GEOMETRY_ID_TEXT in text, p
        assert " um" not in text and "um^2" not in text, p


_NO_NETWORK = textwrap.dedent(
    """
    import socket

    def _blocked(*a, **k):
        raise OSError("network disabled by test_docs_build_offline")

    socket.socket.connect = _blocked
    socket.socket.connect_ex = _blocked
    socket.socket.sendto = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    socket.gethostbyname = _blocked
    """
)


def test_offline_block_positive_control(tmp_path):
    (tmp_path / "sitecustomize.py").write_text(_NO_NETWORK, encoding="utf-8")
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


def test_docs_build_offline(tmp_path):
    importorskip("sphinx")
    (tmp_path / "sitecustomize.py").write_text(_NO_NETWORK, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    out = tmp_path / "html"
    log = tmp_path / "build.log"
    with log.open("wb") as f:
        r = subprocess.run(
            [sys.executable, "-m", "sphinx", "-W", "-b", "html", "-d", str(tmp_path / "dt"),
             str(DOCS), str(out)],
            check=False, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=900,
        )  # fmt: skip
    assert r.returncode == 0, log.read_text(encoding="utf-8")[-3000:]
    assert (out / "results" / "index.html").is_file()
    assert Path(out / "_images").is_dir()
    # the TCAD MOS capacitor pages (Task 13a) are in the build, with their figures
    tcad = out / "_generated" / "tcad"
    assert (tcad / "index.html").is_file()
    for name, d in DEVICES.items():
        assert (tcad / name / "index.html").is_file()
        for g in d.geometries:
            assert (tcad / name / f"{geometry_id(g)}.html").is_file()
    assert any(p.name.endswith("_cgg.svg") for p in (out / "_images").iterdir())


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
    series = docgen._series(cols, "idvd", 1)
    assert [list(y) for _, _, y in series] == [[1.0, 2.0], [5.0, 6.0]]
    cols["vb"] = np.ones(8)
    with pytest.raises(ValueError, match="vb"):
        docgen._series(cols, "idvd", 1)


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
        docgen._curves(root, NFET, GID, "idvd", 1e3, None)


def test_xyce_has_no_cv_and_that_is_not_an_error(tmp_path):
    curves, _ = docgen._curves(docgen.RESULTS, NFET, GID, "cv", 1.0, None)
    assert not any(c.dashed for c in curves)  # no Xyce overlay


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


def test_per_area_spec_entries_are_tcad_only(tmp_path):
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
    docgen.generate(tmp_path)
    s = (tmp_path / "results" / "index.md").read_text(encoding="utf-8")
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


def test_moscap_page_per_device_geometry(tmp_path):
    docgen.generate(tmp_path)
    root = tmp_path / "tcad"
    expected = {f"{name}/{geometry_id(g)}.md" for name, d in DEVICES.items() for g in d.geometries}
    pages = {str(p.relative_to(root)) for p in root.glob("*/*.md") if p.name != "index.md"}
    assert len(expected) == 12 and pages == expected
    for name, device in DEVICES.items():
        for g in device.geometries:
            gid = geometry_id(g)
            page = (root / name / f"{gid}.md").read_text(encoding="utf-8")
            r = _tcad_json(name, gid)
            # the overlay (TCAD against ngspice TT and the corner envelope) and the 1D split
            for fig in ("cgg", "split"):
                assert f"]({gid}_{fig}.svg)" in page
                assert (root / name / f"{gid}_{fig}.svg").is_file()
            # verdicts and numbers rendered from the committed JSON, not recomputed
            assert f"Verdict (1D): **{r['verdict']}**" in page
            for key in ("plateau_acc", "plateau_inv", "dv_dep", "dv_inv"):
                assert f"| {r['verdicts'][key]['verdict']} |" in page
            m = r["metrics"]
            assert f"| {1e3 * m['dv_dep_v']:+.1f} |" in page  # mV, the unit in the header
            assert f"| {1e3 * m['dv_inv_v']:+.1f} |" in page
            assert f"{100 * m['depletion_max_rel']:.2f} %" in page
            assert g.role in page
            # mesh pictures: no mesh file is committed, and the page says so
            assert "mesh.msh" in page and "not committed" in page and "issues/39" in page
            meta = TCAD / "moscap2d" / name / "start" / gid / "cv.meta.json"
            if meta.is_file():
                assert json.loads(meta.read_text("utf-8"))["mesh_sha256"] in page
            else:
                assert "No 2D result" in page
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
            assert (root / name / f"meshconv_{dim}.svg").is_file()
            assert f"](meshconv_{dim}.svg)" in index
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
    svg = out / "tcad" / "nfet_05v0" / "w10p0_l10p00_cgg.svg"
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
