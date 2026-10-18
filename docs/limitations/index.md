# Limitations and status

Known shortcomings of this project, so that nobody reads more into it than is
there.

- **No silicon data.** No measured device I-V or C-V data exists for any
  {{ wafer_space }} {term}`run 1 or run 2 <wafer.space run>` design. See
  {doc}`silicon-validation`.
- **{term}`Phases 0 and 1` only, and only {term}`SPICE`.** The work so far is foundations and
  the SPICE reference dataset.
- **{term}`TCAD` not started.** No TCAD simulation has been run, so there is nothing
  to compare yet.
- **Unverified citations.** Several literature items have not been checked yet
  and are marked "unverified". See {doc}`literature`.
- **The SPICE models are a reference, not the truth.** {term}`BSIM4` is empirical,
  {term}`binned` in L (the {term}`bin` boundary is at 0.7 µm) and fitted to silicon, so it can
  be non-physical between bins (the `spice-fit` cause in the
  {ref}`mismatch taxonomy <mismatch-taxonomy>`). The BSIM parameters used as starting points are
  fitted values, not physical ones.
- **{{ ngspice }} and {{ Xyce }} disagree by 0.6 % on the nfet in subthreshold.** The
  nfet {term}`card <model card>` declares BSIM4 `version=4.5`; ngspice runs it with BSIM4 4.5.0,
  Xyce's oldest BSIM4 is 4.6.1. See {doc}`engine-cross-check`.
- **Cross-host identity has limits.** Byte-identical results are guaranteed
  only on {term}`x86-64-v2` or newer hosts, and verified only on the hardware listed
  in {ref}`cross-host-determinism` (an Intel Xeon Gold 6152 and the
  {{ GitHub_hosted_runner }}s with AMD EPYC 9V45 and 7763 CPUs).
- **Novelty.** No published {{ DEVSIM }}- or {{ Charon }}-versus-BSIM comparison for any
  open {term}`PDK` was found, and no gf180mcu TCAD paper was found. See {doc}`literature`.

```{toctree}
:maxdepth: 1

silicon-validation
literature
engine-cross-check
```
