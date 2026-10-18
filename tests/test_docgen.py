# SPDX-License-Identifier: Apache-2.0
"""Generated results pages (Task 13): deterministic SVGs, page coverage, offline docs build."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("matplotlib", reason="needs the docs dependency group")

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


def test_pages_cover_all_geometries(tmp_path):
    docgen.generate(tmp_path)
    expected = {f"{name}/{geometry_id(g)}.md" for name, d in DEVICES.items() for g in d.geometries}
    pages = {
        str(p.relative_to(tmp_path / "results")) for p in (tmp_path / "results").glob("*/*.md")
    }
    assert len(expected) == 12
    assert pages == expected
    page = (tmp_path / "results" / "nfet_05v0" / "w10p0_l0p60.md").read_text(encoding="utf-8")
    for needle in ("idvg_lin", "idvg_sat", "idvd", "cv", "Envelope", '"Same process" window'):
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


def test_number_format_is_locale_independent():
    assert docgen.fmt(1234.56789) == "1235"
    assert docgen.fmt(0.000123456) == "0.0001235"
    assert docgen.fmt(float("inf")) == "inf" and docgen.fmt(-float("inf")) == "-inf"


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
    pytest.importorskip("sphinx")
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
