# gf180-tcad

Open-source {term}`TCAD` for the GlobalFoundries {term}`GF180MCU` 5 V transistors
({{ gf180mcu_pdk }}), compared quantitatively, reproducibly and in public against the
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
  {repo}`results/tcad/moscap1d` and {repo}`results/tcad/moscap2d` ({doc}`limitations/moscap2d`);
- the calibrated 2D nfet cells at W10/L0.6, W10/L0.7, W10/L1 and W10/L2, in {repo}`results/tcad/moscap2d`;
- their {term}`mesh convergence`, 1D and 2D, in {repo}`results/tcad/meshconv`
  ({doc}`limitations/mesh-convergence`);
- the 1D calibration against the SPICE {term}`Cgg`–Vg, in {repo}`results/tcad/calibration`,
  and its validation at the {term}`held-out geometries <held-out geometry>`, in
  {repo}`results/tcad/validation`, with the calibrated 1D curves in
  {repo}`results/tcad/moscap1d` ({doc}`comparison/cv-agreement`). In 1D the nfet is
  {term}`Agree` at every geometry and the pfet is published as {term}`Disagree`.

The generated TCAD pages are {doc}`/_generated/tcad/index`. The 2D validation
([issue #35](https://github.com/mithro/gf180-tcad/issues/35)) is {term}`Disagree` at the two shortest nfet cells
and {term}`Same process` at W10/L1 and W10/L2 ({ref}`cv-agreement-validation`).
Planned work, each item with its issue, is on the {doc}`roadmap`. No measured silicon data
exists ({doc}`limitations/silicon-validation`). See {doc}`limitations/index`.
```

No published {{ DEVSIM }}- or {{ Charon }}-versus-{term}`BSIM` comparison for any open PDK was
found, and no gf180mcu TCAD paper was found ({doc}`limitations/literature`), so this work is
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
