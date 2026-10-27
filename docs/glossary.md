# Glossary

Terms used in these pages. Each definition is condensed from the page it links to, which is the
authoritative statement. Metric keys (such as `vt_lin_maxgm`) are the keys of `metrics.json`;
their exact extraction is in {py:mod}`gf180tcad.metrics`.

```{glossary}
:sorted:

dev-HEAD TCAD image
  The {term}`TCAD` image built from each upstream project's development HEAD ({{ DEVSIM }} from source,
  {{ meshwell }}, {{ gdsfactory }}, the {{ gf180mcu_gdsfactory }} and {{ gmsh }}), pinned by
  commit: the stack of the final results. See {ref}`tcad-dev-image`.

stable TCAD image
  The {term}`TCAD` image built from the latest PyPI releases of the TCAD stack: the released
  baseline, used to tell a regression in a development version from a bug here. See {ref}`tcad-image`.

TCAD
  Technology computer-aided design: physics-based device simulation, here with {{ DEVSIM }}
  cross-checked with {{ Charon }}. In this project it is what is being tested: its results are
  compared with the {term}`SPICE reference <SPICE reference results>`. See {doc}`index`.

SPICE
  Circuit simulation with compact models. Here the {term}`PDK`'s {term}`BSIM4`
  {term}`model cards <model card>`, evaluated by {{ ngspice }} (primary) and {{ Xyce }}
  (secondary). See {ref}`comparison-space`.

SPICE reference results
  The results of the {term}`PDK`'s {term}`SPICE` models, simulated by {{ ngspice }} and {{ Xyce }}
  and committed under {repo}`results/spice`: the yardstick the {term}`TCAD` is compared with.
  See {doc}`index`.

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

combined range
  Of two ranges: the range from the lower of the two minimums to the higher of the two maximums
  (in interval arithmetic, the interval hull). The code calls it `hull`. See
  {ref}`pdk-same-process-window`.

"Same process" window
  The interval used for the {term}`Same process` verdict: the {term}`combined range` of the
  {term}`spec window` and the {term}`corner envelope`, or the corner envelope alone where the
  {term}`PDK` publishes no spec. The results pages say which one sets it (spec, corner envelope
  or combined range).
  See {ref}`same-process-window`.

Agree
  Verdict for a device and metric: within the technical {term}`tolerance`. See
  {ref}`the verdicts <agreement-verdicts>`.

Same process
  Verdict for a device and metric: outside the {term}`tolerance` but inside the
  {term}`"Same process" window`, which combines the {term}`PDK`'s own min-max {term}`spec window`
  and the {term}`corner envelope`. The {term}`TCAD` device is then inside the range the PDK
  specifies, not at its typical point. See {ref}`the verdicts <agreement-verdicts>`.

Disagree
  Verdict for a device and metric: outside the {term}`"Same process" window`; the {term}`TCAD` is
  describing a different process. See {ref}`the verdicts <agreement-verdicts>`.

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
  1 µm, and the narrow W = 1.6 µm, L = 0.7 µm. It plays the part of the test set of statistics,
  which "should be kept in a “vault,” and be brought out only at the end of the data analysis"
  ([Hastie, Tibshirani and Friedman, *The Elements of Statistical Learning*, 2nd ed., section 7.2](https://hastie.su.domains/ElemStatLearn/)).
  See {ref}`calibration-validation`.

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

C–V
quasi-static
QS
  Capacitance–voltage: the gate capacitance {term}`Cgg` against the gate bias. The quasi-static
  (QS, low-frequency) curve is the equilibrium one and rises back towards the {term}`oxide capacitance <Cox>` in
  inversion; {term}`BSIM4` [`capMod=2`](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip) gives it. A {term}`MOSCAP` solved by small-signal AC with only
  a body contact gives the high-frequency curve instead. See {ref}`plugin-history-latest`.

HF C–V
high-frequency C–V
  The {term}`C–V` measured with a small signal too fast for the inversion layer to follow: in inversion
  the capacitance stays near its depletion minimum instead of recovering to {term}`Cox`.
  Technically, {term}`minority carriers <minority carrier>` are generated thermally in a time of order 2τ·N/n_i, so above that rate
  only the depletion edge responds; a 1D {term}`MOSCAP` with only a body contact gives this
  curve at any practical frequency ([Sze & Ng, ch. 4](https://doi.org/10.1002/0470068329)). See {ref}`plugin-history-latest`.

Cox
oxide capacitance
  The capacitance per area of the gate oxide alone, the ceiling of the {term}`C–V` curve.
  Technically Cox = ε_ox·ε0/t_ox; for the nfet's 15.2 nm and {term}`EPSROX` 3.9 it is
  2.2718 fF/µm² ([Sze & Ng, ch. 4](https://doi.org/10.1002/0470068329)). See {ref}`process-data`.

effective oxide thickness
t_ox_eff
  The oxide thickness that gives the measured (or {term}`SPICE`) accumulation and inversion
  capacitance, so it lumps the charge centroids in the silicon with the physical oxide.
  Technically t_ox_eff = ε_ox·ε0/C_plateau; {term}`BSIM4` separates TOXE (electrical) from TOXP
  (physical) for this reason ([BSIM4 manual](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip), section 7.3). Here it is the tunable
  `t_ox_eff_nm`. See {ref}`process-data-tunables`.

poly depletion
  The depletion of the poly-silicon gate next to the oxide, which adds a capacitance in series
  with {term}`Cox` and lowers the inversion capacitance. Technically the gate is a second
  semiconductor at {term}`NGATE`, whose space charge follows the same charge function as the
  body ([Sze & Ng, ch. 4](https://doi.org/10.1002/0470068329); [BSIM4 manual](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip), the poly-depletion model). See
  {ref}`process-data`.

DLC
DWC
  The length (DLC) and width (DWC) offsets of {term}`BSIM4`'s capacitance geometry:
  LeffCV = L + {term}`XL` − 2·DLC and WeffCV = W + XW − 2·DWC. When the {term}`card <model card>` sets none, DLC defaults
  to LINT and DWC to WINT ([ngspice `b4set.c`](https://sourceforge.net/p/ngspice/ngspice/ci/ngspice-47/tree/src/spicelib/devices/bsim4/b4set.c), [`b4temp.c`](https://sourceforge.net/p/ngspice/ngspice/ci/ngspice-47/tree/src/spicelib/devices/bsim4/b4temp.c);
  [BSIM4 manual](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip), Appendix A). See {ref}`process-data`.

XL
XW
  The {term}`BSIM4` mask/etch offsets of the drawn length and width, added before the
  {term}`DLC`/{term}`DWC` offsets ([BSIM4 manual](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip), Appendix A). Both are 0 on the
  5 V {term}`cards <model card>`. See {ref}`process-data`.

CKAPPAS
CKAPPAD
  The coefficients (V) of {term}`BSIM4`'s bias-dependent gate-source and gate-drain overlap
  ({term}`LDD`) capacitance with CGSL and CGDL, in the `capMod` 1 and 2 overlap equations
  ([BSIM4 manual](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip), section 7.5; [ngspice `b4ld.c`](https://sourceforge.net/p/ngspice/ngspice/ci/ngspice-47/tree/src/spicelib/devices/bsim4/b4ld.c)). See {ref}`process-data`.

CGBO
  {term}`BSIM4`'s gate-bulk overlap capacitance per channel length, multiplied by LeffCV
  ([BSIM4 manual](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip), section 7.5). See {ref}`process-data`.

VFBCV
  {term}`BSIM4`'s flat-band voltage for `capMod=0` only; it does not enter the `capMod=2`
  equations ([BSIM4 manual](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip), Appendix A). See {ref}`process-data`.

VFBSDOFF
  {term}`BSIM4`'s flat-band offset of the source/drain overlap region; 0 on the nfet {term}`card <model card>` and
  unset (default 0) on the pfet card ([BSIM4 manual](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip), Appendix A). See {ref}`process-data`.

EPSROX
  The relative permittivity of the gate oxide in the {term}`BSIM4` {term}`card <model card>`, 3.9 for both 5 V
  devices; the {term}`TCAD` oxide uses it ([BSIM4 manual](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip), Appendix A). See {ref}`process-data`.

NGATE
  The poly-silicon gate doping of the {term}`BSIM4` {term}`card <model card>` (1e20 cm⁻³ n⁺ for the nfet, 3.6e19 p⁺
  for the pfet), the doping of the {term}`TCAD` poly-gate region ([BSIM4 manual](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip), Appendix A).
  See {ref}`process-data`.

XJ
  The source/drain junction depth of the {term}`BSIM4` {term}`card <model card>`, 0.15 µm for both 5 V devices
  ([BSIM4 manual](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip), Appendix A); the 2D {term}`TCAD`
  {term}`MOSCAP` places its source/drain junction there ({py:mod}`gf180tcad.tcad.stack`). See {ref}`process-data`.

NSD
  The source/drain doping of the {term}`BSIM4` {term}`card <model card>` (1e20 cm⁻³ on the nfet card; the pfet card's
  6e16 is no source/drain doping and is not used) ([BSIM4 manual](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip), Appendix A); the peak of the
  2D {term}`TCAD` {term}`MOSCAP`'s source and drain ({py:mod}`gf180tcad.tcad.stack`). See {ref}`process-data`.

LLC
LWC
LWLC
WLC
WWC
WWLC
  The length- and width-dependent terms of {term}`BSIM4`'s capacitance offsets (dLc, dWc);
  zero or unset on the 5 V {term}`cards <model card>`, so LeffCV and WeffCV reduce to the {term}`DLC`/{term}`DWC`
  forms ([BSIM4 manual](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip), Appendix A). See {ref}`process-data`.

uniform refinement
mesh convergence
  Refining every spacing of a mesh by the same factor, grading fixed, to show that the
  results do not depend on the mesh. Here each {term}`TCAD` {term}`MOSCAP` is solved at four
  levels a factor √2 apart ({py:data}`gf180tcad.tcad.meshconv.LEVELS`), and a level is converged
  when the next finer one changes its {term}`C–V` by less than 1 % at every bias
  ([Roache 1994](https://doi.org/10.1115/1.2910291)). See {ref}`mesh-convergence`.

Poisson–Boltzmann
  The electrostatics of a semiconductor in equilibrium: Poisson's equation with the carrier
  densities given by {term}`Boltzmann statistics`, so the charge follows from the potential alone.
  For a uniformly doped {term}`MOS capacitor <MOSCAP>` it has an exact closed-form charge
  function Q_s(ψ_s), the reference the 1D {term}`TCAD` MOS capacitor is tested against
  ({py:mod}`gf180tcad.tcad.analytic`; [Sze & Ng, ch. 4](https://doi.org/10.1002/0470068329)).
  See {ref}`mesh-convergence`.

observed order of convergence
  The rate at which the discretisation error falls as the mesh is refined, measured from the
  results instead of assumed. Technically, for three levels a constant ratio r apart,
  p = log(|C₁ − C₂| / |C₂ − C₃|) / log r; a second-order scheme in its asymptotic range gives
  p ≈ 2 ([Celik et al. 2008](https://doi.org/10.1115/1.2960953)). See {ref}`mesh-convergence`.

Richardson extrapolation
  An estimate of the mesh-independent value from two fine levels and the
  {term}`observed order <observed order of convergence>` p: C_exact ≈ C₃ + (C₃ − C₂)/(r^p − 1)
  ([Richardson 1911](https://doi.org/10.1098/rsta.1911.0009);
  [Celik et al. 2008](https://doi.org/10.1115/1.2960953)). See {ref}`mesh-convergence`.

UMFPACK
  The sparse direct linear solver of [SuiteSparse](https://people.engr.tamu.edu/davis/suitesparse.html)
  that {{ DEVSIM }} uses; version 5.1 fails ("umfpack numeric failed") on the largest 2D cells. See
  {ref}`moscap2d-l10`.

Newton iteration
  The solver step of {{ DEVSIM }}: it linearises the discretised equations about the current
  solution, solves the linear system, updates the solution and repeats until the update falls
  below the {term}`tolerance` ([Newton's method](https://en.wikipedia.org/wiki/Newton%27s_method)). See
  {ref}`moscap2d-solver`.

MOSCAP
MOS capacitor
  A poly-gate, oxide and body stack without source and drain, simulated by the {term}`TCAD` to
  compare its {term}`C–V` with the {term}`SPICE` {term}`Cgg`. See {ref}`plugin-history-latest`.

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

sign-flipped
  Voltages and currents multiplied by the device polarity (+1 for the nfet, −1 for the pfet),
  so the nfet and the pfet plot alike (|Vgs|, |Vds|, |Id|). See {py:mod}`gf180tcad.docgen`.

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
  5 pA flow (1e-12 S × 5 V) with the device off, a leakage floor. See {doc}`limitations/engine-cross-check`.

engine cross-check
  The ngspice-versus-Xyce comparison of the {term}`SPICE reference <SPICE reference results>`. A difference above 0.5 % flags a
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
  One simulation run in its own {term}`sandbox` container: for the {term}`SPICE reference <SPICE reference results>` one
  engine, {term}`corner`, device and geometry; for the {term}`TCAD` one device, geometry and
  set of parameter values. See {ref}`how the reference runs <reproduce-how-it-works>`.

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

render manifest
  The file `<render>.render.json` beside a 3D render. It names the source, value and scale of
  every number the render draws. See {ref}`render-manifest`.

provenance
  The recorded tool and {term}`PDK` versions ({repo}`docker/base/versions.json`) and the generator
  identity, both written to {repo}`results/spice/provenance.json`. See {ref}`image-pinning` and
  {ref}`results-layout`.

generator_sha256
  The sha256 over the sorted (path, sha256) pairs of the source files of
  {py:data}`gf180tcad.reference.GENERATOR_MODULES` plus {repo}`tools/sandbox-run`. See
  {py:func}`gf180tcad.reference.generator_sha256` and {ref}`results-layout`. Each {term}`TCAD` results folder has
  its own, over the import closure of the entry point that writes it
  ({py:data}`gf180tcad.tcad.TCAD_GENERATORS`, from {repo}`src/gf180tcad/generators.json`;
  {py:func}`gf180tcad.tcad.generator_sha256`) and the shared inputs; see {ref}`tcad-provenance`.

Phase 0
Phase 1
Phases 0 and 1
  The first two project phases, both complete: foundations (Phase 0) and the {term}`SPICE`
  reference dataset (Phase 1). Later phases add the {term}`TCAD`. See the
  {repo}`design spec, section 13 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#13-phases>`.

