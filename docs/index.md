# gf180-tcad

**Can open-source physics simulation, given only public data, reproduce a chip maker's own
transistor models?**

This project tests that for the 5 V transistors of the open
{term}`GF180MCU` chip process from GlobalFoundries.

## The question

Chip designers simulate a circuit before it is made. Each transistor in that simulation is a
{term}`SPICE` model: equations the chip maker fits to its own measurements. GlobalFoundries
publishes these models in the {{ gf180mcu_pdk }}, an open
{term}`process design kit (PDK) <PDK>`.

{term}`TCAD` takes another route. It simulates the physics inside the transistor: its layers,
their thickness, their doping, and the {term}`electrons <electron>` and {term}`holes <hole>` that move in them. This project
builds a TCAD model of the GF180MCU transistors from public sources. It then measures how
closely the TCAD curves match the PDK's SPICE curves ({numref}`fig-index-flow`).

```{figure} /_generated/explained/project-flow-light.svg
:figclass: only-light
:name: fig-index-flow
:alt: Two columns of boxes joined by arrows. Left, grey: the PDK's SPICE models, a circuit simulator, reference curves. Right, green: public process data and the PDK's layouts, the TCAD, TCAD curves. A dashed arrow labelled fit runs from the reference curves into the TCAD. Both columns feed one comparison box at the bottom.

The two routes to the same curves. The grey column is the reference, the green column is what
is tested, and every pair of curves is compared at the bottom. The dashed arrow is the fit: the
TCAD's numbers are fitted to the reference curves.
```

```{figure} /_generated/explained/project-flow-dark.svg
:figclass: only-dark
:alt: Two columns of boxes joined by arrows. Left, grey: the PDK's SPICE models, a circuit simulator, reference curves. Right, green: public process data and the PDK's layouts, the TCAD, TCAD curves. A dashed arrow labelled fit runs from the reference curves into the TCAD. Both columns feed one comparison box at the bottom.

The two routes to the same curves. The grey column is the reference, the green column is what
is tested, and every pair of curves is compared at the bottom. The dashed arrow is the fit: the
TCAD's numbers are fitted to the reference curves.
```

## How the comparison works

The PDK's SPICE models are the {term}`reference <SPICE reference results>`, and the TCAD is what
is tested. A circuit simulator runs the SPICE models to give the reference curves. Three TCAD
numbers are fitted to those curves at three gate sizes: the oxide thickness, the body doping and
a voltage shift. The fitted TCAD is then tested in 1D at three sizes it never saw, and in 2D. So
what was fitted stays
apart from what was predicted.

The TCAD runs in two forms. The 1D form is one column down through the gate, its oxide and the
body: the column under the gate in {numref}`fig-index-cell`. The 2D form is a cross-section along the gate's length. Both run for
the two kinds of 5 V transistor, the {term}`nfet <nfet_05v0>` and the {term}`pfet <pfet_05v0>`.

Each pair of curves is judged {term}`Agree`, {term}`Same process` or {term}`Disagree`. Same
process means the TCAD lies inside the range the PDK specifies, not at its typical point.

```{figure} /_generated/explained/parts-cell-light.svg
:figclass: only-light
:name: fig-index-cell
:alt: Cross-section of the transistor: a gate on a thin oxide in the middle, a source on the left and a drain on the right at the surface, a large body below, contacts drawn as dark bars.

The simulated cross-section of the {term}`nfet_05v0`, 10 µm wide with a 0.7 µm gate, cut along the
gate's length. Blue parts are n-type and the orange body is p-type.
{{ x_fig_parts_cell_scale }}
```

```{figure} /_generated/explained/parts-cell-dark.svg
:figclass: only-dark
:alt: Cross-section of the transistor: a gate on a thin oxide in the middle, a source on the left and a drain on the right at the surface, a large body below, contacts drawn as dark bars.

The simulated cross-section of the {term}`nfet_05v0`, 10 µm wide with a 0.7 µm gate, cut along the
gate's length. Blue parts are n-type and the orange body is p-type.
{{ x_fig_parts_cell_scale }}
```

