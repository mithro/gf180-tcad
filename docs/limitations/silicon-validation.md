# Physical validation (future silicon)

There is **no measured data yet**, and no single-device `05v0` structure exists
on {{ wafer_space }} {term}`runs 1 and 2 <wafer.space run>` (design lists:
[run 1](https://github.com/wafer-space/ws-run1), [run 2](https://github.com/wafer-space/ws-run2)).
Since the `05v0` and `06v0` models are the same {term}`BSIM4` {term}`cards <model card>`, the
taped-out `06v0` devices are directly relevant. This page is the inventory. For each structure
the repository will carry pre-computed {term}`TCAD` and {term}`SPICE` predictions at the exact
drawn geometry, so measured data can be dropped in later. The narrow 1.6/0.7 geometry of the
priority-1 devices is part of the {ref}`comparison space <comparison-space>`.

| Priority | Design | Run | Licence |
|---|---|---|---|
| 1 | [TRID](https://github.com/Scafir/gf180mcu-project-trident-gf180-teststructure) | {term}`ws-run1` | [CERN-OHL-W](https://spdx.org/licenses/CERN-OHL-W-2.0.html) |
| 2 | 0000 / [ASHES](https://github.com/GTIceLab/ASHES-GF180nm) | {term}`ws-run2` | **none** |
| 3 | [T0P3](https://github.com/TinyTapeout/tinytapeout-gf-0p3) | ws-run2 | not recorded |
| 4 | [CAB1](https://github.com/ZeduloTech/Cabrera), [CLON](https://github.com/ThorbenMoos/Cloneless2), [DCO0](https://github.com/asinghani/ws-dco-tdc) | ws-run2 | not recorded |
| 4 | [2975](https://github.com/ThorbenMoos/Cloneless1) | ws-run1 | not recorded |
| 5 | ISHI ([run 1](https://github.com/ishi-kai/ISHI-KAI_Multiple_Projects_WaferSapce-GF180-1)) | ws-run1 | not recorded |
| 5 | ISHI ([run 2](https://github.com/ishi-kai/ISHI-KAI_Multiple_Projects_WaferSapce-GF180-2)) | ws-run2 | not recorded |

The structures of each design, and what to note about them:

- **Priority 1, TRID.** Single {term}`nfet_06v0` and {term}`pfet_06v0` devices, W = 1.6 µm,
  L = 0.7 µm. Each has its own gate, drain and source pads (bulk to the rail). TRID also holds
  a pair of metal-insulator-metal (MIM) capacitors of equal area and different perimeter, 6 V
  diodes and a charge-pumping pair. The datasheet says W = 0.75 µm; the layout cell (PCell) and
  the silicon say 1.6 µm.
- **Priority 2, 0000 / ASHES.** `06v0` n and p FETs of W = 2 µm, L = 1 µm (five of each).
  ASHES also holds `03v3` FETs. **No licence**: reference only, do not redistribute. The pad
  map is not documented.
- **Priority 3, T0P3 (Tiny Tapeout GF0.3).** `tt_asw_5v0` analog switches (`05v0`,
  on-resistance versus voltage) and a 5 V current mirror with Kelvin sense. An indirect `05v0`
  check.
- **Priority 4, CAB1, CLON, DCO0 and 2975.** Ring oscillators from 5 V 7-track cells. The
  `05v0` inverter is W = 0.82 µm, L = 0.60 µm (n) and W = 1.22 µm, L = 0.50 µm (p). Their
  frequency is compared with SPICE and with the Standard Delay Format (SDF) timing: a
  circuit-level check.
- **Priority 5, ISHI.** Probe-padded inverters (`05v0` and `06v0`). Check that
  {term}`Dualgate` is over each device: some "5 V" devices are built thin-oxide.