Phase 2
Phase 3
Phase 4
  The {term}`TCAD` phases. Phase 2, in progress: the {{ gplugins }} {{ DEVSIM }} plugin fix and the
  1D and 2D {term}`MOS capacitor <MOSCAP>`, calibrated against the {term}`SPICE` {term}`Cgg`–Vg.
  Phase 3, not started: the 2D MOSFET, on both backends. Phase 4, planned, alongside Phases 2
  and 3: {{ Charon }} beside {{ DEVSIM }}, and their comparison. See the
  {repo}`Phase 2 plan <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md>` and the
  {repo}`Phase 4 plan <docs/superpowers/plans/2026-10-27-phase4-charon-backend.md>`.

Phase 3 entry gate
  The list of what must exist before any MOSFET {term}`TCAD` result, including the deviations
  from the design spec still open at the end of {term}`Phases 0 and 1`. See
  {ref}`limitations-spec-deviations` and the
  {repo}`design spec, section 13 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#13-phases>`.

Gummel symmetry test
  A model benchmark: the model must be smooth through Vds = 0 ({ref}`McAndrew 2006 <lit-mcandrew>`). See {ref}`numerical-acceptance`.

depletion width
  The width of the region around a p-n junction that is emptied of free carriers. The
  {ref}`plugin-history record <plugin-history-results>` measures it on one mesh row, as the span
  of the nodes where both carrier densities are below 1e-2 |NetDoping|.

