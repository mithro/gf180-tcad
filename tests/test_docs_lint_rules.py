# SPDX-License-Identifier: Apache-2.0
"""The three house rules that ``tools/docs_lint.py --rules`` checks (spec §10.3, owner
2026-11-03 02:00): FIGURE (a described situation has a figure), EQUATION (every equation is a
labelled display block with a "where" list defining each symbol and its unit) and FILELINK
(every file or path mentioned is a link). Each check has a positive control (it fires) and a
negative control (the house form passes)."""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
import textwrap
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LINT = ROOT / "tools" / "docs_lint.py"


@cache
def lint():
    spec = importlib.util.spec_from_file_location("docs_lint", LINT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def found(text: str, check: str) -> list[tuple[int, str]]:
    text = textwrap.dedent(text).lstrip("\n")
    return [(line, msg) for line, c, msg in lint().rule_findings(text) if c == check]


# --- FIGURE -------------------------------------------------------------------------------


def test_figure_fires_on_described_situation_without_figure():
    page = """
        # Title

        ## The mesh

        The mesh has finer cells near the oxide than in the body.
        """
    hits = found(page, "FIGURE")
    assert [line for line, _ in hits] == [5]
    assert "mesh" in hits[0][1]


@pytest.mark.parametrize(
    "noun", ["curve", "meshes", "stack", "profile", "cross-section", "regions", "sweep",
             "layout", "die", "junctions"],
)  # fmt: skip
def test_figure_word_list(noun):
    assert found(f"# T\n\nThe {noun} is shown here in words only.\n", "FIGURE")


def test_figure_section_with_named_figure_passes():
    page = """
        # Title

        ## The mesh

        The mesh has finer cells near the oxide, see {numref}`fig-mesh`.

        ```{figure} /_generated/mesh.svg
        :name: fig-mesh
        :alt: A mesh.

        The mesh of the 1D cell.
        ```
        """
    assert found(page, "FIGURE") == []


def test_figure_numref_to_another_section_passes():
    page = """
        # Title

        ## The curve again

        The curve of {numref}`fig-cv` falls at the threshold.
        """
    assert found(page, "FIGURE") == []


@pytest.mark.parametrize(
    "page",
    [
        "# T\n\n## Verdicts\n\n| Device | Curve |\n|---|---|\n| nfet | agree |\n",
        "# T\n\n## Mesh profile\n\nThe run takes ten minutes on one core.\n",
        "# T\n\n## Files\n\nThe function `mesh_profile` writes the output.\n",
        "# T\n\n## Build\n\n```text\nmake curve mesh stack\n```\n",
        "# T\n\n```{glossary}\nmesh\n  The cells the equations are solved on.\n```\n",
        "# T\n\n<!-- the mesh is described in a comment -->\n",
        "# T\n\nSee {doc}`the junction page </explained/pn-junction>`.\n",
    ],
    ids=["table", "heading-only", "code-span", "code-fence", "glossary", "comment", "role-target"],
)
def test_figure_is_quiet_on_non_descriptive_text(page):
    assert found(page, "FIGURE") == []


def test_figure_checks_each_section_on_its_own():
    page = """
        # Title

        ```{figure} a.svg
        :name: fig-a
        :alt: a

        The stack.
        ```

        ## Later

        The stack is thinner here.
        """
    assert [line for line, _ in found(page, "FIGURE")] == [12]


# --- EQUATION -----------------------------------------------------------------------------

GOOD_EQUATION = r"""
    # T

    The capacitance per area of the oxide is {math:numref}`eq-cox`.

    $$
    C_{ox} = \frac{\varepsilon_{ox} \, \varepsilon_0}{t_{ox}}
    $$ (eq-cox)

    where

    - $C_{ox}$ is the oxide capacitance per area, in F/m²;
    - $\varepsilon_{ox}$ is the relative permittivity of the oxide, dimensionless;
    - $\varepsilon_0$ is the permittivity of vacuum, in F/m;
    - $t_{ox}$ is the oxide thickness,
      in m.
    """


def test_equation_house_form_passes():
    assert found(GOOD_EQUATION, "EQUATION") == []


@pytest.mark.parametrize(
    ("latex", "symbols"),
    [
        (r"V_{bi} = V_t \, \ln \frac{N_A \, N_D}{n_i^2}", {"V_bi", "V_t", "N_A", "N_D", "n_i"}),
        (
            (r"W = \sqrt{\frac{2 \, \varepsilon_{si} \, V_{bi}}{q} \left( \frac{1}{N_A} + "
            r"\frac{1}{N_D} \right)}"),
            {"W", r"\varepsilon_si", "V_bi", "q", "N_A", "N_D"},
        ),
        (r"C_{ox} = \frac{\varepsilon_{ox} \, \varepsilon_0}{t_{ox}}",
         {"C_ox", r"\varepsilon_ox", r"\varepsilon_0", "t_ox"}),
        (r"V_{\mathrm{fb}} = \phi_m - \phi_s \quad \text{(volts)}", {"V_fb", r"\phi_m", r"\phi_s"}),
        (r"n = N_C \exp\left( -\frac{E_C - E_F}{k T} \right)",
         {"n", "N_C", "E_C", "E_F", "k", "T"}),
    ],
)  # fmt: skip
def test_equation_symbols_parsed_from_latex(latex, symbols):
    assert lint().latex_symbols(latex) == symbols


def test_equation_fires_without_where_list():
    page = """
        # T

        $$
        V_{bi} = V_t \\, \\ln \\frac{N_A \\, N_D}{n_i^2}
        $$ (eq-vbi)

        Here $N_A$ and $N_D$ are the densities.
        """
    hits = found(page, "EQUATION")
    assert [line for line, _ in hits] == [3]
    assert "where" in hits[0][1] and "V_bi" in hits[0][1]


def test_equation_fires_on_undefined_symbol():
    page = GOOD_EQUATION.replace(
        "    - $\\varepsilon_0$ is the permittivity of vacuum, in F/m;\n", ""
    )
    hits = found(page, "EQUATION")
    assert len(hits) == 1 and "\\varepsilon_0" in hits[0][1]


def test_equation_fires_on_item_without_unit():
    page = GOOD_EQUATION.replace("thickness,\n      in m.", "thickness.")
    hits = found(page, "EQUATION")
    assert len(hits) == 1 and "unit" in hits[0][1] and "t_{ox}" in hits[0][1]


def test_equation_fires_without_label():
    page = GOOD_EQUATION.replace("$$ (eq-cox)", "$$")
    hits = found(page, "EQUATION")
    assert len(hits) == 1 and "label" in hits[0][1]


def test_equation_fires_on_math_directive():
    page = """
        # T

        ```{math}
        :label: eq-w
        W = 1
        ```

        where

        - $W$ is the width, in m.
        """
    hits = found(page, "EQUATION")
    assert len(hits) == 1 and "$$" in hits[0][1]


def test_equation_one_line_block():
    page = "# T\n\n$$ W = 2 L $$ (eq-w)\n\nwhere\n\n- $W$ is the width, in m;\n- $L$ is the length, in m.\n"
    assert found(page, "EQUATION") == []


def test_inline_math_is_not_an_equation():
    assert found("# T\n\nThe width $W$ is shown.\n", "EQUATION") == []


# --- FILELINK -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "See `results/tcad/calibration/nfet_05v0.result.json` for the fit.",
        "The card is `nfet_05v0.toml`.",
        "The mesh file `mesh.msh` is large.",
        "Run `tools/sandbox-run` first.",
        "The page `docs/explained/cv-curve.md` explains it.",
        "Data in `data/process/` and `sweep.csv`.",
        "| File |\n|---|\n| `tests/test_doc_style.py` |",
        "The test `tests/test_docgen.py::test_docs_build_offline` checks it.",
    ],
)
def test_filelink_fires_on_bare_path(line):
    assert found(f"# T\n\n{line}\n", "FILELINK")


