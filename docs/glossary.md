# Glossary

Terms used in these pages. Each definition is condensed from the page it links to, which is the
authoritative statement. Metric keys (such as `vt_lin_maxgm`) are the keys of `metrics.json`;
their exact extraction is in {py:mod}`gf180tcad.metrics`.

```{glossary}
:sorted:

TCAD
  Technology computer-aided design: physics-based device simulation, here with {{ DEVSIM }}
  cross-checked with {{ Charon }}. In this project it is the suspect being validated against the
  {term}`golden reference`. See {doc}`index`.

SPICE
  Circuit simulation with compact models. Here the {term}`PDK`'s {term}`BSIM4`
  {term}`model cards <model card>`, evaluated by {{ ngspice }} (primary) and {{ Xyce }}
  (secondary). See {ref}`comparison-space`.

golden reference
  The {term}`PDK` {term}`SPICE` models, against which the {term}`TCAD` is judged: "the SPICE models are the golden
  reference; the TCAD is the suspect". See {doc}`index`.

PDK
  Process design kit. Here the open {{ gf180mcu_pdk }}, its public documentation
  ({{ gf180mcu_pdk_docs }}) and its {term}`model cards <model card>`, installed in the image by {{ open_pdks }}. See
  {doc}`comparison/pdk-spec-check`.

GF180MCU
  GlobalFoundries' 180 nm MCU process, whose 5 V transistors this project models. See
  {doc}`index`.

BSIM4
BSIM
  The Berkeley compact MOSFET model ({{ BSIM4_site }}) used by the {term}`PDK` {term}`cards <model card>`. It is empirical,
  {term}`binned <bin>` in L and fitted to silicon, so it can be non-physical between {term}`bins <bin>`. See
  {doc}`limitations/index` and {ref}`BSIM4 manual <lit-bsim4>`.

model card
card
  The {term}`BSIM4` parameter set of one device in the {term}`PDK` model library ({{ gf180mcu_models }}), for
  example the {term}`nfet_06v0` card, with its declared `version`. See
  {doc}`limitations/engine-cross-check`.

bin
binned
L bin
  A gate-length range covered by one set of fitted {term}`BSIM4` parameters. The boundary inside the
  comparison space is at L = 0.7 µm. See {ref}`comparison-space`.

nfet_05v0
pfet_05v0
  The 5 V n- and p-channel devices compared here. They are wrappers around the
  {term}`nfet_06v0` and {term}`pfet_06v0` {term}`BSIM4` {term}`cards <model card>`, differing only in the mismatch parameter.
  See {ref}`comparison-space`.

nfet_06v0
pfet_06v0
  The 6 V devices whose {term}`BSIM4` {term}`cards <model card>` the 5 V devices wrap; one thick-oxide ({term}`Dualgate`)
  recipe serves both. See {ref}`comparison-space`.

Dualgate
  The thick-oxide layer of the 5 V and 6 V devices; one thick-oxide recipe serves both `05v0`
  and `06v0`. See {ref}`comparison-space` and {doc}`limitations/silicon-validation`.

Lmin
  The minimum drawn gate length of a device: 0.6 µm for the nfet and 0.5 µm for the pfet. See
  {ref}`comparison-space`.

geometry id
geometry_id
  The identifier of a W/L pair in file paths and on the command line, for example `w10p0_l0p60`
  (W = 10 µm, L = 0.60 µm). See {ref}`results-layout`.

corner
process corner
  A process corner of the {term}`PDK` model library: {term}`TT` and the {term}`FF`, {term}`SS corner`,
  {term}`FS` and {term}`SF` corners. On the command line they are `typical`, `ff`, `ss`, `fs`
  and `sf`. See {ref}`same-process-window`.

TT
typical corner
  The typical corner, at 25 °C here; it is the primary reference. Called `typical` on the
  command line and in result paths. See {ref}`comparison-space`.

FF
SS corner
FS
SF
  The four {term}`process corners <corner>` of the {term}`PDK` model library besides {term}`TT`. With TT they make the
  five corners of the {term}`corner envelope`. The SS corner is not the
  {term}`subthreshold slope`. See {ref}`same-process-window`.

corner envelope
  The min and max of a metric over the five {term}`corners <corner>` ({term}`TT`, {term}`FF`, SS, FS, SF), per engine, device
  and geometry, at the same bias. Published as {repo}`results/spice/envelope.json`. See
  {ref}`same-process-window` and {ref}`pdk-same-process-window`.

spec window
  The {term}`PDK`'s published min-max of a metric. A one-sided limit becomes an interval from 0, because
  a magnitude cannot be negative. See {doc}`comparison/pdk-spec-check`.

hull
  Of two intervals: the interval from the lowest lower bound to the highest upper bound. See
  {ref}`pdk-same-process-window`.

"Same process" window
  The interval used for the {term}`Same process` verdict: the {term}`hull` of the
  {term}`spec window` and the {term}`corner envelope`, or the corner envelope alone where the
  {term}`PDK` publishes no spec. The results pages say which one sets it (`spec`, `envelope` or `hull`).
  See {ref}`same-process-window`.

Agree
  Verdict for a device and metric: within the technical {term}`tolerance`. See
  {ref}`the verdicts <agreement-verdicts>`.

Same process
  Verdict for a device and metric: outside the {term}`tolerance` but inside the {term}`PDK`'s own
  min-max {term}`spec window`. The {term}`TCAD` device is plausibly *a* GF180 device, not *the* typical
  one. See {ref}`the verdicts <agreement-verdicts>`.

Disagree
  Verdict for a device and metric: outside the {term}`spec window`; the {term}`TCAD` is describing a
  different process. See {ref}`the verdicts <agreement-verdicts>`.

tolerance
  The allowed {term}`TCAD`-versus-SPICE error of a metric, from the {ref}`ITRS 2007 <lit-itrs>` Modeling and Simulation
  chapter, Table MS3, unless marked *proposal*. See {ref}`tolerances`.

calibration target
  A characteristic the {term}`process description` may be tuned on: long-channel {term}`Cgg`-Vg,
  long-channel {term}`Vt` and {term}`body effect`, Vt(L) {term}`roll-off <Vt roll-off>` and {term}`subthreshold slope`. See
  {ref}`calibration-validation`.

validation target
  A characteristic that must never be tuned on, because it is the evidence: {term}`Idsat`, {term}`linear Id`,
  {term}`gm`, {term}`gds`, {term}`Vt` at the narrow width, {term}`DIBL`, and everything at the
  {term}`held-out geometries <held-out geometry>`. See {ref}`calibration-validation`.

held-out geometry
  A geometry fixed before calibration and used for validation only: W = 10 µm at L = 0.7 and
  1 µm, and the narrow 1.6/0.7. See {ref}`calibration-validation`.

calibrated parameter budget
parameter budget
  At most 8 calibrated parameters per device type (n or p), shared across all geometries. See
  {ref}`parameter-budget`.

process description
process file
  The single set of doping, oxide, mobility and contact parameters used for every gate length
  and width, recorded machine-readably with the {term}`provenance tag` of each value. See
  {ref}`parameter-budget`.

provenance tag
  The source label every process parameter value carries: `pdk-doc`, `spice-card`, `literature`
  or `calibrated`. See {ref}`parameter-budget`.

Vt
threshold voltage
  The gate voltage at which the device turns on. The `vt_*` metrics are reported signed by
  polarity (nfet positive, pfet negative). See {py:mod}`gf180tcad.metrics`.

VT0
  The {term}`PDK` spec's "linear {term}`threshold voltage <Vt>`", compared with {term}`vt_lin_maxgm`. See
  {ref}`pdk-definition-notes`.

vt_lin_maxgm
max-gm Vt
  {term}`Vt` by linear extrapolation of Id(Vgs) at the point of maximum {term}`gm` on {term}`idvg_lin`
  (Vds = 0.1 V): Vgs* - Id*/gm* - Vds/2. See {py:func}`gf180tcad.metrics.vt_maxgm`.

vt_lin_cc
vt_sat_cc
constant-current Vt
  {term}`Vt` as the first Vgs where Id = 100 nA·W/L, on {term}`idvg_lin` and on `idvg_sat` respectively. See
  {py:func}`gf180tcad.metrics.vt_cc`.

Vt roll-off
roll-off
  The change of {term}`Vt` with gate length: Vt({term}`Lmin`) - Vt(10 µm). See {ref}`tolerances`.

body effect
body_effect_v
  The {term}`Vt` shift under reverse body bias: {term}`vt_lin_cc` at |Vbs| = 2 V minus `vt_lin_cc` at
  |Vbs| = 0. See {py:func}`gf180tcad.metrics.body_effect`.

DIBL
dibl_mv_per_v
  Drain-induced barrier lowering: ({term}`vt_lin_cc` - `vt_sat_cc`) / (5.0 V - 0.1 V), in mV/V. See
  {py:func}`gf180tcad.metrics.dibl`.

subthreshold slope
ss_mv_per_dec
  The gate-voltage change per decade of Id below threshold, fitted over Id/W in [1e-11, 1e-8]
  A/µm, in mV/dec. Often written SS; it is not the {term}`SS corner`. See
  {py:func}`gf180tcad.metrics.subthreshold_slope`.

Idsat
idsat_ua_per_um
  Saturation current per width: |Id|/W at |Vgs| = |Vds| = 5 V and |Vbs| = 0, in µA/µm. See
  {py:func}`gf180tcad.metrics.idsat_per_um`.

Ioff
ioff_pa_per_um
  Off-state leakage per width: Id/W at Vgs = 0 and Vds = 5.5 V, in pA/µm. See
  {py:func}`gf180tcad.metrics.ioff_per_um`.

linear Id
id_lin_a
  The total Id on {term}`idvg_lin` at Vgs = {term}`vt_lin_maxgm` + 0.5 V. See
  {py:func}`gf180tcad.metrics.id_lin`.

gm
gm_peak_s
  Transconductance dId/dVgs; `gm_peak_s` is its maximum on {term}`idvg_lin`. See
  {py:func}`gf180tcad.metrics.gm`.

gds
gds_at_5v_s
  Output conductance dId/dVds; `gds_at_5v_s` is taken at Vgs = Vds = 5 V on {term}`idvd`. See
  {py:func}`gf180tcad.metrics.gds`.

Cgg
cgg_inv_ff
cgg_acc_ff
  Total gate capacitance, from the {term}`cv` sweep at 1 MHz: `cgg_inv_ff` at +5 V (inversion) and
  `cgg_acc_ff` at -5 V (accumulation), in {term}`fF <FF>`. Only ngspice runs the `cv` sweep. See
  {py:mod}`gf180tcad.metrics`.

Rsd
  Source/drain series resistance (contact, silicide and {term}`LDD`). The {term}`SPICE` {term}`card <model card>` has RDSW
  2175 Ω·µm. See {ref}`mismatch-taxonomy`.

BVDSS
  Drain-source breakdown voltage. The {term}`PDK` publishes it, but breakdown is not simulated, so it is
  not compared. See {ref}`pdk-definition-notes`.

σ_mismatch
A_Vt
  The mismatch scale σ_ΔVt = A_Vt / √(W·L) of the {term}`Vt` difference of a pair, with the effective W
  and L ({ref}`Pelgrom 1989 <lit-pelgrom>`), used to express an error
  in physical units. See {ref}`tolerances`.

polarity-stripped
  Voltages and currents multiplied by the device polarity, so the nfet and the pfet plot alike
  (|Vgs|, |Vds|, |Id|). See {py:mod}`gf180tcad.docgen`.

sweep
idvg_lin
idvg_sat
idvd
cv
  One simulated bias family: `idvg_lin` (Id-Vg at Vds = 0.1 V), `idvg_sat` (Id-Vg at
  Vds = 5 V), `idvd` (Id-Vd), `ioff` (Vgs = 0, Vds = 5.5 V) and `cv` ({term}`Cgg`-Vg, ngspice only).
  Each is one `<sweep>.csv`. See {py:data}`gf180tcad.devices.SWEEPS` and {ref}`results-layout`.

gmin
  The small conductance (1e-12 S) that {term}`SPICE` puts across every junction. At Vds = 5 V it lets
  about 5 pA flow with the device off, a leakage floor. See {doc}`limitations/engine-cross-check`.

engine cross-check
  The ngspice-versus-Xyce comparison of the {term}`SPICE` reference. A difference above 0.5 % flags a
  problem with the reference, not with the {term}`TCAD`. See {ref}`comparison-space` and
  {doc}`limitations/engine-cross-check`.

engine_diff
  max |Id,ngspice - Id,Xyce| / max(|Id,ngspice|, |Id,Xyce|) over the bias points where either
  engine gives |Id| > 1 pA. See {py:func}`gf180tcad.spice.xyce.engine_diff`.

strict expected failure
xfail
  A test marked as expected to fail that errors if it unexpectedly passes, so a fix shows up
  ([pytest strict xfail](https://docs.pytest.org/en/stable/how-to/skipping.html#strict-parameter)).
  The known engine differences are listed in {py:data}`gf180tcad.known.KNOWN_ENGINE_DIFFS`. See
  {doc}`limitations/engine-cross-check`.

job
  One engine, {term}`corner`, device and geometry of the {term}`SPICE` reference, run as one {term}`sandbox`
  container. See {ref}`how the reference runs <reproduce-how-it-works>`.

sandbox
  The resource-limited container wrapper {repo}`tools/sandbox-run` ({{ Python }}:
  {py:func}`gf180tcad.sandbox.run`) through which every simulator run goes. See
  {doc}`reproduce/sandbox`.

slice
gf180-tcad.slice
  The {{ systemd }} slice unit (a {term}`cgroup`) that caps the aggregate memory and tasks of all
  {term}`sandbox` containers together. See {ref}`sandbox-host-setup`.

cgroup
  Linux control group ([cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)). The
  {term}`sandbox` containers run with {term}`gf180-tcad.slice` as their cgroup parent. See
  {ref}`sandbox-per-run-limits`.

OOM
  Out of memory. An OOM-killed {term}`sandbox` run exits with 137
  ({py:data}`gf180tcad.sandbox.OOM_EXIT`), which {py:func}`gf180tcad.sandbox.run` raises as
  {py:class}`~gf180tcad.sandbox.SandboxOOM`. See {ref}`sandbox-failure-behaviour`.

manifest
  {repo}`results/MANIFEST.sha256`: the sha256 of every result file. `make reproduce` verifies
  the results against it. See {ref}`one-command`.

manifest digest
  The digest of the image {term}`manifest`
  ([OCI image manifest](https://github.com/opencontainers/image-spec/blob/main/manifest.md)),
  recorded in {repo}`docker/IMAGE`; it selects the image to run. See {ref}`image-pinning`.

config digest
image ID
  The digest of the image configuration
  ([OCI image configuration](https://github.com/opencontainers/image-spec/blob/main/config.md)),
  which covers the layer `diff_id`s; recorded in {repo}`docker/base/IMAGE_ID`. See
  {ref}`image-pinning`.

provenance
  The recorded tool and {term}`PDK` versions ({repo}`docker/base/versions.json`) and the generator
  identity, both written to {repo}`results/spice/provenance.json`. See {ref}`image-pinning` and
  {ref}`results-layout`.

generator_sha256
  The sha256 over the sorted (path, sha256) pairs of the source files of
  {py:data}`gf180tcad.reference.GENERATOR_MODULES` plus {repo}`tools/sandbox-run`. See
  {py:func}`gf180tcad.reference.generator_sha256` and {ref}`results-layout`.

Phase 0
Phase 1
Phases 0 and 1
  The project phases so far: foundations (Phase 0) and the {term}`SPICE` reference dataset (Phase 1).
  Later phases add the {term}`TCAD`. See the
  {repo}`design spec, section 13 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#13-phases>`.

