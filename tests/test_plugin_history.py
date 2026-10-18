# SPDX-License-Identifier: Apache-2.0
"""The "once worked" record of the gplugins DEVSIM plugin (``python -m gf180tcad.history``).

The sandbox-marked tests rebuild the record: they install gplugins v0.8.0 on its Sept-2023 stack
(and v1.4.2 from its frozen lock), with network only in the install step, then run the fixed
check drivers in ``experiments/plugin-history`` with no network. They are slow (minutes each)
and are run with ``pytest -m sandbox``. The others only read committed files.
"""

import importlib.util
import json
import math
import re
import socket
import sys
from pathlib import Path

import pytest

from gf180tcad import history, io

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "results" / "plugin-history"
EXPERIMENT = REPO / "experiments" / "plugin-history"
COMMITTED = ("v0.8.0.json", "v0.8.0-mesh0p5.json", "v1.4.2.json")
CHECKS = ("import", "pin_test", "ddcomponent_mesh", "ddsolver", "ramp", "refine")

sys.path.insert(0, str(EXPERIMENT))
import harness


def _load(name: str) -> dict:
    return json.loads((RESULTS / name).read_bytes())


# --- committed files (no Docker) -------------------------------------------------------------


_TIMING_KEY = re.compile(r"(time|elapsed|duration|date|second|clock|timestamp)", re.IGNORECASE)
# Host paths only: /work/out and /work/src are the fixed container mounts of tools/sandbox-run,
# which appear in exception messages recorded verbatim (e.g. the v1.4.2 ImportError).
_HOST_PATH = re.compile(r"(^|[\s'\"(=])/(home|tmp|usr|opt|root|var|proc|mnt|srv)/")


