# gf180-tcad

Open-source TCAD for the GlobalFoundries GF180MCU 5 V transistors, compared
quantitatively, reproducibly and in public against the PDK's own SPICE models.

**The SPICE models are the golden reference; the TCAD is the suspect.** The
aim is to earn (or fail to earn) confidence in the TCAD setup. Only once that
confidence exists would TCAD be used, in later work, to improve or create SPICE
models. Every mismatch is listed with a probable cause rather than hidden, and
the documentation separates what was calibrated from what was predicted.

```{admonition} Status
:class: warning
Phases 0 and 1 (foundations and the SPICE reference dataset) are in progress.
**No TCAD simulation has been run yet, and there are no results yet.** No
measured silicon data exists. See {doc}`limitations/index`.
```

No published DEVSIM- or Charon-versus-BSIM comparison for any open PDK was
found, and no gf180mcu TCAD paper was found, so this work is novel and should
be read with that in mind.

The documentation has four sections, plus the API reference.

```{toctree}
:maxdepth: 2

reproduce/index
results/index
comparison/index
limitations/index
api/index
```
