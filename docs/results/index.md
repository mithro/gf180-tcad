# Results

The {term}`SPICE` reference dataset ({term}`Phase 1`) is published here as generated pages: one
per device and geometry (2 devices x 6 geometries), each with Id-Vg (linear and log), Id-Vd and
{term}`Cgg`-Vg plots and a table of extracted metrics, plus a summary of the {term}`TT`
(typical corner) values against the {doc}`PDK spec </comparison/pdk-spec-check>` and of the
{{ ngspice }}-versus-{{ Xyce }} differences ({doc}`/limitations/engine-cross-check`). Pages are
generated into `docs/_generated/` (git-ignored) at documentation build time by
{py:func}`gf180tcad.docgen.generate`, called from {repo}`docs/conf.py`, from the committed
{repo}`results/spice` files, so they never show numbers that are not in the dataset.

```{admonition} What exists so far
:class: warning
The generated pages below are the {term}`SPICE` {term}`golden reference` that {term}`TCAD` is
compared against. The TCAD results that exist so far are for both devices at the
start values (`--params start`, the uncalibrated parameters). The 1D results were made on the
{term}`dev-HEAD TCAD image` ({repo}`docker/TCAD_DEV_IMAGE`,
{ref}`which image makes which results <tcad-results-image>`):

- the 1D {term}`MOS capacitor <MOSCAP>` C-V curves, in {repo}`results/tcad/moscap1d`;
- the 1D {term}`mesh convergence`, in {repo}`results/tcad/meshconv`, discussed in
  {doc}`/limitations/mesh-convergence`.

The 2D results were made on the {term}`stable TCAD image` for now (see
{ref}`tcad-results-image`):

- the 2D MOS capacitor C-V curves, cut from the {term}`PDK`'s transistor cells, in
  {repo}`results/tcad/moscap2d`, discussed in {doc}`/limitations/moscap2d`;
- the 2D mesh convergence, in {repo}`results/tcad/meshconv/moscap2d`, discussed in
  {ref}`mesh-convergence-2d`.

They are compared with the PDK in {doc}`/comparison/index`, and their caveats are in
{doc}`/limitations/index`. Calibration of the
TCAD against SPICE is still to come ({repo}`Task 12 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-12-calibrate-against-spice-cggvg>`).
```

```{toctree}
:maxdepth: 2

../_generated/results/index
```
