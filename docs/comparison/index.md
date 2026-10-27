# Comparison with the PDK

What "agrees with the {term}`PDK`" means here, and how mismatches are explained.

The first {term}`TCAD` comparison is the {term}`C–V` calibration of the 1D
{term}`MOS capacitor` and its validation ({doc}`cv-agreement`). Its summary matrix, device ×
geometry → {term}`Agree` / {term}`Same process` / {term}`Disagree` in 1D, is generated from the
committed results on {doc}`/_generated/tcad/index`, with one page per device and geometry. There
is no matrix for the full transistor (MOSFET) yet. What exists besides is the
{term}`SPICE reference <SPICE reference results>` checked against the PDK spec ({doc}`pdk-spec-check`) and
{{ ngspice }} checked against {{ Xyce }} ({doc}`../limitations/engine-cross-check`); both are
summarised, with the current numbers, on the generated
{doc}`SPICE reference results </_generated/results/index>` page.

```{toctree}
:maxdepth: 1

agreement
cv-agreement
pdk-spec-check
pdk-versions
process-data
```