built-in potential
  The voltage that builds up across a p-n junction at equilibrium, with no bias applied. In
  detail: with {term}`Boltzmann statistics` and full ionisation it is
  V_bi = (k_B T / q) ln(N_A N_D / n_i²), the difference of the electrostatic potentials of the
  neutral n and p sides ({ref}`Sze and Ng 2006, ch. 2 <lit-sze>`). A forward bias V lowers the
  drop across the junction to V_bi − V. See {ref}`the junction probe <plugin-history-junction>`.

ideality factor
  How closely a diode follows the ideal exponential law. In detail: n in
  I = I0 (exp(V / (n V_t)) − 1), with V_t = k_B T / q. It is 1 for pure diffusion current
  ({ref}`Shockley 1949 <lit-shockley>`) and near 2 when recombination in the depletion region
  dominates ({ref}`Sah, Noyce and Shockley 1957 <lit-sah>`). See {ref}`plugin-history-latest-junction`.

depletion approximation
  The textbook model of a p-n junction: free carriers are absent inside the depletion region
  and the doping is exactly neutralised outside it. In detail: the space charge is
  ±q N up to the depletion edges, and Poisson's equation then gives the {term}`depletion widths <depletion width>` from
  the {term}`built-in potential` and the doping, x_d = √(2 ε V_bi N_A / (q N_D (N_A + N_D)))
  on the n side ({ref}`Sze and Ng 2006, ch. 2 <lit-sze>`). See {ref}`plugin-history-latest-pn`.

