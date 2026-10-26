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

The 1D MOS capacitor is also calibrated against the SPICE {term}`Cgg`–Vg and validated at the
{term}`held-out geometries <held-out geometry>`, in 1D only
({repo}`results/tcad/calibration`, {repo}`results/tcad/validation`,
{doc}`/comparison/cv-agreement`). The calibrated 2D validation is not run
([issue #35](https://github.com/mithro/gf180-tcad/issues/35)). They are compared with the PDK in
{doc}`/comparison/index`, and their caveats are in {doc}`/limitations/index`.
```

The TCAD pages are generated the same way, by {py:func}`gf180tcad.docgen.generate_tcad`, from
the committed {repo}`results/tcad` files: a summary of the 1D verdicts, one page per device
(calibrated parameters with their bounds and {term}`provenance tags <provenance tag>`, the fixed bookkeeping, the
{term}`mesh convergence` plots) and one per device and geometry (the TCAD-against-ngspice Cgg
overlay with the {term}`corner envelope`, the verdicts, the intrinsic and parasitic parts, the
committed 2D result). Every verdict and error on them is read from the calibration and
validation files, which were computed in the TCAD image; docgen only renders them. No 2D mesh
is committed, so the pages show no mesh picture and say so.

```{toctree}
:maxdepth: 2

../_generated/results/index
../_generated/tcad/index
```
