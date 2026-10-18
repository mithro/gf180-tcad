(process-data)=

# Process data for the MOS capacitors

The {term}`process description` of each device is one {term}`process file`:
{repo}`data/process/nfet_05v0.toml` and {repo}`data/process/pfet_05v0.toml`. Both are read by
{py:func}`gf180tcad.tcad.process.load`, which uses the {{ Python }} standard library's
[`tomllib`](https://docs.python.org/3/library/tomllib.html). Each parameter has a value, a unit
and a {term}`provenance tag`. It also has a public source: a line of the {term}`PDK`'s
{term}`model card` `sm141064.ngspice`, or a link. The card is the one in the pinned image, and its
sha256 is recorded in {repo}`docker/base/versions.json` and in each file's `[card]` table.

## Card values

The values come from the {term}`nfet_06v0` and {term}`pfet_06v0` cards (`.model nfet_06v0.0`
at card line 37055 and `.model pfet_06v0.0` at line 38091), the {term}`L bin` from 0.7 µm and
0.5 µm up to 50 µm. Several card entries are expressions in {term}`corner` parameters, such
as `toxe='1.52e-008+nfet_06v0_tox'`. They are evaluated with the `.param` values of the card's
`.lib typical` section ({term}`TT`, from line 105) by
{py:func}`gf180tcad.tcad.process.eval_card_expr`, and the source cites both lines.
{test}`tests/tcad/test_process.py::test_card_values_and_lines` re-reads every cited line from
the card in the image, checks that it lies inside the right `.model` block and checks the value.

| Parameter | nfet (card line) | pfet (card line) | Role |
|---|---|---|---|
| TOXE | 15.2 nm (37309) | 15.6 nm (38255) | start and lower bound of `t_ox_eff_nm` |
| TOXP | 16.0 nm (37311) | not set, so = TOXE | basis of the `t_ox_eff_nm` upper bound |
| NDEP | 1.7e17 cm⁻³ (37202) | 1.7e17 cm⁻³ (38198) | start of `n_ch_cm3` |
| K1 | 0.9 (37147) | 0.9588 (38162) | lower bound of `n_ch_cm3` |
| VTH0 | 0.67314 V (37337) | −0.8978 V (38274) | Δ only |
| VFB | not set (derived) | −1 V (38269) | Δ only |
| ACDE | 0.3 (37059) | 0.7 (38095) | Δ |
| MOIN | 15 (37201) | 15 (38197) | not used by Δ (see below) |
| NGATE | 1e20 cm⁻³ (37204) | 3.6e19 cm⁻³ (38200) | poly-gate doping, fixed |
| XJ | 0.15 µm (37377) | 0.15 µm (38291) | source/drain depth, 2D |
| EPSROX | 3.9 (37126) | 3.9 (38144) | ε_ox |
| TNOM | 25 °C (37308) | 25 °C (38254) | T = 298.15 K |
| DLC | 54 nm (37104) | 7.4 nm (38129) | 1D bookkeeping, fixed |
| CGSO = CGDO | 1e-10 F/m (37089, 37086) | 7.71e-11 F/m (38117, 38115) | 1D bookkeeping, fixed |
| CGSL = CGDL | 1.5e-10 F/m (37088, 37085) | 5.25e-11 F/m (38116, 38114) | 1D bookkeeping, fixed |
| CF | not set: 7.271e-11 F/m | not set: 7.216e-11 F/m | 1D bookkeeping, fixed |

CF is not on either card, so {term}`BSIM4` uses its default, 2·EPSROX·ε0/π·ln(1 + 4e-7/TOXE)
(BSIM4.5.0 manual eq. 7.5.1).

The nfet ACDE is on line 37059. Line 37397 has the same value, but it belongs to the next bin,
`.model nfet_06v0.1`.

The pfet card's NSD of 6e16 (line 38207) has no clear physical meaning and is not used.

**Reference-model bookkeeping.** DLC, CGSO, CGDO, CGSL, CGDL and CF describe how BSIM4 splits
the {term}`SPICE` {term}`Cgg` into an intrinsic part and extrinsic parts. They are not process data, so
they carry the role `reference-bookkeeping`. They are used only in the 1D comparison, where the
1D structure has no source or drain. In 2D, the source/drain geometry gives the overlap
physically. They are fixed and are not part of the {term}`parameter budget`.

## The three tunables

These are 3 of the 8 calibrated parameters per device type. They will be fitted, so they are
tagged `calibrated`, never `spice-card`. Instead of a `source`, each has a `start_source` and a
`bounds_source`. Their starts and bounds are written into the files before any fit.

| Name | Start (n / p) | Bounds, nfet | Bounds, pfet | Bound source |
|---|---|---|---|---|
| `t_ox_eff_nm` | TOXE: 15.2 / 15.6 | 15.2 … 16.95 | 15.6 … 16.39 | TOXE; TOXP + Δ (below) |
| `n_ch_cm3` | NDEP: 1.7e17 | 6.297e16 … 3.4e17 | 6.785e16 … 3.4e17 | 0.5 × the K1 doping; 2 × NDEP (project choice) |
| `dv_fb_v` | 0 (project choice) | −0.2 … +0.2 | −0.2 … +0.2 | project choice |

- **The `n_ch_cm3` lower bound** is half the doping that K1 implies, N = (K1·Cox(TOXE))²/(2·q·ε_si·ε0)
  ({py:func}`gf180tcad.tcad.process.k1_doping_cm3`), with the constants in
  {py:data}`gf180tcad.tcad.process.CONSTANTS`. The upper bound of 2 × NDEP is a project choice,
  because no public channel profile exists.
- **`dv_fb_v` is a lumped flat-band offset.** It is applied as a rigid gate-bias shift. It lumps
  together Boltzmann statistics in the degenerate gate, SPICE's empirical flat band, and
  interface and fixed charge. It is not a fixed-oxide-charge parameter.

## The charge-centroid allowance Δ

The upper bound of `t_ox_eff_nm` is TOXP + Δ. Δ allows for the charge centroid only: the
inversion or accumulation charge sits a distance X_DC below the interface. Poly depletion is
never part of Δ, because the poly-gate region of the {term}`TCAD` structure simulates it.

Δ comes from the BSIM4 charge-thickness model (CTM), which the cards select with `capMod=2`
(lines 37080 and 38109). The source is the BSIM4.5.0 user's manual, §7.3
([BSIM4.5.0 release](https://www.bsim.berkeley.edu/BSIM4/BSIM450.zip), `doc/BSIM450_Manu.tar`).
{py:func}`gf180tcad.tcad.process.centroid_allowance_nm` evaluates it at Vbs = 0 over the gate
biases of the SPICE {term}`cv` sweep (50 mV steps) that lie on the two plateaus which set the
effective oxide: accumulation, polarity·Vg ≤ −2 V, and strong inversion, polarity·Vg ≥ +2 V
({py:data}`gf180tcad.tcad.process.PLATEAU_V`, the ±2 V plateau convention of the calibration).
Each file records this window in its `[centroid_allowance]` table. Depletion is left out. There
the accumulation formula saturates near Ldebye/3, and the centroid says nothing about the
oxide-capacitance plateaus. Counting it would widen the fit's freedom for no physical reason.

- **Accumulation**, eqs. 7.3.2 and 7.3.3: X_DC = Ldebye/3·exp(ACDE·(NDEP/2e16)^−0.25·E),
  where E = (Vg − Vfbzb)/TOXP in MV/cm. It is smoothed to stay below Xmax = Ldebye/3, with
  δx = 10⁻³·TOXE. X_DC grows towards flat band, so its plateau maximum is at the window edge,
  polarity·Vg = −2 V.
- **Strong inversion**, eq. 7.3.4: X_DC = 1.9 nm/(1 + ((Vgsteff + 4(VTH0 − VFB − Φs))/(2·TOXP))^0.7).
  This falls as Vgsteff rises. The value at Vgsteff → 0 is used as an upper bound for the
  plateau, which avoids modelling Vgsteff. It is below the accumulation value for both devices.

- **MOIN** enters only φδ (eq. 7.3.5), not X_DC, so it does not affect Δ.
- **Inputs:** Φs comes from eq. 2.2.7, using the BSIM4 ni of eq. 12.7.3, and Vfbzb comes from
  eq. 7.2.14 (long channel). VFB is derived as in the manual's Appendix A when the card does not
  set it.

Δ = max X_DC · EPSROX/ε_si over the plateaus, rounded up to 0.01 nm. Two choices follow the reference C code of
the same release instead of the manual's text:
- Eq. 7.3.2 prints VFBeff in the exponent. `b4ld.c` uses Vfbzb, as here. VFBeff tracks Vgb in
  accumulation, so with it X_DC could not change with bias there.
- The manual gives no formula for Ldebye. `b4temp.c` uses √(ε_si·vt/(q·NDEP)), as here.

The gate bias is used in place of Vgse, so the poly-depletion drop is ignored. That only makes
Δ larger.

| | nfet | pfet |
|---|---|---|
| Ldebye/3 | 3.295 nm | 3.295 nm |
| Vfbzb | −0.965 V | −0.794 V (NMOS-equivalent sign) |
| X_DC, accumulation plateau edge (polarity·Vg = −2 V) | **2.845 nm** | **2.361 nm** |
| X_DC, accumulation end (polarity·Vg = −5 V) | 2.089 nm | 1.083 nm |
| X_DC, inversion supremum | 0.943 nm | 0.844 nm |
| Δ | **0.95 nm** | **0.79 nm** |
| `t_ox_eff_nm` upper bound | 16.0 + 0.95 = **16.95 nm** | 15.6 + 0.79 = **16.39 nm** |
| (not used) X_DC over the whole sweep, depletion end | 3.279 nm (Δ would be 1.10 nm) | 3.291 nm (Δ would be 1.10 nm) |

The pfet card is BSIM4 version 4.6 (line 38268), but its CTM equations are those of 4.5.0
(§7.3 of the 4.7 manual has the same form, with ADOS = BDOS = 1). The pfet's LPHIN = 0.1408
(line 38180) is left out, because only the unbinned card values are used. At L = 10 µm it would
raise the pfet Δ by 0.004 nm, which rounds up to 0.80 nm instead of 0.79 nm.

{test}`tests/tcad/test_process.py::test_centroid_allowance_hand_point` checks the nfet numbers
above against a hand evaluation. The 0.5 nm project-choice fallback
({py:data}`gf180tcad.tcad.process.FALLBACK_DELTA_NM`) is not needed, because the CTM equations
can be evaluated from the public manual and code.

The SPICE slopes imply that the oxide actually needed is about 16.2 nm for the nfet and
15.5–16.0 nm for the pfet. Both are inside these bounds. The pfet accumulation side may reach
the TOXE lower bound: that is a result to report, not a failure.

## No calibrated values in the files

The files hold only starts and bounds. {py:func}`gf180tcad.tcad.process.load` requires the
`calibrated` tag on exactly the tunables, each with a `start_source` and a `bounds_source`, and
rejects it on every fixed parameter. Calibration ({ref}`calibration-validation`) writes its values under
`results/tcad/calibration/`. {py:meth}`gf180tcad.tcad.process.ProcessDescription.with_values`
applies them to a loaded description: it refuses fixed parameters and values outside the
bounds.
