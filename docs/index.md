# gf180-tcad

Open-source {term}`TCAD` for the GlobalFoundries {term}`GF180MCU` 5 V transistors
({{ gf180mcu_pdk }}). It is compared quantitatively, reproducibly and in public against the
{term}`PDK`'s own {term}`SPICE` models.

**The PDK's SPICE models are the {term}`reference <SPICE reference results>`; the TCAD is what is
being tested.**

The aim is to earn (or fail to earn) confidence in the TCAD setup. Only once
that confidence exists would TCAD be used, in later work, to improve or create SPICE models.
Every mismatch is listed with its cause and the evidence for it, not hidden. The documentation
separates what was calibrated from what was predicted.

```{admonition} Status
:class: warning
{term}`Phases 0 and 1` (foundations and the SPICE reference dataset) are complete
({doc}`/_generated/results/index`). {term}`Phase 2` (the {{ gplugins }} {{ DEVSIM }} plugin fix
and the {term}`MOS capacitor <MOSCAP>`) is in progress. The committed {term}`TCAD` results are
MOS capacitors only, for {term}`nfet_05v0` and {term}`pfet_05v0`; there is no MOSFET TCAD result:

- the 1D and 2D MOS capacitor {term}`C–V` curves at the start values, in
  {repo}`results/tcad/moscap1d` and {repo}`results/tcad/moscap2d` ({doc}`limitations/moscap2d`,
  {numref}`index-cv-figure`);
- the calibrated 2D nfet cells at W10/L0.6, W10/L0.7, W10/L1, W10/L2 and W1.6/L0.7, in {repo}`results/tcad/moscap2d`;
- the calibrated 2D pfet cells at W10/L0.5, W10/L0.7, W10/L1, W10/L2 and W1.6/L0.7, in the same folder;
- the reduced mesh artefact of each calibrated 2D cell, the mesh around its gate, in
  {repo}`results/tcad/meshes/stable` ({ref}`moscap2d-mesh-artefact`);
- their {term}`mesh convergence`, 1D and 2D, in {repo}`results/tcad/meshconv`
  ({doc}`limitations/mesh-convergence`);
- the 1D calibration against the SPICE {term}`Cgg`–Vg, in {repo}`results/tcad/calibration`.
  Its validation at the {term}`held-out geometries <held-out geometry>` is in
  {repo}`results/tcad/validation`, and the calibrated 1D curves are in
  {repo}`results/tcad/moscap1d` ({doc}`comparison/cv-agreement`). In 1D the nfet is
  {term}`Agree` at every geometry and the pfet is published as {term}`Disagree`.
  Both are drawn at the minimum gate length in {numref}`index-cv-figure`, beside the 2D cells.
- the same 1D fit at the four other SPICE {term}`corners <corner>`, in
  {repo}`results/tcad/corners`. It gives each fitted number's lower and upper bound and its
  spread ({ref}`explained-calibration-corners`, {doc}`limitations/corners`).

The generated TCAD pages are {doc}`/_generated/tcad/index`. The 2D validation
([issue #35](https://github.com/mithro/gf180-tcad/issues/35)) is {term}`Disagree` at five committed cells
and {term}`Same process` at the others ({ref}`cv-agreement-validation`).

Both {{ Charon }} images are built and pinned ({ref}`charon-images`), and no Charon {term}`job` has run.
Planned work, each item with its issue, is on the {doc}`roadmap`. No measured silicon data
exists ({doc}`limitations/silicon-validation`). See {doc}`limitations/index`.
```

```{figure} /_generated/explained/cv-overview-light.svg
:figclass: only-light
:name: index-cv-figure
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

No published {{ DEVSIM }}- or {{ Charon }}-versus-{term}`BSIM` comparison for any open PDK was
found. No gf180mcu TCAD paper was found either ({doc}`limitations/literature`). So this work is
novel and should be read with that in mind.

The documentation has five sections, plus a glossary and the API reference. The first,
{doc}`explained/index`, explains how the parts of a transistor work, with this repo's numbers.

```{toctree}
:maxdepth: 2

explained/index
reproduce/index
results/index
comparison/index
limitations/index
roadmap
glossary
api/index
```
