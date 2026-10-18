# SPDX-License-Identifier: Apache-2.0
"""ngspice binary raw-file parser, on checked-in fixtures (tests/spice/data/regen_fixtures.py)."""

import math
from pathlib import Path

import numpy as np
import pytest

from gf180tcad.spice.rawfile import read_raw

DATA = Path(__file__).parent / "data"


def _raw_bytes(header_lines: list[str], payload: np.ndarray) -> bytes:
    return ("\n".join(header_lines) + "\nBinary:\n").encode("ascii") + payload.astype(
        "<f8"
    ).tobytes()


def _header(flags: str, names: list[str], npoints: str) -> list[str]:
    lines = [
        "Title: synthetic",
        "Date: Thu Jan  1 00:00:00  1970",
        "Plotname: test",
        f"Flags: {flags}",
        f"No. Variables: {len(names)}",
        f"No. Points: {npoints}",
        "Variables:",
    ]
    lines += [f"\t{i}\t{n}\tvoltage" for i, n in enumerate(names)]
    return lines


def test_rawfile_roundtrip_real_fixture():
    data = read_raw(DATA / "rc_dc.raw")
    assert list(data) == ["v(v-sweep)", "v(in)", "v(out)", "i(v1)"]
    for v in data.values():
        assert v.dtype == np.float64
        assert v.shape == (3,)
    np.testing.assert_array_equal(data["v(in)"], [0.0, 1.0, 2.0])
    np.testing.assert_allclose(data["v(out)"], [0.0, 0.5, 1.0], rtol=0, atol=1e-12)
    np.testing.assert_allclose(data["i(v1)"], [0.0, -0.5e-3, -1e-3], rtol=0, atol=1e-15)


def test_rawfile_roundtrip_complex_fixture():
    data = read_raw(DATA / "rc_ac.raw")
    assert list(data) == ["frequency", "v(out)", "i(v1)"]
    for v in data.values():
        assert v.dtype == np.complex128
        assert v.shape == (3,)
    f = data["frequency"]
    np.testing.assert_array_equal(f, [1e5, 2e5, 3e5])
    h = 1 / (1 + 2j * math.pi * f.real * 1e3 * 1e-9)
    np.testing.assert_allclose(data["v(out)"], h, rtol=1e-9)
    # V1 current: -(1 - v(out)) / R1 (ngspice: positive current flows into the + terminal)
    np.testing.assert_allclose(data["i(v1)"], -(1 - h) / 1e3, rtol=1e-9)


def test_synthetic_real_with_padded_point_count(tmp_path):
    # ngspice pads "No. Points:" with spaces when it patches the count after the run (-r).
    payload = np.array([[0.0, 1.5], [1.0, -2.25], [2.0, 1e-300]])
    p = tmp_path / "x.raw"
    p.write_bytes(_raw_bytes(_header("real", ["a", "b"], "3    "), payload))
    data = read_raw(p)
    np.testing.assert_array_equal(data["a"], payload[:, 0])
    np.testing.assert_array_equal(data["b"], payload[:, 1])
    data["a"][0] = 7.0  # writable copy, not a view on a read-only buffer


def test_synthetic_complex(tmp_path):
    payload = np.array([[1.0, 0.0, 2.0, -3.0], [4.0, 0.0, -5.0, 6.0]])
    p = tmp_path / "x.raw"
    p.write_bytes(_raw_bytes(_header("complex", ["f", "z"], "2"), payload))
    data = read_raw(p)
    np.testing.assert_array_equal(data["f"], [1 + 0j, 4 + 0j])
    np.testing.assert_array_equal(data["z"], [2 - 3j, -5 + 6j])


@pytest.mark.parametrize("cut", [1, 8])
def test_truncated_payload_rejected(tmp_path, cut):
    raw = _raw_bytes(_header("real", ["a", "b"], "3"), np.zeros((3, 2)))
    p = tmp_path / "x.raw"
    p.write_bytes(raw[:-cut])
    with pytest.raises(ValueError, match="size"):
        read_raw(p)


def test_multiple_plots_rejected(tmp_path):
    one = _raw_bytes(_header("real", ["a"], "2"), np.zeros((2, 1)))
    p = tmp_path / "x.raw"
    p.write_bytes(one + one)
    with pytest.raises(ValueError, match="one plot"):
        read_raw(p)


def test_ascii_raw_rejected(tmp_path):
    p = tmp_path / "x.raw"
    p.write_text("\n".join(_header("real", ["a"], "1")) + "\nValues:\n 0\t1.0\n")
    with pytest.raises(ValueError, match="binary"):
        read_raw(p)


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda h: [x for x in h if not x.startswith("No. Points")], "No. Points"),
        (lambda h: [x.replace("Flags: real", "Flags: weird") for x in h], "Flags"),
        (lambda h: h[:-1], "variable"),
        (lambda h: [*h[:-1], "\t1\ta\tvoltage"], "duplicate"),
        (lambda h: [*h[:-1], "\t1\tb\tvoltage dims=2,2"], "dims"),
    ],
)
def test_bad_header_rejected(tmp_path, mutate, match):
    header = mutate(_header("real", ["a", "b"], "1"))
    p = tmp_path / "x.raw"
    p.write_bytes(_raw_bytes(header, np.zeros((1, 2))))
    with pytest.raises(ValueError, match=match):
        read_raw(p)
