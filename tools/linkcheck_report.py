#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Steps of .github/workflows/linkcheck.yml, as one testable script (stdlib only).

report  Turn sphinx-build's linkcheck result into the job result.
        Sphinx exits 1 for a timeout as well as for a dead link, and a slow external site is not a
        defect of the change (issue #93), so the exit code is replaced by the entries of
        output.json: a "broken" entry fails, a timeout is a ``::warning::``. On a scheduled run
        (``--state-out``) the number of consecutive runs in which each URL timed out is kept in a
        small JSON file, which the workflow uploads as an artifact and the next run downloads
        (``fetch-state``); a URL that timed out in ``--threshold`` runs in a row fails, so a dead
        site is eventually caught.
fetch-state  Download that file from the latest completed scheduled run (none is fine).
numbers Check through the GitHub API that each issue and pull request number the docs link to
        exists (Sphinx ignores those links because github.com answers them with HTTP 429, #87).
urls    Fetch each https link of README.md and CONTRIBUTING.md, which Sphinx does not build
        (issue #136). Links into the published docs are checked offline against docs/ by
        tests/test_doc_links.py, and links matching docs/conf.py's ``linkcheck_ignore`` are skipped.
        A broken link fails; a timeout is a ``::warning::`` and, on a scheduled run, counts in the
        same state file as ``report``'s, so a link that times out in ``--threshold`` runs in a row
        fails.

usage: linkcheck_report.py report --status N --json FILE [--previous FILE --state-out FILE]
       linkcheck_report.py fetch-state --workflow linkcheck.yml --out FILE
       linkcheck_report.py numbers --repo OWNER/NAME
       linkcheck_report.py urls FILE... [--previous FILE --state-out FILE]
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

THRESHOLD = 3  # consecutive scheduled runs in which a URL times out before it fails the job
ARTIFACT = "linkcheck-timeouts"
STATE_FILE = "timeouts.json"
NUMBER_PATHS = ("docs", "src", "README.md", "CONTRIBUTING.md")
NUMBER_EXCLUDED_DIRS = ("_build", "_generated")
NUMBER_RE = re.compile(r"github\.com/mithro/gf180-tcad/(?:issues|pull)/([0-9]+)")
#: The published docs: a link into them is checked offline (tests/test_doc_links.py), except the
#: root page itself.
OWN_DOCS = "https://gf180-tcad.readthedocs.io/en/latest/"
#: The Sphinx configuration whose ``linkcheck_ignore`` the ``urls`` check also honours.
CONF = Path("docs/conf.py")
URL_RE = re.compile(r"\((https://[^)\s]+)\)")
ATTEMPTS, WAIT_S, TIMEOUT_S = 3, 10, 30
USER_AGENT = "gf180-tcad-linkcheck"


def read_entries(path: Path) -> list[dict]:
    """The entries of output.json (one JSON object per line); a blank line is skipped."""
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def read_state(path: Path | None) -> dict[str, int]:
    """Previous consecutive-timeout counts; a missing or unreadable file is an empty state."""
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"::warning::ignoring unreadable timeout state {path}")
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, int) and v > 0}


