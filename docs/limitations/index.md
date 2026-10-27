# Limitations and status

Known shortcomings of this project, so that nobody reads more into it than is
there.

- **No silicon data.** No measured device I-V or C-V data exists for any
  {{ wafer_space }} {term}`run 1 or run 2 <wafer.space run>` design. See
  {doc}`silicon-validation`.
- **{term}`TCAD`: {term}`MOS capacitors <MOSCAP>` only, no MOSFET TCAD yet.** The
  {term}`SPICE` reference dataset of {term}`Phases 0 and 1` is complete. On the TCAD side the 1D
  and 2D MOS capacitors exist, with the start values and mesh-converged meshes
  ({doc}`mesh-convergence`, {doc}`moscap2d`), and the 1D one also with the calibrated values.
  The generated pages are {doc}`/_generated/tcad/index`; the limits of the model are
  {ref}`below <limitations-moscap>`.
- **The {term}`C–V` calibration is 1D only, and the pfet disagrees.** The 1D MOS capacitor is calibrated
  against the SPICE {term}`Cgg`–Vg
  ({repo}`calibration plan <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-12-calibrate-against-spice-cggvg>`,
  {doc}`/comparison/cv-agreement`). In 1D the nfet is {term}`Agree` at every geometry,
  fitted and held out; the pfet is {term}`Disagree`, because one length-independent stack cannot
  follow the SPICE pfet's depletion edge, which moves by 0.57 V with gate length
  ({ref}`mismatch analysis <cv-agreement-mismatch>`). The 2D validation of the calibrated stack
  is not run: no calibrated 2D results exist, since each 2D {term}`job` takes hours at 16 GiB, one at a
  time, the L = 2 µm cell has no AC and the L = 10 µm cell does not solve in 2D
  ({doc}`moscap2d`); [issue #35](https://github.com/mithro/gf180-tcad/issues/35).
- **TCAD {term}`provenance` was restamped, not regenerated.** The 2D results' `provenance.json`
  names the current generator, not the one that made them (Task 12), and every TCAD tree was
  restamped once more to the per-tree {term}`generator_sha256` of [issue #34](https://github.com/mithro/gf180-tcad/issues/34), without a rerun.
  Only the two calibrated 1D jobs are rerun and compared byte for byte by the cross-check; see
  {ref}`tcad-provenance`.
- **`make reproduce` does not yet reproduce the 2D TCAD files, and has not been run end to
  end.** The 2D job files lack entries the current job writes and the L = 2 µm {term}`sweeps <sweep>` are resumed ones, so a
  fresh run differs from them ({ref}`moscap2d-reproduce`). Only the calibrated 1D
  {term}`MOS capacitor` is cross-checked on a {{ GitHub_hosted_runner }} ({ref}`cross-host-tcad`);
  `make reproduce-quick` runs the same check locally ({ref}`make reproduce-quick <reproduce-quick>`).
- **The {{ gplugins }} {{ DEVSIM }} plugin is broken upstream.** It worked at gplugins v0.8.0 on
  its Sept-2023 stack and its import has failed since v0.8.1. A re-runnable record proves both;
  it is now fixed in {{ gplugins_fork }} and re-verified on the latest stack. See
  {doc}`plugin-history`.
- **Two TCAD stacks.** The final results come from the {term}`dev-HEAD TCAD image`
  (each project at its development HEAD, pinned by commit); the
  {term}`stable TCAD image` (PyPI releases) is the release baseline and is used for
  debugging. A dev HEAD can break what the release did; such drift is reported, never hidden
  by a looser {term}`tolerance`. See {ref}`tcad-dev-image`.
- **2D results are on the stable image for now.** The 1D results are made on the dev-HEAD
  image, byte-identical to the stable image's. The 2D MOS capacitor stays on the stable image
  until its {term}`mesh convergence` is rerun on the dev image, because {{ gmsh }} 5 meshes the 2D
  cells differently. That rerun is planned before the {term}`Phase 2` exit. See {ref}`tcad-results-image`.
- **Two dev-HEAD packages are forks.** The dev-HEAD image runs the full flow. To get there,
  {{ meshwell }} and the {{ gf180mcu_gdsfactory }} come from mithro forks of their upstream
  HEADs ({{ meshwell_fork }}, {{ gf180mcu_fork }}), and one test of {{ gplugins_fork }} is
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
- **The same bytes on another computer: only on some processors.** Byte-identical results are
  guaranteed only on {term}`x86-64-v2` or newer hosts, and the full reference is verified on an
  Intel Xeon Gold 6152 (local) and an AMD EPYC 7763 ({{ GitHub_hosted_runner }}) only
  ({ref}`cross-host-determinism`). On an AMD EPYC 9V45 runner only an 8-job subset has passed,
  and that run did not have the {{ numpy }} fix described there.
- **{term}`Mesh convergence <mesh convergence>` of the triangle mesh is looser in 2D.** The 1D
  {term}`MOSCAP` mesh changes by less than 1e-4 under {term}`uniform refinement`; the 2D mesh is
  selected at the 1 % criterion and carries a discretisation bias of a few 0.1 %. See
  {doc}`mesh-convergence` and {doc}`moscap2d`, which also explains the C/Cox > 1 artefact of the
  {{ meshwell }} default mesh (it rounds the oxide to 1 nm).
- **Not everything the design spec asks for is built yet.** See
  {ref}`limitations-spec-deviations` below.
- **Novelty.** No published {{ DEVSIM }}- or {{ Charon }}-versus-BSIM comparison for any
  open {term}`PDK` was found, and no {term}`gf180mcu <GF180MCU>` TCAD paper was found. See {doc}`literature`.

(limitations-moscap)=

## The TCAD MOS capacitor model

What the {term}`MOS capacitor <MOSCAP>` of {doc}`/comparison/cv-agreement` leaves out or lumps
together. Each is a modelling choice, stated so that the {term}`calibrated <calibrated parameter budget>`
values are not read as more physical than they are.

- **Quasi-static, not high-frequency.** The TCAD curve is the {term}`QS` one: the
  equilibrium {term}`Cgg`, the counterpart of the {term}`BSIM4` `capMod=2` Cgg of the
  {{ ngspice }} {term}`cv` sweep it is compared with. A MOS capacitor with only a body contact,
  measured with a small signal, gives the {term}`HF C–V` curve instead: in inversion it stays
  near its depletion minimum. The 2D cells have source and drain, which supply the inversion
  charge: at {term}`Lmin` their committed 1 MHz small-signal Cgg
  ({repo}`nfet cgx.csv <results/tcad/moscap2d/nfet_05v0/start/w10p0_l0p60/cgx.csv>`,
  {repo}`pfet cgx.csv <results/tcad/moscap2d/pfet_05v0/start/w10p0_l0p50/cgx.csv>`) follows
  their QS curve ({repo}`cv.csv <results/tcad/moscap2d/nfet_05v0/start/w10p0_l0p60/cv.csv>`):
  at all 21 AC biases from −5 V to +5 V the two differ by less than 1e-5 relative (3.3e-7
  measured), {test}`tests/tcad/test_moscap2d.py::test_committed_ac_follows_qs`. The in-image
  check is {test}`tests/tcad/test_moscap2d.py::test_ac_1mhz_recovers_inversion`; the runs are
  described on {doc}`moscap2d`. A measured test-structure C–V would have to be compared with
  the curve of its own contacts.
- **No quantum correction; the effective oxide absorbs it.** {{ DEVSIM }} 2.11.1 has no built-in
  {term}`density-gradient` model, and none is added here: classical {term}`drift-diffusion`
  puts the carrier charge at the interface. The quantum-mechanical dark space, the charge
  centroid that makes TOXE differ from TOXP, is folded into the
  {term}`effective oxide thickness` `t_ox_eff_nm`, bounded by TOXE below and by TOXP plus the
  charge-centroid allowance above ({ref}`process-data-tunables`; cause `oxide-qm` of the
  {ref}`mismatch taxonomy <mismatch-taxonomy>`).
- **The poly gate is simulated, with {term}`Boltzmann statistics`.** The gate is a poly-silicon region
  doped at {term}`NGATE` (n+ 1e20 cm⁻³ for the nfet, p+ 3.6e19 cm⁻³ for the pfet), so
  {term}`poly depletion` is in the model, not in a fitted term. Its carriers follow
  Boltzmann statistics, which place the Fermi level beyond the band edge at these
  dopings. At the start body doping of 1.7e17 cm⁻³ the Boltzmann flat band is **−1.029 V** for
  the nfet and **+1.003 V** for the pfet; at the calibrated body doping (`n_ch_cm3`
  8.81e16 cm⁻³ for the nfet, 2.15e17 cm⁻³ for the pfet,
  {repo}`results/tcad/calibration`) it is −1.012 V and +1.009 V ({py:mod}`gf180tcad.tcad.analytic`).
  With the degenerate gate's Fermi level pinned at its band edge instead (Eg/2 = 0.56 V from the
  intrinsic level, an estimate), the start flat band would be −0.993 V for the nfet and
  +0.993 V for the pfet. The Boltzmann gate puts the Fermi level beyond the band edge by
  36.5 mV in the nfet's n+ gate and 10.2 mV in the pfet's p+ gate, at any body doping. That
  difference is absorbed by the flat-band offset `dv_fb_v` with SPICE's empirical flat band
  and any interface charge ({ref}`process-data-tunables`). All of these numbers are checked by
  {test}`tests/tcad/test_analytic.py::test_flat_band_numbers_of_the_limitations_page`.
- **{term}`DLC` and the parasitics are reference bookkeeping.** The 1D C per area becomes a Cgg of one
  geometry through fixed BSIM4 values of the {term}`card <model card>`: the capacitance area
  (L − 2·DLC)·(W − 2·{term}`DWC`) and the overlap, fringe and {term}`CGBO` terms
  ({py:meth}`gf180tcad.tcad.moscap1d.MoscapCV.area_scaled`). They are not fitted and not part of
  the {term}`parameter budget`. At Lmin they are a large part of Cgg (about 4 of 14 fF
  in accumulation), so Lmin tests the bookkeeping as much as the TCAD. The split is plotted on
  each generated geometry page ({doc}`/_generated/tcad/index`).
- **{{ Xyce }} has no C–V analysis.** Cgg has one SPICE reference, ngspice, and the 0.5 %
  {term}`engine cross-check` cannot apply to it ({ref}`results-layout`).
- **The ΔV ≤ 50 mV crossing {term}`tolerance` is a proposal.** No published standard exists for
  it ({ref}`cv-agreement-metric`).
- **{repo}`results/plugin-history` is not cross-checked.** The {term}`manifest` lists it and two
  local runs give identical files, but it is not part of the check on another computer (a
  GitHub-hosted runner): its 2023 stack has no guarantee of the same bytes on another computer
  ({doc}`plugin-history`).

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
  {term}`Cgg` in depletion, effective {term}`Rsd`, Isub, {term}`Vt roll-off` and the root-mean-square (RMS) error
  of log10(Id). Defined differently: the {term}`body effect` uses the
  {term}`constant-current Vt` only, and {term}`gm_peak_s` is not the gm of the table. Details
  in {ref}`not yet extracted, or defined differently <metrics-not-yet-extracted>`.
- **No mesh pictures on the TCAD results pages.** The
  {repo}`design spec, section 10(b) <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#10-documentation-sphinx--read-the-docs>`
  asks for mesh pictures on the generated device and geometry pages. The 2D meshes are not
  committed ({ref}`moscap2d-meshes`), and the pages render only committed files, so
  {doc}`/_generated/tcad/index` shows each 2D job's mesh sha256 instead
  ([issue #39](https://github.com/mithro/gf180-tcad/issues/39)). The spec now settles how:
  {repo}`section 10.1 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#101-3d-renders-of-the-simulated-processes>`
  (amended 2026-10-27) draws the mesh pictures as part of the 3D renders of the simulated
  processes, from a committed reduced mesh artefact with provenance that is tied to each job's
  mesh sha256. That requirement has a plan of sub-tasks
  ([issue #43](https://github.com/mithro/gf180-tcad/issues/43)) but is not implemented yet, so
  no render and no mesh picture exists.
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