Phase 2
Phase 3
Phase 3 entry gate
  The next phases: a MOS capacitor in {{ DEVSIM }} (Phase 2), then the 2D MOSFET (Phase 3). The
  Phase 3 entry gate is the list of what must exist before any MOSFET {term}`TCAD` result,
  including the deviations from the design spec still open at the end of
  {term}`Phases 0 and 1`. See
  {ref}`limitations-spec-deviations` and the
  {repo}`design spec, section 13 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#13-phases>`.

Gummel symmetry test
  A model benchmark: the model must be smooth through Vds = 0 ({ref}`McAndrew 2006 <lit-mcandrew>`). See {ref}`numerical-acceptance`.

drift-diffusion
density-gradient
  The classical carrier-transport model, and its quantum correction ({ref}`Ancona and Iafrate 1989 <lit-ancona>`). See {ref}`mismatch-taxonomy`.

LDD
S/D
STI
LOD
  Lightly doped drain; source/drain; shallow-trench isolation; length of diffusion (a stress
  effect). See {ref}`mismatch-taxonomy`.

wafer.space run
ws-run1
ws-run2
  A {{ wafer_space }} {term}`GF180MCU` shuttle run ([run 1](https://github.com/wafer-space/ws-run1),
  [run 2](https://github.com/wafer-space/ws-run2)). Some designs on runs 1 and 2 carry candidate
  test structures. See {doc}`limitations/silicon-validation`.

x86-64-v2
  The x86-64 microarchitecture level of the baseline kernels of {{ numpy }}. The {term}`sandbox` pins
  numpy to them, so hosts with different SIMD extensions compute the same bits. See
  {ref}`cross-host-determinism`.

SIMD dispatch
  numpy's run-time choice of a compute kernel by CPU feature level
  ([numpy runtime dispatch](https://numpy.org/doc/stable/reference/simd/build-options.html#runtime-dispatch)).
  Two kernels can differ by one {term}`ulp`. See {ref}`cross-host-determinism`.

ulp
  Unit in the last place: the spacing between adjacent floating-point numbers, so the smallest
  possible difference between two floats. See {ref}`cross-host-determinism`.
```
