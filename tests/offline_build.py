# SPDX-License-Identifier: Apache-2.0
"""The offline docs build that tests/test_docgen.py and tests/test_doc_links.py share.

:func:`build` runs ``sphinx-build -W`` of ``docs/`` with every socket call blocked by
:data:`NO_NETWORK`, a ``sitecustomize`` module on the build's ``PYTHONPATH``. The session
fixture ``offline_html`` in tests/conftest.py calls it once per session (issue #169).
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"

#: A sitecustomize module that makes every socket call raise.
NO_NETWORK = textwrap.dedent(
    """
    import socket

    def _blocked(*a, **k):
        raise OSError("network disabled by the offline docs build")

    socket.socket.connect = _blocked
    socket.socket.connect_ex = _blocked
    socket.socket.sendto = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    socket.gethostbyname = _blocked
    """
)


def build(out: Path) -> Path:
    """``sphinx-build -W -b html`` of docs/ into ``out/html`` with the network blocked; the
    build's output goes to ``out/build.log``. Returns the HTML folder; AssertionError with the build's warning and
    error lines and the log's tail if the build fails."""
    (out / "sitecustomize.py").write_text(NO_NETWORK, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(out)}
    html = out / "html"
    log = out / "build.log"
    with log.open("wb") as f:
        r = subprocess.run(
            [sys.executable, "-m", "sphinx", "-W", "-b", "html", "-d", str(out / "dt"),
             str(DOCS), str(html)],
            check=False, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=900,
        )  # fmt: skip
    text = log.read_text(encoding="utf-8")
    warnings = [line for line in text.splitlines() if "WARNING" in line or "ERROR" in line]
    assert r.returncode == 0, "\n".join(warnings[:20]) + "\n" + text[-1500:]
    return html
