# SPDX-License-Identifier: Apache-2.0
"""Sphinx configuration for the gf180-tcad documentation."""

import fcntl
import os
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
    "api_links",
    "table_cells",
]
myst_enable_extensions = ["colon_fence", "dollarmath", "substitution"]
source_suffix = {".md": "markdown"}
root_doc = "index"

# Internal design spec and plans are not reader-facing; _build is output; _ext is code.
exclude_patterns = ["_build", "_ext", "superpowers", "superpowers/**"]

html_theme = "furo"
# docs/_static/narrow.css: tables at phone width (docs/_ext/table_cells.py adds it).
html_static_path = ["_static"]
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
    "meshwell": ("meshwell", "https://github.com/simbilod/meshwell"),
    "gmsh": ("gmsh", "https://gmsh.info/"),
    "output_cache": (
        "gf180-tcad-output-cache",
        "https://github.com/mithro/gf180-tcad-output-cache",
    ),
    "gplugins": ("gplugins", "https://github.com/gdsfactory/gplugins"),
    "gplugins_fork": ("the gplugins fork", "https://github.com/mithro/gplugins"),
    "meshwell_fork": ("the meshwell fork", "https://github.com/mithro/meshwell"),
    "gf180mcu_fork": ("the gf180mcu fork", "https://github.com/mithro/gf180mcu"),
    "input_mirror": (
        "the input mirror",
        "https://github.com/mithro/gf180-tcad/releases/tag/gf180-tcad/inputs/tcad-dev-20261019",
    ),
    "tidy3d": ("tidy3d", "https://docs.flexcompute.com/projects/tidy3d/"),
    "pyvista": ("pyvista", "https://docs.pyvista.org/"),
    "pydantic": ("pydantic", "https://docs.pydantic.dev/"),
    "meshio": ("meshio", "https://github.com/nschloe/meshio"),
    "gf180mcu_gdsfactory": ("gf180mcu gdsfactory PDK", "https://pypi.org/project/gf180mcu/"),
    "scipy": ("scipy", "https://scipy.org/"),
    "IIC_OSIC_TOOLS": ("IIC-OSIC-TOOLS", "https://github.com/iic-jku/IIC-OSIC-TOOLS"),
    "open_pdks": ("open_pdks", "https://github.com/fossi-foundation/open-pdks"),
    "Ciel": ("Ciel", "https://github.com/fossi-foundation/ciel"),
    "gf180mcu_pdk": ("GF180MCU PDK", "https://github.com/fossi-foundation/gf180mcu-pdk"),
    "gf180mcu_pdk_docs": (
        "GF180MCU PDK documentation",
        "https://gf180mcu-pdk.readthedocs.io/en/latest/",
    ),
    "gf180mcu_models": (
        "GF180MCU primitives library",
        "https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr",
    ),
    "BSIM4_site": (
        "BSIM4",
        "https://web.archive.org/web/20261004115850/https://bsim.berkeley.edu/models/bsim4/",
    ),
    "Docker": ("Docker", "https://docs.docker.com/"),
    "docker_run": ("docker run", "https://docs.docker.com/reference/cli/docker/container/run/"),
    "BuildKit": ("BuildKit", "https://docs.docker.com/build/buildkit/"),
    "systemd": ("systemd", "https://systemd.io/"),
    "uv": ("uv", "https://docs.astral.sh/uv/"),
    "Python": ("Python", "https://www.python.org/"),
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
# ignore-module-all: a module's __all__ may re-export names defined elsewhere
# (gf180tcad.spice.ngspice re-exports SpiceError); documenting them twice makes a short
# reference resolve to either copy, differently in parallel and serial builds.
autodoc_default_options = {"members": True, "undoc-members": True, "ignore-module-all": True}
# viewcode should show gf180tcad only; following imported members also renders pages for
# collections.abc and pathlib, and only in parallel builds.
viewcode_follow_imported_members = False
# Intersphinx is off (offline build). Standard-library and numpy types in signatures are linked
# to their upstream documentation by docs/_ext/api_links.py instead (a fixed table, no network);
# any other unresolved reference fails the build.
# Docstrings are linked as autodoc reads them by docs/_ext/api_links.py (repo paths, tests,
# gf180tcad names, first use of glossary terms and tools per page), so the generator modules,
# whose bytes are hashed into generator_sha256, are never edited for documentation.


