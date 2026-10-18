# Physical validation (future silicon)

There is **no measured data yet**, and no single-device `05v0` structure exists
on wafer.space runs 1 and 2. Since the `05v0` and `06v0` models are the same
BSIM4 cards, the taped-out `06v0` devices are directly relevant. This page is
the inventory. For each structure the repository will carry pre-computed TCAD
and SPICE predictions at the exact drawn geometry, so measured data can be
dropped in later.

| Priority | Design (run) | Structures | Notes |
|---|---|---|---|
| 1 | TRID (ws-run1), CERN-OHL-W | single `nfet_06v0` and `pfet_06v0`, W = 1.6, L = 0.7, with their own G/D/S pads (bulk to rail); MIM equal-area/different-perimeter pair; 6 V diodes; charge-pumping pair | The datasheet says W = 0.75; the PCell and silicon say 1.6. Possible data behind CERN SSO. |
| 2 | 0000 / ASHES (ws-run2) | 2/1 µm `06v0` n and p FETs (×5 each), `03v3` FETs | **No licence**: reference only, do not redistribute; pad map undocumented. |
| 3 | T0P3 (ws-run2, TT GF0.3) | `tt_asw_5v0` analog switches (`05v0`, Ron versus V), 5 V mirror with Kelvin sense | Indirect `05v0` check. |
| 4 | CAB1 / CLON / DCO0 / 2975 | ring oscillators from 5 V 7-track cells (`05v0` inverter 0.82/0.60 n, 1.22/0.50 p) | Frequency versus SPICE/SDF: a circuit-level check. |
| 5 | ISHI (runs 1 and 2) | probe-padded inverters (`05v0` and `06v0`) | Verify that Dualgate is over each device: some "5 V" devices were built thin-oxide. |
