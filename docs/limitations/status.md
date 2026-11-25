(status)=

# Project status

This page lists what the project has finished and where each result is. It is for a reader who
has seen the {doc}`overview </index>` and wants the detail. The shortcomings of each result are
on the other pages of this section.

## What is finished

{term}`Phases 0 and 1` are complete. They built the foundations and the {term}`SPICE` reference
dataset ({doc}`/_generated/results/index`). The SPICE reference rebuilds byte for byte on a second
computer ({ref}`cross-host-determinism`). Work on {term}`Phase 2` (the {{ gplugins }} {{ DEVSIM }}
plugin fix and the {term}`MOS capacitor <MOSCAP>`) is in progress.

The committed {term}`TCAD` results are MOS capacitors only, for {term}`nfet_05v0` and
{term}`pfet_05v0`. There is no MOSFET TCAD result. {numref}`status-cv-figure` draws both
devices at the minimum gate length.

```{figure} /_generated/explained/cv-overview-light.svg
:figclass: only-light
:name: status-cv-figure
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

## The committed TCAD results

Each row is one kind of result, the folder that holds it and the page that explains it. The
generated pages of every result are {doc}`/_generated/tcad/index`.

| Result | Folder | Page |
|---|---|---|
| 1D {term}`C–V` curves, start and calibrated values | {repo}`results/tcad/moscap1d` | {doc}`/comparison/cv-agreement` |
| 2D C–V curves, start values and the ten calibrated cells | {repo}`results/tcad/moscap2d` | {doc}`moscap2d` |
| Reduced mesh artefact of each calibrated 2D cell | {repo}`results/tcad/meshes/stable` | {ref}`moscap2d-mesh-artefact` |
| {term}`Mesh convergence`, 1D and 2D | {repo}`results/tcad/meshconv` | {doc}`mesh-convergence` |
| 1D calibration against the SPICE {term}`Cgg`–Vg | {repo}`results/tcad/calibration` | {doc}`/comparison/cv-agreement` |
| Validation at the {term}`held-out geometries <held-out geometry>` | {repo}`results/tcad/validation` | {ref}`cv-agreement-validation` |
| The 1D fit at the four other SPICE {term}`corners <corner>` | {repo}`results/tcad/corners` | {doc}`corners` |

## The verdicts

| Model | nfet_05v0 | pfet_05v0 |
|---|---|---|
| 1D, the fitted geometries | {term}`Agree` | {term}`Disagree` |
| 1D, the held-out geometries | Agree | {term}`Same process` |
| 2D, W10/L0.6 or W10/L0.5 | Disagree | Same process |
| 2D, W10/L0.7 | Disagree | Same process |
| 2D, W1.6/L0.7 | Disagree | Same process |
| 2D, W10/L1 | Same process | Disagree |
| 2D, W10/L2 | Same process | Disagree |
| 2D, W10/L10 | not run | not run |

Each 1D row gives the worst verdict of its sizes. The pfet's fitted W10/L0.5 and W10/L10 are
Disagree, and W10/L2 is Same process. Of its held-out sizes, W10/L1 is Agree and the others are
Same process. The W10/L10 cell has no 2D result, because its equilibrium solve fails
({ref}`moscap2d-l10`).

The first 2D row holds the shortest gates ({numref}`status-cv-figure`): 0.6 µm for the nfet,
0.5 µm for the pfet. The 2D rows are the calibrated cells of the 2D validation
([issue #35](https://github.com/mithro/gf180-tcad/issues/35), {ref}`cv-agreement-validation`).
In every 2D cell the poly is as drawn, its length bias at 0 ({ref}`process-data-poly-bias`).
The corner fits give each fitted number a lower and an upper bound and its spread
({ref}`explained-calibration-corners`).

## Other engines and measurements

Both {{ Charon }} images are built and pinned ({ref}`charon-images`), and no Charon {term}`job`
has run. No measured silicon data exists ({doc}`silicon-validation`). Planned work, each item
with its issue, is on the {doc}`/roadmap`.
