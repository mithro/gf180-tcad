(roadmap)=

# Roadmap

This page lists the planned and unfinished work. Each item links the issue that tracks it, and
the issue says what is open and what settles it. The phases are those of the
{repo}`design spec, section 13 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#13-phases>`.

## Phase 2: the MOS capacitor

- **2D validation of the calibrated stack** ([issue #35](https://github.com/mithro/gf180-tcad/issues/35)): every calibrated 2D cell that solves
  is committed. Two 2D solves fail; the next two items name them.
  The 2D plateaus lie below {term}`SPICE` (issue #77). The 2D {term}`depletion` crossing lies below 1D
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
  The Charon image recipe is in {repo}`docker/charon-libs/` ({ref}`charon-images`); no Charon
  image is pinned.

## Phase 5: temperature and silicon

- **Temperatures of −40 °C and 125 °C** for the SPICE reference and the TCAD
  ([issue #71](https://github.com/mithro/gf180-tcad/issues/71)).
- **Predictions for the {{ wafer_space }} silicon test structures**
  ([issue #66](https://github.com/mithro/gf180-tcad/issues/66)).
- **The run-2 checkout's {term}`PDK` build** ({{ open_pdks }} 40cee970) compared with the reference, before
  any run-2 silicon is used ({ref}`pdk-versions-run2`,
  [issue #72](https://github.com/mithro/gf180-tcad/issues/72)).

## Documentation

- **3D renders** of the simulated processes
  ({repo}`renders plan <docs/superpowers/plans/2026-10-27-renders-pipeline.md>`,
  [issue #43](https://github.com/mithro/gf180-tcad/issues/43)). The format of their
  {doc}`render manifest <reproduce/render-manifest>` is defined and tested.
- **Explainer pages** on the rest of the MOS capacitor and on the MOSFET
  ({repo}`explainer plan <docs/superpowers/plans/2026-10-27-explainer-docs.md>`,
  [issue #46](https://github.com/mithro/gf180-tcad/issues/46)). The section
  {doc}`explained/index` holds the basics. They cover carriers, energy bands and the
  {term}`Fermi level`, the {term}`pn junction`, the transistor's parts, the {term}`gate oxide`
  and {term}`poly-silicon`. The second tier covers the {term}`MOS capacitor <MOSCAP>`, its
  regions and what sets each part of its {term}`C–V` curve.
