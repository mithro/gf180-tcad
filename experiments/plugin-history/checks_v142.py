# SPDX-License-Identifier: Apache-2.0
"""Check driver for gplugins v1.4.2: where the DEVSIM plugin is broken on its own frozen lock.

Runs in the sandbox with no network, in the venv that ``python -m gf180tcad.history`` builds
with ``uv sync --frozen`` from the v1.4.2 ``uv.lock`` (see README.md here). Only the ``import``
check runs (``import gplugins.devsim``), because the import is what fails; the other checks of
``checks_v080.py`` are recorded as not run.

Usage: ``python checks_v142.py --out RAW.json``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    checks = {"import": harness.run_check(lambda: __import__("gplugins.devsim"))[0]}
    reason = "checks_v142.py runs only the import check (the import is what fails)"
    for name in harness.CHECKS[1:]:
        checks[name] = harness.not_run(reason)
    harness.write(args.out, {"checks": checks, "versions": harness.versions()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
