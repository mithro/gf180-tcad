# Results

The {term}`SPICE reference <SPICE reference results>` dataset ({term}`Phase 1`) is published
here as generated pages, one per device and geometry (2 devices x 6 geometries). Each has Id-Vg
(linear and log), Id-Vd and {term}`Cgg`-Vg plots and a table of extracted metrics. A summary
compares the {term}`TT` (typical corner) values with the
{doc}`PDK spec </comparison/pdk-spec-check>` and lists the {{ ngspice }}-versus-{{ Xyce }}
differences ({doc}`/limitations/engine-cross-check`). Pages are
generated into `docs/_generated/` (git-ignored) at documentation build time by
{py:func}`gf180tcad.docgen.generate`, called from {repo}`docs/conf.py`, from the committed
{repo}`results/spice` files, so they never show numbers that are not in the dataset.
Builds of one checkout serialise on a lock file (`docs/.generated.lock`) and swap the finished
folder in atomically, so two docs builds can run at the same time without corrupting each other.

```{admonition} What exists so far
:class: warning
The generated pages below are the {term}`SPICE reference <SPICE reference results>` that {term}`TCAD` is
compared against. The TCAD results that exist so far are {term}`MOS capacitors <MOSCAP>` of
both devices at the start values (`--params start`, the uncalibrated parameters) and, in 1D
only, at the calibrated values (`--params calibrated`). The 1D results were made on the
{term}`dev-HEAD TCAD image` ({repo}`docker/TCAD_DEV_IMAGE`,
{ref}`which image makes which results <tcad-results-image>`):

- the 1D MOS capacitor {term}`C–V` curves, start and calibrated, in {repo}`results/tcad/moscap1d`;
- the 1D {term}`mesh convergence`, in {repo}`results/tcad/meshconv`, discussed in
  {doc}`/limitations/mesh-convergence`.

The 2D results were made on the {term}`stable TCAD image` (see
{ref}`tcad-results-image`):

- the 2D MOS capacitor C-V curves, cut from the {term}`PDK`'s transistor cells, in
  {repo}`results/tcad/moscap2d`, discussed in {doc}`/limitations/moscap2d`;
- the 2D mesh convergence, in {repo}`results/tcad/meshconv/moscap2d`, discussed in
  {ref}`mesh-convergence-2d`.

The 1D MOS capacitor is also calibrated against the {term}`SPICE` {term}`Cgg`–Vg. It is
validated at the {term}`held-out geometries <held-out geometry>`, in 1D only
({repo}`results/tcad/calibration`, {repo}`results/tcad/validation`,
{doc}`/comparison/cv-agreement`). In 2D one calibrated cell is committed, the nfet at minimum
length ({ref}`cv-agreement-validation`); the other cells are on the {doc}`/roadmap`
([issue #35](https://github.com/mithro/gf180-tcad/issues/35)). They are compared with the PDK in
{doc}`/comparison/index`, and their caveats are in {doc}`/limitations/index`.
```

The TCAD pages ({doc}`/_generated/tcad/index`) are generated the same way, by
{py:func}`gf180tcad.docgen.generate_tcad`, from the committed {repo}`results/tcad` files: a summary of the 1D verdicts, one page per device
(calibrated parameters with their bounds and {term}`provenance tags <provenance tag>`, the fixed bookkeeping, the
{term}`mesh convergence` plots) and one per device and geometry (the TCAD-against-ngspice Cgg
overlay with the {term}`corner envelope`, the verdicts, the intrinsic and parasitic parts, the
committed 2D result). Every verdict and error on them is read from the calibration and
validation files, which were computed in the {term}`dev-HEAD TCAD image`;
{py:mod}`gf180tcad.docgen` only renders them. No 2D mesh is committed
({ref}`moscap2d-meshes`), so the pages show no mesh picture and say so, a
{ref}`recorded deviation <limitations-spec-deviations>` from the design spec
([issue #39](https://github.com/mithro/gf180-tcad/issues/39)).

```{toctree}
:maxdepth: 2

../_generated/results/index
../_generated/tcad/index
```
