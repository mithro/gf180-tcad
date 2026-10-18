# Results

The {term}`SPICE` reference dataset ({term}`Phase 1`) is published here as generated pages: one
per device and geometry (2 devices x 6 geometries), each with Id-Vg (linear and log), Id-Vd and
{term}`Cgg`-Vg plots and a table of extracted metrics, plus a summary of the {term}`TT`
(typical corner) values against the {doc}`PDK spec </comparison/pdk-spec-check>` and of the
{{ ngspice }}-versus-{{ Xyce }} differences ({doc}`/limitations/engine-cross-check`). Pages are
generated into `docs/_generated/` (git-ignored) at documentation build time by
{py:func}`gf180tcad.docgen.generate`, called from {repo}`docs/conf.py`, from the committed
{repo}`results/spice` files, so they never show numbers that are not in the dataset.

```{admonition} SPICE only
:class: warning
No {term}`TCAD` simulation has been run yet. Everything here is the SPICE
{term}`golden reference` that TCAD will later be compared against. TCAD results, mesh pictures
and {term}`process files <process file>` follow in later phases.
```

```{toctree}
:maxdepth: 2

../_generated/results/index
```