def test_filelink_fires_in_a_figure_caption():
    page = "# T\n\n```{figure} a.svg\n:name: fig-a\n:alt: a\n\nDrawn from `results/a.json`.\n```\n"
    assert [line for line, _ in found(page, "FILELINK")] == [7]


@pytest.mark.parametrize(
    "line",
    [
        "See {repo}`results/tcad/calibration/nfet_05v0.result.json`.",
        "See {repo}`the result <results/tcad/calibration/nfet_05v0.result.json>`.",
        "See [`tools/sandbox-run`](https://github.com/mithro/gf180-tcad/blob/main/tools/sandbox-run).",
        "See {test}`tests/test_docgen.py::test_docs_build_offline`.",
        "The device `nfet_05v0` and the key `t_ox_eff_nm`.",
        "Run `uv run --locked pytest tests/test_doc_style.py` to check.",
        "See `https://example.org/a.json`.",
        "```text\ntools/sandbox-run results/a.json\n```",
        "$$ W = 1 $$ (eq-a)\n\nwhere\n\n- $W$ is a width, in m.",
    ],
)
def test_filelink_quiet_on_links_and_non_paths(line):
    assert found(f"# T\n\n{line}\n", "FILELINK") == []


# --- the command line ---------------------------------------------------------------------


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", str(LINT), *args], capture_output=True, text=True, check=False
    )