ohmic contact
  A metal-semiconductor contact that passes current in both directions with negligible
  resistance. In detail: a device simulator such as {{ DEVSIM }} models it by fixing the
  carrier densities at the contact to their equilibrium, charge-neutral values, so the contact
  Potential is the applied bias plus the equilibrium potential of the local doping,
  V_t asinh(N / 2 n_i) ({ref}`Sze and Ng 2006, ch. 3 <lit-sze>`). See {ref}`plugin-history-latest-pn`.

electron
  A negative charge carrier in silicon: an electron freed from the bond between two atoms,
  which moves through the crystal and carries current ({ref}`Sze and Ng 2006, ch. 1 <lit-sze>`). See {ref}`explained-carriers`.

hole
  A positive charge carrier in silicon: a bond that is missing its {term}`electron`. A
  neighbouring bonded electron can move into it, so the hole moves the other way and carries
  current ({ref}`Sze and Ng 2006, ch. 1 <lit-sze>`). See {ref}`explained-carriers`.

intrinsic carrier density
  The density of {term}`electrons <electron>`, equal to that of {term}`holes <hole>`, in pure
  silicon in thermal equilibrium: n_i. Heat frees each electron and its hole as a pair ({ref}`Sze and Ng 2006, ch. 1 <lit-sze>`). See
  {ref}`explained-carriers`.

