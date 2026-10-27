# gf180-tcad

Open-source {term}`TCAD` for the GlobalFoundries {term}`GF180MCU` 5 V transistors
({{ gf180mcu_pdk }}), compared quantitatively, reproducibly and in public against the
{term}`PDK`'s own {term}`SPICE` models.

**The SPICE models are the {term}`SPICE reference`; the TCAD is the suspect.** The
aim is to earn (or fail to earn) confidence in the TCAD setup. Only once that
confidence exists would TCAD be used, in later work, to improve or create SPICE
models. Every mismatch is listed with a probable cause rather than hidden, and
the documentation separates what was calibrated from what was predicted.

```{admonition} Status
:class: warning
{term}`Phases 0 and 1` (foundations and the SPICE reference dataset) are complete
({doc}`/_generated/results/index`). {term}`Phase 2` (the {{ gplugins }} {{ DEVSIM }} plugin fix
and the {term}`MOS capacitor <MOSCAP>`) is in progress. The committed {term}`TCAD` results are
MOS capacitors only, for {term}`nfet_05v0` and {term}`pfet_05v0`; there is no MOSFET TCAD yet:

- the 1D and 2D MOS capacitor {term}`C–V` curves at the start values, in
  {repo}`results/tcad/moscap1d` and {repo}`results/tcad/moscap2d` ({doc}`limitations/moscap2d`);
- their {term}`mesh convergence`, 1D and 2D, in {repo}`results/tcad/meshconv`
  ({doc}`limitations/mesh-convergence`);
- the 1D calibration against the SPICE {term}`Cgg`–Vg, in {repo}`results/tcad/calibration`,
  and its validation at the {term}`held-out geometries <held-out geometry>`, in
  {repo}`results/tcad/validation`, with the calibrated 1D curves in
  {repo}`results/tcad/moscap1d` ({doc}`comparison/cv-agreement`). In 1D the nfet is
  {term}`Agree` at every geometry and the pfet is published as {term}`Disagree`.

The generated TCAD pages are {doc}`/_generated/tcad/index`. The 2D validation of the
calibrated stack is in progress ([issue #35](https://github.com/mithro/gf180-tcad/issues/35)).
Planned, not built yet: {{ DEVSIM }}-versus-{{ Charon }} cross-comparison on every {term}`job`
({repo}`Phase 4 plan <docs/superpowers/plans/2026-10-27-phase4-charon-backend.md>`,
[issue #44](https://github.com/mithro/gf180-tcad/issues/44); none has run yet), 3D renders
of the simulated processes
({repo}`renders plan <docs/superpowers/plans/2026-10-27-renders-pipeline.md>`,
[issue #43](https://github.com/mithro/gf180-tcad/issues/43)) and explainer pages
([issue #46](https://github.com/mithro/gf180-tcad/issues/46)). No measured silicon data exists
({doc}`limitations/silicon-validation`). See {doc}`limitations/index`.
```

No published {{ DEVSIM }}- or {{ Charon }}-versus-{term}`BSIM` comparison for any open PDK was
found, and no gf180mcu TCAD paper was found ({doc}`limitations/literature`), so this work is
novel and should be read with that in mind.

The documentation has four sections, plus a glossary and the API reference.

```{toctree}
:maxdepth: 2

reproduce/index
results/index
comparison/index
limitations/index
glossary
api/index
```