def test_help_documents_the_three_checks():
    out = _run("--help").stdout
    for check in ("FIGURE", "EQUATION", "FILELINK", "--rules"):
        assert check in out


def test_rules_are_opt_in_and_print_file_and_line(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("# T\n\nThe mesh is in `results/a.json`.\n", encoding="utf-8")
    plain = _run("--no-front-matter", str(page))
    assert plain.returncode == 0 and "FIGURE" not in plain.stdout
    ruled = _run("--no-front-matter", "--rules", "all", str(page))
    assert ruled.returncode == 1
    assert f"{page}:3: FAIL FIGURE" in ruled.stdout
    assert f"{page}:3: FAIL FILELINK" in ruled.stdout
    only = _run("--no-front-matter", "--rules", "filelink", str(page))
    assert "FILELINK" in only.stdout and "FIGURE" not in only.stdout


# --- FIGURE: opt-out, software senses, pages outside Sphinx --------------------------------


def test_figure_opt_out_with_a_reason():
    page = "# T\n\n## Files\n\n<!-- figure-ok: the mesh here is a file, not a shape -->\n\nThe mesh file is 9 MB.\n"
    assert found(page, "FIGURE") == []


def test_figure_opt_out_needs_a_reason():
    page = "# T\n\n## Files\n\n<!-- figure-ok: -->\n\nThe mesh file is 9 MB.\n"
    assert found(page, "FIGURE")


@pytest.mark.parametrize(
    "line", ["The TCAD stack is at its latest releases.", "It runs on the latest stack.",
             "The software stack of 2023 is pinned."],
)  # fmt: skip
def test_figure_ignores_a_software_stack(line):
    assert found(f"# T\n\n{line}\n", "FIGURE") == []


def test_figure_outside_sphinx_accepts_an_image():
    page = "# T\n\n![The 2D cell](docs/a.png)\n\nThe stack of the cell.\n"
    assert lint().rule_findings(page, sphinx=False) == []
    assert found(page, "FIGURE")  # in Sphinx an image is not a numbered figure


# --- the house forms build in Sphinx with the docs' MyST settings ---------------------------


def _site_conf() -> dict:
    """The figure and MyST settings of docs/conf.py, read without running it (it runs docgen):
    its extension list, myst_enable_extensions, numfig and numfig_format."""
    tree = ast.parse((ROOT / "docs" / "conf.py").read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = getattr(node.targets[0], "id", None)
            if name in ("extensions", "myst_enable_extensions", "numfig", "numfig_format"):
                out[name] = ast.literal_eval(node.value)
    return out


def test_house_forms_build_and_number(tmp_path):
    """The figure and equation forms of spec §10.3 build under -W with docs/conf.py's own
    extensions (docs/_ext on the path), with numfig on; {numref} and {math:numref} resolve; and
    a light/dark twin pair (the light twin named, the dark twin not) takes one number."""
    pytest.importorskip("sphinx")
    pytest.importorskip("myst_parser")
    site = _site_conf()
    src = tmp_path / "src"
    src.mkdir()
    (src / "conf.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT / 'docs' / '_ext')!r})\n"
        f"extensions = {site['extensions']!r}\n"
        f"myst_enable_extensions = {site['myst_enable_extensions']!r}\n"
        "numfig = True\n"
        f"numfig_format = {site.get('numfig_format', {'figure': 'Fig. %s'})!r}\n",
        encoding="utf-8",
    )
    for name in ("pic.svg", "pic-dark.svg", "two.svg"):
        (src / name).write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>', "utf-8"
        )
    page = textwrap.dedent(GOOD_EQUATION).lstrip("\n") + textwrap.dedent(
        """
        The stack is drawn in {numref}`fig-stack`, the mesh in {numref}`fig-two`.

        ```{figure} pic.svg
        :name: fig-stack
        :alt: The stack.
        :figclass: only-light

        The stack.
        ```

        ```{figure} pic-dark.svg
        :alt: The stack.
        :figclass: only-dark

        The stack.
        ```

        ```{figure} two.svg
        :name: fig-two
        :alt: The mesh.

        The mesh.
        ```
        """
    )
    assert lint().rule_findings(page) == []
    (src / "index.md").write_text(page, "utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "sphinx", "-W", "-q", "-b", "html", str(src), str(tmp_path / "o")],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip
    assert r.returncode == 0, r.stdout + r.stderr
    html = (tmp_path / "o" / "index.html").read_text(encoding="utf-8")
    assert 'href="#equation-eq-cox"' in html

    def number(name):
        m = re.search(rf'href="#{name}"[^>]*><span[^>]*>[^<]*?(\d+)</span>', html)
        assert m, f"no numbered reference to {name}"
        return int(m.group(1))

    assert number("fig-stack") == 1
    if not site.get("numfig"):
        pytest.skip(
            "twin numbering: docs/conf.py has no numfig yet; it arrives with PR #140 "
            "(docs/_ext/theme_figures.py merges each light/dark pair into one figure)"
        )
    assert number("fig-two") == 2  # the dark twin takes no number


# --- FIGURE: the nouns of the review of PR #143 ---------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "The valence band and the conduction band are separated by a gap.",
        "The bands bend near the surface.",
        "The band diagram bends near the oxide.",
        "Poly depletion adds a thin depleted layer at the gate's lower face.",
        "The fringe adds capacitance at the poly sidewalls.",
        "The doping falls off with depth.",
        "The cross section shows the oxide.",
        "The plan view shows the well.",
        "The gate sits on the oxide.",
        "The channel forms under the gate.",
        "The n-well holds the PMOS devices.",
        "The geometry of the cell is fixed.",
        "The drawing shows the two contacts.",
        "The electric field is largest at the surface.",
    ],
)  # fmt: skip
def test_figure_fires_on_the_review_nouns(line):
    assert found(f"# T\n\n{line}\n", "FIGURE"), line