def _walk(obj, where=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{where}/{k}", k, None
            yield from _walk(v, f"{where}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{where}[{i}]")
    else:
        yield where, None, obj


@pytest.mark.parametrize("name", COMMITTED)
def test_history_json_has_no_timings_or_paths(name):
    raw = (RESULTS / name).read_bytes()
    data = json.loads(raw)
    # written by gf180tcad.io.write_json: sorted keys, repr floats, trailing newline
    text = json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
    assert raw == (text + "\n").encode("utf-8")
    host = socket.gethostname()
    for where, key, value in _walk(data):
        if key is not None:
            if not where.startswith("/versions/"):  # package names (python-dateutil)
                assert not _TIMING_KEY.search(key), f"{name}: timing-like key {where}"
        elif isinstance(value, str):
            assert not _HOST_PATH.search(value), f"{name}: absolute path in {where}: {value!r}"
            assert host not in value, f"{name}: host name in {where}"
            assert str(REPO) not in value, f"{name}: repo path in {where}"
        elif isinstance(value, float):
            assert math.isfinite(value)


@pytest.mark.parametrize("name", COMMITTED)
def test_history_json_shape(name):
    data = _load(name)
    assert set(data["checks"]) == set(CHECKS)
    for check in data["checks"].values():
        assert check["status"] in ("pass", "fail", "not_run")
        if check["status"] == "fail":
            assert check["exception_type"] and check["message"]
    assert data["gplugins_tag"] == name.split("-")[0].removesuffix(".json")
    assert re.fullmatch(r"[0-9a-f]{40}", data["gplugins_commit"])
    assert data["image"] == (REPO / "docker" / "IMAGE").read_text("utf-8").splitlines()[0]
    assert data["network"] == "none"


def test_committed_v080_once_worked():
    for name, scale in (("v0.8.0.json", 1.0), ("v0.8.0-mesh0p5.json", 0.5)):
        data = _load(name)
        _assert_v080(data)
        assert data["mesh_scale"] == scale
    full, half = _load("v0.8.0.json"), _load("v0.8.0-mesh0p5.json")
    assert full["pin"] == half["pin"]  # the PIN check uses DEVSIM's own mesh
    assert half["ddcomponent"]["node_count"] > full["ddcomponent"]["node_count"]


def test_committed_v142_import_broken():
    _assert_v142(_load("v1.4.2.json"))


def test_result_names():
    assert history.result_name("v0.8.0", 1.0) == "v0.8.0.json"
    assert history.result_name("v0.8.0", 0.5) == "v0.8.0-mesh0p5.json"
    assert history.result_name("v1.4.2", 1.0) == "v1.4.2.json"


def test_cli_parsing():
    a = history.parse_args(["--version", "v0.8.0", "--out", "x"])
    assert a.version == "v0.8.0" and a.mesh_scale == 1.0 and a.out == Path("x")
    a = history.parse_args(["--version", "v0.8.0", "--mesh-scale", "0.5", "--out", "x"])
    assert a.mesh_scale == 0.5
    with pytest.raises(SystemExit):
        history.parse_args(["--version", "v0.9.0", "--out", "x"])
    with pytest.raises(SystemExit):  # v1.4.2 runs only the import check, which has no mesh
        history.parse_args(["--version", "v1.4.2", "--mesh-scale", "0.5", "--out", "x"])
    for bad in ("0", "-1", "nan", "inf"):
        with pytest.raises(SystemExit):
            history.parse_args(["--version", "v0.8.0", "--mesh-scale", bad, "--out", "x"])


def test_scaled_resolutions_multiplies_every_value():
    base = harness.PN_RESOLUTIONS
    assert harness.scaled_resolutions(1.0) == base
    half = harness.scaled_resolutions(0.5)
    assert set(half) == set(base)
    for layer, spec in base.items():
        assert set(half[layer]) == set(spec)
        for k, v in spec.items():
            assert half[layer][k] == v * 0.5


def test_failure_record_names_exception_and_gplugins_frame(tmp_path):
    src = tmp_path / "gplugins" / "gplugins" / "devsim"
    src.mkdir(parents=True)
    (src / "get_solver.py").write_text("def f():\n    return c.x\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("fake_get_solver", src / "get_solver.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rec = harness.run_check(module.f, gplugins_root=tmp_path / "gplugins")[0]
    assert rec == {
        "status": "fail",
        "exception_type": "NameError",
        "message": "name 'c' is not defined",
        "location": "gplugins/devsim/get_solver.py:2",
    }


def test_depletion_width_on_a_row():
    # nodes of two rows; the row nearest y=1.1 is used; depleted where n, p < 1e-2 |NetDoping|
    x = [0.0, 1.0, 2.0, 3.0, 4.0, 0.0, 1.0]
    y = [1.0, 1.0, 1.0, 1.0, 1.0, 5.0, 5.0]
    n = [1e17, 1e14, 1e10, 1e5, 1e3, 1.0, 1.0]
    p = [1e3, 1e5, 1e10, 1e14, 1e17, 1.0, 1.0]
    nd = [1e17, 1e17, 1e17, -1e17, -1e17, 1e17, 1e17]
    width, y_cut, count = harness.depletion_width(x, y, n, p, nd, y_target=1.1)
    assert (width, y_cut, count) == (2.0, 1.0, 3)


def test_v080_lock_is_hashed_and_era_pinned():
    text = (EXPERIMENT / "v080.lock").read_text(encoding="utf-8")
    assert "--exclude-newer 2023-09-20T18:00:00Z" in text
    assert "--exclude-newer-package klayout=2024-04-01T00:00:00Z" in text
    pins = dict(re.findall(r"^([a-z0-9][a-z0-9._-]*)==(\S+) \\$", text, re.MULTILINE))
    assert pins["devsim"] == "2.6.3" and pins["gdsfactory"] == "7.6.1"
    assert pins["meshwell"] == "1.0.1" and pins["gmsh"] == "4.11.1"
    assert pins["klayout"].startswith("0.28.")
    assert "gplugins" not in pins and "\n-e " not in text  # the source comes from the tag
    blocks = re.split(r"\n(?=[a-z0-9])", text.split("\n", 2)[2])
    assert all("--hash=sha256:" in b for b in blocks if re.match(r"[a-z0-9]", b))


# --- sandbox: rebuild the record --------------------------------------------------------------


def _assert_v080(data: dict) -> None:
    checks = data["checks"]
    for name in ("import", "pin_test", "ddcomponent_mesh", "ddsolver", "ramp"):
        assert checks[name]["status"] == "pass", (name, checks[name])
    refine = checks["refine"]
    assert refine["status"] == "fail"
    assert refine["exception_type"] == "NameError"
    assert refine["message"] == "name 'c' is not defined"
    assert refine["location"] == "gplugins/devsim/get_solver.py:359"
    assert data["versions"]["gplugins"] == "0.8.0" and data["versions"]["devsim"] == "2.6.3"
    assert data["versions"]["python"] == "3.11.17"
    pin = data["pin"]
    assert [b["v"] for b in pin["bias"]] == [0.0, -1.0]
    for b in pin["bias"]:
        assert set(b["currents"]) == {"left", "right"}
        assert all(math.isfinite(c["total"]) for c in b["currents"].values())
        assert b["depletion_width_um"] > 0
    assert pin["bias"][1]["depletion_width_um"] > pin["bias"][0]["depletion_width_um"]
    dd = data["ddcomponent"]
    assert set(dd["contacts"]) == {"anode", "cathode"}
    assert dd["regions"]["si"] == ["slab90", "core"]
    assert dd["node_count"] == sum(dd["node_count_by_region"].values()) > 0
    assert [b["v"] for b in dd["bias"]] == [0.1, 0.2]
    for b in dd["bias"]:
        assert set(b["currents"]) == {"anode", "cathode"}


def _assert_v142(data: dict) -> None:
    imp = data["checks"]["import"]
    assert imp["status"] == "fail"
    assert imp["exception_type"] == "ImportError"
    assert "fuse_polygons" in imp["message"]
    assert all(data["checks"][n]["status"] == "not_run" for n in CHECKS if n != "import")
    assert data["versions"]["gplugins"] == "1.4.2"


@pytest.mark.sandbox
def test_v080_once_worked(tmp_path):
    out = tmp_path / "out"
    history.main(["--version", "v0.8.0", "--out", str(out), "--workdir", str(tmp_path / "wd")])
    data = json.loads((out / "v0.8.0.json").read_bytes())
    _assert_v080(data)
    # a local rerun reproduces the committed record byte for byte
    assert (out / "v0.8.0.json").read_bytes() == (RESULTS / "v0.8.0.json").read_bytes()


@pytest.mark.sandbox
def test_v142_import_broken(tmp_path):
    out = tmp_path / "out"
    history.main(["--version", "v1.4.2", "--out", str(out), "--workdir", str(tmp_path / "wd")])
    _assert_v142(json.loads((out / "v1.4.2.json").read_bytes()))
    assert (out / "v1.4.2.json").read_bytes() == (RESULTS / "v1.4.2.json").read_bytes()


def test_io_is_the_writer():
    # the record is written through gf180tcad.io (repr floats, sorted keys)
    assert history.write_json is io.write_json


def test_doc_quotes_the_record():
    page = (REPO / "docs" / "limitations" / "plugin-history.md").read_text(encoding="utf-8")
    full, half = _load("v0.8.0.json"), _load("v0.8.0-mesh0p5.json")
    w0, w1 = (b["depletion_width_um"] for b in full["pin"]["bias"])
    assert f"{w0:.3g} µm at 0 V and {w1:.3g} µm at −1 V" in page
    assert f"has {full['ddcomponent']['node_count']} mesh nodes" in page
    assert f"gives {half['ddcomponent']['node_count']} nodes" in page
