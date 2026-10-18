# Physical validation (future silicon)

There is **no measured data yet**, and no single-device `05v0` structure exists
on {{ wafer_space }} {term}`runs 1 and 2 <wafer.space run>` (design lists:
[run 1](https://github.com/wafer-space/ws-run1), [run 2](https://github.com/wafer-space/ws-run2)).
Since the `05v0` and `06v0` models are the same {term}`BSIM4` {term}`cards <model card>`, the
taped-out `06v0` devices are directly relevant. This page is the inventory. For each structure
the repository will carry pre-computed {term}`TCAD` and {term}`SPICE` predictions at the exact
drawn geometry, so measured data can be dropped in later. The narrow 1.6/0.7 geometry of the
priority-1 devices is part of the {ref}`comparison space <comparison-space>`.

| Priority | Design (run) | Structures | Notes |
|---|---|---|---|
| 1 | [TRID](https://github.com/Scafir/gf180mcu-project-trident-gf180-teststructure) ({term}`ws-run1`), [CERN-OHL-W](https://spdx.org/licenses/CERN-OHL-W-2.0.html) | single {term}`nfet_06v0` and {term}`pfet_06v0`, W = 1.6, L = 0.7, with their own G/D/S pads (bulk to rail); MIM equal-area/different-perimeter pair; 6 V diodes; charge-pumping pair | The datasheet says W = 0.75; the PCell and silicon say 1.6. |
| 2 | 0000 / [ASHES](https://github.com/GTIceLab/ASHES-GF180nm) ({term}`ws-run2`) | 2/1 µm `06v0` n and p FETs (×5 each), `03v3` FETs | **No licence**: reference only, do not redistribute; pad map undocumented. |
| 3 | T0P3 (ws-run2, [Tiny Tapeout GF0.3](https://github.com/TinyTapeout/tinytapeout-gf-0p3)) | `tt_asw_5v0` analog switches (`05v0`, Ron versus V), 5 V mirror with Kelvin sense | Indirect `05v0` check. |
| 4 | [CAB1](https://github.com/ZeduloTech/Cabrera) / [CLON](https://github.com/ThorbenMoos/Cloneless2) / [DCO0](https://github.com/asinghani/ws-dco-tdc) (ws-run2) / [2975](https://github.com/ThorbenMoos/Cloneless1) (ws-run1) | ring oscillators from 5 V 7-track cells (`05v0` inverter 0.82/0.60 n, 1.22/0.50 p) | Frequency versus SPICE/SDF: a circuit-level check. |
| 5 | ISHI (runs [1](https://github.com/ishi-kai/ISHI-KAI_Multiple_Projects_WaferSapce-GF180-1) and [2](https://github.com/ishi-kai/ISHI-KAI_Multiple_Projects_WaferSapce-GF180-2)) | probe-padded inverters (`05v0` and `06v0`) | Verify that {term}`Dualgate` is over each device: some "5 V" devices were built thin-oxide. |
