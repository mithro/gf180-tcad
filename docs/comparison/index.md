# Comparison with the PDK

What "agrees with the {term}`PDK`" means here, and how mismatches are explained.

No {term}`TCAD` summary matrix yet (device × metric → {term}`Agree` / {term}`Same process` /
{term}`Disagree`); it will appear here. The first TCAD comparison is the {term}`C–V` calibration of the
1D {term}`MOS capacitor` and its validation ({doc}`cv-agreement`). What exists besides is the
{term}`SPICE` reference checked against the PDK spec ({doc}`pdk-spec-check`) and
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
