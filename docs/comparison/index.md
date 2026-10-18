# Comparison with the PDK

What "agrees with the {term}`PDK`" means here, and how mismatches are explained.

No {term}`TCAD` matrix yet: TCAD has not run. The summary matrix (device × metric →
{term}`Agree` / {term}`Same process` / {term}`Disagree`) will appear here. What exists now is
the {term}`SPICE` reference checked against the PDK spec ({doc}`pdk-spec-check`) and
{{ ngspice }} checked against {{ Xyce }} ({doc}`../limitations/engine-cross-check`); both are
summarised, with the current numbers, on the generated
{doc}`SPICE reference results </_generated/results/index>` page.

```{toctree}
:maxdepth: 1

agreement
pdk-spec-check
pdk-versions
process-data
```
