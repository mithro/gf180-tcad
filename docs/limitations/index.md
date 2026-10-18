# Limitations and status

Known shortcomings of this project, so that nobody reads more into it than is
there.

- **No silicon data.** No measured device I-V or C-V data exists for any
  wafer.space run 1 or run 2 design (confirmed by the audit and bench
  sessions). See {doc}`silicon-validation`.
- **Phases 0 and 1 only, and only SPICE.** The work so far is foundations and
  the SPICE reference dataset.
- **TCAD not started.** No TCAD simulation has been run, so there is nothing
  to compare yet.
- **Unverified citations.** Several literature items have not been checked yet
  and are marked "unverified". See {doc}`literature`.
- **The SPICE models are a reference, not the truth.** BSIM4 is empirical,
  binned in L (the bin boundary is at 0.7 µm) and fitted to silicon, so it can
  be non-physical between bins. The BSIM parameters used as starting points are
  fitted values, not physical ones.
- **Novelty.** No published DEVSIM- or Charon-versus-BSIM comparison for any
  open PDK was found, and no gf180mcu TCAD paper was found.

```{toctree}
:maxdepth: 1

silicon-validation
literature
```