def write_state(path: Path | None, counts: dict[str, int]) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(counts, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def report(
    status: int,
    json_path: Path,
    previous: Path | None = None,
    state_out: Path | None = None,
    threshold: int = THRESHOLD,
) -> int:
    """The job's exit code for sphinx-build's exit ``status`` and its output.json."""
    if status == 0:
        write_state(state_out, {})
        return 0
    if not json_path.is_file():
        print(f"sphinx-build failed (exit {status}) before writing {json_path}")
        return status
    entries = read_entries(json_path)
    timeouts = [e for e in entries if e.get("status") == "timeout"]
    broken = [e for e in entries if e.get("status") == "broken"]
    for e in timeouts:
        print(f"::warning::linkcheck timeout: {e['uri']} ({e['filename']}:{e['lineno']})")
    print(f"sphinx-build exit {status}; broken links: {len(broken)}")
    if broken:
        return 1
    if not timeouts:
        print(f"sphinx-build failed (exit {status}) with no broken link and no timeout")
        return status
    if state_out is None:
        return 0
    before = read_state(previous)
    counts = {uri: before.get(uri, 0) + 1 for uri in sorted({e["uri"] for e in timeouts})}
    write_state(state_out, counts)
    dead = [uri for uri, n in counts.items() if n >= threshold]
    for uri in dead:
        print(f"::error::linkcheck: {uri} timed out in {counts[uri]} scheduled runs in a row")
    return 1 if dead else 0


def fetch_state(workflow: str, out: Path) -> int:
    """Download the state of the latest completed scheduled run to ``out``; never fails."""
    listing = subprocess.run(
        ["gh", "run", "list", "--workflow", workflow, "--event", "schedule",
         "--status", "completed", "--limit", "1", "--json", "databaseId",
         "--jq", ".[0].databaseId // empty"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    run_id = listing.stdout.strip()
    if listing.returncode != 0 or not run_id:
        print("no earlier scheduled run: timeout counts start at zero")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        got = subprocess.run(
            ["gh", "run", "download", run_id, "--name", ARTIFACT, "--dir", tmp],
            capture_output=True, text=True, check=False,
        )  # fmt: skip
        src = Path(tmp) / STATE_FILE
        if got.returncode != 0 or not src.is_file():
            print(f"run {run_id} has no {ARTIFACT} artifact: timeout counts start at zero")
            return 0
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(src.read_bytes())
    print(f"timeout counts from run {run_id}")
    return 0


def linked_numbers(root: Path, paths=NUMBER_PATHS) -> list[int]:
    """The sorted issue and pull request numbers that files under ``paths`` link to."""
    found: set[int] = set()
    for rel in paths:
        base = root / rel
        files = [base] if base.is_file() else sorted(base.rglob("*")) if base.is_dir() else []
        for f in files:
            parts = f.relative_to(root).parts
            if not f.is_file() or any(p in NUMBER_EXCLUDED_DIRS for p in parts):
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            found.update(int(n) for n in NUMBER_RE.findall(text))
    return sorted(found)


def check_numbers(repo: str, root: Path) -> int:
    """1 when any linked number does not exist in ``repo`` (an issue or a pull request)."""
    bad = False
    for n in linked_numbers(root):
        got = subprocess.run(
            ["gh", "api", f"repos/{repo}/issues/{n}", "--jq", ".number"],
            capture_output=True, text=True, check=False,
        )  # fmt: skip
        if got.returncode == 0:
            print(f"OK #{n}")
        else:
            print(f"BROKEN #{n}")
            bad = True
    return 1 if bad else 0


def ignore_patterns(conf: Path) -> list[str]:
    """The ``linkcheck_ignore`` list of a Sphinx ``conf.py``, read without running it."""
    for node in ast.parse(conf.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "linkcheck_ignore" for t in node.targets
        ):
            return list(ast.literal_eval(node.value))
    raise ValueError(f"{conf} sets no linkcheck_ignore")


def page_urls(paths: list[Path], own: str = OWN_DOCS) -> list[str]:
    """The sorted https links of Markdown files, without the links into the published docs
    (their root page excepted)."""
    found = set()
    for path in paths:
        found.update(URL_RE.findall(path.read_text(encoding="utf-8")))
    return sorted(u for u in found if not u.startswith(own) or u == own)


def _is_timeout(error: BaseException) -> bool:
    if isinstance(error, (TimeoutError, socket.timeout)):
        return True
    return isinstance(error, urllib.error.URLError) and isinstance(
        error.reason, (TimeoutError, socket.timeout)
    )


def fetch(url: str) -> int:
    """The HTTP status of a GET of ``url``; raises on an error or a timeout."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return r.status


def check_url(
    url: str,
    get: Callable[[str], int] = fetch,
    attempts: int = ATTEMPTS,
    wait_s: float = WAIT_S,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, str]:
    """``("ok", status)``, ``("timeout", message)`` or ``("broken", message)`` for ``url``, with
    ``attempts`` tries ``wait_s`` apart. The last try decides between a timeout and a break."""
    for attempt in range(attempts):
        try:
            return "ok", str(get(url))
        except Exception as e:  # noqa: BLE001 - every failure of the fetch is recorded
            if attempt == attempts - 1:
                return ("timeout" if _is_timeout(e) else "broken"), str(e)
            sleep(wait_s)
    raise AssertionError("unreachable")


def check_urls(
    paths: list[Path],
    root: Path = Path("."),
    previous: Path | None = None,
    state_out: Path | None = None,
    threshold: int = THRESHOLD,
    check: Callable[[str], tuple[str, str]] = check_url,
) -> int:
    """1 when a link of ``paths`` is broken, or when one timed out in ``threshold`` scheduled
    runs in a row. ``state_out`` already holds the counts ``report`` wrote for this run; each
    link that times out here counts on from ``previous``."""
    patterns = ignore_patterns(root / CONF)
    counts = read_state(state_out)
    before = read_state(previous)
    broken, timed_out = [], []
    for url in page_urls([root / p for p in paths]):
        if any(re.match(p, url) for p in patterns):
            print(f"IGNORED (docs/conf.py linkcheck_ignore) {url}")
            continue
        status, detail = check(url)
        if status == "ok":
            print(f"{detail} {url}")
        elif status == "timeout":
            print(f"::warning::link timeout: {url} ({detail})")
            timed_out.append(url)
        else:
            print(f"BROKEN {url} ({detail})")
            broken.append(url)
    if state_out is None:
        return 1 if broken else 0
    for url in timed_out:
        counts[url] = max(counts.get(url, 0), before.get(url, 0) + 1)
    write_state(state_out, counts)
    dead = [url for url in timed_out if counts[url] >= threshold]
    for url in dead:
        print(f"::error::link {url} timed out in {counts[url]} scheduled runs in a row")
    return 1 if broken or dead else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report")
    r.add_argument("--status", type=int, required=True, help="sphinx-build's exit code")
    r.add_argument("--json", type=Path, required=True, help="linkcheck output.json")
    r.add_argument("--previous", type=Path, help="timeout counts of the previous scheduled run")
    r.add_argument("--state-out", type=Path, help="write the new counts here (scheduled runs)")
    r.add_argument("--threshold", type=int, default=THRESHOLD)
    f = sub.add_parser("fetch-state")
    f.add_argument("--workflow", required=True)
    f.add_argument("--out", type=Path, required=True)
    n = sub.add_parser("numbers")
    n.add_argument("--repo", required=True)
    n.add_argument("--root", type=Path, default=Path("."))
    u = sub.add_parser("urls")
    u.add_argument("paths", nargs="+", type=Path, help="Markdown files whose https links to fetch")
    u.add_argument("--root", type=Path, default=Path("."))
    u.add_argument("--previous", type=Path, help="timeout counts of the previous scheduled run")
    u.add_argument("--state-out", type=Path, help="this run's counts, written by report first")
    u.add_argument("--threshold", type=int, default=THRESHOLD)
    a = ap.parse_args(argv)
    if a.cmd == "report":
        return report(a.status, a.json, a.previous, a.state_out, a.threshold)
    if a.cmd == "fetch-state":
        return fetch_state(a.workflow, a.out)
    if a.cmd == "urls":
        return check_urls(a.paths, a.root, a.previous, a.state_out, a.threshold)
    return check_numbers(a.repo, a.root)


if __name__ == "__main__":
    sys.exit(main())
