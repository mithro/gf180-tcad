# Results

The {term}`SPICE` reference dataset ({term}`Phase 1`) is published here as generated pages: one
per device and geometry (2 devices x 6 geometries), each with Id-Vg (linear and log), Id-Vd and
{term}`Cgg`-Vg plots and a table of extracted metrics, plus a summary of the {term}`TT`
(typical corner) values against the {doc}`PDK spec </comparison/pdk-spec-check>` and of the
{{ ngspice }}-versus-{{ Xyce }} differences ({doc}`/limitations/engine-cross-check`). Pages are
generated into `docs/_generated/` (git-ignored) at documentation build time by
{py:func}`gf180tcad.docgen.generate`, called from {repo}`docs/conf.py`, from the committed
{repo}`results/spice` files, so they never show numbers that are not in the dataset.

```{admonition} SPICE pages, and the first TCAD results
:class: warning
The generated pages below are the {term}`SPICE` {term}`golden reference` that {term}`TCAD` is
compared against. The TCAD results that exist so far are all 1D, for both devices at the
start values (`--params start`, the uncalibrated parameters), made on the dev-HEAD image
({repo}`docker/TCAD_DEV_IMAGE`, {ref}`which image makes which results <tcad-results-image>`):

- the 1D {term}`MOS capacitor <MOSCAP>` C-V curves, in {repo}`results/tcad/moscap1d`;
- the 1D {term}`mesh convergence`, in {repo}`results/tcad/meshconv`, discussed in
  {doc}`/limitations/mesh-convergence`.

They are compared with the PDK in {doc}`/comparison/index`, and their caveats are in
{doc}`/limitations/index`. The 2D results are pending ({repo}`Task 11 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`), and calibration of the
TCAD against SPICE is still to come ({repo}`Task 12 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-12-calibrate-against-spice-cggvg>`).
```

```{toctree}
:maxdepth: 2

../_generated/results/index
```
