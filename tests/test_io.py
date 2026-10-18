# SPDX-License-Identifier: Apache-2.0
"""Deterministic CSV/JSON result I/O."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

from gf180tcad.io import read_csv, write_csv, write_json

VALUES = [1e-300, -0.0, 0.1 + 0.2, 1.0, -2.5e17, 5e-324, 1.7976931348623157e308]


def test_csv_roundtrip_exact(tmp_path):
    p = tmp_path / "a.csv"
    cols = {"vgs": VALUES, "id": list(reversed(VALUES))}
    write_csv(p, cols, {"device": "nfet_05v0", "a": "1"})
    got, meta = read_csv(p)
    assert meta == {"device": "nfet_05v0", "a": "1"}
    assert list(got) == ["vgs", "id"]
    for k, v in cols.items():
        assert np.array_equal(got[k], np.array(v))
        assert np.array_equal(np.signbit(got[k]), np.signbit(np.array(v)))
    assert np.signbit(got["vgs"][1])
    assert 0.1 + 0.2 == got["vgs"][2] != 0.3


def test_csv_format(tmp_path):
    p = tmp_path / "a.csv"
    write_csv(p, {"x": [1, 2.5]}, {"b": "2", "a": "1"})
    assert p.read_bytes() == b"# a: 1\n# b: 2\nx\n1.0\n2.5\n"


def test_csv_rejects_ragged(tmp_path):
    with pytest.raises(ValueError):
        write_csv(tmp_path / "a.csv", {"x": [1.0], "y": [1.0, 2.0]}, {})


def _de_locale_works() -> bool:
    code = "import locale; locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')"
    r = subprocess.run(
        [sys.executable, "-c", code], check=False, env={**os.environ, "LC_ALL": "de_DE.UTF-8"}
    )
    return r.returncode == 0


def test_csv_bytes_stable_under_locale(tmp_path):
    if not _de_locale_works():
        pytest.skip("de_DE.UTF-8 locale not installed on this host")
    script = textwrap.dedent(
        """
        import locale, sys
        from pathlib import Path
        from gf180tcad.io import write_csv, write_json
        locale.setlocale(locale.LC_ALL, "de_DE.UTF-8")
        assert locale.localeconv()["decimal_point"] == ","
        write_csv(Path(sys.argv[1]), {"x": [1.5, 1e-300, -0.0]}, {"k": "v"})
        write_json(Path(sys.argv[2]), {"x": [1.5, 1e-300]})
        """
    )
    outs = {}
    for name, loc in (("de", "de_DE.UTF-8"), ("c", "C")):
        c, j = tmp_path / f"{name}.csv", tmp_path / f"{name}.json"
        env = {**os.environ, "LC_ALL": loc}
        if name == "c":
            script_c = script.replace('locale.setlocale(locale.LC_ALL, "de_DE.UTF-8")', "")
            script_c = script_c.replace('assert locale.localeconv()["decimal_point"] == ","', "")
            subprocess.run([sys.executable, "-c", script_c, str(c), str(j)], env=env, check=True)
        else:
            subprocess.run([sys.executable, "-c", script, str(c), str(j)], env=env, check=True)
        outs[name] = (c.read_bytes(), j.read_bytes())
    assert outs["de"] == outs["c"]
    assert b"1.5" in outs["de"][0]


def test_csv_no_crlf(tmp_path):
    p = tmp_path / "a.csv"
    write_csv(p, {"x": [1.0]}, {})
    assert b"\r" not in p.read_bytes()


def test_json_sorted_and_stable(tmp_path):
    p = tmp_path / "a.json"
    obj = {"b": [0.1 + 0.2, 1e-300, 3], "a": {"z": -0.0, "y": "é"}}
    write_json(p, obj)
    first = p.read_bytes()
    write_json(p, {"a": {"y": "é", "z": -0.0}, "b": [0.1 + 0.2, 1e-300, 3]})
    assert p.read_bytes() == first
    text = first.decode("utf-8")
    assert text.endswith("}\n") and "\r" not in text
    assert text.index('"a"') < text.index('"b"')
    assert "0.30000000000000004" in text and "1e-300" in text and "-0.0" in text
    assert "é" in text
    assert json.loads(text) == obj
    assert text.startswith('{\n  "a"')


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_json_rejects_nonfinite(tmp_path, bad):
    with pytest.raises(ValueError):
        write_json(tmp_path / "a.json", {"x": [bad]})


def test_json_handles_numpy(tmp_path):
    p = tmp_path / "a.json"
    write_json(
        p, {"x": np.array([0.1 + 0.2]), "n": np.int64(3), "f": np.float64(0.5), "p": Path("a")}
    )
    assert json.loads(p.read_text(encoding="utf-8")) == {
        "x": [0.1 + 0.2],
        "n": 3,
        "f": 0.5,
        "p": "a",
    }