## Why it matters

A TCAD model that matches the SPICE models explains them from physics. It can also reach sizes
and devices the models do not cover, once it has earned confidence here. Every mismatch is
listed with its cause and the evidence for it. Every script and result is in the repository,
under an open licence, and every input is pinned to an exact version.

## Where it stands

- **The reference is complete.** The SPICE curves are committed and rebuild byte for byte on a
  second computer.
- **The TCAD covers the gate only.** It simulates how much charge the gate holds as its voltage
  changes, the {term}`C–V` curve. It has no result for the transistor's current.
- **In 1D the nfet matches and the pfet only in part.** The nfet agrees at every size. The
  pfet disagrees at two of its three fitted sizes ({numref}`fig-index-cv`) and is Same
  process or Agree at the rest.
- **The 2D cross-sections are mixed.** The calibrated 2D cross-sections carry a fitted poly
  length bias. Two are Agree, four Same process and four Disagree, all four on the
  {term}`depletion` crossing.
- **{{ Charon }} agrees with {{ DEVSIM }} in 1D.** In experiments the C differs by at most
  {{ lim_charon_nfet_devsim }} (nfet) and {{ lim_charon_pfet_devsim }} (pfet). Every committed
  TCAD result is DEVSIM's ({doc}`limitations/charon`).
- **No chip has been measured.** No silicon data exists to check either model against.

{doc}`limitations/status` lists every committed result, its folder and its verdict.

```{figure} /_generated/explained/cv-overview-light.svg
:figclass: only-light
:name: fig-index-cv
:alt: Gate capacitance against gate voltage, nfet above and pfet below: SPICE curves in a grey band, with dotted and dashed 1D lines and dash-dot 2D lines.

The gate's capacitance against its voltage at the shortest gate, nfet above and pfet below. The
solid line is the SPICE model, inside the grey band of its {{ x_corner_count }}
{term}`corners <corner>`. The dotted and dashed lines are the 1D TCAD before and after fitting.
The dash-dot lines are the 2D cross-section before (orange) and after (blue).
```

```{figure} /_generated/explained/cv-overview-dark.svg
:figclass: only-dark
:alt: Gate capacitance against gate voltage, nfet above and pfet below: SPICE curves in a grey band, with dotted and dashed 1D lines and dash-dot 2D lines.

The gate's capacitance against its voltage at the shortest gate, nfet above and pfet below. The
solid line is the SPICE model, inside the grey band of its {{ x_corner_count }}
{term}`corners <corner>`. The dotted and dashed lines are the 1D TCAD before and after fitting.
The dash-dot lines are the 2D cross-section before (orange) and after (blue).
```

## Should you read on?

- **You design circuits on GF180MCU:** {doc}`comparison/index` shows how far the transistor
  models can be rebuilt from physics.
- **You work on open-source TCAD:** {doc}`reproduce/index` rebuilds every result, and
  {doc}`limitations/index` lists what is missing.
- **You are learning how transistors work:** {doc}`explained/index` explains each part with this
  process's numbers.

## The documentation

The documentation has five sections, plus a glossary and the API reference:

- {doc}`explained/index`: how a transistor works, with this project's numbers.
- {doc}`reproduce/index`: how to rebuild every result.
- {doc}`results/index`: the SPICE reference and the TCAD results.
- {doc}`comparison/index`: the TCAD against the PDK, with each verdict.
- {doc}`limitations/index`: what is missing, and the project status.

Planned work, each item with its issue, is on the {doc}`roadmap`. The {doc}`glossary` defines
every term.

```{toctree}
:maxdepth: 2
:hidden:

explained/index
reproduce/index
results/index
comparison/index
limitations/index
roadmap
glossary
api/index
```
