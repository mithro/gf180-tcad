# Results

```{admonition} No results yet
:class: warning
No TCAD simulation has been run. This section is a placeholder; Phase 1 will
first publish the SPICE reference dataset, and TCAD results follow only in
later phases.
```

When results exist, this section will hold auto-generated pages per device and
geometry, built from the hashed result files so the pages never show numbers
that are not reproducible:

- I-V and C-V overlay plots (TCAD, ngspice and Xyce);
- the table of extracted metrics, with a verdict (Agree, Same process or
  Disagree, see {doc}`../comparison/agreement`) for each device and metric;
- mesh pictures;
- the process file in use, with the provenance tag of every parameter.

Pages are generated into `docs/_generated/` at documentation build time.

```{toctree}
:maxdepth: 1

../_generated/index
```
