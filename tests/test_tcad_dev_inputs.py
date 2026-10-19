# SPDX-License-Identifier: Apache-2.0
"""docker/tcad-dev's input scripts, on the host with no network.

- fetch_sources.fetch: the mirror first, then the original URL, with the sha256 checked either
  way (``_download`` monkeypatched);
- local_inputs: the lock rewrite to the fetched copies, the CPython mirror layout, and the removal
  of uv's timestamped uv_cache.json with its RECORD line.
"""

import csv
import hashlib
import http.client
import importlib.util
import io
import json
from pathlib import Path

import pytest

DEV = Path(__file__).resolve().parents[1] / "docker" / "tcad-dev"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"gf180tcad_{name}", DEV / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fetch_sources = _load("fetch_sources")
local_inputs = _load("local_inputs")

GOOD = b"the right bytes"
GOOD_SHA = hashlib.sha256(GOOD).hexdigest()
ENTRY = {
    "mirror_url": "https://mirror.invalid/f",
    "url": "https://origin.invalid/f",
    "sha256": GOOD_SHA,
}


class FakeDownload:
    """``_download`` stand-in: per URL, a list of outcomes (bytes to write, or an exception)."""

    def __init__(self, outcomes: dict[str, list]):
        self.outcomes = {u: list(o) for u, o in outcomes.items()}
        self.calls: list[str] = []

    def __call__(self, url: str, dest: Path) -> str:
        self.calls.append(url)
        out = self.outcomes[url].pop(0)
        if isinstance(out, BaseException):
            dest.write_bytes(b"partial")
            raise out
        dest.write_bytes(out)
        return hashlib.sha256(out).hexdigest()


def _fetch(monkeypatch, tmp_path, outcomes):
    fake = FakeDownload(outcomes)
    monkeypatch.setattr(fetch_sources, "_download", fake)
    dest = tmp_path / "f"
    return fake, dest, lambda: fetch_sources.fetch(ENTRY, dest)


def test_fetch_mirror_succeeds(monkeypatch, tmp_path):
    fake, dest, run = _fetch(monkeypatch, tmp_path, {ENTRY["mirror_url"]: [GOOD]})
    assert run() == "mirror_url"
    assert fake.calls == [ENTRY["mirror_url"]]
    assert dest.read_bytes() == GOOD


def test_fetch_mirror_raises_then_url(monkeypatch, tmp_path):
    err = OSError("connection reset")
    fake, dest, run = _fetch(
        monkeypatch,
        tmp_path,
        {ENTRY["mirror_url"]: [err] * fetch_sources.ATTEMPTS, ENTRY["url"]: [GOOD]},
    )
    assert run() == "url"
    assert fake.calls == [ENTRY["mirror_url"]] * fetch_sources.ATTEMPTS + [ENTRY["url"]]
    assert dest.read_bytes() == GOOD


def test_fetch_mirror_wrong_hash_then_url(monkeypatch, tmp_path):
    bad = b"altered bytes"
    fake, dest, run = _fetch(
        monkeypatch,
        tmp_path,
        {ENTRY["mirror_url"]: [bad], ENTRY["url"]: [GOOD]},
    )
    assert run() == "url"
    # a wrong hash is not retried: the same URL would serve the same wrong bytes
    assert fake.calls == [ENTRY["mirror_url"], ENTRY["url"]]
    assert dest.read_bytes() == GOOD


def test_fetch_http_exception_then_url(monkeypatch, tmp_path):
    """http.client errors (a truncated or malformed response) are not OSErrors; they are retried
    and then fall through to the next URL like any other download error."""
    err = http.client.IncompleteRead(b"part")
    fake, dest, run = _fetch(
        monkeypatch,
        tmp_path,
        {ENTRY["mirror_url"]: [err] * fetch_sources.ATTEMPTS, ENTRY["url"]: [GOOD]},
    )
    assert run() == "url"
    assert fake.calls == [ENTRY["mirror_url"]] * fetch_sources.ATTEMPTS + [ENTRY["url"]]
    assert dest.read_bytes() == GOOD


