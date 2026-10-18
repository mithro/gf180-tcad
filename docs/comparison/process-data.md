(process-data)=

# Process data for the MOS capacitors

The {term}`process description` of each device is one {term}`process file`:
{repo}`data/process/nfet_05v0.toml` and {repo}`data/process/pfet_05v0.toml`. Both are read by
{py:func}`gf180tcad.tcad.process.load`, which uses the {{ Python }} standard library's
[`tomllib`](https://docs.python.org/3/library/tomllib.html). Each parameter has a value, a unit
and a {term}`provenance tag`. Each fixed parameter also has a public source: a line of the
{term}`PDK`'s {term}`model card`, or a link. A `spice-card` value without a card line, such as
CF, names the parameters it is `derived_from`.

The card is `sm141064.ngspice` in the pinned base image ({repo}`docker/IMAGE`, which the {term}`TCAD`
image {repo}`docker/TCAD_IMAGE` is built on). Its sha256 is recorded in
{repo}`docker/base/versions.json` and in each file's `[card]` table. {{ open_pdks }} installs
it from
[`models/ngspice/sm141064.spice`](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice)
of the {{ gf180mcu_models }} at the pinned commit. The two files are byte-identical: both have
sha256 `69a7ab877344a6d477fdd11440457f64e7ad88a624504a737a161da463de8bc8`. So the line numbers
below link into that file.

## Card values

The values come from the {term}`nfet_06v0` and {term}`pfet_06v0` cards: `.model nfet_06v0.0`
at card line [37055](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37055) and `.model pfet_06v0.0` at line [38091](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38091). These
are the {term}`L bin` from 0.7 µm (nfet) and 0.5 µm (pfet) up to 50 µm. Several card entries are
expressions in {term}`corner` parameters, such as `toxe='1.52e-008+nfet_06v0_tox'`. They are
evaluated with the `.param` values of the card's `.lib typical` section ({term}`TT`, from line
[105](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L105)) by {py:func}`gf180tcad.tcad.process.eval_card_expr`, and the source cites both
lines. {test}`tests/tcad/test_process.py::test_card_values_and_lines` re-reads every cited line
from the card in the image. It checks that each line lies inside the right `.model` block, and
that the value is right. The `crosscheck` workflow runs it ({repo}`.github/workflows/crosscheck.yml`).

| Parameter | nfet (card line) | pfet (card line) | Role |
|---|---|---|---|
| TOXE | 15.2 nm ([37309](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37309)) | 15.6 nm ([38255](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38255)) | start and lower bound of `t_ox_eff_nm` |
| TOXP | 16.0 nm ([37311](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37311)) | not set, so = TOXE | basis of the `t_ox_eff_nm` upper bound |
| NDEP | 1.7e17 cm⁻³ ([37202](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37202)) | 1.7e17 cm⁻³ ([38198](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38198)) | start of `n_ch_cm3` |
| K1 | 0.9 ([37147](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37147)) | 0.9588 ([38162](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38162)) | lower bound of `n_ch_cm3` |
| K2 | −0.001 ([37148](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37148)) | 8.936e-3 ([38163](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38163)) | why that bound has a 0.5 margin |
| VTH0 | 0.67314 V ([37337](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37337)) | −0.8978 V ([38274](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38274)) | Δ only |
| VFB | not set (derived) | −1 V ([38269](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38269)) | Δ only |
| PHIN | 0 ([37234](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37234)) | 0 ([38227](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38227)) | Δ only |
| ACDE | 0.3 ([37059](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37059)) | 0.7 ([38095](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38095)) | Δ |
| MOIN | 15 ([37201](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37201)) | 15 ([38197](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38197)) | not used by Δ (see below) |
| capMod | 2 ([37080](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37080)) | 2 ([38109](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38109)) | selects the CTM |
| NGATE | 1e20 cm⁻³ ([37204](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37204)) | 3.6e19 cm⁻³ ([38200](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38200)) | poly-gate doping, fixed |
| XJ | 0.15 µm ([37377](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37377)) | 0.15 µm ([38291](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38291)) | source/drain depth, 2D |
| EPSROX | 3.9 ([37126](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37126)) | 3.9 ([38144](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38144)) | ε_ox |
| TNOM | 25 °C ([37308](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37308)) | 25 °C ([38254](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38254)) | T = 298.15 K |
| DLC | 54 nm ([37104](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37104)) | 7.4 nm ([38129](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38129)) | 1D bookkeeping, fixed |
| CGSO = CGDO | 1e-10 F/m ([37089](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37089), [37086](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37086)) | 7.71e-11 F/m ([38117](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38117), [38115](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38115)) | 1D bookkeeping, fixed |
| CGSL = CGDL | 1.5e-10 F/m ([37088](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37088), [37085](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37085)) | 5.25e-11 F/m ([38116](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38116), [38114](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38114)) | 1D bookkeeping, fixed |
| CF | not set: 7.271e-11 F/m (derived) | not set: 7.216e-11 F/m (derived) | 1D bookkeeping, fixed |
| CKAPPAS = CKAPPAD | 0.6 V ([37099](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37099), [37098](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37098)) | 0.6 V ([38126](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38126), [38125](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38125)) | 1D bookkeeping, fixed |
| CGBO | 1e-13 F/m ([37084](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37084)) | 1e-13 F/m ([38113](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38113)) | 1D bookkeeping, fixed |
| DWC | 0 ([37120](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37120)) | not set, so = WINT 49 nm ([38278](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38278)) | 1D bookkeeping, fixed |
| XL, XW | 0 ([37380](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37380), [37392](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37392)) | 0 ([38294](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38294), [38299](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38299)) | 1D bookkeeping, fixed |

