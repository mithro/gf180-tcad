# SPDX-License-Identifier: Apache-2.0
"""Sphinx configuration for the gf180-tcad documentation."""

import re
import shutil
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]

project = "gf180-tcad"
author = "gf180-tcad contributors"
copyright = "gf180-tcad contributors, Apache-2.0"

# docs/_ext/repo_roles.py: the {repo} and {test} roles (GitHub links checked offline against the
# checkout; a wrong path is a warning, so -W fails the build).
sys.path.insert(0, str(Path(__file__).parent / "_ext"))

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.extlinks",
    "sphinx.ext.viewcode",
    "repo_roles",
]
myst_enable_extensions = ["colon_fence", "dollarmath", "substitution"]
source_suffix = {".md": "markdown"}
root_doc = "index"

# Internal design spec and plans are not reader-facing; _build is output; _ext is code.
exclude_patterns = ["_build", "_ext", "superpowers", "superpowers/**"]

html_theme = "furo"
html_title = "gf180-tcad"
# Keep build dates out of pages so two builds are identical.
html_last_updated_fmt = None
html_show_sphinx = False
html_show_copyright = False

# --- links -----------------------------------------------------------------------------------
# Intersphinx stays off: it fetches inventories over the network, and the build must work
# offline (tests/test_docgen.py::test_docs_build_offline). Every cross-reference below resolves
# from this repository alone.

extlinks = {"doi": ("https://doi.org/%s", "doi:%s")}

# Every tool or project is linked to its upstream page from one place. Write {{ ngspice }} at the
# first mention on a page; tests/test_doc_links.py checks that the first mention is linked. Each
# URL here was fetched (HTTP 200) when it was added; the linkcheck workflow re-checks them weekly.
_TOOLS = {
    "ngspice": ("ngspice", "https://ngspice.sourceforge.io/"),
    "Xyce": ("Xyce", "https://xyce.sandia.gov/"),
    "DEVSIM": ("DEVSIM", "https://devsim.org/"),
    "Charon": ("Charon", "https://charon.sandia.gov/"),
    "gdsfactory": ("gdsfactory", "https://gdsfactory.github.io/gdsfactory/"),
    "KLayout": ("KLayout", "https://www.klayout.de/"),
    "IIC_OSIC_TOOLS": ("IIC-OSIC-TOOLS", "https://github.com/iic-jku/IIC-OSIC-TOOLS"),
    "open_pdks": ("open_pdks", "https://github.com/fossi-foundation/open-pdks"),
    "gf180mcu_pdk": ("GF180MCU PDK", "https://github.com/google/gf180mcu-pdk"),
    "gf180mcu_pdk_docs": (
        "GF180MCU PDK documentation",
        "https://gf180mcu-pdk.readthedocs.io/en/latest/",
    ),
    "gf180mcu_models": (
        "GF180MCU primitives library",
        "https://github.com/google/globalfoundries-pdk-libs-gf180mcu_fd_pr",
    ),
    "BSIM4_site": ("BSIM4", "https://bsim.berkeley.edu/models/bsim4/"),
    "Docker": ("Docker", "https://docs.docker.com/"),
    "docker_run": ("docker run", "https://docs.docker.com/reference/cli/docker/container/run/"),
    "BuildKit": ("BuildKit", "https://docs.docker.com/build/buildkit/"),
    "systemd": ("systemd", "https://systemd.io/"),
    "uv": ("uv", "https://docs.astral.sh/uv/"),
    "numpy": ("numpy", "https://numpy.org/"),
    "matplotlib": ("matplotlib", "https://matplotlib.org/"),
    "pytest": ("pytest", "https://docs.pytest.org/"),
    "ruff": ("ruff", "https://docs.astral.sh/ruff/"),
    "Sphinx": ("Sphinx", "https://www.sphinx-doc.org/"),
    "MyST": ("MyST", "https://myst-parser.readthedocs.io/"),
    "Read_the_Docs": ("Read the Docs", "https://about.readthedocs.com/"),
    "GitHub_Actions": ("GitHub Actions", "https://docs.github.com/en/actions"),
    "GitHub_hosted_runner": (
        "GitHub-hosted runner",
        "https://docs.github.com/en/actions/concepts/runners/github-hosted-runners",
    ),
    "ghcr": (
        "GitHub Container Registry",
        (
            "https://docs.github.com/en/packages/working-with-a-github-packages-registry/"
            "working-with-the-container-registry"
        ),
    ),
    "wafer_space": ("wafer.space", "https://wafer.space/"),
    "Tiny_Tapeout": ("Tiny Tapeout", "https://tinytapeout.com/"),
    "SemiMod": ("SemiMod", "https://semimod.de/"),
    "DMT_core": ("DMT-core", "https://gitlab.com/dmt-development/dmt-core"),
}
myst_substitutions = {key: f"[{text}]({url})" for key, (text, url) in _TOOLS.items()}

# --- API reference ---------------------------------------------------------------------------
# autodoc imports gf180tcad from ../src (the sys.path entry below); the docs dependency group is
# enough. Every py: reference must resolve (nitpicky), so a renamed function fails the build.
# Sphinx 9 autodoc documents module-level data only when it has a doc comment, so each page in
# docs/api lists the public constants with an explicit autodata; path-valued ones get :no-value:
# (their repr would be an absolute host path).
nitpicky = True
autodoc_member_order = "bysource"
# Show default values as written in the source, not their repr: REPO_ROOT-style defaults would
# otherwise put an absolute host path into the HTML.
autodoc_preserve_defaults = True
autodoc_default_options = {"members": True, "undoc-members": True}
# Intersphinx is off (offline build), so standard-library and numpy types in signatures cannot
# resolve. They are ignored explicitly here; gf180tcad's own names are not, so a reference to a
# renamed or removed gf180tcad object still fails the build.
nitpick_ignore_regex = [
    (r"py:class", r"(pathlib|collections\.abc|subprocess|argparse|numpy)\..*"),
    # Sphinx splits the string annotation of a NamedTuple field (tuple[float, ...]) at the comma.
    (r"py:class", r"'tuple\[float"),
]
# Short names in docstrings of the generator modules (reference.GENERATOR_MODULES) that resolve
# only from another module. Editing those docstrings would change generator_sha256 and force a
# regeneration of the SPICE reference for a documentation-only change, so they are ignored here;
# their targets are on the API pages (gf180tcad.spice.common.GRID_TOL and .SpiceResult).
nitpick_ignore = [
    ("py:data", "GRID_TOL"),
    ("py:attr", "SpiceResult.warnings"),
]
_MAGNITUDE = re.compile(r"\|(\w+)\|")


def _fix_docstring(app, what, name, obj, options, lines):
    """Adapt plain-text docstrings to reST without editing them (see nitpick_ignore above).

    Module constants without a doc comment would show their type's docstring (dict, tuple), and
    the docstrings write magnitudes as |Vgs|, which reST would read as a substitution.
    """
    if (
        what == "data"
        and lines
        and type(obj).__doc__
        and "\n".join(lines).strip() == (type(obj).__doc__.strip())
    ):
        lines.clear()
    lines[:] = [_MAGNITUDE.sub(r"\\|\1\\|", line) for line in lines]


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
    app.connect("autodoc-process-docstring", _fix_docstring)
