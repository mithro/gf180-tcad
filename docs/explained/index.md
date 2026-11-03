(explained)=

# How it works

## The basics

- {doc}`Silicon, doping and carriers <silicon-and-carriers>`: what {term}`electrons <electron>`,
  {term}`holes <hole>` and {term}`dopants <dopant>` are, with this process's numbers.
- {doc}`Energy bands and the Fermi level <bands-and-fermi-level>`: how a band diagram shows
  where the carriers are, with the {term}`Fermi level` of this process's gate and body.
- {doc}`The pn junction and its depletion region <pn-junction>`: why a layer without free
  carriers forms where the source meets the body, with this process's dopings.
- {doc}`The parts of a transistor <transistor-parts>`: the gate, the source, the drain, the body
  and the contacts of the simulated cell, beside the {term}`PDK`'s drawing.
- {doc}`Gate oxide and poly-silicon <oxide-and-poly>`: what the {term}`gate oxide` and the
  {term}`poly-silicon` gate are, and how their thickness and doping set the {term}`oxide capacitance <Cox>`.

## The MOS capacitor

- {doc}`The MOS capacitor <mos-capacitor>`: the transistor without its source and drain, and
  why this project fits it to the {term}`SPICE` model first.
- {doc}`Accumulation, depletion and inversion <accumulation-depletion-inversion>`: what gathers
  under the gate as its voltage changes, and the bands of each region.
- {doc}`What sets each part of the C–V curve <cv-curve>`: which of the oxide thickness, the
  body doping and a voltage shift moves each part, and how the fit uses them.
- {doc}`What the calibration changes <calibration>`: the three fitted numbers within their
  limits, what stays fixed and what the {term}`corners <corner>` add.

```{toctree}
:hidden:

silicon-and-carriers
bands-and-fermi-level
pn-junction
transistor-parts
oxide-and-poly
mos-capacitor
accumulation-depletion-inversion
cv-curve
calibration
```
