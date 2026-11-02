# SPDX-License-Identifier: Apache-2.0
"""The three house rules that ``tools/docs_lint.py --rules`` checks (spec §10.3, owner
2026-11-03 02:00): FIGURE (a described situation has a figure), EQUATION (every equation is a
labelled display block with a "where" list defining each symbol and its unit) and FILELINK
(every file or path mentioned is a link). Each check has a positive control (it fires) and a
negative control (the house form passes)."""

from __future__ import annotations

import importlib.util
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
            r"W = \sqrt{\frac{2 \, \varepsilon_{si} \, V_{bi}}{q} \left( \frac{1}{N_A} + "
            r"\frac{1}{N_D} \right)}",
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
    page = GOOD_EQUATION.replace("    - $\\varepsilon_0$ is the permittivity of vacuum, in F/m;\n", "")
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
