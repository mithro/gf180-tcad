# Limitations and status

Known shortcomings of this project, so that nobody reads more into it than is
there.

- **No silicon data.** No measured device I-V or C-V data exists for any
  {{ wafer_space }} {term}`run 1 or run 2 <wafer.space run>` design. See
  {doc}`silicon-validation`.
- **{term}`TCAD`: {term}`MOS capacitors <MOSCAP>` only, no MOSFET TCAD yet.** The
  {term}`SPICE` reference dataset of {term}`Phases 0 and 1` is complete. On the TCAD side the 1D
  and 2D MOS capacitors exist, with the start values and mesh-converged meshes
  ({doc}`mesh-convergence`, {doc}`moscap2d`). The calibration against SPICE is
  {repo}`Task 12 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-12-calibrate-against-spice-cggvg>`.
- **The {{ gplugins }} {{ DEVSIM }} plugin is broken upstream.** It worked at gplugins v0.8.0 on
  its Sept-2023 stack and its import has failed since v0.8.1. A re-runnable record proves both;
  it is now fixed in {{ gplugins_fork }} and re-verified on the latest stack. See
  {doc}`plugin-history`.
- **Two TCAD stacks.** The final results come from the {term}`dev-HEAD TCAD image`
  (each project at its development HEAD, pinned by commit); the
  {term}`stable TCAD image` (PyPI releases) is the baseline for how things used to work and for
  debugging. A dev HEAD can break what the release did; such drift is reported, never hidden
  by a looser {term}`tolerance`. See {ref}`tcad-dev-image`.
- **2D results are on the stable image for now.** The 1D results are made on the dev-HEAD
  image, byte-identical to the stable image's. The 2D MOS capacitor stays on the stable image
  until its {term}`mesh convergence` is rerun on the dev image, because {{ gmsh }} 5 meshes the 2D
  cells differently. That rerun is planned before the {term}`Phase 2` exit. See {ref}`tcad-results-image`.
- **Two dev-HEAD packages are forks.** The dev-HEAD image runs the full flow. To get there,
  {{ meshwell }} and the {{ gf180mcu_gdsfactory }} come from mithro forks of their upstream
  HEADs ({{ meshwell_fork }}, {{ gf180mcu_fork }}), and one test of {{ gplugins_fork }} was
  replaced by a mesh-independent check
  ([mithro/gplugins#10](https://github.com/mithro/gplugins/pull/10)). Each fork adds a small fix for {{ gmsh }} 5 or {{ gdsfactory }} 10
  that upstream does not have yet. These fixes are not upstream, and nothing is sent upstream.
  The forks, and what each fixes, are listed in {ref}`tcad-dev-forks`.
- **Build inputs are mirrored.** Every file the dev-HEAD image build fetches is also on
  {{ input_mirror }}. The build checks each file's sha256, from the mirror or from the original
  URL. A file that disappears from both stops the build; it cannot change it silently. See
  {ref}`tcad-dev-mirror`.
- **Unverified citations.** Several literature items have not been checked yet
  and are marked "unverified". See {doc}`literature`.
- **The SPICE models are a reference, not the truth.** {term}`BSIM4` is empirical,
  {term}`binned` in L (the {term}`bin` boundary is at 0.7 µm) and fitted to silicon, so it can
  be non-physical between bins (the `spice-fit` cause in the
  {ref}`mismatch taxonomy <mismatch-taxonomy>`). The {term}`BSIM` parameters used as starting points are
  fitted values, not physical ones.
- **{{ ngspice }} and {{ Xyce }} disagree by 0.6 % on the nfet in subthreshold.** The
  nfet {term}`card <model card>` declares BSIM4 `version=4.5`; ngspice runs it with BSIM4 4.5.0,
  Xyce's oldest BSIM4 is 4.6.1. See {doc}`engine-cross-check`.
- **Cross-host identity has limits.** Byte-identical results are guaranteed
  only on {term}`x86-64-v2` or newer hosts, and the full reference is verified on an Intel Xeon
  Gold 6152 (local) and an AMD EPYC 7763 ({{ GitHub_hosted_runner }}) only
  ({ref}`cross-host-determinism`). The only pass on an AMD EPYC 9V45 runner was an earlier
  8-job subset, before the {{ numpy }} fix described there.
- **{term}`Mesh convergence <mesh convergence>` of the triangle mesh is looser in 2D.** The 1D
  {term}`MOSCAP` mesh changes by less than 1e-4 under {term}`uniform refinement`; the 2D mesh is
  selected at the 1 % criterion and carries a discretisation bias of a few 0.1 %. See
  {doc}`mesh-convergence` and {doc}`moscap2d`, which also explains the C/Cox > 1 artefact of the
  research spike ({{ meshwell }} rounded the oxide to 1 nm).
- **Not everything the design spec asks for is built yet.** See
  {ref}`limitations-spec-deviations` below.
- **Novelty.** No published {{ DEVSIM }}- or {{ Charon }}-versus-BSIM comparison for any
  open {term}`PDK` was found, and no {term}`gf180mcu <GF180MCU>` TCAD paper was found. See {doc}`literature`.

(limitations-spec-deviations)=

## Deviations from the design spec

Recorded and accepted for the end of {term}`Phases 0 and 1`. Each is a
{term}`Phase 3 entry gate`: it must be closed before any MOSFET {term}`TCAD` result.

- **No layout-extracted secondary SPICE reference.** The
  {repo}`design spec, section 5.2 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#52-technical-definition>`
  asks for a second reference with instance parameters extracted from the {{ gdsfactory }}
  cell layout. Only the primary, schematic-default reference exists
  ({ref}`planned secondary reference <secondary-reference>`).
- **The metric set is narrower than the {term}`tolerance` table.** Not yet extracted:
  {term}`gm` and {term}`gds` at Vgs = {term}`Vt` + 150 mV, gm/Id, Cgd at Vds = 5 V,
  {term}`Cgg` in depletion, effective {term}`Rsd`, Isub, {term}`Vt roll-off` and the RMS error
  of log10(Id). Defined differently: the {term}`body effect` uses the
  {term}`constant-current Vt` only, and {term}`gm_peak_s` is not the gm of the table. Details
  in {ref}`not yet extracted, or defined differently <metrics-not-yet-extracted>`.
- **{term}`Cgg` in depletion is not held to 5 %.** The design spec sets {term}`Cgg` ≤ 5 % in
  accumulation, depletion and inversion. The {term}`TCAD` calibration holds the two plateaus
  to 5 % and replaces the depletion-region 5 % with the voltage shifts of the two
  mid-capacitance crossings, each ≤ 50 mV (a proposal: no published standard). In the
  transition a relative-C metric measures the slope of the curve, not agreement; the numbers
  are on {doc}`/comparison/cv-agreement`. The depletion error is still reported.

```{toctree}
:maxdepth: 1

silicon-validation
literature
engine-cross-check
plugin-history
mesh-convergence
moscap2d
```
