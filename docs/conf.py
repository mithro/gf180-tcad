# SPDX-License-Identifier: Apache-2.0
"""Sphinx configuration for the gf180-tcad documentation."""

import shutil
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]

project = "gf180-tcad"
author = "gf180-tcad contributors"
copyright = "gf180-tcad contributors, Apache-2.0"

extensions = ["myst_parser"]
myst_enable_extensions = ["colon_fence", "dollarmath"]
source_suffix = {".md": "markdown"}
root_doc = "index"

# Internal design spec and plans are not reader-facing; _build is output.
exclude_patterns = ["_build", "superpowers", "superpowers/**"]

html_theme = "furo"
html_title = "gf180-tcad"
# Keep build dates out of pages so two builds are identical.
html_last_updated_fmt = None
html_show_sphinx = False
html_show_copyright = False

# docs/_generated/ is git-ignored and rebuilt from the committed SPICE reference at the start of
# every build (builder-inited). Read the Docs installs only the docs dependency group, which does
# not install gf180tcad itself, so put the source tree on sys.path: it is the least fragile
# option (no change to the RTD install, and a local editable install resolves to the same code).
sys.path.insert(0, str(_root / "src"))

_generated = Path(__file__).parent / "_generated"


def _generate_results(app):
    """Regenerate docs/_generated (committed files in, only docs/_generated out)."""
    from gf180tcad import docgen

    shutil.rmtree(_generated, ignore_errors=True)  # also drops stale pages from older builds
    _generated.mkdir()
    docgen.generate(_generated)


def setup(app):
    app.connect("builder-inited", _generate_results)
