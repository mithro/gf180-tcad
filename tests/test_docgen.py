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
    for needle in ("idvg_lin", "idvg_sat", "idvd", "cv", "Envelope", "Spec window"):
        assert needle in page
    assert (tmp_path / "results" / "nfet_05v0" / "w10p0_l0p60_idvd.svg").is_file()


def test_summary_lists_status_and_engine_diffs(tmp_path):
    docgen.generate(tmp_path)
    s = (tmp_path / "results" / "index.md").read_text(encoding="utf-8")
    assert "pdk-spec-check" in s and "engine-cross-check" in s
    # Six compared spec entries, all inside; nfet idvg_sat rows carry the known-case marker.
    assert s.count("| inside |") == 6
    assert s.count("(known)") == 6


def test_number_format_is_locale_independent():
    assert docgen.fmt(1234.56789) == "1235"
    assert docgen.fmt(0.000123456) == "0.0001235"
    assert docgen.fmt(float("inf")) == "inf" and docgen.fmt(-float("inf")) == "-inf"


def test_docs_build_offline(tmp_path):
    pytest.importorskip("sphinx")
    (tmp_path / "sitecustomize.py").write_text(
        textwrap.dedent(
            """
            import socket

            def _blocked(*a, **k):
                raise OSError("network disabled by test_docs_build_offline")

            socket.socket.connect = _blocked
            socket.socket.connect_ex = _blocked
            socket.create_connection = _blocked
            """
        ),
        encoding="utf-8",
    )
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