def test_fetch_both_fail_exits_and_removes_the_file(monkeypatch, tmp_path):
    _, dest, run = _fetch(
        monkeypatch,
        tmp_path,
        {
            ENTRY["mirror_url"]: [OSError("down")] * fetch_sources.ATTEMPTS,
            ENTRY["url"]: [b"wrong"],
        },
    )
    with pytest.raises(SystemExit) as exc:
        run()
    msg = str(exc.value)
    assert "every URL failed" in msg and "down" in msg and "sha256" in msg
    assert not dest.exists()


# --- local_inputs -----------------------------------------------------------------------------

UPSTREAM = {
    name: {"url": f"https://example.invalid/{name}.tar.gz", "file": f"{name}-0123.tar.gz"}
    for name in local_inputs.URL_INSTALLED
}


def _lock_text() -> str:
    return (
        "".join(f"{n} @ {e['url']} \\\n    --hash=sha256:{'0' * 64}\n" for n, e in UPSTREAM.items())
        + "numpy==2.5.4 \\\n    --hash=sha256:"
        + "1" * 64
        + "\n"
    )


def test_lock_points_url_requirements_at_the_fetched_copies(tmp_path):
    out = local_inputs.lock(UPSTREAM, _lock_text(), tmp_path)
    for name, e in UPSTREAM.items():
        assert f"{name} @ {(tmp_path / e['file']).as_uri()} \\\n" in out
        assert e["url"] not in out
    # hashes and the PyPI pins are untouched
    assert out.count("--hash=sha256:" + "0" * 64) == len(UPSTREAM)
    assert "numpy==2.5.4 \\\n" in out


def test_lock_refuses_a_url_that_is_not_in_the_lock_once(tmp_path):
    text = _lock_text().replace(UPSTREAM["gmsh"]["url"], "https://elsewhere.invalid/gmsh.whl")
    with pytest.raises(SystemExit, match="gmsh"):
        local_inputs.lock(UPSTREAM, text, tmp_path)


def test_python_mirror_layout(tmp_path):
    src, mirror = tmp_path / "src", tmp_path / "mirror"
    src.mkdir()
    file = "cpython-3.13.16+20261013-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
    (src / file).write_bytes(b"python")
    local_inputs.python_mirror({"cpython": {"release": "20261013", "file": file}}, src, mirror)
    assert (mirror / "20261013" / file).read_bytes() == b"python"
    assert not (src / file).exists()


def _dist_info(site: Path, name: str, cache: dict | None) -> Path:
    d = site / f"{name}-1.0.dist-info"
    d.mkdir(parents=True)
    rows = [[f"{name}/__init__.py", "sha256=abc", "3"], [f"{d.name}/METADATA", "sha256=def", "9"]]
    if cache is not None:
        (d / "uv_cache.json").write_text(json.dumps(cache), encoding="utf-8")
        rows.append([f"{d.name}/uv_cache.json", "sha256=ghi", "127"])
    rows.append([f"{d.name}/RECORD", "", ""])
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    (d / "RECORD").write_text(out.getvalue(), encoding="utf-8")
    return d


UV_CACHE = {
    "timestamp": {"secs_since_epoch": 1792387069, "nanos_since_epoch": 1},
    "commit": None,
    "tags": None,
    "env": {},
    "directories": {},
}


def test_strip_uv_cache_removes_the_file_and_its_record_line(tmp_path):
    with_cache = _dist_info(tmp_path, "a", UV_CACHE)
    without = _dist_info(tmp_path, "b", None)
    before_b = (without / "RECORD").read_text(encoding="utf-8")
    local_inputs.strip_uv_cache(tmp_path)
    assert not (with_cache / "uv_cache.json").exists()
    rows = list(csv.reader(io.StringIO((with_cache / "RECORD").read_text(encoding="utf-8"))))
    assert [r[0] for r in rows] == [
        "a/__init__.py",
        "a-1.0.dist-info/METADATA",
        "a-1.0.dist-info/RECORD",
    ]
    assert (without / "RECORD").read_text(encoding="utf-8") == before_b


def test_strip_uv_cache_refuses_an_unknown_file(tmp_path):
    d = _dist_info(tmp_path, "a", {"something": "else"})
    with pytest.raises(SystemExit, match="not uv's cache-info file"):
        local_inputs.strip_uv_cache(tmp_path)
    assert (d / "uv_cache.json").exists()