@pytest.mark.parametrize(
    "line",
    [
        "The run works well on one core.",
        "As well as the tests, the build checks links.",
        "It is the stack of the final results.",
        "The field `t_ox_eff_nm` holds the thickness.",
    ],
)  # fmt: skip
def test_figure_quiet_on_non_physical_senses(line):
    assert found(f"# T\n\n{line}\n", "FIGURE") == [], line


def test_figure_fires_on_a_figure_above_without_numref():
    hits = found("# T\n\n## Later\n\nThe figure above shows it.\n", "FIGURE")
    assert hits and "above" in hits[0][1]


# --- FIGURE-FORM: a named, captioned figure that the page cites -----------------------------


def _figure(name=True, caption=True, figclass=None, path="a.svg"):
    opts = (
        [":alt: a"]
        + ([":name: fig-a"] if name else [])
        + ([f":figclass: {figclass}"] if figclass else [])
    )
    body = "\n\nThe stack of the cell." if caption else ""
    return "```{figure} " + path + "\n" + "\n".join(opts) + body + "\n```\n"


def test_figure_form_house_form_passes():
    page = "# T\n\nThe stack is in {numref}`fig-a`.\n\n" + _figure()
    assert found(page, "FIGURE-FORM") == []


@pytest.mark.parametrize(
    ("page", "word"),
    [
        ("# T\n\nThe mesh is fine.\n\n" + _figure(name=False), ":name:"),
        ("# T\n\nThe stack is in {numref}`fig-a`.\n\n" + _figure(caption=False), "caption"),
        ("# T\n\nThe stack is shown.\n\n" + _figure(), "numref"),
    ],
    ids=["no-name", "no-caption", "not-cited"],
)
def test_figure_form_fires(page, word):
    hits = found(page, "FIGURE-FORM")
    assert len(hits) == 1 and hits[0][0] == 5 and word in hits[0][1]


def test_figure_form_dark_twin_is_exempt():
    page = (
        "# T\n\nThe stack is in {numref}`fig-a`.\n\n"
        + _figure(figclass="only-light")
        + "\n"
        + _figure(name=False, figclass="only-dark", path="b.svg")
    )
    assert found(page, "FIGURE-FORM") == []


