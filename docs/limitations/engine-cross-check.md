# SPICE engine cross-check (ngspice vs Xyce)

The SPICE reference is computed with ngspice and cross-checked with Xyce on
the same PDK model cards, bias grid and instance parameters. The spec says a
difference of more than 0.5 % between the two engines flags a problem with the
reference itself. The check is `test_engines_agree` in `tests/spice/test_xyce.py`.
It covers every geometry of `nfet_05v0` and `pfet_05v0`, for `idvg_sat` and
`idvd`, at the typical corner and 25 °C. The metric is the maximum of
|Id,ngspice − Id,Xyce| / max(|Id,ngspice|, |Id,Xyce|), taken over the bias
points where either engine gives |Id| > 1 pA.

The threshold is not loosened. **Six of the 24 cases fail:** `idvg_sat` for
all six `nfet_05v0` geometries, by 0.56 to 0.61 %. They are marked as strict
expected failures that point to this page, so a fix would show up as an
unexpected pass.

## Cause: different BSIM4 code versions for the nfet card

The nfet model card (`nfet_06v0`, used by `nfet_05v0`) declares
`version=4.5`. The pfet card (`pfet_06v0`) declares `version=4.6` in the
ngspice library and no version in the Xyce library.

- **ngspice 47** chooses its BSIM4 implementation from `version`.
  `showmod m.xdut.m0` in the image reports `BSIM4v5 models` (version 4.5) for
  the nfet and `BSIM4v6 models` for the pfet.
- **Xyce 7.10** has no BSIM4 older than 4.6.1. Its log says: "Device model
  NFET_06V0.1: Model card specifies BSIM4 version 4.5 which is older than the
  oldest version supported in Xyce (4.6.1). Using oldest version available."

The pfet therefore runs comparable code in both engines. The nfet runs
BSIM4 4.5.0 in ngspice and BSIM4 4.6.1 in Xyce.

### Evidence

nfet W = 10 µm, L = 0.6 µm, typical corner, Vbs = 0:

| Gate voltage at Id | ngspice (4.5) | Xyce | Shift |
|---|---|---|---|
| 1 nA (Vds = 5 V) | 0.281972 V | 0.281743 V | −0.229 mV |
| 100 nA (Vds = 5 V) | 0.463006 V | 0.462770 V | −0.237 mV |
| 1 µA (Vds = 5 V) | 0.558662 V | 0.558408 V | −0.254 mV |

In subthreshold, Xyce's current is a nearly constant 0.59 % higher. That is
a gate-voltage shift of about 0.23 mV, and its effect fades in strong
inversion (7e-5 at Vgs = 5 V).

These model-card changes were tried as a bisection. Each was applied
identically to scratch copies of both libraries.

- **Xyce `version` set to 4.6.1, 4.7, 4.8 (4.8.2) or removed:** no change in
  Xyce's result (engine_diff stays 5.6191e-3 for `idvg_lin`).
- **`toxp = toxe`, no `ngate`, `dvt2 = 0`, no `vbm`, all `jts*` = 0, no
  `lp`/`up`/`eu`, `w0 = 0`, `lint = ll = 0`, `k3 = 0`, `etab = 0`, no
  `dsub`, `dvt0 = 0`, `nfactor = 1`:** engine_diff stays 5.57e-3 to 5.62e-3.
  `lpe0 = 0` makes it larger (3.1e-2).
- **ngspice `version` set to 4.6, 4.7 or 4.8** (all three give identical
  results): the difference goes away.

  | Sweep | ngspice 4.5 (PDK as published) | ngspice 4.6 |
  |---|---|---|
  | `idvg_lin` | 5.62e-3 | 1.47e-4 |
  | `idvg_sat` | 6.05e-3 | 3.64e-3 |
  | `idvd` | 3.27e-3 | 1.03e-7 |

  At Vds = 5 V the remaining 3.6e-3 is at the ~6 pA off-state leakage floor,
  Vgs = 0.01 V. The subthreshold gate-voltage shift becomes 0.000 mV.

