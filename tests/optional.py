# SPDX-License-Identifier: Apache-2.0
"""Optional test dependencies (test helper): skip when absent locally, fail on CI.

GitHub Actions sets ``CI=true``. There the docs dependency group is installed, so a missing
``matplotlib`` or ``sphinx`` is a broken environment, and a skip would hide that the docs
tests never ran.
"""

import importlib
import os
from types import ModuleType

import pytest


def importorskip(name: str, reason: str | None = None) -> ModuleType:
    """:func:`pytest.importorskip` locally; a plain import (ImportError fails) when ``CI`` is set."""
    if os.environ.get("CI"):
        return importlib.import_module(name)
    return pytest.importorskip(name, reason=reason)
