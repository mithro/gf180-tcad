(roadmap)=

# Roadmap

This page lists the planned and unfinished work. Each item links the issue that tracks it, and
the issue says what is open and what settles it. The phases are those of the
{repo}`design spec, section 13 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#13-phases>`.

## Phase 2: the MOS capacitor

- **2D validation of the calibrated stack** ([issue #35](https://github.com/mithro/gf180-tcad/issues/35)): every calibrated 2D cell that solves
  is committed. Two 2D solves fail; the next two items name them.
  The 2D plateaus lie below {term}`SPICE` (issue #77, {numref}`roadmap-cv-figure`). The 2D {term}`depletion` crossing lies below 1D
  (issue #108, {ref}`cv-agreement-validation`). The memory grows with every 2D point (issue #78).
- **2D {term}`MOS capacitor <MOSCAP>` at L = 2 µm**: its small-signal (AC) solve fails
  ([issue #59](https://github.com/mithro/gf180-tcad/issues/59)).
- **2D MOS capacitor at L = 10 µm**: its equilibrium solve fails
  ([issue #58](https://github.com/mithro/gf180-tcad/issues/58)).
- **2D results on the {term}`dev-HEAD TCAD image`**, with the 2D {term}`mesh convergence` rerun there
  ([issue #67](https://github.com/mithro/gf180-tcad/issues/67)).
- **{term}`Corner <corner>` bounds and spread** of the {term}`TCAD` physical inputs
  ([issue #57](https://github.com/mithro/gf180-tcad/issues/57)).
- **Mesh pictures of the 2D start cells**, after their meshes are regenerated
  ([issue #149](https://github.com/mithro/gf180-tcad/issues/149)).

```{figure} /_generated/explained/moscap-cell-light.svg
:figclass: only-light
:name: roadmap-cell-figure
:alt: Cross-section of the transistor: the gate, the thin gate oxide and the tall body below them in colour, the source and the drain either side in grey.

The 2D cell `w10p0_l0p70` of the {term}`nfet_05v0`, cut along the gate's length. The 1D
stack is the column under the gate: the gate, the {term}`gate oxide` and the body, in colour.
The source and the drain, muted, are the parts the MOS capacitor leaves out.
{{ x_fig_moscap_cell_scale }}
```

```{figure} /_generated/explained/moscap-cell-dark.svg
:figclass: only-dark
:alt: Cross-section of the transistor: the gate, the thin gate oxide and the tall body below them in colour, the source and the drain either side in grey.

The 2D cell `w10p0_l0p70` of the {term}`nfet_05v0`, cut along the gate's length. The 1D
stack is the column under the gate: the gate, the {term}`gate oxide` and the body, in colour.
The source and the drain, muted, are the parts the MOS capacitor leaves out.
{{ x_fig_moscap_cell_scale }}
```

```{figure} /_generated/explained/cv-overview-light.svg
:figclass: only-light
:name: roadmap-cv-figure
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

The 2D validation runs the calibrated stack in cells like the one in {numref}`roadmap-cell-figure`.
Its curves at the minimum gate length are in {numref}`roadmap-cv-figure`, beside SPICE and the 1D stack.

## Phase 3: the MOSFET

- **The 2D MOSFET**, on both backends
  ([issue #68](https://github.com/mithro/gf180-tcad/issues/68)).
- **Entry gate: a layout-extracted secondary {term}`SPICE` reference** ({ref}`secondary reference <secondary-reference>`,
  [issue #69](https://github.com/mithro/gf180-tcad/issues/69)).
- **Entry gate: the remaining metrics of the {term}`tolerance` table** ({ref}`metrics list <metrics-not-yet-extracted>`,
  [issue #70](https://github.com/mithro/gf180-tcad/issues/70)).

## Phase 4: DEVSIM and Charon

- **{{ Charon }} beside {{ DEVSIM }} on every {term}`job`**, and the comparison of the two
  ({repo}`Phase 4 plan <docs/superpowers/plans/2026-10-27-phase4-charon-backend.md>`,
  [issue #44](https://github.com/mithro/gf180-tcad/issues/44)). No Charon job has run.
  The charon-libs image, built from {repo}`docker/charon-libs/`, is pinned
  ({ref}`charon-images`). The Charon backend and the thin `charon` image come next.

## Phase 5: temperature and silicon

- **Temperatures of −40 °C and 125 °C** for the SPICE reference and the TCAD
  ([issue #71](https://github.com/mithro/gf180-tcad/issues/71)).
- **Predictions for the {{ wafer_space }} silicon test structures**
  ([issue #66](https://github.com/mithro/gf180-tcad/issues/66)).
- **The run-2 checkout's {term}`PDK` build** ({{ open_pdks }} 40cee970) compared with the reference, before
  any run-2 silicon is used ({ref}`pdk-versions-run2`,
  [issue #72](https://github.com/mithro/gf180-tcad/issues/72)).

## Documentation

<!-- figure-ok: these items name the topics of explainer pages and renders; those pages carry the figures -->

- **3D renders** of the simulated processes
  ({repo}`renders plan <docs/superpowers/plans/2026-10-27-renders-pipeline.md>`,
  [issue #43](https://github.com/mithro/gf180-tcad/issues/43)). The format of their
  {doc}`render manifest <reproduce/render-manifest>` is defined and tested.
- **Explainer pages** on the MOSFET
  ({repo}`explainer plan <docs/superpowers/plans/2026-10-27-explainer-docs.md>`,
  [issue #46](https://github.com/mithro/gf180-tcad/issues/46)). The section
  {doc}`explained/index` holds the basics. They cover carriers, energy bands and the
  {term}`Fermi level`, the {term}`pn junction`, the transistor's parts, the {term}`gate oxide`
  and {term}`poly-silicon`. The second tier covers the {term}`MOS capacitor <MOSCAP>`, its
  regions, what sets each part of its {term}`C–V` curve and what the calibration changes.
- **The figure, equation and file-link rules** on every page. Each described thing gets a
  figure, each equation its symbols and units, each file a link. The explainer pages meet them
  (issue #129). Issues #130 to #134 hold the work on the other pages, one issue per group of
  pages.