dopant
  An atom of another element placed in the silicon crystal to set which charge carrier
  outnumbers the other: a {term}`donor` or an {term}`acceptor` ({ref}`Sze and Ng 2006, ch. 1 <lit-sze>`). See
  {ref}`explained-dopants`.

donor
  A {term}`dopant` with one more outer {term}`electron` than silicon. The spare electron is
  free to move, so donors make n-type silicon, where electrons are the {term}`majority carriers <majority carrier>`
  ({ref}`Sze and Ng 2006, ch. 1 <lit-sze>`). See {ref}`explained-dopants`.

acceptor
  A {term}`dopant` with one fewer outer {term}`electron` than silicon. It takes an electron
  from a bond and leaves a {term}`hole`, so acceptors make p-type silicon ({ref}`Sze and Ng 2006, ch. 1 <lit-sze>`). See
  {ref}`explained-dopants`.

majority carrier
  The charge carrier that outnumbers the other in doped silicon: the {term}`electron` in
  n-type silicon, the {term}`hole` in p-type. Its density equals the doping ({ref}`Sze and Ng 2006, ch. 1 <lit-sze>`). See
  {ref}`explained-how-many`.

minority carrier
  The charge carrier that is outnumbered in doped silicon. In thermal equilibrium its density is
  the {term}`intrinsic carrier density` squared divided by the doping, the mass-action law
  ({ref}`Sze and Ng 2006, ch. 1 <lit-sze>`). See {ref}`explained-how-many`.

Boltzmann statistics
  The non-degenerate approximation of carrier statistics. In detail: the Fermi-Dirac
  occupation is replaced by its Boltzmann tail, so n = n_i exp((ψ − φ_n) / V_t) and
  p = n_i exp((φ_p − ψ) / V_t). It holds while the Fermi level stays a few k_B T away from the
  band edges, and fails in degenerately doped regions ({ref}`Sze and Ng 2006, ch. 1 <lit-sze>`).
  See {ref}`the junction probe <plugin-history-junction>`.

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
