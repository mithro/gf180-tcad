# Results

The {term}`SPICE reference <SPICE reference results>` dataset ({term}`Phase 1`) is published
here as generated pages, one per device and geometry (2 devices x 6 geometries). Each has Id-Vg
(linear and log), Id-Vd and {term}`Cgg`-Vg plots and a table of extracted metrics.
Three of the {term}`sweeps <sweep>` of one geometry are drawn in {numref}`results-sweeps-figure`. A summary
compares the {term}`TT` (typical corner) values with the
{doc}`PDK spec </comparison/pdk-spec-check>` and lists the {{ ngspice }}-versus-{{ Xyce }}
differences ({doc}`/limitations/engine-cross-check`).

```{figure} /_generated/explained/spice-sweeps-light.svg
:figclass: only-light
:name: results-sweeps-figure
:alt: Three stacked plots of the nfet: drain current against gate voltage, a family of drain current against drain voltage, and gate capacitance against gate voltage.

Three sweeps of the {term}`SPICE` reference of the {term}`nfet_05v0` at W = 10 µm and L = 0.6 µm,
with the body at 0 V. Top, the drain current against the gate voltage at a drain voltage of
0.1 V: the black line is the {term}`typical corner`, and the grey band spans the
{{ x_corner_count }} {term}`corners <corner>`. Middle, the drain current against the drain
voltage at the typical corner only, one coloured line per gate voltage. Bottom, the gate
capacitance against the gate voltage, with the line and the band as at the top.
```

```{figure} /_generated/explained/spice-sweeps-dark.svg
:figclass: only-dark
:alt: Three stacked plots of the nfet: drain current against gate voltage, a family of drain current against drain voltage, and gate capacitance against gate voltage.

Three sweeps of the {term}`SPICE` reference of the {term}`nfet_05v0` at W = 10 µm and L = 0.6 µm,
with the body at 0 V. Top, the drain current against the gate voltage at a drain voltage of
0.1 V: the black line is the {term}`typical corner`, and the grey band spans the
{{ x_corner_count }} {term}`corners <corner>`. Middle, the drain current against the drain
voltage at the typical corner only, one coloured line per gate voltage. Bottom, the gate
capacitance against the gate voltage, with the line and the band as at the top.
```

The function {py:func}`gf180tcad.docgen.generate` writes the pages at documentation build
time, into the git-ignored folder {repo}`docs/_generated/ <.gitignore#L10>`. The docs configuration
{repo}`docs/conf.py` calls it, and it reads only the committed {repo}`results/spice` files. So the pages never show numbers that are not in
the dataset. Builds of one checkout serialise on the lock file
{repo}`docs/.generated.lock <.gitignore#L12>`, also git-ignored, and swap the
finished folder in atomically. So two docs builds can run at the same time without corrupting
each other.

```{admonition} The simulated results
:class: warning
The generated pages below are the {term}`SPICE reference <SPICE reference results>` that {term}`TCAD` is
compared against. The TCAD results are {term}`MOS capacitors <MOSCAP>` of both devices. They
are run at the start values (`--params start`, the uncalibrated parameters) and at the
calibrated values (`--params calibrated`). The 1D results were made on the
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

The 1D MOS capacitor is calibrated against the {term}`SPICE` {term}`Cgg`–Vg and validated at
the {term}`held-out geometries <held-out geometry>` ({repo}`results/tcad/calibration`,
{repo}`results/tcad/validation`, {doc}`/comparison/cv-agreement`). In 2D, five calibrated cells
per device are committed in {repo}`results/tcad/moscap2d` and compared with SPICE
({ref}`cv-agreement-validation`, [issue #35](https://github.com/mithro/gf180-tcad/issues/35)).
The results are compared with the PDK in {doc}`/comparison/index`, and their caveats are in
{doc}`/limitations/index`.
```

The TCAD pages ({doc}`/_generated/tcad/index`) are generated the same way, by
{py:func}`gf180tcad.docgen.generate_tcad`, from the committed {repo}`results/tcad` files. They
hold a summary of the 1D verdicts and one page per device. A device page gives the calibrated
parameters with their bounds and {term}`provenance tags <provenance tag>`, the fixed
bookkeeping and the {term}`mesh convergence` plots.

A geometry page gives the TCAD-against-ngspice Cgg overlay with the {term}`corner envelope`, the
verdicts, the intrinsic and parasitic parts and the committed 2D result. The curves of such an
overlay are drawn for both devices at the minimum gate length in {numref}`results-cv-figure`.

```{figure} /_generated/explained/cv-overview-light.svg
:figclass: only-light
:name: results-cv-figure
:alt: Gate capacitance against gate voltage, nfet above and pfet below: SPICE curves in a grey band, with dotted and dashed 1D lines and dash-dot 2D lines.

The gate capacitance against the gate voltage of the {term}`nfet_05v0` and the
{term}`pfet_05v0` at the minimum gate length. The solid line is the {term}`SPICE` model at the
{term}`typical corner`, and the grey band spans its {{ x_corner_count }}
{term}`corners <corner>`. The dotted and dashed lines are the 1D stack at the start and the
fitted values. The dash-dot lines are the 2D cell at the start values (orange) and the fitted
values (blue), with no parasitics added outside the cell.
```

```{figure} /_generated/explained/cv-overview-dark.svg
:figclass: only-dark
:alt: Gate capacitance against gate voltage, nfet above and pfet below: SPICE curves in a grey band, with dotted and dashed 1D lines and dash-dot 2D lines.

The gate capacitance against the gate voltage of the {term}`nfet_05v0` and the
{term}`pfet_05v0` at the minimum gate length. The solid line is the {term}`SPICE` model at the
{term}`typical corner`, and the grey band spans its {{ x_corner_count }}
{term}`corners <corner>`. The dotted and dashed lines are the 1D stack at the start and the
fitted values. The dash-dot lines are the 2D cell at the start values (orange) and the fitted
values (blue), with no parasitics added outside the cell.
```

Every verdict and error on the TCAD pages comes from the calibration and validation files.
Those files were computed in the {term}`dev-HEAD TCAD image`, and {py:mod}`gf180tcad.docgen`
only renders them. No 2D mesh is committed ({ref}`moscap2d-meshes`), so the pages show no mesh
picture and say so. That is a {ref}`recorded deviation <limitations-spec-deviations>` from the
design spec ([issue #39](https://github.com/mithro/gf180-tcad/issues/39)).

```{toctree}
:maxdepth: 2

../_generated/results/index
../_generated/tcad/index
```
