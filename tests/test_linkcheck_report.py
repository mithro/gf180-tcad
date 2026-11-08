# SPDX-License-Identifier: Apache-2.0
"""tools/linkcheck_report.py: the steps of .github/workflows/linkcheck.yml, on hand-made inputs.

Covers the status handling of ``report`` (broken, timeout only, clean, sphinx exit 1 with nothing
found, empty and missing output.json), the escalation of a URL that times out in several scheduled
runs in a row, the existence check of issue and pull request numbers with a fake ``gh``, and
``fetch-state`` with a fake ``gh``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "linkcheck_report.py"
_spec = importlib.util.spec_from_file_location("linkcheck_report", TOOL)
lr = importlib.util.module_from_spec(_spec)
sys.modules["linkcheck_report"] = lr
_spec.loader.exec_module(lr)


def _entry(status: str, uri: str, filename: str = "a.md", lineno: int = 3) -> dict:
    return {"filename": filename, "lineno": lineno, "status": status, "code": 0,
            "uri": uri, "info": ""}  # fmt: skip


def _write(path: Path, entries: list[dict]) -> Path:
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return path


BROKEN = _entry("broken", "https://dead.example/404")
TIMEOUT = _entry("timeout", "https://slow.example/")
WORKING = _entry("working", "https://fine.example/")


@pytest.mark.parametrize(
    ("status", "entries", "code", "text"),
    [
        (1, [BROKEN, TIMEOUT, WORKING], 1, "broken links: 1"),
        (1, [BROKEN], 1, "broken links: 1"),
        (1, [TIMEOUT, WORKING], 0, "::warning::linkcheck timeout: https://slow.example/ (a.md:3)"),
        (0, [WORKING], 0, ""),
        (1, [WORKING], 1, "with no broken link and no timeout"),
        (2, [], 2, "with no broken link and no timeout"),
    ],
    ids=["broken+timeout", "broken", "timeout only", "clean", "exit 1 nothing found", "empty"],
)
def test_report_replaces_the_exit_code(tmp_path, capsys, status, entries, code, text):
    assert lr.report(status, _write(tmp_path / "output.json", entries)) == code
    assert text in capsys.readouterr().out


def test_report_clean_run_does_not_need_output_json(tmp_path):
    assert lr.report(0, tmp_path / "missing.json") == 0


def test_report_missing_output_json_keeps_the_exit_code(tmp_path, capsys):
    assert lr.report(3, tmp_path / "missing.json") == 3
    assert "before writing" in capsys.readouterr().out


def _state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_timeouts_count_up_and_fail_at_the_threshold(tmp_path, capsys):
    out = _write(tmp_path / "output.json", [TIMEOUT, WORKING])
    prev = None
    for run in (1, 2, 3):
        new = tmp_path / f"state{run}.json"
        code = lr.report(1, out, prev, new, threshold=3)
        assert _state(new) == {"https://slow.example/": run}
        assert code == (1 if run == 3 else 0)
        prev = new
    text = capsys.readouterr().out
    assert (
        "::error::linkcheck: https://slow.example/ timed out in 3 scheduled runs in a row" in text
    )
    assert text.count("::error::") == 1


def test_a_url_that_answers_again_starts_from_zero(tmp_path):
    prev = tmp_path / "prev.json"
    prev.write_text(json.dumps({"https://slow.example/": 2, "https://gone.example/": 2}))
    new = tmp_path / "new.json"
    out = _write(tmp_path / "output.json", [TIMEOUT])
    assert lr.report(1, out, prev, new, threshold=4) == 0
    assert _state(new) == {"https://slow.example/": 3}  # gone.example answered: dropped


def test_a_clean_scheduled_run_clears_the_counts(tmp_path):
    new = tmp_path / "state" / "new.json"
    assert lr.report(0, tmp_path / "missing.json", None, new) == 0
    assert _state(new) == {}


@pytest.mark.parametrize("content", ["not json", "[1, 2]", '{"u": "x", "v": -1}'])
def test_unusable_previous_state_counts_from_zero(tmp_path, content):
    prev = tmp_path / "prev.json"
    prev.write_text(content)
    new = tmp_path / "new.json"
    out = _write(tmp_path / "output.json", [TIMEOUT])
    assert lr.report(1, out, prev, new) == 0
    assert _state(new) == {"https://slow.example/": 1}


def test_without_state_out_a_timeout_never_escalates(tmp_path):
    out = _write(tmp_path / "output.json", [TIMEOUT])
    prev = tmp_path / "prev.json"
    prev.write_text(json.dumps({"https://slow.example/": 99}))
    assert lr.report(1, out, prev, None) == 0


def test_a_broken_link_still_fails_on_a_scheduled_run(tmp_path):
    new = tmp_path / "new.json"
    assert lr.report(1, _write(tmp_path / "output.json", [BROKEN, TIMEOUT]), None, new) == 1


def test_cli_exit_code(tmp_path):
    out = _write(tmp_path / "output.json", [BROKEN])
    res = subprocess.run(
        [sys.executable, "-I", str(TOOL), "report", "--status", "1", "--json", str(out)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert res.returncode == 1, res.stderr
    assert "broken links: 1" in res.stdout


# --- the number check and fetch-state, with a fake gh ------------------------------------------

_FAKE_GH = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_STATE/calls"
case "$1 $2" in
    "api repos/"*)
        n="${2##*/}"
        case " $DEAD " in *" $n "*) exit 1 ;; esac
        echo "$n" ;;
    "run list") [ -n "${RUN_ID:-}" ] && echo "$RUN_ID"; exit 0 ;;
    "run download")
        [ -n "${ARTIFACT_JSON:-}" ] || exit 1
        dir=""; while [ $# -gt 0 ]; do [ "$1" = --dir ] && dir="$2"; shift; done
        printf '%s' "$ARTIFACT_JSON" > "$dir/timeouts.json" ;;
    *) exit 3 ;;
esac
"""


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    bindir, state = tmp_path / "bin", tmp_path / "gh-state"
    bindir.mkdir()
    state.mkdir()
    gh = bindir / "gh"
    gh.write_text(_FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_STATE", str(state))
    for var in ("DEAD", "RUN_ID", "ARTIFACT_JSON"):
        monkeypatch.delenv(var, raising=False)
    return state


def _tree(root: Path) -> None:
    (root / "docs" / "_build").mkdir(parents=True)
    (root / "docs" / "_generated").mkdir()
    (root / "src").mkdir()
    (root / "docs" / "a.md").write_text(
        "[i](https://github.com/mithro/gf180-tcad/issues/7) "
        "[p](https://github.com/mithro/gf180-tcad/pull/12) "
        "[other](https://github.com/someone/else/issues/500)\n"
    )
    (root / "src" / "m.py").write_text('"""https://github.com/mithro/gf180-tcad/issues/7"""\n')
    (root / "README.md").write_text("see https://github.com/mithro/gf180-tcad/issues/3\n")
    (root / "docs" / "_build" / "x.html").write_text("github.com/mithro/gf180-tcad/issues/900")
    (root / "docs" / "_generated" / "y.md").write_text("github.com/mithro/gf180-tcad/pull/901")


def test_linked_numbers_skip_build_output_and_other_repositories(tmp_path):
    _tree(tmp_path)
    assert lr.linked_numbers(tmp_path) == [3, 7, 12]


def test_numbers_all_exist(tmp_path, fake_gh, capsys):
    _tree(tmp_path)
    assert lr.check_numbers("mithro/gf180-tcad", tmp_path) == 0
    assert capsys.readouterr().out.splitlines() == ["OK #3", "OK #7", "OK #12"]
    assert "api repos/mithro/gf180-tcad/issues/12 --jq .number" in (fake_gh / "calls").read_text()


def test_numbers_a_dead_number_fails_but_checks_the_rest(tmp_path, fake_gh, monkeypatch, capsys):
    _tree(tmp_path)
    monkeypatch.setenv("DEAD", "7")
    assert lr.check_numbers("mithro/gf180-tcad", tmp_path) == 1
    assert capsys.readouterr().out.splitlines() == ["OK #3", "BROKEN #7", "OK #12"]


def test_fetch_state_downloads_the_latest_scheduled_run(tmp_path, fake_gh, monkeypatch, capsys):
    monkeypatch.setenv("RUN_ID", "4242")
    monkeypatch.setenv("ARTIFACT_JSON", '{"https://slow.example/": 2}')
    out = tmp_path / "previous" / "timeouts.json"
    assert lr.fetch_state("linkcheck.yml", out) == 0
    assert _state(out) == {"https://slow.example/": 2}
    calls = (fake_gh / "calls").read_text()
    assert "run list --workflow linkcheck.yml --event schedule --status completed" in calls
    assert "run download 4242 --name linkcheck-timeouts" in calls


@pytest.mark.parametrize(
    ("run_id", "artifact"),
    [("", ""), ("4242", "")],
    ids=["no earlier scheduled run", "earlier run without the artifact"],
)
def test_fetch_state_without_history_succeeds_with_no_file(
    tmp_path, fake_gh, monkeypatch, run_id, artifact
):
    monkeypatch.setenv("RUN_ID", run_id)
    monkeypatch.setenv("ARTIFACT_JSON", artifact)
    out = tmp_path / "previous" / "timeouts.json"
    assert lr.fetch_state("linkcheck.yml", out) == 0
    assert not out.exists()
    assert lr.read_state(out) == {}


# --- urls: the links of README.md and CONTRIBUTING.md (issue #136) ------------------------------


def _pages(tmp_path: Path, text: str) -> Path:
    """A root with docs/conf.py (one ignore pattern) and a README.md holding ``text``."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "conf.py").write_text(
        'import sys\nlinkcheck_ignore = [r"https://flaky\\.example/"]\n', encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(text, encoding="utf-8")
    return tmp_path


def test_page_urls_skip_the_published_docs_but_their_root(tmp_path):
    own = lr.OWN_DOCS
    f = tmp_path / "README.md"
    f.write_text(f"[a](https://x.example/a) [b]({own}page.html) [c]({own}) [a](https://x.example/a)",
                 encoding="utf-8")  # fmt: skip
    assert lr.page_urls([f]) == [own, "https://x.example/a"]


def test_ignore_patterns_are_the_docs_conf_list():
    patterns = lr.ignore_patterns(ROOT / "docs" / "conf.py")
    assert r"https://doi\.org/10\.2172/" in patterns and r"https://man7\.org/" in patterns


def _raiser(errors):
    calls = []

    def get(url):
        calls.append(url)
        e = errors[min(len(calls) - 1, len(errors) - 1)]
        if isinstance(e, BaseException):
            raise e
        return e

    return get, calls


@pytest.mark.parametrize(
    ("errors", "want", "tries"),
    [
        ([200], "ok", 1),
        ([TimeoutError("t"), 200], "ok", 2),
        ([TimeoutError("t")], "timeout", 3),
        ([lr.urllib.error.URLError(lr.socket.timeout("t"))], "timeout", 3),
        ([lr.urllib.error.HTTPError("u", 404, "Not Found", None, None)], "broken", 3),
        ([lr.urllib.error.URLError("no such host")], "broken", 3),
    ],
    ids=["ok", "retry ok", "timeout", "url timeout", "404", "dns"],
)
def test_check_url_classifies(errors, want, tries):
    get, calls = _raiser(errors)
    status, _ = lr.check_url("https://x.example/", get=get, sleep=lambda s: None)
    assert status == want and len(calls) == tries


def test_check_urls_fails_on_a_broken_link_and_skips_ignored_ones(tmp_path, capsys):
    root = _pages(tmp_path, "[a](https://ok.example/) [b](https://dead.example/) "
                            "[c](https://flaky.example/x)")  # fmt: skip
    seen = []

    def check(url):
        seen.append(url)
        return ("broken", "404") if "dead" in url else ("ok", "200")

    assert lr.check_urls([Path("README.md")], root, check=check) == 1
    assert seen == ["https://dead.example/", "https://ok.example/"]
    out = capsys.readouterr().out
    assert "IGNORED (docs/conf.py linkcheck_ignore) https://flaky.example/x" in out
    assert "BROKEN https://dead.example/ (404)" in out


def test_check_urls_timeouts_warn_count_on_and_fail_at_the_threshold(tmp_path, capsys):
    """A timeout warns; on a scheduled run it counts on from the previous run, beside the counts
    report wrote for this run, and fails at the threshold."""
    root = _pages(tmp_path, "[s](https://slow.example/)")
    previous = tmp_path / "prev.json"
    state = tmp_path / "state.json"
    previous.write_text(json.dumps({"https://slow.example/": 1}), encoding="utf-8")
    state.write_text(json.dumps({"https://sphinx.example/": 2}), encoding="utf-8")

    def slow(url):
        return "timeout", "timed out"

    assert lr.check_urls([Path("README.md")], root, check=slow) == 0  # not scheduled: a warning
    assert "::warning::link timeout: https://slow.example/" in capsys.readouterr().out
    assert lr.check_urls([Path("README.md")], root, previous, state, threshold=3, check=slow) == 0
    assert json.loads(state.read_text()) == {
        "https://sphinx.example/": 2,
        "https://slow.example/": 2,
    }
    state.write_text(json.dumps({}), encoding="utf-8")
    previous.write_text(json.dumps({"https://slow.example/": 2}), encoding="utf-8")
    assert lr.check_urls([Path("README.md")], root, previous, state, threshold=3, check=slow) == 1
    assert "timed out in 3 scheduled runs in a row" in capsys.readouterr().out


def test_urls_cli(tmp_path, monkeypatch):
    root = _pages(tmp_path, "[a](https://ok.example/)")
    monkeypatch.setattr(lr, "check_url", lambda url: ("ok", "200"))
    monkeypatch.setattr(lr, "check_urls", lambda *a, **k: 7 if a[1] == root else 0)
    assert lr.main(["urls", "README.md", "--root", str(root)]) == 7
