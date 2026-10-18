# SPDX-License-Identifier: Apache-2.0
"""Sphinx configuration for the gf180-tcad documentation."""

from pathlib import Path

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

# docs/_generated/ is git-ignored and filled at docs-build time by later tasks
# (results pages). Tolerate its absence: create it with a stub index page that
# the Results toctree links to. A generator that writes its own index.md
# replaces the stub.
_generated = Path(__file__).parent / "_generated"
_generated.mkdir(exist_ok=True)
_index = _generated / "index.md"
if not _index.exists():
    _index.write_text(
        "# Generated results\n\nNo generated result pages yet.\n",
        encoding="utf-8",
    )
