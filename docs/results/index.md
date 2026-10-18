# Results

The SPICE reference dataset (Phase 1) is published here as generated pages: one per device and
geometry (2 devices x 6 geometries), each with Id-Vg (linear and log), Id-Vd and Cgg-Vg plots and
a table of extracted metrics, plus a summary of the typical-corner values against the PDK spec and
of the ngspice-versus-Xyce differences. Pages are generated into `docs/_generated/` at
documentation build time from the committed `results/spice` files, so they never show numbers
that are not in the dataset.

```{admonition} SPICE only
:class: warning
No TCAD simulation has been run yet. Everything here is the SPICE golden reference that TCAD will
later be compared against. TCAD results, mesh pictures and process files follow in later phases.
```

```{toctree}
:maxdepth: 2

../_generated/results/index
```