With ngspice forced to 4.6, every nfet geometry agrees: `idvg_sat` 2.7e-4 to
3.6e-3, `idvd` 1.0e-7 to 1.4e-7.

### Regression test

The sandbox test `test_engines_agree_with_ngspice_forced_to_bsim4_4p6` in
`tests/spice/test_xyce.py` guards this explanation against regressions. It
runs each of the six expected-failure cases on a patched scratch copy of the
image's ngspice library. The copy is written inside the sandbox, so the
repository stays read-only. It differs from the PDK library in two ways:

- The nfet card's `version=4.5` becomes `4.6`.
- The library's nested `.lib 'sm141064.spice'` lines point at the copy
  itself.

The test passes the copy to the runner as an explicit input in a
subdirectory of the working directory. It asserts three things:

- Stock ngspice against Xyce exceeds 0.005, which is the expected failure.
- Stock against patched ngspice exceeds 0.005, so the patch took effect.
- Patched ngspice against Xyce stays below 0.005.

| Geometry | Stock ngspice vs Xyce | ngspice at 4.6 vs Xyce |
|---|---|---|
| W10/L0.6 | 6.05e-3 | 3.64e-3 |
| W10/L0.7 | 5.80e-3 | 1.93e-3 |
| W10/L1 | 5.71e-3 | 1.87e-3 |
| W10/L2 | 5.61e-3 | 1.85e-3 |
| W10/L10 | 5.59e-3 | 2.28e-3 |
| W1.6/L0.7 | 5.76e-3 | 2.73e-4 |

## Consequence for the reference

The reference stays ngspice with the PDK as published, including the
declared `version=4.5`. That is the model the foundry card specifies, and
ngspice is the only engine in the image that can run it. Xyce cannot reproduce
it, because it has no BSIM4 4.5.

The nfet version effect is small next to the TCAD-vs-SPICE comparison, but it
is a real ambiguity. The same card gives a ~0.23 mV threshold-voltage
difference and a 0.6 % subthreshold current difference depending on which
BSIM4 release evaluates it. The other cross-check cases all pass:

- `idvd`, nfet: below 0.37 %.
- `idvd`, pfet: below 1e-6.
- `idvg_sat`, pfet: below 0.23 %, at pA leakage levels.

## Other differences between the two libraries (checked, harmless here)

- **Missing 5 V wrappers.** The image's Xyce library has no `nfet_05v0` /
  `pfet_05v0` wrappers. In the ngspice library those wrappers are line for line
  the `nfet_06v0` / `pfet_06v0` wrappers, except for the defaults of `w` and
  `l`, which every netlist overrides. So the Xyce netlist instantiates
  `nfet_06v0` / `pfet_06v0`.
- **Parameters the Xyce wrappers do not pass to the transistor:** `nf`, `sa`,
  `sb`, `sd` and `mulu0`. With nf = 1, sa = sb = sd = 0 and statistics off,
  these are the BSIM4 defaults.
- **Model cards.** The cards are otherwise identical, apart from three
  differences:
  - `rgeomod=0` (the default) is missing from the Xyce nfet cards.
  - The pfet `version` differs, as described above.
  - The `*_dss` subcircuits use different junction diode levels. They are not
    used here.
- **Temperature.** Xyce ignores `.temp` and would run at 27 °C. The Xyce
  netlist therefore sets `.options device temp=25.0`. A netlist line that
  Xyce does not recognise fails the run.

## Working-directory guard

The PDK libraries pull in their sections through relative
`.lib 'sm141064.spice' <section>` lines. While the scratch libraries above
were being patched, ngspice resolved those lines to a copy other than the one
next to the top-level library. A stray `sm141064.spice` in a simulator's
working directory could therefore replace the PDK models without any warning.

Both runners therefore refuse to start in a working directory that holds
anything other than their own files: the netlist, the log and the data file,
which are replaced on each run. The only other entries allowed are ones the
caller names explicitly as inputs. Foreign files are never deleted, and a run
in which the simulator writes any other file fails. Both runners also kill
the simulator after 600 s.