def test_figure_form_numref_with_text_cites():
    page = "# T\n\nSee {numref}`the stack <fig-a>`.\n\n" + _figure()
    assert found(page, "FIGURE-FORM") == []


# --- FIGURE-OK: opt-outs are listed and need a reason of six words ---------------------------


def test_figure_opt_out_needs_six_words():
    short = "# T\n\n<!-- figure-ok: a mesh file here -->\n\nThe mesh file is 9 MB.\n"
    assert found(short, "FIGURE")
    long = "# T\n\n<!-- figure-ok: the mesh here is a file name -->\n\nThe mesh file is 9 MB.\n"
    assert found(long, "FIGURE") == []


def test_figure_opt_outs_are_listed():
    page = "# T\n\n<!-- figure-ok: the mesh here is a file name -->\n\nThe mesh file is 9 MB.\n"
    assert lint().figure_opt_outs(page) == [(3, "the mesh here is a file name")]
    assert lint().figure_opt_outs("# T\n\n<!-- figure-ok: too short -->\n") == []


def test_rules_output_lists_opt_outs(tmp_path):
    page = tmp_path / "page.md"
    page.write_text(
        "# T\n\n<!-- figure-ok: the mesh here is a file name -->\n\nThe mesh file is 9 MB.\n",
        encoding="utf-8",
    )
    r = _run("--no-front-matter", "--rules", "all", str(page))
    assert r.returncode == 0
    assert f"{page}:3: NOTE FIGURE-OK the mesh here is a file name" in r.stdout


# --- FILELINK: the gaps and false positives of the review of PR #143 ------------------------


@pytest.mark.parametrize(
    "line",
    [
        "Run `Makefile` targets.",
        "The image is built from `docker/tcad-dev/Dockerfile`.",
        "Build with the `Dockerfile`.",
        "See `README` for the setup.",
        "See `plots.py:37` for the colour.",
        "See `src/gf180tcad/docgen.py:120-140` for the table.",
        "The cache is `~/.cache/gf180-tcad/out`.",
        "The cv.csv files are committed.",
        "The fit is in results/tcad/calibration/nfet_05v0.result.json today.",
    ],
)  # fmt: skip
def test_filelink_fires_on_the_review_gaps(line):
    assert found(f"# T\n\n{line}\n", "FILELINK"), line


@pytest.mark.parametrize(
    "line",
    [
        "The model uses `np.log` of the ratio.",
        "The handler calls `logger.log` once.",
        "The method reads `self.md` first.",
        "The page reads `numbers.format_value` and `math.pi`.",
        "See [cv.csv](https://github.com/mithro/gf180-tcad/blob/main/cv.csv).",
        "See {repo}`results/a.json` and https://example.org/b.json too.",
        "The site devsim.org hosts it.",
    ],
)  # fmt: skip
def test_filelink_quiet_on_code_names(line):
    assert found(f"# T\n\n{line}\n", "FILELINK") == [], line


# --- EQUATION: units and extra items ---------------------------------------------------------


@pytest.mark.parametrize(
    "unit", ["in F/m²", "in cm⁻³", "in m²/(V·s)", "in eV", "in V", "in cm^-3", "dimensionless"],
)  # fmt: skip
def test_equation_unit_symbols_pass(unit):
    page = (
        "# T\n\n$$ W = 2 L $$ (eq-w)\n\nwhere\n\n- $W$ is the width, in m;\n"
        f"- $L$ is the length, {unit}.\n"
    )
    assert found(page, "EQUATION") == []


@pytest.mark.parametrize("unit", ["in the oxide", "in farads per square metre", "in units"])
def test_equation_unit_words_fire(unit):
    page = (
        "# T\n\n$$ W = 2 L $$ (eq-w)\n\nwhere\n\n- $W$ is the width, in m;\n"
        f"- $L$ is the length, {unit}.\n"
    )
    hits = found(page, "EQUATION")
    assert len(hits) == 1 and "unit" in hits[0][1]


def test_equation_fires_on_extra_where_item():
    page = (
        "# T\n\n$$ W = 2 L $$ (eq-w)\n\nwhere\n\n- $W$ is the width, in m;\n"
        "- $L$ is the length, in m;\n- $H$ is the height, in m.\n"
    )
    hits = found(page, "EQUATION")
    assert len(hits) == 1 and "H" in hits[0][1] and "not" in hits[0][1]