CF is not on either card, so {term}`BSIM4` uses its default, 2·EPSROX·ε0/π·ln(1 + 4e-7/TOXE)
([BSIM4.5.0 manual](https://www.bsim.berkeley.edu/BSIM4/BSIM450.zip), `doc/BSIM450_Manu.tar`, eq. 7.5.1).

The nfet ACDE is on line [37059](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37059). Line [37397](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37397) has the same value, but it
belongs to the next bin, `.model nfet_06v0.1`.

The pfet card's NSD of 6e16 (line [38207](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38207)) has no clear physical meaning and is not
used.

**Reference-model bookkeeping.** DLC, DWC, XL, XW, CGSO, CGDO, CGSL, CGDL, CKAPPAS, CKAPPAD,
CGBO and CF describe how BSIM4 splits the {term}`SPICE` {term}`Cgg` into an intrinsic part and
extrinsic parts: the intrinsic part scales with the capacitance area (L + XL − 2·DLC)·(W + XW −
2·DWC), and the overlap, fringe and gate-bulk parts are added to it
({py:func}`gf180tcad.tcad.moscap1d.parasitic_ff`). The pfet card sets no DWC, so its DWC is
the {term}`BSIM4` default, WINT. They are not process
data, so they carry the role `reference-bookkeeping`. They are used only in the 1D comparison,
where the 1D structure has no source or drain. In 2D, the source/drain geometry gives the overlap
physically. They are fixed and are not part of the {term}`parameter budget`.

## The three tunables

These are 3 of the 8 calibrated parameters per device type. They will be fitted, so they are
tagged `calibrated`, never `spice-card`. Instead of a `source`, each has a `start_source` and a
`bounds_source`, and a structured `start_kind` and `bounds_kind` (one kind per bound). A kind is
`card`, `derived` or `project-choice`
({py:data}`gf180tcad.tcad.process.KINDS`). Their starts and bounds are written into the files
before any fit.

| Name | Start (n / p) | Bounds, nfet | Bounds, pfet | Kinds (start; lower, upper) |
|---|---|---|---|---|
| `t_ox_eff_nm` | TOXE: 15.2 / 15.6 | 15.2 … 16.95 | 15.6 … 16.39 | card; card, derived (TOXP + Δ, below) |
| `n_ch_cm3` | NDEP: 1.7e17 | 6.297e16 … 3.4e17 | 6.785e16 … 3.4e17 | card; project choice, project choice |
| `dv_fb_v` | 0 | −0.2 … +0.2 | −0.2 … +0.2 | project choice; project choice, project choice |

- **The `n_ch_cm3` lower bound** is 0.5 × the doping that K1 implies,
  N = (K1·Cox(TOXE))²/(2·q·ε_si·ε0) ({py:func}`gf180tcad.tcad.process.k1_doping_cm3`), with the
  constants in {py:data}`gf180tcad.tcad.process.CONSTANTS`. **The factor 0.5 is a project
  choice.** It is a margin, because K1 equals the body factor γ₁ = √(2·q·ε_si·N)/Cox only when
  K2 = 0, and both cards have K2 ≠ 0.
- **The `n_ch_cm3` upper bound** of 2 × NDEP is a project choice, because no public channel
  profile exists.
- **`dv_fb_v` is a lumped flat-band offset.** Its start of 0 and its ±0.2 V bounds are project
  choices. It is applied as a rigid gate-bias shift. It lumps together {term}`Boltzmann statistics` in
  the degenerate gate, SPICE's empirical flat band, and interface and fixed charge. It is not a
  fixed-oxide-charge parameter.

## The charge-centroid allowance Δ

The upper bound of `t_ox_eff_nm` is TOXP + Δ, and {py:func}`gf180tcad.tcad.process.load`
checks that equality against the file's `[centroid_allowance]` table. Δ allows for the charge
centroid only: the inversion or accumulation charge sits a distance X_DC below the interface.
Poly depletion is never part of Δ, because the poly-gate region of the {term}`TCAD` structure
simulates it.

Δ comes from the BSIM4 charge-thickness model (CTM), which the cards select with `capMod=2`.
The source is the BSIM4.5.0 user's manual, §7.3
([BSIM4.5.0 release](https://www.bsim.berkeley.edu/BSIM4/BSIM450.zip), `doc/BSIM450_Manu.tar`).
{py:func}`gf180tcad.tcad.process.centroid_allowance_nm` evaluates it at Vbs = 0, using the gate
biases of the SPICE {term}`cv` sweep (50 mV steps) that lie on the two plateaus which set the
effective oxide:
- accumulation, polarity·Vg ≤ −2 V;
- strong inversion, polarity·Vg ≥ +2 V.

This window is {py:data}`gf180tcad.tcad.process.PLATEAU_V`, the ±2 V plateau convention of the
calibration, and each file records it in its `[centroid_allowance]` table. Depletion is left out.
There the accumulation formula saturates near Ldebye/3, and the centroid says nothing about the
oxide-capacitance plateaus. Counting it would widen the fit's freedom for no physical reason.

- **Accumulation**, eqs. 7.3.2 and 7.3.3: X_DC = Ldebye/3·exp(ACDE·(NDEP/2e16)^−0.25·E),
  where E = (Vg − Vfbzb)/TOXP in MV/cm. It is smoothed to stay below Xmax = Ldebye/3. X_DC grows
  towards flat band, so its plateau maximum is at the window edge, polarity·Vg = −2 V.
- **Strong inversion**, eq. 7.3.4: X_DC = 1.9 nm/(1 + ((Vgsteff + 4(VTH0 − VFB − Φs))/(2·TOXP))^0.7).
  This falls as Vgsteff rises. The value at Vgsteff → 0 is used as an upper bound for the
  plateau, which avoids modelling Vgsteff. It is below the accumulation value for both devices.
- **MOIN** enters only φδ (eq. 7.3.5), not X_DC, so it does not affect Δ.
- **Inputs:** Φs comes from eq. 2.2.7, using the BSIM4 ni of eq. 12.7.3, and Vfbzb comes from
  eq. 7.2.14. VFB is derived as in the manual's Appendix A when the card does not set it.

Δ = max X_DC · EPSROX/ε_si over the plateaus, rounded up to 0.01 nm. In three places the manual's
text and the reference C code of the same release ([`src/b4ld.c` and `src/b4temp.c` in the
BSIM4.5.0 release](https://www.bsim.berkeley.edu/BSIM4/BSIM450.zip), the code {{ ngspice }} runs) differ. Each is settled by the code:
- Eq. 7.3.2 prints VFBeff in the exponent; `b4ld.c` uses Vfbzb. VFBeff tracks Vgb in
  accumulation, so with it X_DC could not change with bias there.
- The manual gives no formula for Ldebye; `b4temp.c` uses √(ε_si·vt/(q·NDEP)).
- The manual gives δx = 10⁻³·TOXE; `b4ld.c` uses LINK = 10⁻³·TOXP. They differ for the nfet:
  with the manual's δx its X_DC would be 2.845 nm instead of 2.841 nm. Δ is 0.95 nm either way.

The gate bias is used in place of Vgse, so the poly-depletion drop is ignored. That only makes
Δ larger.

| | nfet | pfet |
|---|---|---|
| Ldebye/3 | 3.295 nm | 3.295 nm |
| Vfbzb | −0.965 V | −0.794 V (NMOS-equivalent sign) |
| X_DC, accumulation plateau edge (polarity·Vg = −2 V) | **2.841 nm** | **2.361 nm** |
| X_DC, accumulation end (polarity·Vg = −5 V) | 2.088 nm | 1.083 nm |
| X_DC, inversion supremum | 0.943 nm | 0.844 nm |
| Δ | **0.95 nm** | **0.79 nm** |
| `t_ox_eff_nm` upper bound | 16.0 + 0.95 = **16.95 nm** | 15.6 + 0.79 = **16.39 nm** |
| (not used) X_DC over the whole sweep, depletion end | 3.278 nm (Δ would be 1.10 nm) | 3.291 nm (Δ would be 1.10 nm) |

The pfet card is BSIM4 version 4.6 (line [38268](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38268)). Its CTM equations are those of
4.5.0. §7.3 of the BSIM4.6.0 manual, and the X_DC code of its `b4ld.c`, have the same form
([BSIM4.6.0 release](https://www.bsim.berkeley.edu/BSIM4/BSIM460.zip)).

**Unbinned, long-channel values.** Δ uses the unbinned card values: those with no L, W or P
term, evaluated at Vbs = 0, with the short-channel terms of Vfbzb dropped. The terms left out are:
- LPHIN, on the pfet only (0.1408, line [38180](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38180));
- LPE0, the lateral non-uniform doping term ([37182](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37182) and [38178](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38178));
- K3, the narrow-width term ([37150](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37150) and [38164](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38164)), with W = 10 µm;
- the DVT short-channel terms.

Here is the rough effect of each on Δ, estimated through Vfbzb (and Φs for LPHIN):

| Term | L = 10 µm | L = 2 µm | L = {term}`Lmin` |
|---|---|---|---|
| pfet LPHIN | +0.004 nm | +0.021 nm | +0.086 nm (L = 0.5 µm) |
| pfet LPE0 | +0.0004 nm | +0.002 nm | +0.008 nm (L = 0.5 µm) |
| nfet LPE0 | −0.0006 nm | −0.003 nm | −0.009 nm (L = 0.6 µm) |
| K3 (both) | ≤ 0.0002 nm | ≤ 0.0002 nm | ≤ 0.0002 nm |

With LPHIN the pfet Δ would round up to 0.80 nm at L = 10 µm and to about 0.88 nm at Lmin. The
nfet Lmin of 0.6 µm lies in the other bin, `nfet_06v0.1`, which these files do not use. Δ is one
bound per device for the long-channel 1D calibration, so the unbinned values are used.

{test}`tests/tcad/test_process.py::test_centroid_allowance_hand_point` checks the nfet numbers
above against a hand evaluation. The 0.5 nm project-choice fallback
({py:data}`gf180tcad.tcad.process.FALLBACK_DELTA_NM`) is not needed, because the CTM equations
can be evaluated from the public manual and code.

The SPICE slopes imply that the oxide actually needed is about 16.2 nm for the nfet, inside its
bounds of 15.2–16.95 nm. For the pfet they imply 15.5–16.0 nm. That range starts below the pfet's
TOXE lower bound of 15.6 nm, so the pfet fit, on its accumulation side, may stop at that bound.
That is a result to report, not a failure.

## No calibrated values in the files

The files hold only starts and bounds. {py:func}`gf180tcad.tcad.process.load` requires the
`calibrated` tag on exactly the tunables, each with its start and bounds sources and kinds, and
rejects it on every fixed parameter. The calibration (Task 12) will write the fitted values to
its own result files under `results/tcad/`, not to these files.
{py:meth}`gf180tcad.tcad.process.ProcessDescription.with_values` applies such values to a loaded
description. It refuses fixed parameters, non-numbers and values outside the bounds.