# --- linkcheck (the linkcheck workflow; never part of the offline html build) ---------------
linkcheck_ignore = [
    # {repo}/{test} links are validated offline against the checkout by docs/_ext/repo_roles.py,
    # and pinned to the commit being built; checking them again would only hit GitHub's rate
    # limit.
    r"https://github\.com/mithro/gf180-tcad/(blob|tree)/",
    # Issue and pull request links answer HTTP 429 to GitHub-hosted runners (issue #87). The
    # linkcheck workflow checks that each number exists through the GitHub API instead, with the
    # workflow's own GITHUB_TOKEN, which has a far higher limit.
    r"https://github\.com/mithro/gf180-tcad/(issues|pull)/\d+",
    # Flaky host: www.osti.gov (where doi:10.2172/... resolves) times out for automated clients.
    # The DOI itself was checked against its Crossref record when it was added.
    r"https://doi\.org/10\.2172/",
    # Flaky host: link.aps.org (doi:10.1103/...) answers 403 to Python's HTTP client although it
    # serves curl (checked when the DOI was added).
    r"https://doi\.org/10\.1103/",
    # Flaky hosts: these answer 403 to GitHub-hosted runners (bot protection on datacenter IPs)
    # but 200 elsewhere; both were fetched when they were added.
    r"https://www\.semiconductors\.org/",
    r"https://semimod\.de/",
    # onlinelibrary.wiley.com (where doi:10.1002/0470068329, Sze & Ng, resolves) answers 403 to
    # GitHub-hosted runners; the DOI was checked against its Crossref record when it was added.
    r"https://doi\.org/10\.1002/0470068329",
    # pubs.aip.org (doi:10.1063/...) answers 403 to GitHub-hosted runners. Both DOIs were checked
    # against their Crossref records when added: Altermatt et al., J. Appl. Phys. 93, 1598
    # (2003), and Misiakos & Tsamakis, J. Appl. Phys. 74, 3293 (1993).
    r"https://doi\.org/10\.1063/1\.1529297",
    r"https://doi\.org/10\.1063/1\.354551",
    # asmedigitalcollection.asme.org (doi:10.1115/...) and royalsocietypublishing.org
    # (doi:10.1098/...) answer 403 to automated clients. The DOIs were checked against their
    # Crossref records when added: Roache, J. Fluids Eng. 116, 405 (1994); Celik et al.,
    # J. Fluids Eng. 130, 078001 (2008); Richardson, Phil. Trans. R. Soc. A 210, 307 (1911).
    r"https://doi\.org/10\.1115/1\.2910291",
    r"https://doi\.org/10\.1115/1\.2960953",
    r"https://doi\.org/10\.1098/rsta\.1911\.0009",
    # Flaky host: man7.org (the Linux man pages, docs/reproduce/sandbox.md) intermittently hits
    # linkcheck's read timeout from GitHub-hosted runners, even with retries; the pages were
    # fetched (HTTP 200) when they were added.
    r"https://man7\.org/",
]
# bsim.berkeley.edu has answered HTTP 401 to every client since 2026-10-24, so BSIM4 links point at
# web.archive.org snapshots of the same URLs (fetched with HTTP 200 and real content when added).
# ngspice.sourceforge.io answers 403 to Sphinx's default browser-like user agent, 200 to this.
user_agent = "gf180-tcad-linkcheck (Sphinx; https://github.com/mithro/gf180-tcad)"
# GitHub renders line and heading anchors with JavaScript, so linkcheck cannot see them.
linkcheck_anchors_ignore_for_url = [r"https://github\.com/.*"]
linkcheck_retries = 3
linkcheck_timeout = 30
linkcheck_rate_limit_timeout = 120.0

# docs/_generated/ is git-ignored and rebuilt from the committed SPICE reference at the start of
# every build (builder-inited). Read the Docs installs only the docs dependency group, which does
# not install gf180tcad itself, so put the source tree on sys.path: it is the least fragile
# option (no change to the RTD install, and a local editable install resolves to the same code).
sys.path.insert(0, str(_root / "src"))

# The explainer pages (docs/explained/) print every number by substitution, {{ x_<name> }}, from
# gf180tcad.explain (committed files, textbook entries and idealised examples), computed here.
from gf180tcad import explain as _explain  # after the sys.path line above

_explained = _explain.substitutions()
if _clash := sorted(set(_explained) & set(myst_substitutions)):
    raise ValueError(f"explainer substitutions clash with docs/conf.py _TOOLS: {_clash}")
myst_substitutions.update(_explained)

_generated = Path(__file__).parent / "_generated"
_lock_path = Path(__file__).parent / ".generated.lock"
_lock_file = None


def _acquire_lock():
    """Take the exclusive lock of this checkout's docs/_generated; held until the build ends."""
    global _lock_file
    if _lock_file is None:
        _lock_file = _lock_path.open("a+b")
        fcntl.flock(_lock_file, fcntl.LOCK_EX)  # blocks while another build of this checkout runs


def _release_lock(app, exception=None):
    """build-finished: let the next build of this checkout start."""
    global _lock_file
    if _lock_file is not None:
        _lock_file.close()  # closing drops the flock
        _lock_file = None


def _generate_results(app):
    """Regenerate docs/_generated (committed files in, only docs/_generated out).

    Concurrent builds of one checkout serialise on an exclusive lock held from here to
    build-finished (the whole read phase), and the tree is generated into a temporary sibling and
    swapped in, so a crashed build never leaves a half-written docs/_generated (issue #40).
    """
    from gf180tcad import docgen

    _acquire_lock()
    # Leftovers of crashed builds; safe to remove because the lock is held.
    for stale in _generated.parent.glob("_generated.*"):
        shutil.rmtree(stale, ignore_errors=True)
    tmp = _generated.with_name(f"_generated.tmp-{os.getpid()}")
    try:
        tmp.mkdir()
        docgen.generate(tmp)
        old = _generated.with_name(f"_generated.old-{os.getpid()}")
        if _generated.exists():  # also drops stale pages from older builds
            os.replace(_generated, old)
        os.replace(tmp, _generated)
        shutil.rmtree(old, ignore_errors=True)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        _release_lock(app)
        raise


def setup(app):
    app.connect("builder-inited", _generate_results)
    app.connect("build-finished", _release_lock)
